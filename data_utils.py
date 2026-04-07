# data_utils.py
import os
import sys

import pandas as pd
import numpy as np
import networkx as nx

from constants import (
    COEF_FENDA_PEAK,
    COEF_RUPTURA_A,
    COEF_RUPTURA_B,
    COEF_FENDA_SED,
    COEF_SED_M,
    COEF_SED_N,
    DEFAULT_DENSITY,
    DEFAULT_EFFICIENCY,
)


def clean_dataframe_columns(df: pd.DataFrame, exclude_cols: list = None) -> pd.DataFrame:
    """Limpa strings e garante que todas as colunas sejam numéricas."""
    if exclude_cols is None:
        exclude_cols = []

    df_cleaned = df.copy()
    for col in df_cleaned.columns:
        # Limpeza de caracteres (apenas para colunas que NÃO estão no exclude_cols)
        if col not in exclude_cols:
            df_cleaned[col] = (
                df_cleaned[col]
                .astype(str)
                .str.replace('"', '', regex=False)
                .str.strip()
                .str.replace(',', '.', regex=False)
            )
        
        # CONVERSÃO CRÍTICA: Força todas as colunas (incluindo subasin_id) 
        # a serem numéricas para evitar erro de merge entre str e int.
        df_cleaned[col] = pd.to_numeric(df_cleaned[col], errors='coerce')

    return df_cleaned


FILE_SCHEMAS = {
    "reservoir.csv": {
        "names": ['subasin_id', 'water_storage_capacity', 'dam_height', 'spillway_discharge'],
        "decimal": ",",
    },
    "routing.csv": {
        "names": ['subasin_id', 'upstream', 'downstream'],
        "decimal": ".",
    },
    "runoff.csv": {
        "names": ['subasin_id', 'runoff_volume', 'runoff_peak_discharge'],
        "decimal": ".",
    },
    "sedyield.csv": {
        "names": ['subasin_id', 'sed_enter_volume'],
        "decimal": ",",
    },
    "sed_param.csv": {
        "names": ['subasin_id', 'sediment_density', 'sediment_retention_efficiency'],
        "decimal": ".",
    },
}


def _detectar_separador(file_path: str) -> str:
    """
    Lê as primeiras linhas do arquivo e detecta o separador mais provável
    entre: tabulação, ponto-e-vírgula, vírgula e espaço.
    """
    with open(file_path, encoding='latin1') as f:
        # Pula o cabeçalho descritivo e lê a linha de dados
        linhas = [f.readline() for _ in range(3)]

    amostra = ''.join(linhas)
    contagens = {sep: amostra.count(sep) for sep in ['\t', ';', ',']}
    return max(contagens, key=contagens.get)


def load_csv_file(file_path: str, schema_config: dict, clean_function) -> pd.DataFrame:
    """
    Lê um arquivo CSV/DAT tabulado, valida o número de colunas,
    renomeia conforme o schema e limpa os dados.
    Detecta automaticamente o separador (tab, ; ou ,).
    """
    qtd_colunas_esperadas = len(schema_config["names"])

    separador = _detectar_separador(file_path)

    df = pd.read_table(
        file_path,
        encoding='latin1',
        skiprows=1,
        sep=separador,
        quotechar='"',
        engine='python',
    )

    # CORREÇÃO 1: Remove colunas extras completamente vazias.
    # Arquivos .dat/.csv costumam ter separadores extras no final de cada linha,
    # o que gera colunas fantasmas que quebravam a validação.
    df = df.dropna(axis=1, how='all')

    if df.shape[1] != qtd_colunas_esperadas:
        raise ValueError(
            f"O arquivo tem {df.shape[1]} colunas, "
            f"mas eram esperadas {qtd_colunas_esperadas}."
        )

    df.columns = schema_config["names"]
    df = clean_function(df, exclude_cols=['subasin_id'])
    return df


