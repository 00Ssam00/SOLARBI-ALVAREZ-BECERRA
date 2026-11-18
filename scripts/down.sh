#!/usr/bin/env bash
# Baja todo. Con --datos también borra el volumen de PostgreSQL.
set -euo pipefail
K="kubectl --context orbstack"
$K delete namespace solarbi --ignore-not-found --wait=true
echo "Namespace solarbi eliminado (el PVC se elimina con él)."
