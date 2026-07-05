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

# ─── Build dynamic addons_path ──────────────────────────────
# Scan mounted layer dirs for Odoo modules (__manifest__.py). A base image
# ships none of these populated; higher layers / the local backend mount them.
build_addons_path() {
    local paths=""
    for base in /mnt/worktrees /mnt/custom /mnt/community /mnt/localization /mnt/enterprise; do
        if [ -d "$base" ]; then
            local dirs
            dirs=$(find "$base" -name '__manifest__.py' -type f 2>/dev/null | while read -r manifest; do dirname "$(dirname "$manifest")"; done | sort -u)
            for dir in $dirs; do paths="${paths}${dir},"; done
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
            sed -i "s|^workers =.*|workers = 0|" "$TEMP_ODOO_RC"
        fi
        echo "NOTICE: Debug mode enabled on port ${ODOO_DEBUG_PORT}"
        exec /opt/venv/bin/python3 -m debugpy --listen 0.0.0.0:${ODOO_DEBUG_PORT} \
            /usr/local/bin/odoo "$@"
    else
        exec odoo "$@"
    fi
}

# Config injection (one image, two environments).
sed -i "s|^admin_passwd =.*|admin_passwd = ${ODOO_ADMIN_PASSWD}|" "$TEMP_ODOO_RC"
sed -i "s|^workers =.*|workers = ${ODOO_WORKERS:-0}|" "$TEMP_ODOO_RC"
sed -i "s|^log_level =.*|log_level = ${ODOO_LOG_LEVEL:-info}|" "$TEMP_ODOO_RC"
sed -i "s|^list_db =.*|list_db = ${ODOO_LIST_DB:-True}|" "$TEMP_ODOO_RC"
sed -i "s|^dbfilter =.*|dbfilter = ${ODOO_DB_FILTER:-.*}|" "$TEMP_ODOO_RC"
sed -i "s|^without_demo =.*|without_demo = ${ODOO_WITHOUT_DEMO:-True}|" "$TEMP_ODOO_RC"
sed -i "s|^proxy_mode =.*|proxy_mode = ${ODOO_PROXY_MODE:-True}|" "$TEMP_ODOO_RC"
sed -i "s|^smtp_server =.*|smtp_server = ${SMTP_SERVER:-localhost}|" "$TEMP_ODOO_RC"
sed -i "s|^smtp_port =.*|smtp_port = ${SMTP_PORT:-25}|" "$TEMP_ODOO_RC"
sed -i "s|^addons_path\s*=.*|addons_path = ${DYNAMIC_ADDONS_PATH}|" "$TEMP_ODOO_RC"

export ODOO_RC="$TEMP_ODOO_RC"

check_config() {
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
}

check_config
echo "Waiting for PostgreSQL at ${DB_HOST:-db}..."
/opt/venv/bin/python3 /usr/local/bin/wait-for-psql.py \
    --db_host "${DB_HOST}" --db_port "${DB_PORT}" --db_user "${DB_USER}" \
    --db_password "${DB_PASSWORD}" --database "${POSTGRES_DB:-postgres}" --timeout=60

case "$1" in
    --* | odoo)
        shift
        DEV_ARGS=()
        if [[ -n "${ODOO_DEV_MODE}" ]] && [[ "${ODOO_DEV_MODE}" != "False" ]]; then
            DEV_ARGS+=( "--dev=${ODOO_DEV_MODE}" )
        fi
        run_odoo -c "$TEMP_ODOO_RC" "${DB_ARGS[@]}" "${DEV_ARGS[@]}" "$@"
        ;;
    -*)
        run_odoo -c "$TEMP_ODOO_RC" "${DB_ARGS[@]}" "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
