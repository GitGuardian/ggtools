#!/bin/bash

set -euo pipefail

# Patches config-backup.yaml to be compatible with the embedded cluster:
#   - Injects DJANGO_SECRET_KEY from DJANGO.key
#   - Maps app_tls_kurl_options -> app_tls_options + app_exposure_mode
#   - Sets a random admin password (overwritten by DB restore anyway)
#
# Usage: ./patch-config.sh [-s|--self-signed]
#
#   -s, --self-signed   Force a KOTS-generated self-signed certificate
#                       (app_tls_disabled), ignoring the source TLS option.
#                       Use this when the source referenced an existing
#                       cert-manager / Let's Encrypt secret that won't exist on
#                       the fresh embedded cluster. Re-issue the real certificate
#                       and switch back to "use existing secret" after install.
#
# Expects: config-backup.yaml and DJANGO.key in the current directory

CONFIG="config-backup.yaml"
DJANGO_KEY_FILE="DJANGO.key"
SELF_SIGNED="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--self-signed) SELF_SIGNED="true"; shift ;;
    -h|--help) grep '^#' "$0" | grep -v '^#!' | sed 's/^# \?//'; exit 0 ;;
    *) echo "Error: unknown option '$1'"; exit 1 ;;
  esac
done

[[ -f "$CONFIG" ]]          || { echo "Error: $CONFIG not found."; exit 1; }
[[ -f "$DJANGO_KEY_FILE" ]] || { echo "Error: $DJANGO_KEY_FILE not found."; exit 1; }

DJANGO_SECRET_KEY=$(cat "$DJANGO_KEY_FILE")

TMPPY=$(mktemp /tmp/patch-config-XXXXXX.py)
trap "rm -f $TMPPY" EXIT

cat > "$TMPPY" <<'PYEOF'
import sys, yaml, secrets, string

config_file, django_key, self_signed = sys.argv[1], sys.argv[2], sys.argv[3] == 'true'
rand_pw = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(24))

TLS_MAP = {
    'app_tls_kurl_use_certificate':             'app_tls_use_certificate',
    'app_tls_kurl_use_existing_secret':         'app_tls_use_existing_secret',
    'app_tls_kurl_use_self_signed_certificate': 'app_tls_disabled',
}

with open(config_file) as f:
    cfg = yaml.safe_load(f)

values = cfg['spec']['values']

print("==> Injecting DJANGO_SECRET_KEY...")
values['django_secret_key'] = {'value': django_key}

print("==> Mapping TLS options...")
kurl_tls = (values.pop('app_tls_kurl_options', None) or {}).get('value', '')
if self_signed:
    tls_opt = 'app_tls_disabled'
    values['app_tls_options']   = {'value': tls_opt}
    values['app_exposure_mode'] = {'value': 'app_exposure_use_ingress'}
    print("TLS: forcing self-signed ({} -> {})".format(kurl_tls or '<none>', tls_opt))
elif kurl_tls:
    tls_opt = TLS_MAP.get(kurl_tls, 'app_tls_disabled')
    values['app_tls_options']   = {'value': tls_opt}
    values['app_exposure_mode'] = {'value': 'app_exposure_use_ingress'}
    print("TLS: {} -> {}".format(kurl_tls, tls_opt))
    if tls_opt == 'app_tls_use_existing_secret':
        print("WARNING: config references an EXISTING TLS secret that won't exist on a")
        print("         fresh embedded cluster -- the install will fail app preflights.")
        print("         Re-run with --self-signed (then re-issue the cert after install).")
else:
    print("WARNING: app_tls_kurl_options not found, skipping TLS mapping")

print("==> Setting random admin password...")
for field in ('admin_password', 'admin_password_check', 'admin_password_confirmation'):
    values[field] = {'value': rand_pw}

with open(config_file, 'w') as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

print("Done. {} is ready for embedded install.".format(config_file))
PYEOF

python3 "$TMPPY" "$CONFIG" "$DJANGO_SECRET_KEY" "$SELF_SIGNED"
