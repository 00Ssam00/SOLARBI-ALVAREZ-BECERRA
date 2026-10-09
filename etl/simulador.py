"""Simulador de telemetría SolarBI: capa Bronze.

Genera 3 días de lecturas cada 5 minutos de un inversor de 5 kWp en
data/bronze/telemetria.csv. Se ejecuta una sola vez y aparte del ETL:
run_etl.py solo lee el archivo, nunca lo regenera ni lo modifica.
"""
import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)  # misma secuencia en cada corrida: el bronze es reproducible

RUTA = Path(__file__).resolve().parent.parent / "data" / "bronze" / "telemetria.csv"
INICIO = datetime(2026, 10, 1, 0, 0)  # hora local de Colombia, sin zona (naive)

# Falla inyectada: el inversor se apaga una hora a pleno sol (potencia 0 con
# irradiancia alta). Es un valor físicamente válido: Silver no lo rechaza y la
# alerta de Grafana (potencia 0 entre 9:00 y 15:00) tiene algo que detectar.
FALLA_INICIO = datetime(2026, 10, 2, 11, 0)
FALLA_FIN = datetime(2026, 10, 2, 12, 0)

RUTA.parent.mkdir(parents=True, exist_ok=True)

with open(RUTA, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["ts", "dispositivo_id", "p_ac_kw", "irradiancia_wm2", "temp_modulo_c"])
    for i in range(3 * 288):                          # 3 días, cada 5 min
        ts = INICIO + timedelta(minutes=5 * i)
        sol = max(0.0, math.sin(math.pi * (ts.hour + ts.minute / 60 - 6) / 12))
        irr = round(1000 * sol * random.uniform(0.7, 1.0), 1)
        p_ac = round(5.0 * irr / 1000 * random.uniform(0.80, 0.90), 3)
        fila = [ts.isoformat(sep=" "), 1, p_ac, irr, round(22 + 30 * sol, 1)]
        r = random.random()                           # se sortea siempre, para no alterar la secuencia
        if FALLA_INICIO <= ts < FALLA_FIN:
            fila[2] = 0.0                             # falla: potencia 0 con sol, sin otras anomalías
            w.writerow(fila)
            continue
        if r < 0.02:
            fila[2] = -1                              # anomalía: potencia negativa
        elif r < 0.04:
            fila[3] = ""                              # anomalía: dato faltante
        w.writerow(fila)
        if r > 0.98:
            w.writerow(fila)                          # anomalía: fila duplicada
