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
from constants import DEFAULT_DENSITY, DEFAULT_EFFICIENCY, DEFAULT_OUTPUT_NAME, COEF_FENDA_PEAK

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
    colunas_tecnicas = schema["names"]

    colunas_exibicao = [NOMES_EXIBICAO_TABELA.get(col, col) for col in colunas_tecnicas]

    janela = tk.Toplevel(root)
    janela.title(f"Entrada manual — {chave}")
    janela.geometry("700x450")
    janela.grab_set()  # Torna a janela modal

    janela.grid_columnconfigure(0, weight=1)
    janela.grid_rowconfigure(1, weight=1)

    # Instrução
    tk.Label(
        janela,
        text=f"Cole ou preencha os dados abaixo. Colunas esperadas: {', '.join(colunas_exibicao)}",
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
    linhas_iniciais += [[""] * len(colunas_tecnicas) for _ in range(50 - len(linhas_iniciais))]

    sheet = Sheet(
        frame_sheet,
        headers=colunas_exibicao,
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

        # Valida número de colunas — aceita linhas com exatamente len(colunas_tecnicas) células
        for idx, linha in enumerate(dados, start=1):
            if len(linha) != len(colunas_tecnicas):
                messagebox.showerror(
                    "Erro de formato",
                    f"Linha {idx} tem {len(linha)} coluna(s), mas eram esperadas {len(colunas_tecnicas)}.\n"
                    f"Verifique se os dados colados estão no formato correto.",
                    parent=janela,
                )
                return

        try:
            df = pd.DataFrame(dados, columns=colunas_tecnicas)
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
    componentes = [ent_sed, btn_sed, btn_sed_manual, rb_file, rb_manual,
                   ent_param_file, btn_param_file, btn_param_manual,
                   ent_density, ent_efficiency]
    for comp in componentes:
        comp.config(state=novo_estado)


def toggle_ajuste() -> None:
    """Habilita ou desabilita os controles da seção de ajuste de parâmetros."""
    novo_estado = tk.NORMAL if ajuste_checkbox.get() else tk.DISABLED
    componentes = [ent_inicio, ent_salto, ent_fim, btn_selecionar_params]
    for comp in componentes:
        comp.config(state=novo_estado)


# ---------------------------------------------------------------------------
# Janela de seleção de parâmetros para ajuste
# ---------------------------------------------------------------------------

# Dicionário global: coluna → BooleanVar (selecionada ou não)
_ajuste_colunas_vars: dict = {}

# Mapeamento de todas as colunas numéricas ajustáveis por arquivo
COLUNAS_AJUSTAVEIS = {
    "reservoir.csv":  ["water_storage_capacity", "dam_height", "spillway_discharge"],
    "routing.csv":    [],   # subasin_id / upstream / downstream — não faz sentido ajustar
    "runoff.csv":     ["runoff_volume", "runoff_peak_discharge"],
    "sedyield.csv":   ["sed_enter_volume"],
    "sed_param.csv":  ["sediment_density", "sediment_retention_efficiency"],
}

# Rótulos amigáveis para exibição
ROTULOS_COLUNAS = {
    "water_storage_capacity":          "Capacidade de armazenamento (reservoir)",
    "dam_height":                      "Altura da barragem (reservoir)",
    "spillway_discharge":              "Vazão do vertedor (reservoir)",
    "runoff_volume":                   "Volume de escoamento (runoff)",
    "runoff_peak_discharge":           "Vazão de pico (runoff)",
    "sed_enter_volume":                "Volume de sedimento afluente (sedyield)",
    "sediment_density":                "Densidade do sedimento (sed_param)",
    "sediment_retention_efficiency":   "Eficiência de retenção (sed_param)",
}

# Mapeamento técnico -> Amigável com Unidades (para exibição na tksheet)
NOMES_EXIBICAO_TABELA = {
    "subasin_id": "ID da Sub-bacia",
    "runoff_volume": "Volume de Escoamento (m³)",
    "runoff_peak_discharge": "Vazão de Pico (m³/s)",
    "water_storage_capacity": "Capacidade de Armazenamento (m³)",
    "dam_height": "Altura da Barragem (m)",
    "spillway_discharge": "Vazão do Vertedor (m³/s)",
    "sed_enter_volume": "Volume de Sedimento Afluente (t)",
    "sediment_density": "Densidade do Sedimento (g/cm³)",
    "sediment_retention_efficiency": "Eficiência de Retenção (%)",
    "coef_peak": "Coeficiente de Pico",
}


def abrir_selecao_parametros() -> None:
    """Abre janela modal para o usuário escolher quais colunas receberão o fator de ajuste."""
    janela = tk.Toplevel(root)
    janela.title("Selecionar parâmetros para ajuste")
    janela.geometry("420x380")
    janela.resizable(False, False)
    janela.grab_set()

    tk.Label(
        janela,
        text="Marque as colunas que receberão o fator de correção:",
        font=('Arial', 9),
        anchor="w",
        padx=10,
        pady=8,
    ).pack(fill="x")

    frame_scroll = tk.Frame(janela)
    frame_scroll.pack(fill="both", expand=True, padx=10)

    canvas = tk.Canvas(frame_scroll, borderwidth=0, highlightthickness=0)
    scrollbar = tk.Scrollbar(frame_scroll, orient="vertical", command=canvas.yview)
    frame_inner = tk.Frame(canvas)

    frame_inner.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=frame_inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Cria checkbuttons para cada coluna ajustável
    for arquivo, colunas in COLUNAS_AJUSTAVEIS.items():
        if not colunas:
            continue
        tk.Label(
            frame_inner,
            text=arquivo,
            font=('Arial', 8, 'bold'),
            fg="#555555",
            anchor="w",
        ).pack(fill="x", pady=(8, 2), padx=5)

        for col in colunas:
            if col not in _ajuste_colunas_vars:
                _ajuste_colunas_vars[col] = tk.BooleanVar(value=True)
            tk.Checkbutton(
                frame_inner,
                text=ROTULOS_COLUNAS.get(col, col),
                variable=_ajuste_colunas_vars[col],
                anchor="w",
            ).pack(fill="x", padx=20)

    # Botões
    frame_btns = tk.Frame(janela)
    frame_btns.pack(pady=10)

    def marcar_todos():
        for var in _ajuste_colunas_vars.values():
            var.set(True)

    def desmarcar_todos():
        for var in _ajuste_colunas_vars.values():
            var.set(False)

    tk.Button(frame_btns, text="Marcar todos",   width=14, command=marcar_todos).pack(side="left", padx=6)
    tk.Button(frame_btns, text="Desmarcar todos", width=14, command=desmarcar_todos).pack(side="left", padx=6)
    tk.Button(
        frame_btns, text="✔ Confirmar",
        bg="#3331c7", fg="white", font=('Arial', 10, 'bold'), width=14,
        command=janela.destroy,
    ).pack(side="left", padx=6)


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

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


def _obter_coef_peak() -> float | pd.DataFrame | None:
    """
    Lê o coeficiente de pico de acordo com o modo selecionado.

    - Modo 1 (arquivo): retorna o DataFrame carregado em 'coef_peak.csv'
    - Modo 2 (valor manual): retorna o float digitado ou COEF_FENDA_PEAK por padrão
    - Retorna None em caso de erro de validação.
    """
    if radio_var_peak.get() == 1:
        df_coef = dataframes.get('coef_peak.csv')
        if df_coef is None:
            messagebox.showerror("Erro", "Arquivo de coeficiente de pico não carregado.")
            return None
        return df_coef
    else:
        val = ent_coef_peak.get().replace(',', '.').strip()
        try:
            return float(val) if val else COEF_FENDA_PEAK
        except ValueError:
            messagebox.showerror("Erro", "Valor do coeficiente de pico inválido. Use um número (ex: 0.707121014402343).")
            return None


def _obter_configuracao_ajuste() -> tuple | None:
    """
    Lê e valida as configurações do ajuste de parâmetros.

    Retorna (inicio, salto, fim, colunas_selecionadas) ou None em caso de erro.
    - inicio, salto, fim são floats (ex: 0.50, 0.10, 1.50)
    - colunas_selecionadas é uma lista de strings com os nomes das colunas marcadas
    """
    try:
        inicio_str = ent_inicio.get().replace(',', '.').replace('%', '').strip()
        salto_str  = ent_salto.get().replace(',', '.').replace('%', '').strip()
        fim_str    = ent_fim.get().replace(',', '.').replace('%', '').strip()

        if not inicio_str or not salto_str or not fim_str:
            messagebox.showerror("Erro", "Preencha todos os campos do ajuste de parâmetros (início, salto e fim).")
            return None

        inicio = float(inicio_str) / 100.0
        salto  = float(salto_str)  / 100.0
        fim    = float(fim_str)    / 100.0

    except ValueError:
        messagebox.showerror("Erro", "Valores do ajuste de parâmetros inválidos. Use números (ex: 50, 10, 150).")
        return None

    if salto <= 0:
        messagebox.showerror("Erro", "O tamanho do salto deve ser maior que zero.")
        return None

    if inicio > fim:
        messagebox.showerror("Erro", "O valor de início não pode ser maior que o valor de fim.")
        return None

    colunas_selecionadas = [col for col, var in _ajuste_colunas_vars.items() if var.get()]

    if not colunas_selecionadas:
        messagebox.showerror("Erro", "Selecione ao menos uma coluna para o ajuste de parâmetros.")
        return None

    return inicio, salto, fim, colunas_selecionadas


# ---------------------------------------------------------------------------
# Aplicação do fator de ajuste nos DataFrames
# ---------------------------------------------------------------------------

def _aplicar_fator(fator: float, colunas_ajuste: list) -> dict:
    """
    Retorna uma cópia ajustada do dicionário dataframes com o fator aplicado
    somente nas colunas indicadas. Os dataframes originais não são alterados.
    """
    dfs_ajustados = {}
    for chave, df in dataframes.items():
        df_copia = df.copy()
        for col in colunas_ajuste:
            if col in df_copia.columns:
                print("coluna antes:", df_copia[col].head())
                df_copia[col] = df_copia[col] * fator
                print("coluna depois:", df_copia[col].head())
        dfs_ajustados[chave] = df_copia
    return dfs_ajustados


# ---------------------------------------------------------------------------
# Cálculo principal
# ---------------------------------------------------------------------------

def _executar_calculo_unico(dfs: dict, nome_arquivo: str, coef_peak) -> None:
    """
    Executa o roteamento hídrico (e sedimentológico, se habilitado) usando
    os dataframes fornecidos e grava o resultado em nome_arquivo.csv.

    coef_peak pode ser um float (valor único) ou um DataFrame (por sub-bacia).
    """
    result_discharge, G, ruptura_dict, sequencia, df_merged = calculate_water_routing(
        df_reservoir=dfs['reservoir.csv'],
        df_routing=dfs['routing.csv'],
        df_runoff=dfs['runoff.csv'],
        coef_peak=coef_peak,
    )

    if sedimentos_checkbox.get():
        df_sedyield = dfs.get('sedyield.csv')
        if df_sedyield is None:
            raise ValueError("Arquivo sedyield.csv não carregado.")

        params = _obter_parametros_sedimentos()
        if params is None:
            raise ValueError("Parâmetros sedimentológicos inválidos.")

        radio_mode, df_sed_param, density_manual, efficiency_manual = params

        # Se sed_param também passou pelo ajuste, usa a versão ajustada
        if 'sed_param.csv' in dfs:
            df_sed_param_uso = dfs['sed_param.csv'] if radio_mode == 1 else None
        else:
            df_sed_param_uso = df_sed_param

        result_discharge = calculate_sediment_routing(
            result_discharge=result_discharge,
            G=G,
            ruptura_dict=ruptura_dict,
            sequencia_processamento=sequencia,
            df_sedyield=df_sedyield,
            df_merged=df_merged,
            radio_mode=radio_mode,
            df_sed_param=df_sed_param_uso,
            density_manual=density_manual,
            efficiency_manual=efficiency_manual,
        )

    result_discharge.to_csv(f"{nome_arquivo}.csv", index=False, sep=';', decimal=',')


def on_calcular_click() -> None:
    """Callback do botão Calcular — orquestra leitura, cálculo e escrita do resultado."""
    try:
        if not _validar_dataframes_obrigatorios():
            return

        # Obtém coeficiente de pico antes de qualquer cálculo
        coef_peak = _obter_coef_peak()
        if coef_peak is None:
            return

        nome_base = ent_name.get().strip() or DEFAULT_OUTPUT_NAME
        logger.info('Cálculo iniciado pelo usuário')
        log_saida("Cálculo iniciado pelo usuário...")

        # ------------------------------------------------------------------
        # Modo com ajuste de parâmetros
        # ------------------------------------------------------------------
        if ajuste_checkbox.get():
            config_ajuste = _obter_configuracao_ajuste()
            if config_ajuste is None:
                return

            inicio, salto, fim, colunas_ajuste = config_ajuste

            fator_atual = inicio
            arquivos_gerados = 0

            log_saida(
                f"Ajuste ativo: de {inicio*100:.0f}% até {fim*100:.0f}%, "
                f"salto de {salto*100:.0f}%"
            )
            log_saida(f"Colunas ajustadas: {', '.join(colunas_ajuste)}")

            while fator_atual <= fim + 1e-9:   # tolerância de ponto flutuante
                percentual_str = f"{round(fator_atual * 100)}"
                nome_arquivo   = f"{nome_base}_{percentual_str}"

                log_saida(f"  → Calculando fator {percentual_str}%...")

                dfs_ajustados = _aplicar_fator(fator_atual, colunas_ajuste)
                _executar_calculo_unico(dfs_ajustados, nome_arquivo, coef_peak)

                log_saida(f"    Arquivo '{nome_arquivo}.csv' gerado com sucesso.")
                arquivos_gerados += 1
                fator_atual += salto

            log_saida(f"Ajuste concluído! {arquivos_gerados} arquivo(s) gerado(s).")

        # ------------------------------------------------------------------
        # Modo sem ajuste — comportamento original
        # ------------------------------------------------------------------
        else:
            log_saida("Construindo grafo das rotas...")
            log_saida("Calculando casos de ruptura...")
            _executar_calculo_unico(dataframes, nome_base, coef_peak)
            log_saida(f"O arquivo {nome_base}.csv foi gerado com sucesso!")

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
root.geometry("650x980")

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



caminhos = {
    "routing.csv": "F:/bolsa/basinflow/data/principais/big_routing.csv",
    "runoff.csv": "F:/bolsa/basinflow/data/principais/big_runoff_10.csv",
    "reservoir.csv": "F:/bolsa/basinflow/data/principais/big_reservoir.csv"
}

caminhos_small_archives = {
    "routing.csv": "F:/bolsa/basinflow/data/principais/routing.csv",
    "runoff.csv": "F:/bolsa/basinflow/data/principais/arq_entrada/runoff_10_v2.csv",
    "reservoir.csv": "F:/bolsa/basinflow/data/principais/reservoir.csv"
}

def importar_arquivo_no_inicio(entry_widget: tk.Entry, chave: str, file_path: str) -> None:
    """Importa um arquivo já selecionado (usado na inicialização automática)."""
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


for label in labels:

    row = tk.Frame(frame_entrada)
    row.pack(fill="x", pady=2)
    
    tk.Label(row,
            text=f"Carregar arquivo {label}:", 
            width=25, 
            anchor="w").pack(side="left")
    ent = tk.Entry(row, state=tk.DISABLED)

    ent.pack(side="left", 
             expand=True, 
             fill="x", 
             padx=5)

    tk.Button(
        row, 
        image=img_icon,
        width=21, 
        height=21,
        command=lambda e=ent, l=label: abrir_editor_manual(l, e)
    ).pack(side="right", padx=(1, 1))

    tk.Button(
        row,
        text="...", 
        width=2, 
        height=1,
        command=lambda e=ent, l=label: selecionar_arquivo(e, l)
    ).pack(side="right")


    #root.after(1, lambda e=ent, l=label: importar_arquivo_no_inicio(e, l, caminhos_small_archives[l]))


# ---------------------------------------------------------------------------
# 1b. SUBSEÇÃO: COEFICIENTE DE PICO (dentro de frame_entrada)
# ---------------------------------------------------------------------------
subframe_coef_peak = tk.LabelFrame(
    frame_entrada,
    text="Coeficiente de pico",
    padx=10,
    pady=8,
)
subframe_coef_peak.pack(fill="x", pady=(8, 2))

radio_var_peak = tk.IntVar(value=2)  # padrão: valor manual


def toggle_coef_peak_widgets() -> None:
    """Habilita/desabilita os widgets conforme o radio button selecionado."""
    if radio_var_peak.get() == 1:
        # modo arquivo: habilita arquivo, desabilita campo manual
        ent_coef_peak_file.config(state=tk.NORMAL)
        btn_coef_peak_file.config(state=tk.NORMAL)
        ent_coef_peak.config(state=tk.DISABLED)
    else:
        # modo manual: desabilita arquivo, habilita campo manual
        ent_coef_peak_file.config(state=tk.DISABLED)
        btn_coef_peak_file.config(state=tk.DISABLED)
        ent_coef_peak.config(state=tk.NORMAL)


# Linha 1 — opção "Carregar do arquivo"
row_cp_file = tk.Frame(subframe_coef_peak)
row_cp_file.pack(fill="x", pady=2)

rb_coef_peak_file = tk.Radiobutton(
    row_cp_file,
    text="Carregar do arquivo (subasin_id, coef_peak):",
    variable=radio_var_peak,
    value=1,
    command=toggle_coef_peak_widgets,
    width=35,
    anchor="w",
)
rb_coef_peak_file.pack(side="left")

ent_coef_peak_file = tk.Entry(row_cp_file, state=tk.DISABLED)
ent_coef_peak_file.pack(side="left", expand=True, fill="x", padx=5)

btn_coef_peak_file = tk.Button(
    row_cp_file,
    text="...",
    width=2,
    height=1,
    state=tk.DISABLED,
    command=lambda: selecionar_arquivo(ent_coef_peak_file, "coef_peak.csv"),
)
btn_coef_peak_file.pack(side="right")

# Linha 2 — opção "Utilizar valor manual"
row_cp_manual = tk.Frame(subframe_coef_peak)
row_cp_manual.pack(fill="x", pady=2)

rb_coef_peak_manual = tk.Radiobutton(
    row_cp_manual,
    text="Utilizar valor padrão/manual:",
    variable=radio_var_peak,
    value=2,
    command=toggle_coef_peak_widgets,
    width=35,
    anchor="w",
)
rb_coef_peak_manual.pack(side="left")

ent_coef_peak = tk.Entry(row_cp_manual, width=20)
ent_coef_peak.insert(0, str(COEF_FENDA_PEAK))
ent_coef_peak.pack(side="left", padx=(5, 0))

tk.Label(row_cp_manual, text="(padrão: COEF_FENDA_PEAK)", fg="#777777", font=('Arial', 8)).pack(side="left", padx=(6, 0))

# Estado inicial: modo manual ativo
toggle_coef_peak_widgets()


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
    row_sed, text="...", state=tk.DISABLED, width=2, height=1,
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
    row_p1, text="...", state=tk.DISABLED, width=2, height=1,
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


# ---------------------------------------------------------------------------
# 3. AJUSTE DE PARÂMETROS (nova seção)
# ---------------------------------------------------------------------------
ajuste_checkbox = tk.BooleanVar(value=False)
frame_ajuste = tk.LabelFrame(root, padx=15, pady=10)
frame_ajuste.pack(fill="x", padx=20, pady=(0, 10))

check_ajuste_btn = tk.Checkbutton(
    frame_ajuste,
    text="Incluir ajuste de parâmetros",
    variable=ajuste_checkbox,
    command=toggle_ajuste,
    font=('Arial', 10, 'bold'),
)
frame_ajuste.configure(labelwidget=check_ajuste_btn)

# Linha com os 3 campos e o botão "Selecionar parâmetros"
row_ajuste = tk.Frame(frame_ajuste)
row_ajuste.pack(fill="x", pady=4)

# --- Início do intervalo ---
tk.Label(row_ajuste, text="Início do intervalo:", anchor="w").pack(side="left")
ent_inicio = tk.Entry(row_ajuste, width=6, state=tk.DISABLED)
ent_inicio.insert(0, "80")
ent_inicio.pack(side="left", padx=(3, 8))
tk.Label(row_ajuste, text="%", fg="#555").pack(side="left")

# --- Tamanho do salto ---
tk.Label(row_ajuste, text="  Tamanho do salto:", anchor="w").pack(side="left")
ent_salto = tk.Entry(row_ajuste, width=6, state=tk.DISABLED)
ent_salto.insert(0, "10")
ent_salto.pack(side="left", padx=(3, 8))
tk.Label(row_ajuste, text="%", fg="#555").pack(side="left")

# --- Fim do intervalo ---
tk.Label(row_ajuste, text="  Fim do intervalo:", anchor="w").pack(side="left")
ent_fim = tk.Entry(row_ajuste, width=6, state=tk.DISABLED)
ent_fim.insert(0, "150")
ent_fim.pack(side="left", padx=(3, 8))
tk.Label(row_ajuste, text="%", fg="#555").pack(side="left")

# --- Botão selecionar parâmetros (lado direito) ---
btn_selecionar_params = tk.Button(
    frame_ajuste,
    text="Selecionar\nparâmetros",
    state=tk.DISABLED,
    font=('Arial', 9, 'bold'),
    bg="#3a3a3a",
    fg="white",
    width=14,
    height=2,
    command=abrir_selecao_parametros,
)
btn_selecionar_params.pack(side="right", padx=(8, 0), pady=(0, 4))


# ---------------------------------------------------------------------------
# 4. BOTÃO CALCULAR
# ---------------------------------------------------------------------------
btn_calcular = tk.Button(
    root,
    command=on_calcular_click,
    text="Calcular",
    bg="#d9d9d9",
    font=('Arial', 12, 'bold'),
    height=2,
)
btn_calcular.pack(pady=15, padx=20, fill="x")

# 5. ÁREA DE SAÍDA (LOG)
frame_saida = tk.LabelFrame(root, text="Saída", padx=10, pady=10)
frame_saida.pack(fill="both", expand=True, padx=20, pady=10)
txt_saida = tk.Text(frame_saida, height=6, bg="#ffffff", state=tk.DISABLED)
txt_saida.pack(fill="both", expand=True)

root.iconbitmap(resource_path("icon.ico"))

# 6. BOTÃO AJUDA
btn_help = tk.Button(
    root,
    text="Ajuda",
    command=abrir_help,
    font=('Arial', 10, 'bold'),
)
btn_help.pack(pady=(0, 5), padx=20)

root.mainloop()

logger.info('Finished')