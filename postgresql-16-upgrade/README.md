# PostgreSQL 16 Upgrade (KOTS only)

For customers using embedded PostgreSQL database, with GitGuardian version `2024.7.0`, we are moving from PostgreSQL version 13 to version 16.

In order to perform the update, it is necessary to first create a backup of the data, which will then be restored after the GitGuardian update. We provide a set of scripts that will allow you to perform this migration.

## Upgrade procedure

### Clone ggotools repository

```shell
git clone https://github.com/GitGuardian/ggtools.git
cd ggtools/postgresql-16-upgrade/scripts
```

### Backup PostgreSQL data

First, you need to dump data using the `backup.sh` script:

```shell
./backup.sh --namespace <gitguardian_namespace> --output </path/to/pg_dump.sql.gz>
```

The script will perform the following steps:

  1. Retrieve the current GitGuardian version using `kubectl`.
  2. Retrieve PostgreSQL running Pod using `kubectl`
  3. Dump the Gitguardian data to the specified path on your desktop using the `--output` option (Data is compressed using `gzip`)
  4. Create a ConfigMap called `postgresql-backup` in the `<gitguardian_namespace>` which contains the following informations:
     - Backup file MD5 hash
     - Backup status
     - Backup date (ISO format)
     - GitGuardian application current version

### Update GitGuardian application

From the KOTS admin console you can now update the GitGuardian application.

:vertical_traffic_light: A preflight check called `PostgreSQL 16 Upgrade` will ensure that the backup was executed correctly by checking the configMap `postgresql-bakcup`.

### Restore PostgreSQL backuped data

Once, the applications update has succesfully completed, you can restore the data using the `restore.sh` script:

```shell
./restore.sh --namespace <gitguardian_namespace> --input </path/to/pg_dump.sql.gz>
```

The script will perform the following steps:

  1. Check that the specified backup file MD5 hash matches the one specified in the configMap `postgresql-backup`
  2. Retrieve PostgreSQL running Pod using `kubectl`.
  3. Scale down all the GitGuardian application Deployments.
  4. Restore the GitGuardian PostgreSQL data.
  5. Scale up all the GitGuardian application Deployments.
  6. Migrate the GitGuardian database with the new application version.
