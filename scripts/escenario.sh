#!/usr/bin/env bash
# Cambia el escenario del simulador en vivo, SIN reconstruir imágenes: normal | falla | bateria_baja
# El valor vive en el ConfigMap solarbi-config; el CronJob lo lee en su siguiente ejecución (<= 1 minuto).
set -euo pipefail
E="${1:?uso: escenario.sh normal|falla|bateria_baja}"
kubectl --context orbstack -n solarbi patch configmap solarbi-config --type merge -p "{\"data\":{\"SIM_ESCENARIO\":\"$E\"}}"
echo "Escenario del simulador: $E (se aplica en la próxima ejecución del CronJob)"
