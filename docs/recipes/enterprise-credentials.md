# Enterprise credentials with SOPS/age

Odoo Enterprise lives in a private repository. odoo-forge materializes the
credential for cloning it from an encrypted file next to your manifest —
never from your shell history, never committed in plaintext.

## How it is stored

The manifest declares the edition; the credential lives encrypted in
`credentials.sops.yaml` next to `project.yaml`:

```yaml
name: client-x
odoo_version: "19.0"
edition: enterprise
```

The file is encrypted with [SOPS](https://github.com/getsops/sops) using an
[age](https://github.com/FiloSottile/age) key. It is safe to commit: only
holders of a matching age private key can decrypt it.

## Check your machine

```bash
uv run forge doctor
```

`doctor` verifies the two local prerequisites: a usable age private key
(conventionally `~/.config/sops/age/keys.txt`) and the conventional SOPS
entry for the Enterprise source credential. Both checks green means
`lock`/`project`/`run` can decrypt on this machine.

If `doctor` fails, the fix is one of:

- no age key → generate one (`age-keygen -o ~/.config/sops/age/keys.txt`)
  and ask a current keyholder to re-encrypt the file for your public key;
- `sops` not on `PATH` → install it; odoo-forge shells out to it directly.

## Rotate keys

When someone leaves the project, or a key may have leaked:

```bash
uv run forge rotate-enterprise-credential --manifest project.yaml
```

This wraps `sops updatekeys`: it rewrites only `credentials.sops.yaml` for
the current recipient set — no other state is touched. Update the recipient
list in your SOPS config first, then rotate.

## Where the secret is allowed to go

By design, the decrypted credential is injected into the spawned Git
subprocess and nowhere else. It must never appear in logs, process listings,
or error messages — the adapters treat that as a contract, and
[SECURITY.md](../../SECURITY.md) treats violations of it as reportable
vulnerabilities.

For the full local setup narrative, see the
[example runtime guide](../22-example-runtime-guide.md).
