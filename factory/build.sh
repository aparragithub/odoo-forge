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
