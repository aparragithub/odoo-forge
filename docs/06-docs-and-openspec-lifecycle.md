# Lifecycle De Docs Y OpenSpec

## Qué es este documento

Es la guía de ciclo de vida para `docs/` y `openspec/`: explica qué es verdad actual, qué es verdad aceptada, qué cambio está vivo y qué historia debe preservarse intacta.

## Por qué importa

Importa porque este repo usa documentación operativa, portfolio canónico y cambios OpenSpec archivados como parte real de su gobernanza. Confundir esas capas lleva a decisiones erróneas y a documentación incoherente.

## Por qué existe

Existe para orientar a maintainers y futuras personas implementadoras antes de editar portfolio, narrativas, changes activos o archivos históricos.

## Cómo ayuda al sistema

Ayuda al sistema porque mantiene la continuidad entre planning, aceptación, archivado y guías actuales, sin perder la separación entre trabajo vivo y evidencia preservada.

## Leer Antes De...

Si necesitás una vista general de toda la serie documental, empezá en [`00-master-index.md`](00-master-index.md). Este `06` es la pieza de lifecycle dentro de esa ruta `00` a `21`.

## Leer Después De...

Leé esto después de [05-tests-and-quality-map.md](05-tests-and-quality-map.md). Siguiente lectura: [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md) para cruzar specs aceptadas con módulos, adapters, tests y flujos visibles; después [08-sp-data-environments-map.md](08-sp-data-environments-map.md), [09-portfolio-and-evidence-crosswalk.md](09-portfolio-and-evidence-crosswalk.md) y [10-diagrams-maintenance-guide.md](10-diagrams-maintenance-guide.md). Luego volvé a [01-repository-map.md](01-repository-map.md) cuando necesites orientación global otra vez.

## Ruta Rápida

1. Empezá acá antes de editar `docs/` o `openspec/`.
2. Decidí si el hecho es verdad actual, verdad aceptada, planning activo o historia preservada.
3. Actualizá la fuente actual de mayor autoridad y preservá intactos los artifacts históricos.

## Estructura De `docs/` Por Propósito

| Path | Propósito | Postura de edición |
| --- | --- | --- |
| `docs/00-*.md` a `docs/21-*.md` | serie numerada para maintainers sobre estructura, autoridad, lifecycle, cruces y mapas focalizados | guía actual |
| `docs/diagrams/` | visuales de arquitectura actual y objetivo, fuentes Mermaid, contrato de render y guía de runtime | editar fuentes `.mmd` y de guía; tratar `.svg` como derivado |
| `docs/specs/platform/portfolio.json` | estado canónico del portfolio, dependencias, evidencia y referencias de protected-history | fuente canónica actual |
| `docs/specs/*.md` | narrativas fechadas de diseño y roadmap | mixto actual/histórico; verificar antes de editar |
| `docs/tools/platform_portfolio/` | validator determinista y tests para integridad de portfolio/documentación | tool canónico de gobernanza |
| `docs/reviews/` | artifacts de revisión/auditoría | preservar como historia |
| `docs/superpowers/` | docs anteriores de planning/apoyo | preservar; preferir docs nuevas antes que reescribir estas |

## Árboles OpenSpec Y Su Significado

| Path | Significado |
| --- | --- |
| `openspec/specs/` | specs canónicas aceptadas para comportamiento distribuido o aceptado |
| `openspec/changes/` | changes vivos en progreso solamente |
| `openspec/changes/archive/` | historias preservadas de changes completados o reemplazados |
| `openspec/config.yaml` | reglas OpenSpec del repositorio, convenciones de verificación y commands de test |

## Verdad Actual Vs Verdad Histórica

| Tema | Interpretación segura actual |
| --- | --- |
| Trabajo de change activo | solo `openspec/changes/sp-data-environments/` está activo |
| Trabajo de roadmap-refresh | histórico; preservado bajo `openspec/changes/archive/2026-07-17-refresh-platform-roadmap-after-stabilization/` |
| Verdad aceptada de runtime/spec | `openspec/specs/**` más docs canónicas actuales como `portfolio.json` |
| Narrativas de changes archivados | evidencia e historia, no autoridad de planning vivo |

