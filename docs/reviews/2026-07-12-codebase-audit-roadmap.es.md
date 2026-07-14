# Resultado de la auditoría del código base y hoja de ruta ordenada por riesgo

> **Nota de traducción:** Esta es la traducción al español para lectura. El documento en inglés
> continúa siendo la fuente técnica.

La revisión acotada de todo el código base aprobó el objetivo inmutable sin bloqueos ni
correcciones obligatorias. Admitió cinco hallazgos INFO/WARNING respaldados por evidencia: un posible
límite de exposición de credenciales, una preocupación reclasificada sobre autoridad del ciclo de vida,
dos problemas semánticos con los plazos de Docker y un problema de coherencia en los diagnósticos de
la CLI. Estos hallazgos pueden corregirse mediante cambios específicos y revisiones ordinarias; la
severidad WARNING o INFO **no** justifica automáticamente un Judgment Day.

El orden recomendado es: primero el límite de seguridad, segundo la conformidad del futuro almacén,
tercero la semántica de plazos, cuarto la legibilidad de la CLI, luego las tres unidades de defectos
reveladas por la caracterización y, por último, la caracterización residual sin defectos. Un Judgment Day opcional entre módulos queda condicionado a
que finalice todo el trabajo acotado y solo se justifica si el delta inmutable combinado genera un
riesgo de integración extraordinario.

## Línea base de la revisión

| Elemento | Valor inmutable |
| --- | --- |
| Rama y commit | `main` en `e149f2b194aa9e1f0c8463ef41c300be0a333314` |
| Árbol de trabajo | Limpio al inicio y al finalizar la revisión |
| Linaje | `review-full-head-e149f2b194aa` |
| Identidad del objetivo | `sha256:1bddc31549d659583ae6f1462dc909fd516677f0729982e113dd1a1b445296f9` |
| Alcance | Árbol completo: 337 archivos, 36,627 líneas |
| Política de revisión | Nivel alto, revisión 4R ordinaria y acotada |
| Recibo | `.git/gentle-ai/review-transactions/v2/review-full-head-e149f2b194aa/review-receipt.json` |
| Estado terminal | Aprobado |

La revisión nativa de nivel alto aplicó las cuatro perspectivas al objetivo completo. El mapa de
enfoque profundo solicitado por el usuario priorizó la fiabilidad de `src/odoo_forge` core/domain,
la resiliencia de `odoo_forge_docker` y `odoo_forge_git`, el riesgo de `odoo_forge_registry`,
`odoo_forge_workspace` y `factory`, y la legibilidad de `odoo_forge_cli`.

La verificación se completó correctamente en el objetivo revisado:

- Import Linter: se mantuvieron 6 contratos.
- Ruff: se completaron correctamente las verificaciones de check y format.
- mypy: 104 archivos superados.
- pytest: 475 pruebas superadas, 1 deseleccionada, 98% de cobertura.

## Resumen de hallazgos

| ID | Problema | Evidencia | Clasificación | Hoja de ruta |
| --- | --- | --- | --- | --- |
| `R1-001` | Los errores del espacio de trabajo pueden exponer credenciales procedentes del stderr sin procesar de Git | `src/odoo_forge_workspace/provider.py:141`, `src/odoo_forge_workspace/provider.py:203-206` | Inferencial; causalidad desconocida | Unidad de trabajo 1 |
| `R3-001` | La auditoría cuestionó la construcción directa de `CLOSED` con limpieza residual; la materialización de confianza la permite deliberadamente | `src/odoo_forge/ports/durable_operation_store.py:16-20`, `:34-51`, `:96-110`; `tests/ports/test_durable_operation_store.py:306-367` | Reclasificado: no requiere actuación en el modelo de valores actual del núcleo | Unidad de trabajo 2 |
| `R4-001` | El sondeo de PostgreSQL puede superar considerablemente su tiempo de espera de disponibilidad | `src/odoo_forge_docker/provider.py:386-388`, tiempo de espera de invocación en `src/odoo_forge_docker/provider.py:448` | Determinista; causalidad desconocida | Unidad de trabajo 3 |
| `R4-002` | El sondeo de salud de Odoo puede superar considerablemente `health_wait_timeout` | `src/odoo_forge_docker/provider.py:402-404`, tiempo de espera de invocación en `src/odoo_forge_docker/provider.py:448` | Determinista; causalidad desconocida | Unidad de trabajo 3 |
| `R2-001` | `stop`, `logs` y `exec` emiten errores de Pydantic multilínea sin procesar | `src/odoo_forge_cli/main.py:519`, capturas en `src/odoo_forge_cli/main.py:546`, `:570` y `:603` | Determinista; introducido | Unidad de trabajo 4 |

No se admitió ningún hallazgo para `odoo_forge_git`, `odoo_forge_registry` ni `factory` durante la
revisión original. La caracterización posterior reprodujo un defecto en el límite de fallos seguro
respecto a credenciales de cada adaptador y un defecto de limpieza de secretos temporales en factory.
El usuario autorizó dividir la anterior unidad de trabajo 5 en cuatro unidades acotadas el 2026-07-12;
son descubrimientos, no correcciones completadas.

## Puertas de decisión

