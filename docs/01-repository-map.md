# Mapa Del Repositorio

## Qué es este documento

Es el mapa principal de `odoo-forge`: resume la estructura del repositorio, sus capas técnicas, qué vive en cada directorio y qué superficies son activas, derivadas o históricas.

## Por qué importa

Importa porque evita cambios en el lugar equivocado, ayuda a distinguir código, documentación, validadores y evidencia histórica, y reduce el riesgo de romper límites de arquitectura o de gobernanza.

## Por qué existe

Existe para dar un punto de entrada único a maintainers y futuras personas implementadoras antes de tocar `src/`, `tests/`, `docs/`, `factory/` u OpenSpec.

## Cómo ayuda al sistema

Ayuda al sistema porque conecta la vista global del repo con el índice maestro `00` y con los documentos especializados `02` a `21`, de modo que cada cambio pueda empezar en la fuente correcta y continuar con trazabilidad.

## Leer Antes De...

Si todavía no venís del índice maestro, leé primero [`00-master-index.md`](00-master-index.md). Ese documento resume toda la serie `00` a `21` y te dice por dónde entrar según el tipo de cambio.

## Leer Después De...

Empezá acá para orientarte en todo el repo. Siguiente lectura: [02-repository-authority-matrix.md](02-repository-authority-matrix.md), luego [03-src-core-map.md](03-src-core-map.md), [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md), [05-tests-and-quality-map.md](05-tests-and-quality-map.md), [06-docs-and-openspec-lifecycle.md](06-docs-and-openspec-lifecycle.md), [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md), [08-sp-data-environments-map.md](08-sp-data-environments-map.md), [09-portfolio-and-evidence-crosswalk.md](09-portfolio-and-evidence-crosswalk.md), [10-diagrams-maintenance-guide.md](10-diagrams-maintenance-guide.md) y después los mapas focalizados [11](11-src-manifest-map.md) a [21](21-src-postgres-docker-foundation-map.md) según el área que vayas a tocar.

## Ruta Rápida

1. Empezá en [`README.md`](../README.md) para la promesa del producto y el estado actual visible para usuarios.
2. Usá este documento para decidir qué directorio es dueño del cambio que querés hacer.
3. Confirmá la autoridad en la [Matriz De Autoridad Del Repositorio](02-repository-authority-matrix.md) antes de editar artifacts de roadmap, diagramas u OpenSpec.
4. Si necesitás un recorrido temático o un punto de entrada por superficie, volvé al [`00-master-index.md`](00-master-index.md).

## Para Qué Sirve Este Repositorio

Desde el punto de vista de una persona usuaria, `odoo-forge` es el toolchain para:

| Necesidad del usuario | Capacidad del repositorio |
| --- | --- |
| Describir un proyecto Odoo sin curar a mano la estructura del repo | Flujo declarativo de manifest y lockfile |
| Materializar localmente fuentes de proyecto por capas | Proyección de workspace respaldada por Git |
| Ejecutar Odoo localmente con inputs reproducibles de runtime | Backend local sobre Docker |
| Trabajar con imágenes de contenedor publicadas | Adapter de image registry orientado a GHCR |
| Preparar futuros flujos de plataforma administrada | Contratos core neutrales al provider y foundations |

Hoy el runtime distribuido está orientado a desarrollo local. Existen varias foundations neutrales al provider, pero managed data environments, orchestración de control plane, remote backends, RBAC y web UI siguen siendo trabajo de estado objetivo.

## Mapa De Arquitectura De Alto Nivel

| Capa | Ubicación principal | Responsabilidad |
| --- | --- | --- |
| Core de dominio | `src/odoo_forge/` | Tipos de dominio puros, validación, planning y contratos de ports |
| Composition root | `src/odoo_forge_cli/` | Entrypoint Typer CLI que conecta commands con servicios core y adapters |
| Runtime adapters | `src/odoo_forge_git/`, `src/odoo_forge_workspace/`, `src/odoo_forge_docker/`, `src/odoo_forge_registry/` | Integraciones concretas para Git, materialización de workspace en filesystem, runtime local sobre Docker y operaciones de imágenes sobre GHCR |
| Foundation de database adapter | `src/odoo_forge_postgres_docker/` | Implementación aislada de `DatabaseProvider` para PostgreSQL en Docker; foundation importante, no la ruta principal de ejecución de la CLI |
| Tests y quality gates | `tests/`, `pyproject.toml`, `.github/workflows/` | Verificación de comportamiento, enforcement de límites de imports, lint, typing y workflows de CI |
| Docs de producto y gobernanza | `docs/`, `openspec/` | Guías actuales, diagramas, autoridad de portfolio, specs aceptadas y evidencia histórica de cambios |
| Image factory | `factory/` | Pipeline de build de imágenes base y smoke tests para imágenes publicadas de Odoo CE |

