# Parte A · Consulta

**SolarBI Pascual · Inteligencia de Negocios · Grupo 01 · 2026-II**
Enfoque del grupo: monitoreo operativo (potencia en el tiempo y detección de fallas).

Máximo 120 palabras por respuesta (sin tablas, diagramas ni código). Fuentes entre corchetes, listadas al final.

---

## Bloque 1 · Power BI y Grafana

### D1. ¿Qué es Grafana?

Grafana es una plataforma de visualización y monitoreo que consulta los datos donde viven, sin copiarlos. Sus piezas son: fuentes de datos (data sources), como el PostgreSQL de SolarBI; paneles, cada uno con una consulta y una visualización; tableros (dashboards), que agrupan paneles; variables, que parametrizan las consultas (por ejemplo, elegir el día) [7]; y alertas (alerting), reglas que vigilan una consulta [1]. Grafana OSS es la edición autoadministrada y gratuita, con licencia AGPLv3, y es la que correremos en Docker [2]. Grafana Cloud es el servicio gestionado por Grafana Labs, con capa gratuita para 3 usuarios [1].


### D2. Power BI frente a Grafana

| Criterio | Power BI | Grafana |
|---|---|---|
| Propósito principal | Análisis e informes de negocio | Monitoreo y visualización operativa |
| Usuario típico | Analista y directivo | Operador e ingeniero de planta |
| Conexión a los datos | Importar o DirectQuery; puerta de enlace si la fuente es local [16] | Consulta en vivo a cada fuente de datos, sin copiar [1] |
| Modelo semántico y lenguaje | Modelo con relaciones y medidas en DAX; transformación en Power Query | Sin modelo; se escribe la consulta del origen (SQL en PostgreSQL) [3] |
| Actualización y tiempo real | Importado: hasta 8 actualizaciones diarias en Pro y 48 en Premium por usuario [13]; DirectQuery: mosaicos desde cada 15 min [16] | La consulta se ejecuta al abrir o al refrescar el tablero; segundos de latencia |
| Alertas | Alertas de datos en el servicio (no en Desktop), sobre tarjetas, medidores y KPI [12] | Reglas con varias consultas, estados y puntos de contacto [4][5] |
| Licenciamiento y costo | Desktop gratis; Pro USD 14 y Premium por usuario USD 24, por usuario al mes [10] | OSS gratis (AGPLv3) [2]; Cloud con capa gratuita; Enterprise por cotización [1] |
| Control de acceso | Seguridad a nivel de fila (row-level security, RLS) con roles y filtros DAX [11] | Organizaciones, equipos y permisos por carpeta y tablero; RBAC fino solo en Enterprise y Cloud [6] |
| Versionado y despliegue | Proyecto `.pbip` en archivos de texto [15] | JSON del tablero y aprovisionamiento por archivos [8][9] |

En SolarBI, Grafana cubre el monitoreo de la potencia; Power BI cubriría el análisis de negocio (energía, ahorro).

*Precios consultados en la página oficial el 3 de octubre de 2026; Microsoft aclara que pueden variar por país.*

### D3. Tableros operativo, analítico y estratégico

Un tablero operativo muestra el estado actual para actuar en minutos (potencia, alarmas). Uno analítico permite explorar causas y tendencias con filtros (rendimiento por día, comparación entre dispositivos). Uno estratégico resume pocos indicadores para decidir (ahorro, energía mensual). En SolarBI, por el enfoque de monitoreo, el tablero principal es operativo y va en Grafana; los indicadores que dependen de tarifas o comparaciones históricas encajan mejor en Power BI por su modelo y sus medidas DAX.

| KPI | Tipo | Herramienta | Por qué |
|---|---|---|---|
| Energía diaria (kWh) | Analítico | Grafana | Es una agregación simple sobre `fact_energia_dia` |
| Energía total acumulada | Estratégico | Power BI | Medida DAX para comparar periodos y plantas |
| Yield (kWh/kWp) y Performance Ratio | Analítico | Power BI | El yield usa la capacidad instalada (5 kWp); el PR además la irradiación. PR = yield final / yield de referencia [33] |
| Ahorro (COP) | Estratégico | Power BI | Combina energía con tarifas, para directivos |
| Disponibilidad y alarmas | Operativo | Grafana | Exigen alertas y datos casi en tiempo real |
| % de datos válidos | Operativo | Grafana | Una caída del porcentaje indica fallas de la fuente, junto a la potencia |