| Puerta | Decisión |
| --- | --- |
| G0: integridad de la línea base | Antes de cada unidad, registrar el commit/árbol inicial y confirmar que los cambios no relacionados quedan excluidos de su evidencia. |
| G1: comportamiento de credenciales | Si una muestra reproducible del stderr de Git puede exponer información de usuario o tokens, tratar la ocultación como un límite de seguridad y completar la unidad de trabajo 1 antes que todas las demás. Aunque no sea reproducible, aplicar el contrato seguro de errores públicos porque stderr no es de confianza. |
| G2: autoridad del ciclo de vida | Mantener la coherencia de snapshots en `DurableOperationRecord.__post_init__` y la autoridad de transición en `DurableOperationStore.resolve_residual`. Aplicar el requisito de transición persistida cuando se adopte el primer almacén duradero concreto. |
| G3: contrato de plazos | Definir si los valores configurados de disponibilidad son plazos de reloj de pared o presupuestos de intentos. Proceder solo después de que las pruebas codifiquen un contrato para PostgreSQL y Odoo. |
| G4: contrato de diagnóstico | Conservar la ubicación del campo y el mensaje al tiempo que se aplica una salida estable y de una sola línea en la CLI para todas las rutas de validación del manifiesto. |
| G5: caracterización sin hallazgos | Añadir pruebas únicamente para límites concretos de alto riesgo que aún no estén caracterizados; no inventar hallazgos ni refactorizaciones amplias. |
| G6: revisión extraordinaria | Ejecutar Judgment Day únicamente si el delta agregado posterior a las correcciones cruza la semántica de seguridad, ciclo de vida y límites de procesos de un modo que las revisiones ordinarias específicas no puedan aislar con confianza. En caso contrario, finalizar con una revisión de integración ordinaria. |

## Unidades de trabajo ordenadas por dependencias

### 1. Aplicar el límite de ocultación de credenciales del espacio de trabajo

**Hallazgo:** `R1-001`

**Objetivo:** Garantizar que ningún diagnóstico sin procesar de Git pueda exponer credenciales
incluidas en una URL remota mediante `WorkspaceError` o la salida de la CLI, conservando a la vez
suficiente contexto seguro para diagnosticar el subcomando de Git que falló.

| Campo de planificación | Límite |
| --- | --- |
| Archivos probables | `src/odoo_forge_workspace/provider.py`; `tests/adapters/test_workspace_provider.py`; pruebas pertinentes de proyección de la CLI solo si el límite público requiere una demostración de extremo a extremo |
| Pruebas y evidencia | Simular stderr de clone que contenga información de usuario HTTPS, valores similares a tokens y una URL con credenciales; comprobar que las excepciones y el stderr de la CLI no contienen ninguno de esos elementos. Cubrir stderr ordinario sin secretos para demostrar que el diagnóstico seguro sigue siendo útil. |
| Criterios de salida | Cada fallo de subproceso del espacio de trabajo emite un mensaje público acotado y sin credenciales; las rutas de tiempo de espera y salida distinta de cero comparten la política; se superan las pruebas específicas del adaptador y la CLI. |
| Límite de reversión | Revertir únicamente el saneamiento de diagnósticos del espacio de trabajo y sus pruebas. El checkout, el reemplazo atómico, el análisis y la promoción permanecen sin cambios. |
| Modo de revisión | Revisión de seguridad ordinaria y específica. Escalar a un Judgment Day explícito solo si la corrección introduce una primitiva de ocultación compartida utilizada en varios adaptadores que manejan credenciales o cambia el modelo público de errores. |

**Finalización y evidencia (2026-07-12):**

- Se modificaron `src/odoo_forge_workspace/provider.py`, `tests/adapters/test_workspace_provider.py` y `tests/cli/test_project.py`.
- El stderr sin procesar de Git y los argv con credenciales ya no cruzan los límites de `CheckoutError`, `WorkspaceError` ni la CLI. La causa y el contexto de las excepciones de tiempo de espera, así como los tracebacks formateados, no contienen secretos; los diagnósticos acotados del subcomando junto con el código de salida o el tiempo de espera siguen siendo útiles.
- Verificación específica: 26 pruebas superadas. Verificación completa: 478 pruebas superadas, 1 deseleccionada; Ruff, mypy y la comprobación del diff se completaron correctamente.
- Harness de ejecución: N/A; las pruebas deterministas de límites del adaptador de subprocesos y la CLI aportan la evidencia del límite de ejecución.
- El INFO `R3-001` de la revisión inicial de la implementación identificó una filtración mediante la causa del tiempo de espera; el seguimiento la resolvió antes de la revisión final.
- Revisión final: linaje `review-c6d10eb0f723761a`, aprobado sin hallazgos. Recibo: `.git/gentle-ai/review-transactions/v2/review-c6d10eb0f723761a/review-receipt.json`.

Esta unidad va primero porque el trabajo posterior de diagnóstico no debe normalizar ni reutilizar
una carga de error insegura. Su contrato de errores públicos es una entrada para la unidad de trabajo
4.

### 2. Exigir un cierre residual conforme en el primer almacén duradero

**Hallazgo:** `R3-001`

**Estado:** Reclasificado — sin cambio de código actual.

