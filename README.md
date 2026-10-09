# SolarBI Pascual · Grafana y flujo ETL

- **Integrante:** Samuel Alvarez Becerra
- **Curso:** Inteligencia de Negocios · Grupo 01 · 2026-II
- **Docente:** Ramiro Grisales Montoya
- **Enfoque del grupo:** monitoreo operativo (potencia en el tiempo y detección de fallas)

## Descripción

Flujo ETL (en la práctica ELT: se carga el dato crudo y se transforma con SQL dentro de la base) sobre la telemetría simulada de un inversor solar de 5 kWp, con una lectura cada 5 minutos durante 3 días. El dato pasa por tres capas en PostgreSQL y se muestra en un tablero de Grafana con una alerta de potencia cero a pleno día. Esta etapa es el diseño: los datos reales (más de 4 millones de filas) llegarán en la segunda etapa del proyecto.

```
data/bronze/telemetria.csv          (crudo, no se modifica nunca)
        │  etl/run_etl.py  (Python delgado: COPY + ejecutar sql/ en orden)
        ▼
bronze.telemetria_cruda  ->  silver.lectura_5min  ->  dwh.fact_energia_dia
 (todo texto)                (limpio, con reglas)      (energía diaria, modelo estrella)
                                      │                          │
                                      └──────────┬───────────────┘
                                                 ▼
                                     Grafana (tablero + alerta)
```

Todo corre en contenedores Docker (PostgreSQL 17 y Grafana 12.4) y la configuración sale de variables de entorno.

## Aclaración sobre Power BI

El Paso 4 del enunciado (Power BI) **no se construyó**. El docente autorizó de forma verbal hacer toda la parte de tableros en Grafana, porque Power BI Desktop solo corre en Windows y este trabajo se desarrolla y se presenta en un solo equipo, un Mac. Las cifras de negocio que pedía Power BI (energía total, energía diaria y porcentaje de datos válidos) están en el tablero de Grafana. Los conceptos de Power BI (DAX, seguridad a nivel de fila, plegado de consultas) se responden en la Parte A (`docs/parte_a.md`). Detalle en `powerbi/README.md`.

## Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| `data/bronze/` | `telemetria.csv`: datos crudos generados por el simulador |
| `data/silver/` | `lectura_5min.csv`: lecturas válidas exportadas por el ETL |
| `etl/` | `simulador.py` (genera el bronze, una sola vez) y `run_etl.py` (único punto de entrada del ETL) |
| `sql/` | Esquemas, tablas, reglas de calidad, modelo Gold y reporte, en orden numérico |
| `grafana/` | `dashboard.json` y `provisioning/` (fuente de datos, tablero y alerta definidos por archivo) |
| `docs/` | `parte_a.md`: las 19 respuestas de la Parte A |
| `powerbi/` | Aviso de omisión y camino para retomar |
| `docker-compose.yml` | PostgreSQL y Grafana |

## Cómo reproducir

Requisitos: Docker (OrbStack o Docker Desktop) y Python 3.

```bash
git clone https://github.com/00Ssam00/SOLARBI-ALVAREZ-BECERRA.git
cd SOLARBI-ALVAREZ-BECERRA

# 1. Credenciales: copia la plantilla y completa las dos contraseñas (el archivo .env no se sube al repo)
cp .env.example .env
#    por ejemplo, para generar una: openssl rand -hex 16

# 2. Servicios (PostgreSQL y Grafana)
docker compose up -d

# 3. Entorno de Python
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 4. ETL completo (crea tablas, carga el bronze, limpia y agrega)
.venv/bin/python etl/run_etl.py
```

El bronze ya viene en el repositorio. `python3 etl/simulador.py` lo regenera idéntico (usa `random.seed(42)`), pero no hace falta.

Servicios locales (solo escuchan en `127.0.0.1`):

| Servicio | URL |
|---|---|
| Grafana | http://localhost:3000 (usuario y contraseña del `.env`) |
| Tablero | http://localhost:3000/d/solarbi-operativo |
| Alerta | http://localhost:3000/alerting/list |

### Idempotencia

`run_etl.py` se puede ejecutar las veces que se quiera con el mismo resultado: el bronze se recarga completo desde el CSV, y Silver y Gold usan clave primaria y `INSERT ... ON CONFLICT DO UPDATE`. Todo ocurre en una sola transacción. Conteos estables en cada ejecución:

| Tabla | Filas |
|---|---|
| `bronze.telemetria_cruda` | 887 |
| `silver.lectura_5min` | 832 |
| `dwh.dim_fecha` | 3 |
| `dwh.dim_dispositivo` | 1 |
| `dwh.fact_energia_dia` | 3 |
| Suma de `energia_kwh` | 75,932 kWh |

## Capas de datos

**Bronze.** Copia fiel del CSV, todo como texto, para que un cambio de formato en la fuente no rompa la carga.

**Silver.** La vista `silver.v_calidad_filas` clasifica cada fila en una sola regla, en este orden de prioridad (así leídas = válidas + rechazadas siempre cuadra):