### D4. Grafana con PostgreSQL: series de tiempo y macros

Una consulta de series de tiempo debe devolver una columna llamada `time` (fecha-hora o época Unix en segundos), ordenada por ese campo, con columnas numéricas y el formato "Time series" [3]. La macro `$__timeFilter(columna)` se expande a un `BETWEEN` con el rango del selector de tiempo, para traer solo lo visible. La macro `$__timeGroup(columna, '1h')` agrupa el tiempo en intervalos (con TimescaleDB usa `time_bucket`) y `$__timeGroupAlias` además nombra la columna `time` [3].

```sql
-- Potencia promedio por hora
SELECT
  $__timeGroupAlias(ts, '1h'),
  AVG(p_ac_kw) AS potencia_promedio_kw
FROM silver.lectura_5min
WHERE $__timeFilter(ts)
  AND dispositivo_id = ${dispositivo}   -- variable del tablero
GROUP BY 1
ORDER BY 1;
```


### D5. Alertas: Grafana Alerting frente a Power BI

Grafana Alerting evalúa reglas (consultas más una condición) cada cierto intervalo; el estado pasa de Normal a Pendiente y a Alerta cuando se cumple el periodo de espera, y los avisos salen por puntos de contacto (correo, Slack, PagerDuty, webhooks) enrutados con políticas [4][5]. Las alertas de datos de Power BI solo se crean en el servicio, sobre tarjetas, medidores o KPI numéricos fijados en un tablero, y se evalúan solo cuando el modelo se actualiza [12]; en informes existen alertas de Fabric Activator (correo o Teams), que exigen capacidad Fabric [34]. Para la planta, la regla propuesta es potencia cero a pleno día:

| Campo | Valor |
|---|---|
| Condición | `p_ac_kw = 0` con `irradiancia_wm2 > 100` |
| Ventana horaria | Entre 9:00 y 15:00, hora de Colombia |
| Umbral | Tres o más lecturas (15 minutos a una lectura cada 5) |
| Evaluación | Cada minuto; periodo pendiente de 2 minutos en la demostración |
| Canal | Correo y Slack del equipo de mantenimiento |


---

## Bloque 2 · Gobernanza de datos

### G1. Gobernanza, gestión y calidad de datos

La gobernanza de datos (data governance) es el ejercicio de autoridad y control (planificar, monitorear, hacer cumplir) sobre la gestión de los activos de datos: define quién decide, con qué reglas y responsabilidades [35]. La gestión de datos (data management) agrupa las funciones que ejecutan esas reglas: arquitectura, almacenamiento, integración y seguridad. La calidad de datos (data quality) es un área de la gestión que mide si el dato sirve para su uso: exactitud, completitud, unicidad. El marco DAMA-DMBOK organiza estas áreas de conocimiento [17]. En SolarBI, la gobernanza decide que la potencia no puede ser negativa, el ETL aplica esa regla (gestión) y el porcentaje de datos válidos mide su cumplimiento (calidad).


### G2. Roles de datos

El dueño del dato (data owner) responde por un conjunto de datos y autoriza su uso; el responsable de datos (data steward) define significados y reglas de calidad y vigila su cumplimiento; el custodio (data custodian) opera la infraestructura que guarda y protege el dato [17]. En este trabajo una sola persona cumple los tres papeles, pero se documentan por separado porque el proyecto crecerá con un equipo.

| Rol de gobernanza | Rol del equipo SolarBI | Responsabilidad concreta |
|---|---|---|
| Dueño del dato | Product owner | Decide qué se mide y quién accede |
| Responsable de datos | Modelador y analista BI | Define KPI, diccionario y reglas de calidad |
| Custodio | Ingeniero de datos | Mantiene Postgres, el ETL, respaldos y accesos |