**Reclasificación:** La auditoría planteó una pregunta legítima sobre cómo demostrar la transición,
pero la corrección propuesta para el modelo del núcleo era un falso positivo.
`DurableOperationRecord` es un valor de snapshot utilizado para carga persistente de confianza y
reproducción, por lo que la materialización directa con `lifecycle=CLOSED` e historial de limpieza
residual es deliberadamente válida. La coherencia del snapshot corresponde a
`DurableOperationRecord.__post_init__`; la autoridad de transición corresponde a
`DurableOperationStore.resolve_residual`. Como actualmente no existe ningún adaptador de almacén
duradero concreto en producción, no hay una ruta de transición persistida explotable que corregir.
Por tanto, `R3-001` no requiere actuación en el modelo de valores actual del núcleo.

**Requisito futuro:** El primer almacén duradero concreto debe implementar `resolve_residual` como
única transición persistida y atómica de `CLEANUP_REQUIRED` a `CLOSED`. Debe usar compare-and-swap,
incrementar la revisión, conservar el bundle terminal exacto y rechazar registros ausentes,
registros terminales sin residuos, registros ya cerrados y conflictos de revisión. La construcción
directa sigue siendo válida durante la materialización de confianza y la reproducción.

| Campo de planificación | Límite |
| --- | --- |
| Evidencia actual | `src/odoo_forge/ports/durable_operation_store.py:16-20`, `:34-51`, `:96-110`; `tests/ports/test_durable_operation_store.py:306-367`; `openspec/changes/archive/2026-07-14-CAP-DURABLE-OPERATIONS-RECORD-FIX/design.md:65-74`, `:228` |
| Pruebas de adopción | Para el primer almacén concreto, demostrar el CAS atómico de `CLEANUP_REQUIRED` a `CLOSED`, el incremento de revisión, la conservación exacta del bundle terminal y el rechazo de registros ausentes, terminales sin residuos, ya cerrados y con conflictos de revisión. Demostrar también que la carga/reproducción de confianza acepta registros cerrados con historial residual materializados directamente. |
| Criterios de salida | No hay criterios de salida de implementación actuales. La futura adopción del almacén solo estará completa cuando las escrituras persistidas tengan una única autoridad de transición y los snapshots materializados conserven el contrato de coherencia actual. |
| Límite de reversión | N/A para el núcleo actual. Un futuro cambio de adaptador debe mantener su implementación, pruebas de conformidad y migración de persistencia, si existe, en una unidad que pueda revertirse con seguridad. |
| Modo de revisión | Revisión ordinaria y específica de adopción del almacén. Una procedencia persistida fuerte es una bifurcación arquitectónica independiente que requiere decisiones de esquema y reproducción, política de migración y Judgment Day; no recomendarla de forma predeterminada. |

Esta unidad reclasificada registra una puerta de conformidad para la futura adopción de un almacén;
no bloquea el trabajo actual de Docker ni de la CLI.

**Deuda independiente de la hoja de ruta:** El delta fusionado en
`openspec/changes/CAP-DURABLE-OPERATIONS-RECORD-FIX/specs/durable-operations/spec.md` parece no estar
todavía sincronizado con `openspec/specs/durable-operations/spec.md`. Esto requiere confirmación
independiente y sincronización de archivado. No constituye evidencia de que `R3-001` sea válido, y
esta actualización de la hoja de ruta no modifica archivos de OpenSpec.

### 3. Dar a la disponibilidad de Docker un único contrato de plazos

**Hallazgos:** `R4-001`, `R4-002`

**Objetivo:** Hacer que las esperas de disponibilidad de PostgreSQL y de salud de Odoo respeten
plazos explícitos de reloj de pared, incluido el tiempo empleado dentro de cada invocación de la CLI
de Docker y en las pausas.

| Campo de planificación | Límite |
| --- | --- |
| Archivos probables | `src/odoo_forge_docker/provider.py`; `tests/adapters/test_docker_provider.py`; pruebas temporales de integración solo si las pruebas unitarias deterministas no pueden demostrar el comportamiento del daemon |
| Pruebas y evidencia | Usar un reloj monotónico inyectado y un comportamiento controlado de subprocesos para cubrir invocaciones lentas, presupuestos fraccionarios, presupuestos nulos/breves, intentos finales y truncamiento de pausas. Demostrar que ambas puertas comparten la misma semántica de plazos y conservan los errores de tiempo de espera tipados y la reversión. |
| Criterios de salida | El tiempo transcurrido está acotado por el plazo configurado de la puerta más una tolerancia documentada de planificación/terminación de procesos; ningún sondeo recibe un tiempo de espera mayor que el presupuesto restante; se superan las pruebas del adaptador. |
| Límite de reversión | Revertir el bucle de disponibilidad/cálculo de plazos y sus pruebas sin modificar la creación de contenedores, la inyección de credenciales, los diagnósticos ni el orden de reversión. |
| Modo de revisión | Revisión de resiliencia ordinaria y específica. Judgment Day no se justifica para cambios aislados en bucles de plazos; reconsiderarlo solo si la implementación altera las garantías de reversión o la semántica general de subprocesos. |

Tratar ambos problemas como una sola unidad de trabajo porque los dos defectos surgen del mismo
desajuste entre el recuento de intentos y el tiempo de espera independiente por invocación.
Corregirlos por separado duplicaría la política y permitiría divergencias semánticas.

