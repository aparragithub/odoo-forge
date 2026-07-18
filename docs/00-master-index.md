# Índice Maestro De Documentación

## Qué es este documento

Es el punto de entrada estable para la documentación de mantenimiento de `odoo-forge`. Ordena la serie numerada `00` a `21`, resume qué cubre cada documento y te dice por dónde entrar según el tipo de cambio que querés hacer.

## Por qué importa

Importa porque este repositorio mezcla código, guías operativas, diagramas, roadmaps fechados, portfolio estructural y evidencia histórica de OpenSpec. Sin una puerta de entrada clara, es fácil leer demasiado, editar la fuente equivocada o tomar como activa una referencia que ya quedó archivada.

## Por qué existe

Existe para que maintainers no tengan que reconstruir mentalmente el mapa documental cada vez que vuelven al repo. También existe para separar con claridad la guía vigente de la historia preservada.

## Cómo ayuda al sistema

Ayuda al sistema porque reduce cambios incorrectos, mejora la trazabilidad entre docs, código y OpenSpec, y mantiene alineada la navegación humana con la verdad estructural del repositorio: `docs/specs/platform/portfolio.json` para estado/capacidades/evidencia y el árbol vivo de `openspec/changes/` para trabajo activo.

## Estado Rápido

- La fuente estructural de verdad para estado, dependencias y evidencia es [`docs/specs/platform/portfolio.json`](specs/platform/portfolio.json).
- El árbol vivo de `openspec/changes/` tiene solo un change activo: [`sp-data-environments`](../openspec/changes/sp-data-environments/proposal.md).
- `refresh-platform-roadmap-after-stabilization` y `fix-roadmap-refresh-verification-closure` son historia archivada bajo `openspec/changes/archive/`.
- La serie vigente para maintainers corre desde este documento `00` hasta [`21-src-postgres-docker-foundation-map.md`](21-src-postgres-docker-foundation-map.md).

## Estrategia De Lectura

### Recorrido secuencial

Usá esta ruta si necesitás reconstruir el repo completo con el menor riesgo de perder contexto:

1. `00` índice maestro.
2. `01` mapa global del repositorio.
3. `02` matriz de autoridad.
4. `03` a `06` para arquitectura, adapters, tests y lifecycle documental/OpenSpec.
5. `07` a `10` para cruces entre specs, portfolio, diagramas y trabajo activo.
6. `11` a `21` para mapas focalizados por subdirectorio o superficie concreta.

### Recorridos temáticos

| Si querés entender... | Leé primero | Después seguí con |
| --- | --- | --- |
| El mapa completo del repo | [`01-repository-map.md`](01-repository-map.md) | [`02-repository-authority-matrix.md`](02-repository-authority-matrix.md), [`03-src-core-map.md`](03-src-core-map.md) |
| Qué documento o artifact manda | [`02-repository-authority-matrix.md`](02-repository-authority-matrix.md) | [`06-docs-and-openspec-lifecycle.md`](06-docs-and-openspec-lifecycle.md), [`09-portfolio-and-evidence-crosswalk.md`](09-portfolio-and-evidence-crosswalk.md) |
| El core y sus límites | [`03-src-core-map.md`](03-src-core-map.md) | [`11-src-manifest-map.md`](11-src-manifest-map.md), [`12-src-backend-map.md`](12-src-backend-map.md), [`13-src-ports-map.md`](13-src-ports-map.md) |
| CLI y adapters | [`04-cli-and-adapters-map.md`](04-cli-and-adapters-map.md) | [`17-src-docker-adapter-map.md`](17-src-docker-adapter-map.md), [`18-src-workspace-adapter-map.md`](18-src-workspace-adapter-map.md), [`19-src-registry-adapter-map.md`](19-src-registry-adapter-map.md), [`20-src-cli-composition-root-map.md`](20-src-cli-composition-root-map.md), [`21-src-postgres-docker-foundation-map.md`](21-src-postgres-docker-foundation-map.md) |
| Tests y quality gates | [`05-tests-and-quality-map.md`](05-tests-and-quality-map.md) | [`14-tests-manifest-map.md`](14-tests-manifest-map.md), [`15-tests-adapters-map.md`](15-tests-adapters-map.md), [`16-tests-cli-map.md`](16-tests-cli-map.md) |
| Specs, portfolio y OpenSpec | [`06-docs-and-openspec-lifecycle.md`](06-docs-and-openspec-lifecycle.md) | [`07-spec-to-module-crosswalk.md`](07-spec-to-module-crosswalk.md), [`08-sp-data-environments-map.md`](08-sp-data-environments-map.md), [`09-portfolio-and-evidence-crosswalk.md`](09-portfolio-and-evidence-crosswalk.md) |
| Diagramas y su mantenimiento | [`10-diagrams-maintenance-guide.md`](10-diagrams-maintenance-guide.md) | [`diagrams/README.md`](diagrams/README.md), [`diagrams/odoo-forge-current-implementation-guide.md`](diagrams/odoo-forge-current-implementation-guide.md) |

### Dónde empezar si querés tocar X

