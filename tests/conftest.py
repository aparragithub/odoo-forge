"""Session-wide test setup.

`odoo_forge_cli.main` resolves its HOST mount base (`_HOST_ROOTS`) once at
import time from `FORGE_MOUNT_BASE`/`XDG_STATE_HOME`. Pinning
`FORGE_MOUNT_BASE=/mnt` here — at collection time, before any test module
imports `odoo_forge_cli.main` — reproduces the pre-change hardcoded `/mnt/*`
host paths for the whole suite, so the many existing tests asserting literal
`/mnt/...` paths keep working unmodified. Tests exercising
`_resolve_mount_base` itself override/unset this env var per-test via
`monkeypatch`, which is safe because that function reads the environment at
call time, not at import time.
"""

import os

os.environ["FORGE_MOUNT_BASE"] = "/mnt"
