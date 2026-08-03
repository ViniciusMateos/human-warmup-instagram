"""
Cliente do Instagram pro human-warmup. Mesmo scaffolding de browser/sessão dos outros
workers (Chrome logado via Playwright, sessão reinjetada a cada abrir), mas SEM chamadas
de API — aqui é tudo UI de verdade (rolar, curtir no botão, ver story), que é o ponto:
parecer gente. Toda ação humana é best-effort e não-fatal.
"""
import json
import os
import random

from playwright.sync_api import sync_playwright

import config
from safety import log


class IG:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self._pw = None
        self.ctx = None
        self.page = None

    # ─────────── ciclo de vida ───────────
    def abrir(self):
        self._pw = sync_playwright().start()
        kwargs = dict(
            headless=config.HEADLESS, locale=config.LOCALE, user_agent=config.USER_AGENT,
            viewport={"width": 1280, "height": 820},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"])
        if getattr(config, "PROXY", None):
            kwargs["proxy"] = config.PROXY
            log.info("Proxy ativo: %s", config.PROXY.get("server"))
        if getattr(config, "USAR_CHROME_REAL", False):
            kwargs["channel"] = "chrome"
        try:
            self.ctx = self._pw.chromium.launch_persistent_context(config.USER_DATA_DIR, **kwargs)
        except Exception as e:
            if "channel" in kwargs:
                log.warning("Chrome real não encontrado (%s); usando Chromium.", e)
                kwargs.pop("channel")
                self.ctx = self._pw.chromium.launch_persistent_context(config.USER_DATA_DIR, **kwargs)
            else:
                raise
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.set_default_timeout(20000)   # ação do Playwright falha em 20s em vez de pendurar
        self._restaurar_sessao()   # o perfil não guarda cookie; a sessão vem do arquivo
        return self

    def fechar(self):
        try:
            if self.ctx:
                self.ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    def __enter__(self):
        return self.abrir()

    def __exit__(self, *a):
        self.fechar()

    # ─────────── sessão ───────────
    def ir(self, url, timeout=30000):
        self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        self.page.wait_for_timeout(1500)

    def _cookies(self):
        try:
            cks = self.ctx.cookies("https://www.instagram.com")
        except Exception:
            cks = self.ctx.cookies()
        return {c["name"]: c["value"] for c in cks}

    def logado(self):
        return bool(self._cookies().get("sessionid"))

    def usuario(self):
        """@username logado agora (do viewer). "" se não der — nunca derruba a run."""
        try:
            return self.page.evaluate("""async () => {
                const r = await fetch('/data/shared_data/');
                if (!r.ok) return '';
                const j = await r.json();
                return (j.config && j.config.viewer && j.config.viewer.username) || '';
            }""") or ""
        except Exception:
            return ""

    def importar_cookies(self, cookies):
        self.ctx.add_cookies(cookies)
        for _tent in range(2):
            try:
                self.ir("https://www.instagram.com/", timeout=45000)
                break
            except Exception as e:
                log.warning("~ instagram.com demorou a abrir (%d/2): %s — sigo pro cookie",
                            _tent + 1, str(e).splitlines()[0][:50])
        if not self.logado():
            return False
        self.salvar_sessao()
        return True

    def salvar_sessao(self):
        try:
            cks = self.ctx.cookies("https://www.instagram.com")
            with open(config.SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(cks, f)
            os.chmod(config.SESSION_FILE, 0o600)
            log.info("Sessão salva (%d cookies).", len(cks))
        except Exception as e:
            log.warning("Não consegui salvar a sessão: %s", e)

    def _restaurar_sessao(self):
        if not os.path.exists(config.SESSION_FILE):
            return
        try:
            with open(config.SESSION_FILE, encoding="utf-8") as f:
                cks = json.load(f)
            if cks:
                self.ctx.add_cookies(cks)
        except Exception as e:
            log.warning("Não consegui restaurar a sessão salva: %s", e)

    # ─────────── ações humanas (UI de verdade, best-effort) ───────────
    def rolar(self, px=None):
        """Rola o feed com a rodinha do mouse, como gente lendo."""
        try:
            self.page.mouse.wheel(0, px or random.randint(500, 900))
            return True
        except Exception:
            return False

    def _ja_curtido(self, art):
        try:
            return art.locator('svg[aria-label="Descurtir"], svg[aria-label="Unlike"]').count() > 0
        except Exception:
            return False

    def curtir_visivel(self):
        """Curte UM post visível via DOUBLE-TAP na mídia (gesto humano e o mais robusto — o svg
        de curtir tem pointer-events off, então clicar nele não faz nada; double-tap na foto SÓ
        curte, nunca descurte). Fallback: clicar o botão. Confirma pelo 'Descurtir' aparecer."""
        vh = (self.page.viewport_size or {}).get("height", 820)
        arts = self.page.locator("article")
        try:
            total = arts.count()
        except Exception:
            total = 0
        for i in range(min(total, 15)):
            art = arts.nth(i)
            try:
                box = art.bounding_box()
                if not box or box["width"] < 200:
                    continue
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + min(box["height"] * 0.38, box["height"] - 90)
                if cy < 130 or cy > vh - 130:       # a mídia precisa estar na tela
                    continue
                if self._ja_curtido(art):           # já curtido → procura outro
                    continue
                if self.dry_run:
                    log.info("[dry] curtiria um post (double-tap)")
                    return True
                self.page.mouse.dblclick(cx, cy)    # 1) double-tap na mídia
                self.page.wait_for_timeout(600)
                if self._ja_curtido(art):
                    return True
                svg = art.locator('svg[aria-label="Curtir"], svg[aria-label="Like"]').first
                if svg.count():                     # 2) fallback: ancestral clicável do svg
                    anc = svg.locator('xpath=ancestor::*[@role="button" or self::button or @tabindex="0"][1]')
                    (anc.first if anc.count() else svg).click(timeout=3000)
                    self.page.wait_for_timeout(500)
                    if self._ja_curtido(art):
                        return True
            except Exception:
                continue
        return False

    def ver_stories(self, maximo):
        """Abre o 1º story do tray e assiste alguns (best-effort). Retorna quantos passou."""
        vistos = 0
        # candidatos pro anel de story no topo do feed (o DOM muda; tenta alguns)
        cands = [
            'div[role="button"] canvas',
            'button:has(canvas)',
            'ul li button[role="button"]',
            'div[role="menu"] li div[role="button"]',
        ]
        try:
            alvo = None
            for s in cands:
                loc = self.page.locator(s).first
                if loc.count():
                    alvo = loc
                    break
            if not alvo:
                return 0
            alvo.click(timeout=4000)
            self.page.wait_for_timeout(2000)
            if "/stories/" not in self.page.url:
                try:
                    self.page.keyboard.press("Escape")
                except Exception:
                    pass
                return 0
            for _ in range(max(1, maximo)):
                self.page.wait_for_timeout(random.randint(2500, 5000))   # assiste
                vistos += 1
                self.page.keyboard.press("ArrowRight")
                self.page.wait_for_timeout(800)
                if "/stories/" not in self.page.url:
                    break
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
        except Exception:
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
        return vistos

    def explorar(self, rolagens=4):
        """Dá uma passada no explorar e rola um pouco."""
        try:
            self.ir("https://www.instagram.com/explore/", timeout=30000)
            for _ in range(max(1, rolagens)):
                self.rolar(random.randint(500, 900))
                self.page.wait_for_timeout(random.randint(1500, 3500))
            return True
        except Exception as e:
            log.warning("~ explorar não rolou: %s", str(e).splitlines()[0][:50])
            return False
