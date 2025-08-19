### Helm: PostgreSQL and Redis for GitGuardian

This folder provides ready-to-use Helm configurations to deploy PostgreSQL and Redis in your Kubernetes cluster for use with the GitGuardian application.

- PostgreSQL topologies:
  - **HA (replication)**: primary with read replica(s); recommended for production for resilience and read scaling.
  - **Standalone**: single-primary setup; suitable for PoC or testing only.
- Redis topology:
  - **Standalone** with persistence (aligned with the scaling guide). If you require Redis replication/sentinel, extend these values as needed.
- All presets are available in three sizes aligned with the GitGuardian scaling guide: **small**, **medium**, **large**.

### Recommendation for cloud providers

If you deploy GitGuardian on a public cloud, prefer the provider's managed services for PostgreSQL and Redis instead of running them in-cluster:

- AWS: [Amazon RDS/Aurora (PostgreSQL)](https://docs.gitguardian.com/self-hosting/installation/databases/postgres-rds), [Amazon ElastiCache (Redis)](https://docs.gitguardian.com/self-hosting/installation/databases/redis-elasticache)
- GCP: [Cloud SQL for PostgreSQL](https://docs.gitguardian.com/self-hosting/installation/databases/postgres-cloudsql), [Memorystore for Redis](https://docs.gitguardian.com/self-hosting/installation/databases/redis-memorystore)
- Azure: [Azure Database for PostgreSQL](https://docs.gitguardian.com/self-hosting/installation/databases/postgres-azure), [Azure Cache for Redis](https://docs.gitguardian.com/self-hosting/installation/databases/redis-azure-cache)

These Helm values are intended for existing-cluster installations or environments where managed services are not available. Managed services typically offer higher availability, automated backups/maintenance, and operational SLAs.

⚠️ Deploying PostgreSQL/Redis using these Bitnami Helm examples on Red Hat OpenShift is not supported.

Presets are mapped as follows:

- PostgreSQL
  - Small: Primary 4 vCPU / 8 GiB / 200 Gi; Read replica 2 vCPU / 4 GiB / 200 Gi
  - Medium: Primary 8 vCPU / 32 GiB / 250 Gi; Read replica 4 vCPU / 16 GiB / 250 Gi
  - Large: Primary 16 vCPU / 64 GiB / 300 Gi; Read replica 8 vCPU / 32 GiB / 300 Gi
- Redis (standalone)
  - Small: 2 vCPU / 2 GiB / 20 Gi
  - Medium: 4 vCPU / 8 GiB / 40 Gi
  - Large: 8 vCPU / 16 GiB / 100 Gi

For broader infrastructure guidance and context on these sizes, see the GitGuardian Scaling guide: [Scaling](https://docs.gitguardian.com/self-hosting/management/infrastructure-management/scaling).

You can customize storage classes, resource requests/limits, and replica counts by editing the values files or using `--set` overrides.

### Prerequisites

- Helm 3.x and `kubectl` configured against your target cluster
- A default `StorageClass` or an explicit one you will set in values files
- Cluster capacity matching the selected preset(s)
- A Kubernetes namespace where PostgreSQL, Redis, and the GitGuardian application will be installed.
  - Example: `kubectl create ns gitguardian`
- An image pull secret named `gim-replicated-registry` in `<namespace>` to download the PostgreSQL image:
  ```bash
  LICENSE_ID="<your_licenseID>"
  NAMESPACE=<namespace>
  echo "{\"auths\": {\"proxy.replicated.com\": {\"auth\": \"$(echo -n \"${LICENSE_ID}:${LICENSE_ID}\" | base64)\"}, \"registry.replicated.com\": {\"auth\": \"$(echo -n \"${LICENSE_ID}:${LICENSE_ID}\" | base64)\"}}}" > ~/.docker/config.json
  kubectl -n $NAMESPACE create secret generic gim-replicated-registry \
    --from-file=.dockerconfigjson=$HOME/.docker/config.json \
    --type=kubernetes.io/dockerconfigjson
  ```
  - If you need help obtaining your LICENSE_ID, contact support at support@gitguardian.com.

### Quick start

Use the commands below to install Bitnami charts with the preset values files. Replace `<namespace>` accordingly.

1) Add Bitnami repo (if not already added) and create/use a namespace:

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami && helm repo update
NAMESPACE=<namespace>
kubectl get ns "$NAMESPACE" >/dev/null 2>&1 || kubectl create ns "$NAMESPACE"
```

2) Optional: customize a values file

Edit the YAML presets under `values/postgres/` (and `values/redis/` later) to fit your environment. Typical edits include `auth.username`, `auth.database`, `persistence.storageClass`, `persistence.size`, and `resources`.

3) Install PostgreSQL (choose topology and size):

```bash
# Standalone (PoC/testing) - small preset
helm upgrade --install pg bitnami/postgresql \
  -n "$NAMESPACE" \
  -f helm-pg-redis/values/postgres/common.yaml \
  -f helm-pg-redis/values/postgres/standalone-small.yaml \
  --wait

# HA (recommended for production) - medium preset
helm upgrade --install pg bitnami/postgresql \
  -n "$NAMESPACE" \
  -f helm-pg-redis/values/postgres/common.yaml \
  -f helm-pg-redis/values/postgres/ha-medium.yaml \
  --wait
```

4) Install Redis (choose size):

```bash
# Standalone - small preset
helm upgrade --install redis bitnami/redis \
  -n "$NAMESPACE" \
  -f helm-pg-redis/values/redis/standalone-small.yaml \
  --wait

# Standalone - large preset
helm upgrade --install redis bitnami/redis \
  -n "$NAMESPACE" \
  -f helm-pg-redis/values/redis/standalone-large.yaml \
  --wait
```

5) Retrieve credentials and assemble connection strings:

```bash
NAMESPACE="$NAMESPACE"

# PostgreSQL
PG_RELEASE=pg
PG_PRIMARY_SERVICE="$PG_RELEASE-postgresql"
PG_PASSWORD=$(kubectl get secret -n "$NAMESPACE" "$PG_RELEASE-postgresql" -o jsonpath='{.data.postgres-password}' | base64 -d)
# Optional app user password if set via auth.password
PG_APP_PASSWORD=$(kubectl get secret -n "$NAMESPACE" "$PG_RELEASE-postgresql" -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)

echo "PostgreSQL host: $PG_PRIMARY_SERVICE.$NAMESPACE.svc.cluster.local:5432"
echo "PostgreSQL postgres user password: $PG_PASSWORD"
echo "PostgreSQL app user password (if configured): ${PG_APP_PASSWORD:-<not-set>}"

# Redis
REDIS_RELEASE=redis
REDIS_SERVICE="$REDIS_RELEASE-redis-master"   # standalone/replication master service
REDIS_PASSWORD=$(kubectl get secret -n "$NAMESPACE" "$REDIS_RELEASE-redis" -o jsonpath='{.data.redis-password}' | base64 -d)

echo "Redis host: $REDIS_SERVICE.$NAMESPACE.svc.cluster.local:6379"
echo "Redis password: $REDIS_PASSWORD"
```

### Using with GitGuardian

Provide these connection details to the GitGuardian application (via your Helm values for the GitGuardian chart, KOTS config, or environment):

For deploying GitGuardian in an existing Kubernetes cluster using Helm, follow the official guide: [Helm-based installation](https://docs.gitguardian.com/self-hosting/installation/installation-existing-helm).

- PostgreSQL
  - Note: The values below are example defaults and can be customized via `auth.username`, `auth.database`, and optionally `auth.password` in the values files.
  - Host: `<pg-release>-postgresql.<namespace>.svc.cluster.local`
  - Port: `5432`
  - Database: `gitguardian-db` (if using the provided values)
  - Username: `gitguardian-user` (if using the provided values) or `postgres`
  - Password: from secret above
  - Example URL: `postgresql://gitguardian-user:<password>@<host>:5432/gitguardian-db`

- Redis
  - Host: `<redis-release>-redis-master.<namespace>.svc.cluster.local`
  - Port: `6379`
  - Password: from secret above
  - Example URL: `redis://:<password>@<host>:6379/0`

If you use the PostgreSQL HA presets, the read service is also available (Bitnami creates a `-read` service for replicas). GitGuardian generally needs a single primary endpoint for writes; configure read/write splitting only if supported and desired within your environment.

### Uninstall

Replace $NAMESPACE accordingly.

```bash
helm uninstall pg -n $NAMESPACE || true
helm uninstall redis -n $NAMESPACE || true
```

This deletes only the Helm releases. PersistentVolumes may remain depending on your `reclaimPolicy` and release settings.
