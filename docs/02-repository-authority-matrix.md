# Matriz De Autoridad Del Repositorio

## Qué es este documento

Es una matriz de autoridad que indica qué superficie del repositorio es dueña de cada tipo de hecho: comportamiento, tests, portfolio, diagramas, historial preservado o automatización.

## Por qué importa

Importa porque en este repo conviven fuentes canónicas, salidas derivadas y evidencia histórica; si se edita la superficie incorrecta, se rompe la trazabilidad o se reescribe historia que debe preservarse.

## Por qué existe

Existe para responder rápido "dónde pertenece este hecho" y para acompañar al [Mapa Del Repositorio](01-repository-map.md) con una política operativa de edición.

## Cómo ayuda al sistema

Ayuda al sistema porque ordena las decisiones de mantenimiento, mantiene coherentes los enlaces entre runtime, docs y OpenSpec, y protege la separación entre verdad actual, derivados y archivos históricos.

## Leer Después De...

Leé esto después del [Mapa Del Repositorio](01-repository-map.md). Siguiente lectura: [03-src-core-map.md](03-src-core-map.md) si el cambio está en runtime code, [06-docs-and-openspec-lifecycle.md](06-docs-and-openspec-lifecycle.md) si el cambio es de docs u OpenSpec, [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md) si necesitás trazabilidad capability -> módulo, y [09-portfolio-and-evidence-crosswalk.md](09-portfolio-and-evidence-crosswalk.md) si necesitás ubicar hechos de portfolio o evidencia.

## Matriz De Autoridad

| Superficie | De qué es dueña | Estado en el repo | Política de edición |
| --- | --- | --- | --- |
| `src/**` | Comportamiento de runtime y lógica de dominio | Canónica | Editar directo con tests |
| `tests/**` | Expectativas ejecutables de comportamiento | Canónica | Editar directo junto con el código |
| `pyproject.toml` | Tooling Python y configuración de architecture gates | Canónica | Editar directo |
| `docs/specs/platform/portfolio.json` | Estado actual de producto, dependencias, evidencia y referencias de protected-history | Canónica | Editar directo; validar estructuralmente |
| `docs/tools/platform_portfolio/validate.py` | Reglas deterministas de gobernanza documental | Tool canónico | Editar directo con sus tests |
| `openspec/specs/**` | Autoridad de especificación aceptada | Canónica | Editar solo cuando cambia el comportamiento aceptado |
| `openspec/changes/sp-data-environments/**` | Trabajo actual de change activo | Canónica en progreso | Editar directo para trabajo en curso |
| `openspec/changes/archive/**` | Evidencia histórica preservada de changes | Histórica | No reescribir |
| `docs/diagrams/*.mmd` | Fuente canónica de diagramas documentados | Canónica | Editar directo |
| `docs/diagrams/*.svg` | Salidas renderizadas de diagramas | Derivada | Regenerar; no editar a mano |
| `docs/specs/*.md` | Narrativas fechadas de roadmap y diseño orientadas a revisión | Mixto actual/histórico | Editar con cuidado; verificar contra fuentes canónicas |
| `README.md` | Overview del repositorio de cara al usuario | Guía actual | Editar con cuidado; verificar contra fuentes canónicas |
| `docs/reviews/**` | Historial de auditoría/revisión | Histórica | Preservar |
| `docs/superpowers/**` | Docs de soporte de diseño/planning anteriores | Histórico/de apoyo | Preferir docs nuevas antes que reescrituras |
| `factory/**` | Pipeline y tests de build de imágenes | Canónica para image factory | Editar directo dentro de ese scope |
| `.github/workflows/quality.yml` | CI principal de calidad de código | Automatización canónica | Editar directo |
| `.github/workflows/build-images.yml` | CI de build/publicación de imágenes | Automatización canónica | Editar directo |
| `.github/workflows/cleanup-untagged.yml` | Automatización de limpieza GHCR | Automatización canónica | Editar directo |
| `dist/**`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.import_linter_cache/` | Outputs de build y tooling | Derivado/local | No tratarlos como fuente |

## Notas De Canonicalidad Actual

| Tema | Interpretación segura actual |
| --- | --- |
| Trabajo OpenSpec activo | El árbol vivo muestra solo `openspec/changes/sp-data-environments/` como activo |
| Change de roadmap-refresh | Histórico; preservado bajo `openspec/changes/archive/2026-07-17-refresh-platform-roadmap-after-stabilization/` |
| Límite actual del runtime | `README.md` más `docs/diagrams/odoo-forge-current-implementation.mmd` y su guía describen el scope distribuido |
| Estado de dependencias y evidencia del producto | `docs/specs/platform/portfolio.json` es la autoridad |
| Contrato de render de diagramas | `docs/diagrams/README.md` y `render-current-implementation.sh` definen cómo Mermaid canónico se convierte en SVG derivado |
| Enforcement del límite de arquitectura | Los contratos de import-linter en `pyproject.toml` más `quality.yml` lo vuelven un gate real de CI |

## Reglas De Edición

1. Actualizá primero las fuentes canónicas.
2. Regenerá los artifacts derivados en lugar de editarlos a mano.
3. Preservá los artifacts históricos; agregá un doc nuevo o una entrada de archive en vez de reescribir historia.
4. Cuando la guía actual y los docs históricos se contradicen, confiá en el árbol vivo y las fuentes canónicas por encima de la prosa narrativa vieja.
