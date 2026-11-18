#!/usr/bin/env bash
# Genera la evidencia del clúster (kubectl get/describe) y la prueba de resiliencia en docs/evidencia/.
set -uo pipefail
cd "$(dirname "$0")/.."
K="kubectl --context orbstack -n solarbi"
E=docs/evidencia
mkdir -p $E
set -a; . ./.env; set +a
cuenta() { docker run --rm -e PGPASSWORD="$LECTOR_CLAVE" postgres:17-alpine psql -h host.docker.internal -p 5433 -U lector_bi -d solarbi -tAc "SELECT (SELECT count(*) FROM gold.fact_lectura_5min) || ' lecturas 5min, ' || (SELECT count(*) FROM gold.fact_energia_dia) || ' dias, ' || (SELECT count(*) FROM gold.fact_evento_alarma) || ' eventos, ' || (SELECT count(*) FROM gold.fact_contexto) || ' anotaciones'"; }
{ echo '$ kubectl get all,pvc,configmap,secret -n solarbi'; $K get all,pvc,configmap,secret; } > $E/01_kubectl_get.txt 2>&1
{ echo '$ kubectl describe statefulset/postgres'; $K describe statefulset/postgres; echo; echo '$ kubectl describe deployment/grafana'; $K describe deployment/grafana; } > $E/02_kubectl_describe.txt 2>&1
{ echo '$ kubectl describe cronjob/simulador'; $K describe cronjob/simulador; echo; echo '$ kubectl describe job/etl'; $K describe job/etl; echo; echo '$ kubectl logs job/etl'; $K logs job/etl -c etl; } > $E/03_etl_y_simulador.txt 2>&1
{
  echo "=== PRUEBA 1: se elimina el pod de PostgreSQL ==="
  echo "Antes:   $(cuenta)"
  echo '$ kubectl delete pod postgres-0'; $K delete pod postgres-0 --wait=true
  $K wait --for=condition=ready pod/postgres-0 --timeout=120s
  sleep 5
  echo "Despues: $(cuenta)"
  echo
  echo "=== PRUEBA 2: se elimina el pod de Grafana ==="
  echo '$ kubectl delete pod -l app=grafana'; $K delete pod -l app=grafana --wait=true
  $K rollout status deployment/grafana --timeout=120s
  sleep 5
  echo "Dashboards provisionados tras el reinicio:"
  curl -s -u "admin:$GRAFANA_CLAVE" "http://localhost:3001/api/search?query=SolarBI" | python3 -c "import sys,json;[print(' -',r['title']) for r in json.load(sys.stdin) if r['type']=='dash-db']"
  echo "Reglas de alerta tras el reinicio:"
  curl -s -u "admin:$GRAFANA_CLAVE" http://localhost:3001/api/v1/provisioning/alert-rules | python3 -c "import sys,json;[print(' -',r['title']) for r in json.load(sys.stdin)]"
} > $E/04_resiliencia.txt 2>&1
echo "Evidencia escrita en $E"
