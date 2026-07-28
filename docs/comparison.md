# How odoo-forge compares

If you deploy Odoo today, you almost certainly use one of three approaches:
[doodba](https://github.com/Tecnativa/doodba), a hand-maintained
`docker-compose` setup, or [Odoo.sh](https://www.odoo.sh). This page states
plainly what each one solves, where odoo-forge overlaps, and — first — when
you should **not** use odoo-forge.

A disclaimer before any table: doodba and Odoo.sh are production-proven at
scale, over years. odoo-forge is weeks old, maintained by one person, and not
yet on PyPI. What follows compares *designs*, not track records — on track
record, the incumbents win today, full stop.

## When NOT to use odoo-forge

- **You need production-proven tooling now.** Use doodba or Odoo.sh. Come
  back when odoo-forge has releases and adopters.
- **You want managed hosting with staging-from-production, backups and
  monitoring done for you.** That is Odoo.sh's product, and it is good at it.
- **You run one instance and rarely touch it.** A plain `docker-compose.yml`
  is less machinery than a manifest, a lock and a CLI. Simplicity wins.
- **Your workflow is deeply invested in the OCA/doodba toolchain**
  (git-aggregator, click-odoo, the copier template). odoo-forge does not
  integrate with those tools today.

## The three incumbents

### doodba

Doodba is a Docker base image plus a copier template: your project builds an
image *containing* your Odoo and addons, with `repos.yaml` (git-aggregator)
and `addons.yaml` declaring what goes in. It standardizes **image
construction** and project layout, and it does that very well, backed by the
OCA ecosystem.

What it deliberately does not manage: deployment orchestration and runtime
lifecycle. The compose files, environments, and version pinning across
projects remain yours to maintain.

### Hand-rolled docker-compose

Full control, zero abstraction, nothing new to learn. The cost appears at
project two: every deployment is a ritual of cloned repos, an `addons_path`
kept by hand, and version pinning that lives in someone's memory. There is no
locking, no drift detection, and no way to treat "the project" as one
reviewable artifact.

### Odoo.sh

Odoo's own PaaS: GitHub integration, staging branches built from production
data, daily backups, managed servers. It requires an Odoo Enterprise
subscription, and the infrastructure is theirs — you operate inside their
platform, not on your own targets.

## What odoo-forge does differently

odoo-forge treats the **project definition as data**: a `project.yaml`
declaring layers, versions, overrides and runtime, resolved into a
`project.lock` that pins every Git ref to an exact commit. From that locked
state it materializes a workspace and provisions a backend — today local
Docker; remote targets are the declared direction, behind ports, as adapters.

| | odoo-forge | doodba | hand compose | Odoo.sh |
| --- | --- | --- | --- | --- |
| Project defined as | declarative manifest + lock | image + YAML addon specs | compose file + habits | Git branches in their platform |
| Exact-commit locking / drift detection | ✅ built in | ➖ refs in `repos.yaml`, no lock/drift step | ❌ manual | ➖ platform-managed |
| Runs without a container image per project | ✅ workspace mounted into a base image | ❌ image build per project | varies | n/a |
| Deployment / runtime lifecycle | ✅ backend providers (local Docker today) | ❌ out of scope | manual | ✅ fully managed |
| Self-hosted | ✅ | ✅ | ✅ | ❌ |
| Works with Odoo Community | ✅ | ✅ | ✅ | ❌ Enterprise subscription required |
| Ecosystem & maturity | ⚠️ early stage | ✅ years, OCA-backed | — | ✅ vendor-backed |
| License | Apache-2.0 | Apache-2.0 | — | proprietary SaaS |

The honest one-line summary: **doodba standardizes how an Odoo image is
built; odoo-forge standardizes what an Odoo project *is*** — and leaves the
image as one replaceable piece. Odoo.sh sells the operated outcome; odoo-forge
aims at the same workflow layer (managed data environments, staging-like
flows) as self-hosted open source, and is explicit that most of that layer is
[still roadmap](../ROADMAP.md).

## Migration cost, both directions

Adopting odoo-forge from compose or doodba means writing a `project.yaml` —
your repos, refs and addon paths, which you already know. Leaving odoo-forge
is equally unceremonious: the materialized workspace is plain Git checkouts on
disk; nothing is trapped in a proprietary format.

*Corrections welcome — if this page misrepresents a tool you know well,
[open an issue](https://github.com/aparragithub/odoo-forge/issues).*
