# Phase 1 — Image Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish multi-arch Odoo Community base images (versions 16.0–19.0) to GHCR via GitHub Actions, with a smoke-test gate that blocks publishing broken images.

**Architecture:** A `factory/` directory holds a parameterized multi-stage Dockerfile plus its support files, driven by a `versions.yaml` matrix that is the single source of truth. A reusable `smoke-test.sh` boots each freshly built image against an ephemeral PostgreSQL and installs `base,sale,purchase,stock`; it runs identically locally and in CI. A GitHub Actions workflow builds each `(version × arch)` on a native runner, smoke-tests it, pushes by digest, then assembles a per-version multi-arch manifest list with a moving and an immutable tag.

**Tech Stack:** Docker + Buildx (multi-arch, BuildKit cache mounts), Bash, YAML, `yq`, GitHub Actions, GHCR. No Python project yet (that is Phase 2) — verification tooling is `docker`, `yq`, `shellcheck`, and the workflow run itself.

## Global Constraints

Copied verbatim from `docs/specs/2026-07-05-phase-1-image-factory-design.md`. Every task's requirements implicitly include these:

- **Community edition only.** No addons baked. Dependencies come from Odoo's own `requirements.txt` (at the pinned branch) plus a hand-maintained `factory/extra_requirements.txt`. No `requirements.collected.txt` layer.
- **Four versions:** 16.0, 17.0, 18.0, 19.0. Python base varies per version (16→3.11, 17→3.11, 18→3.11, 19→3.12). Dockerfile takes `ARG ODOO_VERSION` **and** `ARG PYTHON_VERSION`.
- **`versions.yaml` is the single source of truth** for the matrix — versions are never hardcoded in a second place.
- **Multi-arch** `linux/amd64` + `linux/arm64`, served as a manifest list. arm64 builds on native GitHub ARM runners (no QEMU).
- **Registry:** `ghcr.io/aparragithub/odoo-ce`. Tags per version: moving (`:19`) + immutable (`:19.0-YYYYMMDD`).
- **Non-root** `odoo:1000` baked. `ODOO_UID`/`ODOO_GID` build args must actually be passed by the build (fixes odoo-idp bug §8 #2).
- **OCI revision label:** each image carries `org.opencontainers.image.revision` = the resolved Odoo source SHA.
- **Downstream rule:** the future lockfile always resolves to a **digest**, never the moving tag.

**Prerequisites for local execution:** Docker with Buildx, `yq` (v4+), `shellcheck`. Build context is always the **repo root** (the Dockerfile clones Odoo and `COPY`s from `factory/`), invoked with `-f factory/Dockerfile .`.

---

## File Structure

- `factory/versions.yaml` — the `{odoo, python}` build matrix. Single source of truth.
- `factory/extra_requirements.txt` — small, pinned extra Python deps.
- `factory/wait-for-psql.py` — DB readiness probe (reused verbatim from odoo-idp).
- `factory/odoo.conf` — config template ("one image, two environments"); entrypoint injects overrides.
- `factory/entrypoint.sh` — dynamic `addons_path`, config injection, wait-for-psql (adapted from odoo-idp).
- `factory/Dockerfile` — multi-stage, parameterized by `ODOO_VERSION` + `PYTHON_VERSION`.
- `factory/build.sh` — local helper: resolves Python + Odoo SHA from `versions.yaml`, builds one version single-arch.
- `factory/smoke-test.sh` — reusable publish gate: ephemeral Postgres + `odoo -i base,sale,purchase,stock --stop-after-init`.
- `factory/README.md` — how to build and test locally.
- `.github/workflows/build-images.yml` — matrix build-by-digest per `(version × arch)` + per-version manifest merge.

---

## Task 1: Version matrix — single source of truth

**Files:**
- Create: `factory/versions.yaml`

**Interfaces:**
- Produces: a YAML doc with a top-level `versions:` list; each item has string keys `odoo` (e.g. `"19.0"`) and `python` (e.g. `"3.12"`). Consumed by `factory/build.sh` and `.github/workflows/build-images.yml` via `yq`.

- [ ] **Step 1: Write the matrix file**

```yaml
# factory/versions.yaml
# Single source of truth for the image factory build matrix.
# Each entry maps an Odoo Community version branch to its Python base image tag.
# Adding a version = one entry here (plus verifying its requirements build).
versions:
  # 3.11, not 3.10: Odoo gates gevent/greenlet by python_version; 3.10 selects
  # gevent==21.8.0 (no wheel, breaks under Cython 3.x), 3.11 selects 22.10.2 (wheels).
  - odoo: "16.0"
    python: "3.11"
  - odoo: "17.0"
    python: "3.11"
  - odoo: "18.0"
    python: "3.11"
  - odoo: "19.0"
    python: "3.12"
```

- [ ] **Step 2: Verify it parses and yields the expected matrix**

Run: `yq -o=json -I=0 '.versions' factory/versions.yaml`
Expected (exact): `[{"odoo":"16.0","python":"3.11"},{"odoo":"17.0","python":"3.11"},{"odoo":"18.0","python":"3.11"},{"odoo":"19.0","python":"3.12"}]`

- [ ] **Step 3: Verify a single-version lookup works (the pattern build.sh uses)**

Run: `yq -r '.versions[] | select(.odoo == "19.0") | .python' factory/versions.yaml`
Expected (exact): `3.12`

- [ ] **Step 4: Commit**

```bash
git add factory/versions.yaml
git commit -m "feat(factory): add Odoo version → Python build matrix"
```

---

## Task 2: Container support files

Adapted from odoo-idp `infra/build/`. These are consumed by the Dockerfile in Task 3.

**Files:**
- Create: `factory/extra_requirements.txt`
- Create: `factory/wait-for-psql.py`
- Create: `factory/odoo.conf`
- Create: `factory/entrypoint.sh`

**Interfaces:**
- Produces: `/entrypoint.sh` (container entrypoint), `/usr/local/bin/wait-for-psql.py`, `/etc/odoo/odoo.conf`. The entrypoint reads env vars `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `POSTGRES_DB`, `ODOO_WORKERS`, `ODOO_LOG_LEVEL`, `ODOO_DEBUG_PORT`, `ODOO_DEV_MODE`. Consumed by Task 3 (`COPY`) and Task 4 (smoke test drives it). **No auto-init:** the base image never initializes a database on its own — DB init is a caller decision (the smoke test passes `-i base,sale,purchase,stock` explicitly; higher layers / the local backend own init policy). The entrypoint carries no `INIT_BASE` logic by design.

- [ ] **Step 1: Write `factory/extra_requirements.txt`**

```
# Additional Python dependencies baked into every base image.
# Always pin versions to keep builds reproducible.
websocket-client==1.9.0
phonenumbers==9.0.24
debugpy==1.8.11
```

- [ ] **Step 2: Write `factory/wait-for-psql.py`** (verbatim from odoo-idp)

```python
#!/usr/bin/env python3
import argparse
import sys
import time
import psycopg2

def wait_for_psql(db_host, db_port, db_user, db_password, database, timeout):
    start_time = time.time()
    while True:
        try:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=database,
                connect_timeout=5
            )
            conn.close()
            print("PostgreSQL is ready!")
            return True
        except psycopg2.OperationalError:
            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                print(f"Timeout reached ({timeout}s). PostgreSQL is not available at {db_host}:{db_port}.", file=sys.stderr)
                sys.exit(1)
            print(f"PostgreSQL not ready yet, retrying... ({int(elapsed_time)}s)", flush=True)
            time.sleep(2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wait for PostgreSQL to be ready.")
    parser.add_argument("--db_host", default="db", help="PostgreSQL host")
    parser.add_argument("--db_port", default=5432, type=int, help="PostgreSQL port")
    parser.add_argument("--db_user", default="odoo", help="PostgreSQL user")
    parser.add_argument("--db_password", default="odoo", help="PostgreSQL password")
    parser.add_argument("--database", default="postgres", help="PostgreSQL database")
    parser.add_argument("--timeout", default=60, type=int, help="Total timeout in seconds")
    args = parser.parse_args()
    wait_for_psql(args.db_host, args.db_port, args.db_user, args.db_password, args.database, args.timeout)
```

- [ ] **Step 3: Write `factory/odoo.conf`** (generic base template; entrypoint overrides the marked lines via sed)

```ini
[options]
# Odoo base image config template — "one image, two environments".
# Lines marked (env) are overwritten at container start by entrypoint.sh.

# Paths & Core
addons_path = /opt/odoo/addons
data_dir = /var/lib/odoo

# Security (env)
admin_passwd = changeme
list_db = True
dbfilter = .*
without_demo = True

# Performance (env)
workers = 0
max_cron_threads = 2
limit_memory_hard = 2684354560
limit_memory_soft = 2147483648
limit_time_cpu = 60
limit_time_real = 120

# Logging (env)
log_level = info
logfile = None
log_handler = [':INFO']

# Network & Proxy
http_port = 8069
gevent_port = 8072
proxy_mode = True

# Email (env)
smtp_server = localhost
smtp_port = 25
```

- [ ] **Step 4: Write `factory/entrypoint.sh`** (adapted from odoo-idp: dynamic addons_path, config injection, wait-for-psql, debugpy — NO auto-init; DB init is the caller's decision)

```bash
#!/bin/bash
set -e

# =============================================================================
# Odoo Forge — base image entrypoint (one image, two environments)
# =============================================================================

ODOO_RC=${ODOO_RC:-/etc/odoo/odoo.conf}
TEMP_ODOO_RC="/tmp/odoo.conf"

if [ ! -f "$ODOO_RC" ]; then
    echo "ERROR: Odoo configuration file not found at $ODOO_RC" >&2
    exit 1
fi

# Copy to a temp file so the mounted template can be read-only.
cp "$ODOO_RC" "$TEMP_ODOO_RC"
chmod 600 "$TEMP_ODOO_RC"

if [[ -z "${ODOO_ADMIN_PASSWD}" ]]; then
    ODOO_ADMIN_PASSWD=$(/opt/venv/bin/python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "NOTICE: ODOO_ADMIN_PASSWD auto-generated (set the env var to use a fixed value)"
fi

# ─── Build dynamic addons_path ──────────────────────────────
# Scan mounted layer dirs for Odoo modules (__manifest__.py). A base image
# ships none of these populated; higher layers / the local backend mount them.
build_addons_path() {
    local paths=""
    for base in /mnt/worktrees /mnt/custom /mnt/community /mnt/localization /mnt/enterprise; do
        if [ -d "$base" ]; then
            local dirs
            dirs=$(find "$base" -name '__manifest__.py' -type f 2>/dev/null | while read -r manifest; do dirname "$(dirname "$manifest")"; done | sort -u)
            for dir in $dirs; do paths="${paths}${dir},"; done
        fi
    done
    paths="${paths}/opt/odoo/addons"
    echo "$paths"
}

DYNAMIC_ADDONS_PATH=$(build_addons_path)
echo "addons_path: ${DYNAMIC_ADDONS_PATH}" >&2

run_odoo() {
    if [[ -n "${ODOO_DEBUG_PORT}" ]]; then
        if [[ "${ODOO_WORKERS:-0}" != "0" ]]; then
            echo "WARNING: debugpy requires workers=0. Forcing workers=0." >&2
            sed -i "s|^workers =.*|workers = 0|" "$TEMP_ODOO_RC"
        fi
        echo "NOTICE: Debug mode enabled on port ${ODOO_DEBUG_PORT}"
        exec /opt/venv/bin/python3 -m debugpy --listen 0.0.0.0:${ODOO_DEBUG_PORT} \
            /usr/local/bin/odoo "$@"
    else
        exec odoo "$@"
    fi
}

# Config injection (one image, two environments).
sed -i "s|^admin_passwd =.*|admin_passwd = ${ODOO_ADMIN_PASSWD}|" "$TEMP_ODOO_RC"
sed -i "s|^workers =.*|workers = ${ODOO_WORKERS:-0}|" "$TEMP_ODOO_RC"
sed -i "s|^log_level =.*|log_level = ${ODOO_LOG_LEVEL:-info}|" "$TEMP_ODOO_RC"
sed -i "s|^list_db =.*|list_db = ${ODOO_LIST_DB:-True}|" "$TEMP_ODOO_RC"
sed -i "s|^dbfilter =.*|dbfilter = ${ODOO_DB_FILTER:-.*}|" "$TEMP_ODOO_RC"
sed -i "s|^without_demo =.*|without_demo = ${ODOO_WITHOUT_DEMO:-True}|" "$TEMP_ODOO_RC"
sed -i "s|^proxy_mode =.*|proxy_mode = ${ODOO_PROXY_MODE:-True}|" "$TEMP_ODOO_RC"
sed -i "s|^smtp_server =.*|smtp_server = ${SMTP_SERVER:-localhost}|" "$TEMP_ODOO_RC"
sed -i "s|^smtp_port =.*|smtp_port = ${SMTP_PORT:-25}|" "$TEMP_ODOO_RC"
sed -i "s|^addons_path\s*=.*|addons_path = ${DYNAMIC_ADDONS_PATH}|" "$TEMP_ODOO_RC"

export ODOO_RC="$TEMP_ODOO_RC"

check_config() {
    DB_HOST=${DB_HOST:-${POSTGRES_HOST:-db}}
    DB_PORT=${DB_PORT:-${POSTGRES_PORT:-5432}}
    DB_USER=${DB_USER:-${POSTGRES_USER:-odoo}}
    DB_PASSWORD=${DB_PASSWORD:-${POSTGRES_PASSWORD:-odoo}}
    DB_ARGS=()
    DB_ARGS+=( "--db_host" "${DB_HOST}" )
    DB_ARGS+=( "--db_port" "${DB_PORT}" )
    DB_ARGS+=( "--db_user" "${DB_USER}" )
    DB_ARGS+=( "--db_password" "${DB_PASSWORD}" )
    DB_ARGS+=( "--database" "${POSTGRES_DB:-postgres}" )
}

check_config
echo "Waiting for PostgreSQL at ${DB_HOST:-db}..."
/opt/venv/bin/python3 /usr/local/bin/wait-for-psql.py \
    --db_host "${DB_HOST}" --db_port "${DB_PORT}" --db_user "${DB_USER}" \
    --db_password "${DB_PASSWORD}" --database "${POSTGRES_DB:-postgres}" --timeout=60

case "$1" in
    -- | odoo)
        shift
        DEV_ARGS=()
        if [[ -n "${ODOO_DEV_MODE}" ]] && [[ "${ODOO_DEV_MODE}" != "False" ]]; then
            DEV_ARGS+=( "--dev=${ODOO_DEV_MODE}" )
        fi
        run_odoo -c "$TEMP_ODOO_RC" "${DB_ARGS[@]}" "${DEV_ARGS[@]}" "$@"
        ;;
    -*)
        run_odoo -c "$TEMP_ODOO_RC" "${DB_ARGS[@]}" "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
