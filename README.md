# SolarBI: BI contenerizado en Kubernetes para una microrred híbrida

*From inverter telemetry to actionable insights: a containerized, Kubernetes-orchestrated BI pipeline for a hybrid microgrid.*

Taller 6 de Inteligencia de Negocios, Institución Universitaria Pascual Bravo, 2026-II (docente: Ramiro Grisales Montoya).
Autor: Samuel Alvarez Becerra. Línea de profundización 7: supervisión operativa en tiempo real con Grafana sobre una bodega de datos.

Convierte un año de telemetría real de dos inversores híbridos (solar + batería + red) en un modelo dimensional en PostgreSQL (Bronze, Silver, Gold), con un ETL idempotente y medido, un tablero operativo en Grafana con alertas y un tablero analítico en Power BI. Todo el servidor corre en Kubernetes.

Informe completo: [`docs/BI_Taller6_Alvarez_Becerra.pdf`](docs/BI_Taller6_Alvarez_Becerra.pdf).

## Datos y cita obligatoria

> Bartels, T. S., Wu, R., Lu, X., Chen, Y., Lu, Y., Xia, F., Yang, H., Chen, Y., & Li, T. (2026). *OpenCEM: Multimodal photovoltaic and battery microgrid dataset with context records and sky imagery* (Version 1.0.0) [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.21436223

Licencia de los datos: CC BY 4.0. Registro: https://zenodo.org/records/21436223. **El SQLite (4,4 GB) no se sube a este repositorio.**

### Descarga y verificación

Archivos necesarios (unos 310 MB): `opencem-v1.0.0.sqlite.zst` (302,1 MB), `opencem-v1.0.0-support.zip`, `opencem-v1.0.0-SHA256SUMS.txt`, `README.md` y `LICENSE-DATA.txt`. Colócalos en `origen/` y ejecuta:

```bash
cd origen
shasum -a 256 -c opencem-v1.0.0-SHA256SUMS.txt      # debe decir OK para .sqlite.zst y support.zip
mkdir -p data && zstd -d opencem-v1.0.0.sqlite.zst -o data/opencem-v1.0.0.sqlite
```

El archivo `data/opencem-v1.0.0.sqlite` es la capa Bronze: no se modifica (el ETL lo abre en solo lectura).

## Requisitos del equipo anfitrión

macOS con [OrbStack](https://orbstack.dev) y su Kubernetes activado (`orbctl config set k8s.enable true`), `kubectl`, `make`, `openssl`, `zstd`. Unos 8 GB de RAM libres y 15 GB de disco. Contexto de kubectl esperado: `orbstack`.

## Levantar y bajar (un comando cada uno)

```bash
make up      # construye imágenes, crea el Secret, aplica manifiestos, espera al ETL y a Grafana (~55 s)
make down    # elimina el namespace (y con él el volumen)
```

Al terminar, `make up` muestra las direcciones:

| Servicio | Dirección | Credenciales |
|---|---|---|
| Grafana | http://localhost:3001 | usuario `admin`, clave `GRAFANA_CLAVE` en `.env` |
| PostgreSQL (Power BI, DBeaver) | `localhost:5433`, base `solarbi` | usuario `lector_bi`, clave `LECTOR_CLAVE` en `.env` |

`.env` lo genera `scripts/up.sh` con claves aleatorias la primera vez y **no se versiona**; `.env.ejemplo` es la plantilla.

### Demostración en vivo

```bash
kubectl --context orbstack -n solarbi get pods
kubectl --context orbstack -n solarbi delete pod postgres-0        # los datos siguen ahí
kubectl --context orbstack -n solarbi delete pod -l app=grafana    # vuelve con tablero y alertas
make escenario-falla       # el simulador reporta alarma en el inversor 2 -> alerta en ~2 min
make escenario-bateria     # el SOC cae rápido -> alerta "Batería baja" en ~4 min
make escenario-normal
```

Cambiar un umbral sin reconstruir imágenes: editar `grafana/provisioning/alerting/alertas.yaml`, luego `kubectl --context orbstack kustomize . | sed "s#__RUTA_BRONZE__#$PWD/origen/data#" | kubectl --context orbstack apply -f -` y `kubectl --context orbstack -n solarbi rollout restart deployment/grafana`. (Un `apply` también devuelve el escenario del simulador a `normal`.)

## Arquitectura

```
origen/data/opencem.sqlite (Bronze, hostPath solo lectura)
        │
   Job etl (solarbi-etl:1) ──► StatefulSet postgres ◄── CronJob simulador (cada minuto → rt.lectura)
                                  │  schemas: silver · gold · etl · rt   (PVC 5 Gi)
                                  ├──► Deployment grafana (provisioning: fuente, 2 tableros, 2 alertas)
                                  └──► Power BI / DBeaver (Service LoadBalancer :5433)
Secret solarbi-credenciales · ConfigMap solarbi-config · ConfigMaps de Grafana (kustomize)
```

| Objeto Kubernetes | Para qué |
|---|---|
| Namespace `solarbi` | aislar el proyecto |
| StatefulSet `postgres` + PVC | base que no pierde datos |
| Deployment `grafana` + provisioning | Grafana siempre disponible, sin configuración manual |
| Secret `solarbi-credenciales` | credenciales fuera del código |
| ConfigMap `solarbi-config` y de Grafana | configuración separada del código |
| Service (DNS `postgres`) | comunicación por nombre |
| Job `etl` | carga histórica una vez |
| CronJob `simulador` | datos nuevos cada minuto |
| readiness/liveness probes, requests/limits | salud y límites de recursos |
| Services LoadBalancer | acceso desde el anfitrión |

## Estructura

```
sql/            DDL (01 esquemas, 02 silver, 03 gold, 04 carga de gold, 05 vistas) y consultas/ (JSON, ventanas)
etl/            ETL SQLite → PostgreSQL (Dockerfile + etl.py)
simulador/      Simulador de streaming (Dockerfile + simulador.py)
k8s/            Manifiestos de Kubernetes; kustomization.yaml (raíz) genera los ConfigMaps de Grafana
grafana/        Provisioning (fuente, tableros, alertas); dashboards/*.json los genera scripts/gen_dashboard.py
scripts/        up.sh, down.sh, escenario.sh, evidencia.sh, capturas.py, gen_diccionario.py, build_informe.py
docs/           Informe (PDF), diccionario de datos, guía de Power BI, evidencias y capturas
powerbi/        Proyecto de Power BI en formato PBIP (versionable)
docker-compose.yml  Desarrollo local previo al clúster (cp .env.ejemplo .env && docker compose up)
```

## Modelo (resumen)

Constelación de hechos: `fact_lectura_5min` (grano: inversor × 5 min), `fact_energia_dia` (inversor × día), `fact_evento_alarma` (episodio de alarma), `fact_contexto` (anotación). Dimensiones: `dim_fecha`, `dim_hora`, `dim_inversor` y tres propias (`dim_estado_operativo`, `dim_alarma`, `dim_tipo_contexto`). Detalle, matriz de bus y diccionario: ver el informe y [`docs/diccionario_datos.md`](docs/diccionario_datos.md).

## Limitaciones declaradas

El significado de los bits de alarma y de los códigos de estado no está documentado por OpenCEM; las etiquetas son supuestos. La tarifa (790,49 COP/kWh, referencia pública de EPM estrato 3) es un parámetro editable, no la del contrato. El contexto se carga minimizado (Ley 1581). Ver informe, anexo 3.
