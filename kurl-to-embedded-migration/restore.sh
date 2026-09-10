#!/bin/bash

set -euo pipefail

usage() {
  echo "Usage: $0 -n <embedded-namespace>"
  echo ""
  echo "  Drops the embedded cluster DB content and restores it from db.sql.gz."
  echo "  Expects: db.sql.gz in the current directory"
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
[[ -f "db.sql.gz" ]]   || { echo "Error: db.sql.gz not found."; exit 1; }

echo "==> Dropping DB content..."
kubectl exec -i --namespace "$NAMESPACE" postgresql-0 -- \
  bash -c "PGPASSWORD=\$POSTGRES_PASSWORD psql -U \$POSTGRES_USER -d \$POSTGRES_DB" <<'EOF'
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO PUBLIC;
EOF

echo "==> Restoring DB from db.sql.gz..."
postgres_restore_cmd="PGPASSWORD=\$POSTGRES_PASSWORD psql -U \$POSTGRES_USER -d \$POSTGRES_DB"
gunzip -c db.sql.gz | \
  kubectl exec -i --namespace "$NAMESPACE" postgresql-0 -- bash -c "set -ueo pipefail ; $postgres_restore_cmd"

echo "Done."
