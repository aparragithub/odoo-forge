# Security Policy

## Supported versions

odoo-forge is pre-1.0. Only the latest commit on `main` receives security fixes.

| Version | Supported |
| --- | --- |
| `main` | ✅ |
| anything else | ❌ |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use [GitHub private vulnerability reporting](https://github.com/aparragithub/odoo-forge/security/advisories/new) instead. Reports are acknowledged within a week.

Areas of particular interest:

- Credential injection into spawned subprocesses (Git, Docker, PostgreSQL, GHCR)
- SOPS/age credential materialization and rotation
- Masking of database dumps
- Anything that could leak a secret into logs, process listings, or error messages

## Scope

This policy covers the code in this repository only. Vulnerabilities in Odoo itself should be reported to [Odoo's security team](https://www.odoo.com/security-report).
