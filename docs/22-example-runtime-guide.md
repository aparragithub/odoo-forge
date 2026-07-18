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

## Troubleshooting

| Problem | What to do |
|---|---|
| `sops` missing | Install `sops` locally and confirm it is on `PATH`. `forge run` depends on calling it directly. |
| `credential material is unavailable` | Create `example/credentials.sops.yaml`, encrypt it with `sops`, and confirm your local Age key can decrypt it. |
| Odoo image missing | Make sure `odoo-forge-odoo:19.0` exists locally. Build with `factory/build.sh 19.0` and retag if the build produced a different name. |
| manifest/lock drift | Re-run `uv run forge validate --manifest example/project.yaml`. If drift is reported, refresh `example/project.lock` before `project` or `run`. |
| Local access works but LAN access fails | First confirm the service is up locally at `127.0.0.1:18069`. Then check host firewall rules, Docker host reachability, and that the client is using the correct host LAN IP. |
