-- Carga de Gold desde Silver. Idempotente (ON CONFLICT DO UPDATE).

INSERT INTO gold.dim_inversor (inversor_id, nombre, primera_lectura, ultima_lectura, activo_al_cierre)
SELECT inversor_id, 'Inversor ' || inversor_id, MIN(bloque_ts), MAX(bloque_ts),
       MAX(bloque_ts) >= (SELECT MAX(bloque_ts) FROM silver.lectura_5min) - interval '1 day'
FROM silver.lectura_5min GROUP BY 1
ON CONFLICT (inversor_id) DO UPDATE SET
  primera_lectura = LEAST(gold.dim_inversor.primera_lectura, EXCLUDED.primera_lectura),
  ultima_lectura  = GREATEST(gold.dim_inversor.ultima_lectura, EXCLUDED.ultima_lectura),
  activo_al_cierre = EXCLUDED.activo_al_cierre;

-- Estado operativo: el id codifica (startup, out, chg); 9 = dato ausente.
INSERT INTO gold.dim_estado_operativo (estado_id, startupstatus, outstatus, chgstatus, categoria, descripcion)
SELECT COALESCE(startupstatus,9)*100 + COALESCE(outstatus,9)*10 + COALESCE(chgstatus,9),
       startupstatus, outstatus, chgstatus,
       CASE WHEN outstatus IS NULL THEN 'sin dato'
            ELSE CASE outstatus WHEN 0 THEN 'sin salida' WHEN 1 THEN 'salida nivel 1' WHEN 2 THEN 'salida nivel 2' ELSE 'salida desconocida' END
                 || CASE WHEN chgstatus = 1 THEN ' con carga' ELSE '' END END,
       'arranque=' || COALESCE(startupstatus::text,'?') || ', salida=' || COALESCE(outstatus::text,'?') || ', carga=' || COALESCE(chgstatus::text,'?')
FROM (SELECT DISTINCT startupstatus, outstatus, chgstatus FROM silver.lectura_5min) x
ON CONFLICT DO NOTHING;

INSERT INTO gold.dim_alarma (alarma_id, firma, palabra, valor, bits_activos, severidad, descripcion)
VALUES (0, NULL, NULL, 0, '{}', 'ninguna', 'Sin alarma') ON CONFLICT DO NOTHING;

WITH firmas AS (
  SELECT DISTINCT firma FROM silver.episodio_alarma
  UNION
  SELECT DISTINCT alarma_firma::jsonb FROM silver.lectura_5min WHERE alarma_firma IS NOT NULL
), palabras AS (
  SELECT f.firma, (e.ord - 1)::int AS idx, e.val::int AS val
  FROM firmas f, jsonb_array_elements_text(f.firma) WITH ORDINALITY AS e(val, ord)
  WHERE e.val ~ '^[0-9]+$' AND e.val::int <> 0
), resumen AS (
  SELECT p.firma, MIN(p.idx) AS palabra, MAX(p.val) AS valor,
         ARRAY(SELECT p2.idx * 16 + b FROM palabras p2, generate_series(0,15) b
               WHERE p2.firma = p.firma AND ((p2.val >> b) & 1) = 1 ORDER BY 1) AS bits
  FROM palabras p GROUP BY p.firma
)
INSERT INTO gold.dim_alarma (alarma_id, firma, palabra, valor, bits_activos, severidad, descripcion)
SELECT (abs(hashtext(firma::text)) % 30000) + 1, firma, palabra, valor, bits, 'aviso',
       'Alarma no documentada por OpenCEM; bits globales ' || array_to_string(bits, ',')
FROM resumen
ON CONFLICT DO NOTHING;

