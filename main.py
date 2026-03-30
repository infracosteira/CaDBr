# myapp.py
import logging
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

from data_utils import (
    clean_dataframe_columns,
    FILE_SCHEMAS,
    load_csv_file,
    resource_path,
    calculate_water_routing,
    calculate_sediment_routing,
)
from constants import DEFAULT_DENSITY, DEFAULT_EFFICIENCY, DEFAULT_OUTPUT_NAME

# --- Logging ---
FORMAT = '%(asctime)s - %(levelname)s: %(message)s'
logging.basicConfig(filename='myapp.log', level=logging.INFO, format=FORMAT)
logger = logging.getLogger(__name__)
logger.info('Started')

# --- Estado da aplicação ---
dataframes = {}


# ---------------------------------------------------------------------------
# Helpers de UI
# ---------------------------------------------------------------------------

def log_saida(msg: str) -> None:
    """Escreve uma linha na área de saída e faz scroll para o fim."""
    txt_saida['state'] = tk.NORMAL
    txt_saida.insert(tk.END, msg + '\n')
    txt_saida.see(tk.END)
    txt_saida['state'] = tk.DISABLED


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def selecionar_arquivo(entry_widget: tk.Entry, chave: str) -> None:
    """Abre o diálogo de seleção de arquivo e carrega o CSV/DAT correspondente."""
    file_path = filedialog.askopenfilename(
        title=f"Selecionar arquivo {chave}",
        filetypes=[
            ("Arquivos CSV e DAT", ("*.csv", "*.dat")),
            ("Arquivos CSV", "*.csv"),
            ("Arquivos DAT", "*.dat"),
            ("Todos os arquivos", "*"),
        ]
    )

    if not file_path:
        return

    entry_widget.config(state=tk.NORMAL)
    entry_widget.delete(0, tk.END)
    entry_widget.insert(0, file_path)
    entry_widget.config(state=tk.DISABLED)

    try:
        config = FILE_SCHEMAS[chave]
        df = load_csv_file(file_path, config, clean_dataframe_columns)
        dataframes[chave] = df
        log_saida(f"Arquivo '{chave}' carregado com sucesso")

    except Exception as e:
        messagebox.showerror("Erro", f"Erro ao ler o arquivo {chave}:\n{e}")
        log_saida(f"Erro ao ler o arquivo {chave}:\n{e}")


def toggle_sedimentos() -> None:
    """Habilita ou desabilita os controles da seção de sedimentos conforme o checkbox."""
    novo_estado = tk.NORMAL if sedimentos_checkbox.get() else tk.DISABLED
    componentes = [ent_sed, btn_sed, rb_file, rb_manual, ent_param_file, btn_param_file, ent_density, ent_efficiency]
    for comp in componentes:
        comp.config(state=novo_estado)


def _validar_dataframes_obrigatorios() -> bool:
    """Verifica se os três DataFrames obrigatórios foram carregados. Exibe erro e retorna False se faltar algum."""
    obrigatorios = ['reservoir.csv', 'routing.csv', 'runoff.csv']
    faltando = [k for k in obrigatorios if k not in dataframes]
    if faltando:
        messagebox.showerror("Erro", f"Arquivo(s) não carregado(s): {', '.join(faltando)}")
        return False
    return True


def _obter_parametros_sedimentos() -> tuple | None:
    """
    Lê os parâmetros sedimentológicos de acordo com o modo selecionado.

    Retorna (radio_mode, df_sed_param, density_manual, efficiency_manual)
    ou None em caso de erro.
    """
    if radio_var.get() == 1:
        df_sed_param = dataframes.get('sed_param.csv')
        if df_sed_param is None:
            messagebox.showerror("Erro", "Arquivo sed_param.csv não carregado.")
            return None
        return 1, df_sed_param, None, None
    else:
        try:
            val_dens = ent_density.get().replace(',', '.')
            val_eff = ent_efficiency.get().replace(',', '.').replace('%', '')
            density = float(val_dens) if val_dens else DEFAULT_DENSITY
            efficiency = float(val_eff) / 100 if val_eff else DEFAULT_EFFICIENCY
            return 2, None, density, efficiency
        except ValueError:
            messagebox.showerror("Erro", "Valores manuais de densidade ou eficiência inválidos.")
            return None


