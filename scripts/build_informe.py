"""Construye docs/BI_Taller6_Alvarez_Becerra.pdf desde docs/informe_fuente.html.
Pasos previos: scripts/evidencia.sh, scripts/gen_diccionario.py y scripts/capturas.py. Usa Chrome instalado."""
import html, pathlib, subprocess, sys

raiz = pathlib.Path(__file__).resolve().parent.parent
docs = raiz / "docs"
ev = docs / "evidencia"
leer = lambda p: html.escape(p.read_text(encoding="utf-8").rstrip())


def caja(x, y, w, h, titulo, sub="", color="#fdfbf6", borde="#b9b19d"):
    t = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{color}" stroke="{borde}"/>'
    t += f'<text x="{x + w/2}" y="{y + 20}" text-anchor="middle" font-size="12" font-weight="700" fill="#1c2430">{html.escape(titulo)}</text>'
    for i, l in enumerate(sub.split("|") if sub else []):
        t += f'<text x="{x + w/2}" y="{y + 36 + i*13}" text-anchor="middle" font-size="9.5" fill="#55606f">{html.escape(l)}</text>'
    return t


def flecha(x1, y1, x2, y2, etiqueta="", dash=False):
    t = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#8a6a1f" stroke-width="1.6" marker-end="url(#a)"{" stroke-dasharray=\"5 3\"" if dash else ""}/>'
    if etiqueta:
        t += f'<text x="{(x1+x2)/2}" y="{(y1+y2)/2 - 4}" text-anchor="middle" font-size="9" fill="#8a6a1f">{html.escape(etiqueta)}</text>'
    return t


def svg_arq():
    s = ['<div class="fig"><svg viewBox="0 0 1000 520" width="100%" font-family="Helvetica, Arial, sans-serif">',
         '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#8a6a1f"/></marker></defs>',
         '<rect x="8" y="8" width="196" height="504" rx="10" fill="#f1efe8" stroke="#cfc8b6"/><text x="106" y="30" text-anchor="middle" font-size="12" font-weight="700">Anfitrión (macOS)</text>',
         caja(20, 60, 172, 70, "OpenCEM (Bronze)", "SQLite 4,4 GB|solo lectura"),
         caja(20, 290, 172, 60, "Power BI / DBeaver", "localhost:5433"),
         caja(20, 400, 172, 60, "Navegador", "localhost:3001"),
         '<rect x="226" y="8" width="766" height="504" rx="10" fill="#eef3fb" stroke="#9fb4d6"/><text x="609" y="30" text-anchor="middle" font-size="12" font-weight="700">Kubernetes (OrbStack) · namespace solarbi</text>',
         caja(250, 52, 724, 52, "Secret solarbi-credenciales · ConfigMaps solarbi-config, grafana-datasources, grafana-alertas, grafana-dashboards", "", "#fff7e6", "#e0b96a"),
         caja(250, 140, 170, 76, "Job etl", "solarbi-etl:1|Bronze → Silver → Gold"),
         caja(250, 235, 170, 70, "CronJob simulador", "solarbi-simulador:1|cada minuto → rt.lectura"),
         caja(500, 190, 220, 130, "StatefulSet postgres", "postgres:17-alpine|schemas silver · gold · etl · rt|PVC 5 Gi (local-path)|probes + limits"),
         caja(780, 190, 194, 130, "Deployment grafana", "grafana 11.6.0|provisioning: fuente, 2 tableros,|2 alertas · probes + limits"),
         caja(500, 400, 220, 52, "Service postgres-externo", "LoadBalancer :5433"),
         caja(780, 400, 194, 52, "Service grafana", "LoadBalancer :3001"),
         caja(500, 120, 220, 36, "Service postgres (DNS)", "", "#fdfbf6"),
         flecha(192, 95, 250, 175, "hostPath RO"),
         flecha(420, 178, 500, 240, "COPY"),
         flecha(420, 275, 500, 285, "INSERT"),
         flecha(780, 255, 720, 255, "SELECT (lector_bi)"),
         flecha(610, 400, 610, 322, ""),
         flecha(192, 330, 500, 426, "SQL"),
         flecha(877, 400, 877, 322, ""),
         '<path d="M877,452 L877,490 L106,490 L106,462" fill="none" stroke="#8a6a1f" stroke-width="1.6" marker-end="url(#a)"/><text x="480" y="484" text-anchor="middle" font-size="9" fill="#8a6a1f">HTTP</text>',
         '</svg><p>Figura 5. Arquitectura: de la fuente al consumo, con los objetos de Kubernetes.</p></div>']
    return "\n".join(s)


