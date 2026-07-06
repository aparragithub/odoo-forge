#!/usr/bin/env bash
# Build one Odoo CE base image single-arch (host arch), loaded into the local
# Docker daemon for testing. Resolves Python base + Odoo SHA from versions.yaml.
set -euo pipefail

# Parse the "<owner>" segment out of a git remote URL and echo the derived
# "ghcr.io/<owner>/odoo-ce" image name. Supports the SSH, HTTPS and
# ssh:// forms GitHub issues for "git remote get-url origin". Fails loudly
# (non-zero, message on stderr) on anything else so callers don't silently
# build against a garbage image name.
derive_image_name() {
    local remote_url="$1"
    local owner=""
    if [[ "$remote_url" =~ ^git@github\.com:([^/]+)/ ]]; then
        owner="${BASH_REMATCH[1]}"
    elif [[ "$remote_url" =~ ^https://github\.com/([^/]+)/ ]]; then
        owner="${BASH_REMATCH[1]}"
    elif [[ "$remote_url" =~ ^ssh://git@github\.com/([^/]+)/ ]]; then
        owner="${BASH_REMATCH[1]}"
    fi
    if [ -z "$owner" ]; then
        echo "ERROR: could not parse owner from origin remote URL: $remote_url (set IMAGE to override)" >&2
        return 1
    fi
    echo "ghcr.io/${owner}/odoo-ce"
}

# Resolve the image name to build: an explicit IMAGE override always wins;
# otherwise derive it from the given origin remote URL (may be empty, in
# which case this fails loudly since there is nothing to derive from).
resolve_image_name() {
    local remote_url="${1:-}"
    if [ -n "${IMAGE:-}" ]; then
        echo "$IMAGE"
        return 0
    fi
    if [ -z "$remote_url" ]; then
        echo "ERROR: no git remote 'origin' found; set IMAGE to override" >&2
        return 1
    fi
    derive_image_name "$remote_url"
}

# Resolve the Odoo commit SHA to build. An explicit ODOO_REVISION gives
# parity with a specific CI-built image (skip ls-remote, build exactly that
# SHA) -- it is an intentional escape hatch and is NOT validated against the
# upstream branch, so warn loudly that it's used as-given. Otherwise resolve
# the current branch head via ls-remote, same as before.
resolve_odoo_revision() {
    local version="$1"
    if [ -n "${ODOO_REVISION:-}" ]; then
        echo "WARNING: ODOO_REVISION=$ODOO_REVISION is used as-given and is NOT verified to belong to refs/heads/$version upstream." >&2
        echo "$ODOO_REVISION"
        return 0
    fi
    local rev
    rev=$(git ls-remote https://github.com/odoo/odoo.git "refs/heads/$version" | cut -f1)
    if [ -z "$rev" ]; then
        echo "ERROR: could not resolve Odoo commit SHA for branch $version (does refs/heads/$version exist upstream?)" >&2
        return 1
    fi
    echo "$rev"
}

main() {
    cd "$(git rev-parse --show-toplevel)"

    VERSION="${1:?usage: build.sh <odoo-version>   e.g. build.sh 19.0}"

    PYTHON=$(yq -r ".versions[] | select(.odoo == \"$VERSION\") | .python" factory/versions.yaml)
    if [ -z "$PYTHON" ] || [ "$PYTHON" = "null" ]; then
        echo "ERROR: version $VERSION not found in factory/versions.yaml" >&2
        exit 1
    fi

    # Image name: honor an explicit IMAGE override, otherwise derive
    # "ghcr.io/<owner>/odoo-ce" from the origin remote so the script keeps
    # working after a repo transfer or fork, matching how CI derives it
    # from github.repository_owner.
    REMOTE_URL=""
    if [ -z "${IMAGE:-}" ]; then
        REMOTE_URL=$(git remote get-url origin 2>/dev/null) || true
    fi
    IMAGE_NAME=$(resolve_image_name "$REMOTE_URL") || exit 1

    REV=$(resolve_odoo_revision "$VERSION") || exit 1
    TAG="${IMAGE_NAME}:${VERSION%%.*}"

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
}

# Allow this script to be sourced (e.g. by tests) without triggering a build.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
