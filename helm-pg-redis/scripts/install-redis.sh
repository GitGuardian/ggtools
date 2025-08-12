#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/install-redis.sh <standalone> <small|medium|large> [namespace] [release]
# Defaults: namespace=gg-datastores, release=redis
# Note: We use Bitnami redis chart in standalone mode (single master with optional replicas disabled here).

TOPOLOGY=${1:-standalone}
SIZE=${2:-small}
NAMESPACE=${3:-gg-datastores}
RELEASE=${4:-redis}

if [[ "$TOPOLOGY" != "standalone" ]]; then
  echo "Redis topology currently supported: 'standalone'" >&2
  exit 1
fi

if [[ "$SIZE" != "small" && "$SIZE" != "medium" && "$SIZE" != "large" ]]; then
  echo "Size must be 'small', 'medium', or 'large'" >&2
  exit 1
fi

VALUES_FILE="$(cd "$(dirname "$0")/.." && pwd)/values/redis/${TOPOLOGY}-${SIZE}.yaml"

if [[ ! -f "$VALUES_FILE" ]]; then
  echo "Values file not found: $VALUES_FILE" >&2
  exit 1
fi

kubectl get ns "$NAMESPACE" >/dev/null 2>&1 || kubectl create ns "$NAMESPACE"

helm repo add bitnami https://charts.bitnami.com/bitnami >/dev/null 2>&1 || true
helm repo update >/dev/null

helm upgrade --install "$RELEASE" bitnami/redis \
  --namespace "$NAMESPACE" \
  --wait \
  -f "$VALUES_FILE"

echo "Redis installed: release=$RELEASE namespace=$NAMESPACE values=$VALUES_FILE"

