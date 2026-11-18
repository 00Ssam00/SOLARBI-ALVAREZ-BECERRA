# Diccionario de datos

Generado por `scripts/gen_diccionario.py` desde la base en ejecución. PK = llave primaria, FK = llave foránea.


## gold.dim_alarma

DIMENSIÓN PROPIA: catálogo de firmas de alarma (arreglo JSON de 8 palabras) con sus bits activos.  
**Grano:** Una fila por firma distinta.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| alarma_id | smallint NOT NULL | PK | derivado | hash de la firma (0 = sin alarma) |
| firma | jsonb |  | status.sysalarmflag | JSON de 8 palabras, castear a jsonb |
| palabra | smallint |  | derivado | índice de la primera palabra distinta de 0 |
| valor | integer |  | derivado | valor de esa palabra |
| bits_activos | ARRAY |  | derivado | bits en 1, con índice global palabra*16 + bit |
| severidad | text NOT NULL |  | supuesto | toda alarma activa se trata como 'aviso': el significado de los bits no está documentado |
| descripcion | text NOT NULL |  | derivado | texto con los bits activos |

## gold.dim_estado_operativo

DIMENSIÓN PROPIA: estado operativo derivado de startupstatus, outstatus y chgstatus. No existe como tal en la fuente.  
**Grano:** Una fila por combinación observada.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| estado_id | smallint NOT NULL | PK | derivado | startup*100 + out*10 + chg; 9 = dato ausente |
| startupstatus | smallint |  | status.startupstatus | copia |
| outstatus | smallint |  | status.outstatus | copia |
| chgstatus | smallint |  | status.chgstatus | copia |
| categoria | text NOT NULL |  | derivado (supuesto) | salida 0/1/2 y carga 1: etiquetas no documentadas por OpenCEM |
| descripcion | text NOT NULL |  | derivado | texto con los tres códigos |

## gold.dim_fecha

Calendario en hora local del sitio (Asia/Shanghai). Dimensión de fechas propia con jerarquía año > trimestre > mes > día.  
**Grano:** Una fila por día.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| fecha_id | integer NOT NULL | PK | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| fecha | date NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| anio | smallint NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| trimestre | smallint NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| mes | smallint NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| nombre_mes | text NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| dia_mes | smallint NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| dia_semana | smallint NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| nombre_dia | text NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| semana_iso | smallint NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| es_fin_semana | boolean NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |
| estacion | text NOT NULL |  | Calendario generado (sin fuente) | generate_series 2025-07-01 a 2026-07-31; atributos derivados de la fecha |

## gold.dim_hora

Hora local del día con franja y marca de hora solar.  
**Grano:** Una fila por hora (0 a 23).

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| hora_id | smallint NOT NULL | PK | Calendario generado (sin fuente) | franja: madrugada <6, mañana <12, tarde <18, noche; hora solar 6 a 17 |
| franja | text NOT NULL |  | Calendario generado (sin fuente) | franja: madrugada <6, mañana <12, tarde <18, noche; hora solar 6 a 17 |
| es_hora_solar | boolean NOT NULL |  | Calendario generado (sin fuente) | franja: madrugada <6, mañana <12, tarde <18, noche; hora solar 6 a 17 |

## gold.dim_inversor

Inversores híbridos del sitio. Dimensión de cambio lento tipo 2 candidata (ver informe, SCD).  
**Grano:** Una fila por inversor.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| inversor_id | smallint NOT NULL | PK | analog_measurements.inverter | clave natural |
| nombre | text NOT NULL |  | derivado | 'Inversor ' || id |
| primera_lectura | timestamp with time zone |  | silver.lectura_5min.bloque_ts | MIN por inversor |
| ultima_lectura | timestamp with time zone |  | silver.lectura_5min.bloque_ts | MAX por inversor |
| activo_al_cierre | boolean |  | derivado | última lectura a menos de 1 día del final del registro |

## gold.dim_tipo_contexto

DIMENSIÓN PROPIA: tipo de anotación de contexto (fuente + tipo) con una categoría de negocio.  
**Grano:** Una fila por (fuente, tipo).

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| tipo_contexto_id | smallint NOT NULL | PK | context.value (JSON): source y context_type | categoria por fuente: cómputo, sistema, derivado, calendario |
| fuente | text NOT NULL |  | context.value (JSON): source y context_type | categoria por fuente: cómputo, sistema, derivado, calendario |
| context_type | text NOT NULL |  | context.value (JSON): source y context_type | categoria por fuente: cómputo, sistema, derivado, calendario |
| categoria | text NOT NULL |  | context.value (JSON): source y context_type | categoria por fuente: cómputo, sistema, derivado, calendario |

