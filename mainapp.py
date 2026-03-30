#myapp.py
import logging
import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import networkx as nx
import numpy as np
from data_utils import clean_dataframe_columns, FILE_SCHEMAS, load_csv_file, resource_path
import sys
import os



logger = logging.getLogger(__name__)
FORMAT = '%(asctime)s - %(levelname)s: %(message)s'
logging.basicConfig(filename='myapp.log', level=logging.INFO,format=FORMAT)
logger.info('Started')

dataframes = {}

def selecionar_arquivo(entry_widget, chave):

    file_path = filedialog.askopenfilename(
        title=f"Selecionar arquivo {chave}",
        filetypes=[("Arquivos CSV e DAT", ("*.csv", "*.dat")),
                    ("Arquivos CSV", "*.csv"),
                    ("Arquivos DAT", "*.dat"),
                    ("Todos os arquivos", "*")]
    )

    if not file_path:
        return

    entry_widget.config(state=tk.NORMAL)
    entry_widget.delete(0, tk.END)
    entry_widget.insert(0, file_path)
    entry_widget.config(state=tk.DISABLED)

    try:
        config = FILE_SCHEMAS[chave]

        df = load_csv_file(
            file_path,
            config,
            clean_dataframe_columns
        )

        dataframes[chave] = df

        txt_saida['state'] = tk.NORMAL
        txt_saida.insert(tk.END, f"Arquivo '{chave}' carregado com sucesso\n")
        txt_saida.see(tk.END)
        txt_saida['state'] = tk.DISABLED

    except Exception as e:
        messagebox.showerror(
            "Erro",
            f"Erro ao ler o arquivo {chave}:\n{e}"
        )

        txt_saida['state'] = tk.NORMAL
        txt_saida.insert(tk.END, f"Erro ao ler o arquivo {chave}:\n{e}\n")
        txt_saida.see(tk.END)
        txt_saida['state'] = tk.DISABLED


def toggle_sedimentos():
    
    # Define o estado com base no valor do checkbox
    novo_estado = tk.NORMAL if sedimentos_checkbox.get() else tk.DISABLED
    #                NORMAL = HABILITADO DISABLED = DESABILITADO
    # Lista de componentes que devem ser habilitados/desabilitados
    componentes = [ent_sed, btn_sed, rb_file, rb_manual, ent_param_file, btn_param_file, ent_density, ent_efficiency]
    
    for comp in componentes:
        comp.config(state=novo_estado)

# --- Interface Principal ---
root = tk.Tk()
root.title("Simulador Hidrológico")
root.geometry("650x800")

# 1. ENTRADA DE DADOS
frame_entrada = tk.LabelFrame(root, text="Entrada de dados", padx=10, pady=10)
# pad adiciona espaço interno

frame_entrada.pack(fill="x", padx=20, pady=10)
#o pack com fill="x" faz o frame ocupar toda a largura disponível, então esse retagunlo em especifico
#vai ser o retangulo que engloba toda a seção de entrada de dados
labels = ["routing.csv", "runoff.csv", "reservoir.csv"]

row_name = tk.Frame(frame_entrada)
row_name.pack(fill="x", pady=2)
tk.Label(row_name, text=f"Nome do arquivo de saída:", width=25, anchor="w").pack(side="left")
ent_name = tk.Entry(row_name, state=tk.NORMAL)
ent_name.insert(0, "result_discharge")
ent_name.pack(side='left', expand=True,fill='x',padx=5)

for label in labels:
    row = tk.Frame(frame_entrada)
    row.pack(fill="x", pady=2)

    tk.Label(row, text=f"Carregar arquivo {label}:", width=25, anchor="w").pack(side="left")

    ent = tk.Entry(row, textvariable=label, state=tk.DISABLED)
    ent.pack(side="left", expand=True, fill="x", padx=5)

    tk.Button(
        row,
        text="...",
        command=lambda e=ent, l=label: selecionar_arquivo(e, l)
    ).pack(side="right")


