#!/usr/bin/env bash
# Self-contained unit tests for factory/build.sh's pure logic functions.
# Sources build.sh (its `if [[ "${BASH_SOURCE[0]}" == "$0" ]]` guard keeps it
# from running `main` / a real docker build) and exercises derive_image_name,
# resolve_image_name and resolve_odoo_revision directly. No docker, no
# network -- git ls-remote is stubbed with a bash function.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SH="$SCRIPT_DIR/../build.sh"

# shellcheck source=../build.sh disable=SC1091
source "$BUILD_SH"

PASS=0
FAIL=0

pass() {
    echo "PASS: $1"
    PASS=$((PASS + 1))
}

fail() {
    echo "FAIL: $1"
    FAIL=$((FAIL + 1))
}

assert_eq() {
    local desc="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        pass "$desc"
    else
        fail "$desc (expected: '$expected', got: '$actual')"
    fi
}

# --- derive_image_name: URL form coverage ---------------------------------

out=$(derive_image_name "git@github.com:owner/repo.git")
assert_eq "SSH form (git@github.com:owner/repo.git)" "ghcr.io/owner/odoo-ce" "$out"

out=$(derive_image_name "https://github.com/owner/repo.git")
assert_eq "HTTPS form with .git suffix" "ghcr.io/owner/odoo-ce" "$out"

out=$(derive_image_name "https://github.com/owner/repo")
assert_eq "HTTPS form without .git suffix" "ghcr.io/owner/odoo-ce" "$out"

out=$(derive_image_name "ssh://git@github.com/owner/repo.git")
assert_eq "ssh:// form (ssh://git@github.com/owner/repo.git)" "ghcr.io/owner/odoo-ce" "$out"

if err=$(derive_image_name "not-a-git-url" 2>&1); then
    fail "unparseable URL should fail loudly (got success: '$err')"
else
    if [[ "$err" == *"ERROR"*"could not parse owner"* ]]; then
        pass "unparseable URL fails loudly with a clear ERROR message"
    else
        fail "unparseable URL failed but without a clear ERROR message (got: '$err')"
    fi
fi

# --- resolve_image_name: IMAGE override ------------------------------------
# NOTE: deliberately NOT run in subshells -- PASS/FAIL counters are plain
# shell variables and would not survive a subshell exit. Env vars and stubs
# set here are explicitly unset right after use instead.

export IMAGE="ghcr.io/my-fork/odoo-ce"
out=$(resolve_image_name "git@github.com:owner/repo.git")
assert_eq "IMAGE override wins over a parseable remote URL" "ghcr.io/my-fork/odoo-ce" "$out"

out=$(resolve_image_name "")
assert_eq "IMAGE override wins even with no remote URL" "ghcr.io/my-fork/odoo-ce" "$out"
unset IMAGE

out=$(resolve_image_name "git@github.com:owner/repo.git")
assert_eq "no IMAGE override falls back to deriving from remote URL" "ghcr.io/owner/odoo-ce" "$out"

# --- resolve_odoo_revision: ODOO_REVISION override vs ls-remote -----------

STDERR_FILE="$(mktemp)"

unset ODOO_REVISION 2>/dev/null || true
# Stub git so ls-remote returns a fixed fake SHA instead of hitting the
# network. If resolve_odoo_revision incorrectly took the ODOO_REVISION
# branch it would never call this.
# shellcheck disable=SC2329 # invoked indirectly via resolve_odoo_revision
git() {
    if [ "$1" = "ls-remote" ]; then
        printf 'deadbeefcafefeedfacedeadbeefcafefeedface\trefs/heads/19.0\n'
    else
        command git "$@"
    fi
}
out=$(resolve_odoo_revision "19.0" 2>"$STDERR_FILE")
assert_eq "ODOO_REVISION unset resolves branch head via ls-remote" "deadbeefcafefeedfacedeadbeefcafefeedface" "$out"
unset -f git

export ODOO_REVISION="0123456789abcdef0123456789abcdef01234567"
# Stub git to fail loudly if ls-remote is ever invoked -- ODOO_REVISION
# must short-circuit before reaching it.
# shellcheck disable=SC2329 # invoked indirectly via resolve_odoo_revision
git() {
    if [ "$1" = "ls-remote" ]; then
        echo "TEST FAILURE: ls-remote should have been skipped" >&2
        exit 1
    fi
    command git "$@"
}
out=$(resolve_odoo_revision "19.0" 2>"$STDERR_FILE")
assert_eq "ODOO_REVISION set skips ls-remote and is used as-given" "$ODOO_REVISION" "$out"
if grep -qi "not verified to belong" "$STDERR_FILE"; then
    pass "ODOO_REVISION set emits an unverified-SHA warning"
else
    fail "ODOO_REVISION set should warn that the SHA is unverified"
fi
unset -f git
unset ODOO_REVISION

rm -f "$STDERR_FILE"

echo ""
echo "== $PASS passed, $FAIL failed =="

if [ "$FAIL" -ne 0 ]; then
    exit 1
fi
