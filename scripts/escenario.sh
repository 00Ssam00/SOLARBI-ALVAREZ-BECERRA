#!/usr/bin/env bash
# Cambia el escenario del simulador en vivo: normal | falla | bateria_baja
set -euo pipefail
kubectl --context orbstack -n solarbi set env cronjob/simulador SIM_ESCENARIO="${1:?uso: escenario.sh normal|falla|bateria_baja}"
