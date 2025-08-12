#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/install-postgres.sh <standalone|ha> <small|medium|large> [namespace] [release]
# Defaults: namespace=gg-datastores, release=pg

TOPOLOGY=${1:-standalone}
SIZE=${2:-small}
NAMESPACE=${3:-gg-datastores}
RELEASE=${4:-pg}

if [[ "$TOPOLOGY" != "standalone" && "$TOPOLOGY" != "ha" ]]; then
  echo "Topology must be 'standalone' or 'ha'" >&2
  exit 1
fi

if [[ "$SIZE" != "small" && "$SIZE" != "medium" && "$SIZE" != "large" ]]; then
  echo "Size must be 'small', 'medium', or 'large'" >&2
  exit 1
fi

VALUES_FILE="$(cd "$(dirname "$0")/.." && pwd)/values/postgres/${TOPOLOGY}-${SIZE}.yaml"

if [[ ! -f "$VALUES_FILE" ]]; then
  echo "Values file not found: $VALUES_FILE" >&2
  exit 1
fi

kubectl get ns "$NAMESPACE" >/dev/null 2>&1 || kubectl create ns "$NAMESPACE"

helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null 2>&1 || true
helm repo update >/dev/null

helm upgrade --install "$RELEASE" bitnami/postgresql \
  --namespace "$NAMESPACE" \
  --wait \
  -f "$VALUES_FILE"

echo "PostgreSQL installed: release=$RELEASE namespace=$NAMESPACE values=$VALUES_FILE"