## Mapa De Directorios

### Nivel superior

| Path | Propósito | Nota para maintainers |
| --- | --- | --- |
| `src/` | Código de aplicación | Fuente canónica de runtime |
| `tests/` | Suites de tests Python | Organizadas por concern de dominio/runtime |
| `docs/` | Docs para maintainers y de cara al producto | Autoridad mixta; verificá la matriz antes de editar |
| `openspec/` | Artifacts de entrega guiada por specs | `specs/` es comportamiento aceptado canónico; `changes/` es evidencia de workflow activa o archivada |
| `factory/` | Sistema de build de imágenes de contenedor | Separado de la runtime CLI, pero importante operativamente |
| `.github/workflows/` | CI y automatización | El workflow de quality usa path filters; los workflows de imágenes son independientes |
| `pyproject.toml` | Autoridad de packaging y quality tools | Config central para pytest, coverage, Ruff, mypy e import-linter |
| `uv.lock` | Lockfile de dependencias Python | Resolución derivada de paquetes |

### `src/`

| Path | Rol | Límite de interacción |
| --- | --- | --- |
| `src/odoo_forge/` | Core/dominio puro | Debe permanecer libre de imports de CLI/framework/infraestructura; import-linter lo hace cumplir |
| `src/odoo_forge_cli/` | Composition root Typer | Llama al core y selecciona adapters concretos |
| `src/odoo_forge_git/` | Source adapter | Implementa concerns de obtención de fuentes usando Git |
| `src/odoo_forge_workspace/` | Workspace adapter | Materializa en el filesystem el estado planeado del workspace |
| `src/odoo_forge_docker/` | Backend adapter | Ejecuta workloads locales de Odoo/PostgreSQL mediante Docker |
| `src/odoo_forge_registry/` | Registry adapter | Resuelve, publica, verifica y descarga imágenes vía tooling GHCR/Docker |
| `src/odoo_forge_postgres_docker/` | Foundation de database-provider adapter | Es dueña de la lógica aislada de ciclo de vida PostgreSQL; todavía no es el flujo canónico del runtime local |

Dentro de `src/odoo_forge/`, los subdominios principales son `manifest/`, `backend/`, `ports/`, `image_registry/`, `database/`, `credentials/`, `data_artifacts/`, `project_catalog/` y `durable_operations/`.

### `tests/`

| Path | Qué prueba |
| --- | --- |
| `tests/manifest/` | Schema declarativo del proyecto, lockfile, composición, proyección y drift |
| `tests/backend/` | Planning core del backend, status y errores |
| `tests/ports/` | Expectativas de contratos de ports |
| `tests/adapters/` | Comportamiento de adapters, incluyendo tests de Docker/Git/registry/database adapters |
| `tests/cli/` | Comportamiento y wiring de commands CLI |
| `tests/database/` | Tipos de dominio neutrales al provider y reglas de readiness |
| `tests/credentials/`, `tests/data_artifacts/`, `tests/project_catalog/`, `tests/durable_operations/` | Foundations neutrales todavía no totalmente cableadas a workflows administrados |
| `tests/factory/` | Checks de comportamiento de la image factory |
| `tests/fixtures/` | Inputs compartidos para tests |

### `docs/`

| Path | Qué contiene | Nivel de autoridad |
| --- | --- | --- |
| `docs/diagrams/` | Visuales de arquitectura actual/objetivo y contrato de render | Mixto: las fuentes Mermaid son canónicas para sus diagramas; SVG es derivado |
| `docs/specs/` | Roadmaps, docs de diseño fechados y narrativas de plataforma | Mixto: guía actual más referencias históricas preservadas |
| `docs/specs/platform/portfolio.json` | Portfolio de estado de producto, dependencias y evidencia | Fuente estructural canónica de verdad para el estado del portfolio |
| `docs/tools/platform_portfolio/` | Validator determinista para integridad de portfolio/documentación | Tool de validación canónico, no solo prosa de apoyo |
| `docs/reviews/` | Artifacts de revisión y auditoría | Histórico / orientado a revisión |
| `docs/superpowers/` | Artifacts anteriores de diseño/planning | Histórico / de apoyo |

### `openspec/`

| Path | Qué significa |
| --- | --- |
| `openspec/specs/` | Specs canónicas aceptadas que describen comportamiento distribuido o aceptado |
| `openspec/changes/` | Trabajo de cambio vivo únicamente |
| `openspec/changes/sp-data-environments/` | Directorio de cambio activo actual en el árbol vivo |
| `openspec/changes/archive/` | Cambios históricos inmutables, incluyendo historia de roadmap-refresh y corrective-closure |
| `openspec/config.yaml` | Convenciones de workflow y verificación OpenSpec para este repo |

### `factory/`

