#!/bin/bash
set -e

# =============================================================================
# Odoo Forge — base image entrypoint (one image, two environments)
# =============================================================================

ODOO_RC=${ODOO_RC:-/etc/odoo/odoo.conf}
TEMP_ODOO_RC="/tmp/odoo.conf"
TEMP_DB_PASSWORD_FILE=""

cleanup_temp_db_password_file() {
    local status=$?
    if [[ -n "$TEMP_DB_PASSWORD_FILE" ]]; then
        rm -f -- "$TEMP_DB_PASSWORD_FILE" || true
        TEMP_DB_PASSWORD_FILE=""
    fi
    return "$status"
}

trap cleanup_temp_db_password_file EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 131' QUIT
trap 'exit 143' TERM

# shellcheck source=lib/credentials.sh disable=SC1091
source "$(dirname "$0")/lib/credentials.sh"

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
    if ! ODOO_CONF_KEY="$key" ODOO_CONF_VALUE="$value" ODOO_CONF_UPSERT="${ODOO_CONF_UPSERT:-0}" /opt/venv/bin/python3 - "$TEMP_ODOO_RC" <<'PYEOF'
import os
import re
import sys
import tempfile

path = sys.argv[1]
key = os.environ["ODOO_CONF_KEY"]
value = os.environ["ODOO_CONF_VALUE"]
upsert = os.environ.get("ODOO_CONF_UPSERT") == "1"

if "\n" in value:
    print(f"ERROR: value for config key '{key}' contains a newline; refusing to write (would corrupt {path})", file=sys.stderr)
    sys.exit(1)

pattern = re.compile(r"^" + re.escape(key) + r"\s*=.*$", re.MULTILINE)

with open(path, "r") as f:
    content = f.read()

new_content, count = pattern.subn(lambda m: f"{key} = {value}", content, count=1)
if count == 0:
    if not upsert:
        print(f"ERROR: config key '{key}' not found in {path}", file=sys.stderr)
        sys.exit(1)
    # Key is intentionally absent from the template (e.g. db_password); insert
    # it under the [options] section rather than failing.
    section = re.search(r"^\[options\][^\n]*$", content, re.MULTILINE)
    if section is None:
        print(f"ERROR: [options] section not found in {path}; cannot insert '{key}'", file=sys.stderr)
        sys.exit(1)
    idx = section.end()
    new_content = content[:idx] + f"\n{key} = {value}" + content[idx:]

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

# Like set_conf, but inserts the key under [options] when it is absent from the
# template instead of failing. Used for keys deliberately omitted from the
# shipped config (e.g. db_password, injected at runtime and kept out of argv).
upsert_conf() {
    ODOO_CONF_UPSERT=1 set_conf "$@"
}

# ─── Build dynamic addons_path ──────────────────────────────
# Scan mounted layer dirs for Odoo modules (__manifest__.py). A base image
# ships none of these populated; higher layers / the local backend mount them.
#
# Ordering/precedence (manifest-derived mount-root model): the fixed system
# roots come first — `worktrees` FIRST, then community, then enterprise —
# then arbitrary user categories declared under /mnt/custom/<category>/,
# scanned in sorted order; then /opt/odoo/addons last. `worktrees` leads on
# purpose: Odoo resolves duplicate module names by FIRST match in
# addons_path, so an `unlock`-promoted writable worktree must precede the
# read-only projection of the same repo to shadow it. `localization` is NOT a
# system root — it is an ordinary user category (/mnt/custom/localization) if
# ever declared. A root/category that exists but has no modules is skipped
# without error.
build_addons_path() {
    local paths=""
    local base dir category_dir

    for base in /mnt/worktrees /mnt/community /mnt/enterprise; do
        if [ -d "$base" ]; then
            while IFS= read -r dir; do
                paths="${paths}${dir},"
            done < <(find "$base" -name '__manifest__.py' -type f 2>/dev/null | while read -r manifest; do dirname "$(dirname "$manifest")"; done | sort -u)
        fi
    done

    if [ -d /mnt/custom ]; then
        while IFS= read -r category_dir; do
            while IFS= read -r dir; do
                paths="${paths}${dir},"
            done < <(find "$category_dir" -name '__manifest__.py' -type f 2>/dev/null | while read -r manifest; do dirname "$(dirname "$manifest")"; done | sort -u)
        done < <(find /mnt/custom -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)
    fi

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
    DB_PASSWORD=$(read_secret_value DB_PASSWORD)
    if [[ -z "$DB_PASSWORD" ]]; then
        DB_PASSWORD=$(read_secret_value POSTGRES_PASSWORD)
    fi
    DB_PASSWORD=${DB_PASSWORD:-odoo}
    DB_PASSWORD_FILE_PATH=${DB_PASSWORD_FILE:-${POSTGRES_PASSWORD_FILE:-}}
    if [[ -z "$DB_PASSWORD_FILE_PATH" ]]; then
        TEMP_DB_PASSWORD_FILE=$(umask 077 && mktemp)
        chmod 600 "$TEMP_DB_PASSWORD_FILE"
        printf '%s' "$DB_PASSWORD" >"$TEMP_DB_PASSWORD_FILE"
        DB_PASSWORD_FILE_PATH="$TEMP_DB_PASSWORD_FILE"
    fi
    upsert_conf db_password "$DB_PASSWORD"
    DB_ARGS=()
    DB_ARGS+=( "--db_host" "${DB_HOST}" )
    DB_ARGS+=( "--db_port" "${DB_PORT}" )
    DB_ARGS+=( "--db_user" "${DB_USER}" )
    DB_ARGS+=( "--database" "${POSTGRES_DB:-postgres}" )

    echo "Waiting for PostgreSQL at ${DB_HOST}..."
    /opt/venv/bin/python3 /usr/local/bin/wait-for-psql.py \
        --db_host "${DB_HOST}" --db_port "${DB_PORT}" --db_user "${DB_USER}" \
        --db_password_file "${DB_PASSWORD_FILE_PATH}" --database "${POSTGRES_DB:-postgres}" --timeout=60
    cleanup_temp_db_password_file
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
