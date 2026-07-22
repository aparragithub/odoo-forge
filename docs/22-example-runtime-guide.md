# Bring Up the Versioned Example Odoo Runtime

Use `example/project.yaml` as the versioned manifest. Keep `example/project.lock` and `example/credentials.sops.yaml` local only; both are ignored on purpose.

## Quick path

1. Prepare local `age` + `sops`, then create an encrypted `example/credentials.sops.yaml`.
2. Ensure the Odoo image exists locally as `odoo-forge-odoo:19.0`.
3. Run `uv run forge validate`, `uv run forge project`, and `uv run forge run` against `example/project.yaml`.
4. Verify access locally and from another machine on the LAN.

## Recommended manifest shape

`example/project.yaml` should include at least:

```yaml
workspace:
  checkout_timeout_seconds: 300
backend:
  odoo:
    bind_host: 0.0.0.0
    http_port: 18069
```

## 1. Prepare credentials

One time on your machine, make sure `age` and `sops` are installed and that your local Age key can decrypt the file you create.

Create `example/credentials.sops.yaml` with these keys and encrypt it with `sops`:

```yaml
local-backend/postgres-password: <postgres-password>
local-backend/odoo-db-password: <odoo-db-password>
```

The runtime reads `example/credentials.sops.yaml` next to the manifest. If the file is missing, unencrypted, or not decryptable on this machine, `forge run` will fail.

## 2. Ensure the image exists locally

The example runtime expects the Odoo image tag `odoo-forge-odoo:19.0` to exist in your local Docker daemon.

Check it:

```bash
docker image inspect odoo-forge-odoo:19.0 >/dev/null
```

If it is missing, build an Odoo 19 image:

```bash
factory/build.sh 19.0
```

That build flow may produce a different local tag, so retag it if needed so the runtime can find the exact tag it plans:

```bash
docker tag <built-image> odoo-forge-odoo:19.0
```

## 3. Validate, project, and run

From the repo root:

```bash
uv run forge validate --manifest example/project.yaml
uv run forge project --manifest example/project.yaml
uv run forge run --manifest example/project.yaml
```

Expected flow:

- `validate` checks the manifest and reports manifest/lock drift when relevant.
- `project` materializes the locked workspace declared by `example/project.lock`.
- `run` starts PostgreSQL and Odoo using the local Docker backend.

## 4. Verify access

With `backend.odoo.bind_host: 0.0.0.0` and `backend.odoo.http_port: 18069`:

- Local machine: `http://127.0.0.1:18069`
- LAN machine: `http://<your-host-lan-ip>:18069`
- Example LAN URL on the current host: `http://192.168.1.216:18069`

Replace the LAN IP with the actual IP of the machine running Docker.

If the service is up but you want confirmation from the CLI:

```bash
uv run forge status --manifest example/project.yaml
```

## 5. Optional: test the Enterprise source credential

`example/project.yaml` stays `edition: community` on purpose — no token required
for the default example. If you want to exercise the Enterprise credential flow
(`source-credentials-model`) locally, follow this on a **separate** manifest or
a scratch copy, not on the versioned `example/project.yaml`.

### 5.1 Create a GitHub token with Enterprise access

1. On GitHub, go to **Settings → Developer settings → Personal access tokens
   → Fine-grained tokens** (or Tokens (classic) if your org requires it).
2. Create a token scoped to read access on `odoo/enterprise` (or your private
   fork/mirror). Fine-grained tokens: grant **Contents: Read-only** on that
   repository only. Classic tokens: the `repo` scope is the minimum that
   works, but prefer fine-grained + read-only when your GitHub plan supports it.
3. Set an expiration and copy the token value once — GitHub will not show it again.

### 5.2 Register it locally, so `forge lock`/`forge onboard` can use it

The Enterprise credential is resolved by convention, under the handle
`enterprise/source-git` — you never declare it in the manifest. Create (or add
to) your local `credentials.sops.yaml`, next to the manifest you're testing with:

```yaml
enterprise/source-git: <your-github-token>
local-backend/postgres-password: <postgres-password>
local-backend/odoo-db-password: <odoo-db-password>
```

Encrypt it with `sops` using your local Age key, the same way as step 1 above.
`forge doctor` will confirm both the Age key and this conventional entry
resolve before you try a real fetch:

```bash
uv run forge doctor
```

To rotate the token later (e.g. after regenerating it on GitHub), update the
plaintext value and re-run:

```bash
uv run forge rotate-enterprise-credential
```

### 5.3 Register it in GitHub, so CI can use it

CI decrypts the same way, via a repository secret written to a runner keyfile
(see `.github/workflows/quality.yml`). On GitHub:

1. Go to the repo's **Settings → Secrets and variables → Actions**.
2. Add a new repository secret named `SOPS_AGE_KEY_ENTERPRISE`.
3. Its value is your **Age private key** (the `AGE-SECRET-KEY-...` line from
   `~/.config/sops/age/keys.txt`), **not** the GitHub token — CI needs the Age
   key to decrypt `credentials.sops.yaml`, which must contain the
   `enterprise/source-git` entry (encrypted with a recipient CI can decrypt,
   i.e. this same Age key's public key must be one of the `.sops.yaml`
   recipients for that file).
4. Fork PRs never receive this secret (the workflow guards for that and skips
   the keyfile step); only pushes/PRs within this repository can decrypt.

### 5.4 Host allow-list note

The credential is only ever injected for fetch URLs whose host is
`github.com` (the default Enterprise host, exact match). If you point
`enterprise.url` at a different host, injection is refused fail-fast — this
is a deliberate security control, not a bug.

## Troubleshooting

| Problem | What to do |
|---|---|
| `sops` missing | Install `sops` locally and confirm it is on `PATH`. `forge run` depends on calling it directly. |
| `credential material is unavailable` | Create `example/credentials.sops.yaml`, encrypt it with `sops`, and confirm your local Age key can decrypt it. |
| `Enterprise credential required but unavailable` | Run `uv run forge doctor` to see whether the Age key or the `enterprise/source-git` entry is missing, then follow §5. |
| `Enterprise credential injection refused: host '...' is not an allowed enterprise credential host` | `enterprise.url` points at a host other than `github.com`. This is the allow-list rejecting an unexpected host on purpose. |
| Odoo image missing | Make sure `odoo-forge-odoo:19.0` exists locally. Build with `factory/build.sh 19.0` and retag if the build produced a different name. |
| manifest/lock drift | Re-run `uv run forge validate --manifest example/project.yaml`. If drift is reported, refresh `example/project.lock` before `project` or `run`. |
| Local access works but LAN access fails | First confirm the service is up locally at `127.0.0.1:18069`. Then check host firewall rules, Docker host reachability, and that the client is using the correct host LAN IP. |
