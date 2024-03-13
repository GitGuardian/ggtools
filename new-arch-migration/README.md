# Migrating from the legacy to the new Architecture

To initiate the migration process or if you have any questions regarding the new architecture, please reach out to our [support team](mailto:support@gitguardian.com?subject=Migration+New+Architecture). We aim for a smooth migration process to enhance your GitGuardian setup with a future-ready, secure, and scalable architecture that aligns with the demands of modern cloud environments.

Explore the [New Architecture documentation](https://docs.gitguardian.com/self-hosting/new-architecture) for a deep dive into its advantages, including enhanced performance, security, and scalability features. Our guide provides a thorough understanding of the architectural upgrades and the additional benefits of switching to the new architecture of GitGuardian.

Migration can be approached in two ways to best suit your operational needs:
- [In-place migration with external databases](#in-place-migration-with-external-databases) (approx. 1 hour of downtime)
- [Blue/green migration with external databases](#bluegreen-migration-with-external-databases) (no downtime)

Understanding the distinction between in-place and blue/green migration is crucial before proceeding with the guide. These strategies facilitate the shift from the legacy to the new architecture:

- **In-Place Migration**: This method migrates GitGuardian to a new architecture within the same Kubernetes namespace, resulting in approximately up to 1 hour of downtime.
- **Blue/Green Migration**: Unlike in-place migration, this strategy sets up a parallel "green" environment in a new Kubernetes namespace to deploy GitGuardian's new architecture version, enabling a transition with zero downtime.

Review and discuss both migration methods and reach out to our [support team](mailto:support@gitguardian.com?subject=Migration+New+Architecture) for tailored guidance and support throughout the transition process.

## Application Topology Changes

We have updated the names of specific containers in the GitGuardian Kubernetes deployment. This change could impact you if your custom monitoring solutions are closely linked to the specific names of these containers. We highly recommend reviewing the [side-by-side application topology page](./TOPOLOGY.md) to understand the differences between the 2 architectures. This will help you anticipate and adjust your monitoring setups accordingly.

## Requirements

GitGuardian provides a set of scripts that require specific tools to be installed on your host to facilitate application migration:

- [kubectl](https://kubernetes.io/docs/tasks/tools/#kubectl) (version ≥ 1.27.0)
- [kubectl kots plugin](https://docs.replicated.com/reference/kots-cli-getting-started#install) (version ≥ 1.107.7)
- [yq](https://mikefarah.gitbook.io/yq/) (Only for Blue/Green Migration)

You need to be an administrator of the GitGuardian namespace where the application is deployed.

The new version must use the same GitGuardian version as the legacy version. Please ensure you have the latest legacy version installed before upgrading to the new version.

⚠️ The GitGuardian team needs to update your license information (Channel switching from `prod` to `stable`) to provide you with the new architecture of the application, so you need to [sync with them](?subject=Migration+New+Architecture+in+place+migration+external) before upgrading.

## In-place migration with external databases

⚠️ Please note, this migration guide is specifically designed for customers who have installed GitGuardian on an [existing Kubernetes cluster with an external database](https://docs.gitguardian.com/self-hosting/installation/installation-existing-cluster-legacy). If your GitGuardian instance is running on an embedded cluster, visit this [page](./EMBEDDED.md).

⚠️ This migration will require some downtime, which may take up to one hour.

ℹ️ For airgap installation, first, download the airgap bundle file from your download portal.

1. To begin with, please create a backup of your GitGuardian's external PostgreSQL database.
2. You can now migrate GitGuardian to the new architecture using the following command line:
        
    ```bash
    # For Online installation
    ./migrate.sh --namespace <gitguardian_namespace> \
    --deploy

    # For Airgap installation
    ./migrate.sh --namespace <gitguardian_namespace> \
    --airgap-bundle <new_arch-version-airgap--bundle-file> \
    --deploy
    ```

    *Expected result:*

    ```bash
    => Migrate GitGuardian application
        • Checking for application updates ✓  

        • There are currently 1 updates available in the Admin Console, ensuring latest is deployed

        • To access the Admin Console, run kubectl kots admin-console --namespace <gitguardian_namespace>

        • Currently deployed release: sequence <N>, version YYYY.MM.PATCH
        • Downloading available release: sequence <N>, version YYYY.MM.PATCH
        • Deploying release: sequence <N>, version YYYY.MM.PATCH
    OK
    ```
    
Et voilà! You should access to your GitGuardian dashboard.

### Rollback procedure

If you encounter any blocking issues after the migration, you can rollback to the legacy architecture.

⚠️ You need first to synchronize with the GitGuardian team before running the following steps in order to update your license information.

Once the GitGuardian team has updated your license, you can rollback GitGuardian using the following command line:

```bash
# For Online installation
./migrate.sh --namespace <gitguardian_namespace> \
--deploy

# For Airgap installation
./migrate.sh --namespace <gitguardian_namespace> \
--airgap-bundle <new_airgap--bundle-file> \
--deploy
```

ℹ️ To avoid any conflicts during the migration, it will first uninstall all existing releases based on the new architecture in `<gitguardian_namespace>`.

*Expected result:*

```bash
=> Retrieve kots admin pod
OK

=> Retrieve helm releases
OK

=> Uninstall gitguardian Helm release
release "gitguardian" uninstalled
OK

=> Uninstall postgresql Helm release
release "postgresql" uninstalled
OK

=> Uninstall redis Helm release
release "redis" uninstalled
OK

=> Migrate GitGuardian application
    • Checking for application updates ✓  

    • There are currently 1 updates available in the Admin Console, ensuring latest is deployed

    • To access the Admin Console, run kubectl kots admin-console --namespace <gitguardian_namespace>

    • Currently deployed release: sequence <N>, version YYYY.MM.PATCH
    • Downloading available release: sequence <N>, version YYYY.MM.PATCH
    • Deploying release: sequence <N>, version YYYY.MM.PATCH
OK
```

ℹ️ Please note that the deployment process will continue for a few minutes after the script has ended.

You should have now access to your GitGuardian dashboard.

## Blue/green migration with external databases

💁‍♂️ Please note that you will need to [contact GitGuardian](mailto:support@gitguardian.com?subject=Migration+New+Architecture-blue-green) to obtain a new license YAML file.

💡 This migration automates deploying a new KOTS instance with the new architecture, using your legacy KOTS configuration. If you wish to transition from KOTS to Helm, manual recreation of the `values.yaml` file is necessary for redeployment. For assistance, [contact GitGuardian](mailto:support@gitguardian.com?subject=Migration+New+Architecture-blue-green+helm+only),

This migration will deploy a new version of GitGuardian in a separate namespace in the same existing cluster, alongside the current namespace containing the legacy GitGuardian application, so that this will prevent any downtime during the deployment of the new application. This is not possible to do the blue/green migration in the same namespace. The two versions of the application will use the same external databases.

At the end of the deployment, depending on how you expose the application (Ingress, LoadBalancer), you will need to switch traffic to the new application.

1. Run the `bg-migrate.sh` script to deploy the new application

    ```bash
    # For online installation
    ./bg-migrate.sh \
      --v1-namespace <legacy_namespace> \
      --v2-namespace <new_namespace> \
      --license-file <v2_license_file> \
      --shared-password "<kots_new_admin_password>" \
      --set "app_hostname=<new_app_hostname>"

    # For airgap installation
    ./bg-migrate.sh \
      --v1-namespace <legacy_namespace> \
      --v2-namespace <new_namespace> \
      --airgap-bundle <new_airgap--bundle-file> \
      --license-file <new_license_file> \
      --shared-password "<kots_new_admin_password>" \
      --set "app_hostname=<new_app_hostname>"
    ```

    ℹ️ The script will perform the following steps:
    - Retrieve the legacy KOTS configuration from the specified legacy namespace.
    - In order to expose the new application alongside the legacy one, you need to update the KOTS configuration that was extracted from legacy and update the application hostname. Here it is done using `--set "app_hostname=<new_app_hostname>"`.
    - Deploy the new application in the specified new namespace (Will create it if not exists).

    *Expected result:*

    ```yaml
    => Retrieve V1 kots configuration
    OK

    => Set app_hostname in kots configuration
    OK

    => Install V2 application
      • Deploying Admin Console
        • Creating namespace ✓  
        • Waiting for datastore to be ready ✓  
      • Waiting for Admin Console to be ready ✓  
      • Waiting for installation to complete ✓  
    OK
    ```

2. Once you are ready to switch the traffic to the new application:

    Scale down the legacy application
        
    ```yaml
    ./scale.sh --namespace <v1_namespace> \ 
      --v1 \
      --all \
      --replicas 0
    ```
        
    *Expected result:*
        
    ```yaml
    => Retrieve GitGuardian deployments
    OK

    => Scale deployment.apps/redis to 0 replicas
    OK

    => Scale deployment.apps/postgresql to 0 replicas
    OK

    => Scale deployment.apps/gitguardian-scanner-ods to 0 replicas
    OK

    => Scale deployment.apps/gitguardian-worker to 0 replicas
    OK

    => Scale deployment.apps/gitguardian-long-tasks to 0 replicas
    OK

    => Scale deployment.apps/gitguardian-scanner to 0 replicas
    OK

    => Scale deployment.apps/gitguardian-email to 0 replicas
    OK

    => Scale deployment.apps/gitguardian-beat to 0 replicas
    OK

    => Scale deployment.apps/gitguardian-app to 0 replicas
    OK
    ```
    
3. Update the new application hostname and deploy the new configuration using this command:
        
    ```yaml
    ./update-config.sh --namespace <new_namespace> \
        --set "app_hostname=<app_hostname>" \
        --deploy
    ```

    Should you prefer using a `LoadBalancer` service over a `ClusterIP`, please adjust your [annotations](https://docs.gitguardian.com/self-hosting/management/infrastructure-management/load-balancer#kots-based-installation) accordingly.

    You should have now access to your GitGuardian dashboard.

4. Once you've verified that your GitGuardian application is functioning correctly, you may proceed to delete the legacy namespac in your kubernetes cluster. Please be aware that deleting the namespace will prevent any possibility of reverting to the legacy application.