**Finalización y evidencia (2026-07-12):**

- Se modificaron `src/odoo_forge_docker/provider.py` y `tests/adapters/test_docker_provider.py`.
- La disponibilidad de PostgreSQL y la salud de Odoo utilizan ahora una política compartida de plazos basada en un reloj monotónico. La duración de los sondeos y las pausas consume el presupuesto configurado, y el tiempo de espera de cada subproceso queda limitado al presupuesto positivo restante.
- Los plazos agotados omiten el subproceso en lugar de invocarlo con `timeout=0` y devuelven el error tipado específico de la puerta de disponibilidad. Un tiempo de espera real de Docker mientras aún queda presupuesto positivo continúa devolviendo `DockerUnavailableError`.
- La revisión inicial identificó un hallazgo INFO sobre la clasificación de `timeout=0`; el seguimiento eliminó los sondeos finales sin sentido y con presupuesto nulo, y lo resolvió antes de la revisión final.
- Verificación específica final: 12 pruebas superadas, 58 deseleccionadas. Verificación del adaptador: 70 pruebas superadas. Verificación completa: 490 pruebas superadas, 1 deseleccionada, 98% de cobertura. Ruff, mypy y la comprobación del diff se completaron correctamente.
- Harness de ejecución: N/A; las pruebas deterministas con reloj y comportamiento de subprocesos inyectados demuestran el límite de plazos sin requerir un daemon de Docker activo.
- Revisión final: linaje `review-82b5faa3aa182019`, aprobado sin hallazgos. Recibo: `.git/gentle-ai/review-transactions/v2/review-82b5faa3aa182019/review-receipt.json`.

### 4. Normalizar los diagnósticos de validación de la CLI

**Hallazgo:** `R2-001`

**Objetivo:** Hacer que `stop`, `logs` y `exec` informen los fallos de validación de Pydantic con el
mismo contrato de diagnóstico orientado a campos y de una sola línea que utilizan `validate`,
`lock`, `project`, `unlock`, `run` y `status`.

| Campo de planificación | Límite |
| --- | --- |
| Archivos probables | `src/odoo_forge_cli/main.py`; `tests/cli/test_backend.py`; un pequeño auxiliar compartido para pruebas de la CLI solo si ya se ajusta a las convenciones del proyecto |
| Pruebas y evidencia | Invocar cada comando afectado con un manifiesto no válido; comprobar el código de salida 1, una línea estable `error: <field>: <message>` por cada error de validación, que no haya traceback ni representación multilínea sin procesar de Pydantic. Volver a ejecutar las pruebas existentes de límites de error de los comandos. |
| Criterios de salida | Todos los comandos que consumen manifiestos exponen un formato de validación coherente y el comportamiento existente de errores de backend/dominio permanece sin cambios. |
| Límite de reversión | Revertir únicamente la representación de errores de validación de los tres comandos y sus pruebas; la derivación de identidad del backend y las llamadas a proveedores permanecen intactas. |
| Modo de revisión | Revisión de legibilidad ordinaria y específica. Judgment Day no se justifica. |

Esta unidad depende de la política segura de errores públicos de la unidad de trabajo 1, pero no
depende de los detalles de implementación del ciclo de vida ni de Docker.

**Finalización y evidencia (2026-07-12):**

- Se modificaron `src/odoo_forge_cli/main.py` y `tests/cli/test_backend.py`.
- Se añadió un único representador interno de errores de validación y se aplicó de forma coherente en los límites de validación del manifiesto de `stop`, `logs` y `exec`.
- Los manifiestos no válidos ahora terminan con código 1 y errores estables, orientados a campos y de una sola línea. Los valores rechazados y secretos, las representaciones multilínea sin procesar de Pydantic, los tracebacks y la construcción del proveedor de backend no cruzan estos límites.
- Los límites existentes de `ManifestError` y `BackendError`, el comportamiento correcto y la propagación del código de salida de `exec` permanecen sin cambios.
- TDD RED: 3 pruebas fallidas. GREEN específico: 3 pruebas superadas. Verificación de la CLI de backend: 32 pruebas superadas. Verificación completa de la CLI: 78 pruebas superadas. Verificación completa: 493 pruebas superadas, 1 deseleccionada. Ruff, mypy y la comprobación del diff se completaron correctamente.
- Harness de ejecución: N/A; el runner de la CLI de Typer ejercita el límite de presentación.
- Revisión final: linaje `review-192994a7729f5a11`, aprobado sin hallazgos. Recibo: `.git/gentle-ai/review-transactions/v2/review-192994a7729f5a11/review-receipt.json`.

### 5. Aplicar el límite de fallos de Git seguro respecto a credenciales

**Descubrimiento:** La caracterización reprodujo exposición de secretos mediante superficies de
fallo de Git.

**Objetivo:** Garantizar que las URL sin procesar con credenciales, stderr, atributos de error,
causas `TimeoutExpired`/`FileNotFoundError` y tracebacks formateados no puedan exponer secretos,
conservando la clasificación de ref/autenticación/red/no encontrado y diagnósticos útiles y acotados.

