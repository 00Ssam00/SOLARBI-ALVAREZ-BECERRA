"""Genera grafana/dashboards/solarbi.json (el JSON es producto del código; no se edita a mano)."""
import json, pathlib

DS = {"type": "grafana-postgresql-datasource", "uid": "solarbi-pg"}
INV = "inversor_id IN (${inversor:csv})"


def q(sql, fmt="time_series"):
    return [{"refId": "A", "datasource": DS, "format": fmt, "rawQuery": True, "editorMode": "code", "rawSql": sql}]


def panel(i, tipo, titulo, x, y, w, h, sql, fmt="time_series", unit=None, extra=None, desc=None):
    p = {"id": i, "type": tipo, "title": titulo, "datasource": DS, "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": q(sql, fmt), "fieldConfig": {"defaults": {}, "overrides": []}, "options": {}}
    if unit:
        p["fieldConfig"]["defaults"]["unit"] = unit
    if desc:
        p["description"] = desc
    if extra:
        for k, v in extra.items():
            if k in ("options",):
                p["options"].update(v)
            elif k == "defaults":
                p["fieldConfig"]["defaults"].update(v)
            else:
                p[k] = v
    return p


def fila(i, titulo, y):
    return {"id": i, "type": "row", "title": titulo, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "collapsed": False, "panels": []}


ULT = ("SELECT DISTINCT ON (inversor_id) ts AS time, 'Inversor ' || inversor_id AS metric, {col} AS value "
       "FROM rt.lectura WHERE " + INV + " ORDER BY inversor_id, ts DESC")
RT30 = "ts > now() - interval '30 minutes'"
SEM_SOC = {"defaults": {"min": 0, "max": 100, "thresholds": {"mode": "absolute", "steps": [
    {"color": "red", "value": None}, {"color": "orange", "value": 30}, {"color": "green", "value": 50}]}}}

