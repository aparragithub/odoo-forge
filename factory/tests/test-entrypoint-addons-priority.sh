#!/usr/bin/env bash
# Unit test for entrypoint.sh's build_addons_path() honoring
# FORGE_ADDONS_PATH_ORDER (manifest-derived `mount_priority`, T2.6). When the
# env var is set, build_addons_path MUST scan the roots in exactly that order
# (a user category can outrank system roots); when unset it MUST fall back to
# the fixed default (worktrees, community, enterprise, then sorted
# /mnt/custom/*). Tested in isolation by extracting the function and
# redirecting its hardcoded /mnt/... roots at a throwaway fake tree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRYPOINT="$SCRIPT_DIR/../entrypoint.sh"

TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT
MNT_ROOT="$TEST_ROOT/mnt"
mkdir -p "$MNT_ROOT"

PASS=0
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
pass() { printf 'PASS: %s\n' "$1"; PASS=$((PASS + 1)); }

make_module() {
    local rel="$1" mod="$2"
    mkdir -p "$MNT_ROOT/$rel/$mod"
    printf '# stub\n' >"$MNT_ROOT/$rel/$mod/__manifest__.py"
}

make_module "worktrees/wt_repo" "wt_mod"
make_module "community/base_repo" "base_mod"
make_module "enterprise/ee_repo" "ee_mod"
make_module "custom/overrides/ov_repo" "ov_mod"
make_module "custom/oca/oca_repo" "oca_mod"

func_src="$(sed -n '/^build_addons_path()/,/^}$/p' "$ENTRYPOINT")"
[[ -n "$func_src" ]] || fail "could not extract build_addons_path() from entrypoint.sh"
func_src="$(printf '%s\n' "$func_src" | sed "s#/mnt/#${MNT_ROOT}/#g")"
eval "$func_src"

# --- env-driven priority order: custom/overrides outranks the system roots ---
export FORGE_ADDONS_PATH_ORDER="$MNT_ROOT/custom/overrides,$MNT_ROOT/worktrees,$MNT_ROOT/community,$MNT_ROOT/enterprise,$MNT_ROOT/custom/oca"
result="$(build_addons_path)"
expected="$MNT_ROOT/custom/overrides/ov_repo,$MNT_ROOT/worktrees/wt_repo,$MNT_ROOT/community/base_repo,$MNT_ROOT/enterprise/ee_repo,$MNT_ROOT/custom/oca/oca_repo,/opt/odoo/addons"
if [[ "$result" == "$expected" ]]; then
    pass "FORGE_ADDONS_PATH_ORDER is honored verbatim (custom/overrides outranks system roots)"
else
    fail "env-driven order not honored
  expected: $expected
  actual:   $result"
fi

# --- unset env: falls back to the fixed default order -----------------------
unset FORGE_ADDONS_PATH_ORDER
result="$(build_addons_path)"
expected="$MNT_ROOT/worktrees/wt_repo,$MNT_ROOT/community/base_repo,$MNT_ROOT/enterprise/ee_repo,$MNT_ROOT/custom/oca/oca_repo,$MNT_ROOT/custom/overrides/ov_repo,/opt/odoo/addons"
if [[ "$result" == "$expected" ]]; then
    pass "unset FORGE_ADDONS_PATH_ORDER falls back to the default order (worktrees first, then sorted custom)"
else
    fail "fallback order wrong
  expected: $expected
  actual:   $result"
fi

printf '\n== %d passed ==\n' "$PASS"
