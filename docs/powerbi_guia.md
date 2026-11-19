# Guía de Power BI (se construye en Windows)

Formato entregado: `powerbi/SolarBI.pbix` más `powerbi/medidas.dax` (medidas en texto) y `powerbi/SolarBI.pbix.texto/` (definición de páginas y visuales en JSON). El modelo de datos es binario dentro del `.pbix`; el formato PBIP (TMDL en texto) sería más limpio para Git (Archivo > Opciones > Características en versión preliminar > Guardar con formato de proyecto de Power BI).

## 1. Conexión (no a los archivos de origen)

El Service `postgres-externo` (LoadBalancer :5433) solo escucha en `127.0.0.1` del Mac (comprobado con `lsof`), así que **otro PC no lo alcanza**. Para que Power BI en Windows llegue al clúster, en el Mac abre un reenvío de puerto en otra terminal y déjalo corriendo mientras trabajas:

```bash
kubectl --context orbstack -n solarbi port-forward --address 0.0.0.0 svc/postgres 5435:5432
ipconfig getifaddr en0        # IP del Mac en la red (los dos equipos deben estar en la misma red)
```

En Power BI: *Obtener datos > Base de datos PostgreSQL*, servidor `IP_DEL_MAC:5435`, base `solarbi`, modo **Importar**, usuario `lector_bi` y la clave `LECTOR_CLAVE` de `.env` (rol de solo lectura). Cuando termines, cierra el reenvío (Ctrl+C): mientras está abierto, la base es accesible desde la red local con ese rol. Si el Mac tiene el firewall activo, permite las conexiones entrantes para `kubectl`. Si Power BI pide cifrado y falla, en las opciones de la conexión desactiva "Cifrar conexiones". Alternativa si no hay red compartida: exportar las tablas `gold.*` a CSV con DBeaver (menos fiel a lo que pide el enunciado).

Tablas a importar: `gold.dim_fecha`, `gold.dim_hora`, `gold.dim_inversor`, `gold.dim_estado_operativo`, `gold.dim_alarma`, `gold.dim_tipo_contexto`, `gold.fact_lectura_5min`, `gold.fact_energia_dia`, `gold.fact_evento_alarma`, `gold.fact_contexto`, `gold.parametro`.

## 2. Modelo semántico

Relaciones uno a muchos (dimensión → hecho), dirección única:

| Dimensión | Hecho | Columna |
|---|---|---|
| dim_fecha[fecha_id] | fact_lectura_5min, fact_energia_dia, fact_evento_alarma, fact_contexto | fecha_id |
| dim_hora[hora_id] | fact_lectura_5min, fact_evento_alarma, fact_contexto | hora_id |
| dim_inversor[inversor_id] | los cuatro hechos | inversor_id |
| dim_estado_operativo[estado_id] | fact_lectura_5min | estado_id |
| dim_alarma[alarma_id] | fact_lectura_5min, fact_evento_alarma | alarma_id |
| dim_tipo_contexto[tipo_contexto_id] | fact_contexto | tipo_contexto_id |

**Tabla de fechas propia:** `dim_fecha` marcada como tabla de fechas (*Herramientas de tabla > Marcar como tabla de fechas*, columna `fecha`). Ordenar `nombre_mes` por `mes` y `nombre_dia` por `dia_semana`. Jerarquía: anio > trimestre > nombre_mes > fecha.

## 3. Medidas DAX

```dax
Energía solar kWh   = SUM ( fact_energia_dia[pv_kwh_integrado] )
Carga kWh           = SUM ( fact_energia_dia[consumo_kwh_integrado] )
Red kWh             = SUM ( fact_energia_dia[red_kwh_integrado] )

Autosuficiencia =
VAR dias = FILTER ( fact_energia_dia, fact_energia_dia[cobertura_dia] >= 0.9 )
RETURN 1 - DIVIDE ( SUMX ( dias, fact_energia_dia[red_kwh_integrado] ),
                    SUMX ( dias, fact_energia_dia[consumo_kwh_integrado] ) )

Disponibilidad = AVERAGE ( fact_energia_dia[cobertura_dia] )

-- Inteligencia de tiempo
Solar YTD kWh   = TOTALYTD ( [Energía solar kWh], dim_fecha[fecha] )
Solar mes anterior kWh = CALCULATE ( [Energía solar kWh], DATEADD ( dim_fecha[fecha], -1, MONTH ) )
Variación vs mes anterior = DIVIDE ( [Energía solar kWh] - [Solar mes anterior kWh], [Solar mes anterior kWh] )

-- Economía (con el parámetro what-if de tarifa)
Tarifa COP/kWh = SELECTEDVALUE ( 'Parámetro tarifa'[Tarifa], 790.49 )
Costo importación COP = [Red kWh] * [Tarifa COP/kWh]
Valor solar COP       = [Energía solar kWh] * [Tarifa COP/kWh]

-- Operación
SOC mínimo % = MIN ( fact_lectura_5min[soc_min] )
% bloques con batería baja =
DIVIDE ( CALCULATE ( COUNTROWS ( fact_lectura_5min ), fact_lectura_5min[soc_min] < 30 ),
         COUNTROWS ( fact_lectura_5min ) )
Eventos de alarma = COUNTROWS ( fact_evento_alarma )
```

Nota: la dimensión de fechas termina el 31 jul 2026 y el registro, el 13 jul 2026; `TOTALYTD` y `DATEADD` funcionan dentro de ese rango.

## 4. Parámetro de escenario (what-if)

*Modelado > Nuevo parámetro > Rango numérico*: nombre `Parámetro tarifa`, mínimo 500, máximo 1200, incremento 10, valor predeterminado 790. Agrega la segmentación. Las medidas de arriba ya lo usan.

## 5. Páginas (mínimo tres, con navegación, segmentaciones y drill-down)

1. **Resumen ejecutivo.** Tarjetas: Energía solar, Carga, Red, Autosuficiencia, Costo importación. Columnas por mes (con drill-down año > trimestre > mes > día) comparando solar y red. Segmentaciones: inversor y fecha. Botón de navegación a las otras páginas.
2. **Balance energético.** Diagrama de Sankey (visual de Marketplace "Sankey Chart") u otra visual de flujo: de dónde viene la energía (sol, red) y a dónde va (carga, batería). Si no usas Sankey, un gráfico de cascada con Solar + Red = Carga + variación de batería. Perfil horario con `dim_hora[hora_id]`. Aquí va el what-if de tarifa con el costo.
3. **Calidad y alarmas.** Eventos de alarma por mes y por `dim_alarma[descripcion]`; Disponibilidad por mes; tabla de `fact_energia_dia` con energía integrada contra contador (`pv_kwh_equipo`); SOC mínimo.

Botones de navegación en las tres páginas (*Insertar > Botones > Navegador de páginas*).

## 6. Capturas para el informe

Guárdalas como `docs/img/powerbi_1.png`, `powerbi_2.png`, `powerbi_3.png` en el repositorio y vuelve a generar el PDF con `python3 scripts/build_informe.py`.
