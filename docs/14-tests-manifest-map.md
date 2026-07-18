# Mapa De `tests/manifest/`

## Qué es este documento

Es la ficha de mantenimiento de `tests/manifest/`: organiza la suite que protege la semántica del manifest, del lockfile, de la proyección al workspace y del drift.

## Por qué importa

Importa porque el directorio `src/odoo_forge/manifest/` es una superficie pequeña en archivos, pero fundacional en comportamiento. Si esta suite se debilita, se pueden introducir regresiones silenciosas en la capa que decide qué proyecto existe realmente.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras sepan qué subáreas ya están cubiertas, dónde debe vivir cada prueba nueva y por qué no conviene desviar estas verificaciones a tests CLI o adapters cuando el comportamiento es puro.

## Cómo ayuda al sistema

Ayuda al sistema porque mantiene segura la evolución del manifest como contrato autoritativo: permite cambiar implementación interna sin perder determinismo, compatibilidad ni señales de drift correctas.

## Leer después de...

Leer después de [05-tests-and-quality-map.md](05-tests-and-quality-map.md) y [11-src-manifest-map.md](11-src-manifest-map.md).

## Siguiente lectura...

Seguir con [15-tests-adapters-map.md](15-tests-adapters-map.md). Si el cambio llega hasta runtime local, complementar con [12-src-backend-map.md](12-src-backend-map.md).

## Ruta rápida

1. Empezar aquí cuando un cambio toque `schema`, `composition`, `locking`, `projection`, `lockfile` o `drift`.
2. Agregar la prueba en la subárea más angosta posible.
3. Subir a CLI solo si cambió la presentación o el wiring, no la semántica pura.

## Qué comportamientos protege

| Comportamiento protegido | Archivos principales |
| --- | --- |
| Validación estructural del manifest | `test_schema.py` |
| Coherencia de composición y overrides | `test_composition.py` |
| Resolución de refs por defecto del core | `test_resolution.py` |
| Construcción del lock y orden de resolución | `test_locking.py` |
| Formato, compatibilidad y serialización del lockfile | `test_lockfile.py`, `test_lockfile_format.py` |
| Drift entre manifest, lock y estado materializado | `test_drift.py`, `test_projection_roundtrip.py` |
| Proyección, mount planning, materialización y unlock | `test_projection.py` |
| Familias de errores de dominio manifest/workspace | `test_errors.py` |

## Subáreas y archivos importantes

| Archivo | Qué cubre | Por qué es importante |
| --- | --- | --- |
| `test_schema.py` | parsing Pydantic, discriminadores, defaults y fixtures válidos/malformados | fija la puerta de entrada de `project.yaml` |
| `test_composition.py` | orden onion, edition coherence, overrides válidos e inválidos, reserva de `core` | garantiza rechazo temprano antes de I/O |
| `test_resolution.py` | `resolve_default_ref()` del core | evita mutaciones implícitas o defaults inconsistentes |
| `test_locking.py` | resolución de SHAs, overrides efectivos, published layers, hash `generated_from` | protege el corazón de `forge lock` |
| `test_lockfile.py` | hash canónico del manifest | estabiliza la identidad del lock |
| `test_lockfile_format.py` | schema versions, canonical JSON y round-trip byte-identical | evita roturas de compatibilidad y drift falso |
| `test_projection.py` | clasificación de roots, projection plan, workspace projection, materialized state, mount planning, unlock | protege la traducción del lock al filesystem real |
| `test_projection_roundtrip.py` | casos integrados lock + projection + drift | confirma que el circuito completo no produce falsos positivos |
| `test_drift.py` | drift estructurado y casos de no materialización o commit mismatch | asegura que `validate` reporte lo correcto |
| `test_errors.py` | jerarquía de errores del área | mantiene contratos públicos previsibles |

## Qué invariantes del sistema defiende esta suite

| Invariante | Dónde se ve con claridad |
| --- | --- |
| Un manifest inválido debe fallar antes de tocar red o filesystem | `test_composition.py`, `test_locking.py` |
| El lock debe ser determinista y canónico | `test_lockfile.py`, `test_lockfile_format.py` |
| Published layers y Git layers no son lo mismo | `test_locking.py`, `test_drift.py`, `test_projection.py` |
| El workspace materializado se interpreta por reglas del core, no por heurística del adapter | `test_projection.py` |
| El drift es un reporte estructurado, no solo texto | `test_drift.py` |
| Unlock y mount planning deben rechazar incoherencias fuertes | `test_projection.py` |

## Por qué esta suite es crítica para evolución segura

Esta suite es crítica porque concentra el valor de tres propiedades que el resto del repo asume como dadas:

1. El manifest expresa intención válida.
2. El lock congela esa intención de forma estable.
3. La comparación con el workspace materializado produce conclusiones confiables.

Si cualquiera de esas tres propiedades se degrada, el daño no queda aislado. Impacta `validate`, `lock`, `project`, `unlock`, `run` y también la credibilidad de la documentación del repo.

## Qué suele significar un fallo aquí

| Tipo de fallo | Lectura operacional habitual |
| --- | --- |
| Falla en `test_schema.py` | cambió la forma aceptada del manifest o se rompió compatibilidad |
| Falla en `test_composition.py` | una regla de coherencia ya no se aplica antes de I/O |
| Falla en `test_locking.py` | `forge lock` puede estar fijando refs o overrides de forma errónea |
| Falla en `test_lockfile_format.py` | riesgo de incompatibilidad de lockfile o drift espurio |
| Falla en `test_projection.py` | el runtime podría montar repos equivocados o aceptar evidencia inconsistente |
| Falla en `test_drift.py` / `test_projection_roundtrip.py` | `forge validate` o `run` pueden confiar en estado incorrecto |

## Cómo elegir dónde poner una prueba nueva

| Si el cambio afecta... | Agregar primero en... |
| --- | --- |
| forma del YAML o defaults del modelo | `test_schema.py` |
| reglas de negocio sobre layers, editions u overrides | `test_composition.py` |
| resolución de refs o construcción del lock | `test_locking.py` |
| serialización/compatibilidad del lock | `test_lockfile.py` o `test_lockfile_format.py` |
| roots, mounts, evidence selection, unlock o materialized state | `test_projection.py` |
| comparación manifest-lock-state | `test_drift.py` o `test_projection_roundtrip.py` |

## Checklist para maintainers

- Mantener estos tests como primera barrera para cambios puros del manifest.
- Evitar mover cobertura hacia `tests/cli/` si la semántica sigue siendo del core.
- Cuando se agregue una regla nueva de coherencia, asegurar un caso que pruebe rechazo antes de I/O.
- Si cambia la forma del lock, revisar también la compatibilidad histórica y el round-trip canónico.
- Si el cambio toca mounts o backend planning, revisar además [12-src-backend-map.md](12-src-backend-map.md) y [15-tests-adapters-map.md](15-tests-adapters-map.md).
