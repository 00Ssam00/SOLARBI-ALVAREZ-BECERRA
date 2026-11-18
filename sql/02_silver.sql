-- Silver: lecturas validadas y agregadas a bloques de 5 minutos (UTC).
CREATE TABLE IF NOT EXISTS silver.lectura_5min (
    inversor_id     SMALLINT    NOT NULL,
    bloque_ts       TIMESTAMPTZ NOT NULL,
    n_lecturas      INTEGER     NOT NULL,
    pv_w_prom       REAL,
    pv_w_max        REAL,
    carga_w_prom    REAL,
    red_w_prom      REAL,        -- potencia tomada de la red (linepowerw_a)
    inyec_w_prom    REAL,        -- potencia hacia la red (gridpowerw_a)
    bat_w_prom      REAL,        -- battchgpower
    soc_prom        REAL,
    soc_min         REAL,
    bat_v_prom      REAL,
    bat_a_prom      REAL,        -- positivo = descarga
    temp_max_c      REAL,
    e_pv_wh         REAL,        -- energía integrada en el bloque
    e_carga_wh      REAL,
    e_red_wh        REAL,
    segundos_cubiertos REAL     NOT NULL,
    startupstatus   SMALLINT,
    outstatus       SMALLINT,
    chgstatus       SMALLINT,
    n_alarmas       INTEGER     NOT NULL DEFAULT 0,
    alarma_firma    TEXT,        -- firma de alarma más alta del bloque (JSON como texto)
    PRIMARY KEY (inversor_id, bloque_ts)
);

CREATE TABLE IF NOT EXISTS silver.energia_dia_equipo (
    inversor_id     SMALLINT NOT NULL,
    fecha_local     DATE     NOT NULL,   -- Asia/Shanghai
    pv_kwh          REAL,
    carga_bat_kwh   REAL,
    descarga_bat_kwh REAL,
    consumo_kwh     REAL,
    n_lecturas      INTEGER NOT NULL,
    PRIMARY KEY (inversor_id, fecha_local)
);

CREATE TABLE IF NOT EXISTS silver.episodio_alarma (
    inversor_id     SMALLINT    NOT NULL,
    inicio_ts       TIMESTAMPTZ NOT NULL,
    fin_ts          TIMESTAMPTZ NOT NULL,
    firma           JSONB       NOT NULL,   -- arreglo de 8 palabras de sysalarmflag
    n_lecturas      INTEGER     NOT NULL,
    PRIMARY KEY (inversor_id, inicio_ts)
);

-- Contexto (JSON de anotaciones). Se carga MINIMIZADO: solo claves de una lista blanca.
-- Se omiten comandos, rutas, descripciones libres y metadatos (Ley 1581 de 2012, principio de finalidad y minimización).
CREATE TABLE IF NOT EXISTS silver.contexto (
    contexto_id     INTEGER     PRIMARY KEY,   -- context.id del Bronze
    registrado_ts   TIMESTAMPTZ,
    inicio_ts       TIMESTAMPTZ NOT NULL,
    fin_ts          TIMESTAMPTZ NOT NULL,
    valor           JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_contexto_valor ON silver.contexto USING gin (valor jsonb_path_ops);
CREATE INDEX IF NOT EXISTS ix_contexto_inicio ON silver.contexto (inicio_ts);