```

- [ ] **Step 5: Lint the entrypoint**

Run: `shellcheck factory/entrypoint.sh`
Expected: no output, exit 0. (If `SC2086` warnings appear on intentional word-splitting of `$dirs`, they are acceptable — the odoo-idp original relies on it; leave as-is.)

- [ ] **Step 6: Syntax-check the Python probe**

Run: `python3 -m py_compile factory/wait-for-psql.py && echo OK`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add factory/extra_requirements.txt factory/wait-for-psql.py factory/odoo.conf factory/entrypoint.sh
git commit -m "feat(factory): add container support files (entrypoint, conf, deps, psql probe)"
```

---

## Task 3: Parameterized Dockerfile + local build helper

**Files:**
- Create: `factory/Dockerfile`
- Create: `factory/build.sh`

**Interfaces:**
- Consumes: `factory/versions.yaml` (Task 1), all support files (Task 2).
- Produces: `factory/build.sh <odoo-version>` builds and `--load`s a single-arch image tagged `ghcr.io/aparragithub/odoo-ce:<major>` (e.g. `:19`). Consumed by Task 4 and Task 5.

- [ ] **Step 1: Write `factory/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

# ============================================================
# Stage 1: Builder
# ============================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ARG ODOO_VERSION

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential git pkg-config \
    libpq-dev libldap2-dev libsasl2-dev libxml2-dev libxslt1-dev \
    libffi-dev libjpeg-dev zlib1g-dev

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Clone Odoo Community at the pinned version branch (shallow).
RUN git clone --branch ${ODOO_VERSION} --depth 1 \
    https://github.com/odoo/odoo.git /opt/odoo

# Layer 1: Odoo core deps (from the cloned source — version-correct by definition).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip wheel && \
    pip install -r /opt/odoo/requirements.txt

# Layer 2: Hand-maintained extra deps.
COPY factory/extra_requirements.txt /tmp/extra_requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /tmp/extra_requirements.txt

# ============================================================
# Stage 2: Production
# ============================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS production

ARG ODOO_VERSION
ARG ODOO_UID=1000
ARG ODOO_GID=1000
ARG ODOO_REVISION=unknown

ENV PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    PATH="/opt/venv/bin:/opt/odoo:$PATH" \
    ODOO_RC=/etc/odoo/odoo.conf \
    ODOO_VERSION=${ODOO_VERSION}

WORKDIR /opt/odoo

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl postgresql-client \
    libpq5 libldap-2.5-0 libsasl2-2 libxml2 libxslt1.1 libjpeg62-turbo \
    zlib1g libffi8 fontconfig xfonts-75dpi xfonts-base fonts-noto-cjk \
    libx11-6 libxcb1 libxext6 libxrender1 \
    && ARCH=$(dpkg --print-architecture); \
    if [ "$ARCH" = "amd64" ]; then \
      curl -o /tmp/wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb; \
    elif [ "$ARCH" = "arm64" ]; then \
      curl -o /tmp/wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_arm64.deb; \
    fi; \
    apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb && rm -f /tmp/wkhtmltox.deb

RUN groupadd -g ${ODOO_GID} odoo \
    && useradd -u ${ODOO_UID} -g odoo -m -s /bin/bash odoo

RUN mkdir -p /mnt/custom /mnt/community /mnt/localization /mnt/enterprise /var/lib/odoo /etc/odoo \
    && chown -R odoo:odoo /mnt/custom /mnt/community /mnt/localization /mnt/enterprise /var/lib/odoo /etc/odoo

COPY --chown=odoo:odoo --from=builder /opt/venv /opt/venv
COPY --chown=odoo:odoo --from=builder /opt/odoo /opt/odoo

RUN ln -s /opt/odoo/odoo-bin /usr/local/bin/odoo

COPY --chown=odoo:odoo factory/odoo.conf /etc/odoo/odoo.conf
COPY --chown=odoo:odoo factory/entrypoint.sh /entrypoint.sh
COPY --chown=odoo:odoo factory/wait-for-psql.py /usr/local/bin/wait-for-psql.py
RUN chmod +x /entrypoint.sh /usr/local/bin/wait-for-psql.py

VOLUME ["/var/lib/odoo"]
EXPOSE 8069 8072

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8069/web/health || exit 1

LABEL org.opencontainers.image.title="odoo-ce" \
      org.opencontainers.image.source="https://github.com/aparragithub/odoo-forge" \
      org.opencontainers.image.revision="${ODOO_REVISION}" \
      org.opencontainers.image.version="${ODOO_VERSION}"

USER odoo

ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]
```

