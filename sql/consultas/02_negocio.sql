-- Consultas de negocio: agregaciones, funciones de ventana y comparativos entre periodos.

-- N1. Energía FV mensual por inversor, variación contra el mes anterior (LAG) y acumulado del año (SUM OVER).
WITH mensual AS (
  SELECT f.inversor_id, date_trunc('month', d.fecha)::date AS mes,
         SUM(f.pv_kwh_integrado) AS pv_kwh, AVG(f.cobertura_dia) AS cobertura
  FROM gold.fact_energia_dia f JOIN gold.dim_fecha d USING (fecha_id)
  GROUP BY 1, 2
)
SELECT inversor_id, mes, ROUND(pv_kwh::numeric, 1) AS pv_kwh, ROUND((cobertura*100)::numeric) AS cobertura_pct,
       ROUND((100 * (pv_kwh - LAG(pv_kwh) OVER w) / NULLIF(LAG(pv_kwh) OVER w, 0))::numeric, 1) AS var_vs_mes_ant_pct,
       ROUND(SUM(pv_kwh) OVER (PARTITION BY inversor_id ORDER BY mes)::numeric, 1) AS acumulado_kwh
FROM mensual
WINDOW w AS (PARTITION BY inversor_id ORDER BY mes)
ORDER BY inversor_id, mes;

-- N2. Autosuficiencia diaria = 1 - red/carga, con media móvil de 7 días y ranking del mes (AVG/RANK OVER).
WITH dia AS (
  SELECT f.inversor_id, d.fecha, f.red_kwh_integrado AS red, f.consumo_kwh_integrado AS carga,
         1 - f.red_kwh_integrado / NULLIF(f.consumo_kwh_integrado, 0) AS autosuf
  FROM gold.fact_energia_dia f JOIN gold.dim_fecha d USING (fecha_id)
  WHERE f.cobertura_dia >= 0.9 AND f.consumo_kwh_integrado > 1
)
SELECT inversor_id, fecha, ROUND((autosuf*100)::numeric, 1) AS autosuf_pct,
       ROUND((AVG(autosuf) OVER (PARTITION BY inversor_id ORDER BY fecha ROWS 6 PRECEDING)*100)::numeric, 1) AS media_7d_pct,
       RANK() OVER (PARTITION BY inversor_id, date_trunc('month', fecha) ORDER BY autosuf DESC) AS puesto_en_el_mes
FROM dia
ORDER BY inversor_id, fecha
LIMIT 40;

-- N3. Horas pico de generación: percentil 90 de potencia FV por hora local y inversor (percentile_cont).
SELECT inversor_id, hora_id,
       ROUND(AVG(pv_w_prom)::numeric) AS pv_prom_w,
       ROUND((percentile_cont(0.9) WITHIN GROUP (ORDER BY pv_w_prom))::numeric) AS pv_p90_w
FROM gold.fact_lectura_5min
WHERE cobertura >= 0.5 AND pv_w_prom IS NOT NULL
GROUP BY 1, 2
HAVING AVG(pv_w_prom) > 50
ORDER BY 1, 2;

-- N4. Impacto de la carga de cómputo (solo hay anotaciones para el inversor 1, sobre todo en nov-dic 2025):
--     potencia de carga media con y sin anotación activa (join por rango de tiempo).
WITH marcada AS (
  SELECT l.inversor_id, l.carga_w_prom,
         EXISTS (SELECT 1 FROM gold.fact_contexto c
                 JOIN gold.dim_tipo_contexto t USING (tipo_contexto_id)
                 WHERE t.categoria = 'carga de cómputo' AND c.inversor_id = l.inversor_id
                   AND l.bloque_ts BETWEEN c.inicio_ts AND c.fin_ts) AS con_computo
  FROM gold.fact_lectura_5min l
  WHERE l.carga_w_prom IS NOT NULL AND l.cobertura >= 0.5
    AND l.inversor_id = 1 AND l.bloque_ts >= '2025-11-01' AND l.bloque_ts < '2026-01-01'
)
SELECT inversor_id, con_computo, COUNT(*) AS bloques, ROUND(AVG(carga_w_prom)::numeric) AS carga_media_w
FROM marcada GROUP BY 1, 2 ORDER BY 1, 2;

-- N5. Alarmas: duración típica por tipo y mes con comparativo contra el mes anterior.
WITH m AS (
  SELECT date_trunc('month', f.inicio_ts)::date AS mes, f.alarma_id, COUNT(*) AS eventos,
         ROUND((percentile_cont(0.5) WITHIN GROUP (ORDER BY f.duracion_s))::numeric) AS duracion_mediana_s
  FROM gold.fact_evento_alarma f GROUP BY 1, 2
)
SELECT mes, alarma_id, eventos, duracion_mediana_s,
       eventos - LAG(eventos) OVER (PARTITION BY alarma_id ORDER BY mes) AS dif_vs_mes_ant
FROM m ORDER BY alarma_id, mes
LIMIT 30;
