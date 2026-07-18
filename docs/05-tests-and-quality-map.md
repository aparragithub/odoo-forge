# Mapa De Tests Y Quality

## Qué es este documento

Es el mapa de verificación del repositorio: organiza suites de tests, markers opt-in, tooling local y workflows de CI que validan código, límites de arquitectura y gobernanza documental.

## Por qué importa

Importa porque en `odoo-forge` no alcanza con que el código funcione: también hay que preservar contratos del core, selección correcta de tests y expectativas reales sobre qué ejecuta CI.

## Por qué existe

Existe para que quienes mantienen el repo sepan dónde ubicar pruebas nuevas, qué herramientas mandan sobre cada tipo de verificación y qué cambios quedan fuera del flujo automático principal.

## Cómo ayuda al sistema

Ayuda al sistema porque reduce regresiones, hace explícitos los gates de arquitectura y evita suposiciones falsas sobre coverage, markers o triggers de GitHub Actions.

## Leer Después De...

Leé esto después de [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md). Siguiente lectura: [06-docs-and-openspec-lifecycle.md](06-docs-and-openspec-lifecycle.md). Si querés cerrar el circuito con trazabilidad por capability, seguí con [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md).

## Ruta Rápida

1. Empezá acá antes de cambiar el scope de tests o la configuración de tools.
2. Usá la taxonomía de abajo para ubicar tests nuevos en la capa más angosta que pruebe el comportamiento.
3. Revisá los path filters de CI antes de asumir que un cambio solo de docs va a ejecutar el workflow principal.

## Taxonomía De Directorios De Tests

| Path | Qué prueba |
| --- | --- |
| `tests/manifest/` | schema, composición, formato de lockfile, locking, projection, drift, resolución de manifest |
| `tests/backend/` | tipos del backend plan, parseo de status, errores del backend |
| `tests/ports/` | contratos de ports y expectativas de protocolos |
| `tests/adapters/` | comportamiento concreto de adapters Git, workspace, Docker, registry y PostgreSQL Docker |
| `tests/cli/` | wiring de commands, flujos visibles para usuarios, límites de salida |
| `tests/database/` | tipos de base de datos neutrales al provider, readiness y errores |
| `tests/credentials/` | reglas de materialización y seguridad de credenciales |
| `tests/data_artifacts/` | contratos de restore/discard y reglas de redaction |
| `tests/project_catalog/` | comportamiento de resolución autoritativa del catálogo |
| `tests/durable_operations/` | servicio de durable operations y tipos de lifecycle |
| `tests/factory/` | checks de wiring de image factory |
| `tests/fixtures/` | fixtures de manifest reutilizables |

## Capas De Test Por Defecto Vs Opt-In

| Capa | ¿Por defecto? | Cómo se selecciona |
| --- | --- | --- |
| Unit tests e integration tests normales sin markers especiales | Sí | `uv run pytest` |
| Tests `integration` | No | se deseleccionan por defecto vía `addopts` de pytest; ejecutar con `uv run pytest -m integration` |
| Tests `real_docker` | No | opt-in explícito con `uv run pytest -m real_docker` |

Uso actual de markers que conviene recordar:

- `tests/adapters/test_docker_provider_integration.py` usa `pytest.mark.integration`.
- `tests/adapters/test_postgres_docker_provider_integration.py` usa `pytest.mark.integration` y `pytest.mark.real_docker`.

## Qué Controla `pyproject.toml`

| Sección | Impacto para maintainers |
| --- | --- |
| `[project]` / `[project.scripts]` | metadata del package y entrypoint `forge` |
| `[tool.hatch.build.targets.wheel]` | qué packages de `src/` entran al wheel |
| `[dependency-groups.dev]` | toolchain local de desarrollo y quality |
| `[tool.pytest.ini_options]` | test paths por defecto, selección por defecto de markers, argumentos de coverage |
| `[tool.coverage.*]` | fuente de coverage, branch coverage, reporte de líneas faltantes |
| `[tool.ruff.*]` | set de reglas de lint, target de formato, roots de imports |
| `[tool.mypy]` y `[tool.pydantic-mypy]` | límites de typing estricto y comportamiento del plugin de Pydantic |
| `[tool.importlinter]` y contracts | límites arquitectónicos de imports, especialmente aislamiento del core |

