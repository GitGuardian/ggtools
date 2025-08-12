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

- AWS: Amazon RDS/Aurora (PostgreSQL), Amazon ElastiCache/MemoryDB (Redis)
- GCP: Cloud SQL for PostgreSQL, Memorystore for Redis
- Azure: Azure Database for PostgreSQL, Azure Cache for Redis

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

### Quick start

Use the commands below to install Bitnami charts with the preset values files. Create the target namespace if missing.

1) Add Bitnami repo (if not already added) and create a namespace:

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami && helm repo update
kubectl get ns gg-datastores >/dev/null 2>&1 || kubectl create ns gg-datastores
```

2) Optional: customize a values file

Edit the YAML presets under `values/postgres/` (and `values/redis/` later) to fit your environment. Typical edits include `auth.username`, `auth.database`, `persistence.storageClass`, `persistence.size`, and `resources`.

3) Install PostgreSQL (choose topology and size):

```bash
# Standalone (PoC/testing) - small preset
helm upgrade --install pg bitnami/postgresql \
  -n gg-datastores \
  -f helm-pg-redis/values/postgres/standalone-small.yaml \
  --wait

# HA (recommended for production) - medium preset
helm upgrade --install pg bitnami/postgresql \
  -n gg-datastores \
  -f helm-pg-redis/values/postgres/ha-medium.yaml \
  --wait
```

4) Install Redis (choose size):

```bash
# Standalone - small preset
helm upgrade --install redis bitnami/redis \
  -n gg-datastores \
  -f helm-pg-redis/values/redis/standalone-small.yaml \
  --wait

# Standalone - large preset
helm upgrade --install redis bitnami/redis \
  -n gg-datastores \
  -f helm-pg-redis/values/redis/standalone-large.yaml \
  --wait
```

5) Retrieve credentials and assemble connection strings:

```bash
NAMESPACE=gg-datastores

# PostgreSQL (Bitnami postgresql)
PG_RELEASE=pg
PG_PRIMARY_SERVICE="$PG_RELEASE-postgresql"
PG_PASSWORD=$(kubectl get secret -n "$NAMESPACE" "$PG_RELEASE-postgresql" -o jsonpath='{.data.postgres-password}' | base64 -d)
# Optional app user password if set via auth.password
PG_APP_PASSWORD=$(kubectl get secret -n "$NAMESPACE" "$PG_RELEASE-postgresql" -o jsonpath='{.data.password}' 2>/dev/null | base64 -d || true)

echo "PostgreSQL host: $PG_PRIMARY_SERVICE.$NAMESPACE.svc.cluster.local:5432"
echo "PostgreSQL postgres user password: $PG_PASSWORD"
echo "PostgreSQL app user password (if configured): ${PG_APP_PASSWORD:-<not-set>}"

# Redis (Bitnami redis)
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

### Customization

- To change storage class, set `primary.persistence.storageClass` (PostgreSQL) or `master.persistence.storageClass` (Redis). For HA, also set the replica persistence storage class.
- To change size, either switch to another preset file or adjust `resources.requests/limits` and `persistence.size` entries.
- To change database/user names and passwords, edit the `auth.*` block in the PostgreSQL values files. For Redis, set `auth.password` if you want a fixed password.

### Customization

- Edit the YAML presets directly under `values/postgres/` and `values/redis/` to match your environment.
- Common fields: `auth.username`, `auth.database`, `auth.password` (optional), `persistence.storageClass`, `persistence.size`, `resources.requests/limits`.

### Uninstall

```bash
helm uninstall pg -n gg-datastores || true
helm uninstall redis -n gg-datastores || true
```

This deletes only the Helm releases. PersistentVolumes may remain depending on your `reclaimPolicy` and release settings.