def on_calcular_click() -> None:
    """Callback do botão Calcular — orquestra leitura, cálculo e escrita do resultado."""
    try:
        if not _validar_dataframes_obrigatorios():
            return

        nome = ent_name.get() or DEFAULT_OUTPUT_NAME
        logger.info('Cálculo iniciado pelo usuário')
        log_saida("Cálculo iniciado pelo usuário...")

        log_saida("Construindo grafo das rotas...")
        log_saida("Calculando casos de ruptura...")

        result_discharge, G, ruptura_dict, sequencia, df_merged = calculate_water_routing(
            df_reservoir=dataframes['reservoir.csv'],
            df_routing=dataframes['routing.csv'],
            df_runoff=dataframes['runoff.csv'],
        )

        if sedimentos_checkbox.get():
            df_sedyield = dataframes.get('sedyield.csv')
            if df_sedyield is None:
                messagebox.showerror("Erro", "Arquivo sedyield.csv não carregado.")
                log_saida("Erro: Arquivo sedyield.csv não carregado.")
                return

            params = _obter_parametros_sedimentos()
            if params is None:
                return

            radio_mode, df_sed_param, density_manual, efficiency_manual = params

            log_saida("Calculando sedimentos...")

            result_discharge = calculate_sediment_routing(
                result_discharge=result_discharge,
                G=G,
                ruptura_dict=ruptura_dict,
                sequencia_processamento=sequencia,
                df_sedyield=df_sedyield,
                df_merged=df_merged,
                radio_mode=radio_mode,
                df_sed_param=df_sed_param,
                density_manual=density_manual,
                efficiency_manual=efficiency_manual,
            )

        result_discharge.to_csv(f"{nome}.csv", index=False)
        log_saida(f"O arquivo {nome}.csv foi gerado com sucesso!")

    except Exception:
        erro = traceback.format_exc()
        messagebox.showerror("Erro inesperado", erro)
        logger.exception("Erro inesperado")


# ---------------------------------------------------------------------------
# Interface Gráfica
# ---------------------------------------------------------------------------

root = tk.Tk()
root.title("Simulador Hidrológico")
root.geometry("650x800")

# 1. ENTRADA DE DADOS
frame_entrada = tk.LabelFrame(root, text="Entrada de dados", padx=10, pady=10)
frame_entrada.pack(fill="x", padx=20, pady=10)

labels = ["routing.csv", "runoff.csv", "reservoir.csv"]

row_name = tk.Frame(frame_entrada)
row_name.pack(fill="x", pady=2)
tk.Label(row_name, text="Nome do arquivo de saída:", width=25, anchor="w").pack(side="left")
ent_name = tk.Entry(row_name, state=tk.NORMAL)
ent_name.insert(0, DEFAULT_OUTPUT_NAME)
ent_name.pack(side='left', expand=True, fill='x', padx=5)

for label in labels:
    row = tk.Frame(frame_entrada)
    row.pack(fill="x", pady=2)
    tk.Label(row, text=f"Carregar arquivo {label}:", width=25, anchor="w").pack(side="left")
    ent = tk.Entry(row, state=tk.DISABLED)
    ent.pack(side="left", expand=True, fill="x", padx=5)
    tk.Button(
        row, text="...",
        command=lambda e=ent, l=label: selecionar_arquivo(e, l)
    ).pack(side="right")


# 2. SIMULAR DINÂMICA DE SEDIMENTOS
sedimentos_checkbox = tk.BooleanVar(value=False)
frame_sedimentos = tk.LabelFrame(root, padx=15, pady=10)
frame_sedimentos.pack(fill="x", padx=20, pady=10)