### G3. Contrato de datos

Un contrato de datos (data contract) es un acuerdo escrito entre quien produce un dato y quien lo consume. Debe incluir esquema, unidades, frecuencia, responsable y niveles de calidad; el estándar ODCS lo organiza en esquema, calidad, acuerdo de servicio y equipo [30]. Si la fuente cambia un campo sin avisar (por ejemplo, `p_ac_kw` pasa a vatios), el ETL puede fallar al cargar o, peor, aceptar valores 1000 veces mayores: el tablero mostraría picos falsos y la alerta perdería sentido. Por eso se valida el esquema al entrar a Bronze y se rechaza lo que no cumpla el contrato.

Ejemplo simplificado (no sigue el esquema oficial de ODCS; el umbral de 95 % es una propuesta):

```yaml
dispositivo: inversor_01      # frecuencia: 5 minutos, responsable: Samuel Alvarez
campos:
  - {nombre: ts, tipo: timestamp, zona: America/Bogota}
  - {nombre: p_ac_kw, tipo: numerico, unidad: kW, rango: ">= 0"}
calidad: {datos_validos_min: "95 %"}
```


### G4. Seguridad a nivel de fila y control de acceso en Grafana

La seguridad a nivel de fila (RLS) de Power BI se define con roles cuyo filtro DAX deja ver solo las filas verdaderas; los miembros se asignan en el servicio y la restricción aplica a quien tenga rol Visor [11]. En Grafana el control equivalente es por organizaciones, equipos y permisos de carpeta o tablero (ver, editar, administrar); los permisos por fuente de datos son de Enterprise y Cloud [6]. No hay RLS nativo: la consulta puede filtrar con `${__user.email}` [36], pero solo protege si el usuario no puede editar el panel. Una barrera sólida son las políticas de fila de PostgreSQL [23].

```dax
-- Rol "ResponsableSitio" sobre la tabla dim_dispositivo
[responsable_correo] = USERPRINCIPALNAME()
```

```sql
-- Equivalente aproximado en una consulta de Grafana
SELECT ... FROM dwh.dim_dispositivo
WHERE responsable_correo = '${__user.email}'
```


### G5. Ley 1581 de 2012

Los datos de SolarBI (potencia, irradiancia y temperatura de un inversor) no son personales: la ley define dato personal como información vinculada o asociable a personas naturales determinadas o determinables [18]. Si el tablero mostrara qué operador atendió cada alarma, sí lo serían: habría un titular, un responsable y un encargado del tratamiento, y aplicarían principios como finalidad, libertad (consentimiento), acceso restringido y seguridad [18]. Postura del equipo: recoger lo mínimo, informar la finalidad, restringir el acceso, no publicar nombres ni credenciales y no subir datos personales al repositorio.


---

## Bloque 3 · Automatización de procesos ETL

### E1. ETL frente a ELT, capas y Power Query

En ETL (extraer, transformar, cargar) la transformación ocurre antes de cargar, en un servidor intermedio; en ELT se carga el dato crudo y se transforma dentro del destino [20]. SolarBI es ELT: `COPY` carga el CSV a Bronze y SQL limpia (Silver) y agrega (Gold) dentro de PostgreSQL [19][22]. Power Query sí es una herramienta ETL: extrae de la fuente, transforma con pasos M y carga al modelo de Power BI; cuando el plegado de consultas (query folding) empuja los pasos a la base, en la práctica se parece a ELT [14].

| Capa | Contenido en SolarBI | Operación |
|---|---|---|
| Bronze | `data/bronze/telemetria.csv` y su tabla cruda | Carga sin modificar |
| Silver | `silver.lectura_5min` | Deduplicar, quitar faltantes, validar rango |
| Gold | `dwh.fact_energia_dia` | Agregación diaria y energía en kWh |


### E2. Carga completa, incremental e idempotencia

