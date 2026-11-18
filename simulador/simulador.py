"""Simulador de streaming: cada ejecución (CronJob, 1 por minuto) inserta las lecturas del
último minuto en rt.lectura, una cada 12 s por inversor, siguiendo el perfil horario real
(promedio por hora local de gold.fact_lectura_5min) más ruido.

SIM_ESCENARIO: normal | falla | bateria_baja   (para provocar las alertas en vivo)
"""
import datetime as dt
import math
import os
import random

import psycopg

PASO_S = 12
CAPACIDAD_WH = 10000.0
INVERSORES = (1, 2)
ESCENARIO = os.environ.get("SIM_ESCENARIO", "normal")


def conectar():
    return psycopg.connect(
        host=os.environ.get("PGHOST", "postgres"), dbname=os.environ.get("PGDATABASE", "solarbi"),
        user=os.environ.get("PGUSER", "simulador_rw"), password=os.environ.get("PGPASSWORD", ""))


def perfil(pg, inv, hora):
    r = pg.execute("""SELECT AVG(pv_w_prom), AVG(carga_w_prom), AVG(red_w_prom), AVG(soc_prom),
                             AVG(bat_v_prom), AVG(temp_max_c)
                      FROM gold.fact_lectura_5min WHERE inversor_id = %s AND hora_id = %s""", (inv, hora)).fetchone()
    if r and r[0] is not None:
        return [float(x) if x is not None else 0.0 for x in r]
    sol = max(0.0, math.sin(math.pi * (hora - 6) / 12)) if 6 <= hora <= 18 else 0.0
    return [1500 * sol, 400.0, 100.0, 70.0, 53.0, 30.0]


def main():
    ahora = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    with conectar() as pg:
        hora_local = (ahora + dt.timedelta(hours=8)).hour
        for inv in INVERSORES:
            pv_p, carga_p, red_p, soc_p, volt_p, temp_p = perfil(pg, inv, hora_local)
            ult = pg.execute("SELECT soc FROM rt.lectura WHERE inversor_id=%s ORDER BY ts DESC LIMIT 1", (inv,)).fetchone()
            soc = float(ult[0]) if ult and ult[0] is not None else soc_p
            for k in range(5, -1, -1):
                ts = ahora - dt.timedelta(seconds=k * PASO_S)
                pv = max(0.0, random.gauss(pv_p, 0.08 * pv_p + 5))
                carga = max(0.0, random.gauss(carga_p, 0.1 * carga_p + 10))
                red = max(0.0, random.gauss(red_p, 0.1 * red_p + 5))
                alarma = False
                if ESCENARIO == "bateria_baja":
                    pv, carga = 0.0, max(carga, 1500.0)
                    red = 0.0
                elif ESCENARIO == "falla" and inv == 2:
                    alarma = True
                soc = min(100.0, max(0.0, soc + (pv + red - carga) * PASO_S / 3600.0 / CAPACIDAD_WH * 100.0))
                if ESCENARIO == "bateria_baja":
                    soc = min(soc, max(5.0, soc - 0.4))
                pg.execute("""INSERT INTO rt.lectura (ts, inversor_id, pv_w, carga_w, red_w, soc, bat_v, temp_c, alarma)
                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (inversor_id, ts) DO NOTHING""",
                           (ts, inv, round(pv), round(carga), round(red), round(soc, 1),
                            round(random.gauss(volt_p, 0.1), 2), round(random.gauss(temp_p, 0.3), 1), alarma))
        pg.execute("DELETE FROM rt.lectura WHERE ts < now() - interval '24 hours'")
    print(f"[simulador] {ahora:%H:%M:%S}Z escenario={ESCENARIO}: 12 lecturas insertadas", flush=True)


if __name__ == "__main__":
    main()
