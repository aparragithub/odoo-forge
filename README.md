# odoo-forge

Plataforma modular para Odoo: proyectos por capas, manifests declarativos y backends de ejecución desacoplados.

Un proyecto Odoo no se modela como un layout fijo de repositorios, sino como una definición declarativa de capas, versiones, overrides y runtime. La intención del sistema es mantener separado el core de dominio de los adapters concretos para Git, Docker, registry, filesystem y futuras superficies de plataforma.

## Estado actual

La implementación operativa actual incluye:

- manejo de `project.yaml` y `project.lock`;
- resolución efectiva de capas y overrides;
- materialización de workspace respaldada por Git;
- planning de backend a partir de estado materializado;
- backend local Odoo/PostgreSQL sobre Docker;
- adapter aislado `DatabaseProvider` para PostgreSQL en Docker;
- operaciones de imágenes en GHCR;
- image factory para imágenes base.

También existen foundations neutrales al provider para credenciales, artefactos de datos, catálogo de proyectos y operaciones durables. Esas piezas todavía no están conectadas a un flujo operativo administrado de data environments.

Tenancy, control plane, backends remotos, RBAC y UI web siguen siendo estado objetivo. La fuente estructural y canónica para estado de producto, dependencias, evidencia y handoffs es [`docs/specs/platform/portfolio.json`](docs/specs/platform/portfolio.json).

## Por dónde entrar

- Si querés navegar la documentación de mantenimiento, empezá en [`docs/00-master-index.md`](docs/00-master-index.md).
- Si querés entender el límite de lo implementado hoy, seguí con [`docs/diagrams/odoo-forge-current-implementation-guide.md`](docs/diagrams/odoo-forge-current-implementation-guide.md).
- Si querés entender la estructura del repositorio, seguí con [`docs/01-repository-map.md`](docs/01-repository-map.md).

## Verdad actual sobre roadmap y OpenSpec

- El árbol vivo de `openspec/changes/` tiene solo un change activo: [`sp-data-environments`](openspec/changes/sp-data-environments/proposal.md).
- `refresh-platform-roadmap-after-stabilization` ya no es trabajo activo: quedó archivado en `openspec/changes/archive/2026-07-17-refresh-platform-roadmap-after-stabilization/`.
- `fix-roadmap-refresh-verification-closure` también es historia archivada, no trabajo vivo.
- La roadmap fechada [`docs/specs/2026-07-14-stabilization-roadmap.md`](docs/specs/2026-07-14-stabilization-roadmap.md) debe leerse como secuencia y contexto histórico de estabilización, no como inventario autoritativo de changes activos.

## Resumen de dirección

1. Fundación operativa: image factory, CLI core, materialización de workspace, backend local Docker, adapter PostgreSQL en Docker y adapter GHCR. Implementado.
2. Foundations neutrales al provider: credenciales, artefactos de datos, `DatabaseProvider`, catálogo de proyectos y operaciones durables. Implementadas, pero todavía separadas de flujos administrados.
3. Workflows de plataforma: data environments administrados, tenancy, control plane, gobernanza y journeys por actor. Bloqueados, planificados o ausentes según `portfolio.json`.
4. Superficies remotas e interfaces: EC2, Kubernetes, Fargate, RBAC y UI web. Estado objetivo.
