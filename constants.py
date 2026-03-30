# constants.py
# Coeficientes físicos e valores padrão utilizados nos cálculos hidrológicos e sedimentológicos.

# --- Roteamento Hídrico ---

# Fração média do volume efluente que passa pela fenda durante ruptura
COEF_FENDA_PEAK = 0.707121014402343

# Coeficientes da equação de vazão de pico pós-ruptura: Q = A * V^B
COEF_RUPTURA_A = 0.0344
COEF_RUPTURA_B = 0.6527

# --- Sedimentos ---

# Fração média do volume efluente de sedimentos que passa pela fenda
COEF_FENDA_SED = 0.842584358697712

# Coeficientes da equação de volume de sedimento erodido: Vs = m * (V * pm * H)^n
COEF_SED_M = 0.0261
COEF_SED_N = 0.769

# --- Parâmetros padrão (modo manual) ---

DEFAULT_DENSITY = 1.5      # Densidade aparente seca da barragem de terra (g/cm³)
DEFAULT_EFFICIENCY = 0.50  # Eficiência de retenção de sedimentos (fração, 0-1)

# --- Arquivos de saída ---

DEFAULT_OUTPUT_NAME = "result_discharge"
