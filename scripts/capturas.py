"""Capturas de Grafana para el informe. Usa Chrome instalado y autenticación básica contra Grafana local.
Uso: .venv/bin/python scripts/capturas.py   (requiere: pip install playwright)"""
import base64, pathlib, sys
from playwright.sync_api import sync_playwright

raiz = pathlib.Path(__file__).resolve().parent.parent
env = dict(l.strip().split("=", 1) for l in (raiz / ".env").read_text().splitlines() if "=" in l)
auth = base64.b64encode(f"admin:{env['GRAFANA_CLAVE']}".encode()).decode()
destino = raiz / "docs" / "img"
destino.mkdir(parents=True, exist_ok=True)
base = "http://localhost:3001"
tag = sys.argv[1] if len(sys.argv) > 1 else "normal"

with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", headless=True)
    ctx = nav.new_context(viewport={"width": 1600, "height": 1000}, extra_http_headers={"Authorization": f"Basic {auth}"})
    pg = ctx.new_page()
    for uid, nombre, alto in (("solarbi-tiempo-real", "tiempo_real", 760), ("solarbi-historico", "historico", 1500)):
        pg.set_viewport_size({"width": 1600, "height": alto})
        pg.goto(f"{base}/d/{uid}?orgId=1&kiosk", wait_until="domcontentloaded")
        pg.wait_for_timeout(15000)
        pg.screenshot(path=str(destino / f"grafana_{nombre}_{tag}.png"))
    pg.close()
    pg = ctx.new_page()
    pg.set_viewport_size({"width": 1600, "height": 900})
    pg.goto(f"{base}/alerting/list?view=list", wait_until="domcontentloaded")
    pg.wait_for_timeout(6000)
    pg.screenshot(path=str(destino / f"grafana_alertas_{tag}.png"))
    nav.close()
print("capturas en", destino)
