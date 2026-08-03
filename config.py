"""
Configuração do worker human-warmup — AQUECIMENTO HUMANO.

Não segue, não manda DM: só navega como gente (rola o feed, vê story, curte umas
coisas) pra deixar a conta com cara de uso real. Ideal pras contas novas/aquecendo.

Sessão e navegador seguem o MESMO padrão dos outros workers (sessão universal no dir
pai, profile por conta via env), então roda igual sob o run_manager.
"""
import os

_BASE = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────── Sessão / navegador ─────────────────
# Sessão UNIVERSAL (a conta ATIVA): mesma dos outros bots, no dir pai comum. Override por env.
SESSION_FILE = os.environ.get("IG_SESSION_FILE") or os.path.join(
    os.path.dirname(os.path.dirname(_BASE)), "session_cookies.json")
# profile do Chromium POR CONTA (device isolado) — o backend aponta via IG_USER_DATA_DIR.
USER_DATA_DIR = os.environ.get("IG_USER_DATA_DIR") or os.path.join(_BASE, "browser_profile")


def _carregar_proxy():
    import json
    f = os.path.join(_BASE, "proxy.json")
    if os.path.exists(f):
        try:
            d = json.load(open(f, encoding="utf-8"))
            if d.get("enabled") and d.get("server"):
                return {k: d[k] for k in ("server", "username", "password") if d.get(k)}
        except Exception:
            pass
    return None


PROXY = _carregar_proxy()


def _envbool(nome, padrao):
    v = os.environ.get(nome)
    return padrao if v is None else v.strip().lower() in ("1", "true", "yes", "on")


HEADLESS = _envbool("IG_HEADLESS", False)
USAR_CHROME_REAL = _envbool("IG_CHROME_REAL", True)
LOCALE = "pt-BR"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")

# ─────────────────────── Comportamento humano ───────────────
APLICAR_CAPS = True
DURACAO_MIN = (3, 7)          # quanto tempo navegar, em MINUTOS (sorteia nessa faixa)
MAX_CURTIDAS = 3              # teto de curtidas por run (0 = não curte, só navega)
PROB_CURTIR = 25             # % de chance de curtir a cada rolagem (0-100)
VER_STORIES = True           # dá uma olhada em stories
MAX_STORIES = 4              # quantos stories ver no máximo
PROB_STORY = 25             # % de chance de ir ver stories (0-100)
VER_EXPLORE = True           # passa no explorar uma vez
DELAY_SCROLL = (2.0, 6.0)    # dwell entre rolagens (parado "lendo" o post)
DELAY_ACAO_UI = (1.0, 3.0)   # pausa depois de uma ação (curtir etc.)

# Janela de horário: desligada por padrão (o cronograma já escolhe a hora).
USAR_JANELA = False
ACTIVE_HOURS = (8, 23)

# ─────────────────────────── Paths ──────────────────────────
OUTPUT_DIR = os.path.join(_BASE, "output")
LOG_FILE = os.path.join(OUTPUT_DIR, "run.log")
