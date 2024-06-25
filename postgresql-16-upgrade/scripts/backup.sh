#!/usr/bin/env bash

#####
#
# -- Back up the GitGuardian PostgreSQL Embedded DB using kubectl --
#
# The script will execute the following steps:
#   - Retrieve the currently deployed GitGuardian application version
#   - Create a backup of the GitGuardian application PostgresSQL database
#   - Store backup informations (hash, date, status, version) in a configMap called 'postgresql-backup'
#
#####

#set -x
set -ueo pipefail

# --- Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"

KUBECTL_ARGS=""
NAMESPACE=""
OUTPUT_FILE=""
ERROR_LOG_FILE=$(mktemp)

REPLICATED_APP="gitguardian"

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
    Backup the GitGuardian PostgreSQL DB.
    The dump file is compressed using gzip.

OPTIONS:

    --context <string>
        The name of the kubeconfig context to use

    --kubeconfig <string>
        Path to the kubeconfig file to use for CLI requests

    -n | --namespace <string>
        Specify the kubernetes namespace (Mandatory)

    -o | --output <path>
        Specify the backup output file

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
  -o | --output)
    shift
    OUTPUT_FILE="$1"
    shift
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

if [[ -z "$OUTPUT_FILE" ]]; then
  usage
  echo
  echo_error "You must specify the output file"
  exit 1
fi

# --- Main
trap _exit EXIT
trap 'exit 1' ERR

echo_step "Retrieve GitGuardian version"
gitguardian_version=$(kubectl $KUBECTL_ARGS get configmap gim-config --output jsonpath="{.data.APP_VERSION}")
if [[ -z "$gitguardian_version" ]]; then
  echo "Unable to retrieve the current GitGuardian version"
  exit 1
fi
echo_ok

echo_step "Retrieve PostgreSQL pod"
postgres_pod_selector="kots.io/app-slug=${REPLICATED_APP}, app.kubernetes.io/name=postgresql, app.kubernetes.io/component=primary"
pod=$(kubectl $KUBECTL_ARGS get pod \
  --field-selector="status.phase=Running" \
  --selector="$postgres_pod_selector" \
  --output=name 2>$ERROR_LOG_FILE | head -1)
if [[ -z "$pod" ]]; then
  echo "No running PostgreSQL pod found" >$ERROR_LOG_FILE
  exit 1
fi
echo_ok

echo_step "Create a backup of the GitGuardian database"
postgres_backup_cmd="PGPASSWORD=\$POSTGRES_POSTGRES_PASSWORD pg_dump -U postgres -d \$POSTGRES_DATABASE --create --clean --if-exists | gzip"
kubectl $KUBECTL_ARGS \
  exec --quiet $pod -- \
  sh -c "$postgres_backup_cmd" >"$OUTPUT_FILE" 2>$ERROR_LOG_FILE
if [[ -s "$ERROR_LOG_FILE" ]]; then
  exit 1
fi
echo_ok

echo_step "Store backup informations"
# Generate backup file hash
if [[ "$OS" == "darwin" ]]; then
  hash=$(md5 -q $OUTPUT_FILE)
else
  hash=$(md5sum $OUTPUT_FILE | awk '{print $1}')
fi

kubectl $KUBECTL_ARGS \
  create configmap postgresql-backup \
  --save-config=true \
  --dry-run=client \
  --from-literal=version="$gitguardian_version" \
  --from-literal=hash="$hash" \
  --from-literal=status="completed" \
  -o yaml | \
  kubectl apply -f -
echo_ok

echo
echo "Backup was successfully created in ${OUTPUT_FILE}"
echo "You can now proceed with the GitGuardian application update using KOTS"
echo
