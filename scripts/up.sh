#!/usr/bin/env bash
# Levanta todo SolarBI en el Kubernetes de OrbStack con un solo comando.
set -euo pipefail
cd "$(dirname "$0")/.."
CTX=orbstack
K="kubectl --context $CTX"
BRONZE="$(pwd)/origen/data"

[ -f "$BRONZE/opencem-v1.0.0.sqlite" ] || { echo "Falta $BRONZE/opencem-v1.0.0.sqlite (ver README, sección Datos)"; exit 1; }
$K get nodes >/dev/null || { echo "Kubernetes de OrbStack no responde"; exit 1; }

# 1) Credenciales: se generan una vez en .env (ignorado por git) y viven en un Secret.
if [ ! -f .env ]; then
  gen() { openssl rand -base64 24 | tr -d '/+=' | cut -c1-24; }
  { echo "PG_USUARIO=solarbi_admin"; echo "PG_CLAVE=$(gen)"; echo "LECTOR_CLAVE=$(gen)"
    echo "SIM_CLAVE=$(gen)"; echo "GRAFANA_CLAVE=$(gen)"; } > .env
  chmod 600 .env
  echo "Credenciales generadas en .env"
fi

# 2) Imágenes (OrbStack comparte el motor de Docker con Kubernetes, no hace falta registro)
docker build -q -f etl/Dockerfile -t solarbi-etl:1 .
docker build -q -f simulador/Dockerfile -t solarbi-simulador:1 .

# 3) Manifiestos
$K apply -f k8s/00-namespace.yaml
$K -n solarbi create secret generic solarbi-credenciales --from-env-file=.env --dry-run=client -o yaml | $K apply -f -
$K -n solarbi delete job etl --ignore-not-found      # los Jobs son inmutables: se recrea en cada up
$K kustomize . | sed "s#__RUTA_BRONZE__#$BRONZE#" | $K apply -f -

# 4) Esperar
echo "Esperando PostgreSQL..."
$K -n solarbi rollout status statefulset/postgres --timeout=180s
echo "Esperando el ETL (carga de Silver y Gold)..."
$K -n solarbi wait --for=condition=complete job/etl --timeout=600s
$K -n solarbi rollout status deployment/grafana --timeout=180s

echo
echo "Listo."
echo "  Grafana:    http://localhost:3001   (usuario admin, clave en .env: GRAFANA_CLAVE)"
echo "  PostgreSQL: localhost:5433          (usuario lector_bi, clave en .env: LECTOR_CLAVE)"