| Campo de planificación | Límite |
| --- | --- |
| Producción y pruebas | `src/odoo_forge_git/git_provider.py`; `tests/adapters/test_git_provider.py` |
| Pruebas y evidencia | Ejercitar fallos con URL y stderr que contengan credenciales, atributos de errores públicos, cadenas de causas por tiempo de espera y binario ausente, y tracebacks formateados. Comprobar que no sobrevive ningún secreto y que cada clase de fallo existente y el contexto acotado sin secretos siguen siendo útiles. |
| Criterios de salida | Todas las superficies de fallo de Git enumeradas son seguras respecto a credenciales; la clasificación de ref/autenticación/red/no encontrado permanece estable; se superan las pruebas específicas. |
| Límite de reversión | Revertir únicamente el saneamiento de fallos de Git y sus pruebas específicas; la semántica de las operaciones Git permanece sin cambios. |
| Modo de revisión | Revisión de seguridad ordinaria y específica. Sin Judgment Day salvo que el cambio altere un modelo público de errores compartido entre adaptadores. |

**Finalización y evidencia (2026-07-12):**

- Se modificaron `src/odoo_forge_git/git_provider.py` y `tests/adapters/test_git_provider.py`.
- Se sanea la información de usuario de HTTP(S), de URI arbitrarios, incluido `ssh://`, y de remotos con formato scp. Los remotos malformados con forma de credencial se convierten en un marcador de ocultación acotado.
- El stderr sin procesar se sustituye por diagnósticos acotados. Los atributos públicos, strings, tracebacks, causas y contextos no contienen secretos, mientras que se conservan el contexto útil de host/ruta y los errores tipados de referencia no encontrada, autenticación y red. Las pruebas también demuestran el contrato no interactivo de los subprocesos.
- RED inicial de TDD: 3 pruebas fallidas, 17 superadas. RED final de seguimiento: 5 pruebas fallidas, 22 superadas. Verificación específica final: 27 pruebas superadas. Verificación de adaptadores/CLI: 213 pruebas superadas, 1 deseleccionada. Verificación completa: 503 pruebas superadas, 1 deseleccionada. Ruff, format, mypy, los contratos de importación y la comprobación del diff se completaron correctamente.
- Harness de ejecución: N/A; las pruebas con mocks del límite de subprocesos aportan la evidencia del límite de ejecución.
- El INFO `R3-001` de la revisión inicial identificó una filtración de información de usuario en URI no HTTP; el seguimiento la resolvió antes de la revisión final.
- Revisión final: linaje `review-0d8d94269a7b724d`, aprobado sin hallazgos. Recibo: `.git/gentle-ai/review-transactions/v2/review-0d8d94269a7b724d/review-receipt.json`.

### 6. Aplicar el límite de fallos del registro seguro respecto a credenciales

**Descubrimiento:** La caracterización reprodujo exposición de secretos mediante superficies de
fallo del registro.

**Objetivo:** Garantizar que referencias sin procesar, stderr, errores anidados de publicación/pull,
causas por tiempo de espera y binario ausente, y tracebacks formateados no puedan exponer secretos,
conservando la precedencia de autenticación sobre no encontrado, `exists` falso solo para no
encontrado genuino y la inmutabilidad del digest.

| Campo de planificación | Límite |
| --- | --- |
| Producción y pruebas | `src/odoo_forge_registry/provider.py`; errores/referencia compartidos del registro solo si es necesario; `tests/adapters/test_registry_provider.py` |
| Pruebas y evidencia | Ejercitar referencias y stderr con credenciales en rutas de publicación, pull, exists, tiempo de espera y binario ausente, incluidos errores anidados y tracebacks formateados. Demostrar el saneamiento sin debilitar la clasificación ni las garantías del digest. |
| Criterios de salida | Todas las superficies de fallo del registro enumeradas son seguras respecto a credenciales; la precedencia de autenticación, el comportamiento de `exists` para no encontrado genuino y la inmutabilidad del digest permanecen estables; se superan las pruebas específicas. |
| Límite de reversión | Revertir únicamente el saneamiento de fallos del registro y sus pruebas específicas; la referencia y los errores compartidos cambian solo si el límite lo requiere. |
| Modo de revisión | Revisión de seguridad ordinaria y específica. Judgment Day solo ante una ruptura del modelo de errores compartido o del puerto. |

**Finalización y evidencia (2026-07-12):**