INSERT INTO gold.fact_lectura_5min
SELECT s.inversor_id, s.bloque_ts,
       to_char(s.bloque_ts AT TIME ZONE 'Asia/Shanghai', 'YYYYMMDD')::int,
       extract(hour FROM s.bloque_ts AT TIME ZONE 'Asia/Shanghai')::smallint,
       COALESCE(s.startupstatus,9)*100 + COALESCE(s.outstatus,9)*10 + COALESCE(s.chgstatus,9),
       COALESCE(a.alarma_id, 0), s.n_lecturas, LEAST(1.0, s.segundos_cubiertos / 300.0),
       s.pv_w_prom, s.pv_w_max, s.carga_w_prom, s.red_w_prom, s.inyec_w_prom, s.bat_w_prom,
       s.soc_prom, s.soc_min, s.bat_v_prom, s.bat_a_prom, s.temp_max_c,
       s.e_pv_wh, s.e_carga_wh, s.e_red_wh, s.n_alarmas
FROM silver.lectura_5min s
LEFT JOIN gold.dim_alarma a ON a.firma = s.alarma_firma::jsonb
ON CONFLICT (inversor_id, bloque_ts) DO UPDATE SET
  estado_id=EXCLUDED.estado_id, alarma_id=EXCLUDED.alarma_id, n_lecturas=EXCLUDED.n_lecturas,
  cobertura=EXCLUDED.cobertura, pv_w_prom=EXCLUDED.pv_w_prom, pv_w_max=EXCLUDED.pv_w_max,
  carga_w_prom=EXCLUDED.carga_w_prom, red_w_prom=EXCLUDED.red_w_prom, inyec_w_prom=EXCLUDED.inyec_w_prom,
  bat_w_prom=EXCLUDED.bat_w_prom, soc_prom=EXCLUDED.soc_prom, soc_min=EXCLUDED.soc_min,
  bat_v_prom=EXCLUDED.bat_v_prom, bat_a_prom=EXCLUDED.bat_a_prom, temp_max_c=EXCLUDED.temp_max_c,
  e_pv_wh=EXCLUDED.e_pv_wh, e_carga_wh=EXCLUDED.e_carga_wh, e_red_wh=EXCLUDED.e_red_wh,
  n_alarmas=EXCLUDED.n_alarmas;

WITH d AS (
  SELECT inversor_id, to_char(bloque_ts AT TIME ZONE 'Asia/Shanghai', 'YYYYMMDD')::int AS fecha_id,
         SUM(e_pv_wh)/1000.0 AS pv, SUM(e_carga_wh)/1000.0 AS carga, SUM(e_red_wh)/1000.0 AS red,
         SUM(segundos_cubiertos)/3600.0 AS horas
  FROM silver.lectura_5min GROUP BY 1, 2
)
INSERT INTO gold.fact_energia_dia
SELECT d.inversor_id, d.fecha_id, d.pv, e.pv_kwh,
       CASE WHEN e.pv_kwh > 0 THEN (d.pv - e.pv_kwh) / e.pv_kwh END,
       d.carga, e.consumo_kwh, d.red, e.carga_bat_kwh, e.descarga_bat_kwh,
       d.horas, LEAST(1.0, d.horas / 24.0)
FROM d LEFT JOIN silver.energia_dia_equipo e
  ON e.inversor_id = d.inversor_id AND to_char(e.fecha_local, 'YYYYMMDD')::int = d.fecha_id
ON CONFLICT (inversor_id, fecha_id) DO UPDATE SET
  pv_kwh_integrado=EXCLUDED.pv_kwh_integrado, pv_kwh_equipo=EXCLUDED.pv_kwh_equipo,
  pv_dif_pct=EXCLUDED.pv_dif_pct, consumo_kwh_integrado=EXCLUDED.consumo_kwh_integrado,
  consumo_kwh_equipo=EXCLUDED.consumo_kwh_equipo, red_kwh_integrado=EXCLUDED.red_kwh_integrado,
  carga_bat_kwh_equipo=EXCLUDED.carga_bat_kwh_equipo, descarga_bat_kwh_equipo=EXCLUDED.descarga_bat_kwh_equipo,
  horas_con_dato=EXCLUDED.horas_con_dato, cobertura_dia=EXCLUDED.cobertura_dia;