- [ ] **Step 2: Write `factory/build.sh`**

```bash
#!/usr/bin/env bash
# Build one Odoo CE base image single-arch (host arch), loaded into the local
# Docker daemon for testing. Resolves Python base + Odoo SHA from versions.yaml.
set -euo pipefail

VERSION="${1:?usage: build.sh <odoo-version>   e.g. build.sh 19.0}"

PYTHON=$(yq -r ".versions[] | select(.odoo == \"$VERSION\") | .python" factory/versions.yaml)
if [ -z "$PYTHON" ] || [ "$PYTHON" = "null" ]; then
    echo "ERROR: version $VERSION not found in factory/versions.yaml" >&2
    exit 1
fi

REV=$(git ls-remote https://github.com/odoo/odoo.git "refs/heads/$VERSION" | cut -f1)
TAG="ghcr.io/aparragithub/odoo-ce:${VERSION%.0}"

echo "Building $TAG  (odoo $VERSION, python $PYTHON, rev ${REV:0:7})"
docker buildx build \
    -f factory/Dockerfile \
    --build-arg ODOO_VERSION="$VERSION" \
    --build-arg PYTHON_VERSION="$PYTHON" \
    --build-arg ODOO_REVISION="$REV" \
    --build-arg ODOO_UID=1000 \
    --build-arg ODOO_GID=1000 \
    -t "$TAG" \
    --load \
    .
echo "Built: $TAG"
```

