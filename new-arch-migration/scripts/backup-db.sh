#!/usr/bin/env bash

#####
#
# -- Back up the GitGuardian PostgreSQL Embedded DB using kubectl --
#
# The script is compatible with both V1 and V2. By default it uses V2 specs
# but you can enable using V1 specs by specifying --v1 flag
#
# The output file (specified with --output flag) is compressed using gzip and
# can be restored using the restore-db.sh script in both V1 and V2 app.
#####

#set -x
set -eo pipefail

# --- Variables
APP_SLUG="${GITGUARDIAN_APP_SLUG:-gitguardian-seal}"

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KUBECTL_ARGS=""
NAMESPACE=""
OUTPUT_FILE=""
ERROR_LOG_FILE=$(mktemp)

# By default, use v2 parameters
POSTGRES_BACKUP_CMD="PGPASSWORD=\$POSTGRES_PASSWORD pg_dump -U \$POSTGRES_USER -d \$POSTGRES_DATABASE --no-privileges --no-owner --clean --if-exists | gzip"
POSTGRES_POD_SELECTOR="kots.io/app-slug=${APP_SLUG}, app.kubernetes.io/name=postgresql, app.kubernetes.io/component=primary"

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
    Backup the GitGuardian Postgres DB.
    The dump file is compressed using gzip.

OPTIONS:

    --v1
        Use v1 app specs

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
  --v1)
    POSTGRES_BACKUP_CMD="PGPASSWORD=\$POSTGRES_PRM_PASSWORD pg_dump -U \$POSTGRES_PRM_NAME -d \$POSTGRES_PRM_DB --no-privileges --no-owner --clean --if-exists | gzip"
    POSTGRES_POD_SELECTOR="kots.io/app-slug=${APP_SLUG}, app=postgresql"
    shift
    ;;
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

echo_step "Retrieve PostgreSQL pod"
pod=$(kubectl $KUBECTL_ARGS get pod \
  --field-selector="status.phase=Running" \
  --selector="$POSTGRES_POD_SELECTOR" \
  --output=name 2>$ERROR_LOG_FILE | head -1)
if [[ -z "$pod" ]]; then
  echo "No running PostgreSQL pod found" >$ERROR_LOG_FILE
  exit 1
fi
echo_ok

echo_step "Create a backup of the GitGuardian database"
kubectl $KUBECTL_ARGS \
  exec --quiet $pod -- \
  sh -c "$POSTGRES_BACKUP_CMD" >"$OUTPUT_FILE" 2>$ERROR_LOG_FILE
if [[ -s "$ERROR_LOG_FILE" ]]; then
  exit 1
fi
echo_ok

echo
echo "Backup was successfully created in ${OUTPUT_FILE}"