## Mapa De Interacción De Quality Tools

| Tool | Rol principal | Cómo interactúa con las demás |
| --- | --- | --- |
| Ruff | checks de lint + formato | Primera pasada rápida de higiene antes de fallos de tipos o tests |
| mypy | typing estático estricto sobre `src` y `tests` | Valida contratos tipados que los tests pueden no cubrir exhaustivamente |
| import-linter | architecture gate | Impide que el core importe CLI, adapters o módulos externos prohibidos |
| pytest | verificación de comportamiento | Ejecuta tests con deselección de markers por defecto desde `pyproject.toml` |
| coverage | capa de reporting sobre pytest | Usa defaults de pytest-cov desde `addopts` y secciones de coverage |
| GitHub Actions `quality.yml` | wrapper de ejecución en CI | Ejecuta import-linter, Ruff, mypy y pytest en ese orden |

## Scope De GitHub Actions

| Workflow | Scope de trigger | Qué ejecuta |
| --- | --- | --- |
| `.github/workflows/quality.yml` | cambios bajo `src/**`, `tests/**`, `pyproject.toml`, `.github/workflows/**`, más manual dispatch | `uv sync`, `uv run lint-imports`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest` |
| `.github/workflows/build-images.yml` | paths relacionados con factory/imágenes y manual dispatch | build de imágenes y smoke validation |
| `.github/workflows/cleanup-untagged.yml` | schedule y manual dispatch | automatización de limpieza GHCR |

Consecuencia importante: cambios solo de docs no disparan automáticamente `quality.yml`.

## Validación De Gobernanza Documental

| Superficie | Rol | Relación con el workflow principal de quality |
| --- | --- | --- |
| `docs/tools/platform_portfolio/validate.py` | validator determinista de `docs/specs/platform/portfolio.json` y de la integridad documental relacionada | separado de `quality.yml`; no es parte del pipeline por defecto de calidad de código |
| `docs/tools/platform_portfolio/test_validate.py` | prueba el validator en sí | vive en la suite de tests Python, pero el propósito de gobernanza del validator sigue siendo distinto |
| `openspec/specs/platform-portfolio-documentation-integrity/` | spec aceptada de gobernanza documental | describe por qué existe el validator y qué protege |

Esa separación importa. El repositorio tiene un flujo de calidad de código y una barrera separada de gobernanza documental. Se superponen en tooling, pero NO representan la misma superficie de autoridad.

## Reglas De Ubicación Para Maintainers

| Si cambiaste... | Empezá actualizando... |
| --- | --- |
| lógica pura de manifest/backend/core | los tests de dominio correspondientes y cualquier test de contrato de ports afectado |
| comportamiento `subprocess` de adapters | `tests/adapters/` primero, luego tests CLI si cambia output visible al usuario |
| wiring de commands o límites de error | `tests/cli/` |
| límites de arquitectura | contratos de import-linter en `pyproject.toml` y cualquier test que afirme aislamiento |
| reglas de gobernanza documental | código/tests del validator y las fuentes docs/OpenSpec afectadas |

## Checklist De Verificación

- Los tests nuevos viven en la capa significativa más angosta.
- La elección de marker es explícita cuando un test necesita un daemon real o Docker real.
- `pyproject.toml` sigue siendo la fuente única para configuración de pytest, Ruff, mypy, coverage e import-linter.
- Las asunciones de CI coinciden con los path filters de `.github/workflows/quality.yml`.
- La validación de gobernanza documental se trata como adyacente a, no idéntica a, el flujo principal de calidad.