## Tipos De Artifacts OpenSpec

| Artifact | Significado |
| --- | --- |
| `exploration.md` | encuadre del problema, alternativas y unknowns antes del compromiso |
| `proposal.md` | change deseado, scope, rationale y encuadre de rollback |
| `design.md` | enfoque técnico y decisiones de arquitectura para el change |
| `tasks.md` | desglose de implementación y plan de ejecución |
| `apply-progress.md` | progreso de implementación o receipts de ejecución durante la aplicación |
| `verify-report.md` | evidencia y outcome de verificación después de implementar |
| `archive-report.md` | registro explícito de cierre al archivar un change |
| `reviews/` | estado preservado de revisión, receipts, chain bundles y metadata relacionada |
| `evidence/` | receipts preservados de evidencia como hashes, notas de fallo capturadas o proof artifacts |
| `specs/<capability>/spec.md` dentro de un change | texto delta de spec propuesto por ese change |

No todo directorio de change contiene todos los artifacts, pero los archived changes muestran el vocabulario completo de lifecycle que el repo preserva.

## Lifecycle: De Planning A Archive

| Fase | Ubicación principal | Qué se vuelve autoritativo |
| --- | --- | --- |
| Explore | `openspec/changes/<change>/exploration.md` | todavía no hay nada distribuido |
| Propose | `openspec/changes/<change>/proposal.md` | scope y rationale deseados |
| Design | `openspec/changes/<change>/design.md` | enfoque técnico del change |
| Task | `openspec/changes/<change>/tasks.md` | slices de ejecución |
| Apply | código/docs/tests más `apply-progress.md` opcional | cambios de runtime/docs en sus hogares canónicos |
| Verify | `verify-report.md` y evidencia de tests/build | prueba de que el cambio aplicado coincide con la intención |
| Promote accepted behavior | `openspec/specs/**` y docs actuales como `portfolio.json` | verdad canónica aceptada |
| Archive | `openspec/changes/archive/<dated-change>/` | workflow histórico y evidencia preservados |

## Reglas De Preservación

| Preservar acá | Por qué |
| --- | --- |
| `openspec/changes/archive/**` | evidencia histórica inmutable del workflow |
| subdirectorios `reviews/` | receipts de revisión y estado de cadenas forman parte del registro |
| subdirectorios `evidence/` | proof externo y fallos capturados deben seguir siendo reproducibles/auditables |
| docs fechadas bajo `docs/specs/` cuando son referencias históricas | explican decisiones pasadas aunque la verdad actual se haya movido a otro lado |

No reescribas directorios OpenSpec archivados para hacer que la historia se vea más prolija. Agregá en cambio un documento actual nuevo, una spec aceptada nueva o un archive report.

## Tabla De Decisión Para Maintainers

| Si necesitás actualizar... | Editá primero acá |
| --- | --- |
| comportamiento distribuido o aceptado | `openspec/specs/**` y código/docs canónicos correspondientes |
| estado actual de producto/dependencias/evidencia | `docs/specs/platform/portfolio.json` |
| trabajo futuro activo | `openspec/changes/sp-data-environments/**` |
| solo contexto histórico | dejá intactos los bytes del archive; agregá una doc actual más nueva si hace falta |

## Matiz Importante Actual

El repo contiene muchos directorios históricos de changes, pero quienes mantienen el proyecto deberían tratar solo `openspec/changes/sp-data-environments/` como trabajo activo. Las referencias a roadmap-refresh o a su corrective closure fuera del archive son históricas o desactualizadas salvo que estén corroboradas por el árbol vivo y por docs canónicas actuales.

## Checklist Antes De Editar Docs U OpenSpec

- El hecho pertenece a docs actuales, specs aceptadas, un change activo o historia preservada.
- Si cambia un diagrama, editá la fuente Mermaid y no el SVG renderizado.
- Si cambia un hecho de portfolio/estado, actualizá `docs/specs/platform/portfolio.json` y validalo.
- Si un change está completo, promové la verdad aceptada antes de archivar los artifacts del workflow.
- Los artifacts históricos siguen preservados en `openspec/changes/archive/**`, incluyendo receipts de `reviews/` y `evidence/`.
