-- Consultas sobre campos JSON con operadores nativos de PostgreSQL (jsonb).
-- El campo vive en silver.contexto.valor (anotaciones) y en gold.dim_alarma.firma (alarmas).

-- Q1. Qué tipos de anotación hay y cuánto duran. Operadores ->> y COALESCE.
SELECT valor->>'source'                         AS fuente,
       COALESCE(valor->>'context_type','sin_tipo') AS tipo,
       COUNT(*)                                 AS anotaciones,
       ROUND(AVG(EXTRACT(epoch FROM fin_ts - inicio_ts))::numeric, 0) AS duracion_media_s
FROM silver.contexto
GROUP BY 1, 2
ORDER BY anotaciones DESC
LIMIT 10;

-- Q2. Contención @> (usa el índice GIN) y ruta anidada #>> :
--     potencia de carga media que el propio pipeline derivó, por inversor.
SELECT (valor->>'inverter')::int AS inversor,
       COUNT(*)                  AS ventanas,
       ROUND(AVG((valor #>> '{metrics,ac_load_w_mean}')::numeric), 1) AS carga_ac_media_w,
       ROUND(AVG((valor #>> '{metrics,pv_power_w_mean}')::numeric), 1) AS pv_media_w
FROM silver.contexto
WHERE valor @> '{"source":"derived_context_pipeline"}'
  AND valor #> '{metrics}' IS NOT NULL
GROUP BY 1
ORDER BY 1;

-- Q3. jsonb_path_exists: cargas de entrenamiento de 2 o más épocas (la clave 'epochs' solo existe en esas anotaciones).
SELECT valor->>'model' AS modelo, COUNT(*) AS corridas,
       MAX((valor->>'epochs')::int) AS epocas_max
FROM silver.contexto
WHERE jsonb_path_exists(valor, '$ ? (@.epochs >= 2)')
GROUP BY 1
ORDER BY corridas DESC
LIMIT 8;

-- Q4. La firma de alarma es un arreglo JSON de 8 palabras: se desanida con jsonb_array_elements_text.
SELECT a.alarma_id, e.ord - 1 AS palabra, e.val::int AS valor, COUNT(f.*) AS eventos
FROM gold.dim_alarma a
CROSS JOIN LATERAL jsonb_array_elements_text(a.firma) WITH ORDINALITY AS e(val, ord)
JOIN gold.fact_evento_alarma f USING (alarma_id)
WHERE e.val ~ '^[0-9]+$' AND e.val::int <> 0
GROUP BY 1, 2, 3
ORDER BY eventos DESC;
