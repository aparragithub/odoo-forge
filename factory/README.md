# Odoo Forge — Image Factory

Builds multi-arch **Odoo Community** base images (`ghcr.io/aparragithub/odoo-ce`)
for the versions declared in [`versions.yaml`](versions.yaml). Community edition
only — no addons are baked (enterprise/OCA/localization are Phase 3 layers).

## Layout

| File | Purpose |
|---|---|
| `versions.yaml` | Single source of truth: `{odoo, python}` build matrix. |
| `Dockerfile` | Multi-stage, parameterized by `ODOO_VERSION` + `PYTHON_VERSION`. |
| `entrypoint.sh` | Dynamic `addons_path`, config injection, wait-for-psql. |
| `odoo.conf` | Config template; entrypoint injects env overrides at start. |
| `extra_requirements.txt` | Pinned extra Python deps baked into every image. |
| `build.sh` | Build one version single-arch locally. |
| `smoke-test.sh` | Boot an image against an ephemeral Postgres; the CI publish gate. |

## Build a version locally

```bash
./factory/build.sh 19.0        # -> ghcr.io/aparragithub/odoo-ce:19
```

## Test it

```bash
./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19
```

The smoke test starts a throwaway PostgreSQL, runs `odoo -i base,sale,purchase,stock
--stop-after-init`, and fails (non-zero exit) if Odoo cannot initialize —
the same gate CI runs before publishing.

## Add a version

1. Add an entry to `versions.yaml` with its Python base.
2. `./factory/build.sh <version> && ./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:<major>`.
3. Push — CI picks up the new matrix entry automatically.

**Prerequisites:** Docker with Buildx, `yq` (v4+).
