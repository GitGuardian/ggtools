#!/usr/bin/env bash

#####
#
# -- Restore the GitGuardian PostgreSQL Embedded DB using kubectl --
#
# The script will execute the following steps:
#   - Check the provided backup file
#   - Restore de PostgresSQL backup
#   - Run migrations with the new application version
#####

#set -x
set -ueo pipefail

# --- Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

KUBECTL_ARGS=""
NAMESPACE=""
INPUT_FILE=""
ERROR_LOG_FILE=$(mktemp)

REPLICATED_APP="gitguardian"
FORCE="false"

# --- Functions
function cleanup() {
  if [[ -f "$ERROR_LOG_FILE" ]]; then
    rm -f "$ERROR_LOG_FILE"
  fi
}

function print_error() {
  if [[ -s "$ERROR_LOG_FILE" ]]; then
    echo
    echo -e "\033[1;31mERROR:\033[0m"
    echo "-------"
    cat "$ERROR_LOG_FILE"
  fi
}

function _exit() {
  exit_code=$?
  if [[ ${exit_code} -gt 0 ]]; then
    echo_ko
  fi
  print_error
  cleanup
  echo
}

function echo_step() {
  echo -en "\n=> "
  echo $@
}

function echo_ok() {
  echo -e "\033[1;32mOK\033[0m"
}

function echo_ko() {
  echo -e "\033[1;31mKO\033[0m "
}

function echo_info() {
  echo -en "\033[1;32m[INFO]\033[0m "
  echo $@
}

function echo_error() {
  echo -en "\033[1;31m[ERROR]\033[0m " >&2
  echo $@ >&2
}

function usage() {
  cat <<USAGE

Usage:
    $(basename $0) [OPTIONS]

Description:
    Restore the GitGuardian PostgreSQL database.

OPTIONS:

    --context <string>
        The name of the kubeconfig context to use

    --kubeconfig <string>
        Path to the kubeconfig file to use for CLI requests

    -n | --namespace <string>
        Specify the kubernetes namespace (Mandatory)

    -i | --input <path>
        Specify the backup inpu file to use to restore database

    --force
        Force restore (even if DB was already restored)

    -h | --help
        Display this help message
USAGE
}

# --- Options
while (("$#")); do
  case "$1" in
  -n | --namespace)
    NAMESPACE=$2
    KUBECTL_ARGS="${KUBECTL_ARGS} $1 $NAMESPACE"
    shift 2
    ;;
  --context | --kubeconfig)
    KUBECTL_ARGS="${KUBECTL_ARGS} $1=$2"
    shift 2
    ;;
  -i | --input)
    shift
    INPUT_FILE="$1"
    shift
    ;;
  --force)
    shift
    FORCE="true"
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  -*)
    echo_error "Unknown flag $1"
    exit 1
    ;;
  *) # positional argument
    break
    ;;
  esac
done

if [[ -z "$NAMESPACE" ]]; then
  usage
  echo
  echo_error "You must specify the namespace"
  exit 1
fi

if [[ ! -s "$INPUT_FILE" ]]; then
  usage
  echo
  echo_error "Input file ${INPUT_FILE} doesn't exist"
  exit 1
fi

# --- Main
trap _exit EXIT
trap 'exit 1' ERR

if [[ "$FORCE" == "false" ]]; then
  echo_step "Check backup status"
  status=$(kubectl $KUBECTL_ARGS get configmap postgresql-backup --output jsonpath="{.data.status}")
  if [[ "$status" == "" ]]; then
    echo_error "Failed to retrieve the backup status from 'postgresql-backup"
    exit 1
  fi
  echo_ok
fi