# 2. SIMULAR DINÂMICA DE SEDIMENTOS
sedimentos_checkbox = tk.BooleanVar(value=False) # Começa DESMARCADA
frame_sedimentos = tk.LabelFrame(root, padx=15, pady=10)
frame_sedimentos.pack(fill="x", padx=20, pady=10)

check_btn = tk.Checkbutton(frame_sedimentos, text="Simular dinâmica de sedimentos", 
                           variable=sedimentos_checkbox, command=toggle_sedimentos, font=('Arial', 10, 'bold'))

frame_sedimentos.configure(labelwidget=check_btn)

# Linha do arquivo sedyield.csv
row_sed = tk.Frame(frame_sedimentos)
row_sed.pack(fill="x", pady=5)
tk.Label(row_sed, text="Carregar arquivo sedyield.csv:", width=25, anchor="w").pack(side="left")
ent_sed = tk.Entry(row_sed, state=tk.DISABLED)
ent_sed.pack(side="left", expand=True, fill="x", padx=5)
btn_sed = tk.Button(row_sed, text="...", state=tk.DISABLED, command=lambda: selecionar_arquivo(ent_sed, "sedyield.csv"))
btn_sed.pack(side="right")

# Sub-seção Parâmetros Sedimentológicos

subframe_params = tk.LabelFrame(frame_sedimentos, text="Parâmetros sedimentológicos", padx=10, pady=10)
subframe_params.pack(fill="x", pady=5)

radio_var = tk.IntVar(value=1)

# Opção 1: Carregar do arquivo
row_p1 = tk.Frame(subframe_params)
row_p1.pack(fill="x")
rb_file = tk.Radiobutton(row_p1, text="Carregar do arquivo:", variable=radio_var, value=1, state=tk.DISABLED)
rb_file.pack(side="left")
ent_param_file = tk.Entry(row_p1, state=tk.DISABLED)
ent_param_file.pack(side="left", expand=True, fill="x", padx=5)
btn_param_file = tk.Button(row_p1, text="...", state=tk.DISABLED, command=lambda: selecionar_arquivo(ent_param_file, "sed_param.csv"))
btn_param_file.pack(side="right")

# Opção 2: Valores manuais
rb_manual = tk.Radiobutton(subframe_params, text="Utilizar valores abaixo:", variable=radio_var, value=2, state=tk.DISABLED)
rb_manual.pack(anchor="w")

# Campos de densidade e eficiência
row_manual = tk.Frame(subframe_params)
row_manual.pack(fill="x", padx=20)

default_density = 1.5  # g/cm³
default_efficiency = 0.50  # 50%

tk.Label(
    row_manual,
    text="Densidade aparente seca da barragem de terra :"
).grid(row=0, column=0, sticky="w")

ent_density = tk.Entry(row_manual, width=6, state=tk.NORMAL)
ent_density.grid(row=0, column=1, padx=(5,0), pady=2)
ent_density.insert(0, str(default_density))
ent_density.config(state=tk.DISABLED)

tk.Label(row_manual, text="g/cm³").grid(row=0, column=2, sticky="w")

# EFICIÊNCIA
tk.Label(
    row_manual,
    text="Eficiência da retenção de sedimentos em reservatórios:"
).grid(row=1, column=0, sticky="w")

ent_efficiency = tk.Entry(row_manual, width=6, state=tk.NORMAL)
ent_efficiency.grid(row=1, column=1, padx=(5, 0), pady=2)
ent_efficiency.insert(0, str(default_efficiency * 100))
ent_efficiency.config(state=tk.DISABLED)

tk.Label(row_manual, text="%").grid(row=1, column=2, sticky="w")

# FUNÇÃO PRINCIPAL DE CÁLCULO