def calculate_water_routing(
    df_reservoir: pd.DataFrame,
    df_routing: pd.DataFrame,
    df_runoff: pd.DataFrame,
) -> tuple:
    """
    Constrói o grafo direcionado e executa o roteamento hídrico em ordem topológica.

    Retorna:
        result       (DataFrame) — volume e vazão de entrada/saída e flag de ruptura
        G            (DiGraph)   — grafo com atributos dos nós
        ruptura_dict (dict)      — mapeamento subasin_id → bool de ruptura
        sequencia    (list)      — ordem topológica de processamento
        df_merged    (DataFrame) — reservoir + runoff mesclados
    """
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
        create_using=nx.DiGraph(),
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
            volume_in[i] = G.nodes[i]['runoff_volume'] + sum(volume_out[up] for up in upstreams)
            peak_in[i] = G.nodes[i]['runoff_peak_discharge'] + sum(peak_out[up] for up in upstreams)
        else:
            volume_in[i] = G.nodes[i]['runoff_volume']
            peak_in[i] = G.nodes[i]['runoff_peak_discharge']

        spillway = G.nodes[i]['spillway_discharge']
        storage_capacity = G.nodes[i]['water_storage_capacity']

        rompeu = COEF_FENDA_PEAK * peak_in[i] > spillway
        ruptura_dict[i] = rompeu

        if rompeu:
            volume_out[i] = volume_in[i] + storage_capacity
            peak_out[i] = COEF_RUPTURA_A * (volume_out[i] ** COEF_RUPTURA_B)
        else:
            volume_out[i] = volume_in[i]
            peak_out[i] = COEF_FENDA_PEAK * peak_in[i]

    result = pd.DataFrame({
        "subasin_id":       df_runoff["subasin_id"],
        "volume_entrada":   df_runoff["subasin_id"].map(volume_in).round(4),
        "volume_total":     df_runoff["subasin_id"].map(volume_out).round(4),
        "vazão_de_entrada": df_runoff["subasin_id"].map(peak_in).round(4),
        "vazão_de_saida":   df_runoff["subasin_id"].map(peak_out).round(4),
        "rompeu":           df_runoff["subasin_id"].map(ruptura_dict),
    })

    return result, G, ruptura_dict, sequencia, df_merged


def calculate_sediment_routing(
    result_discharge: pd.DataFrame,
    G: nx.DiGraph,
    ruptura_dict: dict,
    sequencia_processamento: list,
    df_sedyield: pd.DataFrame,
    df_merged: pd.DataFrame,
    radio_mode: int,
    df_sed_param: pd.DataFrame = None,
    density_manual: float = None,
    efficiency_manual: float = None,
) -> pd.DataFrame:
    """
    Executa o roteamento de sedimentos no grafo em ordem topológica.

    radio_mode=1 → parâmetros lidos de df_sed_param
    radio_mode=2 → parâmetros manuais (density_manual, efficiency_manual)

    Retorna result_discharge enriquecido com as colunas de sedimento.
    """
    sed_attrs = df_sedyield.set_index('subasin_id').to_dict(orient='index')
    nx.set_node_attributes(G, sed_attrs)

    default_density = density_manual if density_manual is not None else DEFAULT_DENSITY
    default_efficiency = efficiency_manual if efficiency_manual is not None else DEFAULT_EFFICIENCY

    if radio_mode == 1:
        density_map = dict(zip(df_sed_param['subasin_id'], df_sed_param['sediment_density']))
        efficiency_map = dict(zip(df_sed_param['subasin_id'], df_sed_param['sediment_retention_efficiency']))
    else:
        density_map = {}
        efficiency_map = {}

    sed_discharge = pd.DataFrame()
    sed_discharge["subasin_id"] = result_discharge["subasin_id"]
    sed_discharge['volume_sedimento_erodido'] = (
        result_discharge['rompeu'] * COEF_SED_M
        * (result_discharge['volume_total'] * COEF_FENDA_SED * df_merged['dam_height']) ** COEF_SED_N
    ).round(4)

    # CORREÇÃO 2: Coluna massa_sedimento_erodido estava presente no código original
    # mas foi perdida na refatoração. Restaurada aqui usando a densidade padrão,
    # igual ao comportamento original (calculada antes do loop, com default_density).
    sed_discharge['massa_sedimento_erodido'] = (
        sed_discharge['volume_sedimento_erodido'] * default_density
    ).round(4)

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

        # CORREÇÃO 3: Uso de .get() com fallback 0.0 para evitar KeyError quando
        # um subasin_id do grafo não existe no arquivo sedyield (sem aresta no routing).
        sed_local = G.nodes[i].get('sed_enter_volume', 0.0)
        sed_in[i] = sed_local + sum(sed_out[up] for up in upstreams) if upstreams else sed_local

        if ruptura_dict[i]:
            vol_erodido = sed_discharge.loc[
                sed_discharge['subasin_id'] == i, 'volume_sedimento_erodido'
            ].values[0]
            sed_out[i] = sed_in[i] + vol_erodido * current_density
        else:
            sed_out[i] = current_efficiency * sed_in[i]

    sed_discharge['sedimento_afluente'] = sed_discharge['subasin_id'].map(sed_in).round(4)
    sed_discharge['sedimento_efluente'] = sed_discharge['subasin_id'].map(sed_out).round(4)

    return result_discharge.merge(sed_discharge, on='subasin_id')


def resource_path(relative_path: str) -> str:
    """Retorna o caminho absoluto para o recurso — funciona em dev e com PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