def svg_modelo():
    dims = [("dim_fecha", 0), ("dim_hora", 1), ("dim_inversor", 2), ("dim_estado_operativo", 3), ("dim_alarma", 4), ("dim_tipo_contexto", 5)]
    hechos = [("fact_lectura_5min", "P1 · 5 min", [0, 1, 2, 3, 4]), ("fact_energia_dia", "P2 · día", [0, 2]),
              ("fact_evento_alarma", "P3 · episodio", [0, 1, 2, 4]), ("fact_contexto", "P4 · anotación", [0, 1, 2, 5])]
    W, wd, wf = 1000, 150, 200
    cx_d = [20 + i * 160 + wd / 2 for i in range(6)]
    cx_f = [30 + i * 240 + wf / 2 for i in range(4)]
    s = [f'<div class="fig"><svg viewBox="0 0 {W} 400" width="100%" font-family="Helvetica, Arial, sans-serif">']
    for fi, (n, g, ds) in enumerate(hechos):
        for d in ds:
            s.append(f'<line x1="{cx_f[fi]}" y1="270" x2="{cx_d[d]}" y2="90" stroke="#b9b19d" stroke-width="1"/>')
    for n, i in dims:
        propia = n in ("dim_estado_operativo", "dim_alarma", "dim_tipo_contexto")
        s.append(caja(20 + i * 160, 30, wd, 60, n, "dimensión propia" if propia else "dimensión conformada", "#fff7e6" if propia else "#eef3fb", "#e0b96a" if propia else "#9fb4d6"))
    for fi, (n, g, ds) in enumerate(hechos):
        s.append(caja(30 + fi * 240, 270, wf, 62, n, g, "#e9f3e8", "#8fb98b"))
    s.append('</svg><p>Figura 6. Constelación de hechos: cuatro procesos de negocio que comparten dimensiones. En ámbar, las dimensiones construidas por el equipo.</p></div>')
    return "\n".join(s)


def pbi():
    ims = sorted((docs / "img").glob("powerbi_*.png"))
    if not ims:
        return '<div class="pend"><b>Capturas de Power BI pendientes.</b> Se construye en el PC con Windows (ver docs/powerbi_guia.md). Guarda las capturas como docs/img/powerbi_1.png, powerbi_2.png, … y vuelve a ejecutar scripts/build_informe.py.</div>'
    return "\n".join(f'<div class="fig"><img src="img/{p.name}"><p>Figura Power BI {i+1}.</p></div>' for i, p in enumerate(ims))


def aviso(t):
    return t


h = (docs / "informe_fuente.html").read_text(encoding="utf-8")
h = h.replace("{{EVID_INVENTARIO}}", leer(ev / "00b_inventario_bronze.txt"))
h = h.replace("{{EVID_CHECKSUM}}", leer(ev / "00_descarga_checksum.txt"))
h = h.replace("{{EVID_RESILIENCIA}}", leer(ev / "04_resiliencia.txt"))
h = h.replace("{{EVID_GET}}", leer(ev / "01_kubectl_get.txt"))
desc = "\n".join((ev / "02_kubectl_describe.txt").read_text(encoding="utf-8").splitlines()[:64])
h = h.replace("{{EVID_DESCRIBE}}", html.escape(desc) + "\n[...] (salida completa en docs/evidencia/02_kubectl_describe.txt)")
h = h.replace("{{DICCIONARIO}}", (docs / "_diccionario.html").read_text(encoding="utf-8"))
h = h.replace("{{SVG_ARQ}}", svg_arq()).replace("{{SVG_MODELO}}", svg_modelo()).replace("{{PBI}}", pbi())
fuente = docs / "_informe.html"
fuente.write_text(h, encoding="utf-8")
pdf = docs / "BI_Taller6_Alvarez_Becerra.pdf"
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", f"file://{fuente}"],
               check=True, capture_output=True)
print("PDF:", pdf, pdf.stat().st_size // 1024, "KB")