| Si querés tocar... | Empezá acá | Confirmá después en |
| --- | --- | --- |
| `README.md` o la narrativa visible del proyecto | [`01-repository-map.md`](01-repository-map.md) | [`09-portfolio-and-evidence-crosswalk.md`](09-portfolio-and-evidence-crosswalk.md), `docs/specs/platform/portfolio.json` |
| Estado de producto, dependencias o evidencia | `docs/specs/platform/portfolio.json` | [`09-portfolio-and-evidence-crosswalk.md`](09-portfolio-and-evidence-crosswalk.md) |
| Un change OpenSpec activo | [`06-docs-and-openspec-lifecycle.md`](06-docs-and-openspec-lifecycle.md) | [`08-sp-data-environments-map.md`](08-sp-data-environments-map.md) |
| Core de manifest | [`11-src-manifest-map.md`](11-src-manifest-map.md) | [`07-spec-to-module-crosswalk.md`](07-spec-to-module-crosswalk.md), `tests/manifest/` |
| Planning/backend local | [`12-src-backend-map.md`](12-src-backend-map.md) | [`17-src-docker-adapter-map.md`](17-src-docker-adapter-map.md), `tests/backend/` |
| Contratos/ports | [`13-src-ports-map.md`](13-src-ports-map.md) | [`04-cli-and-adapters-map.md`](04-cli-and-adapters-map.md), `tests/ports/` |
| CLI | [`20-src-cli-composition-root-map.md`](20-src-cli-composition-root-map.md) | [`16-tests-cli-map.md`](16-tests-cli-map.md), [`04-cli-and-adapters-map.md`](04-cli-and-adapters-map.md) |
| Diagramas | [`10-diagrams-maintenance-guide.md`](10-diagrams-maintenance-guide.md) | [`diagrams/README.md`](diagrams/README.md) |
| Un roadmap o doc histórico | [`06-docs-and-openspec-lifecycle.md`](06-docs-and-openspec-lifecycle.md) | `docs/specs/platform/portfolio.json` y el árbol vivo de `openspec/changes/` |

## Serie `01` A `21`

| Nro | Documento | Para qué sirve |
| --- | --- | --- |
| `01` | [`01-repository-map.md`](01-repository-map.md) | Mapa global del repo y de sus superficies activas, derivadas e históricas. |
| `02` | [`02-repository-authority-matrix.md`](02-repository-authority-matrix.md) | Determina qué artifact manda antes de editar. |
| `03` | [`03-src-core-map.md`](03-src-core-map.md) | Explica el core puro en `src/odoo_forge/`. |
| `04` | [`04-cli-and-adapters-map.md`](04-cli-and-adapters-map.md) | Resume CLI, adapters y fronteras hexagonales. |
| `05` | [`05-tests-and-quality-map.md`](05-tests-and-quality-map.md) | Mapa de tests, gates y validación. |
| `06` | [`06-docs-and-openspec-lifecycle.md`](06-docs-and-openspec-lifecycle.md) | Distingue guía actual, verdad aceptada, trabajo activo e historia preservada. |
| `07` | [`07-spec-to-module-crosswalk.md`](07-spec-to-module-crosswalk.md) | Cruza specs aceptadas con módulos y tests. |
| `08` | [`08-sp-data-environments-map.md`](08-sp-data-environments-map.md) | Explica el único change OpenSpec activo del árbol vivo. |
| `09` | [`09-portfolio-and-evidence-crosswalk.md`](09-portfolio-and-evidence-crosswalk.md) | Relaciona `portfolio.json` con evidencia, history y claims actuales. |
| `10` | [`10-diagrams-maintenance-guide.md`](10-diagrams-maintenance-guide.md) | Regla de mantenimiento y render de diagramas. |
| `11` | [`11-src-manifest-map.md`](11-src-manifest-map.md) | Detalle de `src/odoo_forge/manifest/`. |
| `12` | [`12-src-backend-map.md`](12-src-backend-map.md) | Detalle de `src/odoo_forge/backend/`. |
| `13` | [`13-src-ports-map.md`](13-src-ports-map.md) | Detalle de `src/odoo_forge/ports/`. |
| `14` | [`14-tests-manifest-map.md`](14-tests-manifest-map.md) | Cobertura y organización de `tests/manifest/`. |
| `15` | [`15-tests-adapters-map.md`](15-tests-adapters-map.md) | Cobertura y organización de `tests/adapters/`. |
| `16` | [`16-tests-cli-map.md`](16-tests-cli-map.md) | Cobertura y organización de `tests/cli/`. |
| `17` | [`17-src-docker-adapter-map.md`](17-src-docker-adapter-map.md) | Mapa del adapter Docker local. |
| `18` | [`18-src-workspace-adapter-map.md`](18-src-workspace-adapter-map.md) | Mapa del adapter de materialización de workspace. |
| `19` | [`19-src-registry-adapter-map.md`](19-src-registry-adapter-map.md) | Mapa del adapter de registry/GHCR. |
| `20` | [`20-src-cli-composition-root-map.md`](20-src-cli-composition-root-map.md) | Mapa del composition root Typer. |
| `21` | [`21-src-postgres-docker-foundation-map.md`](21-src-postgres-docker-foundation-map.md) | Mapa de la foundation PostgreSQL sobre Docker. |

## Regla De Navegación Segura

Si una afirmación habla de estado actual, dependencias, evidencia o handoffs, corroborala con `docs/specs/platform/portfolio.json`. Si habla de trabajo OpenSpec activo, corroborala con `openspec/changes/`. Si el archivo está bajo `openspec/changes/archive/` o es una roadmap fechada vieja, tratala como historia preservada.
