# Odoo Forge — Image Factory

Builds multi-arch **Odoo Community** base images (`ghcr.io/aparragithub/odoo-ce`)
for the versions declared in [`versions.yaml`](versions.yaml). Community edition
only — no addons are baked (enterprise/OCA/localization are Phase 3 layers).

## Layout

| File | Purpose |
|---|---|
| `versions.yaml` | Single source of truth: `{odoo, python}` build matrix. |
| `Dockerfile` | Multi-stage, parameterized by `ODOO_VERSION`, `PYTHON_VERSION` + `ODOO_REVISION`. |
| `entrypoint.sh` | Dynamic `addons_path`, config injection, wait-for-psql. |
| `odoo.conf` | Config template; entrypoint injects env overrides at start. |
| `wait-for-psql.py` | Polls PostgreSQL readiness before the entrypoint launches the Odoo server. |
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

The smoke test is self-contained: it creates its own Docker network and a
throwaway PostgreSQL container, runs `odoo -i base,sale,purchase,stock
--stop-after-init`, then boots the image again as a normal server and polls
`/web/health` until it returns `200`. It fails (non-zero exit) if either
phase does not pass, and it tears its network/containers down on exit either
way (`trap cleanup EXIT`). This is the exact script CI runs before
publishing — locally and in CI it behaves identically.

## Environment variables

The entrypoint (`entrypoint.sh`) reads these at container start and injects
them into the config template (`odoo.conf`) or into the `odoo` CLI args. All
have defaults; only set what you need to override.

| Variable | Default | Effect |
|---|---|---|
| `ODOO_ADMIN_PASSWD` | auto-generated | Master password. If unset, a random one is generated at startup and logged as a `NOTICE`; set it explicitly for a fixed value. |
| `ODOO_WORKERS` | `0` | `workers` config value. Forced to `0` when `ODOO_DEBUG_PORT` is set (debugpy requires no worker processes). |
| `ODOO_LOG_LEVEL` | `info` | `log_level` config value. |
| `ODOO_LIST_DB` | `True` | `list_db` config value — whether the database selector is shown. |
| `ODOO_DB_FILTER` | `.*` | `dbfilter` config value. |
| `ODOO_WITHOUT_DEMO` | `True` | `without_demo` config value. |
| `ODOO_PROXY_MODE` | `True` | `proxy_mode` config value. |
| `SMTP_SERVER` | `localhost` | `smtp_server` config value. |
| `SMTP_PORT` | `25` | `smtp_port` config value. |
| `ODOO_DEBUG_PORT` | unset | When set, the entrypoint wraps the Odoo process in `debugpy --listen 0.0.0.0:<port>` and forces `workers=0`. |
| `ODOO_DEV_MODE` | unset | When set to anything other than `False`, passed through as `--dev=<value>` (e.g. `xml,reload`). Only applied when launching the Odoo server. |
| `DB_HOST` / `POSTGRES_HOST` | `db` | PostgreSQL host, passed as `--db_host`. `DB_HOST` wins if both are set. |
| `DB_PORT` / `POSTGRES_PORT` | `5432` | PostgreSQL port, passed as `--db_port`. |
| `DB_USER` / `POSTGRES_USER` | `odoo` | PostgreSQL user, passed as `--db_user`. |
| `DB_PASSWORD` / `POSTGRES_PASSWORD` | `odoo` | PostgreSQL password, passed as `--db_password`. |
| `POSTGRES_DB` | `postgres` | Database used for the readiness check and passed as `--database`. |

Behavior contracts worth knowing:

- **DB wait is scoped to server launches.** `wait-for-psql.py` only runs
  before the entrypoint execs the Odoo server (`odoo` or any `-`-prefixed
  arg list). Arbitrary commands (`bash`, `odoo --version`, etc.) exec
  immediately with no PostgreSQL dependency.
- **Config injection fails loudly.** Each config value is set in the
  container's copy of `odoo.conf` by matching an existing `key = value` line.
  If a key is missing from the template, the entrypoint exits non-zero
  instead of silently doing nothing.
- **The mounted config template stays read-only.** The image's
  `/etc/odoo/odoo.conf` is never edited in place; the entrypoint copies it to
  `/tmp/odoo.conf`, edits the copy, and points `ODOO_RC` at that copy. A
  volume-mounted template can stay read-only from the container's point of
  view.

## Add a version

1. Add an entry to `versions.yaml` with its Python base.
2. `./factory/build.sh <version> && ./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:<major>`.
3. Push — CI picks up the new matrix entry automatically.

**Prerequisites:** Docker with Buildx, `yq` (v4+).
