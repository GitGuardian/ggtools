#!/usr/bin/env bash

#####
#
# -- Restore the GitGuardian PostgreSQL Embedded DB using kubectl --
#
# The script is compatible with both V1 and V2. By default it uses V2 specs
# but you can enable using V1 specs by specifying --v1 flag
#
# The dump file provided
#####

#set -x
set -eo pipefail

# --- Variables
APP_SLUG="${GITGUARDIAN_APP_SLUG:-gitguardian-seal}"

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KUBECTL_ARGS=""
NAMESPACE=""
INPUT_FILE=""
ERROR_LOG_FILE=$(mktemp)

# By default, use v2 parameters
POSTGRES_RESTORE_CMD="PGPASSWORD=\$POSTGRES_PASSWORD psql -h postgresql -U \$POSTGRES_USER -d \$POSTGRES_DATABASE"
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
    Backup the GitGuardian PostgresSQL database.
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

    -i | --input <path>
        Specify the backup inpu file to use to restore database

    -h | --help
        Display this help message
USAGE
}

# --- Options
while (("$#")); do
  case "$1" in
  --v1)
    POSTGRES_RESTORE_CMD="PGPASSWORD=\$POSTGRES_PRM_PASSWORD psql -U \$POSTGRES_PRM_NAME -d \$POSTGRES_PRM_DB"
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
  -i | --input)
    shift
    INPUT_FILE="$1"
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

if [[ ! -s "$INPUT_FILE" ]]; then
  usage
  echo
  echo_error "Input file ${INPUT_FILE} doesn't exist"
  exit 1
fi

# --- Main
trap _exit EXIT
trap 'exit 1' ERR

echo_step "Retrieve PostgreSQL pod"
pod=$(kubectl $KUBECTL_ARGS get pod \
  --selector="$POSTGRES_POD_SELECTOR" \
  --output=name 2>$ERROR_LOG_FILE | head -1)
if [[ -z "$pod" ]]; then
  echo "PostgreSQL pod not found" >$ERROR_LOG_FILE
  exit 1
fi
echo_ok

echo_step "Restore the GitGuardian DB"
gunzip -c ${INPUT_FILE} | \
	kubectl $KUBECTL_ARGS \
    exec -i $pod -- \
		bash -c "$POSTGRES_RESTORE_CMD" >/dev/null 2>$ERROR_LOG_FILE
if [[ -s "$ERROR_LOG_FILE" ]]; then
  exit 1
fi
echo_ok

echo
echo "DB was successfully restored from ${INPUT_FILE}"
