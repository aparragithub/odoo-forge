# Mapa De `src/odoo_forge_registry/`

## Qué es este documento

Es la ficha de mantenimiento de `src/odoo_forge_registry/`: documenta el adapter de image registry y el resolver de artifacts `published` del manifest, ambos apoyados en GHCR a través de Docker CLI.

## Por qué importa

Importa porque este package concentra dos garantías críticas: que las imágenes se traten por referencias inmutables y que las layers `published` del manifest se resuelvan a digests verificables. Si eso se rompe, el sistema pierde reproducibilidad.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras entiendan cómo se separan las operaciones de registry genéricas del flujo más específico que traduce `registry://...` del manifest a artifacts concretos.

## Cómo ayuda al sistema

Ayuda al sistema porque mantiene fuera del core todo detalle de GHCR, `docker push`, `docker pull` y `docker buildx imagetools inspect`, pero deja disponibles outcomes tipados para CLI, locking y published artifact resolution.

## Leer después de...

Leer después de [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md), [11-src-manifest-map.md](11-src-manifest-map.md), [13-src-ports-map.md](13-src-ports-map.md) y [16-tests-cli-map.md](16-tests-cli-map.md).

## Siguiente lectura...

Después de esta ficha, la siguiente lectura recomendada es volver a [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md) para recorrer capability -> port -> adapter -> command, y luego a [15-tests-adapters-map.md](15-tests-adapters-map.md) para la cobertura concreta.

## Ruta rápida

1. Empezar aquí si el cambio toca image commands, published layers o resolución de digests.
2. Separar si el cambio pertenece al provider `GhcrImageRegistryProvider` o al `PublishedArtifactRegistryResolver`.
3. Confirmar que la CLI y `manifest/locking` sigan consumiendo ports y resultados inmutables, no detalles de GHCR.

## Qué vive en este package

| Archivo | Responsabilidad principal | Contrato que implementa |
| --- | --- | --- |
| `provider.py` | operaciones de image registry sobre GHCR vía Docker CLI | `ImageRegistryProvider` |
| `published_artifact_resolver.py` | traducción de `registry://<path>` + `version` a digest published | `PublishedArtifactResolver` |

## Interacciones con GHCR

| Operación | Implementación | Qué hace realmente |
| --- | --- | --- |
| resolve digest | `GhcrImageRegistryProvider.resolve_digest()` | inspecciona una ref publicable y la convierte a `repo@sha256:...` |
| publish | `GhcrImageRegistryProvider.publish()` | hace `docker push`, extrae digest o lo reinspecciona si hace falta |
| pull | `GhcrImageRegistryProvider.pull()` | hace `docker pull` de una ref digest y devuelve handle local |
| exists | `GhcrImageRegistryProvider.exists()` | inspecciona remotamente y confirma que el digest pedido coincide |
| inspect remoto | `_inspect_digest()` | usa `docker buildx imagetools inspect ... --format {{json .}}` |

Aunque el nombre del provider diga GHCR, el punto clave para maintainers es el boundary: todo ocurre mediante Docker CLI y referencias normalizadas, no mediante lógica distribuida por la CLI o el core.

## Flujos resolve, publish, pull y exists

| Flujo | Entrada | Salida | Uso principal |
| --- | --- | --- | --- |
| `resolve_digest` | `ImageRef` publicable | `ImageDigestRef` canónica | `image-resolve`, resolver de artifacts publicados |
| `publish` | `ImageRef` local/publicable | `ImageDigestRef` canónica | `image-publish` |
| `pull` | `ImageDigestRef` | `LocalImageRef` | `image-pull` |
| `exists` | `ImageDigestRef` | `bool` | `image-exists` |

## Rol del published artifact resolver

`PublishedArtifactRegistryResolver` existe para una tarea más angosta que el provider general.

| Paso | Qué hace |
| --- | --- |
| 1 | recibe `source` y `version` desde el manifest |
| 2 | transforma `registry://owner/repo` en `ghcr.io/owner/repo:<version>` |
| 3 | delega la resolución del digest al port de registry |
| 4 | exige que el resultado final contenga `@sha256:...` válido |
| 5 | devuelve `PublishedArtifactResolution` usable por `build_lock()` |

Esto importa porque `manifest/locking` no debería aprender cómo luce GHCR. Solo debería pedir "resolvé este artifact publicado a un digest inmutable".

## Relación con tipos core y commands CLI

| Superficie | Cómo interactúa con este package |
| --- | --- |
| `src/odoo_forge/ports/image_registry_provider.py` | define `publish`, `pull`, `resolve_digest`, `exists` |
| `src/odoo_forge/ports/published_artifact_resolver.py` | define `resolve(source, version)` |
| `src/odoo_forge/image_registry/types.py` | aporta `ImageRef`, `ImageDigestRef`, `LocalImageRef` |
| `src/odoo_forge_cli/main.py` | cablea `image-resolve`, `image-publish`, `image-pull`, `image-exists` |
| `src/odoo_forge/manifest/locking.py` | usa `PublishedArtifactResolver` para layers `published` |

## Clasificación de fallos y autorización

| Tipo de problema | Cómo responde este package | Implicación |
| --- | --- | --- |
| credenciales en la ref (`userinfo`) | rechazo temprano | evita soportar patterns inseguros en refs |
| auth/authorization | `RegistryAuthenticationError` o wrappers de publish/pull | el command falla limpio y la causa apunta a permisos reales |
| imagen inexistente | `RegistryImageNotFoundError` o `PublishedArtifactNotFoundError` | evita asumir éxito sobre tags o digests ausentes |
| digest distinto al esperado | `RegistryDigestMismatchError` | protege la inmutabilidad prometida por `exists` |
| Docker/buildx ausente, timeout o JSON inválido | `RegistryUnavailableError` | deja claro que el problema es operacional, no semántico |

## Riesgos si se modifica mal

| Cambio mal hecho | Consecuencia real |
| --- | --- |
| aceptar refs sin normalización estricta | la CLI puede trabajar con referencias ambiguas o mutables |
| degradar `exists()` a una mera presencia de repo/tag | se pierde la garantía de digest exacto |
| mezclar published artifact logic dentro de la CLI o del core | se dispersa el conocimiento de GHCR y se rompen los ports |
| ocultar auth/not-found detrás de un error genérico | maintainers y operadores pierden diagnóstico accionable |
| permitir `registry://` inválidos | `build_lock()` puede fijar artifacts no reproducibles |

## Qué se rompe si esta área se entiende mal

1. `forge lock` puede congelar published layers sin garantía de digest real.
2. `image-publish` y `image-resolve` pueden devolver refs no canónicas.
3. `image-exists` puede afirmar presencia sin verificar identidad.
4. El core puede contaminarse con reglas específicas de GHCR.

## Checklist para maintainers

- Mantener la normalización de refs y el rechazo de `userinfo` como frontera temprana.
- Verificar cualquier cambio contra `tests/adapters/test_registry_provider.py`, `tests/adapters/test_published_artifact_resolver.py` y `tests/cli/test_image_registry.py`.
- Si el cambio toca locking de published layers, revisar también [11-src-manifest-map.md](11-src-manifest-map.md).
- No mover conocimiento de GHCR a `main.py` ni a `manifest/locking.py`.
- Releer [13-src-ports-map.md](13-src-ports-map.md) antes de agregar operaciones nuevas al contract de registry.
