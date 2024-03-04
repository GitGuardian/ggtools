#!/usr/bin/env bash

#####
#
# -- Scale GitGuardian app components using kubectl --
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
COMPONENTS=()
LABEL_SELECTOR=app.kubernetes.io/component
REPLICAS=1
ERROR_LOG_FILE=$(mktemp)

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
    $(basename $0) [OPTIONS] <deployment>

Description:
    Scale Gitguardian deployment resource.

OPTIONS:

    --v1
        Use v1 app specs

    --context <string>
        The name of the kubeconfig context to use

    --kubeconfig <string>
        Path to the kubeconfig file to use for CLI requests

    -n | --namespace <string>
        Specify the kubernetes namespace (Mandatory)

    -c | --component <string>
        The gitguardian app component to scale (Mandatory)

    -r | --replicas <number>
        The new desired number of replicas

    -h | --help
        Display this help message
USAGE
}

# --- Options
while (("$#")); do
  case "$1" in
  --v1)
    LABEL_SELECTOR="app"
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
  -c | --component)
    set +u
    COMPONENTS=("${COMPONENTS[@]}" "$2")
    set -u
    shift 2
    ;;
  -r | --replicas)
    shift
    REPLICAS=$1
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

set +u
if [[ "${#COMPONENTS[@]}" -eq 0 ]]; then
  usage
  echo
  echo_error "You must specify GitGuardian components to scale"
  exit 1
fi
set -u

# --- Main
trap _exit EXIT
trap 'exit 1' ERR

for component in "${COMPONENTS[@]}"; do
  echo_step "Retrieve the GitGuardian ${component} component"
  deployment=$(kubectl $KUBECTL_ARGS get deployment \
    --selector="kots.io/app-slug=${APP_SLUG}, ${LABEL_SELECTOR}=${component}" \
    --output=name 2>$ERROR_LOG_FILE)
  if [[ -z "$deployment" ]]; then
    echo "GitGuardian ${component} component not found" >>$ERROR_LOG_FILE
    exit 1
  fi
  echo_ok

  echo_step "Scale GitGuardian ${component} component to $REPLICAS replicas"
  kubectl $KUBECTL_ARGS \
    scale $deployment \
    --timeout=1m \
    --replicas=$REPLICAS >/dev/null 2>$ERROR_LOG_FILE
  echo_ok
done