- Se modificaron `src/odoo_forge/image_registry/errors.py`, `src/odoo_forge_registry/provider.py` y `tests/adapters/test_registry_provider.py`.
- Las referencias que contienen información de usuario se rechazan antes de ejecutar el subproceso. El stderr sin procesar, los fallos anidados de publicación/pull, los tiempos de espera, los binarios ausentes y el JSON malformado exponen ahora diagnósticos seguros y acotados; los atributos públicos, strings, tracebacks, causas y contextos permanecen sin secretos.
- Se conserva la precedencia de autenticación sobre no encontrado, y `exists` devuelve falso únicamente para respuestas genuinas de no encontrado. Los desajustes de digest tras una operación correcta generan un `RegistryDigestMismatchError` acotado sin exponer ninguno de los digests; los errores de autenticación y de indisponibilidad continúan propagándose, mientras que la inmutabilidad del digest y el comportamiento de GHCR permanecen intactos.
- RED inicial de TDD: 5 pruebas fallidas. Verificación específica final: 27 pruebas superadas. Verificación pertinente: 187 pruebas superadas, 1 deseleccionada. Verificación completa: 513 pruebas superadas, 1 deseleccionada. Todas las puertas de calidad se completaron correctamente.
- Harness de ejecución: N/A; las pruebas con mocks del límite de subprocesos aportan la evidencia del límite de ejecución.
- El hallazgo INFO de la revisión inicial identificó una confusión entre desajuste y ausencia del digest; el seguimiento la resolvió antes de la revisión final.
- Revisión final: linaje `review-9323fdde84c3b849`, aprobado sin hallazgos. Recibo: `.git/gentle-ai/review-transactions/v2/review-9323fdde84c3b849/review-receipt.json`.
- No se ha creado ningún commit ni pull request para esta unidad de trabajo.

### 7. Garantizar la limpieza del secreto temporal de factory

**Descubrimiento:** La caracterización reprodujo una limpieza incompleta del archivo de contraseña
en texto plano de respaldo.

**Objetivo:** Garantizar que el archivo de contraseña en texto plano de respaldo tenga modo `0600` y
se elimine tras éxito o fallo de disponibilidad, y ante señal/terminación donde lo permita el control
del shell, conservando el paso mediante ruta de archivo y evitando texto plano en argv o logs.

| Campo de planificación | Límite |
| --- | --- |
| Producción y pruebas | `factory/entrypoint.sh`; harness de shell específico; smoke de imagen solo si es necesario |
| Pruebas y evidencia | Ejercitar el modo del archivo y la limpieza tras éxito o fallo de disponibilidad y en rutas controlables de señal/terminación. Comprobar que los secretos siguen basados en archivo y ausentes de argv y logs. |
| Criterios de salida | El archivo de respaldo tiene modo `0600`, se limpia en todas las rutas de salida controlables por el shell, se conserva el paso existente mediante ruta de archivo y se supera el harness específico. |
| Límite de reversión | Revertir únicamente la creación/limpieza local del archivo de respaldo y su harness; la arquitectura de credenciales del contenedor permanece sin cambios. |
| Modo de revisión | Revisión de alto riesgo porque factory es shell/runtime sensible para la seguridad. Usar Judgment Day solo si el cambio cruza la arquitectura de credenciales del contenedor en lugar de limitarse a la limpieza local. |

**Finalización y evidencia (2026-07-12):**

- Se modificaron `factory/entrypoint.sh` y `factory/tests/test-entrypoint-temp-secret-cleanup.sh`.
- El archivo de respaldo propiedad del proceso tiene modo `0600`, se pasa únicamente mediante su ruta y nunca expone texto plano en argv ni logs. La limpieza es idempotente tras éxito o fallo de disponibilidad y ante `TERM`, conserva el estado del comando y nunca elimina un archivo de secreto propiedad del llamador.
- El reenvío de argumentos seguro ante metacaracteres y el despacho de comandos permanecen intactos.
- RED de TDD: el archivo de respaldo permanecía tras la disponibilidad. Harness de ejecución GREEN: 4 escenarios superados. Pruebas de factory: 16 aserciones superadas. ShellCheck se completó correctamente. Verificación de Python: 513 pruebas superadas, 1 deseleccionada. Todas las puertas de calidad se completaron correctamente.
- El smoke de imagen no estuvo disponible porque Docker no está instalado; esta limitación del entorno sigue sin verificarse mediante una ejecución a nivel de imagen.
- Revisión final: linaje `review-921022ea4df4f21d`, aprobado sin hallazgos. Recibo: `.git/gentle-ai/review-transactions/v2/review-921022ea4df4f21d/review-receipt.json`.
- No se ha creado ningún commit ni pull request para esta unidad de trabajo.

### 8. Caracterizar los límites residuales sin defectos

**Alcance:** Aserciones ausentes para límites de Git, registro y factory, extrayendo cualquier
defecto reproducido como una subunidad correctiva canónica independiente.

| Campo de planificación | Límite |
| --- | --- |
| Producción y pruebas | Solo pruebas específicas o harness de shell; sin cambios de producción |
| Pruebas y evidencia | Añadir únicamente aserciones ausentes para comportamiento ya correcto y registrar el riesgo que cierra cada aserción. |
| Criterios de salida | Los límites residuales seleccionados tienen evidencia concisa y satisfactoria; no se incluyen cambios de comportamiento de producción. |
| Límite de reversión | Revertir las aserciones de caracterización de forma independiente por área. |
| Modo de revisión | Revisión ordinaria y específica. Cualquier otro defecto reproducible se convierte en una unidad de trabajo canónica independiente. |

**Finalización y evidencia (2026-07-12):**