| Path | Propósito |
| --- | --- |
| `factory/Dockerfile`, `factory/build.sh`, `factory/versions.yaml` | Inputs canónicos para build de imágenes base |
| `factory/smoke-test.sh` | Verificación smoke como gate de publicación de imágenes construidas |
| `factory/tests/` | Cobertura de tests shell específica de factory |
| `factory/README.md` | Guía de uso local de factory |

## Canónico Vs Derivado Vs Histórico

Aplicá esta regla antes de editar: cambiá la fuente de mayor autoridad que realmente sea dueña del hecho y después regenerá o alineá todo lo derivado.

| Categoría | Ejemplos | ¿Editar directo? |
| --- | --- | --- |
| Fuente canónica de runtime | `src/**`, `tests/**`, `pyproject.toml` | Sí |
| Fuente canónica de producto/estado | `docs/specs/platform/portfolio.json`, `openspec/specs/**`, archivos activos de OpenSpec changes | Sí |
| Fuente canónica de diagramas | `docs/diagrams/*.mmd` y el script/config de render que define la salida | Sí |
| Artifacts derivados | `docs/diagrams/*.svg`, build outputs, caches, wheels | Solo vía su generador/renderizador |
| Evidencia histórica | `openspec/changes/archive/**`, artifacts de revisión fechados, roadmaps/docs de diseño viejos preservados | No; agregá guía nueva en otro lado |
| Guía transicional con solapamiento histórico | `README.md`, `docs/specs/*.md`, guía actual de implementación | Sí, pero verificá primero contra fuentes canónicas |

Matiz importante actual: el árbol vivo contiene solo `openspec/changes/sp-data-environments/` como cambio activo. Algunos documentos narrativos todavía mencionan `refresh-platform-roadmap-after-stabilization` como activo, pero sus bytes ahora viven bajo `openspec/changes/archive/`. Tratá esas menciones como guía histórica o desactualizada salvo que estén corroboradas por el árbol vivo y `portfolio.json`.

## Flujo De Interacción Del Runtime

La ruta de runtime es intencionalmente hexagonal.

1. Una persona usuaria ejecuta `forge`.
2. `src/odoo_forge_cli/` parsea el command y actúa como composition root.
3. La CLI llama a servicios y tipos puros del core en `src/odoo_forge/`.
4. La lógica core valida manifests, resuelve estado de lockfile, planifica acciones de workspace/backend o normaliza concerns de imágenes/base de datos.
5. Cuando el core necesita side effects, depende de contratos `ports/`.
6. Adapters concretos bajo `src/odoo_forge_git/`, `src/odoo_forge_workspace/`, `src/odoo_forge_docker/` y `src/odoo_forge_registry/` realizan el trabajo externo.
7. Los resultados vuelven a través de la CLI hacia la persona usuaria.

El database adapter PostgreSQL sobre Docker es adyacente a este flujo, no su centro actual: aporta groundwork de database-provider sin ser dueño de la ruta principal de orchestración del backend local.

## Flujo De Documentación Y OpenSpec

Usá este lifecycle del repositorio cuando evoluciones comportamiento o guía de mantenimiento.

1. Capturá el comportamiento deseado en un OpenSpec change activo bajo `openspec/changes/<change>/`.
2. Promové el comportamiento aceptado a `openspec/specs/**` cuando el change aterrice.
3. Reflejá el estado de producto/dependencias/evidencia en `docs/specs/platform/portfolio.json`.
4. Mantené actualizada la guía orientada a revisión en `README.md`, este mapa del repositorio y docs focalizados como la guía actual de implementación.
5. Mantené alineados los diagramas editando la fuente Mermaid y regenerando el SVG derivado.
6. Archivá OpenSpec changes completados o reemplazados bajo `openspec/changes/archive/` sin reescribir evidencia preservada.

Para docs gobernadas por portfolio, `docs/tools/platform_portfolio/validate.py` es la barrera determinista que chequea integridad estructural por fuera del flujo principal de calidad.

## Mapa De Tests Y Quality Gates

| Superficie | Autoridad | Qué hace cumplir |
| --- | --- | --- |
| `pyproject.toml` | Config central de tools | selección de pytest, coverage, Ruff, mypy, import-linter |
| `uv run pytest` | Verificación de comportamiento | Suite principal de tests Python |
| `uv run lint-imports` | Architecture gate | El core no debe importar módulos CLI/framework/infraestructura |
| `uv run mypy` | Typing estricto | Type-safety en `src/` y `tests/` |
| `uv run ruff check .` y `uv run ruff format --check .` | Estilo y consistencia | Lint y formato |
| `.github/workflows/quality.yml` | Puerta de calidad de CI | Ejecuta import-linter, Ruff, mypy y pytest en cambios de código/tests filtrados por path |
| `docs/tools/platform_portfolio/validate.py` | Validador de gobernanza documental | Chequea integridad de portfolio/documentación fuera del flujo principal de calidad |
| `.github/workflows/build-images.yml` | CI de factory | Build y smoke-test de imágenes Odoo CE independientemente del quality Python |
| `.github/workflows/cleanup-untagged.yml` | Higiene de registry | Limpia de forma segura digests sin tag de GHCR producidos por churn del flujo de imágenes |

