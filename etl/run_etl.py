"""Punto de entrada del ETL de SolarBI.

    python etl/run_etl.py

Lee el CSV de bronze (sin modificarlo ni regenerarlo), lo carga a PostgreSQL con
COPY, ejecuta los SQL de sql/ en orden e imprime el reporte de calidad y los
conteos de cada tabla. Es idempotente: ejecutarlo varias veces deja los mismos
conteos. Toda la corrida es una sola transacción: si algo falla, no queda nada a medias.
La conexión sale de las variables PG* (archivo .env), nunca del código.
"""
import os
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
BRONZE_CSV = RAIZ / "data" / "bronze" / "telemetria.csv"
SILVER_CSV = RAIZ / "data" / "silver" / "lectura_5min.csv"
SQL = RAIZ / "sql"

COLUMNAS = "ts, dispositivo_id, p_ac_kw, irradiancia_wm2, temp_modulo_c"
TABLAS = [
    "bronze.telemetria_cruda",
    "silver.lectura_5min",
    "dwh.dim_fecha",
    "dwh.dim_dispositivo",
    "dwh.fact_energia_dia",
]


def conectar(intentos=10, espera=3):
    """Conecta con las variables PG*; reintenta por si la base aún está arrancando."""
    for n in range(1, intentos + 1):
        try:
            return psycopg.connect(connect_timeout=5)
        except psycopg.OperationalError as e:
            # solo se reintenta si la base aún arranca; un error de credenciales no se arregla esperando
            if n == intentos or "authentication failed" in str(e) or "does not exist" in str(e):
                raise
            print(f"  base de datos no disponible (intento {n}/{intentos}), reintento en {espera} s...")
            time.sleep(espera)


def ejecutar_sql(cur, nombre):
    print(f"  {nombre}")
    cur.execute((SQL / nombre).read_text(encoding="utf-8"))


def cargar_bronze(cur):
    """Reemplaza bronze.telemetria_cruda por el contenido del CSV (la fuente de verdad es el archivo)."""
    print(f"  COPY {BRONZE_CSV.relative_to(RAIZ)} -> bronze.telemetria_cruda")
    cur.execute("TRUNCATE bronze.telemetria_cruda RESTART IDENTITY")
    with open(BRONZE_CSV, "rb") as f, cur.copy(
        f"COPY bronze.telemetria_cruda ({COLUMNAS}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    ) as copy:
        while bloque := f.read(65536):
            copy.write(bloque)


def reporte_calidad(cur):
    cur.execute((SQL / "05_reporte_calidad.sql").read_text(encoding="utf-8"))
    filas = cur.fetchall()
    print("\nREPORTE DE CALIDAD (Silver)")
    print(f"  {'concepto':<32}{'filas':>8}{'%':>9}")
    for _, concepto, n, pct in filas:
        print(f"  {concepto:<32}{n:>8}{pct:>9}")
    leidas = filas[0][2]
    rechazadas = sum(f[2] for f in filas[1:-1])
    validas = filas[-1][2]
    ok = "OK" if leidas == validas + rechazadas else "NO CUADRA"
    print(f"  comprobación: {leidas} = {validas} + {rechazadas}  {ok}")
    return ok == "OK"


def exportar_silver(cur):
    """Devuelve las lecturas limpias como CSV (bytes), ordenadas y con la hora local de Colombia."""
    consulta = (
        "COPY (SELECT to_char(ts AT TIME ZONE 'America/Bogota', 'YYYY-MM-DD HH24:MI:SS') AS ts, "
        "dispositivo_id, p_ac_kw, irradiancia_wm2, temp_modulo_c "
        "FROM silver.lectura_5min ORDER BY ts, dispositivo_id) TO STDOUT WITH (FORMAT csv, HEADER true)"
    )
    with cur.copy(consulta) as copy:
        return b"".join(bytes(bloque) for bloque in copy)


def conteos(cur):
    print("\nCONTEOS (deben ser iguales en cada ejecución)")
    for tabla in TABLAS:
        cur.execute(f"SELECT count(*) FROM {tabla}")
        print(f"  {tabla:<28}{cur.fetchone()[0]:>8}")
    cur.execute("SELECT coalesce(sum(energia_kwh), 0), coalesce(sum(lecturas_validas), 0) FROM dwh.fact_energia_dia")
    energia, validas = cur.fetchone()
    print(f"  suma energia_kwh (fact)     {energia:>8}")
    print(f"  suma lecturas_validas (fact){validas:>8}")


def resumen_diario(cur):
    cur.execute(
        """SELECT f.fecha, d.nombre, e.energia_kwh, e.lecturas_validas, e.pct_datos_validos
           FROM dwh.fact_energia_dia e
           JOIN dwh.dim_fecha f ON f.fecha_key = e.fecha_key
           JOIN dwh.dim_dispositivo d ON d.dispositivo_key = e.dispositivo_key
           ORDER BY f.fecha, d.nombre"""
    )
    print("\nRESUMEN DIARIO (dwh.fact_energia_dia)")
    print(f"  {'fecha':<12}{'dispositivo':<14}{'energia_kwh':>12}{'válidas':>9}{'% válidos':>11}")
    for fecha, nombre, kwh, validas, pct in cur.fetchall():
        print(f"  {fecha!s:<12}{nombre:<14}{kwh:>12}{validas:>9}{pct:>11}")


def main():
    load_dotenv(RAIZ / ".env")
    if not BRONZE_CSV.exists():
        sys.exit(f"No existe {BRONZE_CSV.relative_to(RAIZ)}. Genera el bronze una vez con: python etl/simulador.py")

    print("ETL SolarBI")
    try:
        with conectar() as conn:  # una transacción: commit al salir sin error, rollback si falla
            with conn.cursor() as cur:
                print("1. Esquemas y tablas")
                ejecutar_sql(cur, "01_esquemas.sql")
                ejecutar_sql(cur, "02_bronze.sql")
                print("2. Bronze")
                cargar_bronze(cur)
                print("3. Silver y Gold")
                ejecutar_sql(cur, "03_silver.sql")
                ejecutar_sql(cur, "04_gold.sql")
                cuadra = reporte_calidad(cur)
                conteos(cur)
                resumen_diario(cur)
                silver_csv = exportar_silver(cur)
    except psycopg.Error as e:
        sys.exit(f"\nError de base de datos: {e.__class__.__name__}: {str(e).splitlines()[0]}")
    # el archivo se escribe solo después del commit: si algo falló, no queda un CSV a medias
    SILVER_CSV.parent.mkdir(parents=True, exist_ok=True)
    SILVER_CSV.write_bytes(silver_csv)
    print(f"\nSILVER EXPORTADO: {SILVER_CSV.relative_to(RAIZ)} ({silver_csv.count(b'\n') - 1} filas)")
    print("\nETL terminado." if cuadra else "\nETL terminado con descuadre en el reporte de calidad.")
    return 0 if cuadra else 1


if __name__ == "__main__":
    sys.exit(main())
