"""
human_warmup — aquecimento HUMANO de conta do Instagram.

Não segue e não manda DM: só navega como gente (rola o feed com pausas, vê alguns
stories, curte pouca coisa, passa no explorar) pra deixar a conta com cara de uso
real. Feito pras contas novas/aquecendo antes de botar volume nelas.

Uso:
  python main.py --modo leve            # navega de leve (recomendado p/ conta nova)
  python main.py --modo medio           # conta já andada
  python main.py --dry-run --modo leve  # navega mas NÃO curte nada
  python main.py --listar-modos
"""
import argparse
import os
import sys
import time
import random
import traceback
from datetime import datetime

import config
import perfis
from safety import Guard, LimiteAtingido, log, fmt_tempo
from ig import IG

LOGS_ERRO_DIR = os.path.join(config.OUTPUT_DIR, "logs")
_T_INICIO = time.monotonic()


def progresso(done, total, label=""):
    """Marcador machine-readable pro backend/app desenharem a barra de progresso."""
    print(f"[progress] {done} {total} {label}".rstrip(), flush=True)


def _carregar_cookies(path):
    import json
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict) and "cookies" in raw:
        raw = raw["cookies"]
    ss_map = {"no_restriction": "None", "unspecified": "Lax", "lax": "Lax",
              "strict": "Strict", "none": "None"}
    out = []
    for c in raw:
        ck = {"name": c["name"], "value": c["value"],
              "domain": c.get("domain") or ".instagram.com", "path": c.get("path", "/"),
              "httpOnly": bool(c.get("httpOnly")), "secure": bool(c.get("secure", True)),
              "sameSite": ss_map.get(str(c.get("sameSite", "")).lower(), "Lax")}
        exp = c.get("expirationDate") or c.get("expires")
        if exp and not c.get("session"):
            ck["expires"] = int(float(exp))
        out.append(ck)
    return out


def modo_importar_cookies(path):
    cookies = _carregar_cookies(path)
    log.info("Importando %d cookies de %s…", len(cookies), path)
    with IG() as ig:
        ok = ig.importar_cookies(cookies)
    if ok:
        log.info("Sessão logada! Já pode rodar os bots.")
        return
    log.error("Importei os cookies mas a sessão NÃO está logada. Exporte de novo com a "
              "conta logada no instagram.com (precisa de um sessionid válido).")
    sys.exit(1)


def modo_login():
    log.info("Abrindo navegador para login manual…")
    with IG() as ig:
        ig.ir("https://www.instagram.com/")
        input(">>> Loga na janela do Chrome e aperte ENTER aqui quando estiver no feed… ")
        log.info("Sessão detectada." if ig.logado() else "Não detectei sessionid — confira o login.")