- [ ] **Step 3: Make the helper executable and lint it**

Run: `chmod +x factory/build.sh && shellcheck factory/build.sh`
Expected: exit 0, no errors.

- [ ] **Step 4: Build Odoo 19.0 locally**

Run: `./factory/build.sh 19.0`
Expected: build completes; final line `Built: ghcr.io/aparragithub/odoo-ce:19`.

- [ ] **Step 5: Verify the version baked into the image**

Run: `docker run --rm --entrypoint odoo ghcr.io/aparragithub/odoo-ce:19 --version`
Expected: output contains `Odoo Server 19.0`.

- [ ] **Step 6: Verify the OCI revision label is set**

Run: `docker inspect ghcr.io/aparragithub/odoo-ce:19 --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'`
Expected: a 40-character git SHA (not `unknown`).

- [ ] **Step 7: Commit**

```bash
git add factory/Dockerfile factory/build.sh
git commit -m "feat(factory): parameterized multi-stage Dockerfile + local build helper"
```

---

## Task 4: Smoke-test gate

**Files:**
- Create: `factory/smoke-test.sh`

**Interfaces:**
- Consumes: an image ref (the one built in Task 3).
- Produces: `factory/smoke-test.sh <image-ref>` — exits 0 only if Odoo initializes `base,sale,purchase,stock` against a fresh PostgreSQL. Reused verbatim by the CI workflow (Task 6). Manages its own Postgres container on a throwaway network, so it behaves identically locally and in CI (no reliance on GitHub service-container networking).

