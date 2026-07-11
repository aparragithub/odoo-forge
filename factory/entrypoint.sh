#!/bin/bash
set -e

# =============================================================================
# Odoo Forge — base image entrypoint (one image, two environments)
# =============================================================================

ODOO_RC=${ODOO_RC:-/etc/odoo/odoo.conf}
TEMP_ODOO_RC="/tmp/odoo.conf"

if [ ! -f "$ODOO_RC" ]; then
    echo "ERROR: Odoo configuration file not found at $ODOO_RC" >&2
    exit 1
fi

# Copy to a temp file so the mounted template can be read-only.
cp "$ODOO_RC" "$TEMP_ODOO_RC"
chmod 600 "$TEMP_ODOO_RC"

if [[ -z "${ODOO_ADMIN_PASSWD}" ]]; then
    ODOO_ADMIN_PASSWD=$(/opt/venv/bin/python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "NOTICE: ODOO_ADMIN_PASSWD auto-generated (set the env var to use a fixed value)"
fi

# ─── Safe config injection ──────────────────────────────────
# Replaces a "key = value" line in $TEMP_ODOO_RC via Python (value passed
# through the environment, never interpolated into a shell/regex string), so
# values containing "|", "&", "\" or any other sed/regex metacharacter are
# handled safely. Fails loudly if the key is not present in the template,
# instead of silently no-op'ing like a sed miss would.
set_conf() {
    local key="$1"
    local value="$2"
    if ! ODOO_CONF_KEY="$key" ODOO_CONF_VALUE="$value" /opt/venv/bin/python3 - "$TEMP_ODOO_RC" <<'PYEOF'
import os
import re
import sys
import tempfile

path = sys.argv[1]
key = os.environ["ODOO_CONF_KEY"]
value = os.environ["ODOO_CONF_VALUE"]

if "\n" in value:
    print(f"ERROR: value for config key '{key}' contains a newline; refusing to write (would corrupt {path})", file=sys.stderr)
    sys.exit(1)

pattern = re.compile(r"^" + re.escape(key) + r"\s*=.*$", re.MULTILINE)

with open(path, "r") as f:
    content = f.read()

new_content, count = pattern.subn(lambda m: f"{key} = {value}", content, count=1)
if count == 0:
    print(f"ERROR: config key '{key}' not found in {path}", file=sys.stderr)
    sys.exit(1)

# Atomic write: write to a temp file in the same directory, then os.replace()
# so a mid-write I/O failure can never leave a half-written config on disk.
directory = os.path.dirname(path) or "."
fd, tmp_path = tempfile.mkstemp(dir=directory)
try:
    with os.fdopen(fd, "w") as f:
        f.write(new_content)
    os.replace(tmp_path, path)
except Exception:
    os.unlink(tmp_path)
    raise
PYEOF
    then
        echo "ERROR: failed to set config key '${key}' in ${TEMP_ODOO_RC}" >&2
        exit 1
    fi
}

# ─── Build dynamic addons_path ──────────────────────────────
# Scan mounted layer dirs for Odoo modules (__manifest__.py). A base image
# ships none of these populated; higher layers / the local backend mount them.
build_addons_path() {
    local paths=""
    local base dir
    for base in /mnt/worktrees /mnt/custom /mnt/community /mnt/localization /mnt/enterprise; do
        if [ -d "$base" ]; then
            while IFS= read -r dir; do
                paths="${paths}${dir},"
            done < <(find "$base" -name '__manifest__.py' -type f 2>/dev/null | while read -r manifest; do dirname "$(dirname "$manifest")"; done | sort -u)
        fi
    done
    paths="${paths}/opt/odoo/addons"
    echo "$paths"
}

DYNAMIC_ADDONS_PATH=$(build_addons_path)
echo "addons_path: ${DYNAMIC_ADDONS_PATH}" >&2

run_odoo() {
    if [[ -n "${ODOO_DEBUG_PORT}" ]]; then
        if [[ "${ODOO_WORKERS:-0}" != "0" ]]; then
            echo "WARNING: debugpy requires workers=0. Forcing workers=0." >&2
            set_conf workers 0
        fi
        echo "NOTICE: Debug mode enabled on port ${ODOO_DEBUG_PORT}"
        exec /opt/venv/bin/python3 -m debugpy --listen 0.0.0.0:"${ODOO_DEBUG_PORT}" \
            /usr/local/bin/odoo "$@"
    else
        exec odoo "$@"
    fi
}

# Config injection (one image, two environments).
set_conf admin_passwd "${ODOO_ADMIN_PASSWD}"
set_conf workers "${ODOO_WORKERS:-0}"
set_conf log_level "${ODOO_LOG_LEVEL:-info}"
set_conf list_db "${ODOO_LIST_DB:-True}"
set_conf dbfilter "${ODOO_DB_FILTER:-.*}"
set_conf without_demo "${ODOO_WITHOUT_DEMO:-True}"
set_conf proxy_mode "${ODOO_PROXY_MODE:-True}"
set_conf smtp_server "${SMTP_SERVER:-localhost}"
set_conf smtp_port "${SMTP_PORT:-25}"
set_conf addons_path "${DYNAMIC_ADDONS_PATH}"

export ODOO_RC="$TEMP_ODOO_RC"

# True when the arguments are a pure diagnostic invocation (--version,
# --help/-h) rather than an actual server launch. These must exec immediately
# with no DB dependency, even though they are dispatched through the
# `odoo`/`--*` branches below.
is_diagnostic_cmd() {
    local arg
    for arg in "$@"; do
        case "$arg" in
            --version | --help | -h)
                return 0
                ;;
        esac
    done
    return 1
}

