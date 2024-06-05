#!/usr/bin/env bash

#####
#
# -- Migrate GitGuardian app with the latest available version using kubectl kots plugin --
#
#####

#set -x
set -eo pipefail

# --- Variables
APP_SLUG="${GITGUARDIAN_APP_SLUG:-gitguardian-seal}"

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KUBECTL_ARGS=""
KOTS_ARGS=""
KOTS_ADM_POD_SELECTOR="app=kotsadm"
NAMESPACE=""
PRUNE_FLAG="false"
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
    $(basename $0) [OPTIONS]

Description:
    Migrate the GitGuardian application.

OPTIONS:

    --context <string>
        The name of the kubeconfig context to use

    --kubeconfig <string>
        Path to the kubeconfig file to use for CLI requests

    -n | --namespace <string>
        Specify the kubernetes namespace

    --airgap-bundle <string>
        Path to the application airgap bundle where application images and metadata will be loaded from  (airgap only).

    --kotsadm-registry <string>
        Registry host where images will be pushed before the migration (airgap only).

    --kotsadm-namespace <string>
        Registry namespace in which images will be pushed (airgap only).

    --registry-username <string>
        Username to use to authenticate with the application registry (airgap only).

    --registry-password <string>
        Password to use to authenticate with the application registry (airgap only).

    --disable-image-push
        Disable images from being pushed to private registry (airgap only).

    --deploy-version-label <string>
        Specify the version to deploy

    --deploy
        Deploy new upstream release

    --skip-preflights
        Skip preflight checks

    --prune
        Uninstall all existing helm releases before upgrading

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
  --airgap-bundle | --deploy-version-label | --kotsadm-registry | --kotsadm-namespace | --registry-username | --registry-password)
    KOTS_ARGS="${KOTS_ARGS} $1=$2"
    shift 2
    ;;
  --skip-preflights | --deploy | --disable-image-push)
    KOTS_ARGS="${KOTS_ARGS} $1"
    shift
    ;;
  --prune)
    PRUNE_FLAG="true"
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

# --- Main
trap _exit EXIT
trap 'exit 1' ERR

if [[ "$PRUNE_FLAG" == "true" ]]; then
  echo_step "Retrieve kots admin pod"
  pod=$(kubectl $KUBECTL_ARGS get pod \
    --selector="$KOTS_ADM_POD_SELECTOR" \
    --output=name 2>$ERROR_LOG_FILE | head -1)
  if [[ -z "$pod" ]]; then
    echo "Kots admin pod not found" >$ERROR_LOG_FILE
    exit 1
  fi
  echo_ok

  echo_step "Retrieve helm releases"
  releases=$(kubectl $KUBECTL_ARGS \
    exec --quiet $pod -- \
    sh -c "helm -n $NAMESPACE list --short" 2>$ERROR_LOG_FILE)
  if [[ -s "$ERROR_LOG_FILE" ]]; then
    exit 1
  fi
  echo_ok

  if [[ -n "$releases" ]]; then
    for release in $releases; do
      echo_step "Uninstall $release Helm release"
      kubectl $KUBECTL_ARGS \
        exec --quiet $pod -- \
        sh -c "helm -n $NAMESPACE uninstall $release --wait" 2>$ERROR_LOG_FILE
      if [[ -s "$ERROR_LOG_FILE" ]]; then
        exit 1
      fi
      echo_ok
    done
  fi
fi

echo_step "Migrate GitGuardian application"
kubectl kots $KUBECTL_ARGS upstream upgrade $APP_SLUG \
  --wait $KOTS_ARGS 2>$ERROR_LOG_FILE
echo_ok
