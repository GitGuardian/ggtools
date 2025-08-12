#!/usr/bin/env bash
set -euo pipefail

# Usage: ./scripts/uninstall.sh [namespace] [pg-release] [redis-release]
# Defaults: namespace=gg-datastores, pg-release=pg, redis-release=redis

NAMESPACE=${1:-gg-datastores}
PG_RELEASE=${2:-pg}
REDIS_RELEASE=${3:-redis}

set +e
helm uninstall "$PG_RELEASE" -n "$NAMESPACE" 2>/dev/null || true
helm uninstall "$REDIS_RELEASE" -n "$NAMESPACE" 2>/dev/null || true
set -e

echo "Uninstalled releases (if existed) from namespace=$NAMESPACE: $PG_RELEASE, $REDIS_RELEASE"

