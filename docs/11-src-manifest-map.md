# Mapa De `src/odoo_forge/manifest/`

## Qué es este documento

Es la ficha de mantenimiento del subdirectorio `src/odoo_forge/manifest/`: explica la semántica del manifest, el lockfile, la proyección al workspace y la detección de drift.

## Por qué importa

Importa porque esta área decide qué significa `project.yaml`, qué queda fijado en `project.lock` y cómo se compara la intención declarada con el estado materializado. Si aquí se rompe una regla, el resto del sistema trabaja con una base incoherente.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras sepan qué archivos son dueños de cada parte del flujo manifest -> lock -> workspace -> drift, y no mezclen validación pura con adapters o CLI.

## Cómo ayuda al sistema

Ayuda al sistema porque preserva determinismo, trazabilidad y límites de arquitectura: el core define intención y comparación estructurada; la CLI y los adapters solo cargan datos, ejecutan side effects y presentan resultados.

## Leer después de...

Leer después de [03-src-core-map.md](03-src-core-map.md) y [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md).

## Siguiente lectura...

Seguir con [12-src-backend-map.md](12-src-backend-map.md). Para la capa de verificación específica, continuar luego con [14-tests-manifest-map.md](14-tests-manifest-map.md).

## Ruta rápida

1. Empezar aquí si el cambio toca `project.yaml`, `project.lock`, montaje de repos o validación de drift.
2. Identificar primero si el cambio pertenece a `schema`, `composition`, `locking`, `projection` o `drift`.
3. Confirmar después qué port aporta la evidencia externa necesaria.

## Qué vive en este directorio

| Archivo | Responsabilidad principal | Qué protege |
| --- | --- | --- |
| `schema.py` | Modelos Pydantic del manifest | La forma autoritativa de `project.yaml` |
| `composition.py` | Orden core -> layers -> client y chequeos de coherencia | Que el manifest sea válido antes de cualquier I/O |
| `resolution.py` | Resolución del ref por defecto del core | Coherencia entre `odoo_version` y `core.ref` |
| `locking.py` | Construcción pura del lockfile a partir del manifest y ports | Fijación determinista de refs y artifacts |
| `lockfile.py` | Tipos del lockfile y hash canónico del manifest | Persistencia estable y lectura compatible |
| `projection.py` | Plan de checkout, atribución de estado materializado, mount planning y unlock | Traducción de lock a workspace real |
| `state.py` | Modelos del estado materializado | Comparación pura contra lock |
| `drift.py` | Reportes estructurados de drift | Detección explícita de desalineaciones |
| `artifacts.py` | Tipos de artifacts publicados resueltos | Integración entre published layers y locking |
| `errors.py` | Errores tipados del dominio manifest/workspace | Fallos previsibles en CLI y tests |

## Modelo conceptual del área

| Concepto | Significado en este repo | Dónde se fija |
| --- | --- | --- |
| Schema | Intención declarada por usuarios | `schema.py` |
| Composition | Validación estructural y orden lógico del manifest | `composition.py` |
| Locking | Conversión de refs declaradas a identidades inmutables | `locking.py`, `lockfile.py` |
| Projection | Qué checkout debe existir y dónde debe montarse | `projection.py` |
| Materialized state | Evidencia ya escaneada del workspace | `state.py`, `projection.py` |
| Drift | Diferencia entre intención, lock y estado materializado | `drift.py` |

## Entrypoints clave

| Entrypoint | Qué hace | Consumido desde |
| --- | --- | --- |
| `Manifest` | Modelo raíz del manifest | CLI, tests y helpers del core |
| `compose()` | Valida coherencia antes de I/O | `validate`, `build_lock`, validaciones internas |
| `build_lock()` | Produce `Lockfile` con Git layers y published layers resueltas | comando `forge lock` |
| `compute_manifest_hash()` | Fija la identidad canónica del manifest que originó el lock | `build_lock()` y `detect_drift()` |
| `plan_projection()` | Convierte manifest + lock en pasos de checkout | comando `forge project` |
| `project_workspace()` | Orquesta los checkouts a través de `WorkspaceProvider` | comando `forge project` |
| `materialize_state()` | Traduce evidencia escaneada a `MaterializedState` | `validate` y `run` |
| `build_mount_planning_view()` | Selecciona binds autoritativos para el backend | comando `forge run` |
| `plan_unlock()` | Calcula promoción a worktree editable | comando `forge unlock` |
| `detect_drift()` | Reporta drift manifest-lock y lock-state | comando `forge validate` y validaciones del backend |

