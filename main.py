# main.py
from email.mime import image
import logging
import traceback
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

import pandas as pd
from tksheet import Sheet

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
# Entrada manual via planilha (tksheet)
# ---------------------------------------------------------------------------

def abrir_editor_manual(chave: str, entry_widget: tk.Entry) -> None:
    """
    Abre uma janela com uma planilha editável (tksheet) pré-configurada
    com os cabeçalhos do schema do arquivo. O usuário pode digitar ou
    colar dados (Ctrl+V) e confirmar para importar como se fosse um arquivo.
    """
    schema = FILE_SCHEMAS[chave]
    colunas = schema["names"]

    janela = tk.Toplevel(root)
    janela.title(f"Entrada manual — {chave}")
    janela.geometry("700x450")
    janela.grab_set()  # Torna a janela modal

    janela.grid_columnconfigure(0, weight=1)
    janela.grid_rowconfigure(1, weight=1)

    # Instrução
    tk.Label(
        janela,
        text=f"Cole ou preencha os dados abaixo. Colunas esperadas: {', '.join(colunas)}",
        anchor="w",
        padx=10,
        pady=6,
        font=('Arial', 9),
        fg="#444444",
    ).grid(row=0, column=0, columnspan=2, sticky="ew")

    # Frame da planilha
    frame_sheet = tk.Frame(janela)
    frame_sheet.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 5))
    frame_sheet.grid_columnconfigure(0, weight=1)
    frame_sheet.grid_rowconfigure(0, weight=1)

    # Linhas iniciais: reusa dados já carregados ou abre em branco
    df_existente = dataframes.get(chave)
    if df_existente is not None:
        linhas_iniciais = [list(row) for row in df_existente.itertuples(index=False, name=None)]
    else:
        linhas_iniciais = []
    # Garante ao menos 50 linhas preenchíveis
    linhas_iniciais += [[""] * len(colunas) for _ in range(50 - len(linhas_iniciais))]

    sheet = Sheet(
        frame_sheet,
        headers=colunas,
        data=linhas_iniciais,
        height=340,
        expand_sheet_if_paste_too_big=True
    )
    sheet.enable_bindings()          # Habilita Ctrl+C, Ctrl+V, seleção, etc.
    sheet.grid(row=0, column=0, sticky="nsew")

    # ---------------------------------------------------------------------------
    def confirmar():
        """Lê os dados da planilha, valida e carrega no dicionário dataframes."""
        dados = sheet.get_sheet_data(get_header=False)

        # Remove linhas completamente vazias
        dados = [linha for linha in dados if any(str(c).strip() for c in linha)]

        if not dados:
            messagebox.showwarning("Aviso", "Nenhum dado foi preenchido.", parent=janela)
            return

        # Valida número de colunas — aceita linhas com exatamente len(colunas) células
        for idx, linha in enumerate(dados, start=1):
            if len(linha) != len(colunas):
                messagebox.showerror(
                    "Erro de formato",
                    f"Linha {idx} tem {len(linha)} coluna(s), mas eram esperadas {len(colunas)}.\n"
                    f"Verifique se os dados colados estão no formato correto.",
                    parent=janela,
                )
                return

        try:
            df = pd.DataFrame(dados, columns=colunas)
            df = clean_dataframe_columns(df, exclude_cols=['subasin_id'])
        except Exception as e:
            messagebox.showerror("Erro ao processar dados", str(e), parent=janela)
            return

        # Salva e atualiza a entry como "[manual]"
        dataframes[chave] = df
        entry_widget.config(state=tk.NORMAL)
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, "[entrada manual]")
        entry_widget.config(state=tk.DISABLED)

        log_saida(f"Arquivo '{chave}' carregado manualmente com {len(df)} linhas")
        janela.destroy()

    # ---------------------------------------------------------------------------
    # Botões da janela
    frame_btns = tk.Frame(janela)
    frame_btns.grid(row=2, column=0, columnspan=2, pady=(0, 10))

    tk.Button(
        frame_btns,
        text="✔ Confirmar",
        bg="#3331c7",
        fg="white",
        font=('Arial', 10, 'bold'),
        width=14,
        command=confirmar,
    ).pack(side="left", padx=8)

    tk.Button(
        frame_btns,
        text="✖ Cancelar",
        bg="#f44336",
        fg="white",
        font=('Arial', 10, 'bold'),
        width=14,
        command=janela.destroy,
    ).pack(side="left", padx=8)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

