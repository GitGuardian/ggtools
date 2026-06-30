#!/bin/bash

set -euo pipefail

usage() {
  echo "Usage: $0 -n <kurl-namespace>"
  echo ""
  echo "  Backs up KOTS config, PostgreSQL DB, and DJANGO_SECRET_KEY from a kURL install."
  echo "  Outputs: config-backup.yaml  db.sql.gz  DJANGO.key"
  exit 1
}

NAMESPACE=""
while getopts "n:h" opt; do
  case $opt in
    n) NAMESPACE="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

[[ -z "$NAMESPACE" ]] && { echo "Error: -n is required."; usage; }

echo "==> Backing up KOTS config..."
kubectl kots get config --namespace "$NAMESPACE" --decrypt > config-backup.yaml

echo "==> Backing up PostgreSQL database..."
postgres_backup_cmd="PGPASSWORD=\$POSTGRES_PASSWORD pg_dump -U \$POSTGRES_USER -d \$POSTGRES_DB --create --clean --if-exists | gzip"
kubectl exec --namespace "$NAMESPACE" --quiet postgresql-0 -- \
  bash -c "set -ueo pipefail ; $postgres_backup_cmd" > db.sql.gz

echo "==> Saving DJANGO_SECRET_KEY..."
kubectl get secrets gim-secrets --namespace "$NAMESPACE" \
  -o jsonpath='{.data.DJANGO_SECRET_KEY}' | base64 -d > DJANGO.key

echo "Done. Artifacts: config-backup.yaml  db.sql.gz  DJANGO.key"
