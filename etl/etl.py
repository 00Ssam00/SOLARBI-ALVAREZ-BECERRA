"""ETL SolarBI: Bronze (SQLite OpenCEM) -> Silver -> Gold (PostgreSQL).

Idempotente: cada tabla se escribe con ON CONFLICT DO UPDATE sobre su clave
natural, así que repetir la corrida (o solaparla) deja los mismos datos.
Parámetros por variables de entorno: SQLITE_PATH, ETL_DESDE, ETL_HASTA (UTC,
YYYY-MM-DD) y las PG* de conexión.
"""
import datetime as dt
import glob
import json
import os
import sqlite3
import sys
import time

import psycopg
from psycopg import sql as psql

BLOQUE_S = 300
TZ_LOCAL_S = 8 * 3600          # Asia/Shanghai (sin horario de verano)
GAP_MAX_S = 60                 # intervalo mayor: no se integra energía
DT_TIPICO_S = 12.6

# Rangos físicos plausibles para anular valores (regla -> acción 'anulada').
RANGOS = {
    "pv": (0, 8000), "soc": (0, 100), "volt": (30, 80),
    "temp": (-20, 120), "carga": (0, 20000), "red": (-50, 20000),
}


NZ_ALARMA = ("(sysalarmflag IS NOT NULL AND sysalarmflag NOT IN "
             "('[0,0,0,0,0,0,0,0]','[null]'))")


def log(msg):
    print(f"[etl {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ts_utc(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


def conectar_pg():
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"), port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "solarbi"), user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""), autocommit=False)


def aplicar_ddl(pg):
    for f in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "sql", "0[123]_*.sql"))):
        log(f"DDL {os.path.basename(f)}")
        with open(f, encoding="utf-8") as fh:
            pg.execute(fh.read())
    pg.commit()


def asegurar_roles(pg):
    """Roles de mínimo privilegio: lector_bi (Grafana y Power BI) y simulador_rw (solo rt)."""
    for rol, var in (("lector_bi", "LECTOR_CLAVE"), ("simulador_rw", "SIM_CLAVE")):
        clave = os.environ.get(var)
        if not clave:
            log(f"sin {var}: no se crea el rol {rol}")
            continue
        existe = pg.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rol,)).fetchone()
        pg.execute(psql.SQL("{} ROLE {} LOGIN PASSWORD {}").format(
            psql.SQL("ALTER" if existe else "CREATE"), psql.Identifier(rol), psql.Literal(clave)))
        if rol == "lector_bi":
            pg.execute("GRANT USAGE ON SCHEMA gold, silver, etl, rt TO lector_bi")
            pg.execute("GRANT SELECT ON ALL TABLES IN SCHEMA gold, silver, etl, rt TO lector_bi")
        else:
            pg.execute("GRANT USAGE ON SCHEMA rt, gold TO simulador_rw")
            pg.execute("GRANT SELECT, INSERT, DELETE ON rt.lectura TO simulador_rw")
            pg.execute("GRANT SELECT ON gold.fact_lectura_5min TO simulador_rw")
    pg.commit()


def expr_nz(col, lo, hi):
    return f"CASE WHEN {col} BETWEEN {lo} AND {hi} THEN {col} END"


def reglas_analog(lite, t0, t1):
    """Cuenta por inversor cuántas filas rompen cada regla (una sola pasada)."""
    r = RANGOS
    def fuera(col, k):
        return f"SUM({col} IS NOT NULL AND {col} NOT BETWEEN {r[k][0]} AND {r[k][1]})"
    sql = f"""
    SELECT inverter, COUNT(*),
      {fuera('pv1power','pv')}, {fuera('battsoc','soc')}, {fuera('battvolt','volt')},
      {fuera('temper1','temp')}, {fuera('outsumw','carga')}, {fuera('linepowerw_a','red')},
      SUM(NOT (COALESCE(pv1power BETWEEN {r['pv'][0]} AND {r['pv'][1]}, 0) OR COALESCE(outsumw BETWEEN {r['carga'][0]} AND {r['carga'][1]}, 0) OR COALESCE(battsoc BETWEEN {r['soc'][0]} AND {r['soc'][1]}, 0))),
      SUM(pv1power IS NULL)
    FROM analog_measurements WHERE read_ts >= ? AND read_ts < ? GROUP BY inverter"""
    return lite.execute(sql, (t0, t1)).fetchall()


