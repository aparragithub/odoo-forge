# Guía De Mantenimiento De Diagramas

## Qué es este documento

Es la guía operativa para mantener los diagramas del repositorio: define qué archivo es canónico, qué archivo es derivado, qué rol cumple el renderer y cómo actualizar los diagramas sin romper gobernanza ni coherencia documental.

## Por qué importa

Importa porque en este repo los diagramas no son decoración. El validador de portfolio/documentación comprueba su integridad, la coherencia del renderer y el vínculo entre diagrama, SVG y guía asociada.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras actualicen diagramas de forma segura, reproducible y auditable, sin editar a mano archivos generados ni introducir claims obsoletos.

## Cómo ayuda al sistema

Ayuda al sistema porque mantiene sincronizadas la representación visual, la guía narrativa y la autoridad documental que usa el repositorio para describir el estado actual y el estado objetivo.

## Leer Después De...

Leé esto después de [09-portfolio-and-evidence-crosswalk.md](09-portfolio-and-evidence-crosswalk.md). Siguiente lectura: `docs/diagrams/README.md`, `docs/diagrams/odoo-forge-current-implementation-guide.md` y luego [01-repository-map.md](01-repository-map.md) para volver a la vista global.

## Regla canónica básica

| Artifact | Estado | Regla |
| --- | --- | --- |
| `docs/diagrams/odoo-forge-current-implementation.mmd` | Canónico | Se edita directo |
| `docs/diagrams/odoo-forge-current-implementation.mmd.svg` | Derivado | Se regenera; no se edita a mano |
| `docs/diagrams/render-current-implementation.sh` | Herramienta canónica de render | Debe seguir fijada al runtime e imagen permitidos |

Mermaid es la fuente autoritativa. El SVG es solo una salida derivada. Si editás el SVG a mano, estás rompiendo el contrato de mantenimiento del repo.

## Rol del renderer

El renderer `docs/diagrams/render-current-implementation.sh` convierte el Mermaid canónico a SVG usando Mermaid CLI fijado por tag y digest.

Su rol no es cosmético; garantiza:

| Garantía | Por qué importa |
| --- | --- |
| Runtime y versión fijados | Evita diferencias arbitrarias entre máquinas |
| Render determinista con `--check` | Permite verificar que el SVG corresponde al Mermaid actual |
| Configuración de tema/fuente/viewport estable | Reduce cambios espurios en el SVG |
| Límite de ejecución controlado | Hace que el chequeo documental sea repetible |

## Diagramas actuales y objetivo

Hoy conviene leer dos diagramas distintos:

| Archivo | Qué representa |
| --- | --- |
| `docs/diagrams/odoo-forge-current-implementation.mmd` | Estado actual implementado del sistema |
| `docs/diagrams/odoo-forge-complete-platform.mmd` | Estado objetivo más amplio de la plataforma |

La diferencia es crítica: el diagrama actual documenta lo que ya existe o está fundado de forma explícita; el diagrama completo muestra la dirección futura. No deben mezclarse claims de uno con el otro.

## Relación con la guía explicativa

`docs/diagrams/odoo-forge-current-implementation-guide.md` explica en lenguaje humano el diagrama actual. Esa guía debe seguir alineada con Mermaid y con el portfolio.

Relación correcta:

1. El `.mmd` fija la estructura visual canónica.
2. El `.svg` es la imagen derivada de ese `.mmd`.
3. La guía explica el mismo estado actual en prosa.
4. El portfolio sigue siendo la autoridad del estado, dependencias y evidencia cuando haya dudas.

## Flujo seguro de actualización

1. Confirmá si el cambio describe estado actual o estado objetivo.
2. Editá primero el archivo `.mmd` correcto.
3. Si el cambio altera explicación narrativa, alineá la guía correspondiente.
4. Regenerá o verificá el SVG con `docs/diagrams/render-current-implementation.sh` o `docs/diagrams/render-current-implementation.sh --check`.
5. Si el cambio afecta gobernanza documental, corré `python docs/tools/platform_portfolio/validate.py --root .`.

## Errores comunes

| Error | Consecuencia |
| --- | --- |
| Editar el `.svg` a mano | El derivado deja de corresponder al Mermaid canónico |
| Cambiar claims del diagrama actual usando elementos que solo existen en el target | La documentación afirma capacidades no entregadas |
| Actualizar la guía sin actualizar Mermaid, o viceversa | La prosa y el diagrama divergen |
| Modificar el renderer sin respetar su pin o su contrato | El validator puede marcar `fixed-renderer` o `renderer-coherence` |
| Dejar links rotos entre HTML/guía/diagramas | El validator puede marcar `html-guide-link` u otros errores de integridad |

## Consecuencias de gobernanza y validación

`docs/tools/platform_portfolio/validate.py` revisa varios aspectos de esta superficie. Puede fallar, entre otros, por:

| Código de validación | Qué significa |
| --- | --- |
| `fixed-renderer` | El renderer ya no coincide con la versión fijada esperada |
| `renderer-coherence` | El render chequeado no coincide con el SVG derivado |
| `missing-derived-output` | Falta el SVG esperado |
| `html-guide-link` | El vínculo desde la documentación HTML ya no apunta a la guía canónica |
| `stale-claim` | El diagrama o la doc asociada contienen afirmaciones obsoletas |

## Regla final para maintainers

Si una afirmación visual cambia, cambiá primero Mermaid. Si una afirmación de estado cambia, verificála primero contra `portfolio.json`. Si una evidencia histórica contradice una guía, preservá la historia y escribí una guía actual nueva en vez de maquillar el archive.
