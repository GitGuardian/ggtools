#!/bin/bash

set -euo pipefail

usage() {
  echo "Usage: $0 -p <name_prefix> -r <replicas> [-n <namespace>]"
  echo ""
  echo "  -p  Deployment name prefix (e.g. 'webapp' matches 'webapp-*')"
  echo "  -r  Number of replicas to scale to"
  echo "  -n  Kubernetes namespace (default: current context namespace)"
  echo ""
  echo "Example: $0 -p webapp -r 2 -n production"
  exit 1
}

NAMESPACE_ARGS=()
PREFIX=""
REPLICAS=""

while getopts "p:r:n:h" opt; do
  case $opt in
    p) PREFIX="$OPTARG" ;;
    r) REPLICAS="$OPTARG" ;;
    n) NAMESPACE_ARGS=("-n" "$OPTARG") ;;
    h) usage ;;
    *) usage ;;
  esac
done

if [[ -z "$PREFIX" || -z "$REPLICAS" ]]; then
  echo "Error: -p and -r are required."
  usage
fi

if ! [[ "$REPLICAS" =~ ^[0-9]+$ ]]; then
  echo "Error: replicas must be a non-negative integer."
  exit 1
fi

REGEX="^${PREFIX}-"

echo "Fetching deployments matching '${REGEX}' ..."

DEPLOYMENTS=$(kubectl get deployments "${NAMESPACE_ARGS[@]}" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' \
  | grep -E "$REGEX" || true)

if [[ -z "$DEPLOYMENTS" ]]; then
  echo "No deployments found matching '${REGEX}'."
  exit 0
fi

echo "Found deployments:"
echo "$DEPLOYMENTS" | sed 's/^/  - /'
echo ""

read -rp "Scale all of the above to ${REPLICAS} replica(s)? [y/N] " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

while IFS= read -r DEPLOY; do
  echo -n "Scaling ${DEPLOY} to ${REPLICAS}... "
  kubectl scale deployment "$DEPLOY" "${NAMESPACE_ARGS[@]}" --replicas="$REPLICAS"
done <<< "$DEPLOYMENTS"

echo "Done."
