#!/bin/bash

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

function echo_pass() {
  echo -e "\033[1;32mPASS\033[0m"
}

function echo_ko() {
  echo -e "\033[1;31mKO\033[0m "
}

function echo_error() {
  echo -en "\033[1;31m[ERROR]\033[0m " >&2
  echo $@ >&2
}

function echo_warn() {
  echo -en "\033[1;32m[WARN]\033[0m "
  echo $@
}

function install_preflight() {
  echo -e "--- INSTALLING PREFLIGHT PLUGIN"
  curl --silent https://krew.sh/preflight | bash >$script_dir/preflights_install.logs 2>&1
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
        
    --local
        Execute only local tests

    --install-preflight
        Install latest preflight plugin using krew for local preflights

    --remote
        Execute only remote tests

    --force
        Force retemplating even if preflights have been played before     

    --nosave
        Do not save results in-cluster (not recommended)            

    -h | --help
        Display this help message
USAGE
}

#conf
REMOTE_PREFLIGHTS_TEMPLATE="templates/on-prem/helm_preflights_remote.yaml"
LOCAL_PREFLIGHTS_TEMPLATE="templates/on-prem/helm_preflights_local.yaml"
PREFLIGHTS_TEMPLATING_OPTION="--set onPrem.preflightsTemplating.enabled=true"

#inputs
CHART=""
NAMESPACE=""
LOCAL_CHECKS="yes"
REMOTE_CHECKS="yes"
VALUES_FILES=""
FORCE="no"
SAVE="yes"
INSTALL_PREFLIGHT="no"

#outputs
GLOBAL_OUTPUT=""
GLOBAL_RC=0
LOCAL_CHECKS_STATUS="empty"
REMOTE_CHECKS_STATUS="empty"

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
  --force)
    FORCE="yes"
    shift
    ;;
  --install-preflight)
    INSTALL_PREFLIGHT="yes"
    shift
    ;;
  --nosave)
    SAVE="no"
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
      echo_error "You can have only one chart path, please check your command"
      exit 1
    fi      
    CHART=$1
    shift
    ;;
  esac
done


if [[ "$LOCAL_CHECKS" == "no" ]] && [[ "$REMOTE_CHECKS" == "no" ]];
then
    usage
    echo_error "You selected no tests, remove --local and --remote to run all tests"
    exit 1
fi

if [[ -z "$CHART" ]] && [[ "$LOCAL_CHECKS" == "yes" ]];
then
    usage
    echo_error "You must provide a chart (path or OCI uri)"
    exit 1    
fi

if [[ ! `which kubectl helm` ]];
then
  echo_error "You need helm and kubectl in your PATH" 
  exit 1
fi


if [[ "$LOCAL_CHECKS" == "yes" ]];
then
  if [[ ! `kubectl preflight version 2>/dev/null` ]];
  then
    if [[ "$INSTALL_PREFLIGHT" == "no" ]];
    then
      echo_error "You need kubectl preflight plugin to run local tests, use --install-preflight to get it" 
      exit 1
    else
      install_preflight
    fi
  fi

  if [[ ! -f "$script_dir/local_preflights.yaml" ]] || [[ "$FORCE" == "yes" ]] ;
  then
    echo -e "--- TEMPLATING LOCAL TESTS"
    helm template $NAMESPACE $VALUES_FILES $PREFLIGHTS_TEMPLATING_OPTION -s $LOCAL_PREFLIGHTS_TEMPLATE $CHART > $script_dir/local_preflights.yaml
    retcode_localtpl=$?
    if [ $retcode_localtpl -ne 0 ];
    then
      rm -f $script_dir/local_preflights.yaml
      echo_error "Unable to template local preflights"
      LOCAL_CHECKS_STATUS="error"
      GLOBAL_RC=1
    fi
  fi

  if [ -z ${retcode_localtpl+x} ] || [ $retcode_localtpl -eq 0 ];
  then
    echo -e "--- RUNNING LOCAL TESTS"
    output=`kubectl preflight $NAMESPACE --interactive=false $script_dir/local_preflights.yaml 2>/dev/null`
    retcode=$?
    echo -e "$output"
    GLOBAL_OUTPUT+="--- RUNNING LOCAL TESTS$output"
    if [ $retcode -eq 0 ];
    then
      echo_pass
      LOCAL_CHECKS_STATUS="pass"
    elif [ $retcode -eq 4 ];
    then
      echo_warn "At least, one check is in warn status"
      LOCAL_CHECKS_STATUS="warn"
    else
      echo_ko
      LOCAL_CHECKS_STATUS="error"
      GLOBAL_RC=1
    fi
  fi