## gold.fact_contexto

P4 Contexto operativo: anotaciones del registro de contexto, minimizadas.  
**Grano:** Una anotación del registro de contexto.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| contexto_id | integer NOT NULL | PK | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |
| tipo_contexto_id | smallint NOT NULL | FK → gold.dim_tipo_contexto(tipo_contexto_id) | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |
| inversor_id | smallint | FK → gold.dim_inversor(inversor_id) | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |
| fecha_id | integer NOT NULL | FK → gold.dim_fecha(fecha_id) | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |
| hora_id | smallint NOT NULL | FK → gold.dim_hora(hora_id) | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |
| inicio_ts | timestamp with time zone NOT NULL |  | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |
| fin_ts | timestamp with time zone NOT NULL |  | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |
| duracion_s | double precision NOT NULL |  | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |
| cpu_cores | smallint |  | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |
| esfuerzo | text |  | context (id, start, end, value) | value (JSON) minimizado; inversor_id = value.inverter; cpu_cores y esfuerzo = value.cpu_cores_active y llm_estimated_task_effort |

## gold.fact_energia_dia

P2 Balance energético: energía integrada por día y contraste contra el contador del equipo.  
**Grano:** Un inversor en un día local.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| inversor_id | smallint NOT NULL | PK FK → gold.dim_inversor(inversor_id) | Bronze (SQLite) | copia con tipo ajustado |
| fecha_id | integer NOT NULL | PK FK → gold.dim_fecha(fecha_id) | Bronze (SQLite) | copia con tipo ajustado |
| pv_kwh_integrado | real |  | silver.lectura_5min.e_pv_wh | SUM por día local / 1000 |
| pv_kwh_equipo | real |  | statistics.pvgeneratenergytoday [kWh] | MAX por día local (contador del inversor, se reinicia a medianoche) |
| pv_dif_pct | real |  | derivado | (integrado - equipo) / equipo |
| consumo_kwh_integrado | real |  | silver.lectura_5min.e_carga_wh | SUM por día / 1000 |
| consumo_kwh_equipo | real |  | statistics.usedenergytoday [kWh] | MAX por día local |
| red_kwh_integrado | real |  | silver.lectura_5min.e_red_wh | SUM por día / 1000 |
| carga_bat_kwh_equipo | real |  | statistics.batchgenergytoday [kWh] | MAX por día local |
| descarga_bat_kwh_equipo | real |  | statistics.batdischgenergytoday [kWh] | MAX por día local |
| horas_con_dato | real |  | silver.lectura_5min.segundos_cubiertos | SUM / 3600 |
| cobertura_dia | real |  | derivado | horas_con_dato / 24, tope 1 (es la disponibilidad del registro) |

## gold.fact_evento_alarma

P3 Eventos de alarma: episodios de una misma firma de alarma sin interrupción.  
**Grano:** Un episodio (inversor, inicio).

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| inversor_id | smallint NOT NULL | PK FK → gold.dim_inversor(inversor_id) | status.sysalarmflag | episodio = racha de lecturas con la misma firma distinta de cero; duracion_s = fin - inicio |
| inicio_ts | timestamp with time zone NOT NULL | PK | status.sysalarmflag | episodio = racha de lecturas con la misma firma distinta de cero; duracion_s = fin - inicio |
| fin_ts | timestamp with time zone NOT NULL |  | status.sysalarmflag | episodio = racha de lecturas con la misma firma distinta de cero; duracion_s = fin - inicio |
| fecha_id | integer NOT NULL | FK → gold.dim_fecha(fecha_id) | status.sysalarmflag | episodio = racha de lecturas con la misma firma distinta de cero; duracion_s = fin - inicio |
| hora_id | smallint NOT NULL | FK → gold.dim_hora(hora_id) | status.sysalarmflag | episodio = racha de lecturas con la misma firma distinta de cero; duracion_s = fin - inicio |
| alarma_id | smallint NOT NULL | FK → gold.dim_alarma(alarma_id) | status.sysalarmflag | episodio = racha de lecturas con la misma firma distinta de cero; duracion_s = fin - inicio |
| duracion_s | double precision NOT NULL |  | status.sysalarmflag | episodio = racha de lecturas con la misma firma distinta de cero; duracion_s = fin - inicio |
| n_lecturas | integer NOT NULL |  | status.sysalarmflag | episodio = racha de lecturas con la misma firma distinta de cero; duracion_s = fin - inicio |