- La caracterización del registro demuestra el comportamiento compartido de subprocesos y los contratos canónicos de digest. La caracterización de factory demuestra el cableado del Dockerfile y del entorno de ejecución, incluido el `USER odoo` efectivo final.
- La caracterización del registro superó 30 pruebas; la de factory superó 2 pruebas; la verificación completa superó 518 pruebas con 1 deseleccionada.
- La revisión inicial informó un INFO por una debilidad en la aserción del usuario efectivo. La aserción se reforzó antes de la revisión final.
- Revisión final: linaje `review-final-registry-factory-20260712`, aprobado sin hallazgos. Recibo: `.git/gentle-ai/review-transactions/v2/review-final-registry-factory-20260712/review-receipt.json`.
- La caracterización satisfactoria de Registry/Factory se confirmó posteriormente en `81f90fd` (`test(registry-factory): characterize provider and image wiring`).
- El smoke de imagen Docker sigue sin estar disponible localmente, por lo que el límite de ejecución a nivel de imagen no está verificado en este entorno.

#### 8.1. Corregir la clasificación de referencias remotas de Git

La caracterización de Git reprodujo un defecto nuevo en lugar de ocultarlo dentro de la
caracterización satisfactoria: el diagnóstico estándar `fatal: couldn't find remote ref` se
clasificaba como `NetworkError`. Se extrajo como una subunidad correctiva canónica.

- La implementación se ancla en el diagnóstico estable y devuelve `RefNotFoundError`. Se conservan la precedencia de autenticación, el fallback de red y los fallos públicos seguros respecto a credenciales.
- Verificación: matriz de clasificación, 6 pruebas superadas; Git, 33; adaptadores/CLI, 41; verificación completa, 524 pruebas superadas y 1 deseleccionada.
- Revisión final: linaje `review-e4d66c58962320de`, aprobado sin hallazgos. Recibo: `.git/gentle-ai/review-transactions/v2/review-e4d66c58962320de/review-receipt.json`.
- La corrección está implementada, pero no se ha confirmado en un commit en el momento de actualizar esta hoja de ruta.

La caracterización residual está completa después de extraer y corregir este defecto, con la
salvedad de la limitación local del smoke de imagen Docker indicada anteriormente.

### 9. Juicio opcional de integración entre módulos

**Estado:** No iniciado ni autorizado por esta hoja de ruta. No se ha realizado ningún Judgment Day.

**Objetivo:** Utilizar un juicio adversarial doble únicamente si el delta agregado completo presenta
un riesgo extraordinario entre módulos que no pueda revisarse adecuadamente como las unidades
acotadas anteriores.

El objetivo inmutable concreto debe crearse en la puerta G6 del siguiente modo: inmovilizar el árbol
candidato de Git exacto que contenga únicamente los resultados aceptados de las unidades de trabajo
1-8, registrar su ID de árbol completo de 40 caracteres, registrar un resumen SHA-256 de la lista
ordenada de rutas y bytes de archivos, y vincular ambos valores al commit de línea base sin cambios
`e149f2b194aa9e1f0c8463ef41c300be0a333314`. Ambos jueces ciegos deben recibir ese mismo objetivo,
alcance, rutas de skills resueltas y criterios. Un nombre de rama cambiante o un directorio de
trabajo no constituyen un objetivo válido.

Judgment Day es extraordinario aquí solo si el delta agregado acopla la ocultación de credenciales,
la autoridad del ciclo de vida duradero, el comportamiento de tiempo de espera/reversión de Docker y
la presentación de errores de la CLI de manera que una sola regresión pueda escapar de las revisiones
aisladas. El tamaño por sí solo y la presencia de hallazgos WARNING/INFO son razones insuficientes.

Ambos jueces ciegos y de solo lectura evalúan los mismos criterios:

1. Ningún material de credenciales puede cruzar los límites de adaptadores, errores de dominio, registros o CLI.
2. Todo almacén duradero concreto hace de `resolve_residual` la única transición persistida y atómica a `CLOSED`, mientras que la materialización/reproducción de confianza sigue siendo válida y auditable.
3. Los plazos de disponibilidad de Docker están acotados sin debilitar la reversión ni la clasificación de errores.
4. La normalización de la CLI conserva los códigos de salida, el contexto de los campos y los diagnósticos ajenos a la validación.
5. Las superficies de fallo de Git y del registro conservan las garantías de clasificación e integridad sin exponer credenciales.
6. La limpieza de secretos temporales de factory conserva el paso de credenciales mediante archivo y elimina los archivos en texto plano en las salidas controlables por el shell.
7. El delta combinado no introduce regresiones graves en los límites de arquitectura, la seguridad de reproducción ni la recuperación ante fallos.

Iniciar y persistir una transacción nativa `judgment_day` para el objetivo inmovilizado antes de
lanzar ambos jueces. Combinar sus resultados en un ledger inmovilizado y persistir la transacción,
el ledger, la identidad del objetivo y las referencias de los artefactos. Solo los hallazgos graves
confirmados independientemente por ambos jueces pueden activar correcciones. Un informe de un solo
juez sigue siendo sospechoso y no puede activar una corrección automática; las contradicciones
requieren escalamiento humano. Antes de la primera corrección, obtener aprobación humana explícita.
Permitir como máximo dos rondas acotadas de corrección y dos nuevos juicios específicos sobre el
ledger inmovilizado más cada delta inmutable de corrección. Después de las correcciones, ejecutar una
verificación final independiente, persistir el resultado y emitir un recibo terminal que contenga
los recuentos de confirmados, sospechosos, contradicciones e INFO, además de todas las referencias de
correcciones y nuevos juicios. La transacción debe finalizar exactamente como `approved` o
`escalated`; los problemas sin resolver después de la segunda ronda finalizan como `escalated`.

