"""Genera docs/diccionario_datos.md y docs/_diccionario.html desde la base viva (information_schema)
más el linaje (origen y regla de transformación) escrito aquí. Requiere el clúster arriba."""
import html, pathlib, subprocess, collections

raiz = pathlib.Path(__file__).resolve().parent.parent
env = dict(l.strip().split("=", 1) for l in (raiz / ".env").read_text().splitlines() if "=" in l)

SQL = r"""
SELECT c.table_schema, c.table_name, c.column_name, c.data_type, c.is_nullable,
  EXISTS (SELECT 1 FROM information_schema.key_column_usage k JOIN information_schema.table_constraints t
          USING (constraint_name, table_schema) WHERE t.constraint_type='PRIMARY KEY'
          AND k.table_name=c.table_name AND k.table_schema=c.table_schema AND k.column_name=c.column_name),
  (SELECT string_agg(DISTINCT ccu.table_schema||'.'||ccu.table_name||'('||ccu.column_name||')', ',')
     FROM information_schema.key_column_usage k JOIN information_schema.table_constraints t USING (constraint_name, table_schema)
     JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name=t.constraint_name AND ccu.table_schema=t.table_schema
     WHERE t.constraint_type='FOREIGN KEY' AND k.table_name=c.table_name AND k.table_schema=c.table_schema AND k.column_name=c.column_name)
FROM information_schema.columns c
WHERE c.table_schema IN ('gold','silver','rt') AND c.table_name !~ '_stg$'
  AND c.table_name IN (SELECT table_name FROM information_schema.tables WHERE table_type='BASE TABLE')
ORDER BY c.table_schema, c.table_name, c.ordinal_position"""

out = subprocess.run(["docker", "run", "--rm", "-e", f"PGPASSWORD={env['PG_CLAVE']}", "postgres:17-alpine", "psql", "-h",
                      "host.docker.internal", "-p", "5433", "-U", env['PG_USUARIO'], "-d", "solarbi", "-tA", "-F", "\t", "-c", SQL],
                     capture_output=True, text=True, check=True).stdout