- [ ] **Step 1: Write `factory/smoke-test.sh`**

```bash
#!/usr/bin/env bash
# Publish gate: boot the given image against an ephemeral PostgreSQL and
# initialize base,sale,purchase,stock. Non-zero exit blocks publishing. Self-contained:
# creates and tears down its own network + Postgres, so it runs identically
# locally and in CI.
set -euo pipefail

IMAGE="${1:?usage: smoke-test.sh <image-ref>}"
SUFFIX="$$-${RANDOM}"
NET="odoo-smoke-${SUFFIX}"
PG="pg-smoke-${SUFFIX}"

cleanup() {
    docker rm -f "$PG" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" \
    -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres \
    postgres:16 >/dev/null

echo "==> Smoke test: $IMAGE  (odoo -i base,sale,purchase,stock --stop-after-init)"
docker run --rm --network "$NET" \
    -e DB_HOST="$PG" -e DB_PORT=5432 -e DB_USER=odoo -e DB_PASSWORD=odoo \
    -e POSTGRES_DB=postgres \
    "$IMAGE" \
    odoo -d smoke_test -i base,sale,purchase,stock --stop-after-init --no-http

echo "==> SMOKE TEST PASSED: $IMAGE"
```

Note on DB args: the entrypoint's `wait-for-psql` connects to `POSTGRES_DB=postgres` (which always exists). The `-d smoke_test` passed here overrides the config's database (last value wins in Odoo's option parser), so Odoo creates and initializes a fresh `smoke_test` DB.

- [ ] **Step 2: Make executable and lint**

Run: `chmod +x factory/smoke-test.sh && shellcheck factory/smoke-test.sh`
Expected: exit 0, no errors.

- [ ] **Step 3: Run the smoke test against the 19.0 image (happy path)**

Run: `./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:19`
Expected: Odoo logs `Modules loaded.` then `Initiating shutdown`; script prints `==> SMOKE TEST PASSED` and exits 0.

- [ ] **Step 4: Prove the gate actually blocks (red test)**

**Important — what the gate catches:** the smoke test catches **real crashes** during init: a missing runtime Python dependency (ImportError while a module loads) or a DB init failure. It does **NOT** catch a *nonexistent module name* — Odoo only logs a warning for an unknown `-i` module and exits **0**. So `-i nonexistent_module` is an INVALID red test (it would pass, falsely). The valid red test breaks a real dependency, matching the spec §8 criterion ("verified by intentionally breaking a dependency").

Run (on a throwaway network + Postgres, remove a real runtime dep in a disposable layer, then init):

```bash
NET="rt-$$"; PG="pg-rt-$$"
docker network create "$NET"
docker run -d --name "$PG" --network "$NET" -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres postgres:16
sleep 3
docker run --rm --network "$NET" -e DB_HOST="$PG" -e DB_USER=odoo -e DB_PASSWORD=odoo -e POSTGRES_DB=postgres \
  --entrypoint bash ghcr.io/aparragithub/odoo-ce:19 -c \
  "pip uninstall -y python-dateutil >/dev/null 2>&1 && odoo -d rt -i base --stop-after-init --no-http --db_host $PG --db_user odoo --db_password odoo"
echo "exit=$?"
docker rm -f "$PG"; docker network rm "$NET"
```

Expected: Odoo aborts with `ModuleNotFoundError: No module named 'dateutil'` and a **non-zero** exit (observed: exit 1). Because `smoke-test.sh` runs `odoo ... --stop-after-init` under `set -e`, a real broken image produces exactly this non-zero exit and blocks publishing. (One-off proof; no file changes — the disposable `pip uninstall` runs only in the throwaway container, never in the built image.)

- [ ] **Step 5: Commit**

```bash
git add factory/smoke-test.sh
git commit -m "feat(factory): reusable smoke-test publish gate"
```

---

## Task 5: Verify cross-version parameterization + document usage

Proves the `ODOO_VERSION`/`PYTHON_VERSION` parameterization works for a version with a **different Python base** (16.0 → 3.11), not just the default. Ships the local-usage docs as the task deliverable.

**Files:**
- Create: `factory/README.md`

**Interfaces:**
- Consumes: `build.sh`, `smoke-test.sh`, `versions.yaml`.
- Produces: `factory/README.md` documenting local build + test.

- [ ] **Step 1: Build Odoo 16.0 (different Python base: 3.11)**

Run: `./factory/build.sh 16.0`
Expected: build completes on `python:3.11-slim-bookworm`; final line `Built: ghcr.io/aparragithub/odoo-ce:16`.

- [ ] **Step 2: Verify the 16.0 version**

Run: `docker run --rm --entrypoint odoo ghcr.io/aparragithub/odoo-ce:16 --version`
Expected: output contains `Odoo Server 16.0`.

- [ ] **Step 3: Smoke-test the 16.0 image**

Run: `./factory/smoke-test.sh ghcr.io/aparragithub/odoo-ce:16`
Expected: `==> SMOKE TEST PASSED`, exit 0. (This proves the matrix design: a version on a different Python base builds and initializes with no Dockerfile branching.)

- [ ] **Step 4: Write `factory/README.md`**

````markdown
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
````

- [ ] **Step 5: Commit**

```bash
git add factory/README.md
git commit -m "docs(factory): local build/test usage; verified 16.0 on python 3.11"
```

---

## Task 6: CI workflow — build-by-digest + multi-arch merge

**Files:**
- Create: `.github/workflows/build-images.yml`

**Interfaces:**
- Consumes: `factory/versions.yaml`, `factory/Dockerfile`, `factory/smoke-test.sh`.
- Produces: multi-arch manifest lists at `ghcr.io/aparragithub/odoo-ce:<major>` and `:<version>-<YYYYMMDD>`.

- [ ] **Step 1: Write `.github/workflows/build-images.yml`**

```yaml
name: Build Odoo CE base images

on:
  push:
    branches: [main]
    paths:
      - 'factory/**'
      - '.github/workflows/build-images.yml'
  workflow_dispatch:

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/odoo-ce

jobs:
  setup:
    runs-on: ubuntu-latest
    outputs:
      versions: ${{ steps.gen.outputs.versions }}
      date: ${{ steps.gen.outputs.date }}
    steps:
      - uses: actions/checkout@v4
      - uses: mikefarah/yq@v4
      - id: gen
        run: |
          versions=$(yq -o=json -I=0 '.versions' factory/versions.yaml)
          echo "versions=$versions" >> "$GITHUB_OUTPUT"
          echo "date=$(date -u +%Y%m%d)" >> "$GITHUB_OUTPUT"

  build:
    needs: setup
    permissions:
      contents: read
      packages: write
    strategy:
      fail-fast: false
      matrix:
        entry: ${{ fromJson(needs.setup.outputs.versions) }}
        arch: [amd64, arm64]
    runs-on: ${{ matrix.arch == 'arm64' && 'ubuntu-24.04-arm' || 'ubuntu-latest' }}
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Resolve Odoo source SHA
        id: rev
        run: |
          sha=$(git ls-remote https://github.com/odoo/odoo.git "refs/heads/${{ matrix.entry.odoo }}" | cut -f1)
          echo "sha=$sha" >> "$GITHUB_OUTPUT"

      - name: Build (load for smoke test)
        uses: docker/build-push-action@v6
        with:
          context: .
          file: factory/Dockerfile
          platforms: linux/${{ matrix.arch }}
          load: true
          tags: odoo-ce:test
          build-args: |
            ODOO_VERSION=${{ matrix.entry.odoo }}
            PYTHON_VERSION=${{ matrix.entry.python }}
            ODOO_REVISION=${{ steps.rev.outputs.sha }}
            ODOO_UID=1000
            ODOO_GID=1000
          cache-from: type=gha,scope=${{ matrix.entry.odoo }}-${{ matrix.arch }}
          cache-to: type=gha,mode=max,scope=${{ matrix.entry.odoo }}-${{ matrix.arch }}

      - name: Smoke test (publish gate)
        run: ./factory/smoke-test.sh odoo-ce:test

      - name: Push by digest
        id: push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: factory/Dockerfile
          platforms: linux/${{ matrix.arch }}
          outputs: type=image,name=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }},push-by-digest=true,name-canonical=true,push=true
          build-args: |
            ODOO_VERSION=${{ matrix.entry.odoo }}
            PYTHON_VERSION=${{ matrix.entry.python }}
            ODOO_REVISION=${{ steps.rev.outputs.sha }}
            ODOO_UID=1000
            ODOO_GID=1000
          cache-from: type=gha,scope=${{ matrix.entry.odoo }}-${{ matrix.arch }}

      - name: Export digest
        run: |
          mkdir -p /tmp/digests
          digest="${{ steps.push.outputs.digest }}"
          touch "/tmp/digests/${digest#sha256:}"

      - name: Upload digest
        uses: actions/upload-artifact@v4
        with:
          name: digest-${{ matrix.entry.odoo }}-${{ matrix.arch }}
          path: /tmp/digests/*
          retention-days: 1

  merge:
    needs: [setup, build]
    permissions:
      contents: read
      packages: write
    strategy:
      matrix:
        entry: ${{ fromJson(needs.setup.outputs.versions) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          pattern: digest-${{ matrix.entry.odoo }}-*
          path: /tmp/digests
          merge-multiple: true

      - uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Create multi-arch manifest list
        working-directory: /tmp/digests
        run: |
          MAJOR="${{ matrix.entry.odoo }}"; MAJOR="${MAJOR%.0}"
          IMMUTABLE="${{ matrix.entry.odoo }}-${{ needs.setup.outputs.date }}"
          docker buildx imagetools create \
            -t "${REGISTRY}/${IMAGE_NAME}:${MAJOR}" \
            -t "${REGISTRY}/${IMAGE_NAME}:${IMMUTABLE}" \
            $(for d in *; do echo "${REGISTRY}/${IMAGE_NAME}@sha256:${d}"; done)

      - name: Inspect result
        run: |
          MAJOR="${{ matrix.entry.odoo }}"; MAJOR="${MAJOR%.0}"
          docker buildx imagetools inspect "${REGISTRY}/${IMAGE_NAME}:${MAJOR}"
```

- [ ] **Step 2: Lint the workflow** (if `actionlint` is available)

Run: `actionlint .github/workflows/build-images.yml`
Expected: exit 0. (If `actionlint` is not installed, skip — the real gate is the CI run in Step 4.)

- [ ] **Step 3: Commit and push**

```bash
git add .github/workflows/build-images.yml
git commit -m "ci(factory): build + smoke-test + publish multi-arch CE images to GHCR"
git push
```

- [ ] **Step 4: Verify the workflow run (the real gate)**

Run: `gh run watch $(gh run list --workflow=build-images.yml --limit 1 --json databaseId -q '.[0].databaseId')`
Expected: all 8 `build` jobs (4 versions × 2 arches) pass their smoke test and push by digest; all 4 `merge` jobs succeed.

- [ ] **Step 5: Verify the published images**

Run: `docker buildx imagetools inspect ghcr.io/aparragithub/odoo-ce:19`
Expected: a manifest list with two entries — `linux/amd64` and `linux/arm64`.

Run: `docker run --rm --entrypoint odoo ghcr.io/aparragithub/odoo-ce:16 --version`
Expected: `Odoo Server 16.0` (confirms the pulled multi-arch image runs on the host arch).

---

## Self-Review

**Spec coverage** (against `2026-07-05-phase-1-image-factory-design.md`):

- §1 CE-only, 4 versions, 2 arches, GHCR/Actions → Tasks 1, 3, 6. ✅
- §3 bug #3 (no collected reqs) → Task 3 Dockerfile (only `requirements.txt` + `extra_requirements.txt`). ✅
- §3 bug #2 (UID/GID passed for real) → Task 3 `build.sh` + Task 6 `build-args`. ✅
- §3 bug #1 (N/A) → not carried; nothing to do. ✅
- §4 clone-at-branch + PYTHON_VERSION mapping + OCI revision label → Task 1 (matrix), Task 3 (Dockerfile ARGs + LABEL), verified Task 3 Step 6 / Task 5. ✅
- §5 repo structure → Tasks 1–6 create exactly the listed files. ✅
- §6 CI build-by-digest + merge, smoke gate, native ARM runners → Task 6. ✅
- §7 moving + immutable tags, digest rule → Task 6 merge job. ✅
- §8 success criteria (pull works, boots, red test blocks, revision label, add-a-version = one entry) → Task 4 Step 4 (red test), Task 5 (add-a-version proof + 16.0), Task 6 Steps 4–5. ✅

**Placeholder scan:** No `TBD`/`TODO`/"handle edge cases" in steps. The `odoo.conf` `admin_passwd = changeme` is a real default overwritten by the entrypoint at start, not a placeholder. ✅

**Type/name consistency:** `versions.yaml` keys `odoo`/`python` used identically in `build.sh`, `setup` job, and matrix (`matrix.entry.odoo` / `matrix.entry.python`). Image name `ghcr.io/aparragithub/odoo-ce` and moving-tag derivation `${VERSION%.0}` consistent across `build.sh`, `smoke-test.sh` args, and the merge job. Smoke test invoked as `smoke-test.sh <image>` in both Task 4 and Task 6. ✅

**Known execution risks (flagged, not blockers):**
- `ubuntu-24.04-arm` hosted runners must be available to the account; if not, fall back to a QEMU build for arm64 (`docker/setup-qemu-action` + single-runner multi-platform build) — a workflow-only change.
- Exact `odoo → python` mapping (Open Question §9) is validated empirically by Task 5 (16.0) and Task 6 (all four); if a version fails to build on its mapped Python, adjust its `versions.yaml` entry and re-run — no other file changes.