INSERT INTO gold.fact_evento_alarma
SELECT e.inversor_id, e.inicio_ts, e.fin_ts,
       to_char(e.inicio_ts AT TIME ZONE 'Asia/Shanghai', 'YYYYMMDD')::int,
       extract(hour FROM e.inicio_ts AT TIME ZONE 'Asia/Shanghai')::smallint,
       a.alarma_id, extract(epoch FROM e.fin_ts - e.inicio_ts), e.n_lecturas
FROM silver.episodio_alarma e JOIN gold.dim_alarma a ON a.firma = e.firma
ON CONFLICT (inversor_id, inicio_ts) DO UPDATE SET
  fin_ts=EXCLUDED.fin_ts, alarma_id=EXCLUDED.alarma_id,
  duracion_s=EXCLUDED.duracion_s, n_lecturas=EXCLUDED.n_lecturas;

INSERT INTO gold.dim_tipo_contexto (tipo_contexto_id, fuente, context_type, categoria)
SELECT (abs(hashtext(fuente || '|' || tipo)) % 30000) + 1, fuente, tipo,
       CASE WHEN fuente LIKE 'workstation%' OR fuente = 'wsl_bash_history' OR fuente = 'manual_workload_entry' THEN 'carga de cómputo'
            WHEN fuente = 'windows_event_log' THEN 'evento de sistema'
            WHEN fuente = 'derived_context_pipeline' THEN 'contexto derivado'
            ELSE 'calendario y notas manuales' END
FROM (SELECT DISTINCT valor->>'source' AS fuente, COALESCE(valor->>'context_type', 'sin_tipo') AS tipo FROM silver.contexto) x
ON CONFLICT DO NOTHING;

INSERT INTO gold.fact_contexto
SELECT c.contexto_id, t.tipo_contexto_id,
       CASE WHEN (c.valor->>'inverter') ~ '^[12]$' THEN (c.valor->>'inverter')::smallint END,
       to_char(c.inicio_ts AT TIME ZONE 'Asia/Shanghai', 'YYYYMMDD')::int,
       extract(hour FROM c.inicio_ts AT TIME ZONE 'Asia/Shanghai')::smallint,
       c.inicio_ts, c.fin_ts, extract(epoch FROM c.fin_ts - c.inicio_ts),
       CASE WHEN (c.valor->>'cpu_cores_active') ~ '^[0-9]+$' THEN (c.valor->>'cpu_cores_active')::smallint END,
       c.valor->>'llm_estimated_task_effort'
FROM silver.contexto c
JOIN gold.dim_tipo_contexto t ON t.fuente = c.valor->>'source' AND t.context_type = COALESCE(c.valor->>'context_type', 'sin_tipo')
WHERE to_char(c.inicio_ts AT TIME ZONE 'Asia/Shanghai', 'YYYYMMDD')::int IN (SELECT fecha_id FROM gold.dim_fecha)
  AND ((c.valor->>'inverter') IS NULL OR (c.valor->>'inverter') !~ '^[12]$'
       OR (c.valor->>'inverter')::smallint IN (SELECT inversor_id FROM gold.dim_inversor))
ON CONFLICT (contexto_id) DO UPDATE SET
  tipo_contexto_id=EXCLUDED.tipo_contexto_id, inversor_id=EXCLUDED.inversor_id, fecha_id=EXCLUDED.fecha_id,
  hora_id=EXCLUDED.hora_id, inicio_ts=EXCLUDED.inicio_ts, fin_ts=EXCLUDED.fin_ts,
  duracion_s=EXCLUDED.duracion_s, cpu_cores=EXCLUDED.cpu_cores, esfuerzo=EXCLUDED.esfuerzo;
