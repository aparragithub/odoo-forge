#!/usr/bin/env bash
# Unit test for entrypoint.sh's build_addons_path(): a pure filesystem-
# scanning function, tested in isolation (no python3/odoo mocks needed) by
# extracting its source and redirecting its hardcoded /mnt/... roots at a
# throwaway fake tree.
#
# Asserts the manifest-derived mount-root model (design 9700 + refinement
# 9702):
#   - system/structural roots = ONLY worktrees, community, enterprise, in
#     that fixed order (worktrees FIRST so an unlock-promoted worktree
#     shadows the read-only copy of the same repo via addons_path first-wins);
#   - `localization` is DROPPED entirely as a system root (it becomes an
#     ordinary user category, at /mnt/custom/localization, if ever declared);
#   - arbitrary user categories nest under /mnt/custom/<category>/ and are
#     scanned in sorted order after the fixed prefix;
#   - /opt/odoo/addons is always last;
#   - an existing-but-empty root/category is skipped without error.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRYPOINT="$SCRIPT_DIR/../entrypoint.sh"

TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

MNT_ROOT="$TEST_ROOT/mnt"
mkdir -p "$MNT_ROOT"

PASS=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

pass() {
    printf 'PASS: %s\n' "$1"
    PASS=$((PASS + 1))
}

make_module() {
    # make_module <relative-repo-dir-under-mnt> <module-name>
    # build_addons_path() reports the *repo* directory (one level above the
    # module dir that holds __manifest__.py) as the addons_path entry, so
    # fixtures need repo/module/__manifest__.py, not module/__manifest__.py
    # directly under the root.
    local rel="$1" mod="$2"
    mkdir -p "$MNT_ROOT/$rel/$mod"
    printf '# stub\n' >"$MNT_ROOT/$rel/$mod/__manifest__.py"
}

# --- fixed system roots -----------------------------------------------------
make_module "community/base_repo" "base_mod"
make_module "enterprise/ee_repo" "ee_mod"
make_module "worktrees/wt_repo" "wt_mod"

# --- old, now-dropped root: must NOT appear in the new addons_path ---------
make_module "localization/l10n_repo" "l10n_ar"

# --- arbitrary user categories nested under /mnt/custom/<category>/ --------
make_module "custom/oca/oca_repo" "oca_mod"
make_module "custom/adhoc/adhoc_repo" "adhoc_mod"

# --- existing-but-empty category: must be skipped without error -----------
mkdir -p "$MNT_ROOT/custom/empty-category"

# Extract build_addons_path() in isolation and redirect its hardcoded
# /mnt/... roots at our fake tree (# as sed delimiter since $MNT_ROOT itself
# contains slashes).
func_src="$(sed -n '/^build_addons_path()/,/^}$/p' "$ENTRYPOINT")"
[[ -n "$func_src" ]] || fail "could not extract build_addons_path() from entrypoint.sh"
func_src="$(printf '%s\n' "$func_src" | sed "s#/mnt/#${MNT_ROOT}/#g")"
eval "$func_src"

result="$(build_addons_path)"

expected="$MNT_ROOT/worktrees/wt_repo,$MNT_ROOT/community/base_repo,$MNT_ROOT/enterprise/ee_repo,$MNT_ROOT/custom/adhoc/adhoc_repo,$MNT_ROOT/custom/oca/oca_repo,/opt/odoo/addons"

if [[ "$result" == "$expected" ]]; then
    pass "addons_path: fixed system-root prefix (worktrees, community, enterprise), then sorted /mnt/custom/<category> globs, then /opt/odoo/addons last"
else
    fail "unexpected addons_path ordering
  expected: $expected
  actual:   $result"
fi

if [[ "$result" != *"localization"* ]]; then
    pass "'localization' is no longer a system root (would become an ordinary /mnt/custom/localization category if declared)"
else
    fail "dropped 'localization' root leaked into addons_path: $result"
fi

printf '\n== %d passed ==\n' "$PASS"
