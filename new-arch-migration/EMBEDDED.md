# In-place migration with embedded databases

## Requirements

GitGuardian provides a set of scripts that require specific tools to be installed on your host to facilitate application migration:

- [git](https://git-scm.com/downloads)
- [kubectl](https://kubernetes.io/docs/tasks/tools/#kubectl) (version ≥ 1.27.0)
- [kubectl kots plugin](https://docs.replicated.com/reference/kots-cli-getting-started#install) (version ≥ 1.107.7)
- [yq](https://mikefarah.gitbook.io/yq/) (Only for Blue/Green Migration)

You need to be an administrator of the GitGuardian namespace where the application is deployed.

⚠️ Please ensure you have the latest legacy version installed before upgrading to the new architecture.

⚠️ The GitGuardian team needs to update your license information (Channel switching from `prod` to `stable`) to give you access to the new architecture, so you need to [sync with them](?subject=Migration+New+Architecture+in+place+migration+external) before upgrading.

⚠️ Please note, this migration guide is specifically designed for customers who have installed GitGuardian on an [embedded Kubernetes cluster with an embedded database](https://docs.gitguardian.com/self-hosting/installation/installation-embedded-cluster-legacy). If your GitGuardian instance is running on an existing cluster, visit this [page](./README.md).

## Migration Procedure

⚠️ This migration requires downtime, the duration of which depends on your environment and the size of the GitGuardian PostgreSQL database, as it involves backing up and restoring the database.

1. Save the Data Encryption Key and keep it in **a secure location**. Use the following command to display the key:

    ```bash
    kubectl get secrets gitguardian-env-variables -o jsonpath='{.data.DJANGO_SECRET_KEY}' | base64 -d
    ```

2. Clone the ggtools repository.

    ```bash
    git clone https://github.com/GitGuardian/ggtools.git
    cd ggtools/new-arch-migration/scripts
    ```

3. Scale down the GitGuardian app deployment to make the application inaccessible, allowing workers to process remaining tasks.

    ```bash
    ./scale.sh --v1 \
        --namespace default \
        --component app \
        --replicas 0
    ```

    **Expected result:**

    ```bash
    => Retrieve the GitGuardian app component
    OK

    => Scale GitGuardian app component to 0 replicas
    OK
    ```

4. Verify all asynchronous tasks are completed by running the following command until the expected result is obtained:

    ```bash
    ./inspect-workers.sh --v1 --namespace default
    ```

    **Expected result:**

    ```bash
    => Retrieve GitGuardian worker deployment
    OK

    => Inspect workers...
    ->  workers@gitguardian-worker-594874fc65-t84t6: OK
        - empty -
    ->  scanner@gitguardian-scanner-77754cc999-sg2nl: OK
        - empty -
    ->  long_tasks@gitguardian-long-tasks-c5d7cf4cc-l27sf: OK
        - empty -
    ->  scanner-ods@gitguardian-scanner-ods-5b9799d98f-kdn4k: OK
        - empty -

    4 nodes online.
    ```

    Each worker should return: `- empty -`

5. Scale down workers to free up cpu/memory

    ```bash
    ./scale.sh --v1 \
        --namespace default \
        --component worker \
        --component scanner \
        --component long-tasks \
        --component email \
        --replicas 0
    ```

    **Expected result:**

    ```bash
    => Retrieve the GitGuardian worker component
    OK

    => Scale GitGuardian worker component to 0 replicas
    OK

    => Retrieve the GitGuardian scanner component
    OK

    => Scale GitGuardian scanner component to 0 replicas
    OK  

    => Retrieve the GitGuardian long-tasks component
    OK

    => Scale GitGuardian long-tasks component to 0 replicas
    OK  

    => Retrieve the GitGuardian email component
    OK

    => Scale GitGuardian email component to 0 replicas
    OK            
    ```

6. Backup the GitGuardian PostgreSQL database.

    ```bash
    ./backup-db.sh --v1 --namespace default \
        -o pg-dump-gitguardian-v1-$(date +'%Y%m%d_%H%M%S').gz
    ```

    **Expected result:**

    ```bash
    => Retrieve PostgreSQL k8s resource
    OK

    => Create a backup of the GitGuardian database
    OK

    Backup successfully created at ***pg-dump-gitguardian-v1-20240223_162744.gz***
    ```

7. Migrate GitGuardian to the new architecture with the following command:

    ```bash
    ./migrate.sh --namespace default --deploy
    ```

    **Expected result:**

    ```bash
    => Migrate GitGuardian application
        • Checking for application updates ✓  

        • There are currently 1 updates available in the Admin Console, ensuring latest is deployed

        • To access the Admin Console, run kubectl kots admin-console --namespace default

        • Currently deployed release: sequence <N>, version YYYY.MM.PATCH
        • Downloading available release: sequence <N>, version YYYY.MM.PATCH
        • Deploying release: sequence <N>, version YYYY.MM.PATCH
    OK
    ```

8. Restore the database dump with:

    ```bash
    ./restore-db.sh \
        --namespace default \
        -i <pg-dump-gitguardian-v1-YYYYmmDD_HHMMSS.gz>
    ```

    **Expected result:**

    ```bash
    => Retrieve PostgreSQL pod
    OK

    => Restore the GitGuardian DB
    OK

    DB successfully restored from <pg-dump-gitguardian-v1-YYYYmmDD_HHMMSS.gz>
    ```

You should have now access to your GitGuardian dashboard.

## Rollback Procedure for embedded databases

If you encounter issues after migration, you can rollback to the legacy architecture.

⚠️ Coordinate with the GitGuardian team to update your license information before proceeding with the rollback.

1. Optional: Create a new backup of the PostgreSQL database (or use your legacy database backup).

    ```bash
    ./scale.sh \
        --namespace default \
        --component hook \
        --component internal-api \
        --component internal-api-long \
        --component public-api \
        --replicas 0
    ```

    **Expected result:**

    ```bash
    => Scale GitGuardian components to 0 replicas
    OK
    ```

2. Verify all workers are idle:

    ```bash
    ./inspect-workers.sh --namespace default
    ```

    **Expected result:**

    ```bash
    => All workers report: - empty -
    OK
    ```

3. Backup the GitGuardian PostgreSQL database:

    ```bash
    ./backup-db.sh --namespace default \
        -o pg-dump-gitguardian-v2-$(date +'%Y%m%d_%H%M%S').gz
    ```

    **Expected result:**

    ```bash
    Backup successfully created at ***pg-dump-gitguardian-v2-20240223_172744.gz***
    ```

4. After updating your license, rollback GitGuardian to the legacy architecture:

    ```bash
    ./migrate.sh --namespace default --prune --deploy
    ```

    **Expected result:**

    ```bash
    => Uninstall and reinstall GitGuardian application
    OK
    ```

5. Restore the PostgreSQL dump:

    ```bash
    ./restore-db.sh \
        --v1 \
        --namespace default \
        -i <pg-dump-gitguardian-vX-YYYYmmDD_HHMMSS.gz>
    ```

    **Expected result:**

    ```bash
    DB successfully restored from <pg-dump-gitguardian-v1-YYYYmmDD_HHMMSS.gz>
    ```

You should have now access to your GitGuardian dashboard.