def silver_lectura(lite, pg, t0, t1):
    r = RANGOS
    sql = f"""
    WITH base AS (
      SELECT inverter, read_ts,
             {expr_nz('pv1power', *r['pv'])}      AS pv,
             {expr_nz('battsoc', *r['soc'])}      AS soc,
             {expr_nz('battvolt', *r['volt'])}    AS volt,
             {expr_nz('temper1', *r['temp'])}     AS temp,
             {expr_nz('outsumw', *r['carga'])}    AS carga,
             {expr_nz('linepowerw_a', *r['red'])} AS red,
             gridpowerw_a AS inyec, battchgpower AS bat_w, battcurr AS bat_a,
             MIN(COALESCE(LEAD(read_ts) OVER (PARTITION BY inverter ORDER BY read_ts) - read_ts, {DT_TIPICO_S}), {GAP_MAX_S}) AS dts
      FROM analog_measurements WHERE read_ts >= ? AND read_ts < ?
    )
    SELECT inverter, CAST(read_ts / {BLOQUE_S} AS INTEGER) * {BLOQUE_S} AS b, COUNT(*),
           AVG(pv), MAX(pv), AVG(carga), AVG(red), AVG(inyec), AVG(bat_w),
           AVG(soc), MIN(soc), AVG(volt), AVG(bat_a), MAX(temp),
           SUM(pv * dts) / 3600.0, SUM(carga * dts) / 3600.0, SUM(red * dts) / 3600.0,
           SUM(dts)
    FROM base WHERE NOT (pv IS NULL AND carga IS NULL AND soc IS NULL)
    GROUP BY inverter, b"""
    filas = {}
    for row in lite.execute(sql, (t0, t1)):
        filas[(row[0], row[1])] = list(row)
    log(f"Silver analog: {len(filas)} bloques")

    sql_s = f"""
    SELECT inverter, CAST(read_ts / {BLOQUE_S} AS INTEGER) * {BLOQUE_S} AS b,
           startupstatus, outstatus, chgstatus, MAX(read_ts),
           SUM({NZ_ALARMA}), MAX(CASE WHEN {NZ_ALARMA} THEN sysalarmflag END)
    FROM status WHERE read_ts >= ? AND read_ts < ? GROUP BY inverter, b"""
    est = {(r[0], r[1]): r for r in lite.execute(sql_s, (t0, t1))}
    log(f"Silver status: {len(est)} bloques")

    with pg.cursor() as cur, cur.copy("""COPY silver.lectura_5min_stg (inversor_id, bloque_ts, n_lecturas,
        pv_w_prom, pv_w_max, carga_w_prom, red_w_prom, inyec_w_prom, bat_w_prom, soc_prom, soc_min,
        bat_v_prom, bat_a_prom, temp_max_c, e_pv_wh, e_carga_wh, e_red_wh, segundos_cubiertos,
        startupstatus, outstatus, chgstatus, n_alarmas, alarma_firma) FROM STDIN""") as cp:
        for k, f in filas.items():
            e = est.get(k)
            cp.write_row([f[0], dt.datetime.fromtimestamp(f[1], dt.timezone.utc), f[2], *f[3:18],
                          e[2] if e else None, e[3] if e else None, e[4] if e else None,
                          int(e[6] or 0) if e else 0, e[7] if e else None])
    return len(filas)