if [[ "$FORCE" == "true" ]] || [[ "$status" == "completed" ]]; then
  echo_step "Check backup file"
  secret_hash=$(kubectl $KUBECTL_ARGS get configmap postgresql-backup --output jsonpath="{.data.hash}")
  if [[ -z "$secret_hash" ]]; then
    echo "Unable to retrieve the backup file hash from postgresql-backup configMap"
    exit 1
  fi
  if [[ "$OS" == "darwin" ]]; then
    hash=$(md5 -q $INPUT_FILE)
  else
    hash=$(md5sum $INPUT_FILE | awk '{print $1}')
  fi

  if [[ "$secret_hash" != "$hash" ]]; then
    echo "Checksum mismatch error"
    echo "expected file hash : ${secret_hash}"
    echo "provided file hash : ${hash}"
    exit 1
  fi
  echo_ok

  deployments=()
  while IFS= read -r line; do
      deployments+=("$line")
  done < <(kubectl $KUBECTL_ARGS get deployment \
      --selector="app.kubernetes.io/name=${REPLICATED_APP}" \
      --output=name 2>$ERROR_LOG_FILE)

  if [[ "${#deployments[@]}" -gt 0 ]]; then
    echo_step "Scale down GitGuardian deployments"
      for deployment in "${deployments[@]}"; do
        # Get the current replicas
        replicas=$(kubectl $KUBECTL_ARGS \
          get $deployment \
          --output jsonpath="{.status.replicas}")
        # Scale down
        kubectl $KUBECTL_ARGS \
          scale $deployment \
          --timeout=3m \
          --replicas=0 2>$ERROR_LOG_FILE
        # Add replicas annotation
        kubectl $KUBECTL_ARGS \
          annotate --overwrite $deployment \
          replicas="${replicas}" >/dev/null 2>$ERROR_LOG_FILE
      done
    echo_ok

    echo_step "Waiting for all GitGuardian pods to be deleted"
      for deployment in "${deployments[@]}"; do
        kubectl $KUBECTL_ARGS \
          wait --for=delete pod \
          --field-selector="status.phase!=Succeeded,status.phase!=Failed" \
          --selector="kots.io/app-slug=${REPLICATED_APP}, app.kubernetes.io/name=${REPLICATED_APP}" \
          --timeout=3m 2>$ERROR_LOG_FILE
      done
    echo_ok
  fi

  echo_step "Retrieve PostgreSQL pod"
  postgres_pod_selector="app.kubernetes.io/name=postgres, app.kubernetes.io/instance=postgresql"
  pod=$(kubectl $KUBECTL_ARGS get pod \
    --field-selector="status.phase=Running" \
    --selector="$postgres_pod_selector" \
    --output=name 2>$ERROR_LOG_FILE | head -1)
  if [[ -z "$pod" ]]; then
    echo "No running PostgreSQL pod found" >$ERROR_LOG_FILE
    exit 1
  fi
  echo_ok

  echo_step "Restore the GitGuardian DB"
  sleep 20
  postgres_restore_cmd="PGPASSWORD=\$POSTGRES_PASSWORD psql -U \$POSTGRES_USER -d postgres"
  gunzip -c ${INPUT_FILE} | \
    kubectl $KUBECTL_ARGS \
      exec -i $pod -- \
      bash -c "set -ueo pipefail ; $postgres_restore_cmd" >/dev/null 2>$ERROR_LOG_FILE
  if [[ -s "$ERROR_LOG_FILE" ]]; then
    exit 1
  fi
  echo_ok

  echo_step "Update backup status"
  kubectl $KUBECTL_ARGS \
    patch configmap postgresql-backup \
    --type=json \
    --patch='[{ "op": "replace", "path": "/data/status", "value": "restored" }]' >/dev/null 2>$ERROR_LOG_FILE
  echo_ok

  if [[ "${#deployments[@]}" -gt 0 ]]; then
    echo_step "Scale up GitGuardian deployments"
    for deployment in "${deployments[@]}"; do
      # Retrive replicas from annotations
      replicas=$(kubectl $KUBECTL_ARGS \
        get $deployment \
        --output jsonpath="{.metadata.annotations.replicas}" \
      )
      # Scale up
      kubectl $KUBECTL_ARGS \
        scale $deployment \
        --timeout=3m \
        --replicas=${replicas:-1} 2>$ERROR_LOG_FILE
      # Remove replicas annotation
      kubectl $KUBECTL_ARGS \
        patch $deployment \
        --type=json \
        --patch='[{"op":"remove","path":"/metadata/annotations/replicas"}]' >/dev/null 2>$ERROR_LOG_FILE
    done
    echo_ok

    echo_step "Waiting for GitGuardian application to be ready"
    kubectl $KUBECTL_ARGS \
      wait --for=condition=ready pod \
      --field-selector="status.phase!=Succeeded,status.phase!=Failed" \
      --selector="app.kubernetes.io/name=${REPLICATED_APP}" \
      --timeout=3m 2>$ERROR_LOG_FILE
    echo_ok
  fi
else
  echo
  echo "PostgreSQL database has already been restored"
  echo
fi

echo_step "Migrate GitGuardian database"
# get internal-api pod
pod=$(kubectl $KUBECTL_ARGS get pod \
  --field-selector="status.phase=Running" \
  --selector="app.kubernetes.io/component=internal-api" \
  --output=name 2>$ERROR_LOG_FILE | head -1)
if [[ -z "$pod" ]]; then
  echo "No running internal-api pod found" >$ERROR_LOG_FILE
  exit 1
fi
kubectl $KUBECTL_ARGS \
  exec $pod -- \
    python manage.py migrate
echo_ok

echo
echo "DB was successfully restored from ${INPUT_FILE}"