Una carga completa (full load) reemplaza todo el destino en cada corrida; una incremental procesa solo lo nuevo o cambiado. Una carga es idempotente si ejecutarla varias veces deja el mismo resultado. En `fact_energia_dia`, la clave primaria `(fecha_key, dispositivo_key)` impide filas repetidas y `INSERT ... ON CONFLICT DO UPDATE` actualiza la fila existente en lugar de duplicarla, de forma atómica [21]. Así, correr el ETL dos veces conserva los conteos y reprocesar un día corrige sus valores sin duplicarlos.

```sql
INSERT INTO dwh.fact_energia_dia (fecha_key, dispositivo_key, energia_kwh, pct_datos_validos)
SELECT fecha_key, dispositivo_key, energia_kwh, pct_datos_validos
FROM tmp_resumen_diario
ON CONFLICT (fecha_key, dispositivo_key)
DO UPDATE SET energia_kwh        = EXCLUDED.energia_kwh,
              pct_datos_validos  = EXCLUDED.pct_datos_validos;
```


### E3. Tres formas de automatizar un flujo

| | cron / Programador de tareas | Apache Airflow | Actualización programada de Power BI |
|---|---|---|---|
| Qué es | Planificadores del sistema operativo que ejecutan un comando según una expresión de tiempo; cron usa cinco campos [37][38] | Plataforma para desarrollar, programar y monitorear flujos definidos como DAG en Python [24] | Función del servicio que recarga un modelo importado; hasta 8 veces al día en Pro y 48 en Premium por usuario [13] |
| Qué automatiza | Cualquier script, por ejemplo `python etl/run_etl.py` | Pipelines con varias tareas, dependencias, reintentos y monitoreo | Solo el refresco del modelo, no el ETL |
| Cuándo conviene | Un solo paso sin dependencias (SolarBI hoy) | Varias fuentes y pasos, con necesidad de visibilidad | Cuando los datos ya están listos en la base |

En Kubernetes, el equivalente de cron es el recurso CronJob, con la misma sintaxis de cinco campos [25].


### E4. Plegado de consultas

El plegado de consultas es el mecanismo con el que Power Query traduce los pasos de transformación a una sola consulta nativa que ejecuta la fuente (aquí, PostgreSQL), en lugar de traer todo y procesarlo localmente. Mejora el rendimiento porque filtra y agrega donde están los datos y mueve menos filas [14]. Se verifica con "View Native Query", que muestra la solicitud enviada a la fuente cuando el conector lo permite; en Power Query Online hay además indicadores de plegado por paso y un plan de consulta [14]. En SolarBI, la consulta nativa debería incluir el filtro de fechas. Los CSV no se pliegan.


---

## Bloque 4 · Internet de las Cosas (IoT)

### I1. Arquitectura IoT por capas

Las capas son: dispositivo (inversor con sensores), puerta de enlace (gateway) en el borde que lee el inversor y publica, red o intermediario (broker) que distribuye los mensajes, almacenamiento y aplicación. En el trabajo, `simulador.py` hace de dispositivo y puerta de enlace; el resto de la ruta es real. El diagrama indica la capa de la lectura en cada momento.

```
Inversor ─> Gateway ─> Broker MQTT ─> Archivo CSV ─> PostgreSQL ─────────────> Grafana
(sensor)    (borde)    (red)          [Bronze]       silver.lectura_5min       panel de potencia
                       simulados      crudo          [Silver] limpio           (lee Silver)
                                                     dwh.fact_energia_dia      stat de energía
                                                     [Gold] agregado diario    (lee Gold)
```

### I2. MQTT

MQTT es un protocolo de publicación y suscripción (publish/subscribe): los clientes publican mensajes en un tema (topic) y se suscriben a filtros de tema; un intermediario los enruta sin que productor y consumidor se conozcan [26]. QoS 0 entrega como máximo una vez (puede perderse), QoS 1 al menos una vez (puede duplicarse) y QoS 2 exactamente una vez, con más sobrecarga [26][27]. Para telemetría cada 5 minutos propongo QoS 1: perder una lectura es peor que recibir un duplicado, que el ETL elimina. Los comodines son `+` (un nivel) y `#` (varios).

```
pascualbravo/solar/medellin/inversor01/p_ac_kw      (también irradiancia_wm2, temp_modulo_c)
Suscripciones:  pascualbravo/solar/+/+/p_ac_kw  |  pascualbravo/solar/medellin/#
```


