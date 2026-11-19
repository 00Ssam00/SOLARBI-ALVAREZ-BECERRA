-- Gold: modelo dimensional con tres procesos de negocio.
--   P1 Operación (lecturas cada 5 min)  -> gold.fact_lectura_5min
--   P2 Balance energético diario        -> gold.fact_energia_dia
--   P3 Eventos de alarma                -> gold.fact_evento_alarma

CREATE TABLE IF NOT EXISTS gold.dim_fecha (
    fecha_id      INTEGER PRIMARY KEY,         -- yyyymmdd (hora local Asia/Shanghai)
    fecha         DATE NOT NULL UNIQUE,
    anio          SMALLINT NOT NULL,
    trimestre     SMALLINT NOT NULL,
    mes           SMALLINT NOT NULL,
    nombre_mes    TEXT NOT NULL,
    dia_mes       SMALLINT NOT NULL,
    dia_semana    SMALLINT NOT NULL,           -- 1 = lunes
    nombre_dia    TEXT NOT NULL,
    semana_iso    SMALLINT NOT NULL,
    es_fin_semana BOOLEAN NOT NULL,
    estacion      TEXT NOT NULL                -- hemisferio norte (Shenzhen)
);
INSERT INTO gold.dim_fecha
SELECT to_char(d,'YYYYMMDD')::int, d::date,
       extract(year from d), extract(quarter from d), extract(month from d),
       (ARRAY['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'])[extract(month from d)::int],
       extract(day from d), extract(isodow from d),
       (ARRAY['lunes','martes','miércoles','jueves','viernes','sábado','domingo'])[extract(isodow from d)::int],
       extract(week from d), extract(isodow from d) >= 6,
       CASE WHEN extract(month from d) IN (12,1,2) THEN 'invierno'
            WHEN extract(month from d) IN (3,4,5)  THEN 'primavera'
            WHEN extract(month from d) IN (6,7,8)  THEN 'verano' ELSE 'otoño' END
FROM generate_series('2025-07-01'::date, '2026-07-31'::date, '1 day') AS d
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS gold.dim_hora (
    hora_id       SMALLINT PRIMARY KEY,        -- 0..23, hora local
    franja        TEXT NOT NULL,
    es_hora_solar BOOLEAN NOT NULL
);
INSERT INTO gold.dim_hora
SELECT h, CASE WHEN h < 6 THEN 'madrugada' WHEN h < 12 THEN 'mañana' WHEN h < 18 THEN 'tarde' ELSE 'noche' END,
       h BETWEEN 6 AND 17
FROM generate_series(0,23) AS h
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS gold.dim_inversor (
    inversor_id   SMALLINT PRIMARY KEY,
    nombre        TEXT NOT NULL,
    primera_lectura TIMESTAMPTZ,
    ultima_lectura  TIMESTAMPTZ,
    activo_al_cierre BOOLEAN
);

-- Dimensión propia 1: estado operativo (combinación de startup/out/chg).
-- Las etiquetas son SUPUESTOS: el diccionario de OpenCEM no documenta los códigos.
CREATE TABLE IF NOT EXISTS gold.dim_estado_operativo (
    estado_id     SMALLINT PRIMARY KEY,
    startupstatus SMALLINT,
    outstatus     SMALLINT,
    chgstatus     SMALLINT,
    categoria     TEXT NOT NULL,
    descripcion   TEXT NOT NULL,
    UNIQUE NULLS NOT DISTINCT (startupstatus, outstatus, chgstatus)
);

