-- Gold: dimensiones simples y hecho diario (alimentan el esquema estrella del Entregable III).
CREATE TABLE IF NOT EXISTS dwh.dim_fecha (
    fecha_key  integer PRIMARY KEY,          -- AAAAMMDD
    fecha      date    NOT NULL UNIQUE,
    anio       smallint NOT NULL,
    mes        smallint NOT NULL,
    dia        smallint NOT NULL,
    dia_semana smallint NOT NULL             -- 1 = lunes ... 7 = domingo
);

CREATE TABLE IF NOT EXISTS dwh.dim_dispositivo (
    dispositivo_key serial PRIMARY KEY,
    dispositivo_id  integer NOT NULL UNIQUE, -- id de la fuente
    nombre          text    NOT NULL,
    capacidad_kwp   numeric(6,2),
    sitio           text
);

CREATE TABLE IF NOT EXISTS dwh.fact_energia_dia (
    fecha_key           integer NOT NULL REFERENCES dwh.dim_fecha (fecha_key),
    dispositivo_key     integer NOT NULL REFERENCES dwh.dim_dispositivo (dispositivo_key),
    energia_kwh         numeric(10,3) NOT NULL,
    lecturas_validas    integer       NOT NULL,
    lecturas_esperadas  integer       NOT NULL,   -- 288 por día (24 h / 5 min)
    pct_datos_validos   numeric(5,2)  NOT NULL,
    PRIMARY KEY (fecha_key, dispositivo_key)
);

INSERT INTO dwh.dim_fecha (fecha_key, fecha, anio, mes, dia, dia_semana)
SELECT to_char(d, 'YYYYMMDD')::integer, d::date,
       extract(year FROM d), extract(month FROM d), extract(day FROM d),
       extract(isodow FROM d)
FROM generate_series(
         (SELECT min((ts AT TIME ZONE 'America/Bogota')::date) FROM silver.lectura_5min)::timestamp,
         (SELECT max((ts AT TIME ZONE 'America/Bogota')::date) FROM silver.lectura_5min)::timestamp,
         interval '1 day') AS d
ON CONFLICT (fecha_key) DO NOTHING;

INSERT INTO dwh.dim_dispositivo (dispositivo_id, nombre, capacidad_kwp, sitio)
SELECT DISTINCT l.dispositivo_id,
       'Inversor ' || lpad(l.dispositivo_id::text, 2, '0'),
       CASE WHEN l.dispositivo_id = 1 THEN 5.0 END,   -- capacidad conocida solo del inversor 1
       'Pascual Bravo'
FROM silver.lectura_5min l
ON CONFLICT (dispositivo_id) DO NOTHING;

-- Hecho diario. Energía por intervalo = potencia (kW) x 5/60 h. El día es el día
-- local de Colombia. pct_datos_validos = lecturas válidas / 288 esperadas, máximo 100.
INSERT INTO dwh.fact_energia_dia
    (fecha_key, dispositivo_key, energia_kwh, lecturas_validas, lecturas_esperadas, pct_datos_validos)
SELECT to_char((l.ts AT TIME ZONE 'America/Bogota')::date, 'YYYYMMDD')::integer,
       d.dispositivo_key,
       round(sum(l.p_ac_kw * 5.0 / 60), 3),
       count(*),
       288,
       least(100, round(100.0 * count(*) / 288, 2))
FROM silver.lectura_5min l
JOIN dwh.dim_dispositivo d ON d.dispositivo_id = l.dispositivo_id
GROUP BY 1, 2
ON CONFLICT (fecha_key, dispositivo_key) DO UPDATE
SET energia_kwh        = EXCLUDED.energia_kwh,
    lecturas_validas   = EXCLUDED.lecturas_validas,
    lecturas_esperadas = EXCLUDED.lecturas_esperadas,
    pct_datos_validos  = EXCLUDED.pct_datos_validos;
