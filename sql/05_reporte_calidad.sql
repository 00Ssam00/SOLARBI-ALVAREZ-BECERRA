-- Reporte de calidad (solo lectura): una fila por concepto, en orden de presentación.
WITH conteo AS (
    SELECT resultado, count(*) AS filas FROM silver.v_calidad_filas GROUP BY resultado
), total AS (
    SELECT count(*) AS leidas FROM silver.v_calidad_filas
)
SELECT 1 AS orden, 'filas leídas' AS concepto, leidas AS filas, 100.00 AS porcentaje FROM total
UNION ALL
SELECT 2, 'rechazadas: ' || r.regla, coalesce(c.filas, 0),
       round(100.0 * coalesce(c.filas, 0) / t.leidas, 2)
FROM (VALUES ('duplicado'), ('faltante'), ('formato'), ('fuera_de_rango')) AS r(regla)
LEFT JOIN conteo c ON c.resultado = r.regla CROSS JOIN total t
UNION ALL
SELECT 3, 'filas válidas', coalesce(c.filas, 0), round(100.0 * coalesce(c.filas, 0) / t.leidas, 2)
FROM total t LEFT JOIN conteo c ON c.resultado = 'valida'
ORDER BY 1, 2;