### I3. Pila abierta de monitoreo IoT

| Componente | Papel | Dónde encaja PostgreSQL |
|---|---|---|
| Mosquitto | Intermediario MQTT de código abierto (versiones 5.0, 3.1.1 y 3.1) [28] | |
| Telegraf | Agente con plugins: se suscribe al intermediario y escribe en bases como InfluxDB o PostgreSQL [29] | Telegraf puede escribir directo en PostgreSQL |
| InfluxDB o TimescaleDB | Base de series de tiempo para almacenar y consultar lecturas; InfluxDB está diseñada para ese fin [40] | TimescaleDB es una extensión de PostgreSQL [39] y Grafana la soporta con `time_bucket` [3] |
| Grafana | Visualización y alertas [1] | Lee de cualquiera de las anteriores |

En SolarBI, PostgreSQL ya cumple el papel de almacenamiento para Silver y Gold, y podría recibir los mensajes de Telegraf sin cambiar los tableros.


### I4. Lotes frente a flujo continuo

Agregar de 5 minutos a un día gana simplicidad, menos almacenamiento y consultas rápidas, pero pierde detalle: una caída de 30 minutos queda oculta en una energía diaria normal y no hay aviso inmediato. El procesamiento por lotes (batch) ejecuta a intervalos, con menor costo y mayor latencia; el flujo continuo (streaming) procesa cada evento con baja latencia y mayor costo [19]. Grafana sobre la tabla de 5 minutos atiende el monitoreo cercano al tiempo real; Power BI, o un panel sobre `fact_energia_dia`, atiende la granularidad diaria.


---

## Bloque 5 · Control de versiones

### V1. Git, GitHub, `.pbix` y `.pbip`

Git es el sistema de control de versiones distribuido; GitHub es la plataforma que aloja repositorios Git y añade revisión de código, incidencias y solicitudes de cambios [31]. Un `.pbix` es un binario comprimido: Git no puede mostrar qué cambió por dentro ni fusionar versiones. El formato de proyecto `.pbip` guarda el modelo y el informe como archivos de texto en carpetas, aptos para Git, y excluye con `.gitignore` la caché local [15]. Un tablero de Grafana se versiona exportando su JSON y se despliega con aprovisionamiento por archivos [8][9].

| Término | Definición |
|---|---|
| Repositorio (repository) | Proyecto completo con el historial de cada archivo [31] |
| Commit | Instantánea guardada de los cambios preparados con `git add` [31] |
| Rama (branch) | Línea de desarrollo separada, para proponer cambios sin tocar la principal [31] |
| Solicitud de cambios (pull request) | Propuesta de integrar cambios, con discusión y revisión antes de fusionar [32] |


---

## Referencias

