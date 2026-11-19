-- SolarBI Taller 6: esquemas y tablas de control del ETL.
-- Capas: Bronze = SQLite original (solo lectura, fuera de PostgreSQL)
--        silver = datos validados y agregados a 5 minutos
--        gold   = modelo dimensional (hechos y dimensiones)
--        etl    = control: corridas, conteos por regla, conciliación
--        rt     = tiempo real: lo escribe el simulador y lo lee Grafana
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS rt;

CREATE TABLE IF NOT EXISTS etl.corrida (
    corrida_id   BIGSERIAL PRIMARY KEY,
    inicio       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fin          TIMESTAMPTZ,
    desde_utc    TIMESTAMPTZ NOT NULL,
    hasta_utc    TIMESTAMPTZ NOT NULL,
    estado       TEXT NOT NULL DEFAULT 'en_curso' CHECK (estado IN ('en_curso','ok','error')),
    detalle      TEXT
);

-- Conteo por regla de calidad de la última corrida de cada ventana.
CREATE TABLE IF NOT EXISTS etl.regla_calidad (
    corrida_id   BIGINT NOT NULL REFERENCES etl.corrida(corrida_id) ON DELETE CASCADE,
    regla        TEXT   NOT NULL,
    tabla_origen TEXT   NOT NULL,
    inversor_id  SMALLINT NOT NULL,
    filas_afectadas BIGINT NOT NULL,
    accion       TEXT   NOT NULL,
    descripcion  TEXT   NOT NULL,
    PRIMARY KEY (corrida_id, regla, inversor_id)
);

-- Conciliación: lo que entró del Bronze contra lo que quedó en Silver/Gold.
CREATE TABLE IF NOT EXISTS etl.conciliacion (
    corrida_id   BIGINT NOT NULL REFERENCES etl.corrida(corrida_id) ON DELETE CASCADE,
    control      TEXT   NOT NULL,
    inversor_id  SMALLINT NOT NULL,
    valor_origen NUMERIC NOT NULL,
    valor_destino NUMERIC NOT NULL,
    diferencia   NUMERIC GENERATED ALWAYS AS (valor_destino - valor_origen) STORED,
    cuadra       BOOLEAN NOT NULL,
    PRIMARY KEY (corrida_id, control, inversor_id)
);
