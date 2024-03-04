#!/usr/bin/env bash

#####
#
# -- Inspect GitGuardian workers status --
#
# This script allows you to check that all Celery tasks are completed.
#
#####

#set -x
set -eo pipefail

# --- Variables
APP_SLUG="${GITGUARDIAN_APP_SLUG:-gitguardian-seal}"

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KUBECTL_ARGS=""
NAMESPACE=""
ERROR_LOG_FILE=$(mktemp)

# By default, use v2 parameters
WORKER_CONTAINER="worker"
WORKER_DEPLOYMENT_SELECTOR="kots.io/app-slug=${APP_SLUG}, app.kubernetes.io/component=worker"

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
    Inspect GitGuardian workers.

OPTIONS:

    --v1
        Enable v1 context

    --context <string>
        The name of the kubeconfig context to use

    --kubeconfig <string>
        Path to the kubeconfig file to use for CLI requests

    -n | --namespace <string>
        Specify the kubernetes namespace (Mandatory)

    -h | --help
        Display this help message
USAGE
}

# --- Options
while (("$#")); do
  case "$1" in
  --v1)
    WORKER_CONTAINER="worker"
    WORKER_DEPLOYMENT_SELECTOR="kots.io/app-slug=${APP_SLUG}, app=worker"
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

# --- Main
trap _exit EXIT
trap 'exit 1' ERR

echo_step "Retrieve GitGuardian worker deployment"
deployment=$(kubectl $KUBECTL_ARGS get deployment \
  --selector="$WORKER_DEPLOYMENT_SELECTOR" \
  --output=name 2>$ERROR_LOG_FILE)
if [[ -z "$deployment" ]]; then
  echo "GitGuardian worker deployment not found" >>$ERROR_LOG_FILE
  exit 1
fi
echo_ok

echo_step "Inspect workers..."
kubectl $KUBECTL_ARGS exec -it $deployment -c $WORKER_CONTAINER -- \
  celery -A ward_run_app inspect active
