#!/bin/bash

# set -x
script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

OS="$(uname | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m | sed -e 's/x86_64/amd64/' -e 's/\(arm\)\(64\)\?.*/\1\2/' -e 's/aarch64$/arm64/')"

PREFLIGHTS_ROOT_DIR="${HOME}/.local"
PREFLIGHTS_BIN_DIR="${PREFLIGHTS_ROOT_DIR}/bin"
HELM_MINIMUM_VERSION="3.13.3"

STABLE_CHARTS=("oci://registry.replicated.com/gitguardian/gitguardian" "oci://registry.replicated.com/gitguardian/stable/gitguardian" "oci://registry.replicated.com/gitguardian-seal/gitguardian" "oci://registry.replicated.com/gitguardian-seal/stable/gitguardian")

export PATH="${PREFLIGHTS_BIN_DIR}:${PATH}"

function echo_pass() {
  echo -e "\033[1;32mPASS\033[0m"
}

function exit_ko() {
  echo -e "\033[1;31mKO\033[0m "
  exit 1
}

function exit_error() {
  echo -en "\033[1;31m[ERROR]\033[0m " >&2
  echo $@ >&2
  exit 1
}

function echo_warn() {
  echo -en "\033[38;2;255;165;0m[WARN]\033[0m"
  echo $@
}

function install_jq() {
  local os=$(echo $OS | sed -e 's/darwin/macos/')
  echo -e "--- INSTALLING JQ BINARY"
  mkdir -p "${PREFLIGHTS_BIN_DIR}"
  curl -fsSL https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-${os}-${ARCH} \
    --output "${PREFLIGHTS_BIN_DIR}/jq"
  chmod +x "${PREFLIGHTS_BIN_DIR}/jq"
}

function install_helm() {
  echo -e "--- INSTALLING HELM BINARY"
  mkdir -p "${PREFLIGHTS_BIN_DIR}"
  export HELM_INSTALL_DIR="${PREFLIGHTS_BIN_DIR}"
  curl --silent https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
}

function install_preflight() {
  echo -e "--- INSTALLING PREFLIGHT PLUGIN"
  curl --silent https://krew.sh/preflight | bash >$script_dir/preflights_install.logs 2>&1
}

# Function to check if a string is in an array
function contains_string_in_array() {
  local search_string=$1
  shift
  local array=("$@")

  for item in "${array[@]}"; do
    if [[ "$item" == "$search_string" ]]; then
      return 0  # Found
    fi
  done

  return 1  # Not found
}

function write_results() {
  if [[ "$SAVE" == "yes" ]];
  then
    echo -e "\n--- SAVING RESULTS TO SECRET gitguardian-preflights-results"
    #Used to preserve formatting
    cat <<K8SSECRET > $script_dir/preflights-output
$GLOBAL_OUTPUT
K8SSECRET

    kubectl create secret generic gitguardian-preflights-results \
    --save-config=true \
    --dry-run=client \
    --from-file="$script_dir/preflights-output" \
    -o yaml | \
    kubectl apply $NAMESPACE -f -
    rm -f $script_dir/preflights-output

    #add this for telemetry usage later in backend
    kubectl patch secrets gitguardian-preflights-results $NAMESPACE -p='{"stringData":{"STATUS_LOCAL":"'$LOCAL_CHECKS_STATUS'","STATUS_REMOTE":"'$REMOTE_CHECKS_STATUS'"}}'
  fi
}

function run_hide_output() {
  local cmd="$1"
  local flag="$2"

  if [[ "$DEBUG_MODE" == "yes" ]];
  then
    flag="none"
  fi

  case "$flag" in
    stderr)
      eval "$cmd 2> /dev/null"
      ;;
    all)
      eval "$cmd &> /dev/null"
      ;;
    none)
      eval "$cmd"
      ;;
    *)
      echo "Invalid flag: $flag"
      return 1
      ;;
  esac

  return $?
}

