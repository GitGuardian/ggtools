# kURL to Embedded Migration

> **Heads-up on TLS certificates.** If the source install references an *existing* TLS
> secret managed by cert-manager / Let's Encrypt, read [step 6](#6-handle-an-existing-tls-certificate-cert-manager--lets-encrypt)
> **before** you start — it changes what you do in steps 3 and 8.

## 1. Set your namespace

```bash
KURL_NAMESPACE=default     # kURL namespace (used for backup)
```

## 2. Unscale Deployments

Scale down web app pods:

```bash
./scale.sh -p webapp -r 0 -n $KURL_NAMESPACE
```

Verify all Celery workers are idle:

```bash
kubectl exec -it deployment/worker-worker -c worker --namespace $KURL_NAMESPACE \
  -- celery -A ward_run_app inspect active
```

Expected output — all queues should be empty:

```
->  scanners@worker-scanners-85d5bc59d8-9vrg4: OK
    - empty -
->  worker@worker-worker-68dd895cbc-sgks9: OK
    - empty -
...
```

Scale down worker pods:

```bash
./scale.sh -p worker -r 0 -n $KURL_NAMESPACE
```

## 3. Backup

```bash
./backup.sh -n $KURL_NAMESPACE
./patch-config.sh
```

Produces `config-backup.yaml`, `db.sql.gz`, and `DJANGO.key` in the current directory.

> **If the source uses an existing cert-manager / LE certificate:** the backed-up
> config carries `app_tls_kurl_use_existing_secret`, which `patch-config.sh` maps to
> `app_tls_use_existing_secret`. That secret does **not** exist on a fresh embedded
> cluster, so the install will fail its app preflights (the script also prints a warning
> when it detects this). Run the patch with `--self-signed` instead, then re-issue the real
> certificate after install:
>
> ```bash
> ./patch-config.sh --self-signed
> ```
>
> See [step 6](#6-handle-an-existing-tls-certificate-cert-manager--lets-encrypt) for the
> full certificate workflow.

## 4. Nuke kURL

```bash
curl -sSL https://k8s.kurl.sh/latest/tasks.sh | sudo bash -s reset
```

## 5. Reclaim the Ceph disk (`gitguardian-seal` / rook-ceph installs only)

> **Skip this step** unless the source was a `gitguardian-seal` kURL install that used
> **rook-ceph** as the volume provider.

These installs reserved a large **raw** disk for Ceph. The new embedded cluster stores
its data under `/var/lib/embedded-cluster`, so reuse that disk for it. Do this **after**
purging kURL (step 4) and **before** installing the embedded cluster.

```bash
# Identify the raw disk Ceph was using (NOT the OS disk!)
lsblk

# Format it and mount it where the embedded cluster expects its data
sudo mkfs.ext4 /dev/sdX                       # replace sdX with the raw Ceph disk
sudo mkdir -p /var/lib/embedded-cluster
sudo mount /dev/sdX /var/lib/embedded-cluster

# Persist across reboots — prefer the disk UUID over /dev/sdX (device names can change)
UUID=$(sudo blkid -s UUID -o value /dev/sdX)
echo "UUID=$UUID  /var/lib/embedded-cluster  ext4  defaults  0  2" | sudo tee -a /etc/fstab

# Reboot and confirm it remounts automatically before continuing
sudo reboot
```

After reboot, verify with `mount | grep embedded-cluster` that the disk is mounted.

## 6. Handle an existing TLS certificate (cert-manager / Let's Encrypt)

> **Skip this step** unless the source instance referenced an **existing TLS secret**
> (e.g. a cert-manager-issued Let's Encrypt certificate) in its KOTS config.

This is a chicken-and-egg problem: the embedded installer fails the application preflights
because the referenced TLS secret doesn't exist yet, but cert-manager can't issue the
certificate because the cluster — and its ingress controller — don't exist until *after*
the install completes (the embedded installer brings up the ingress controller only after
the app is installed, so HTTP-01 validation isn't possible during install).

**Recommended approach** — install with a self-signed cert, then swap in the real one:

1. At step 3, patch the config with the `--self-signed` flag so the embedded install uses a
   **KOTS-generated self-signed certificate** instead of the missing secret:

   ```bash
   ./patch-config.sh --self-signed
   ```

   This forces `app_tls_options: app_tls_disabled` regardless of the source TLS setting, so
   the backed-up config won't reference a secret that doesn't exist yet.
2. Install the embedded cluster normally (step 8).
3. Once the cluster is up and the **ingress controller is installed**, install cert-manager
   and let it issue the Let's Encrypt certificate.
4. Switch the TLS config in KOTS back to **use existing secret**, point it at the issued
   secret name, and redeploy.

**Faster fallback:** run the installer with `--ignore-app-preflights` (see step 8). The
install completes despite the missing-secret preflight failure, and you fix the certificate
in a running cluster afterward.

## 7. (Optional) Create the customer on GitGuardian application

Only applicable for customer using `gitguardian-seal` app: Create a customer on `gitguardian` replicated app and use it from step 8.

## 8. Install Embedded

```bash
LICENSE_ID=YourLicenseID
CONSOLE_PASSWORD=UseYourOwnPassword

curl -f "https://replicated.app/embedded/gitguardian/stable" \
  -H "Authorization: $LICENSE_ID" \
  -o gitguardian.tgz

tar -xvzf gitguardian.tgz

sudo ./gitguardian install \
  --license license.yaml \
  --admin-console-password $CONSOLE_PASSWORD \
  --config-values ./config-backup.yaml
```

> **CIDR conflicts.** If the installer reports
> `The network range 10.244.0.0/16 is not available`, pass an alternative RFC-1918 `/16`
> (or larger) block with `--cidr`, e.g. `--cidr 172.16.0.0/16`. The embedded installer
> **only** accepts RFC-1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) — it
> rejects the `100.64.0.0/10` shared/CGNAT space even if the provider routes it for you.
> On nodes where the entire RFC-1918 space is already routed out an interface, you may have
> to pick an RFC-1918 range and accept the overlap.

> **Existing TLS certificate.** To let the install complete despite a missing TLS secret
> (see [step 6](#6-handle-an-existing-tls-certificate-cert-manager--lets-encrypt)), add
> `--ignore-app-preflights`, then fix the certificate in the running cluster.

> **Install failed with a generic error?** A bare
> `ERROR: install addons: install Admin Console: unable to install the application: exit status 1`
> gives no detail. The real cause is in the installer logs under **`/var/log/embedded-cluster/`**.

## 9. Wait for the app to be ready

```bash
./gitguardian shell
EMBEDDED_NAMESPACE=kotsadm
./wait-ready.sh -n $EMBEDDED_NAMESPACE
```

## 10. Scale down

```bash
./scale.sh -p webapp -r 0 -n $EMBEDDED_NAMESPACE
./scale.sh -p worker -r 0 -n $EMBEDDED_NAMESPACE
```

## 11. Restore DB

```bash
./restore.sh -n $EMBEDDED_NAMESPACE
```

## 12. Scale up the app

```bash
./scale.sh -p webapp -r 1 -n $EMBEDDED_NAMESPACE
./scale.sh -p worker -r 1 -n $EMBEDDED_NAMESPACE
```
</content>
</invoke>
