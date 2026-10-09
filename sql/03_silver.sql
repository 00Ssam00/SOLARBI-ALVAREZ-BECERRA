-- Silver: lecturas limpias de 5 minutos.
CREATE TABLE IF NOT EXISTS silver.lectura_5min (
    ts              timestamptz   NOT NULL,
    dispositivo_id  integer       NOT NULL,
    p_ac_kw         numeric(8,3)  NOT NULL CHECK (p_ac_kw >= 0),
    irradiancia_wm2 numeric(8,1)  NOT NULL,
    temp_modulo_c   numeric(5,1),
    PRIMARY KEY (ts, dispositivo_id)
);

-- Clasifica cada fila de bronze en una sola regla, con este orden de prioridad:
--   1. duplicado       misma (ts, dispositivo_id) que otra fila anterior
--   2. faltante        potencia o irradiancia vacía (también temperatura)
--   3. formato         valor que no es un número, o fecha o id mal escritos
--   4. fuera_de_rango  potencia negativa
-- Así cada fila rechazada cuenta en una sola regla y leídas = válidas + rechazadas.
CREATE OR REPLACE VIEW silver.v_calidad_filas AS
WITH numerada AS (
    SELECT b.*,
           row_number() OVER (PARTITION BY ts, dispositivo_id ORDER BY fila) AS rn
    FROM bronze.telemetria_cruda b
)
SELECT fila, ts, dispositivo_id, p_ac_kw, irradiancia_wm2, temp_modulo_c,
       CASE
           WHEN rn > 1 THEN 'duplicado'
           WHEN nullif(btrim(p_ac_kw), '') IS NULL
             OR nullif(btrim(irradiancia_wm2), '') IS NULL
             OR nullif(btrim(temp_modulo_c), '') IS NULL THEN 'faltante'
           WHEN ts !~ '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$'
             OR dispositivo_id !~ '^\d+$'
             OR p_ac_kw !~ '^-?\d+(\.\d+)?$'
             OR irradiancia_wm2 !~ '^-?\d+(\.\d+)?$'
             OR temp_modulo_c !~ '^-?\d+(\.\d+)?$' THEN 'formato'
           WHEN p_ac_kw::numeric < 0 THEN 'fuera_de_rango'
           ELSE 'valida'
       END AS resultado
FROM numerada;

-- Carga idempotente: la clave primaria evita duplicados en reejecuciones.
-- Los timestamps naive del bronze son hora de Colombia.
INSERT INTO silver.lectura_5min (ts, dispositivo_id, p_ac_kw, irradiancia_wm2, temp_modulo_c)
SELECT (ts::timestamp AT TIME ZONE 'America/Bogota'),
       dispositivo_id::integer,
       p_ac_kw::numeric,
       irradiancia_wm2::numeric,
       temp_modulo_c::numeric
FROM silver.v_calidad_filas
WHERE resultado = 'valida'
ON CONFLICT (ts, dispositivo_id) DO UPDATE
SET p_ac_kw         = EXCLUDED.p_ac_kw,
    irradiancia_wm2 = EXCLUDED.irradiancia_wm2,
    temp_modulo_c   = EXCLUDED.temp_modulo_c;