DESC = {  # tabla: (descripción, grano o nota)
 "gold.dim_fecha": ("Calendario en hora local del sitio (Asia/Shanghai). Dimensión de fechas propia con jerarquía año > trimestre > mes > día.", "Una fila por día."),
 "gold.dim_hora": ("Hora local del día con franja y marca de hora solar.", "Una fila por hora (0 a 23)."),
 "gold.dim_inversor": ("Inversores híbridos del sitio. Dimensión de cambio lento tipo 2 candidata (ver informe, SCD).", "Una fila por inversor."),
 "gold.dim_estado_operativo": ("DIMENSIÓN PROPIA: estado operativo derivado de startupstatus, outstatus y chgstatus. No existe como tal en la fuente.", "Una fila por combinación observada."),
 "gold.dim_alarma": ("DIMENSIÓN PROPIA: catálogo de firmas de alarma (arreglo JSON de 8 palabras) con sus bits activos.", "Una fila por firma distinta."),
 "gold.dim_tipo_contexto": ("DIMENSIÓN PROPIA: tipo de anotación de contexto (fuente + tipo) con una categoría de negocio.", "Una fila por (fuente, tipo)."),
 "gold.fact_lectura_5min": ("P1 Operación: variables eléctricas promediadas por bloque de 5 minutos.", "Un inversor en un bloque de 5 minutos UTC."),
 "gold.fact_energia_dia": ("P2 Balance energético: energía integrada por día y contraste contra el contador del equipo.", "Un inversor en un día local."),
 "gold.fact_evento_alarma": ("P3 Eventos de alarma: episodios de una misma firma de alarma sin interrupción.", "Un episodio (inversor, inicio)."),
 "gold.fact_contexto": ("P4 Contexto operativo: anotaciones del registro de contexto, minimizadas.", "Una anotación del registro de contexto."),
 "gold.parametro": ("Parámetros de negocio editables (tarifa, umbrales).", "Una fila por parámetro."),
 "silver.lectura_5min": ("Lecturas validadas y agregadas a 5 minutos (Silver).", "Inversor y bloque de 5 minutos."),
 "silver.energia_dia_equipo": ("Máximos diarios de los contadores del propio inversor (tabla statistics).", "Inversor y día local."),
 "silver.episodio_alarma": ("Episodios de alarma construidos con una máquina de estados sobre status.", "Inversor e inicio del episodio."),
 "silver.contexto": ("Anotaciones de contexto con JSON minimizado (lista blanca de claves).", "Una anotación."),
 "rt.lectura": ("Lecturas en tiempo real escritas por el simulador (alimentan Grafana).", "Inversor y marca de tiempo."),
}
L = {  # tabla.columna: (origen, regla)
 "gold.dim_fecha.*": ("Calendario generado (sin fuente)", "generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha"),
 "gold.dim_hora.*": ("Calendario generado (sin fuente)", "franja: madrugada <6, mañana <12, tarde <18, noche; hora solar 6 a 17"),
 "gold.dim_inversor.inversor_id": ("analog_measurements.inverter", "clave natural"),
 "gold.dim_inversor.nombre": ("derivado", "'Inversor ' || id"),
 "gold.dim_inversor.primera_lectura": ("silver.lectura_5min.bloque_ts", "MIN por inversor"),
 "gold.dim_inversor.ultima_lectura": ("silver.lectura_5min.bloque_ts", "MAX por inversor"),
 "gold.dim_inversor.activo_al_cierre": ("derivado", "última lectura a menos de 1 día del final del registro"),
 "gold.dim_estado_operativo.estado_id": ("derivado", "startup*100 + out*10 + chg; 9 = dato ausente"),
 "gold.dim_estado_operativo.startupstatus": ("status.startupstatus", "copia"),
 "gold.dim_estado_operativo.outstatus": ("status.outstatus", "copia"),
 "gold.dim_estado_operativo.chgstatus": ("status.chgstatus", "copia"),
 "gold.dim_estado_operativo.categoria": ("derivado (supuesto)", "salida 0/1/2 y carga 1: etiquetas no documentadas por OpenCEM"),
 "gold.dim_estado_operativo.descripcion": ("derivado", "texto con los tres códigos"),
 "gold.dim_alarma.alarma_id": ("derivado", "hash de la firma (0 = sin alarma)"),
 "gold.dim_alarma.firma": ("status.sysalarmflag", "JSON de 8 palabras, castear a jsonb"),
 "gold.dim_alarma.palabra": ("derivado", "índice de la primera palabra distinta de 0"),
 "gold.dim_alarma.valor": ("derivado", "valor de esa palabra"),
 "gold.dim_alarma.bits_activos": ("derivado", "bits en 1, con índice global palabra*16 + bit"),
 "gold.dim_alarma.severidad": ("supuesto", "toda alarma activa se trata como 'aviso': el significado de los bits no está documentado"),
 "gold.dim_alarma.descripcion": ("derivado", "texto con los bits activos"),
 "gold.dim_tipo_contexto.*": ("context.value (JSON): source y context_type", "categoria por fuente: cómputo, sistema, derivado, calendario"),
 "gold.fact_lectura_5min.inversor_id": ("analog_measurements.inverter", "FK a dim_inversor"),
 "gold.fact_lectura_5min.bloque_ts": ("analog_measurements.read_ts", "FLOOR(read_ts / 300) * 300, en UTC"),
 "gold.fact_lectura_5min.fecha_id": ("derivado de bloque_ts", "fecha local Asia/Shanghai (yyyymmdd)"),
 "gold.fact_lectura_5min.hora_id": ("derivado de bloque_ts", "hora local Asia/Shanghai"),
 "gold.fact_lectura_5min.estado_id": ("status.startupstatus/outstatus/chgstatus", "valor de la última lectura del bloque"),
 "gold.fact_lectura_5min.alarma_id": ("status.sysalarmflag", "firma distinta de cero más alta del bloque; 0 si no hay"),
 "gold.fact_lectura_5min.n_lecturas": ("COUNT(*)", "lecturas válidas en el bloque"),
 "gold.fact_lectura_5min.cobertura": ("segundos cubiertos / 300", "cada lectura cubre min(dt hasta la siguiente, 60 s); tope 1"),
 "gold.fact_lectura_5min.pv_w_prom": ("analog_measurements.pv1power [W]", "AVG; valores fuera de 0 a 8000 se anulan (R01)"),
 "gold.fact_lectura_5min.pv_w_max": ("analog_measurements.pv1power [W]", "MAX"),
 "gold.fact_lectura_5min.carga_w_prom": ("analog_measurements.outsumw [W]", "AVG; fuera de 0 a 20000 se anula (R05)"),
 "gold.fact_lectura_5min.red_w_prom": ("analog_measurements.linepowerw_a [W]", "AVG; potencia tomada de la red; fuera de -50 a 20000 se anula (R06)"),
 "gold.fact_lectura_5min.inyec_w_prom": ("analog_measurements.gridpowerw_a [W]", "AVG; salida hacia la red (supuesto)"),
 "gold.fact_lectura_5min.bat_w_prom": ("analog_measurements.battchgpower [W]", "AVG"),
 "gold.fact_lectura_5min.soc_prom": ("analog_measurements.battsoc [%]", "AVG; fuera de 0 a 100 se anula (R02)"),
 "gold.fact_lectura_5min.soc_min": ("analog_measurements.battsoc [%]", "MIN"),
 "gold.fact_lectura_5min.bat_v_prom": ("analog_measurements.battvolt [V]", "AVG; fuera de 30 a 80 se anula (R03)"),
 "gold.fact_lectura_5min.bat_a_prom": ("analog_measurements.battcurr [A]", "AVG; positivo = descarga"),
 "gold.fact_lectura_5min.temp_max_c": ("analog_measurements.temper1 [°C]", "MAX; fuera de -20 a 120 se anula (R04)"),
 "gold.fact_lectura_5min.e_pv_wh": ("analog_measurements.pv1power", "SUM(W * dt) / 3600, dt = min(siguiente - actual, 60 s)"),
 "gold.fact_lectura_5min.e_carga_wh": ("analog_measurements.outsumw", "SUM(W * dt) / 3600"),
 "gold.fact_lectura_5min.e_red_wh": ("analog_measurements.linepowerw_a", "SUM(W * dt) / 3600"),
 "gold.fact_lectura_5min.n_alarmas": ("status.sysalarmflag", "lecturas del bloque con alguna palabra distinta de 0"),
 "gold.fact_energia_dia.pv_kwh_integrado": ("silver.lectura_5min.e_pv_wh", "SUM por día local / 1000"),
 "gold.fact_energia_dia.pv_kwh_equipo": ("statistics.pvgeneratenergytoday [kWh]", "MAX por día local (contador del inversor, se reinicia a medianoche)"),
 "gold.fact_energia_dia.pv_dif_pct": ("derivado", "(integrado - equipo) / equipo"),
 "gold.fact_energia_dia.consumo_kwh_integrado": ("silver.lectura_5min.e_carga_wh", "SUM por día / 1000"),
 "gold.fact_energia_dia.consumo_kwh_equipo": ("statistics.usedenergytoday [kWh]", "MAX por día local"),
 "gold.fact_energia_dia.red_kwh_integrado": ("silver.lectura_5min.e_red_wh", "SUM por día / 1000"),
 "gold.fact_energia_dia.carga_bat_kwh_equipo": ("statistics.batchgenergytoday [kWh]", "MAX por día local"),
 "gold.fact_energia_dia.descarga_bat_kwh_equipo": ("statistics.batdischgenergytoday [kWh]", "MAX por día local"),
 "gold.fact_energia_dia.horas_con_dato": ("silver.lectura_5min.segundos_cubiertos", "SUM / 3600"),
 "gold.fact_energia_dia.cobertura_dia": ("derivado", "horas_con_dato / 24, tope 1 (es la disponibilidad del registro)"),
 "gold.fact_evento_alarma.*": ("status.sysalarmflag", "episodio = racha de lecturas con la misma firma distinta de cero; duracion_s = fin - inicio"),
 "gold.fact_contexto.*": ("context (id, start, end, value)", "value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort"),
 "gold.parametro.*": ("definido por el equipo", "se edita sin tocar el código"),
}
filas = [(l.split("\t") + [""] * 7)[:7] for l in out.splitlines() if l.strip()]
por = collections.OrderedDict()
for esq, tab, col, tipo, nulo, pk, fk in filas:
    por.setdefault(f"{esq}.{tab}", []).append((col, tipo, nulo == "YES", pk == "t", fk))