def episodios_alarma(lite, pg, t0, t1):
    """Máquina de estados sobre status: un episodio = racha con la misma firma distinta de cero."""
    cur = lite.execute("""SELECT inverter, read_ts, sysalarmflag FROM status
                          WHERE read_ts >= ? AND read_ts < ? ORDER BY inverter, read_ts""", (t0, t1))
    eps, act = [], {}
    for inv, ts, firma in cur:
        nz = firma is not None and firma not in ("[0,0,0,0,0,0,0,0]", "[null]")
        a = act.get(inv)
        if a and (not nz or a["firma"] != firma):
            eps.append((inv, a["ini"], a["fin"], a["firma"], a["n"]))
            a = act[inv] = None
        if nz:
            if a is None:
                act[inv] = {"ini": ts, "fin": ts, "firma": firma, "n": 1}
            else:
                a["fin"] = ts
                a["n"] += 1
    eps += [(i, a["ini"], a["fin"], a["firma"], a["n"]) for i, a in act.items() if a]
    with pg.cursor() as cur2, cur2.copy("""COPY silver.episodio_alarma_stg
          (inversor_id, inicio_ts, fin_ts, firma, n_lecturas) FROM STDIN""") as cp:
        for inv, i, f, firma, n in eps:
            cp.write_row([inv, dt.datetime.fromtimestamp(i, dt.timezone.utc),
                          dt.datetime.fromtimestamp(f, dt.timezone.utc), firma, n])
    return len(eps)


def energia_equipo(lite, pg, t0, t1):
    rows = lite.execute(f"""
      SELECT inverter, date(read_ts + {TZ_LOCAL_S}, 'unixepoch') AS d,
             MAX(pvgeneratenergytoday), MAX(batchgenergytoday), MAX(batdischgenergytoday),
             MAX(usedenergytoday), COUNT(*)
      FROM statistics WHERE read_ts >= ? AND read_ts < ? GROUP BY inverter, d""", (t0, t1)).fetchall()
    with pg.cursor() as cur, cur.copy("""COPY silver.energia_dia_equipo_stg (inversor_id, fecha_local,
         pv_kwh, carga_bat_kwh, descarga_bat_kwh, consumo_kwh, n_lecturas) FROM STDIN""") as cp:
        for r in rows:
            cp.write_row([r[0], dt.date.fromisoformat(r[1]), *r[2:]])
    return len(rows)


# Lista blanca de claves del JSON de contexto (minimización de datos personales, Ley 1581).
CLAVES_OK = {"source", "device", "inverter", "context_type", "task_type", "cpu_cores_active",
             "llm_estimated_task_effort", "task_files", "model", "dataset", "epochs", "batch_size",
             "metrics", "weekday", "day_type", "local_date", "sample_count", "active_minutes"}


def contexto(lite, pg, t0, t1):
    """Carga context.value (JSON) minimizado. Devuelve (cargadas, json_invalido, filas_recortadas)."""
    n = inval = recortadas = 0
    with pg.cursor() as cur, cur.copy("""COPY silver.contexto_stg (contexto_id, registrado_ts, inicio_ts, fin_ts, valor)
                                         FROM STDIN""") as cp:
        for cid, rec, ini, fin, val in lite.execute(
                'SELECT id, recorded, start, "end", value FROM context WHERE start >= ? AND start < ?', (t0, t1)):
            try:
                d = json.loads(val)
                assert isinstance(d, dict)
            except Exception:
                inval += 1
                continue
            limpio = {k: v for k, v in d.items() if k in CLAVES_OK}
            if len(limpio) != len(d):
                recortadas += 1
            f = lambda x: dt.datetime.fromtimestamp(x, dt.timezone.utc)
            cp.write_row([cid, f(rec) if rec else None, f(ini), f(fin), json.dumps(limpio)])
            n += 1
    return n, inval, recortadas


