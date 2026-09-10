#!/bin/bash

set -euo pipefail

usage() {
  echo "Usage: $0 -n <embedded-namespace>"
  echo ""
  echo "  Polls 'kubectl kots get app' until the app reports ready."
  echo "  Must be run inside './gitguardian shell'."
  exit 1
}

NAMESPACE=""
while getopts "n:h" opt; do
  case $opt in
    n) NAMESPACE="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

[[ -z "$NAMESPACE" ]] && { echo "Error: -n is required."; usage; }

echo "Waiting for gitguardian to be ready in namespace '$NAMESPACE'..."
until kubectl kots get app gitguardian -n "$NAMESPACE" | grep -qi "ready"; do
  echo "  Not ready yet, retrying in 15s..."
  sleep 15
done

echo "App is ready."
