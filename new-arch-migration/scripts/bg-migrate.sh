#!/usr/bin/env bash

#####
#
# -- Blue/Green migration of GitGuardian app --
#
# The migration process takes place within a single cluster and
# involves using separate namespaces for both V1 and V2.
#
# The script performs the following steps:
#   1/ Retrieve the V1 KOTS config from the specified namespace
#   2/ Optionally make changes on the extracted configuration
#   3/ Install the V2 app in the specified namespace using the V1 extracted config
#####

#set -x
set -ueo pipefail

# --- Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

KUBECTL_ARGS=""
KOTS_ARGS=""
KOTS_INSTALL_ARGS=""
ERROR_LOG_FILE=$(mktemp)

KOTS_CONFIG_FILE=""
KOT_CONFIG_SET=()
KOTS_CONFIG_TEMPFILE=$(mktemp)
KOTS_LICENSE_FILE=""

# v2 app hostanme
HOSTNAME=""

V1_APP_SLUG="gitguardian-seal"
V1_NAMESPACE=""

V2_APP_SLUG="gitguardian"
V2_APP_CHANNEL="stable"
V2_NAMESPACE=""

ENSURE_RBAC="false"

# --- Functions
function cleanup() {
  if [[ -f "$KOTS_CONFIG_TEMPFILE" ]]; then
    rm -f "$KOTS_CONFIG_TEMPFILE"
  fi
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
    Migrate The GitGuardian application.

OPTIONS:

    --context <string>
        The name of the kubeconfig context to use

    --kubeconfig <string>
        Path to the kubeconfig file to use for CLI requests

    --v1-namespace <string>
        Specify the kubernetes V1 namespace (legacy)

    --v2-namespace <string>
        Specify the kubernetes namespace (new)

    --channel <string>
        Specify the kots application channel to use (Default: $V2_APP_CHANNEL)

    --airgap-bundle <string>
        Path to the application airgap bundle where application images and metadata will be loaded from

    --deploy-version-label <string>
        Specify the version to deploy

    --config-values <path>
        Specify the kots config values file

    --license-file <path>
        Specify the kots license file

    --shared-password <path>
        Specify the kots password (new)

    --ensure-rbac
        When enabled, the script attempts to create the (cluster-scoped) RBAC resources necessary to manage applications.

    --skip-preflights
        Skip preflight checks

    --set <param=value>
        Override parameter in kots config

    -h | --help
        Display this help message
USAGE
}

# --- Options
while (("$#")); do
  case "$1" in
  --context | --kubeconfig)
    KOTS_ARGS="${KOTS_ARGS} $1=$2"
    KUBECTL_ARGS="${KUBECTL_ARGS} $1=$2"
    shift 2
    ;;
  --v1-namespace)
    V1_NAMESPACE=$2
    shift 2
    ;;
  --v2-namespace)
    V2_NAMESPACE=$2
    shift 2
    ;;
  --channel)
    V2_APP_CHANNEL=$2
    shift 2
    ;;
  --ensure-rbac)
    ENSURE_RBAC="true"
    shift
    ;;
  --config-values)
    KOTS_CONFIG_FILE=$2
    shift 2
    ;;
  --set)
    set +u
    KOTS_CONFIG_SET=("${KOTS_CONFIG_SET[@]}" "$2")
    set -u
    shift 2
    ;;
  --airgap-bundle | --deploy-version-label)
    KOTS_INSTALL_ARGS="${KOTS_INSTALL_ARGS} $1=$2"
    shift 2
    ;;
  --skip-preflights)
    KOTS_INSTALL_ARGS="${KOTS_INSTALL_ARGS} $1"
    shift
    ;;
  --license-file)
    KOTS_LICENSE_FILE="$2"
    KOTS_INSTALL_ARGS="${KOTS_INSTALL_ARGS} $1=$2"
    shift 2
    ;;
  --shared-password)
    KOTS_SHARED_PASSWORD="$2"
    KOTS_INSTALL_ARGS="${KOTS_INSTALL_ARGS} $1=$2"
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

if [[ -z "$V1_NAMESPACE" ]]; then
  usage
  echo
  echo_error "You must specify the v1 namespace: --v1-namespace <string>"
  exit 1
fi

if [[ -z "$V2_NAMESPACE" ]]; then
  usage
  echo
  echo_error "You must specify the v2 namespace: --v2-namespace <string>"
  exit 1
fi

if [[ ! -s "$KOTS_LICENSE_FILE" ]]; then
  usage
  echo
  echo_error "License file not found or is empty: --license-file <string>"
  exit 1
fi

if [[ -z "$KOTS_SHARED_PASSWORD" ]]; then
  usage
  echo
  echo_error "You must specify the KOTS password: --shared-password <string>"
  exit 1
fi

# --- Main
trap _exit EXIT
trap 'exit 1' ERR

if [[ "$ENSURE_RBAC" == "true" ]]; then
  echo_step "Create "$V2_NAMESPACE" namespace"
  kubectl $KUBECTL_ARGS \
    create namespace "$V2_NAMESPACE" --dry-run=client -o yaml | kubectl $KUBECTL_ARGS apply -f -
  echo_ok

  echo_step "Create minimal cluster-scoped RBAC permissions"
  kubectl $KUBECTL_ARGS apply -n "${V2_NAMESPACE}" -f - <<EOF
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: kotsadm
  labels:
    kots.io/backup: velero
    kots.io/kotsadm: "true"
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: kotsadm-role
rules:
  - apiGroups: [""]
    resources: ["namespaces", "nodes"]
    verbs: ["get", "list"]
  - apiGroups: ["apiextensions.k8s.io"]
    resources: ["customresourcedefinitions"]
    verbs: ["get", "list"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: kotsadm-rolebinding
  labels:
    kots.io/backup: velero
    kots.io/kotsadm: "true"
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: kotsadm-role
subjects:
  - kind: ServiceAccount
    name: kotsadm
    namespace: ${V2_NAMESPACE}
EOF
  echo_ok
fi

if [[ -z "$KOTS_CONFIG_FILE" ]]; then
  KOTS_CONFIG_FILE="$KOTS_CONFIG_TEMPFILE"
  echo_step "Retrieve V1 kots configuration"
  kubectl kots get config $KOTS_ARGS \
    --namespace "$V1_NAMESPACE" \
    --appslug "$V1_APP_SLUG" > "$KOTS_CONFIG_FILE" 2>$ERROR_LOG_FILE
  echo_ok

  set +u
  for set in "${KOTS_CONFIG_SET[@]}"; do
    key=$(echo $set | cut -d'=' -f1)
    value=$(echo $set | cut -d'=' -f2)
    echo_step "Set $key in kots configuration"
    yq -i ".spec.values.$key.value = \"$value\"" "$KOTS_CONFIG_FILE" 2>$ERROR_LOG_FILE
    echo_ok
  done
  set -u
fi

echo_step "Install V2 application"
kubectl kots install "${V2_APP_SLUG}/${V2_APP_CHANNEL}" \
  $KOTS_ARGS \
  --namespace "$V2_NAMESPACE" \
  --use-minimal-rbac \
  --config-values "$KOTS_CONFIG_FILE" \
  --no-port-forward \
  --wait-duration "30m" $KOTS_INSTALL_ARGS 2>$ERROR_LOG_FILE
echo_ok