paneles = [
    fila(100, "Operación en tiempo real (el simulador escribe cada minuto)", 0),
    panel(1, "stat", "Carga de la batería (SOC)", 0, 1, 6, 5, ULT.replace("{col}", "soc"), unit="percent", extra=SEM_SOC,
          desc="Último valor por inversor. La alerta 'Batería baja' se dispara por debajo de 30 %."),
    panel(2, "stat", "Potencia FV ahora", 6, 1, 6, 5, ULT.replace("{col}", "pv_w"), unit="watt"),
    panel(3, "stat", "Alarmas activas (últimos 2 min)", 12, 1, 6, 5,
          "SELECT now() AS time, 'Alarmas' AS metric, COUNT(*) FILTER (WHERE alarma) AS value FROM rt.lectura "
          "WHERE ts > now() - interval '2 minutes' AND " + INV,
          extra={"defaults": {"thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}, {"color": "red", "value": 1}]}}}),
    panel(4, "stat", "Temperatura", 18, 1, 6, 5, ULT.replace("{col}", "temp_c"), unit="celsius"),
    panel(5, "timeseries", "Potencia FV y carga (30 min)", 0, 6, 12, 8,
          "SELECT ts AS time, 'FV inv ' || inversor_id AS metric, pv_w AS value FROM rt.lectura WHERE " + RT30 + " AND " + INV +
          " UNION ALL SELECT ts, 'Carga inv ' || inversor_id, carga_w FROM rt.lectura WHERE " + RT30 + " AND " + INV + " ORDER BY 1",
          unit="watt"),
    panel(6, "timeseries", "SOC de la batería (30 min)", 12, 6, 12, 8,
          "SELECT ts AS time, 'Inversor ' || inversor_id AS metric, soc AS value FROM rt.lectura WHERE " + RT30 + " AND " + INV + " ORDER BY 1",
          unit="percent", extra={"defaults": {"min": 0, "max": 100}}),
    fila(101, "Histórico (usa el rango de tiempo del tablero y el filtro de inversor)", 14),
    panel(7, "timeseries", "Energía FV diaria: integrada vs contador del equipo", 0, 15, 12, 8,
          "SELECT d.fecha::timestamp AS time, SUM(f.pv_kwh_integrado) AS \"Integrada (kWh)\", SUM(f.pv_kwh_equipo) AS \"Contador del equipo (kWh)\" "
          "FROM gold.fact_energia_dia f JOIN gold.dim_fecha d USING (fecha_id) WHERE $__timeFilter(d.fecha) AND f." + INV + " GROUP BY 1 ORDER BY 1",
          unit="kwatth", extra={"options": {}, "defaults": {"custom": {"drawStyle": "bars", "fillOpacity": 60}}},
          desc="La diferencia es la conciliación: el contador cuenta el día completo; la integración solo ve donde hay lecturas."),
    panel(8, "barchart", "Perfil horario de potencia FV (promedio)", 12, 15, 12, 8,
          "SELECT hora_id::text AS \"Hora local\", AVG(pv_w_prom) AS \"FV promedio (W)\" FROM gold.fact_lectura_5min "
          "WHERE $__timeFilter(bloque_ts) AND " + INV + " GROUP BY hora_id ORDER BY hora_id", fmt="table", unit="watt"),
    panel(9, "timeseries", "SOC mínimo por ${agrupacion}", 0, 23, 12, 8,
          "SELECT date_trunc('${agrupacion}', bloque_ts) AS time, 'Inversor ' || inversor_id AS metric, MIN(soc_min) AS value "
          "FROM gold.fact_lectura_5min WHERE $__timeFilter(bloque_ts) AND " + INV + " GROUP BY 1, 2 ORDER BY 1",
          unit="percent", extra={"defaults": {"min": 0, "max": 100}}),
    panel(10, "timeseries", "Eventos de alarma por día", 12, 23, 12, 8,
          "SELECT date_trunc('day', inicio_ts) AS time, 'Inversor ' || inversor_id AS metric, COUNT(*) AS value "
          "FROM gold.fact_evento_alarma WHERE $__timeFilter(inicio_ts) AND " + INV + " GROUP BY 1, 2 ORDER BY 1",
          extra={"defaults": {"custom": {"drawStyle": "bars", "fillOpacity": 60}}}),
    fila(102, "Calidad del dato (última corrida del ETL)", 31),
    panel(11, "table", "Conteos por regla de calidad", 0, 32, 12, 9,
          "SELECT regla AS \"Regla\", accion AS \"Acción\", SUM(filas_afectadas) AS \"Filas\" FROM etl.regla_calidad "
          "WHERE corrida_id = (SELECT MAX(corrida_id) FROM etl.corrida WHERE estado = 'ok') GROUP BY 1, 2 ORDER BY 1", fmt="table"),
    panel(12, "table", "Conciliación Bronze → Silver → Gold", 12, 32, 12, 9,
          "SELECT control AS \"Control\", inversor_id AS \"Inversor\", valor_origen AS \"Origen\", valor_destino AS \"Destino\", cuadra AS \"Cuadra\" "
          "FROM etl.conciliacion WHERE corrida_id = (SELECT MAX(corrida_id) FROM etl.corrida WHERE estado = 'ok') ORDER BY 1, 2", fmt="table"),
]

dash = {
    "uid": "solarbi-operacion", "title": "SolarBI: operación de la microrred", "tags": ["solarbi", "taller6"],
    "timezone": "browser", "schemaVersion": 39, "version": 1, "editable": False, "refresh": "10s",
    "time": {"from": "2026-06-01T00:00:00.000Z", "to": "2026-06-20T00:00:00.000Z"},
    "templating": {"list": [
        {"name": "inversor", "label": "Inversor", "type": "query", "datasource": DS, "multi": True, "includeAll": True,
         "refresh": 1, "current": {"selected": True, "text": "All", "value": "$__all"},
         "query": "SELECT inversor_id AS __value, nombre AS __text FROM gold.dim_inversor ORDER BY 1"},
        {"name": "agrupacion", "label": "Agrupar por", "type": "custom", "query": "hour,day",
         "current": {"selected": True, "text": "day", "value": "day"},
         "options": [{"text": "hour", "value": "hour", "selected": False}, {"text": "day", "value": "day", "selected": True}]},
    ]},
    "panels": paneles,
}
out = pathlib.Path(__file__).resolve().parent.parent / "grafana" / "dashboards" / "solarbi.json"
out.write_text(json.dumps(dash, ensure_ascii=False, indent=1), encoding="utf-8")
print("escrito", out)