def tratar_erro(exc, titulo):
    os.makedirs(LOGS_ERRO_DIR, exist_ok=True)
    caminho = os.path.join(LOGS_ERRO_DIR, "erro_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".log")
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        caminho = "(não consegui salvar o arquivo de erro)"
    log.error("%s: %s", titulo, str(exc)[:160])
    log.error("   detalhes completos em: %s", caminho)


def run(dry=False, ignorar_janela=False):
    guard = Guard(dry_run=dry)
    try:
        guard.checar_janela(ignorar=ignorar_janela)
    except LimiteAtingido as e:
        log.info("Não vou rodar agora: %s", e)
        return

    log.info("Abrindo Instagram (%s)…", "DRY-RUN" if dry else "AÇÃO REAL")
    with IG(dry_run=dry) as ig:
        aberto = False
        for _tent in range(3):
            try:
                ig.ir("https://www.instagram.com/", timeout=45000)
                aberto = True
                break
            except Exception as e:
                log.warning("~ a home do IG demorou a abrir (%d/3): %s — repito",
                            _tent + 1, str(e).splitlines()[0][:50])
        if not aberto:
            log.error("Não consegui abrir o Instagram (túnel congestionado?). Tenta de novo.")
            return
        if not ig.logado():
            log.error("Sem sessão logada. Conecte uma conta primeiro.")
            return
        ig.salvar_sessao()   # mantém o cookie fresco e registra qual conta é
        log.info("Conta: @%s — começando o aquecimento.", ig.usuario() or "?")

        duracao = random.uniform(config.DURACAO_MIN[0], config.DURACAO_MIN[1]) * 60
        total = int(duracao)
        log.info("Vou navegar ~%s como gente (curtidas até %d).",
                 fmt_tempo(duracao), config.MAX_CURTIDAS if config.APLICAR_CAPS else 0)
        inicio = time.monotonic()
        fim = inicio + duracao
        curtidas = stories_vistos = rolagens = 0
        ja_explorou = False

        def _label():
            # placar ao vivo na barrinha + tempo restante (o aquecimento é medido por tempo)
            restam = max(0, int(fim - time.monotonic()))
            mm, ss = divmod(restam, 60)
            falta = f"{mm}m {ss:02d}s" if mm else f"{ss}s"
            return f"faltam {falta} · curtidas {curtidas} · stories {stories_vistos}"

        progresso(0, total, _label())

        try:
            while time.monotonic() < fim:
                progresso(min(int(time.monotonic() - inicio), total), total, _label())
                # cada ação sorteia seu PRÓPRIO dado (senão o curtir "comia" o dado do story
                # e o story nunca era alcançado)
                pode_curtir = config.MAX_CURTIDAS and curtidas < config.MAX_CURTIDAS
                if pode_curtir and random.random() * 100 < config.PROB_CURTIR:
                    if ig.curtir_visivel():
                        curtidas += 1
                        log.info("curti um post (%d/%d)", curtidas, config.MAX_CURTIDAS)
                        guard.dormir(config.DELAY_ACAO_UI, "depois de curtir")
                        continue
                    ig.rolar(); rolagens += 1     # não achou post pra curtir agora — rola e segue
                    guard.dormir(config.DELAY_SCROLL, "procurando post")
                elif config.VER_STORIES and stories_vistos == 0 and random.random() * 100 < config.PROB_STORY:
                    log.info("vou dar uma olhada nos stories…")
                    v = ig.ver_stories(config.MAX_STORIES)
                    stories_vistos += v
                    log.info("vi %d stories", v) if v else log.info("sem story pra ver agora")
                    guard.dormir(config.DELAY_ACAO_UI, "depois dos stories")
                elif config.VER_EXPLORE and not ja_explorou and random.random() < 0.15:
                    ja_explorou = True
                    if ig.explorar(random.randint(3, 6)):
                        log.info("dei uma passada no explorar")
                    try:
                        ig.ir("https://www.instagram.com/", timeout=30000)   # volta pro feed
                    except Exception:
                        pass
                else:
                    ig.rolar(); rolagens += 1
                    if rolagens % 10 == 0:       # heartbeat: mostra que tá vivo, sem virar sopa
                        log.info("rolando o feed… (%d rolagens, %d curtidas)", rolagens, curtidas)
                    guard.dormir(config.DELAY_SCROLL, "lendo o feed")
            progresso(total, total, _label())
        except KeyboardInterrupt:
            log.info("Interrompido manualmente (Ctrl+C).")
        except Exception as e:
            tratar_erro(e, "erro no aquecimento — parando o run")
        finally:
            log.info("──────────────── SALDO DA EXECUÇÃO ────────────────")
            log.info("   curtidas .............. %d", curtidas)
            log.info("   stories vistos ........ %d", stories_vistos)
            log.info("   rolagens .............. %d", rolagens)
            log.info("   tempo de execução ..... %s", fmt_tempo(time.monotonic() - inicio))
            log.info("────────────────────────────────────────────────────")
            log.info("[saldo] curtidas=%d stories=%d rolagens=%d", curtidas, stories_vistos, rolagens)


def main():
    ap = argparse.ArgumentParser(description="human_warmup")
    ap.add_argument("--import-cookies", metavar="FILE", help="importa cookies (JSON) e valida a sessão")
    ap.add_argument("--login", action="store_true", help="login manual (1ª vez)")
    ap.add_argument("--dry-run", action="store_true", help="navega mas NÃO curte nada")
    ap.add_argument("--ignore-window", action="store_true", help="ignora janela de horário")
    ap.add_argument("--modo", metavar="NOME", default="leve", help="modo: leve, medio…")
    ap.add_argument("--listar-modos", action="store_true", help="lista os modos salvos e sai")
    a = ap.parse_args()

    if a.listar_modos:
        for nome, p in perfis.carregar_perfis().items():
            log.info("modo: %-8s duracao_min=%s | max_curtidas=%s | ver_stories=%s | explore=%s",
                     nome, p["duracao_min"], p["max_curtidas"], p["ver_stories"], p["ver_explore"])
        return
    if a.import_cookies:
        modo_importar_cookies(a.import_cookies)
        return
    if a.login:
        modo_login()
        return

    perfil = perfis.get_perfil(a.modo)
    if not perfil:
        log.error("Modo '%s' não existe. Use --listar-modos.", a.modo)
        sys.exit(2)
    perfis.aplicar(config, perfil)
    log.info("Modo: %s  |  duração: %s min  |  curtidas até: %s",
             a.modo, config.DURACAO_MIN, config.MAX_CURTIDAS)

    try:
        run(dry=a.dry_run, ignorar_janela=a.ignore_window)
    except KeyboardInterrupt:
        log.info("Interrompido.")
    except Exception as e:
        tratar_erro(e, "erro fatal")
        sys.exit(2)


if __name__ == "__main__":
    main()