| Orden | Regla | Rechaza |
|---|---|---|
| 1 | `duplicado` | misma pareja (`ts`, `dispositivo_id`) que una fila anterior; se conserva la primera |
| 2 | `faltante` | cualquier campo vacío |
| 3 | `formato` | valor no numérico o fecha mal escrita |
| 4 | `fuera_de_rango` | `p_ac_kw < 0` (físicamente imposible) |

La potencia 0 es **válida**. Resultado del reporte:

| Concepto | Filas | % |
|---|---|---|
| Leídas | 887 | 100,00 |
| Rechazadas: duplicado | 23 | 2,59 |
| Rechazadas: faltante | 15 | 1,69 |
| Rechazadas: formato | 0 | 0,00 |
| Rechazadas: fuera de rango | 17 | 1,92 |
| **Válidas** | **832** | **93,80** |

**Gold.** `dwh.fact_energia_dia` (clave primaria `fecha_key, dispositivo_key`) con `dim_fecha` y `dim_dispositivo`, un esquema estrella pequeño.

| Fecha | Energía (kWh) | Lecturas válidas | % datos válidos |
|---|---|---|---|
| 2026-10-01 | 26,945 | 282 | 97,92 |
| 2026-10-02 | 22,681 | 274 | 95,14 |
| 2026-10-03 | 26,306 | 276 | 95,83 |

## Decisiones propias

- **Energía por intervalo = potencia (kW) × 5/60 h.** La energía diaria suma solo lecturas válidas y **no imputa** las perdidas, así que queda subestimada entre 2 y 5 % por día.
- **`pct_datos_validos` = lecturas válidas / 288 esperadas por día** (24 h × 12 lecturas por hora), con tope de 100. Es una decisión nuestra, no del enunciado. No es lo mismo que el 93,80 % de Silver, que divide entre las 887 filas leídas (cuenta los duplicados como rechazo).
- **Zona horaria.** El CSV trae fechas sin zona; se interpretan como `America/Bogota` y se guardan en `timestamptz`. PostgreSQL y Grafana corren en esa zona. Sin esto, todo se vería corrido 5 horas.
- **Falla inyectada.** El simulador apaga el inversor el 2026-10-02 de 11:00 a 11:55 (potencia 0 con irradiancia de 720 a 960 W/m²), para que la alerta tenga algo que detectar. Es un valor válido, por eso Silver no lo rechaza.

## Grafana

El tablero `SolarBI: monitoreo operativo` (rango fijo del 1 al 3 de octubre, auto-refresh apagado, zona `America/Bogota`) tiene 6 paneles: energía total, energía del día seleccionado, % de datos válidos del día, potencia AC e irradiancia cada 5 minutos (`$__timeFilter`), potencia promedio por hora (`$__timeGroupAlias`) y energía diaria.

**Alerta `potencia-cero-dia`:** cada 1 minuto cuenta las lecturas con `p_ac_kw = 0` e irradiancia mayor a 100 W/m² entre las 9:00 y las 15:00 (hora Colombia). Si son tres o más, pasa a pendiente y, tras 2 minutos, a *Firing*. Detecta exactamente las 12 lecturas de la falla. La consulta mira los últimos 30 días porque los datos son históricos; con datos en vivo bastaría una ventana de 15 minutos. La fuente de datos, el tablero y la alerta se definen por archivos en `grafana/provisioning/`, sin configuración manual.

## Automatización con cron (solo documentada, no implementada)

Ejecutar el ETL todos los días a medianoche (Linux o macOS):

```
0 0 * * *  cd /ruta/al/proyecto && .venv/bin/python etl/run_etl.py >> etl.log 2>&1
```

En Windows, con el Programador de tareas (sin probar):

```
schtasks /Create /SC DAILY /ST 00:00 /TN "SolarBI ETL" /TR "cmd /c cd /d C:\ruta\al\proyecto && .venv\Scripts\python.exe etl\run_etl.py >> etl.log 2>&1"
```

Como el ETL es idempotente, una ejecución repetida no duplica datos.

## Seguridad

- Ninguna credencial está en el repositorio: viven en `.env` (excluido por `.gitignore`); el repo solo trae `.env.example`, sin valores.
- Los puertos de los contenedores solo escuchan en `127.0.0.1`.
- Los datos de PostgreSQL viven en un volumen nombrado de Docker, fuera del repositorio.

## Limitaciones

- Los datos son simulados: no hay inversor real ni transporte por MQTT. Esas capas se explican en la Parte A.
- Un solo dispositivo; el modelo admite más, pero no se probó con varios.
- Las medidas DAX de `powerbi/README.md` no están probadas.
- El cron no está implementado, solo escrito.

## English corner

> One governed dataset, two views: Grafana for real-time operations and Power BI for business decisions.

In this delivery only the Grafana view was built; the Power BI view is documented in `powerbi/README.md`.

## Quién hizo qué

| Integrante | Aportes |
|---|---|
| Samuel Alvarez Becerra | Trabajo individual autorizado: simulador y capa Bronze, reglas de Silver, modelo Gold, `run_etl.py`, Docker Compose, tablero y alerta de Grafana, respuestas de la Parte A, README e informe en PDF |
