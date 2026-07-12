#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRYPOINT="$SCRIPT_DIR/../entrypoint.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

SECRET_MARKER='entrypoint-secret-marker'
PASS=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

pass() {
    printf 'PASS: %s\n' "$1"
    PASS=$((PASS + 1))
}

prepare_case() {
    local name="$1"
    CASE_DIR="$TEST_ROOT/$name"
    mkdir -p "$CASE_DIR/bin" "$CASE_DIR/tmp" "$CASE_DIR/lib"
    cp "$ENTRYPOINT" "$CASE_DIR/entrypoint.sh"
    cp "$SCRIPT_DIR/../lib/credentials.sh" "$CASE_DIR/lib/credentials.sh"
    # Keep production control flow intact while redirecting image-only paths.
    sed -i \
        -e "s|/opt/venv/bin/python3|$CASE_DIR/bin/python3|g" \
        -e "s|/usr/local/bin/wait-for-psql.py|$CASE_DIR/wait-for-psql.py|g" \
        -e "s|TEMP_ODOO_RC=\"/tmp/odoo.conf\"|TEMP_ODOO_RC=\"$CASE_DIR/odoo.conf\"|" \
        "$CASE_DIR/entrypoint.sh"
    chmod +x "$CASE_DIR/entrypoint.sh"

    cat >"$CASE_DIR/template.conf" <<'EOF'
[options]
admin_passwd = admin
workers = 0
log_level = info
list_db = True
dbfilter = .*
without_demo = True
proxy_mode = True
smtp_server = localhost
smtp_port = 25
addons_path = /opt/odoo/addons
EOF

    cat >"$CASE_DIR/bin/python3" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "-" ]]; then
    cat >/dev/null
    exit 0
fi
printf '%s\n' "$@" >"$HARNESS_ARGS"
password_file=""
while (($#)); do
    if [[ "$1" == "--db_password_file" ]]; then
        password_file="$2"
        break
    fi
    shift
done
[[ -n "$password_file" ]] || exit 91
printf '%s\n' "$password_file" >"$HARNESS_PASSWORD_PATH"
stat -c '%a' "$password_file" >"$HARNESS_MODE"
if [[ "${HARNESS_WAIT_RESULT:-success}" == "signal" ]]; then
    kill -TERM "$PPID"
    sleep 5
fi
[[ "${HARNESS_WAIT_RESULT:-success}" == "success" ]]
EOF
    chmod +x "$CASE_DIR/bin/python3"

    cat >"$CASE_DIR/bin/odoo" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$HARNESS_ODOO_ARGS"
EOF
    chmod +x "$CASE_DIR/bin/odoo"
}

run_case() {
    local result="$1"
    shift
    set +e
    PATH="$CASE_DIR/bin:$PATH" TMPDIR="$CASE_DIR/tmp" ODOO_RC="$CASE_DIR/template.conf" \
        ODOO_ADMIN_PASSWD=admin DB_PASSWORD="$SECRET_MARKER" HARNESS_WAIT_RESULT="$result" \
        HARNESS_ARGS="$CASE_DIR/wait.args" HARNESS_PASSWORD_PATH="$CASE_DIR/password.path" \
        HARNESS_MODE="$CASE_DIR/password.mode" HARNESS_ODOO_ARGS="$CASE_DIR/odoo.args" \
        "$CASE_DIR/entrypoint.sh" "$@" >"$CASE_DIR/output" 2>&1
    CASE_STATUS=$?
    set -e
}

assert_fallback_cleaned() {
    local path
    path="$(<"$CASE_DIR/password.path")"
    [[ ! -e "$path" ]] || fail "fallback password file survived entrypoint termination"
    [[ "$(<"$CASE_DIR/password.mode")" == "600" ]] || fail "fallback password file mode was not 0600"
    ! grep -Fq -- "$SECRET_MARKER" "$CASE_DIR/wait.args" || fail "plaintext secret appeared in readiness argv"
    ! grep -Fq -- "$SECRET_MARKER" "$CASE_DIR/output" || fail "plaintext secret appeared in entrypoint output"
}

prepare_case success
run_case success odoo '--db-filter=tenant.*' '--log-handler=a&b:INFO'
[[ "$CASE_STATUS" -eq 0 ]] || fail "successful readiness changed exit status"
assert_fallback_cleaned
grep -Fxq -- '--db-filter=tenant.*' "$CASE_DIR/odoo.args" || fail "metacharacter argument was not forwarded"
grep -Fxq -- '--log-handler=a&b:INFO' "$CASE_DIR/odoo.args" || fail "ampersand argument was not forwarded"
pass "fallback secret is mode 0600, path-only, cleaned after success, and arguments are preserved"

prepare_case failure
run_case failure odoo
[[ "$CASE_STATUS" -eq 1 ]] || fail "readiness failure status was not preserved"
assert_fallback_cleaned
pass "fallback secret is cleaned after readiness failure"

prepare_case signal
run_case signal odoo
[[ "$CASE_STATUS" -eq 143 ]] || fail "TERM status was not preserved"
assert_fallback_cleaned
pass "fallback secret is cleaned after TERM"

prepare_case caller-owned
caller_secret="$CASE_DIR/caller password"
printf '%s' "$SECRET_MARKER" >"$caller_secret"
chmod 640 "$caller_secret"
set +e
PATH="$CASE_DIR/bin:$PATH" TMPDIR="$CASE_DIR/tmp" ODOO_RC="$CASE_DIR/template.conf" \
    ODOO_ADMIN_PASSWD=admin DB_PASSWORD_FILE="$caller_secret" HARNESS_WAIT_RESULT=failure \
    HARNESS_ARGS="$CASE_DIR/wait.args" HARNESS_PASSWORD_PATH="$CASE_DIR/password.path" \
    HARNESS_MODE="$CASE_DIR/password.mode" HARNESS_ODOO_ARGS="$CASE_DIR/odoo.args" \
    "$CASE_DIR/entrypoint.sh" odoo >"$CASE_DIR/output" 2>&1
CASE_STATUS=$?
set -e
[[ "$CASE_STATUS" -eq 1 ]] || fail "caller-owned readiness failure status was not preserved"
[[ -f "$caller_secret" ]] || fail "caller-owned password file was deleted"
[[ "$(<"$CASE_DIR/password.path")" == "$caller_secret" ]] || fail "caller-owned path was not forwarded intact"
pass "caller-owned password file is never deleted"

printf '\n== %d passed ==\n' "$PASS"