def on_calcular_click():
    try:

        if ent_name.get():
            nome = ent_name.get()
        else:
            nome = "result_discharge"

        logger.info('Cálculo iniciado pelo usuário')

        txt_saida['state'] = tk.NORMAL
        txt_saida.insert(tk.END, f"Cálculo iniciado pelo usuário...\n")
        txt_saida.see(tk.END)
        txt_saida['state'] = tk.DISABLED

        df_reservoir = dataframes.get('reservoir.csv')
        df_routing = dataframes.get('routing.csv')
        df_runoff = dataframes.get('runoff.csv')

        df_routing['downstream'] = df_routing['downstream'].replace(-999, np.nan)

        df_merged = (df_reservoir.merge(df_runoff, on='subasin_id', how='left'))
        node_attrs = (df_merged.set_index('subasin_id').to_dict(orient='index'))

        logger.info('DataFrames mesclados para construção do grafo')

        txt_saida['state'] = tk.NORMAL
        txt_saida.insert(tk.END, f"Construindo grafo das rotas...\n")
        txt_saida.see(tk.END)
        txt_saida['state'] = tk.DISABLED

        df_edges = df_routing.dropna(subset=['downstream'])
        df_edges = df_routing.dropna(subset=['downstream']).copy()
        df_edges['upstream'] = df_edges['upstream'].astype(int)
        df_edges['downstream'] = df_edges['downstream'].astype(int)

    # Cria um grafo direcionado (DiGraph) a partir do DataFrame.
        G = nx.from_pandas_edgelist(
                df_edges,
                source='upstream',
                target='downstream',
                create_using=nx.DiGraph()
            )
        
        txt_saida['state'] = tk.NORMAL
        txt_saida.insert(tk.END, f"Preparando sequencia de processamento...\n")
        txt_saida.see(tk.END)
        txt_saida['state'] = tk.DISABLED

        nx.set_node_attributes(G, node_attrs) #usando nx para determinar os atributos do grafo G com os dados do dicionario node_attrs

        sequencia_processamento = list(nx.topological_sort(G))

        #cria um dataframe tendo como base os ids dos açudes
        result_discharge = pd.DataFrame(columns=["subasin_id"])
        result_discharge["subasin_id"] = df_runoff["subasin_id"]    

        peak_in = {} # Vazão de pico na entrada - water routing (m³/s)
        peak_out = {} # Vazão de pico na saída - water routing (m³/s)
        volume_in = {} # Volume na entrada do açude - water routing (m³)
        volume_out = {} # Volume na saída do açude - water routing (m³)
        ruptura_dict = {} # Contador de casos de ruptura (m³/s)
        

        txt_saida['state'] = tk.NORMAL
        txt_saida.insert(tk.END, f"Calculando casos de ruptura...\n")
        txt_saida.see(tk.END)
        txt_saida['state'] = tk.DISABLED

        for i in sequencia_processamento:

            upstreams = list(G.predecessors(i))  #lista com todos os predecessores do açude atual

            # 1. Entradas (volume e pico)

            if upstreams:     #se ele tiver predecessores

                volume_in[i] = (G.nodes[i]['runoff_volume']+ sum(volume_out[up] for up in upstreams)) # o volume de entrada será o volume dele, mais a soma do volume de todos os predecessores na lista pega anteriormente

                peak_in[i] = (G.nodes[i]['runoff_peak_discharge'] + sum(peak_out[up] for up in upstreams))   # a mesma ideia ocorre aqui para o valor de pico de SAIDA
            else:
                volume_in[i] = G.nodes[i]['runoff_volume']
                peak_in[i] = G.nodes[i]['runoff_peak_discharge']       #caso ele seja uma folha (sem predecessores), os valores serão os próprios dele mesmo.

            # 2. Dados do açude

            spillway = G.nodes[i]['spillway_discharge']
            storage_capacity = G.nodes[i]['water_storage_capacity']    #limite do vertedouro do açude i, bem como a sua capacidade

            # 3. Verificação de ruptura
            # o valor 0.707121014402343, representa o percentual médio do volume efluente que passa pela fenda:

            rompeu = (0.707121014402343 * peak_in[i] > spillway)
            ruptura_dict[i] = rompeu

            # 4. Saídas (volume e pico)

            if rompeu:
                volume_out[i] = volume_in[i] + storage_capacity
                peak_out[i] = 0.0344 * (volume_out[i] ** 0.6527)

                """ print(
                    f"Volume: {volume_out[i]:.2f} | "
                    f"Açude {i} ROMPEU | "
                    f"Peak in = {peak_in[i]:.2f} | "
                    f"Peak out = {peak_out[i]:.2f}"
                ) """

            else:
                volume_out[i] = volume_in[i]
                peak_out[i] = 0.707121014402343 * peak_in[i]

        result_discharge['volume_entrada'] = result_discharge['subasin_id'].map(volume_in).astype(int)
        result_discharge['volume_total'] = result_discharge['subasin_id'].map(volume_out).astype(int)
        result_discharge['vazão_de_entrada'] = result_discharge['subasin_id'].map(peak_in).round(2)
        result_discharge['vazão_de_saida'] = result_discharge['subasin_id'].map(peak_out).round(2)
        result_discharge['rompeu'] = result_discharge['subasin_id'].map(ruptura_dict)

        
        if sedimentos_checkbox.get():

        
            df_sedyield = dataframes.get('sedyield.csv')

            print("Nós do grafo:", list(G.nodes))
            print(df_sedyield.head())
            
            if df_sedyield is not None:
                sed_attrs = df_sedyield.set_index('subasin_id').to_dict(orient='index')
                nx.set_node_attributes(G, sed_attrs)
            else:
                messagebox.showerror(
                    "Erro",
                    "Arquivo sedyield.csv não carregado."
                )
                txt_saida['state'] = tk.NORMAL
                txt_saida.insert(tk.END, f"Erro: Arquivo sedyield.csv não carregado.\n")
                txt_saida.see(tk.END)
                txt_saida['state'] = tk.DISABLED
                return

            
            
            txt_saida['state'] = tk.NORMAL
            txt_saida.insert(tk.END, f"Calculando sedimentos...\n")
            txt_saida.see(tk.END)
            txt_saida['state'] = tk.DISABLED

            pm_fenda = 0.842584358697712
            m = 0.0261
            n = 0.769

            # Acessar os valores
            # --- Lógica de Acesso aos Parâmetros ---
            if radio_var.get() == 1:
                # MODO ARQUIVO
                df_sed_param = dataframes.get('sed_param.csv')
                if df_sed_param is not None:
                    # Criar dicionários mapeando subasin_id para os valores
                    density_map = dict(zip(df_sed_param['subasin_id'], df_sed_param['sediment_density']))
                    efficiency_map = dict(zip(df_sed_param['subasin_id'], df_sed_param['sediment_retention_efficiency']))
                else:
                    messagebox.showerror("Erro", "Arquivo sed_param.csv não carregado.")
                    return
            else:
                # MODO MANUAL
                try:
                    # Limpa string de % ou vírgulas e converte
                    val_dens = ent_density.get().replace(',', '.')
                    val_eff = ent_efficiency.get().replace(',', '.').replace('%', '')
                    
                    default_density = float(val_dens) if val_dens else 1.5
                    # Se for eficiência em %, divide por 100
                    default_efficiency = float(val_eff) / 100 if val_eff else 0.50
                    
                    # Criamos dicionários vazios, pois usaremos o valor padrão no .get() dentro do loop
                    density_map = {}
                    efficiency_map = {}
                except ValueError:
                    messagebox.showerror("Erro", "Valores manuais de densidade ou eficiência inválidos.")
                    return
            
            sedimentos_discharge = pd.DataFrame(columns=["subasin_id"])
            sedimentos_discharge["subasin_id"] = result_discharge["subasin_id"]

            sedimentos_discharge['volume_sedimento_erodido'] = (
                result_discharge['rompeu'] * m * ( result_discharge['volume_total'] * pm_fenda * df_merged['dam_height'] ) ** n).round(2)

            sedimentos_discharge['massa_sedimento_erodido'] = (
                sedimentos_discharge['volume_sedimento_erodido'] * default_density
            ).round(2)

            sed_in = {} # Massa de sedimentos afluente - sediment routing (ton)
            sed_out = {} # Massa de sedimentos efluente - sediment routing (ton)

            logger.info('Iniciando cálculo de sedimentos')
            
            print(G.nodes)

            for i in sequencia_processamento:

                upstreams = list(G.predecessors(i)) #lista com todas as bacias acima da bacia atual

                # Tenta pegar do mapa (arquivo). Se não existir ou for modo manual, usa o default
                if radio_var.get() == 1:
                    # No modo arquivo, se o ID não existir no .csv, você pode definir um fallback
                    current_density = density_map.get(i)
                    current_efficiency = efficiency_map.get(i)
                else:
                    current_density = default_density
                    current_efficiency = default_efficiency

                sed_local = G.nodes[i]['sed_enter_volume'] 

                if upstreams:
                    sed_in[i] = sed_local + sum(sed_out[up] for up in upstreams)
                else:
                    sed_in[i] = sed_local

                # 2. Saída de sedimentos
                if ruptura_dict[i]:
                    # Cálculo da massa erodida local usando a densidade específica deste nó
                    vol_erodido = sedimentos_discharge.loc[sedimentos_discharge['subasin_id'] == i, 'volume_sedimento_erodido'].values[0]
                    massa_erodida = vol_erodido * current_density
                    
                    sed_out[i] = sed_in[i] + massa_erodida
                else:
                    # Se não rompeu, aplica a eficiência de retenção
                    sed_out[i] = current_efficiency * sed_in[i]

                """ print(
                    f"Açude {i} | "
                    f"Sed_in = {sed_in[i]:.2f} | "
                    f"Sed_out = {sed_out[i]:.2f} | "
                    f"Rompeu = {ruptura_dict[i]}"
                ) """

            logger.info('Finalizando cálculo de sedimentos')

            sedimentos_discharge['sedimento_afluente'] = (sedimentos_discharge['subasin_id'].map(sed_in).round(2))
            sedimentos_discharge['sedimento_efluente'] = (    sedimentos_discharge['subasin_id'].map(sed_out).round(2))

            result_discharge = result_discharge.merge(
                sedimentos_discharge,
                on='subasin_id')
            """ print("result_discharge com sedimentos:")
            print(result_discharge.head(10)) """

        result_discharge.to_csv(f"{nome}.csv", index=False)

        """ print("calculo de sedimentos finalizado!") """

        txt_saida['state'] = tk.NORMAL
        txt_saida.insert(tk.END, f"O arquivo {nome}.csv foi gerado com sucesso! \n")
        txt_saida.see(tk.END)
        txt_saida['state'] = tk.DISABLED

    except Exception as e:
        import traceback
        erro = traceback.format_exc()
        messagebox.showerror("Erro inesperado", erro)
        logger.exception("Erro inesperado")

    

btn_calcular = tk.Button(root, command=on_calcular_click, text="Calcular", bg="#d9d9d9", font=('Arial', 12, 'bold'), height=2)
btn_calcular.pack(pady=15, padx=20, fill="x")

# 4. ÁREA DE SAÍDA (LOG)    
frame_saida = tk.LabelFrame(root, text="Saída", padx=10, pady=10)
frame_saida.pack(fill="both", expand=True, padx=20, pady=10)
txt_saida = tk.Text(frame_saida, height=6, bg="#ffffff", state=tk.DISABLED)
txt_saida.pack(fill="both", expand=True)

root.iconbitmap(resource_path("icon.ico"))

root.mainloop()

logger.info('Finished') 
