# Helm Preflights

The Helm Preflights are a set of tests that can be run at any time to ensure your cluster meets GitGuardian's requirements.

This directory contains a script called `preflights.sh` which:
- Generates tests templates according to the provided values files.
- Runs tests.
- Fetches and displays the results.
- Stores the results in a Kubernetes secret within your cluster.

⚠️ Helm Preflights are available starting from GitGuardian version **2024.4.0**.

## Checks

Below is a table detailing the tests conducted by this tool:

| Check                                   | Type   | Status          | From version
|-----------------------------------------|--------|-----------------|--------------
| Required Kubernetes version             | Local  | Pass/Warn/Error | 2024.4.0
| Custom CA certificate validity          | Local  | Pass/Error | 2024.5.0
| Existing secret presence                | Local  | Pass/Error | 2024.6.0
| Required PostgreSQL version & connectivity | Remote | Pass/Warn/Error | 2024.4.0
| Required Redis version & connectivity   | Remote | Pass/Warn/Error | 2024.4.0

## Requirements

The Kubernetes namespace should be the one that will be used for Gitguardian app.

Additionally, the script requires the following:
- [helm v3](https://helm.sh/docs/intro/install/) (version >= v3.13.3)
- [kubectl](https://kubernetes.io/docs/tasks/tools/#kubectl) (version ≥ 1.27.0)
- [jq](https://github.com/jqlang/jq)
- [kubectl preflight plugin](https://troubleshoot.sh/docs/#installation) (version ≥ 0.84.0, possible to install through the script)

It is designed to run similarly to `helm install` command, an example is provided below.

## Usage

To download the script to your workstation:

```bash
curl -O https://raw.githubusercontent.com/GitGuardian/ggtools/main/helm-preflights/preflights.sh
chmod +x preflights.sh
```

Options include:
- Specifying multiple values files.
- Setting the namespace.
- Install `kubectl preflight` plugin.

To view all available options, run `./preflights.sh --help`.

### Example

#### Use an OCI chart
```bash
./preflights.sh \
-n <namespace> \
-f local-values.yaml \
oci://registry.replicated.com/gitguardian/gitguardian
```

#### Use a local chart (Airgap mode)
```bash
./preflights.sh \
-n <namespace> \
-f local-values.yaml \
gitguardian-<version>.tgz
```
