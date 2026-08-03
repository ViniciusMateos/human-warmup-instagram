"""
Modos (perfis) do human-warmup: quanto tempo navegar, quantas curtidas, etc.

Persiste em perfis.json; os DEFAULTS vivem aqui (clone novo já funciona). O backend
semeia estes modos na 1ª leitura (bots.ler_modos), então aparecem editáveis no app.
"""
import copy
import json
import os

_BASE = os.path.dirname(os.path.abspath(__file__))
PERFIS_FILE = os.path.join(_BASE, "perfis.json")

PERFIL_PADRAO = {
    "aplicar_caps": True,
    "duracao_min": [3, 7],       # tempo de navegação, em MINUTOS (faixa)
    "max_curtidas": 3,           # teto de curtidas por run (0 = só navega)
    "prob_curtir": 25,           # % de chance de curtir a cada rolagem (0-100)
    "ver_stories": True,
    "max_stories": 4,
    "prob_story": 25,            # % de chance de ir ver stories (0-100)
    "ver_explore": True,
    "delay_scroll": [2.0, 6.0],  # dwell entre rolagens
    "delay_acao_ui": [1.0, 3.0],
    "active_hours": [8, 23],
}

_MODOS_BUILTIN = {
    "leve": {                    # ⭐ pras contas novas — bem de leve, quase só olhando
        "duracao_min": [2, 4],
        "max_curtidas": 5,
        "prob_curtir": 30,
        "max_stories": 4,
        "prob_story": 25,
    },
    "medio": {                   # conta já andada — navega mais e curte mais
        "duracao_min": [5, 9],
        "max_curtidas": 12,
        "prob_curtir": 40,
        "max_stories": 6,
        "prob_story": 35,
    },
}

_MAP_CONFIG = {
    "aplicar_caps": "APLICAR_CAPS", "duracao_min": "DURACAO_MIN", "max_curtidas": "MAX_CURTIDAS",
    "prob_curtir": "PROB_CURTIR", "ver_stories": "VER_STORIES", "max_stories": "MAX_STORIES",
    "prob_story": "PROB_STORY", "ver_explore": "VER_EXPLORE", "delay_scroll": "DELAY_SCROLL",
    "delay_acao_ui": "DELAY_ACAO_UI", "active_hours": "ACTIVE_HOURS",
}


def _default_perfis():
    out = {}
    for nome, override in _MODOS_BUILTIN.items():
        p = copy.deepcopy(PERFIL_PADRAO)
        p.update(override)
        out[nome] = p
    return out


def carregar_perfis():
    if os.path.exists(PERFIS_FILE):
        try:
            with open(PERFIS_FILE, encoding="utf-8") as f:
                d = json.load(f)
            for nome, p in list(d.items()):
                base = copy.deepcopy(PERFIL_PADRAO)
                base.update(p)
                d[nome] = base
            return d
        except Exception:
            pass
    d = _default_perfis()
    salvar_perfis(d)
    return d


def salvar_perfis(d):
    with open(PERFIS_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def get_perfil(nome):
    return carregar_perfis().get(nome)


def salvar_perfil(nome, valores):
    perfis = carregar_perfis()
    base = copy.deepcopy(PERFIL_PADRAO)
    base.update(valores or {})
    perfis[nome] = base
    salvar_perfis(perfis)
    return base


def aplicar(config, perfil):
    """Sobrescreve os atributos do módulo `config` com os valores do perfil."""
    for campo, attr in _MAP_CONFIG.items():
        if campo in perfil:
            v = perfil[campo]
            if isinstance(v, list) and len(v) == 2:
                v = tuple(v)
            setattr(config, attr, v)
