# Render the current implementation diagram

`odoo-forge-current-implementation.mmd` is the source of truth. Its adjacent
`odoo-forge-current-implementation.mmd.svg` is generated and must change only by running the
renderer.

## Render

From the repository root, run:

```sh
docs/diagrams/render-current-implementation.sh
```

The script uses the official Mermaid CLI `11.16.0` image, pinned to this immutable OCI index:

```text
ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0@sha256:29077c6bd02f14bdfdd5fee552d9c00fe68d4fab3cd84952d21e2d1faf2fadaf
```

Docker is the default runtime. Podman users can preserve their user namespace with:

```sh
CONTAINER_RUNTIME=podman docs/diagrams/render-current-implementation.sh
```

On hosts where `getenforce` reports `Enforcing`, the script adds the `:Z` private-label option to
the bind mount for both Docker and Podman. It leaves the option off when SELinux is permissive,
disabled, or unavailable, so the same command remains portable to non-SELinux systems.

The script writes as the host UID/GID. Its checked-in Mermaid and Puppeteer configurations fix the
theme, background, font stack, deterministic Mermaid ID seed, viewport, device scale, and Chromium
launch arguments.

## Check

The isolated generated-file check renders to a temporary sibling and compares it byte-for-byte:

```sh
docs/diagrams/render-current-implementation.sh --check
```

Use that command as a dedicated documentation job in CI. It requires Docker (or Podman through
`CONTAINER_RUNTIME`) and may pull the image if the exact digest is not cached; it never resolves an
unpinned tag. Ordinary Python unit tests do not invoke the container.

Byte-for-byte equality is the acceptance criterion only after two consecutive renders prove that
this pinned Mermaid/Chromium image emits stable SVG in the execution environment. If that check
ever fails between identical renders, inspect the diff before adding normalization. Normalize only
confirmed non-semantic metadata, document the transformation here, and keep it in the render script;
never hand-edit generated SVG.

## Update the renderer

1. Choose a concrete release from the official `mermaid-js/mermaid-cli` releases.
2. Verify the matching GHCR manifest and record its `Docker-Content-Digest`.
3. Update both the tag and digest in `render-current-implementation.sh`.
4. Render twice from a clean source and compare the two SVG files byte-for-byte.
5. Run `--check`, inspect the SVG diff, and commit the script, configuration, source, and generated
   SVG as one reviewable work unit.

The current tag was verified against the official `11.16.0` GitHub release and GHCR returned OCI
index digest `sha256:29077c6bd02f14bdfdd5fee552d9c00fe68d4fab3cd84952d21e2d1faf2fadaf`.
