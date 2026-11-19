-- Parámetros de negocio editables y vistas de indicadores (las consumen Power BI, Grafana y el informe).

CREATE TABLE IF NOT EXISTS gold.parametro (
    clave   TEXT PRIMARY KEY,
    valor   NUMERIC NOT NULL,
    unidad  TEXT NOT NULL,
    fuente  TEXT NOT NULL
);
INSERT INTO gold.parametro VALUES
  ('tarifa_cop_kwh', 790.49, 'COP/kWh',
   'EPM, kWh de estrato 3 en Medellín al cierre de 2025 (El Colombiano, feb 2026). Referencia pública; sustituir por la tarifa del contrato real.'),
  ('soc_umbral_bajo', 30, '%', 'Umbral de la alerta Batería baja (el valor operativo vive en el ConfigMap grafana-alertas).'),
  ('cobertura_dia_minima', 0.9, 'fracción', 'Un día cuenta para comparar contra el contador del equipo si tiene al menos 90 % de cobertura.')
ON CONFLICT (clave) DO NOTHING;

CREATE OR REPLACE VIEW gold.v_kpi_mensual AS
SELECT f.inversor_id, d.anio, d.mes, d.nombre_mes,
       SUM(f.pv_kwh_integrado)       AS pv_kwh,
       SUM(f.consumo_kwh_integrado)  AS carga_kwh,
       SUM(f.red_kwh_integrado)      AS red_kwh,
       AVG(f.cobertura_dia)          AS disponibilidad,
       1 - SUM(f.red_kwh_integrado) FILTER (WHERE f.cobertura_dia >= 0.9)
           / NULLIF(SUM(f.consumo_kwh_integrado) FILTER (WHERE f.cobertura_dia >= 0.9), 0) AS autosuficiencia,
       SUM(f.red_kwh_integrado) * p.valor AS costo_red_cop,
       SUM(f.pv_kwh_integrado)  * p.valor AS valor_solar_cop
FROM gold.fact_energia_dia f
JOIN gold.dim_fecha d USING (fecha_id)
CROSS JOIN gold.parametro p
WHERE p.clave = 'tarifa_cop_kwh'
GROUP BY f.inversor_id, d.anio, d.mes, d.nombre_mes, p.valor;

-- Porcentaje de datos válidos por inversor, desde la última corrida correcta del ETL.
CREATE OR REPLACE VIEW etl.v_pct_validos AS
WITH ultima AS (SELECT MAX(corrida_id) AS id FROM etl.corrida WHERE estado = 'ok'),
     r AS (SELECT inversor_id, SUM(filas_afectadas) FILTER (WHERE regla = 'R07_FILA_SIN_MEDIDAS') AS descartadas,
                  SUM(filas_afectadas) FILTER (WHERE regla ~ '^R0[1-6]_') AS anuladas
           FROM etl.regla_calidad, ultima WHERE corrida_id = ultima.id AND inversor_id IN (1, 2) GROUP BY inversor_id),
     c AS (SELECT inversor_id, valor_origen AS filas_validas FROM etl.conciliacion, ultima
           WHERE corrida_id = ultima.id AND control LIKE 'filas Bronze%')
SELECT c.inversor_id, c.filas_validas + r.descartadas AS filas_bronze, r.descartadas, r.anuladas,
       ROUND(100.0 * c.filas_validas / (c.filas_validas + r.descartadas), 3) AS pct_filas_utilizables
FROM c JOIN r USING (inversor_id);