El path filter de `quality.yml` importa: cambios solo de documentación no disparan automáticamente el flujo principal de calidad de código.

## Dónde Mirar Cuando...

| Si necesitás... | Empezá acá | Luego confirmá en |
| --- | --- | --- |
| Entender qué pueden hacer hoy las personas usuarias | `README.md` | `docs/specs/platform/portfolio.json`, `docs/diagrams/odoo-forge-current-implementation-guide.md` |
| Cambiar comportamiento de la CLI | `src/odoo_forge_cli/main.py` | `tests/cli/`, módulo core relevante bajo `src/odoo_forge/` |
| Cambiar semántica de manifest/lock/proyecto | `src/odoo_forge/manifest/` | `tests/manifest/`, spec aceptada en `openspec/specs/manifest/` |
| Cambiar comportamiento del runtime local | `src/odoo_forge_docker/` y `src/odoo_forge/backend/` | `tests/backend/`, `tests/adapters/`, `openspec/specs/local-backend/` |
| Cambiar comportamiento del image registry | `src/odoo_forge_registry/`, `src/odoo_forge/image_registry/` | `tests/adapters/`, `tests/ports/`, `openspec/specs/image-registry-provider/` |
| Trabajar en foundations de database-provider | `src/odoo_forge/database/`, `src/odoo_forge_postgres_docker/` | `tests/database/`, `tests/adapters/`, `openspec/specs/database-provider/`, `openspec/specs/docker-postgresql-database-adapter/` |
| Entender estado o dependencias actuales de la plataforma | `docs/specs/platform/portfolio.json` | specs aceptadas relevantes y archived changes |
| Actualizar el diagrama actual de implementación | `docs/diagrams/odoo-forge-current-implementation.mmd` | `docs/diagrams/README.md` para reglas de render |
| Determinar si un documento es seguro de reescribir | [Matriz De Autoridad Del Repositorio](02-repository-authority-matrix.md) | ubicación en el árbol vivo y estado de archivo |
| Retomar trabajo de planificación de producto sin riesgo | `openspec/changes/sp-data-environments/` | `docs/specs/platform/portfolio.json` y evidencia archivada prerequisito |

## Guía De Continuación Segura

| Área | Siguiente movimiento seguro | Evitá |
| --- | --- | --- |
| Código de runtime | Cambiar core o adapter junto con los tests y referencias a specs correspondientes | Saltarte las reglas de límites de imports o cablear foundations en workflows sin autoridad explícita de spec |
| Documentación | Actualizar docs de guía actuales y contrastarlas con `portfolio.json` y el estado vivo de OpenSpec | Tratar narrativas archivadas de changes como verdad activa |
| OpenSpec | Continuar trabajo nuevo desde `sp-data-environments` o crear un change nuevo acotado | Reabrir directorios archivados para editarlos |
| Diagramas | Editar `.mmd` y luego renderizar `.svg` | Editar a mano SVG generado |
| Factory | Mantener juntos la lógica de build de imágenes y los smoke tests | Mezclar cambios de workflow de factory con docs/código de runtime no relacionados sin necesidad |

## Vacíos De Documentación

El repositorio ya tiene un mapa para maintainers, pero estos vacíos siguen siendo buenos candidatos de seguimiento:

1. Un reemplazo o complemento en inglés para `docs/diagrams/odoo-forge-current-implementation-guide.md`, que es detallado, está en español y está enfocado en runtime.
2. Una guía focalizada para maintainers de los subdominios de `src/odoo_forge/` que mapee specs aceptadas de OpenSpec a módulos concretos.
3. Una guía breve de gobernanza documental que explique cómo se relacionan `portfolio.json`, el validator, los roadmaps fechados y los archived OpenSpec changes.
4. Una nota dedicada que reconcilie referencias desactualizadas al change archivado de roadmap-refresh en `README.md` y `docs/specs/2026-07-14-stabilization-roadmap.md`.

## Checklist De Revisión

- El directorio que pensás tocar está listado arriba con el nivel de autoridad correcto.
- La fuente que estás editando es canónica, no meramente derivada o histórica.
- Las afirmaciones de runtime están corroboradas por `README.md`, `portfolio.json` o specs aceptadas.
- Las afirmaciones sobre OpenSpec reflejan el árbol vivo de `openspec/changes/`, no solo docs narrativos viejos.