def lin(t, c):
    return L.get(f"{t}.{c}") or L.get(f"{t}.*") or ("Bronze (SQLite)", "copia con tipo ajustado")

md, hh = ["# Diccionario de datos\n", "Generado por `scripts/gen_diccionario.py` desde la base en ejecución. PK = llave primaria, FK = llave foránea.\n"], []
for t, cols in por.items():
    d, g = DESC.get(t, ("", ""))
    md.append(f"\n## {t}\n\n{d}  \n**Grano:** {g}\n\n| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |\n|---|---|---|---|---|")
    hh.append(f"<h4>{t}</h4><p class='d'>{html.escape(d)} <b>Grano:</b> {html.escape(g)}</p><table class='dic'><tr><th>Columna</th><th>Tipo</th><th>Llave</th><th>Origen</th><th>Regla</th></tr>")
    for col, tipo, nulo, pk, fk in cols:
        llave = ("PK " if pk else "") + (f"FK → {fk}" if fk else "")
        o, r = lin(t, col)
        md.append(f"| {col} | {tipo}{'' if nulo else ' NOT NULL'} | {llave.strip()} | {o} | {r} |")
        hh.append(f"<tr><td>{html.escape(col)}</td><td>{html.escape(tipo)}{'' if nulo else ' NN'}</td><td>{html.escape(llave.strip())}</td><td>{html.escape(o)}</td><td>{html.escape(r)}</td></tr>")
    hh.append("</table>")
(raiz / "docs" / "diccionario_datos.md").write_text("\n".join(md) + "\n", encoding="utf-8")
(raiz / "docs" / "_diccionario.html").write_text("\n".join(hh), encoding="utf-8")
print(len(por), "tablas;", sum(len(c) for c in por.values()), "columnas")