function usage() {
  cat <<USAGE

Usage:
    $(basename $0) [OPTIONS] chart

Description:
    Execute Gitguardian Preflight on a cluster.
    Chart can be local path or OCI uri.
    Dependencies: kubectl, helm, preflight plugin (installable using --install-preflight option)

OPTIONS:

    -f FILE
        Pass a values file, can be used several times

    -n NAMESPACE
        Specify the Kubernetes destination namespace

    --version
        Specify the version of the Helm chart to use (default to latest)

    --local
        Execute only local tests

    --install-jq
        Install jq tool

    --install-helm
        Install helm

    --install-preflight
        Install latest preflight plugin using krew for local preflights

    --remote
        Execute only remote tests

    --reuse
        Use existing templates if preflights have been played before

    --nosave
        Do not save results in-cluster (not recommended)

    --no-replicated
        Use this option for dev, do not render Replicated pull secrets

    -h | --help
        Display this help message
USAGE
}

trap "write_results" EXIT

#conf
REMOTE_PREFLIGHTS_TEMPLATE="-s templates/on-prem/helm_preflights_remote.yaml"
LOCAL_PREFLIGHTS_TEMPLATE="-s templates/on-prem/helm_preflights_local.yaml"
PULL_SECRETS_OPTION="-s templates/image-pull-secrets.yaml"
PREFLIGHTS_TEMPLATING_OPTION="--dry-run=server --set onPrem.preflightsTemplating.enabled=true"
REMOTE_CRONJOB_NAME="gitguardian-remote-preflights"

#inputs
CHART=""
CHART_VERSION=""
DEVEL=""
NAMESPACE=""
LOCAL_CHECKS="yes"
REMOTE_CHECKS="yes"
VALUES_FILES=""
FORCE="yes"
SAVE="yes"
DEBUG_MODE="no"
INSTALL_JQ="no"
INSTALL_HELM="no"
INSTALL_PREFLIGHT="no"

#outputs
GLOBAL_OUTPUT=""
LOCAL_CHECKS_STATUS="empty"
REMOTE_CHECKS_STATUS="empty"

#input parsing
while (("$#")); do
  case "$1" in
  --local)
    REMOTE_CHECKS="no"
    shift
    ;;
  --remote)
    LOCAL_CHECKS="no"
    shift
    ;;
  -n)
    shift
    NAMESPACE="--namespace $1"
    shift
    ;;
  --version)
    shift
    CHART_VERSION="--version $1"
    shift
    ;;
  --reuse)
    FORCE="no"
    shift
    ;;
  --install-jq)
    INSTALL_JQ="yes"
    shift
    ;;
  --install-preflight)
    INSTALL_PREFLIGHT="yes"
    shift
    ;;
  --install-helm)
    INSTALL_HELM="yes"
    shift
    ;;
  --no-replicated)
    PULL_SECRETS_OPTION=""
    shift
    ;;
  --nosave)
    SAVE="no"
    shift
    ;;
  --debug)
    DEBUG_MODE="yes"
    shift
    ;;
  -f)
    shift
    VALUES_FILES+="-f $1 "
    shift
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *) # positional argument
    if [ -n "$CHART" ];
    then
      usage
      exit_error "You can have only one chart path, please check your command"
    fi
    CHART=$1
    shift
    ;;
  esac
done

#Checks
if [[ "$LOCAL_CHECKS" == "no" ]] && [[ "$REMOTE_CHECKS" == "no" ]];
then
    usage
    exit_error "You selected no tests, remove --local and --remote to run all tests"
fi

if [[ -z "$CHART" ]] && [[ "$LOCAL_CHECKS" == "yes" ]];
then
    usage
    exit_error "You must provide a chart (path or OCI uri)"
fi

if ! which kubectl &>/dev/null;
then
  exit_error "You need kubectl in your PATH"
fi

