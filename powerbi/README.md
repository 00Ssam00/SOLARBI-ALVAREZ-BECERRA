# Power BI: omitido en esta entrega

**El Paso 4 del enunciado (página de Power BI con medidas DAX) no se construyó.** El docente, Ramiro Grisales Montoya, autorizó de forma verbal hacer toda la parte de tableros en Grafana. Power BI Desktop solo corre en Windows, y este trabajo se desarrolla y se presenta en un solo equipo, un Mac.

Por eso esta carpeta no contiene un `.pbix` ni un `.pbip`. Los conceptos de Power BI (DAX, seguridad a nivel de fila, plegado de consultas, `.pbip` frente a `.pbix`) se responden en la Parte A de la consulta (`docs/parte_a.md`, preguntas D2, G4, E4 y V1).

## Dónde queda cubierto cada requisito del Paso 4

| Pide el enunciado | Dónde está | Fuente de la cifra |
|---|---|---|
| Tarjeta con la energía total (kWh) | Grafana, panel "Energía total del rango (kWh)" | `sum(energia_kwh)` de `dwh.fact_energia_dia` |
| Gráfico con la energía diaria | Grafana, panel "Energía diaria (kWh)" (barras por fecha, no línea) | `dwh.fact_energia_dia` |
| Tarjeta con el % de datos válidos | Grafana, panel "% de datos válidos del día" | `pct_datos_validos` de `dwh.fact_energia_dia` |
| Conexión a PostgreSQL | Fuente de datos `solarbi-pg`, aprovisionada en `grafana/provisioning/datasources/` | Usuario del ETL (variables `PG*` del `.env`) |
| Cifras desde medidas, no desde columnas arrastradas | Cada cifra sale de una consulta SQL sobre el modelo `dwh`, no de columnas sueltas | `grafana/dashboard.json` |

## Si más adelante se retoma Power BI (Entregable V)

El modelo `dwh` ya tiene forma de esquema estrella (`fact_energia_dia`, `dim_fecha`, `dim_dispositivo`), así que no haría falta rehacer datos. Pasos previstos, **sin probar**:

1. En Power BI Desktop (Windows): Obtener datos, PostgreSQL, servidor `localhost:5432`, base `solarbi`, modo Importar.
2. Usuario y clave de `PGUSER` y `PGPASSWORD` en `.env`.
3. Cargar `dwh.fact_energia_dia`, `dwh.dim_fecha` y `dwh.dim_dispositivo`, y relacionarlas por `fecha_key` y `dispositivo_key`.
4. Medidas de partida (sin probar):

```dax
Energia total (kWh) = SUM ( fact_energia_dia[energia_kwh] )

% datos validos =
DIVIDE (
    SUM ( fact_energia_dia[lecturas_validas] ),
    SUM ( fact_energia_dia[lecturas_esperadas] )
)
```

La segunda suma lecturas válidas y esperadas por separado en vez de promediar porcentajes diarios, así un día con menos lecturas pesa lo que corresponde.