# aqui tambem definimos o tipo de dado que a variavel deve esperar, nesse caso um string e uma classe do tkinter chamada tk.Entry, que é o campo de entrada de texto da interface gráfica. O tipo de retorno é None, ou seja, a função não retorna nenhum valor.

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
    
    #o entry_widget é onde o texto do caminho do arquivo é exibido. É literalmente a caixa de entrada.

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
    componentes = [ent_sed, btn_sed, btn_sed_manual, rb_file, rb_manual,
                   ent_param_file, btn_param_file, btn_param_manual,
                   ent_density, ent_efficiency]
    for comp in componentes:
        comp.config(state=novo_estado)


def _validar_dataframes_obrigatorios() -> bool:
    """Verifica se os três DataFrames obrigatórios foram carregados."""
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

        result_discharge.to_csv(f"{nome}.csv", index=False, sep=';', decimal=',')
        log_saida(f"O arquivo {nome}.csv foi gerado com sucesso!")

    except Exception:
        erro = traceback.format_exc()
        messagebox.showerror("Erro inesperado", erro)
        logger.exception("Erro inesperado")


def abrir_help() -> None:
    """Abre a página de documentação do projeto."""
    webbrowser.open("https://github.com/infracosteira/CaDBr/blob/main/README.md")


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

img_icon = tk.PhotoImage(file=resource_path("tableicon.png")).subsample(1, 1)

for label in labels:
    row = tk.Frame(frame_entrada)

    row.pack(fill="x", pady=2)
    tk.Label(row, text=f"Carregar arquivo {label}:", width=25, anchor="w").pack(side="left")
    ent = tk.Entry(row, state=tk.DISABLED)
    ent.pack(side="left", expand=True, fill="x", padx=5)
    # Botão editor manual (✎) — abre planilha tksheet
    tk.Button(
        row, image=img_icon,
        width=21, height=21,
        command=lambda e=ent, l=label: abrir_editor_manual(l, e)
    ).pack(side="right", padx=(1, 1))
    # Botão seleção de arquivo (...)
    tk.Button(
        row, text="...", width=2, height=1,
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

# Linha sedyield.csv
row_sed = tk.Frame(frame_sedimentos)
row_sed.pack(fill="x", pady=5)
tk.Label(row_sed, text="Carregar arquivo sedyield.csv:", width=25, anchor="w").pack(side="left")
ent_sed = tk.Entry(row_sed, state=tk.DISABLED)
ent_sed.pack(side="left", expand=True, fill="x", padx=5)
btn_sed_manual = tk.Button(
    row_sed, image=img_icon, width=21, height=21, state=tk.DISABLED,
    command=lambda: abrir_editor_manual("sedyield.csv", ent_sed)
)
btn_sed_manual.pack(side="right", padx=(2, 0))
btn_sed = tk.Button(
    row_sed, text="...", state=tk.DISABLED,width=2, height=1,
    command=lambda: selecionar_arquivo(ent_sed, "sedyield.csv")
)
btn_sed.pack(side="right")

# Sub-seção Parâmetros sedimentológicos
subframe_params = tk.LabelFrame(frame_sedimentos, text="Parâmetros sedimentológicos", padx=10, pady=10)
subframe_params.pack(fill="x", pady=5)

radio_var = tk.IntVar(value=1)

row_p1 = tk.Frame(subframe_params)
row_p1.pack(fill="x")
rb_file = tk.Radiobutton(row_p1, text="Carregar do arquivo:", variable=radio_var, value=1, state=tk.DISABLED)
rb_file.pack(side="left")
ent_param_file = tk.Entry(row_p1, state=tk.DISABLED)
ent_param_file.pack(side="left", expand=True, fill="x", padx=5)
btn_param_manual = tk.Button(
    row_p1, image=img_icon, width=21, height=21, state=tk.DISABLED,
    command=lambda: abrir_editor_manual("sed_param.csv", ent_param_file)
)
btn_param_manual.pack(side="right", padx=(2, 1))
btn_param_file = tk.Button(
    row_p1, text="...", state=tk.DISABLED,width=2, height=1,
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

# 5. BOTÃO AJUDA
btn_help = tk.Button(
    root,
    text="Ajuda",
    command=abrir_help,
    font=('Arial', 10, 'bold'),
)
btn_help.pack(pady=(0, 5), padx=20)

root.mainloop()

logger.info('Finished')

#encontrar uma forma de variar os parametros 
