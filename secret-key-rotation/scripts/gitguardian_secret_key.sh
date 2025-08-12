#!/bin/bash

set -e


fetch_secret_keys() {
    # Fetch secret keys using provided namespace
    secret_key=$(kubectl get secret "${namespace[@]}" $secret_name \
                  -o jsonpath='{.data.DJANGO_SECRET_KEY}' | base64 --decode)
    encryption_keys=$(kubectl get secret "${namespace[@]}" $secret_name \
                  -o jsonpath='{.data.ENCRYPTION_KEYS}' | base64 --decode)
    echo "Django secret key hash: $(echo -n "$secret_key" | md5)"
    if [ -z "$encryption_keys" ]; then echo "No encryption keys found, Django secret key is thus used for DB encryption"; fi
    for key in ${encryption_keys//,/ }; do   # loop over comma separated
        echo "DB encryption key hash: $(echo -n "$key" | md5)"
    done
}

rotate_secret_keys() {
  echo "Starting rotation of encryption keys in namespace ${namespace[1]}"
  echo "After deployment, this will invalidate all current user sessions, as well as password reset links"
  echo "Complete rotation will be done after completion of all rotation jobs in admin area"
  echo "Do you want to continue? [yN]" && read -r confirm && [[ "$confirm" == [yY]  ]] || exit 1

  backup=$(mktemp)
  kubectl kots get config --appslug	$app_name "${namespace[@]}" --decrypt > "$backup"
  echo "Backup of KOTS config written to $backup"
  # Generate new django secret key
  new_django_key=$(LC_ALL=C tr -dc A-Za-z0-9 </dev/urandom | head -c 50 )
  echo "Setting new key with hash $(echo -n "$new_django_key" | md5)"
  current_key=$(kubectl get secret "${namespace[@]}" $secret_name \
                  -o jsonpath='{.data.DJANGO_SECRET_KEY}' | base64 --decode)
  current_encryption_keys=$(kubectl get secret "${namespace[@]}" $secret_name \
                -o jsonpath='{.data.ENCRYPTION_KEYS}' | base64 --decode)

  # new encryption starts with new key, that will be used for re-encryption, then current key for fallback
  if [ -n "$current_encryption_keys" ]; then
    new_encryption_keys=$(echo -n "$new_django_key,$current_encryption_keys,$current_key")
  else
    new_encryption_keys=$(echo -n "$new_django_key,$current_key")
  fi
  config_values=$(mktemp)
  trap "rm -f $config_values" EXIT
  cat <<EOF > "$config_values"
apiVersion: kots.io/v1beta1
kind: ConfigValues
spec:
  values:
    django_secret_key:
      value: $new_django_key
    db_encryption_keys:
      value: $new_encryption_keys
EOF

  # Set it directly in KOTS config values
  kubectl kots set config $app_name "${namespace[@]}"  \
              --config-file "$config_values" --merge

  echo "App configuration is updated with new keys"
  echo "Please go to the admin console and deploy the new version"
  echo "When completed, go to the admin area to perform the rotation of the database encrypted fields"
  echo "Do you want to launch admin console now? [yN]" && read -r launch
  [[ "$launch" == [yY]  ]] && kubectl kots admin-console "${namespace[@]}"
}

namespace=()

usage() {
  echo "GitGuardian secrets rotation"
  echo "Usage: $0 [--namespace NAMESPACE] (status|rotate)"
  exit 0
}

# Parse command line options
while [[ $# -gt 0 ]]
do
    key="$1"
    case $key in
        --namespace|-n)
            namespace=( "--namespace" "$2" )
            shift # past argument
            shift # past value
            ;;
        status)
            action=fetch_secret_keys
            shift # past argument
            ;;
        rotate)
            action=rotate_secret_keys
            shift # past argument
            ;;
        --help|-h|help)
            usage=1
            shift ;;
        *)
            # Unknown option
            echo "Unknown action: $key"
            ;;
    esac
done

[ -n "$usage" ] && usage
if [ -z "$action" ] && [ -z "$usage" ]; then echo "No action specified"; exit 1; fi
if [ -z "${namespace[*]}" ]; then echo "No namespace specified"; exit 1; fi

app_name=$(kubectl kots get apps "${namespace[@]}" | cut -d ' ' -f 1 | tail -n 1)

case "$app_name" in
  gitguardian-seal)  # v1 legacy
    secret_name="gitguardian-env-variables" ;;
  gitguardian)       # v2
    secret_name="gim-secrets" ;;
  *)
    echo "Unknown app name: $app_name" && exit 1 ;;
esac

[ -n "$action" ] && eval "$action"