Si no se cumple la puerta G6, utilizar una revisión de integración ordinaria y específica, y el
conjunto completo de calidad del repositorio.

## Dependencias y límites de entrega

```text
ocultación de credenciales del espacio de trabajo ---> diagnósticos de la CLI

límite de credenciales de Git -----+
límite de credenciales del registro +---> caracterización residual sin defectos
limpieza de secretos de factory ----+
                                        |
                                        +---> corrección extraída de referencia remota de Git

resultados aceptados de unidades 1-8 ----> juicio opcional de integración
```

Cada unidad de trabajo puede revisarse de forma independiente y revertirse con seguridad. Un commit
o PR posterior puede utilizar una unidad de trabajo como límite de entrega, manteniendo juntos la
implementación, las pruebas y la evidencia, pero esta hoja de ruta no prescribe la creación de
commits ni PR. No existe ningún commit para esta hoja de ruta en el momento de su redacción.

## Fuera de alcance

- Volver a ejecutar o reclasificar la revisión 4R ordinaria completada como Judgment Day.
- Tratar el estado aprobado como prueba de que no existen defectos.
- Corregir automáticamente hallazgos WARNING/INFO sin un cambio acotado y evidencia específica.
- Refactorizar módulos únicamente para ajustarlos al mapa de perspectivas.
- Cambiar API públicas, esquemas persistidos o comportamiento de compatibilidad salvo que la puerta de decisión de una unidad de trabajo lo requiera explícitamente.
- Combinar defectos recién descubiertos en una unidad de trabajo existente sin alcance y evidencia independientes.
- Crear commits, ramas o pull requests como parte de esta tarea exclusivamente documental.

## Lista de seguimiento

- [ ] G0: Inmovilizar y registrar el objetivo inicial de cada unidad de trabajo.
- [x] Unidad 1: Aplicar y probar la ocultación de credenciales del espacio de trabajo (completada el 2026-07-12).
- [ ] Unidad 2: Reclasificada — sin cambio de código actual; aplicar la conformidad al adoptar el primer almacén duradero concreto.
- [ ] Confirmar y sincronizar de forma independiente el delta no sincronizado de OpenSpec de operaciones duraderas durante el trabajo de archivado.
- [x] Unidad 3: Aplicar un único contrato de plazos de reloj de pared para ambas puertas de Docker (completada el 2026-07-12).
- [x] Unidad 4: Normalizar los diagnósticos de validación de `stop`, `logs` y `exec` (completada el 2026-07-12).
- [x] Unidad 5: Aplicar el límite de fallos de Git seguro respecto a credenciales (completada el 2026-07-12).
- [x] Unidad 6: Aplicar el límite de fallos del registro seguro respecto a credenciales (completada el 2026-07-12).
- [x] Unidad 7: Garantizar la limpieza del secreto temporal de factory (completada el 2026-07-12).
- [x] Unidad 8: Completar la caracterización residual y extraer el defecto de referencia remota de Git (completada el 2026-07-12; smoke de imagen Docker no disponible localmente).
- [x] Unidad 8.1: Corregir la clasificación de referencias remotas de Git y conservar la precedencia de autenticación, el fallback de red y la seguridad de credenciales (implementada y aprobada el 2026-07-12; aún sin commit).
- [x] Ejecutar pruebas específicas con cada unidad completada y registrar los resultados exactos.
- [x] Ejecutar la verificación completa después de la caracterización residual y la corrección extraída de Git (524 pruebas superadas, 1 deseleccionada).
- [ ] G6: Decidir si el riesgo extraordinario entre módulos justifica realmente Judgment Day.
- [ ] Unidad 9: Si se cumple G6 y se autoriza por separado, ejecutar el juicio opcional de integración entre módulos.
- [ ] Si se autoriza Judgment Day, inmovilizar su objetivo inmutable y aplicar el protocolo terminal de dos rondas.
- [ ] Cerrar con una revisión ordinaria aprobada o un resultado terminal de Judgment Day; no dejar un linaje de revisión abierto indefinidamente.

## Posdata — 2026-07-14

Esta nota, añadida sin modificar el contenido anterior, actualiza los hechos de entrega sin
reescribir el registro de revisión.

- El endurecimiento de credenciales del registro está confirmado en `a11eb99`.
- La limpieza del secreto temporal de factory está confirmada en `44f3213`.
- La clasificación de referencias remotas de Git está confirmada en `02e2674`.
- Esta hoja de ruta de auditoría y su traducción al español están confirmadas en `db82fc1`.
- El delta completado `CAP-DURABLE-OPERATIONS-RECORD-FIX` se sincronizó en
  `openspec/specs/durable-operations/spec.md` y se archivó en
  `openspec/changes/archive/2026-07-14-CAP-DURABLE-OPERATIONS-RECORD-FIX/`.
- El archivo conserva el informe original de verificación PASS WITH WARNINGS. Su única advertencia
  de trazabilidad no se convirtió en evidencia satisfactoria y no se inició una nueva revisión.
- El Judgment Day opcional entre módulos sigue sin estar autorizado ni realizado.
