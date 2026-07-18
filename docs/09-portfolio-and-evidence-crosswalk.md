# Cruce De Portfolio Y Evidencia

## Qué es este documento

Es una guía de trazabilidad que explica cómo se relacionan `portfolio.json`, el validator, la evidencia catalogada, los gaps, la historia protegida, los archived OpenSpec changes y la documentación guía del repositorio.

## Por qué importa

Importa porque este repo no usa solo prosa: usa un portfolio estructurado y un validador determinista para convertir gobernanza documental en una superficie verificable.

## Por qué existe

Existe para responder dos preguntas clave: dónde pertenece cada hecho y cómo se valida antes de considerarlo confiable.

## Cómo ayuda al sistema

Ayuda al sistema porque mantiene alineadas verdad actual, evidencia, historia protegida y guías narrativas, evitando que una afirmación viva en el archivo incorrecto o sin validación.

## Leer Después De...

Leé esto después de [08-sp-data-environments-map.md](08-sp-data-environments-map.md). Siguiente lectura: [10-diagrams-maintenance-guide.md](10-diagrams-maintenance-guide.md).

## Piezas principales y su rol

| Superficie | Rol real |
| --- | --- |
| `docs/specs/platform/portfolio.json` | Fuente estructural canónica del estado de portfolio, dependencias, decisiones, evidencia y gaps |
| `docs/tools/platform_portfolio/validate.py` | Validador determinista que comprueba integridad estructural y límites de repositorio/documentación |
| `docs/tools/platform_portfolio/test_validate.py` | Pruebas del validador; demuestran que los invariantes importantes están cubiertos |
| `openspec/changes/archive/**` | Historia preservada de cambios cerrados; fuente válida de evidencia cuando el portfolio la referencia |
| `docs/specs/*.md` y `docs/0x-*.md` | Guía narrativa actual o histórica; útil para humanos, pero subordinada a fuentes canónicas cuando hay conflicto |

## Cómo encajan entre sí

### `portfolio.json`

`docs/specs/platform/portfolio.json` es la pieza central.

Contiene, entre otras cosas:

| Sección | Para qué sirve |
| --- | --- |
| `meta.source_documents` | Lista de documentos fuente que sostienen el portfolio |
| `meta.evidence_catalog` | Catálogo de evidencia referenciable por ID |
| `meta.gap_catalog` | Catálogo de gaps cuando una evidencia no existe o una aceptación sigue incompleta |
| `meta.protected_history_paths` y `meta.protected_history_sha256` | Historia protegida que no debe mutarse silenciosamente |
| `meta.command_catalog` | Comandos de verificación que las decompositions pueden citar |
| `meta.historical_alias_map` | Mapa entre alias históricos y entidades actuales |
| `items` | Outcomes, prerequisites, ports, adapters, integrations, workflows y changes |
| `decisions` | Decisiones resueltas o pendientes con evidencia asociada |
| `decompositions` | Cambios SDD futuros y sus dependencias/verificaciones |

### `validate.py`

El validador convierte ese portfolio en un contrato ejecutable.

Valida, entre otras cosas:

| Invariante | Qué evita |
| --- | --- |
| IDs únicos y referencias resolubles | Items, edges o transfers colgantes |
| Gramática de `dotted_scope` | Ambiguedad en transfers de ownership |
| Acyclicidad de dependencias | Roadmaps imposibles o contradictorios |
| Evidencia y gaps coherentes | Evidencia inventada o no verificable sin justificación |
| Paths de archive protegidos | Reescritura silenciosa de historia preservada |
| Integridad de diagramas y renderer | Que la documentación visual quede incoherente con sus reglas |

### Evidencia, gaps e historia protegida

La relación correcta es esta:

1. Un item o una decisión del portfolio declara evidencia por ID.
2. Ese ID se resuelve en `meta.evidence_catalog` hacia una ruta concreta o una referencia controlada.
3. Si la evidencia ya no es verificable pero la afirmación histórica debe mantenerse, la ausencia debe quedar explicada mediante `gap_catalog`.
4. Si un documento está protegido por hash en `protected_history_sha256`, no debe reescribirse porque el validador lo considera historia inmutable.

## Dónde pertenece cada hecho

| Tipo de hecho | Dónde pertenece primero | Cómo se valida |
| --- | --- | --- |
| Estado actual de un outcome, prerequisite o decision | `docs/specs/platform/portfolio.json` | `python docs/tools/platform_portfolio/validate.py --root .` |
| Evidencia concreta que respalda una aceptación | Archivo real del repo y su entrada en `meta.evidence_catalog` | El validador comprueba existencia, alcance y soporte |
| Falta de evidencia o bloqueo conocido | `meta.gap_catalog` y los `gaps` del item/acceptance correspondiente | El validador exige consistencia entre gap y ausencia verificable |
| Historia cerrada de un change | `openspec/changes/archive/<fecha>-<change>/` | La ruta archivada y, cuando aplica, hashes protegidos |
| Comportamiento aceptado de producto o runtime | `openspec/specs/**` | Revisión de specs más tests/código relacionados |
| Explicación orientada a maintainers | `docs/01` a `docs/10` y guías actuales | Coherencia manual contra fuentes canónicas |
| Diagrama actual o objetivo | `docs/diagrams/*.mmd` | Renderer y chequeos del validator |

## Qué lugar ocupa la historia archivada

Los archived OpenSpec changes NO son planificación activa, pero sí pueden ser evidencia válida o contexto obligatorio.

Casos visibles en el repo:

| Archive | Cómo encaja hoy |
| --- | --- |
| `2026-07-10-platform-subproject-redefinition/` | Introduce el portfolio outcome-first y el validador |
| `2026-07-16-CHG-FIRST-DATABASE-ADAPTER/` | Conserva evidencia de la primera base para `DPROV-DB` y `S62` |
| `2026-07-16-fix-roadmap-refresh-verification-closure/` | Aporta reglas y evidencia preservada para integridad documental |
| `2026-07-17-refresh-platform-roadmap-after-stabilization/` | Cierra el refresh del roadmap y preserva la revisión/candidate history |

## Regla práctica para ubicar una afirmación

| Si la afirmación dice... | Va primero en... |
| --- | --- |
| "esto está aceptado / logrado / propuesto" | `portfolio.json` |
| "esto pasó en tal change y debe preservarse" | el archive correspondiente |
| "esto es la explicación para maintainers" | la guía `docs/0x-*.md` apropiada |
| "esto es un contrato de comportamiento aceptado" | `openspec/specs/**` |
| "esto es la imagen actual o target del sistema" | `.mmd` y su guía asociada |

## Flujo seguro de actualización

1. Cambiá primero la fuente canónica del hecho.
2. Si el cambio toca portfolio, actualizá `docs/specs/platform/portfolio.json`.
3. Si agregás o movés evidencia, actualizá `meta.evidence_catalog` y, si hace falta, `gap_catalog`.
4. Ejecutá `python docs/tools/platform_portfolio/validate.py --root .`.
5. Si el cambio modifica narrativa, recién después alineá `docs/01` a `10`, `README.md` o guías relacionadas.

## Errores comunes

- Corregir solo una guía narrativa y olvidar `portfolio.json`.
- Reemplazar evidencia real por una ruta que no existe o que cae fuera del alcance admitido por el validador.
- Editar historia protegida en vez de agregar una guía actual nueva.
- Usar un archive como si fuera el inventario activo del repo.
- Registrar una ausencia de evidencia sin crear el gap correspondiente.
