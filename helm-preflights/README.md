# Helm preflights

The Helm preflights are a set of tests that can be run at any time to ensure your cluster meets GitGuardian's requirements.

This folder contains a script (`preflights.sh`) that:
- Generates tests templates according to the provided values files
- Runs tests
- Fetches and displays the results
- Pushes results inside a Kubernetes secret in your cluster

## Requirements

The Kubernetes namespace should be the one that will be used for Gitguardian app.

This script will work from GitGuardian version **2024.4.0**.

Additionally, the script requires the following:
- [helm v3](https://helm.sh/docs/intro/install/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/#kubectl) (version ≥ 1.27.0)
- [kubectl preflight plugin](https://troubleshoot.sh/docs/#installation) (version ≥ 0.84.0, possible to install through the script)

It is designed to run similarly to `helm install` command, an example is provided below.

## Usage

Download the script on your workstation:
```bash
curl -O https://raw.githubusercontent.com/GitGuardian/ggtools/main/preflights-helm/helm-preflights/preflights.sh
chmod +x preflights.sh 
```

Among all the options, you can:
- Define several values file
- Define the namespace
- Install `kubectl preflight` plugin

To view all options, run `./preflights.sh --help`.

### Example

```bash
./preflights.sh \
-n <namespace> \
-f local-values.yaml \
oci://registry.replicated.com/gitguardian/gitguardian
```