def main():
    sqlite_path = os.environ.get("SQLITE_PATH", "/datos/opencem-v1.0.0.sqlite")
    desde = ts_utc(os.environ.get("ETL_DESDE", "2025-07-12"))
    hasta = ts_utc(os.environ.get("ETL_HASTA", "2026-07-14"))
    t0, t1 = desde.timestamp(), hasta.timestamp()
    log(f"Ventana UTC {desde:%Y-%m-%d} a {hasta:%Y-%m-%d}; Bronze: {sqlite_path}")

    lite = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    pg = conectar_pg()
    aplicar_ddl(pg)
    pg.execute("UPDATE etl.corrida SET estado='error', fin=now(), detalle='interrumpida' WHERE estado='en_curso'")
    corrida = pg.execute("INSERT INTO etl.corrida (desde_utc, hasta_utc) VALUES (%s,%s) RETURNING corrida_id",
                         (desde, hasta)).fetchone()[0]
    pg.commit()
    try:
        # tablas de paso: se recrean vacías en cada corrida
        pg.execute("""DROP TABLE IF EXISTS silver.lectura_5min_stg, silver.episodio_alarma_stg,
                      silver.energia_dia_equipo_stg;
          CREATE UNLOGGED TABLE silver.lectura_5min_stg (LIKE silver.lectura_5min INCLUDING DEFAULTS);
          CREATE UNLOGGED TABLE silver.episodio_alarma_stg (inversor_id SMALLINT, inicio_ts TIMESTAMPTZ,
                      fin_ts TIMESTAMPTZ, firma TEXT, n_lecturas INTEGER);
          CREATE UNLOGGED TABLE silver.energia_dia_equipo_stg (LIKE silver.energia_dia_equipo INCLUDING DEFAULTS);
          DROP TABLE IF EXISTS silver.contexto_stg;
          CREATE UNLOGGED TABLE silver.contexto_stg (contexto_id INTEGER, registrado_ts TIMESTAMPTZ,
                      inicio_ts TIMESTAMPTZ, fin_ts TIMESTAMPTZ, valor JSONB)""")

        # --- reglas de calidad (conteos) ---
        reglas = []
        bronze_analog = {}
        for (inv, n, pv, soc, volt, temp, carga, red, sinm, pvn) in reglas_analog(lite, t0, t1):
            bronze_analog[inv] = n
            reglas += [
                ("R01_PV_FUERA_RANGO", "analog_measurements", inv, pv, "anulada", "pv1power fuera de 0..8000 W"),
                ("R02_SOC_FUERA_RANGO", "analog_measurements", inv, soc, "anulada", "battsoc fuera de 0..100 %"),
                ("R03_VOLT_FUERA_RANGO", "analog_measurements", inv, volt, "anulada", "battvolt fuera de 30..80 V"),
                ("R04_TEMP_FUERA_RANGO", "analog_measurements", inv, temp, "anulada", "temper1 fuera de -20..120 C"),
                ("R05_CARGA_FUERA_RANGO", "analog_measurements", inv, carga, "anulada", "outsumw fuera de 0..20000 W"),
                ("R06_RED_FUERA_RANGO", "analog_measurements", inv, red, "anulada", "linepowerw_a fuera de -50..20000 W"),
                ("R07_FILA_SIN_MEDIDAS", "analog_measurements", inv, sinm, "descartada", "pv, carga y soc nulos (o anulados) a la vez"),
                ("R08_PV_NULO", "analog_measurements", inv, pvn, "conservada", "pv1power nulo (se deja nulo, sin imputar)"),
            ]
        for inv, n in lite.execute("""SELECT inverter, SUM(sysalarmflag IS NULL OR sysalarmflag='[null]')
                                      FROM status WHERE read_ts >= ? AND read_ts < ? GROUP BY inverter""", (t0, t1)):
            reglas.append(("R09_ALARMA_AUSENTE", "status", inv, n or 0, "conservada", "sysalarmflag nulo: no se asume sin alarma"))
        log(f"Reglas: {len(reglas)} conteos")

        n_bl = silver_lectura(lite, pg, t0, t1)
        n_ep = episodios_alarma(lite, pg, t0, t1)
        n_ed = energia_equipo(lite, pg, t0, t1)
        n_ctx, ctx_inval, ctx_recort = contexto(lite, pg, t0, t1)
        reglas += [("R12_CONTEXTO_JSON_INVALIDO", "context", 0, ctx_inval, "descartada", "context.value no es un objeto JSON válido"),
                   ("R13_CONTEXTO_CLAVES_PERSONALES", "context", 0, ctx_recort, "recortada", "se eliminaron claves fuera de la lista blanca (comandos, rutas, texto libre)")]
        log(f"Contexto: {n_ctx} anotaciones, {ctx_inval} inválidas, {ctx_recort} recortadas")
        log(f"Silver staging: {n_bl} bloques, {n_ep} episodios, {n_ed} días de equipo")

        # --- carga a Silver (upsert) ---
        pg.execute("""INSERT INTO silver.lectura_5min SELECT * FROM silver.lectura_5min_stg
            ON CONFLICT (inversor_id, bloque_ts) DO UPDATE SET
              n_lecturas=EXCLUDED.n_lecturas, pv_w_prom=EXCLUDED.pv_w_prom, pv_w_max=EXCLUDED.pv_w_max,
              carga_w_prom=EXCLUDED.carga_w_prom, red_w_prom=EXCLUDED.red_w_prom, inyec_w_prom=EXCLUDED.inyec_w_prom,
              bat_w_prom=EXCLUDED.bat_w_prom, soc_prom=EXCLUDED.soc_prom, soc_min=EXCLUDED.soc_min,
              bat_v_prom=EXCLUDED.bat_v_prom, bat_a_prom=EXCLUDED.bat_a_prom, temp_max_c=EXCLUDED.temp_max_c,
              e_pv_wh=EXCLUDED.e_pv_wh, e_carga_wh=EXCLUDED.e_carga_wh, e_red_wh=EXCLUDED.e_red_wh,
              segundos_cubiertos=EXCLUDED.segundos_cubiertos, startupstatus=EXCLUDED.startupstatus,
              outstatus=EXCLUDED.outstatus, chgstatus=EXCLUDED.chgstatus, n_alarmas=EXCLUDED.n_alarmas,
              alarma_firma=EXCLUDED.alarma_firma""")
        pg.execute("""INSERT INTO silver.episodio_alarma
              SELECT inversor_id, inicio_ts, fin_ts, firma::jsonb, n_lecturas FROM silver.episodio_alarma_stg
            ON CONFLICT (inversor_id, inicio_ts) DO UPDATE SET
              fin_ts=EXCLUDED.fin_ts, firma=EXCLUDED.firma, n_lecturas=EXCLUDED.n_lecturas""")
        pg.execute("""INSERT INTO silver.energia_dia_equipo SELECT * FROM silver.energia_dia_equipo_stg
            ON CONFLICT (inversor_id, fecha_local) DO UPDATE SET
              pv_kwh=EXCLUDED.pv_kwh, carga_bat_kwh=EXCLUDED.carga_bat_kwh,
              descarga_bat_kwh=EXCLUDED.descarga_bat_kwh, consumo_kwh=EXCLUDED.consumo_kwh,
              n_lecturas=EXCLUDED.n_lecturas""")

        pg.execute("""INSERT INTO silver.contexto SELECT * FROM silver.contexto_stg
            ON CONFLICT (contexto_id) DO UPDATE SET registrado_ts=EXCLUDED.registrado_ts,
              inicio_ts=EXCLUDED.inicio_ts, fin_ts=EXCLUDED.fin_ts, valor=EXCLUDED.valor""")

        # --- regla de bloque y hueco, ya en Silver ---
        for inv, bajo, gaps in pg.execute("""
            SELECT inversor_id, COUNT(*) FILTER (WHERE segundos_cubiertos < 75),
                   COUNT(*) FILTER (WHERE segundos_cubiertos < 300 * 0.9)
            FROM silver.lectura_5min_stg GROUP BY 1""").fetchall():
            reglas.append(("R10_BLOQUE_BAJA_COBERTURA", "silver.lectura_5min", inv, bajo, "marcada", "bloque con menos de 25 % de cobertura (<75 s)"))
            reglas.append(("R11_BLOQUE_CON_HUECOS", "silver.lectura_5min", inv, gaps, "marcada", "bloque con menos de 90 % de cobertura"))
        for (rg, tab, inv, n, acc, desc) in reglas:
            pg.execute("""INSERT INTO etl.regla_calidad (corrida_id, regla, tabla_origen, inversor_id, filas_afectadas, accion, descripcion)
                          VALUES (%s,%s,%s,%s,%s,%s,%s)""", (corrida, rg, tab, inv, int(n or 0), acc, desc))

        # --- dimensiones y hechos (Gold) ---
        pg.execute(open(os.path.join(os.path.dirname(__file__), "sql", "04_cargar_gold.sql"), encoding="utf-8").read())

        # --- conciliación ---
        for inv, n_bronze in bronze_analog.items():
            descartadas = next(n for (rg, _, i, n, _, _) in reglas if rg == "R07_FILA_SIN_MEDIDAS" and i == inv)
            usadas = pg.execute("SELECT COALESCE(SUM(n_lecturas),0) FROM silver.lectura_5min_stg WHERE inversor_id=%s", (inv,)).fetchone()[0]
            ok = (n_bronze - descartadas) == usadas
            pg.execute("INSERT INTO etl.conciliacion (corrida_id, control, inversor_id, valor_origen, valor_destino, cuadra) VALUES (%s,%s,%s,%s,%s,%s)",
                       (corrida, "filas Bronze - descartadas = filas en Silver", inv, n_bronze - descartadas, usadas, ok))
        for inv, a, b in pg.execute("""SELECT s.inversor_id, SUM(s.e_pv_wh)/1000, (SELECT SUM(pv_kwh_integrado) FROM gold.fact_energia_dia g
                 WHERE g.inversor_id = s.inversor_id AND g.fecha_id BETWEEN %s AND %s)
                 FROM silver.lectura_5min_stg s GROUP BY 1""",
                 (int(desde.strftime("%Y%m%d")), int(hasta.strftime("%Y%m%d")))).fetchall():
            pg.execute("INSERT INTO etl.conciliacion (corrida_id, control, inversor_id, valor_origen, valor_destino, cuadra) VALUES (%s,%s,%s,%s,%s,%s)",
                       (corrida, "kWh PV Silver = kWh PV Gold", inv, round(a or 0, 3), round(b or 0, 3), abs((a or 0) - (b or 0)) < 0.5))
        for inv, a, b in pg.execute("""SELECT inversor_id, SUM(pv_kwh_equipo), SUM(pv_kwh_integrado)
                 FROM gold.fact_energia_dia WHERE pv_kwh_equipo IS NOT NULL AND cobertura_dia >= 0.9
                 AND fecha_id BETWEEN %s AND %s GROUP BY 1""",
                 (int(desde.strftime("%Y%m%d")), int(hasta.strftime("%Y%m%d")))).fetchall():
            pg.execute("INSERT INTO etl.conciliacion (corrida_id, control, inversor_id, valor_origen, valor_destino, cuadra) VALUES (%s,%s,%s,%s,%s,%s)",
                       (corrida, "kWh PV equipo vs integrado, dias con cobertura >= 90 % (tolerancia 25 %)", inv, round(a, 3), round(b, 3), abs(b - a) <= 0.25 * a))
        gold_ctx = pg.execute("SELECT COUNT(*) FROM gold.fact_contexto WHERE inicio_ts >= %s AND inicio_ts < %s", (desde, hasta)).fetchone()[0]
        pg.execute("INSERT INTO etl.conciliacion (corrida_id, control, inversor_id, valor_origen, valor_destino, cuadra) VALUES (%s,%s,%s,%s,%s,%s)",
                   (corrida, "anotaciones de contexto Bronze - invalidas = filas en Gold", 0, n_ctx - ctx_inval, gold_ctx, n_ctx == gold_ctx))
        pg.execute("DROP TABLE IF EXISTS silver.lectura_5min_stg, silver.episodio_alarma_stg, silver.energia_dia_equipo_stg, silver.contexto_stg")
        asegurar_roles(pg)
        pg.execute("UPDATE etl.corrida SET fin=now(), estado='ok', detalle=%s WHERE corrida_id=%s",
                   (f"{n_bl} bloques, {n_ep} episodios, {n_ed} dias de equipo", corrida))
        pg.commit()
        log(f"OK corrida {corrida}")
    except Exception as e:
        pg.rollback()
        pg.execute("UPDATE etl.corrida SET fin=now(), estado='error', detalle=%s WHERE corrida_id=%s", (str(e)[:500], corrida))
        pg.commit()
        log(f"ERROR: {e}")
        raise


if __name__ == "__main__":
    sys.exit(main())