if ! which helm &>/dev/null;
then
  if [[ "$INSTALL_HELM" == "no" ]];
  then
    exit_error "You need helm in your PATH. Use --install-helm to get it locally"
  else
    install_helm
  fi
fi

# check helm minimum
helm_current_version=$(helm version --template="{{.Version}}")
helm_current_version=${helm_current_version#v}

if [[ $(printf "%s\n%s\n" "$HELM_MINIMUM_VERSION" "$helm_current_version" | sort -V | head -n 1) != "$HELM_MINIMUM_VERSION" ]]; then
  if [[ "$INSTALL_HELM" == "no" ]];
  then
    exit_error "Your current Helm version ($helm_current_version) is below the minimum required version ($HELM_MINIMUM_VERSION). Use --install-helm to get it locally"
  else
    install_helm
  fi
fi

# If specified chart is not considered as a stable chart, enable Helm --devel flag
if ! contains_string_in_array "$CHART" "${STABLE_CHARTS[@]}"; then
  DEVEL="--devel"
fi

values_array=($VALUES_FILES)
for i in "${!values_array[@]}";
do
  if [[ ${values_array[$i]} == "-f" ]]; then
    file=${values_array[$((i+1))]}
    if [ ! -f $file ];
    then
      exit_error "The file $file does not exist"
    fi
  fi
done

#Main
if [ -n "$PULL_SECRETS_OPTION" ] && [[ "$FORCE" == "yes" ]];
then
  echo -e "--- TEMPLATING PULL SECRETS"
  echo -e "Please wait ..."
  if ! run_hide_output "helm template $DEVEL $NAMESPACE $VALUES_FILES $CHART_VERSION $PULL_SECRETS_OPTION $CHART > $script_dir/local_secrets.yaml" "stderr";
  then
    LOCAL_CHECKS_STATUS="error"
    exit_error "Unable to template pull secrets"
  elif ! run_hide_output "kubectl $NAMESPACE apply -f $script_dir/local_secrets.yaml" "all";
  then
    LOCAL_CHECKS_STATUS="error"
    exit_error "Unable to apply pull secrets"
  fi
  rm -f $script_dir/local_secrets.yaml
fi

if [[ "$LOCAL_CHECKS" == "yes" ]];
then
  if ! run_hide_output "kubectl preflight version" "all";
  then
    if [[ "$INSTALL_PREFLIGHT" == "no" ]];
    then
      exit_error "You need kubectl preflight plugin to run local tests, use --install-preflight to get it"
    else
      install_preflight
    fi
  fi

  if [[ ! -f "$script_dir/local_preflights.yaml" ]] || [[ "$FORCE" == "yes" ]] ;
  then
    echo -e "--- TEMPLATING LOCAL TESTS"
    echo -e "Please wait ..."
    if ! run_hide_output "helm template $DEVEL $NAMESPACE $VALUES_FILES $CHART_VERSION $PREFLIGHTS_TEMPLATING_OPTION $LOCAL_PREFLIGHTS_TEMPLATE $CHART > $script_dir/local_preflights.yaml" "stderr";
    then
      rm -f $script_dir/local_preflights.yaml
      LOCAL_CHECKS_STATUS="error"
      exit_error "Unable to template local preflights"
    fi
  fi

  echo -e "--- RUNNING LOCAL TESTS"
  output=`run_hide_output "kubectl preflight $NAMESPACE --interactive=false $script_dir/local_preflights.yaml" "stderr"`
  retcode=$?
  echo -e "$output"
  GLOBAL_OUTPUT+="--- RUNNING LOCAL TESTS$output"
  if [ $retcode -eq 0 ];
  then
    LOCAL_CHECKS_STATUS="pass"
    echo_pass
  elif [ $retcode -eq 4 ];
  then
    LOCAL_CHECKS_STATUS="warn"
    echo_warn "At least, one check is in warn status"
  else
    LOCAL_CHECKS_STATUS="error"
    exit_ko
  fi
fi

if [[ "$REMOTE_CHECKS" == "yes" ]];
then
  if ! run_hide_output "jq --version" "all";
  then
    if [[ "$INSTALL_JQ" == "no" ]];
    then
      exit_error "You need jq tool to run remote tests, use --install-jq to get it"
    else
      install_jq
    fi
  fi
  if ! `run_hide_output "kubectl get cronjob $REMOTE_CRONJOB_NAME $NAMESPACE" "all"` || [[ "$FORCE" == "yes" ]] ; then
    echo -e "--- TEMPLATING REMOTE TESTS"
    echo -e "Please wait ..."
    if ! run_hide_output "helm template $DEVEL $NAMESPACE $VALUES_FILES $CHART_VERSION $PREFLIGHTS_TEMPLATING_OPTION $REMOTE_PREFLIGHTS_TEMPLATE $CHART > $script_dir/remote_preflights.yaml" "stderr";
    then
      REMOTE_CHECKS_STATUS="error"
      exit_error "Unable to template remote preflights"
    else
      run_hide_output "kubectl delete $NAMESPACE cronjob $REMOTE_CRONJOB_NAME" "all"
      if ! run_hide_output "kubectl apply $NAMESPACE -f $script_dir/remote_preflights.yaml" "all";
      then
        REMOTE_CHECKS_STATUS="error"
        exit_error "Unable to apply remote preflights"
      fi
      sleep 2
    fi
    rm -f $script_dir/remote_preflights.yaml
  fi

  echo -e "--- RUNNING REMOTE TESTS"
  echo -e "If this step is too long, please check the pod is running in the accurate namespace"
  echo -e "Please wait ..."
  #Start job
  run_hide_output "kubectl create job $NAMESPACE --from=cronjob/$REMOTE_CRONJOB_NAME $REMOTE_CRONJOB_NAME-`mktemp -u XXXXX | tr '[:upper:]' '[:lower:]'` --dry-run=client -o json | jq 'del(.metadata.ownerReferences)' | kubectl apply -f -" "all"
  sleep 5
  pod=$(kubectl get pods $NAMESPACE -l gitguardian=remote-preflight --sort-by=.metadata.creationTimestamp -o 'jsonpath={.items[-1].metadata.name}')


  while true; do
    # Check the status of the pod
    pod_status=$(kubectl get pod $pod $NAMESPACE -o jsonpath='{.status.phase}')

    # If pod_status is not empty, the pod has reached a terminal state
    if [ -n "$pod_status" ]; then
        case "$pod_status" in
            "Succeeded")
                break
                ;;
            "Failed")
                break
                ;;
            "Pending")
                waiting_pod=$(kubectl get pod $pod $NAMESPACE -o jsonpath='{.status.containerStatuses[-1].state.waiting.reason}')
                if [ -n "$waiting_pod" ] && [[ "$waiting_pod" == "ImagePullBackOff" ]];
                then
                  echo ""
                  exit_error "Unable to pull the test image, are your credentials configured properly?"
                fi
                ;;
        esac
    fi
    echo -n "."
    sleep 5
  done

  # Print preflights output
  output=`kubectl logs $NAMESPACE $pod`
  echo -e "$output"
  GLOBAL_OUTPUT+="
--- RUNNING REMOTE TESTS$output"
  retcode=$(kubectl get pods $pod $NAMESPACE -o 'jsonpath={.status.containerStatuses[0].state.terminated.exitCode}')

  if [ $retcode -eq 0 ];
  then
    if [[ "$output" =~ "WARN" ]];
    then
      REMOTE_CHECKS_STATUS="warn"
      echo_warn "At least, one check is in warn status"
    elif [[ "$output" =~ "FAIL" ]];
    then
      REMOTE_CHECKS_STATUS="error"
      exit_ko
    else
      REMOTE_CHECKS_STATUS="pass"
      echo_pass
    fi
  else
    REMOTE_CHECKS_STATUS="error"
    exit_ko
  fi
fi