check_btn = tk.Checkbutton(
    frame_sedimentos,
    text="Simular dinâmica de sedimentos",
    variable=sedimentos_checkbox,
    command=toggle_sedimentos,
    font=('Arial', 10, 'bold'),
)
frame_sedimentos.configure(labelwidget=check_btn)

row_sed = tk.Frame(frame_sedimentos)
row_sed.pack(fill="x", pady=5)
tk.Label(row_sed, text="Carregar arquivo sedyield.csv:", width=25, anchor="w").pack(side="left")
ent_sed = tk.Entry(row_sed, state=tk.DISABLED)
ent_sed.pack(side="left", expand=True, fill="x", padx=5)
btn_sed = tk.Button(
    row_sed, text="...", state=tk.DISABLED,
    command=lambda: selecionar_arquivo(ent_sed, "sedyield.csv")
)
btn_sed.pack(side="right")

subframe_params = tk.LabelFrame(frame_sedimentos, text="Parâmetros sedimentológicos", padx=10, pady=10)
subframe_params.pack(fill="x", pady=5)

radio_var = tk.IntVar(value=1)

row_p1 = tk.Frame(subframe_params)
row_p1.pack(fill="x")
rb_file = tk.Radiobutton(row_p1, text="Carregar do arquivo:", variable=radio_var, value=1, state=tk.DISABLED)
rb_file.pack(side="left")
ent_param_file = tk.Entry(row_p1, state=tk.DISABLED)
ent_param_file.pack(side="left", expand=True, fill="x", padx=5)
btn_param_file = tk.Button(
    row_p1, text="...", state=tk.DISABLED,
    command=lambda: selecionar_arquivo(ent_param_file, "sed_param.csv")
)
btn_param_file.pack(side="right")

rb_manual = tk.Radiobutton(subframe_params, text="Utilizar valores abaixo:", variable=radio_var, value=2, state=tk.DISABLED)
rb_manual.pack(anchor="w")

row_manual = tk.Frame(subframe_params)
row_manual.pack(fill="x", padx=20)

tk.Label(row_manual, text="Densidade aparente seca da barragem de terra:").grid(row=0, column=0, sticky="w")
ent_density = tk.Entry(row_manual, width=6, state=tk.NORMAL)
ent_density.grid(row=0, column=1, padx=(5, 0), pady=2)
ent_density.insert(0, str(DEFAULT_DENSITY))
ent_density.config(state=tk.DISABLED)
tk.Label(row_manual, text="g/cm³").grid(row=0, column=2, sticky="w")

tk.Label(row_manual, text="Eficiência da retenção de sedimentos em reservatórios:").grid(row=1, column=0, sticky="w")
ent_efficiency = tk.Entry(row_manual, width=6, state=tk.NORMAL)
ent_efficiency.grid(row=1, column=1, padx=(5, 0), pady=2)
ent_efficiency.insert(0, str(DEFAULT_EFFICIENCY * 100))
ent_efficiency.config(state=tk.DISABLED)
tk.Label(row_manual, text="%").grid(row=1, column=2, sticky="w")


# 3. BOTÃO CALCULAR
btn_calcular = tk.Button(
    root,
    command=on_calcular_click,
    text="Calcular",
    bg="#d9d9d9",
    font=('Arial', 12, 'bold'),
    height=2,
)
btn_calcular.pack(pady=15, padx=20, fill="x")

# 4. ÁREA DE SAÍDA (LOG)
frame_saida = tk.LabelFrame(root, text="Saída", padx=10, pady=10)
frame_saida.pack(fill="both", expand=True, padx=20, pady=10)
txt_saida = tk.Text(frame_saida, height=6, bg="#ffffff", state=tk.DISABLED)
txt_saida.pack(fill="both", expand=True)

root.iconbitmap(resource_path("icon.ico"))
root.mainloop()

logger.info('Finished')