[1] Grafana Labs. *Grafana OSS, Cloud y Enterprise.* https://grafana.com/oss/grafana/
[2] Grafana Labs. *Licencias de Grafana (AGPLv3).* https://grafana.com/licensing/
[3] Grafana Labs. *Editor de consultas de PostgreSQL (macros y series de tiempo).* https://grafana.com/docs/grafana/latest/datasources/postgres/query-editor/
[4] Grafana Labs. *Conceptos de Grafana Alerting.* https://grafana.com/docs/grafana/latest/alerting/fundamentals/
[5] Grafana Labs. *Evaluación de reglas de alerta.* https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/
[6] Grafana Labs. *Roles y permisos.* https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/
[7] Grafana Labs. *Variables de tablero.* https://grafana.com/docs/grafana/latest/dashboards/variables/
[8] Grafana Labs. *Provisioning.* https://grafana.com/docs/grafana/latest/administration/provisioning/
[9] Grafana Labs. *Modelo JSON del tablero.* https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/view-dashboard-json-model/
[10] Microsoft. *Precios de Power BI.* https://www.microsoft.com/en-us/power-platform/products/power-bi/pricing
[11] Microsoft Learn. *Seguridad a nivel de fila (RLS) con Power BI.* https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security
[12] Microsoft Learn. *Alertas de datos en el servicio de Power BI.* https://learn.microsoft.com/en-us/power-bi/create-reports/service-set-data-alerts
[13] Microsoft Learn. *Actualización programada.* https://learn.microsoft.com/en-us/power-bi/connect-data/refresh-scheduled-refresh
[14] Microsoft Learn. *Evaluación de consultas y plegado de consultas en Power Query.* https://learn.microsoft.com/en-us/power-query/query-folding-basics
[15] Microsoft Learn. *Proyectos de Power BI Desktop (PBIP).* https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview
[16] Microsoft Learn. *DirectQuery en Power BI.* https://learn.microsoft.com/en-us/power-bi/connect-data/desktop-directquery-about
[17] DAMA International. *DAMA-DMBOK: Data Management Body of Knowledge.* https://www.dama.org/cpages/body-of-knowledge
[18] Congreso de Colombia. *Ley 1581 de 2012, por la cual se dictan disposiciones generales para la protección de datos personales.* https://www.alcaldiabogota.gov.co/sisjur/normas/Norma1.jsp?i=49981
[19] Microsoft Learn (Azure Databricks). *Arquitectura medallion (Bronze, Silver, Gold).* https://learn.microsoft.com/en-us/azure/databricks/lakehouse/medallion
[20] Amazon Web Services. *Diferencia entre ETL y ELT.* https://aws.amazon.com/compare/the-difference-between-etl-and-elt/
[21] PostgreSQL Global Development Group. *INSERT (ON CONFLICT).* https://www.postgresql.org/docs/current/sql-insert.html
[22] PostgreSQL Global Development Group. *COPY.* https://www.postgresql.org/docs/current/sql-copy.html
[23] PostgreSQL Global Development Group. *Políticas de seguridad de fila.* https://www.postgresql.org/docs/current/ddl-rowsecurity.html
[24] Apache Software Foundation. *Apache Airflow.* https://airflow.apache.org/docs/apache-airflow/stable/index.html
[25] The Kubernetes Authors. *CronJob.* https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/
[26] OASIS. *MQTT Version 5.0.* https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html
[27] HiveMQ. *MQTT Essentials, parte 6: niveles de calidad de servicio.* https://www.hivemq.com/blog/mqtt-essentials-part-6-mqtt-quality-of-service-levels/
[28] Eclipse Foundation. *Eclipse Mosquitto.* https://github.com/eclipse-mosquitto/mosquitto
[29] InfluxData. *Telegraf.* https://docs.influxdata.com/telegraf/v1/
[30] Bitol. *Open Data Contract Standard.* https://bitol-io.github.io/open-data-contract-standard/latest/
[31] GitHub Docs. *Acerca de Git.* https://docs.github.com/en/get-started/using-git/about-git
[32] GitHub Docs. *Acerca de las pull requests.* https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests
[33] U.S. Department of Energy. *Understanding Solar Photovoltaic System Performance: An Assessment of 75 Federal Photovoltaic Systems* (diciembre de 2021). https://www.energy.gov/sites/default/files/2022-01/understanding-solar-photovoltaic-system-performance.pdf
[34] Microsoft Learn. *Alertas de Power BI en informes y Fabric Activator.* https://learn.microsoft.com/en-us/fabric/real-time-intelligence/data-activator/activator-get-data-power-bi
[35] DAMA Rocky Mountain Chapter. *DMBoK Figure 14 Context Diagram: Data Governance and Stewardship.* https://damarmc.org/news/13242927
[36] Grafana Labs. *Variables globales.* https://grafana.com/docs/grafana/latest/visualizations/dashboards/variables/global-variables/
[37] Michael Kerrisk. *crontab(5), Linux manual page.* https://man7.org/linux/man-pages/man5/crontab.5.html
[38] Microsoft Learn. *Acerca del Programador de tareas.* https://learn.microsoft.com/en-us/windows/win32/taskschd/about-the-task-scheduler
[39] Timescale. *TimescaleDB.* https://github.com/timescale/timescaledb
[40] InfluxData. *Introducción a InfluxDB.* https://docs.influxdata.com/influxdb/v2/get-started/