## Quién llama a esta área

| Caller entrante | Relación con `manifest/` |
| --- | --- |
| `src/odoo_forge_cli/main.py::validate` | Parsea manifest, carga lock, escanea workspace, materializa estado y llama a `detect_drift()` |
| `src/odoo_forge_cli/main.py::lock` | Construye el lock mediante `build_lock()` |
| `src/odoo_forge_cli/main.py::project` | Usa `plan_projection()` y `project_workspace()` |
| `src/odoo_forge_cli/main.py::unlock` | Usa `plan_unlock()` para promover repos |
| `src/odoo_forge_cli/main.py::run` | Usa `materialize_state()` y `build_mount_planning_view()` antes del planning del backend |
| `src/odoo_forge/backend/plan.py` | Consume la vista de mounts y modelos derivados de manifest para planificar runtime |

## Dependencias salientes

| Dependencia saliente | Para qué se usa | Regla importante |
| --- | --- | --- |
| `SourceProvider` | Resolver `url` + `ref` a commit SHA | `locking.py` depende del port, nunca del adapter Git |
| `PublishedArtifactResolver` | Resolver layers `published` a digests inmutables | El core no debe aprender detalles de GHCR o Docker |
| `WorkspaceProvider` | Checkout, scan y promote | `projection.py` orquesta con el port, no ejecuta Git |
| `backend/plan.py` | Consume mount planning ya validado | La planificación del runtime depende de evidencia manifest coherente |

## Dónde se toman las decisiones delicadas

| Subárea | Decisión crítica | Riesgo si se cambia mal |
| --- | --- | --- |
| `schema.py` | Qué se acepta como manifest válido | Fixtures, validación CLI y hashing dejan de ser compatibles |
| `composition.py` | Qué incoherencias se rechazan antes de I/O | Puede ejecutarse red o filesystem con manifests inválidos |
| `locking.py` | Qué queda fijado y en qué orden | El lock pierde determinismo o resuelve repos equivocados |
| `lockfile.py` | Compatibilidad entre versiones de lock y hash estable | Se rompen round-trips y drift falso |
| `projection.py` | Cómo se atribuye evidencia de scan a mounts reales | El backend monta repos equivocados o acepta evidencia inconsistente |
| `drift.py` | Qué diferencias se consideran drift y cómo se reportan | El sistema puede declarar limpio un estado roto, o viceversa |

## Estado materializado y proyección

`MaterializedState` no lee disco. Representa hechos ya escaneados por `WorkspaceProvider.scan()` y luego reinterpretados por `materialize_state()`.

Esto importa porque `manifest/` separa dos cosas distintas:

1. La evidencia cruda del adapter.
2. El significado autoritativo de esa evidencia dentro del dominio.

`build_mount_planning_view()` es el punto donde esa separación se vuelve operativa: valida estructura, deriva identidad `(layer, repo)`, decide si gana un worktree o un checkout read-only y rechaza incoherencias antes de que el backend intente levantar contenedores.

## Qué se rompe si esta área se entiende mal

| Malentendido | Qué se rompe en la práctica |
| --- | --- |
| Confundir `compose()` con resolución externa | Se agregan side effects a una fase que debe seguir siendo pura |
| Tratar el lock como una copia informal del manifest | Se pierde la función de fijar SHAs y digests inmutables |
| Asumir que `materialize_state()` escanea disco por sí misma | Se mezcla lógica de atribución con trabajo del adapter |
| Ignorar el chequeo estructural de `build_mount_planning_view()` | El backend puede montar rutas incoherentes o evidencia inesperada |
| Reducir el drift a un string de UI | Se pierde estructura testeable y clasificación tipada |
| Tocar orden o serialización del lock sin pensar en hash/canonical JSON | Aparecen drifts falsos, incompatibilidades y roturas de round-trip |

## Checklist para maintainers

- Mantener el área libre de imports a adapters, Docker, Git o CLI.
- Rechazar incoherencias antes de cualquier I/O siempre que la información ya esté en el manifest.
- Conservar el carácter estructurado de `DriftEntry`, `Lockfile` y `MaterializedState`.
- Verificar `tests/manifest/` antes de asumir que un cambio es solo de parseo o formato.
- Si cambia el efecto visible sobre runtime, revisar también [12-src-backend-map.md](12-src-backend-map.md) y [14-tests-manifest-map.md](14-tests-manifest-map.md).