-- Dimensión propia 2: alarma (firma de 8 palabras del inversor).
CREATE TABLE IF NOT EXISTS gold.dim_alarma (
    alarma_id     SMALLINT PRIMARY KEY,
    firma         JSONB UNIQUE,
    palabra       SMALLINT,                    -- índice de la primera palabra distinta de 0
    valor         INTEGER,
    bits_activos  INTEGER[],
    severidad     TEXT NOT NULL,               -- supuesto, ver diccionario
    descripcion   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.fact_lectura_5min (
    inversor_id   SMALLINT    NOT NULL REFERENCES gold.dim_inversor,
    bloque_ts     TIMESTAMPTZ NOT NULL,
    fecha_id      INTEGER     NOT NULL REFERENCES gold.dim_fecha,
    hora_id       SMALLINT    NOT NULL REFERENCES gold.dim_hora,
    estado_id     SMALLINT    REFERENCES gold.dim_estado_operativo,
    alarma_id     SMALLINT    REFERENCES gold.dim_alarma,
    n_lecturas    INTEGER     NOT NULL,
    cobertura     REAL        NOT NULL,        -- 0..1, segundos cubiertos / 300
    pv_w_prom     REAL, pv_w_max REAL,
    carga_w_prom  REAL, red_w_prom REAL, inyec_w_prom REAL, bat_w_prom REAL,
    soc_prom      REAL, soc_min REAL,
    bat_v_prom    REAL, bat_a_prom REAL, temp_max_c REAL,
    e_pv_wh       REAL, e_carga_wh REAL, e_red_wh REAL,
    n_alarmas     INTEGER     NOT NULL,
    PRIMARY KEY (inversor_id, bloque_ts)
);
CREATE INDEX IF NOT EXISTS ix_fl5_fecha ON gold.fact_lectura_5min (fecha_id);
CREATE INDEX IF NOT EXISTS ix_fl5_ts ON gold.fact_lectura_5min (bloque_ts);

CREATE TABLE IF NOT EXISTS gold.fact_energia_dia (
    inversor_id   SMALLINT NOT NULL REFERENCES gold.dim_inversor,
    fecha_id      INTEGER  NOT NULL REFERENCES gold.dim_fecha,
    pv_kwh_integrado   REAL,
    pv_kwh_equipo      REAL,
    pv_dif_pct         REAL,                   -- (integrado - equipo) / equipo
    consumo_kwh_integrado REAL,
    consumo_kwh_equipo REAL,
    red_kwh_integrado  REAL,
    carga_bat_kwh_equipo REAL,
    descarga_bat_kwh_equipo REAL,
    horas_con_dato     REAL,
    cobertura_dia      REAL,                   -- 0..1
    PRIMARY KEY (inversor_id, fecha_id)
);

CREATE TABLE IF NOT EXISTS gold.fact_evento_alarma (
    inversor_id   SMALLINT    NOT NULL REFERENCES gold.dim_inversor,
    inicio_ts     TIMESTAMPTZ NOT NULL,
    fin_ts        TIMESTAMPTZ NOT NULL,
    fecha_id      INTEGER     NOT NULL REFERENCES gold.dim_fecha,
    hora_id       SMALLINT    NOT NULL REFERENCES gold.dim_hora,
    alarma_id     SMALLINT    NOT NULL REFERENCES gold.dim_alarma,
    duracion_s    DOUBLE PRECISION NOT NULL,
    n_lecturas    INTEGER     NOT NULL,
    PRIMARY KEY (inversor_id, inicio_ts)
);

-- Tiempo real (lo escribe el simulador dentro del clúster).
CREATE TABLE IF NOT EXISTS rt.lectura (
    ts            TIMESTAMPTZ NOT NULL,
    inversor_id   SMALLINT    NOT NULL,
    pv_w          REAL, carga_w REAL, red_w REAL,
    soc           REAL, bat_v REAL, temp_c REAL,
    alarma        BOOLEAN NOT NULL DEFAULT false,
    origen        TEXT NOT NULL DEFAULT 'simulador',
    PRIMARY KEY (inversor_id, ts)
);
CREATE INDEX IF NOT EXISTS ix_rt_ts ON rt.lectura (ts DESC);

-- Dimensión propia 3: tipo de contexto (fuente + tipo de anotación + categoría de negocio).
CREATE TABLE IF NOT EXISTS gold.dim_tipo_contexto (
    tipo_contexto_id SMALLINT PRIMARY KEY,
    fuente           TEXT NOT NULL,
    context_type     TEXT NOT NULL,
    categoria        TEXT NOT NULL,
    UNIQUE (fuente, context_type)
);

-- P4 Contexto operativo: una fila por anotación (grano: una anotación del registro de contexto).
CREATE TABLE IF NOT EXISTS gold.fact_contexto (
    contexto_id      INTEGER PRIMARY KEY,
    tipo_contexto_id SMALLINT NOT NULL REFERENCES gold.dim_tipo_contexto,
    inversor_id      SMALLINT REFERENCES gold.dim_inversor,   -- nulo si la anotación no es de un inversor
    fecha_id         INTEGER  NOT NULL REFERENCES gold.dim_fecha,
    hora_id          SMALLINT NOT NULL REFERENCES gold.dim_hora,
    inicio_ts        TIMESTAMPTZ NOT NULL,
    fin_ts           TIMESTAMPTZ NOT NULL,
    duracion_s       DOUBLE PRECISION NOT NULL,
    cpu_cores        SMALLINT,
    esfuerzo         TEXT
);
CREATE INDEX IF NOT EXISTS ix_fcontexto_ts ON gold.fact_contexto (inicio_ts, fin_ts);
CREATE INDEX IF NOT EXISTS ix_fcontexto_tipo ON gold.fact_contexto (tipo_contexto_id);
