import pandas as pd
import numpy as np
import networkx as nx
import os
import sys

def clean_dataframe_columns(df, exclude_cols=None):
    if exclude_cols is None:
        exclude_cols = []
    df_cleaned = df.copy()

    for col in df_cleaned.columns:
        if col not in exclude_cols:
            # Converte para string, limpa espaços e troca vírgula por ponto
            df_cleaned[col] = (
                df_cleaned[col]
                .astype(str)
                .str.replace('"', '', regex=False)
                .str.strip()
                .str.replace(',', '.', regex=False)
            )
            # Converte para float final
            df_cleaned[col] = pd.to_numeric(df_cleaned[col], errors='coerce')
    
    return df_cleaned

FILE_SCHEMAS = {
    "reservoir.csv": {
        "names": ['subasin_id', 'water_storage_capacity', 'dam_height', 'spillway_discharge'],
        "decimal": ","
    },
    "routing.csv": {
        "names": ['subasin_id', 'upstream', 'downstream'],
        "decimal": "."
    },
    "runoff.csv": {
        "names": ['subasin_id', 'runoff_volume', 'runoff_peak_discharge'],
        "decimal": "."
    },
    "sedyield.csv": {
        "names": ['subasin_id', 'sed_enter_volume'],
        "decimal": "."
    },
    "sed_param.csv": {
        "names": ['subasin_id','sediment_density', 'sediment_retention_efficiency'],
        "decimal": "."
    }
}

def load_csv_file(file_path, schema_config, clean_function):

    qtd_colunas_esperadas = len(schema_config["names"])

    df = pd.read_table(
        file_path,
        encoding='latin1',
        skiprows=1,
        sep='\t',
        quotechar='"',
        engine='python'
    )

    if df.shape[1] != qtd_colunas_esperadas:
        raise ValueError(
            f"O arquivo tem {df.shape[1]} colunas, "
            f"mas eram esperadas {qtd_colunas_esperadas}."
        )

    df.columns = schema_config["names"]

    df = clean_function(df, exclude_cols=['subasin_id'])

    return df

def calculate_water_routing(df_reservoir, df_routing, df_runoff):

    df_routing = df_routing.copy()
    df_routing['downstream'] = df_routing['downstream'].replace(-999, np.nan)

    df_merged = df_reservoir.merge(df_runoff, on='subasin_id', how='left')
    node_attrs = df_merged.set_index('subasin_id').to_dict(orient='index')

    df_edges = df_routing.dropna(subset=['downstream']).copy()
    df_edges['upstream'] = df_edges['upstream'].astype(int)
    df_edges['downstream'] = df_edges['downstream'].astype(int)

    G = nx.from_pandas_edgelist(
        df_edges,
        source='upstream',
        target='downstream',
        create_using=nx.DiGraph()
    )

    nx.set_node_attributes(G, node_attrs)

    sequencia = list(nx.topological_sort(G))

    peak_in = {}
    peak_out = {}
    volume_in = {}
    volume_out = {}
    ruptura_dict = {}

    for i in sequencia:

        upstreams = list(G.predecessors(i))

        if upstreams:
            volume_in[i] = (
                G.nodes[i]['runoff_volume'] +
                sum(volume_out[up] for up in upstreams)
            )
            peak_in[i] = (
                G.nodes[i]['runoff_peak_discharge'] +
                sum(peak_out[up] for up in upstreams)
            )
        else:
            volume_in[i] = G.nodes[i]['runoff_volume']
            peak_in[i] = G.nodes[i]['runoff_peak_discharge']

        spillway = G.nodes[i]['spillway_discharge']
        storage_capacity = G.nodes[i]['water_storage_capacity']

        rompeu = (0.707121014402343 * peak_in[i] > spillway)
        ruptura_dict[i] = rompeu

        if rompeu:
            volume_out[i] = volume_in[i] + storage_capacity
            peak_out[i] = 0.0344 * (volume_out[i] ** 0.6527)
        else:
            volume_out[i] = volume_in[i]
            peak_out[i] = 0.707121014402343 * peak_in[i]

    result = pd.DataFrame({
        "subasin_id": df_runoff["subasin_id"],
        "volume_entrada": df_runoff["subasin_id"].map(volume_in).astype(int),
        "volume_total": df_runoff["subasin_id"].map(volume_out).astype(int),
        "vazão_de_entrada": df_runoff["subasin_id"].map(peak_in).round(2),
        "vazão_de_saida": df_runoff["subasin_id"].map(peak_out).round(2),
        "rompeu": df_runoff["subasin_id"].map(ruptura_dict)
    })

    return result, G, ruptura_dict, sequencia, df_merged

def calculate_sediment_routing(
    result_discharge,
    G,
    ruptura_dict,
    sequencia_processamento,
    df_sedyield,
    df_merged,
    radio_mode,
    df_sed_param=None,
    density_manual=None,
    efficiency_manual=None):

    # adiciona atributos de sedimento no grafo
    sed_attrs = df_sedyield.set_index('subasin_id').to_dict(orient='index')
    nx.set_node_attributes(G, sed_attrs)

    pm_fenda = 0.842584358697712
    m = 0.0261
    n = 0.769

    default_density = density_manual if density_manual else 1.5
    default_efficiency = efficiency_manual if efficiency_manual else 0.50

    # --- modo arquivo ---
    if radio_mode == 1:
        density_map = dict(zip(
            df_sed_param['subasin_id'],
            df_sed_param['sediment_density']
        ))
        efficiency_map = dict(zip(
            df_sed_param['subasin_id'],
            df_sed_param['sediment_retention_efficiency']
        ))
    else:
        density_map = {}
        efficiency_map = {}

    sedimentos_discharge = pd.DataFrame()
    sedimentos_discharge["subasin_id"] = result_discharge["subasin_id"]

    sedimentos_discharge['volume_sedimento_erodido'] = (
        result_discharge['rompeu'] * m *
        (result_discharge['volume_total'] * pm_fenda * df_merged['dam_height']) ** n
    ).round(2)

    sed_in = {}
    sed_out = {}

    for i in sequencia_processamento:

        upstreams = list(G.predecessors(i))

        if radio_mode == 1:
            current_density = density_map.get(i, default_density)
            current_efficiency = efficiency_map.get(i, default_efficiency)
        else:
            current_density = default_density
            current_efficiency = default_efficiency

        sed_local = G.nodes[i]['sed_enter_volume']

        if upstreams:
            sed_in[i] = sed_local + sum(sed_out[up] for up in upstreams)
        else:
            sed_in[i] = sed_local

        if ruptura_dict[i]:
            vol_erodido = sedimentos_discharge.loc[
                sedimentos_discharge['subasin_id'] == i,
                'volume_sedimento_erodido'
            ].values[0]

            massa_erodida = vol_erodido * current_density
            sed_out[i] = sed_in[i] + massa_erodida
        else:
            sed_out[i] = current_efficiency * sed_in[i]

    sedimentos_discharge['sedimento_afluente'] = (
        sedimentos_discharge['subasin_id'].map(sed_in).round(2)
    )

    sedimentos_discharge['sedimento_efluente'] = (
        sedimentos_discharge['subasin_id'].map(sed_out).round(2)
    )

    return result_discharge.merge(
        sedimentos_discharge,
        on='subasin_id'
    )


def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funciona em dev e PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)