fi

if [[ "$REMOTE_CHECKS" == "yes" ]];
then

  kubectl get cronjob gitguardian-remote-preflights $NAMESPACE &>/dev/null
  existingTests=$?

  if [[ $existingTests -ne 0 ]] || [[ "$FORCE" == "yes" ]] ; then
    echo -e "--- TEMPLATING REMOTE TESTS"
    helm template $NAMESPACE $VALUES_FILES $PREFLIGHTS_TEMPLATING_OPTION -s $REMOTE_PREFLIGHTS_TEMPLATE $CHART > $script_dir/remote_preflights.yaml
    retcode_remotetpl=$?
    if [ $retcode_remotetpl -ne 0 ];
    then
      echo_error "Unable to template remote preflights"
      REMOTE_CHECKS_STATUS="error"
      GLOBAL_RC=1
    else  
      kubectl delete $NAMESPACE cronjob gitguardian-remote-preflights &>/dev/null
      kubectl apply $NAMESPACE -f $script_dir/remote_preflights.yaml 2>/dev/null
      sleep 2
    fi
    rm -f $script_dir/remote_preflights.yaml
  fi

  if [ -z ${retcode_remotetpl+x} ] || [ $retcode_remotetpl -eq 0 ];
  then

    echo -e "--- RUNNING REMOTE TESTS"

    #Start job
    kubectl create job $NAMESPACE --from=cronjob/gitguardian-remote-preflights gitguardian-remote-preflights-`mktemp -u XXXXX | tr '[:upper:]' '[:lower:]'` &>/dev/null
    sleep 5
    pod=$(kubectl get pods $NAMESPACE -l gitguardian=remote-preflight --sort-by=.metadata.creationTimestamp -o 'jsonpath={.items[-1].metadata.name}')
    
    echo -e "If this step is too long, please check the pod is running in the accurate namespace"
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
          esac
      fi
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
      echo_pass
      REMOTE_CHECKS_STATUS="pass"
    elif [ $retcode -eq 4 ];
    then
      echo_warn "At least, one check is in warn status"
      REMOTE_CHECKS_STATUS="warn"
    else
      echo_ko
      REMOTE_CHECKS_STATUS="error"
      GLOBAL_RC=1
    fi
  fi
fi

if [[ "$SAVE" == "yes" ]];
then
  echo -e "--- SAVING RESULTS TO SECRET gitguardian-preflights-results"
  #Used to preserve formatting
  cat <<K8SSECRET > $script_dir/raw_output
$GLOBAL_OUTPUT
K8SSECRET

  kubectl create secret generic gitguardian-preflights-results \
  --save-config=true \
  --dry-run=client \
  --from-file="$script_dir/raw_output" \
  -o yaml | \
  kubectl apply $NAMESPACE -f -
  rm -f $script_dir/raw_output

  #add this for telemetry usage later in backend
  kubectl patch secrets gitguardian-preflights-results $NAMESPACE -p='{"stringData":{"STATUS_LOCAL":"'$LOCAL_CHECKS_STATUS'","STATUS_REMOTE":"'$REMOTE_CHECKS_STATUS'"}}'
fi

exit $GLOBAL_RC

