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
