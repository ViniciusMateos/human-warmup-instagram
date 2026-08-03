"""
Camada leve de segurança do human-warmup: log (com log por sessão), exceções e
o Guard (janela de horário + dormir humano). Sem State: o aquecimento é sem histórico —
cada run só navega; não tem "de onde retomar".
"""
import os
import sys
import time
import random
import logging
from datetime import datetime

import config


def setup_logger():
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    logger = logging.getLogger("humanwarmup")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    fmt = logging.Formatter("%(asctime)s  %(levelname)-5s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    # log POR SESSÃO (output/logs/run_<ts>.log), mantém só os 30 mais recentes
    _logs_dir = os.path.join(config.OUTPUT_DIR, "logs")
    os.makedirs(_logs_dir, exist_ok=True)
    _sess = logging.FileHandler(
        os.path.join(_logs_dir, "run_" + time.strftime("%Y%m%d_%H%M%S") + ".log"), encoding="utf-8")
    _sess.setFormatter(fmt)
    try:
        _antigos = sorted(f for f in os.listdir(_logs_dir)
                          if f.startswith("run_") and f.endswith(".log"))
        for _f in _antigos[:-30]:
            os.remove(os.path.join(_logs_dir, _f))
    except Exception:
        pass
    logger.addHandler(fh)
    logger.addHandler(_sess)
    logger.addHandler(ch)
    return logger


log = setup_logger()


def fmt_tempo(segundos):
    seg = int(round(segundos))
    if seg < 60:
        return f"{seg}s"
    m, s = divmod(seg, 60)
    return f"{m}m {s}s" if s else f"{m}m"


def _dormir_contando(t, motivo=""):
    """Dorme `t` segundos. Em pausas longas (>15s) emite [espera] a cada ~12s com o tempo
    restante → app/Live Activity mostram a contagem regressiva ('faltam Xm Ys')."""
    if t <= 15:
        time.sleep(t)
        return
    fim = time.monotonic() + t
    while True:
        restam = fim - time.monotonic()
        if restam <= 0.5:
            break
        print(f"[espera] {int(round(restam))} {motivo}".rstrip(), flush=True)
        time.sleep(min(restam, 12))


class LimiteAtingido(Exception):
    """Fora da janela de horário — não roda agora."""


class Guard:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run

    def checar_janela(self, ignorar=False):
        if ignorar or not config.APLICAR_CAPS or not getattr(config, "USAR_JANELA", False):
            return
        h = datetime.now().hour
        ini, fim = config.ACTIVE_HOURS
        if not (ini <= h < fim):
            raise LimiteAtingido(f"Fora da janela ({ini}h–{fim}h). Agora: {h}h.")

    def dormir(self, faixa, motivo=""):
        a, b = faixa
        t = random.uniform(a, b)
        # navegar (dwell) É o comportamento — dorme de verdade mesmo em dry-run; o dry só evita
        # a ÚNICA ação real (curtir). Pausas longas emitem [espera] pra contagem no app/LA.
        _dormir_contando(t, motivo)
