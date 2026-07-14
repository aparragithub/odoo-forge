#!/bin/sh
set -eu

IMAGE='ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0@sha256:29077c6bd02f14bdfdd5fee552d9c00fe68d4fab3cd84952d21e2d1faf2fadaf'
SOURCE='odoo-forge-current-implementation.mmd'
OUTPUT='odoo-forge-current-implementation.mmd.svg'
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

case "${1:-render}" in
  render)
    container_output=$OUTPUT
    host_output="$script_dir/$OUTPUT"
    ;;
  --check)
    host_output=$(mktemp "$script_dir/.odoo-forge-current-implementation.check.XXXXXX.svg")
    container_output=${host_output##*/}
    trap 'rm -f "$host_output"' EXIT HUP INT TERM
    ;;
  *)
    printf 'Usage: %s [render|--check]\n' "$0" >&2
    exit 2
    ;;
esac

runtime=${CONTAINER_RUNTIME:-docker}

if command -v getenforce >/dev/null 2>&1 && [ "$(getenforce)" = Enforcing ]; then
  volume_suffix=':Z'
else
  volume_suffix=''
fi

case "$runtime" in
  docker)
    user_args="--user $(id -u):$(id -g)"
    ;;
  podman)
    user_args="--userns keep-id --user $(id -u):$(id -g)"
    ;;
  *)
    printf 'CONTAINER_RUNTIME must be docker or podman, got: %s\n' "$runtime" >&2
    exit 2
    ;;
esac

if ! command -v "$runtime" >/dev/null 2>&1; then
  printf 'Container runtime not found: %s\n' "$runtime" >&2
  exit 127
fi

# Word splitting is intentional: both supported argument sets contain separate flags.
# shellcheck disable=SC2086
"$runtime" run --rm $user_args \
  --volume "$script_dir:/data$volume_suffix" \
  "$IMAGE" \
  --input "$SOURCE" \
  --output "$container_output" \
  --configFile mermaid-config.json \
  --puppeteerConfigFile puppeteer-config.json \
  --backgroundColor white \
  --width 1800 \
  --height 1200 \
  --scale 1 \
  --quiet

if [ "${1:-render}" = '--check' ]; then
  if ! cmp -s "$script_dir/$OUTPUT" "$host_output"; then
    printf '%s is stale; run %s\n' "$OUTPUT" "$0" >&2
    exit 1
  fi
  printf '%s is current\n' "$OUTPUT"
fi
