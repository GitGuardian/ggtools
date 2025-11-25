# GitGuardian Tools

Welcome to the GitGuardian Tools Repository! Here, you'll find a collection of shared tools and scripts designed to enhance the experience of GitGuardian's customers.

Should you have any inquiries or need assistance, please don't hesitate to contact our [support team](mailto:support@gitguardian.com?subject=Inquiry+about+GitGuardian+Tools).

Below is a brief overview of the tools available in this repository:

| Tools                                                                | Description                                                                                                                                                                                                                                                        |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [api-migration](./api-migration)                                     | Facilitates the migration of incident remediation progress across different environments, including SaaS ↔ Self-Hosted, Self-Hosted ↔ Self-Hosted, and SaaS ↔ SaaS.                                                                                             |
| [new-arch-migration](./new-arch-migration)                           | Assists in transitioning from the legacy GitGuardian architecture to the new architecture for Self-Hosted environments.                                                                                                                                            |
| [honeytoken-tools](./honeytoken-tools)                               | Script to disseminate honeytokens in your repositories via Pull Requests                                                                                                                                                                                           |
| [team-mapping-github-gitguardian](./team-mapping-github-gitguardian) | An example script using the GitHub and GitGuardian APIs to map GitHub Teams and the repositories they own to GitGuardian Teams and their perimeters.                                                                                                               |
| [team-mapping-gitlab-gitguardian](./team-mapping-gitlab-gitguardian) | An example script using the Gitlab and GitGuardian APIs to map Gitlab Groups and the repositories they own to GitGuardian Teams and their perimeters.                                                                                                              |
| [secret-key-rotation](./secret-key-rotation) | Rotate the Database Encryption Secret Key. |
| [helm-preflights](./helm-preflights)                                 | Ensures GitGuardian requirements are met prior installation or upgrade via [Helm on existing clusters](https://docs.gitguardian.com/self-hosting/installation/installation-existing-helm) by conducting tests from both the local user and the Kubernetes cluster. |
| [helm-pg-redis-poc](./helm-pg-redis-poc) | Helm values and install commands to deploy PostgreSQL and Redis for GitGuardian (PoC/testing only). Includes small/medium/large presets aligned with [Scaling](https://docs.gitguardian.com/self-hosting/management/infrastructure-management/scaling).  |
