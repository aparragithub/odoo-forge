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
WEB="web-smoke-${SUFFIX}"

cleanup() {
    docker rm -f "$WEB" >/dev/null 2>&1 || true
    docker rm -f "$PG" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "$NET" >/dev/null
docker run -d --name "$PG" --network "$NET" \
    -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres \
    postgres:16 >/dev/null

echo "==> Smoke test: $IMAGE  (odoo -i base,sale,purchase,stock --stop-after-init)"
set +e
timeout 900 docker run --rm --network "$NET" \
    -e DB_HOST="$PG" -e DB_PORT=5432 -e DB_USER=odoo -e DB_PASSWORD=odoo \
    -e POSTGRES_DB=postgres \
    "$IMAGE" \
    odoo -d smoke_test -i base,sale,purchase,stock --stop-after-init --no-http
status=$?
set -e
if [ "$status" -ne 0 ]; then
    if [ "$status" -eq 124 ]; then
        echo "==> SMOKE TEST FAILED: $IMAGE  (module install did not finish within 900s timeout)" >&2
    else
        echo "==> SMOKE TEST FAILED: $IMAGE  (module install exited with status $status)" >&2
    fi
    exit 1
fi

echo "==> Smoke test: $IMAGE  (HTTP health check on a normal server launch)"
docker run -d --name "$WEB" --network "$NET" \
    -e DB_HOST="$PG" -e DB_PORT=5432 -e DB_USER=odoo -e DB_PASSWORD=odoo \
    -e POSTGRES_DB=postgres \
    "$IMAGE" \
    odoo -d smoke_test >/dev/null

# Poll /web/health via `docker exec curl` inside the container's own network
# namespace — avoids depending on host port publishing, so this works
# identically whether the runner maps ports or not (local or CI).
HEALTH_OK=""
for _ in $(seq 1 30); do
    if docker exec "$WEB" curl -sf -o /dev/null -w '%{http_code}' http://localhost:8069/web/health 2>/dev/null | grep -q '^200$'; then
        HEALTH_OK=1
        break
    fi
    sleep 2
done

if [[ -z "$HEALTH_OK" ]]; then
    echo "==> SMOKE TEST FAILED: $IMAGE  (/web/health did not return 200 within timeout)" >&2
    echo "----- container logs -----" >&2
    docker logs "$WEB" >&2 || true
    exit 1
fi

echo "==> SMOKE TEST PASSED: $IMAGE"
