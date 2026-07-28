# odoo-forge

[![Licencia](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Arquitectura](https://img.shields.io/badge/architecture-hexagonal-informational.svg)](#arquitectura)

**Plataforma declarativa para componer proyectos Odoo: manifests por capas, overrides resueltos y backends de ejecución desacoplados.**

[English](README.md) · [Documentación](docs/00-master-index.md) · [Roadmap](ROADMAP.md)

---

## El problema

Un proyecto Odoo se arma normalmente a mano: un layout fijo de repositorios clonados, un `addons_path` mantenido manualmente, un `docker-compose.yml` a medida y un pinneo de versiones que vive en la memoria de alguien. Reproducir un despliegue significa reproducir un ritual.

odoo-forge modela el proyecto como **datos**. Capas, versiones, overrides, credenciales y runtime pasan a ser una definición declarativa — un `project.yaml` resuelto en un `project.lock` — que se puede validar, fijar a commits exactos, materializar en disco y provisionar contra el backend elegido.

El core de dominio se mantiene libre de infraestructura. Git, Docker, PostgreSQL, el registry de imágenes y los pipelines de CI viven detrás de puertos, así que una nueva superficie de ejecución es un adapter nuevo, nunca una reescritura.

## Estado

Es un **proyecto en etapa temprana y desarrollo activo** (primer commit en julio de 2026, un solo maintainer). Sobre sus límites es explícito.

**Operativo hoy**

- Manejo de `project.yaml` / `project.lock`, con detección de drift
- Resolución efectiva de capas y overrides
- Materialización de workspace respaldada por Git
- Planning de backend a partir del estado materializado
- Backend local Odoo + PostgreSQL sobre Docker
- Adapter aislado `DatabaseProvider` para PostgreSQL en Docker
- Operaciones de imágenes en GHCR (resolve, publish, pull, exists)
- Image factory para imágenes base
- Manejo de credenciales Enterprise respaldado por SOPS/age

**Foundations neutrales al provider, todavía no conectadas a un flujo administrado**

Credenciales, artefactos de datos, catálogo de proyectos y operaciones durables existen como piezas neutrales. Están implementadas, pero aún no expuestas como workflows administrados de data environments.

**Estado objetivo**

Data environments administrados, tenancy, control plane, RBAC, backends remotos (EC2, Kubernetes, Fargate) y UI web.

La fuente estructural y canónica para estado de producto, dependencias, evidencia y handoffs es [`docs/specs/platform/portfolio.json`](docs/specs/platform/portfolio.json). La prosa de este README es un resumen; el portfolio es autoritativo.

## Inicio rápido

![forge validate, project y run levantando un stack local de Odoo](docs/assets/quickstart.gif)

Requiere Python 3.11+, [uv](https://docs.astral.sh/uv/) y un daemon de Docker activo para los comandos de backend.

```bash
git clone https://github.com/aparragithub/odoo-forge.git
cd odoo-forge
uv sync
uv run forge --help
```

Todavía no está publicado en PyPI — se instala desde el código fuente.

Un manifest mínimo se ve así:

```yaml
name: forge-min
odoo_version: "19.0"
edition: community
core:
  type: core
  url: https://github.com/odoo/odoo.git
  ref: "19.0"
client:
  addons_path: client/addons
workspace:
  checkout_timeout_seconds: 300
backend:
  odoo:
    bind_host: 0.0.0.0
    http_port: 18069
```

Validarlo, fijar cada ref declarada a un commit SHA, proyectarlo en el filesystem y levantar el stack:

```bash
uv run forge validate --manifest example/project.yaml
uv run forge lock     --manifest example/project.yaml
uv run forge project  --manifest example/project.yaml
uv run forge run      --manifest example/project.yaml
uv run forge status
```

En [`example/`](example/) hay un manifest completo y funcional.

## CLI

| Familia | Comandos |
| --- | --- |
| Manifest | `validate`, `lock`, `project`, `unlock`, `onboard` |
| Backend local | `run`, `status`, `stop`, `destroy`, `logs` |
| Imágenes (GHCR) | `image-resolve`, `image-publish`, `image-pull`, `image-exists` |
| Pipelines | `pipeline-trigger`, `pipeline-status` |
| Mantenimiento | `doctor`, `rotate-enterprise-credential` |

Para la firma completa de cualquier comando: `uv run forge <comando> --help`.

## Arquitectura

Hexagonal, y verificada en lugar de declarativa: **9 contratos de import-linter rompen el build** si el core de dominio toca infraestructura, la CLI o cualquier adapter.

| Paquete | Rol |
| --- | --- |
| `odoo_forge` | Dominio puro — modelos Pydantic, composición de manifests, puertos |
| `odoo_forge_cli` | Capa de presentación Typer (`forge`) |
| `odoo_forge_git` | Provider de fuentes Git |
| `odoo_forge_workspace` | Materialización de workspace |
| `odoo_forge_docker` | Backend local Docker |
| `odoo_forge_postgres_docker` | Adapter de base de datos PostgreSQL sobre Docker |
| `odoo_forge_registry` | Adapter de registry de imágenes GHCR |
| `odoo_forge_catalog` | Adapter de índice del catálogo de proyectos |
| `odoo_forge_pipeline_github` | Adapter de pipelines GitHub Actions |

Los adapters dependen del core. El core no depende de nada más que de sus propios puertos.

## Desarrollo

```bash
uv sync
uv run pytest                     # tests unitarios (integración deseleccionada por defecto)
uv run pytest -m integration      # tests de backend con daemon real
uv run pytest -m real_docker      # tests de aceptación PostgreSQL en Docker
uv run ruff check .
uv run mypy src
uv run lint-imports               # contratos de arquitectura
```

## Documentación

| Punto de entrada | Qué cubre |
| --- | --- |
| [`ROADMAP.md`](ROADMAP.md) | Qué funciona hoy, qué está construido sin conectar, y qué viene después |
| [`docs/comparison.md`](docs/comparison.md) | Cómo se compara odoo-forge con doodba, compose a mano y Odoo.sh — incluyendo cuándo no usarlo |
| [`docs/recipes/`](docs/recipes/README.md) | Guías por tarea: agregar una capa de addons, override con tu fork, credenciales Enterprise |
| [`docs/00-master-index.md`](docs/00-master-index.md) | Índice de toda la documentación de mantenimiento |
| [`docs/diagrams/odoo-forge-current-implementation-guide.md`](docs/diagrams/odoo-forge-current-implementation-guide.md) | El límite exacto de lo implementado hoy |
| [`docs/01-repository-map.md`](docs/01-repository-map.md) | Estructura del repositorio |
| [`docs/06-docs-and-openspec-lifecycle.md`](docs/06-docs-and-openspec-lifecycle.md) | Cómo se mantienen sincronizados docs y specs |

## Specs y roadmap

El desarrollo es spec-driven. Las especificaciones viven en [`openspec/specs/`](openspec/specs/) como baseline acumulada; los changes pasan por `openspec/changes/` y quedan en `openspec/changes/archive/` al completarse.

- **No hay ningún change activo.** `openspec/changes/` contiene solo el archivo histórico.
- Hay 46 changes completados en [`openspec/changes/archive/`](openspec/changes/archive/), incluido `2026-07-17-sp-data-environments`.
- [`docs/specs/2026-07-14-stabilization-roadmap.md`](docs/specs/2026-07-14-stabilization-roadmap.md) es contexto histórico de estabilización — una secuencia, no un inventario autoritativo de trabajo activo.

## Dirección

1. **Fundación operativa** — image factory, CLI core, materialización de workspace, backend local Docker, adapter PostgreSQL, adapter GHCR. *Implementado.*
2. **Foundations neutrales al provider** — credenciales, artefactos de datos, `DatabaseProvider`, catálogo de proyectos, operaciones durables. *Implementadas, todavía separadas de flujos administrados.*
3. **Workflows de plataforma** — data environments administrados, tenancy, control plane, gobernanza, journeys por actor. *Bloqueados, planificados o ausentes según `portfolio.json`.*
4. **Superficies remotas e interfaces** — EC2, Kubernetes, Fargate, RBAC, UI web. *Estado objetivo.*

## Contribuir

Issues y pull requests son bienvenidos — empezá por [CONTRIBUTING.md](CONTRIBUTING.md) y la etiqueta [`good-first-issue`](https://github.com/aparragithub/odoo-forge/issues?q=is%3Aissue+is%3Aopen+label%3Agood-first-issue). Todo cambio entra por pull request atado a un issue abierto; nada se pushea directo a `main`.

## Licencia

[Apache License 2.0](LICENSE) — Copyright 2026 Angel Parra.