## gold.fact_lectura_5min

P1 Operación: variables eléctricas promediadas por bloque de 5 minutos.  
**Grano:** Un inversor en un bloque de 5 minutos UTC.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| inversor_id | smallint NOT NULL | PK FK → gold.dim_inversor(inversor_id) | analog_measurements.inverter | FK a dim_inversor |
| bloque_ts | timestamp with time zone NOT NULL | PK | analog_measurements.read_ts | FLOOR(read_ts / 300) * 300, en UTC |
| fecha_id | integer NOT NULL | FK → gold.dim_fecha(fecha_id) | derivado de bloque_ts | fecha local Asia/Shanghai (yyyymmdd) |
| hora_id | smallint NOT NULL | FK → gold.dim_hora(hora_id) | derivado de bloque_ts | hora local Asia/Shanghai |
| estado_id | smallint | FK → gold.dim_estado_operativo(estado_id) | status.startupstatus/outstatus/chgstatus | valor de la última lectura del bloque |
| alarma_id | smallint | FK → gold.dim_alarma(alarma_id) | status.sysalarmflag | firma distinta de cero más alta del bloque; 0 si no hay |
| n_lecturas | integer NOT NULL |  | COUNT(*) | lecturas válidas en el bloque |
| cobertura | real NOT NULL |  | segundos cubiertos / 300 | cada lectura cubre min(dt hasta la siguiente, 60 s); tope 1 |
| pv_w_prom | real |  | analog_measurements.pv1power [W] | AVG; valores fuera de 0 a 8000 se anulan (R01) |
| pv_w_max | real |  | analog_measurements.pv1power [W] | MAX |
| carga_w_prom | real |  | analog_measurements.outsumw [W] | AVG; fuera de 0 a 20000 se anula (R05) |
| red_w_prom | real |  | analog_measurements.linepowerw_a [W] | AVG; potencia tomada de la red; fuera de -50 a 20000 se anula (R06) |
| inyec_w_prom | real |  | analog_measurements.gridpowerw_a [W] | AVG; salida hacia la red (supuesto) |
| bat_w_prom | real |  | analog_measurements.battchgpower [W] | AVG |
| soc_prom | real |  | analog_measurements.battsoc [%] | AVG; fuera de 0 a 100 se anula (R02) |
| soc_min | real |  | analog_measurements.battsoc [%] | MIN |
| bat_v_prom | real |  | analog_measurements.battvolt [V] | AVG; fuera de 30 a 80 se anula (R03) |
| bat_a_prom | real |  | analog_measurements.battcurr [A] | AVG; positivo = descarga |
| temp_max_c | real |  | analog_measurements.temper1 [°C] | MAX; fuera de -20 a 120 se anula (R04) |
| e_pv_wh | real |  | analog_measurements.pv1power | SUM(W * dt) / 3600, dt = min(siguiente - actual, 60 s) |
| e_carga_wh | real |  | analog_measurements.outsumw | SUM(W * dt) / 3600 |
| e_red_wh | real |  | analog_measurements.linepowerw_a | SUM(W * dt) / 3600 |
| n_alarmas | integer NOT NULL |  | status.sysalarmflag | lecturas del bloque con alguna palabra distinta de 0 |

## gold.parametro

Parámetros de negocio editables (tarifa, umbrales).  
**Grano:** Una fila por parámetro.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| clave | text NOT NULL | PK | definido por el equipo | se edita sin tocar el código |
| valor | numeric NOT NULL |  | definido por el equipo | se edita sin tocar el código |
| unidad | text NOT NULL |  | definido por el equipo | se edita sin tocar el código |
| fuente | text NOT NULL |  | definido por el equipo | se edita sin tocar el código |

## rt.lectura

Lecturas en tiempo real escritas por el simulador (alimentan Grafana).  
**Grano:** Inversor y marca de tiempo.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| ts | timestamp with time zone NOT NULL | PK | Bronze (SQLite) | copia con tipo ajustado |
| inversor_id | smallint NOT NULL | PK | Bronze (SQLite) | copia con tipo ajustado |
| pv_w | real |  | Bronze (SQLite) | copia con tipo ajustado |
| carga_w | real |  | Bronze (SQLite) | copia con tipo ajustado |
| red_w | real |  | Bronze (SQLite) | copia con tipo ajustado |
| soc | real |  | Bronze (SQLite) | copia con tipo ajustado |
| bat_v | real |  | Bronze (SQLite) | copia con tipo ajustado |
| temp_c | real |  | Bronze (SQLite) | copia con tipo ajustado |
| alarma | boolean NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |
| origen | text NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |

## silver.contexto

Anotaciones de contexto con JSON minimizado (lista blanca de claves).  
**Grano:** Una anotación.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| contexto_id | integer NOT NULL | PK | Bronze (SQLite) | copia con tipo ajustado |
| registrado_ts | timestamp with time zone |  | Bronze (SQLite) | copia con tipo ajustado |
| inicio_ts | timestamp with time zone NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |
| fin_ts | timestamp with time zone NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |
| valor | jsonb NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |

## silver.energia_dia_equipo

Máximos diarios de los contadores del propio inversor (tabla statistics).  
**Grano:** Inversor y día local.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| inversor_id | smallint NOT NULL | PK | Bronze (SQLite) | copia con tipo ajustado |
| fecha_local | date NOT NULL | PK | Bronze (SQLite) | copia con tipo ajustado |
| pv_kwh | real |  | Bronze (SQLite) | copia con tipo ajustado |
| carga_bat_kwh | real |  | Bronze (SQLite) | copia con tipo ajustado |
| descarga_bat_kwh | real |  | Bronze (SQLite) | copia con tipo ajustado |
| consumo_kwh | real |  | Bronze (SQLite) | copia con tipo ajustado |
| n_lecturas | integer NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |

## silver.episodio_alarma

Episodios de alarma construidos con una máquina de estados sobre status.  
**Grano:** Inversor e inicio del episodio.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| inversor_id | smallint NOT NULL | PK | Bronze (SQLite) | copia con tipo ajustado |
| inicio_ts | timestamp with time zone NOT NULL | PK | Bronze (SQLite) | copia con tipo ajustado |
| fin_ts | timestamp with time zone NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |
| firma | jsonb NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |
| n_lecturas | integer NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |

## silver.lectura_5min

Lecturas validadas y agregadas a 5 minutos (Silver).  
**Grano:** Inversor y bloque de 5 minutos.

| Columna | Tipo | Llave | Origen (linaje) | Regla de transformación |
|---|---|---|---|---|
| inversor_id | smallint NOT NULL | PK | Bronze (SQLite) | copia con tipo ajustado |
| bloque_ts | timestamp with time zone NOT NULL | PK | Bronze (SQLite) | copia con tipo ajustado |
| n_lecturas | integer NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |
| pv_w_prom | real |  | Bronze (SQLite) | copia con tipo ajustado |
| pv_w_max | real |  | Bronze (SQLite) | copia con tipo ajustado |
| carga_w_prom | real |  | Bronze (SQLite) | copia con tipo ajustado |
| red_w_prom | real |  | Bronze (SQLite) | copia con tipo ajustado |
| inyec_w_prom | real |  | Bronze (SQLite) | copia con tipo ajustado |
| bat_w_prom | real |  | Bronze (SQLite) | copia con tipo ajustado |
| soc_prom | real |  | Bronze (SQLite) | copia con tipo ajustado |
| soc_min | real |  | Bronze (SQLite) | copia con tipo ajustado |
| bat_v_prom | real |  | Bronze (SQLite) | copia con tipo ajustado |
| bat_a_prom | real |  | Bronze (SQLite) | copia con tipo ajustado |
| temp_max_c | real |  | Bronze (SQLite) | copia con tipo ajustado |
| e_pv_wh | real |  | Bronze (SQLite) | copia con tipo ajustado |
| e_carga_wh | real |  | Bronze (SQLite) | copia con tipo ajustado |
| e_red_wh | real |  | Bronze (SQLite) | copia con tipo ajustado |
| segundos_cubiertos | real NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |
| startupstatus | smallint |  | Bronze (SQLite) | copia con tipo ajustado |
| outstatus | smallint |  | Bronze (SQLite) | copia con tipo ajustado |
| chgstatus | smallint |  | Bronze (SQLite) | copia con tipo ajustado |
| n_alarmas | integer NOT NULL |  | Bronze (SQLite) | copia con tipo ajustado |
| alarma_firma | text |  | Bronze (SQLite) | copia con tipo ajustado |
