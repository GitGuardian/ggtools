### Helm: PostgreSQL and Redis for GitGuardian

This folder provides ready-to-use Helm configurations to deploy PostgreSQL and Redis in your Kubernetes cluster for use with the GitGuardian application.

- PostgreSQL topologies:
  - **HA (replication)**: primary with read replica(s); recommended for production for resilience and read scaling.
  - **Standalone**: single-primary setup; suitable for PoC or testing only.
- Redis topology:
  - **Standalone** with persistence (aligned with the scaling guide). If you require Redis replication/sentinel, extend these values as needed.
- All presets are available in three sizes aligned with the GitGuardian scaling guide: **small**, **medium**, **large**.

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

The scripts below install Bitnami charts using the preset values files. They also create the target namespace when missing.

1) Add Bitnami repo (if not already added):

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami && helm repo update
```

2) Install PostgreSQL (choose topology and size):

```bash
# Examples
./scripts/install-postgres.sh standalone small           # standalone small
./scripts/install-postgres.sh ha medium gg-datastores pg # HA medium in ns gg-datastores, release name pg
```

3) Install Redis (choose size):

```bash
# Examples
./scripts/install-redis.sh standalone small
./scripts/install-redis.sh standalone large gg-datastores redis
```

4) Retrieve credentials and assemble connection strings:

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

### How to customize the values files

You can either edit one of the preset files in `values/` or keep presets immutable and layer your own overrides file(s) at install time.

1) Create an overrides file (example for PostgreSQL HA):

```yaml
# my-postgres-overrides.yaml
auth:
  username: gitguardian-user
  database: gitguardian-db
  # password: "<set-a-strong-password>" # optional; if omitted, Bitnami autogenerates one

primary:
  persistence:
    storageClass: fast-ssd
    size: 350Gi
  resources:
    requests:
      cpu: 12000m
      memory: 48Gi
    limits:
      cpu: 16000m
      memory: 64Gi

readReplicas:
  replicaCount: 2
  persistence:
    storageClass: fast-ssd
    size: 300Gi
  resources:
    requests:
      cpu: 6000m
      memory: 24Gi
    limits:
      cpu: 8000m
      memory: 32Gi
```

2) Install by layering your overrides on top of a preset:

```bash
./scripts/install-postgres.sh ha large gg-datastores pg
helm upgrade --install pg bitnami/postgresql \
  -n gg-datastores \
  -f helm-pg-redis/values/postgres/ha-large.yaml \
  -f my-postgres-overrides.yaml \
  --wait
```

3) One-off tweaks via --set (useful for small changes):

```bash
helm upgrade --install pg bitnami/postgresql \
  -n gg-datastores \
  -f helm-pg-redis/values/postgres/ha-medium.yaml \
  --set primary.persistence.storageClass=gp3 \
  --set auth.username=gitguardian-user \
  --set auth.database=gitguardian-db \
  --wait
```

Redis follows the same approach (see `values/redis/`). Common customizations:

- Set a fixed password: `auth.password: <your-password>` (otherwise autogenerated)
- Change storage class/size: `master.persistence.storageClass`, `master.persistence.size`
- Tune resources: `master.resources.requests/limits`

### Uninstall

```bash
./scripts/uninstall.sh gg-datastores pg redis
```

This deletes only the Helm releases. PersistentVolumes may remain depending on your `reclaimPolicy` and release settings.


