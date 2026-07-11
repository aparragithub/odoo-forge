#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/credentials.sh disable=SC1091
source "$SCRIPT_DIR/../lib/credentials.sh"

secret_file="$(mktemp)"
trap 'rm -f "$secret_file"' EXIT
printf '%s' 'file-only-password' >"$secret_file"

# DB_PASSWORD_FILE / DB_PASSWORD are consumed via ${!name} indirection in
# read_secret_value, which shellcheck cannot trace.
# shellcheck disable=SC2034
DB_PASSWORD_FILE="$secret_file"
# shellcheck disable=SC2034
DB_PASSWORD='environment-password'
if [[ "$(read_secret_value DB_PASSWORD)" != 'file-only-password' ]]; then
    echo "FAIL: DB_PASSWORD_FILE must take precedence" >&2
    exit 1
fi

unset DB_PASSWORD_FILE
if [[ "$(read_secret_value DB_PASSWORD)" != 'environment-password' ]]; then
    echo "FAIL: DB_PASSWORD must remain a compatibility fallback" >&2
    exit 1
fi

wait_help="$(python3 "$SCRIPT_DIR/../wait-for-psql.py" --help)"
if [[ "$wait_help" != *"--db_password_file"* || "$wait_help" == *"--db_password "* ]]; then
    echo "FAIL: wait-for-psql must accept only a password-file argument" >&2
    exit 1
fi

echo "PASS: entrypoint secret-file resolution"