# Builds DB_ARGS and waits for PostgreSQL to accept connections. Only relevant
# when we are actually about to launch the Odoo server — arbitrary commands
# (e.g. `bash`, `odoo --version`) must exec immediately with no DB dependency.
wait_for_db() {
    DB_HOST=${DB_HOST:-${POSTGRES_HOST:-db}}
    DB_PORT=${DB_PORT:-${POSTGRES_PORT:-5432}}
    DB_USER=${DB_USER:-${POSTGRES_USER:-odoo}}
    DB_PASSWORD=${DB_PASSWORD:-${POSTGRES_PASSWORD:-odoo}}
    DB_ARGS=()
    DB_ARGS+=( "--db_host" "${DB_HOST}" )
    DB_ARGS+=( "--db_port" "${DB_PORT}" )
    DB_ARGS+=( "--db_user" "${DB_USER}" )
    DB_ARGS+=( "--db_password" "${DB_PASSWORD}" )
    DB_ARGS+=( "--database" "${POSTGRES_DB:-postgres}" )

    echo "Waiting for PostgreSQL at ${DB_HOST}..."
    /opt/venv/bin/python3 /usr/local/bin/wait-for-psql.py \
        --db_host "${DB_HOST}" --db_port "${DB_PORT}" --db_user "${DB_USER}" \
        --db_password "${DB_PASSWORD}" --database "${POSTGRES_DB:-postgres}" --timeout=60
}

case "$1" in
    -- | odoo)
        shift
        if is_diagnostic_cmd "$@"; then
            run_odoo "$@"
        fi
        wait_for_db
        DEV_ARGS=()
        if [[ -n "${ODOO_DEV_MODE}" ]] && [[ "${ODOO_DEV_MODE}" != "False" ]]; then
            DEV_ARGS+=( "--dev=${ODOO_DEV_MODE}" )
        fi
        run_odoo -c "$TEMP_ODOO_RC" "${DB_ARGS[@]}" "${DEV_ARGS[@]}" "$@"
        ;;
    -*)
        if is_diagnostic_cmd "$@"; then
            run_odoo "$@"
        fi
        wait_for_db
        run_odoo -c "$TEMP_ODOO_RC" "${DB_ARGS[@]}" "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
