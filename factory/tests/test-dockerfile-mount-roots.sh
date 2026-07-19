#!/usr/bin/env bash
# Static assertion on factory/Dockerfile's mount-root mkdir/chown line: the
# production stage must only pre-create the system/structural roots
# (community, enterprise, worktrees) plus the `custom` parent namespace for
# user-declared categories. `localization` is dropped entirely (it becomes
# an ordinary user category at /mnt/custom/localization if ever declared),
# and per-category `custom` subdirs (e.g. /mnt/custom/oca) are created at
# mount time, not pre-created individually in the image.
#
# No docker build here (network/registry heavy, out of scope for this
# lightweight factory test) -- this is a text-level contract check on the
# Dockerfile itself, consistent with test-build-sh.sh's approach of testing
# factory scripts without a real image build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE="$SCRIPT_DIR/../Dockerfile"

PASS=0

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    exit 1
}

pass() {
    printf 'PASS: %s\n' "$1"
    PASS=$((PASS + 1))
}

mkdir_line="$(grep -m1 '^RUN mkdir -p /mnt' "$DOCKERFILE")"
[[ -n "$mkdir_line" ]] || fail "no mount-root 'RUN mkdir -p /mnt...' line found in $DOCKERFILE"

chown_line="$(grep -m1 'chown -R odoo:odoo ' "$DOCKERFILE")"
[[ -n "$chown_line" ]] || fail "no 'chown -R odoo:odoo ...' line found in $DOCKERFILE"

for root in /mnt/community /mnt/enterprise /mnt/worktrees /mnt/custom; do
    [[ "$mkdir_line" == *"$root"* ]] || fail "mkdir line is missing expected root: $root"
    [[ "$chown_line" == *"$root"* ]] || fail "chown line is missing expected root: $root"
done
pass "mkdir/chown pre-create the system roots (community, enterprise, worktrees) and the custom parent namespace"

[[ "$mkdir_line" != *"/mnt/localization"* ]] || fail "mkdir line still references dropped root /mnt/localization"
[[ "$chown_line" != *"/mnt/localization"* ]] || fail "chown line still references dropped root /mnt/localization"
pass "'localization' is no longer pre-created (would become an ordinary /mnt/custom/localization category if declared)"

printf '\n== %d passed ==\n' "$PASS"
