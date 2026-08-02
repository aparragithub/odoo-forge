#!/usr/bin/env bash

set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "usage: $0 WHEEL_DIRECTORY" >&2
  exit 2
fi

wheel_directory="$1"
shopt -s nullglob
smoke_root="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/odoo-forge-wheel-smoke.XXXXXX")"

cleanup() {
  rm -rf -- "$smoke_root"
}

cleanup_and_exit() {
  local status="$1"
  trap - HUP INT TERM
  cleanup
  exit "$status"
}

trap cleanup EXIT
trap 'cleanup_and_exit 129' HUP
trap 'cleanup_and_exit 130' INT
trap 'cleanup_and_exit 143' TERM

select_wheel() {
  local directory="$1"
  local -a matches=("$directory"/odoo_forge_toolkit-*.whl)
  if [[ "${#matches[@]}" -ne 1 ]]; then
    return 1
  fi
  printf '%s\n' "${matches[0]}"
}

# A pre-existing lookalike must never be reused as the owned temp path.
collision_parent="$(mktemp -d "$smoke_root/collision.XXXXXX")"
collision_path="$collision_parent/candidate.000000"
mkdir "$collision_path"
unique_path="$(mktemp -d "$collision_parent/candidate.XXXXXX")"
[[ "$unique_path" != "$collision_path" ]]
rm -rf -- "$unique_path" "$collision_path"

# Wheel selection fails closed for zero and multiple project wheels.
zero_directory="$smoke_root/zero"
multiple_directory="$smoke_root/multiple"
mkdir "$zero_directory" "$multiple_directory"
if select_wheel "$zero_directory"; then
  echo "::error::zero-wheel fixture was accepted" >&2
  exit 1
fi

wheel="$(select_wheel "$wheel_directory")"
cp -- "$wheel" "$multiple_directory/odoo_forge_toolkit-0.whl"
cp -- "$wheel" "$multiple_directory/odoo_forge_toolkit-1.whl"
if select_wheel "$multiple_directory"; then
  echo "::error::multiple-wheel fixture was accepted" >&2
  exit 1
fi

# Nonzero and timeout exits must run cleanup for their owned paths.
assert_failure_cleanup() {
  local mode="$1"
  local owned="$smoke_root/owned-$mode"
  mkdir "$owned"
  if (
    trap 'rm -rf -- "$owned"' EXIT
    if [[ "$mode" == "nonzero" ]]; then
      exit 73
    fi
    timeout --kill-after=1s 1s "$venv/bin/python" -c 'import time; time.sleep(2)'
  ); then
    echo "::error::$mode fixture unexpectedly succeeded" >&2
    exit 1
  fi
  [[ ! -e "$owned" ]]
}

venv="$smoke_root/venv"
uv venv "$venv"
assert_failure_cleanup nonzero
assert_failure_cleanup timeout
uv pip install --python "$venv/bin/python" --no-deps "$wheel"

compat_venv="$smoke_root/compat-venv"
uv venv "$compat_venv"
uv pip install --python "$compat_venv/bin/python" "$wheel"

# A polluted PYTHONPATH must not be able to satisfy the wheel proof.
shadow="$smoke_root/shadow"
mkdir -p "$shadow/odoo_forge_instances_postgres"
printf 'raise RuntimeError("shadow package imported")\n' \
  > "$shadow/odoo_forge_instances_postgres/__init__.py"
if PYTHONPATH="$shadow" "$venv/bin/python" -c 'import odoo_forge_instances_postgres'; then
  echo "::error::shadow package was accepted" >&2
  exit 1
fi

external_cwd="$smoke_root/external"
mkdir "$external_cwd"
(
  cd "$external_cwd"
  env -u PYTHONPATH PYTHONNOUSERSITE=1 "$compat_venv/bin/forge" --help > /dev/null
  env -u PYTHONPATH PYTHONNOUSERSITE=1 "$compat_venv/bin/python" - <<'PY'
import importlib

for module_name in (
    "odoo_forge", "odoo_forge_cli", "odoo_forge_git",
    "odoo_forge_workspace", "odoo_forge_docker", "odoo_forge_registry",
    "odoo_forge_postgres_docker", "odoo_forge_catalog",
    "odoo_forge_pipeline_github",
):
    importlib.import_module(module_name)
print("all packages import from the built wheel")
PY
  env -u PYTHONPATH PYTHONNOUSERSITE=1 "$venv/bin/python" - <<'PY'
import importlib
import sys
from pathlib import Path

package = importlib.import_module("odoo_forge_instances_postgres")
assert "odoo_forge_instances_postgres.migrate" not in sys.modules
assert package.__all__ == [
    "MigrationAutocommitError",
    "MigrationLockTimeoutError",
    "RegistryTableRejectedError",
    "CatalogVerificationError",
]
importlib.import_module("odoo_forge_instances_postgres.migrations")
assert "odoo_forge_instances_postgres.migrate" not in sys.modules

errors = importlib.import_module("odoo_forge_instances_postgres.errors")
migrate = importlib.import_module("odoo_forge_instances_postgres.migrate")
for name in package.__all__:
    assert getattr(package, name) is getattr(errors, name) is getattr(migrate, name)
site_packages = next(Path(entry).resolve() for entry in sys.path if entry.endswith("site-packages"))
for module in (package, errors, migrate):
    assert Path(module.__file__).resolve().is_relative_to(site_packages)
print("all instance-postgres errors import from the exact built wheel")
PY
)
