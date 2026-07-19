# La edición y el enterprise son estructurales; las categorías de mount las declara el usuario

El manifiesto `project.yaml` mezclaba tres cosas mal resueltas: la edición se infería con una bandera por-repo (`requires_edition: enterprise`) en lugar de declararse una vez; el source de Enterprise —privado, sin URL pública en el core— no tenía dónde vivir; y las categorías de capa (`category`) eran un `Literal` cerrado de cuatro valores que hardcodeaba una taxonomía (`community`, `enterprise`, `worktrees`, `custom`) más un `localization` heredado. Decidimos volver **estructural** lo que es estructural (edición y enterprise) y **abierto** lo que es del usuario (las categorías), y dejar el `addons_path` donde ya se resuelve bien: el entrypoint de la imagen.

## Decisiones

**D1 — Bloque `enterprise:` de primera clase, singleton, hermano de `core:`.** Enterprise es privado y no tiene URL pública; declararlo como un layer más era forzarlo dentro de `layers:` sin serlo. Ahora es un bloque singleton (`url`, `ref`) al nivel de `core:`, compuesto en la posición 2 de la cadena (`core → enterprise → layers → client`) sólo cuando `edition == "enterprise"`. La validación es simétrica: requerido si-y-sólo-si la edición es enterprise, prohibido en caso contrario.

**D2 — Split de `requires_edition` en algo estructural + una precondición.** Se eliminó `GitRepo.requires_edition` (una bandera por-repo ambigua). La edición pasa a ser estructural vía el bloque `enterprise:` (D1); y la necesidad de que una capa tenga Enterprise presente se expresa con `requires_enterprise: bool` en `GitLayer`/`PublishedLayer`, usada **sólo como precondición de coherencia** —nunca afecta la clasificación de mount ni la posición en la cadena—. La clave vieja se rechaza con un error de migración accionable que nombra el reemplazo. Es un cambio breaking, documentado en el CHANGELOG.

**D3 — `category` es un slug libre validado, no un enum cerrado.** El usuario declara la categoría que quiera; el sistema sólo la ubica. `category` acepta un slug (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, 1–63 chars); `None` normaliza a `"custom"`. La validación es deliberadamente mínima —forma de slug y cota de longitud, que también cierran path-traversal—, sin ninguna otra semántica.

**D4 — El `addons_path` se descubre en el entrypoint, no se cablea por Python.** Odoo recibe el `addons_path` vía `odoo.conf`, que escribe `factory/entrypoint.sh` (`build_addons_path`) escaneando los roots montados en `/mnt`. No se construye una ruta en `backend/plan.py` ni se pasa por `ContainerSpec`. El spike previo confirmó que ese es el punto correcto; el blast radius real de las categorías abiertas es `entrypoint.sh` + `Dockerfile`, no el core Python.

## Refinamiento del modelo de mount

Sobre D3 se acordó un modelo de mount **puro** que elimina, por construcción, el riesgo de colisión de nombres:

- Los roots de sistema/estructurales son **únicamente** `community`, `enterprise` y `worktrees`. `localization` se **elimina** como root reservado: si alguien lo declara, es una categoría de usuario más y vive en `/mnt/custom/localization`.
- `worktrees` queda reservado estrictamente para las copias editables promovidas por `unlock`; `classify_root` **nunca** lo devuelve.
- `custom` es el namespace **padre** de toda categoría declarada por el usuario: `adhoc` monta en `/mnt/custom/adhoc/`, `oca` en `/mnt/custom/oca/`, y lo no categorizado (default `"custom"`) en `/mnt/custom/default/`.
- **No hay blocklist de nombres reservados.** Como toda categoría anida bajo `/mnt/custom/`, una categoría llamada literalmente `community`/`enterprise`/`worktrees` se vuelve un simple subfolder ahí (`/mnt/custom/community`) y jamás puede colisionar con un root de sistema. La colisión que un blocklist evitaría es estructuralmente imposible una vez que hay anidamiento.
- En consecuencia `MOUNT_ROOTS`/`build_mount_roots` dejan de ser una constante estática y pasan a **derivarse del manifiesto** (`build_mount_roots(base, manifest)`): los roots de sistema fijos más una entrada `custom/<category>` por cada categoría distinta declarada. `MountRoot` se ensancha de `Literal[...]` a `str`.
- El orden/precedencia del `addons_path` en el entrypoint queda: roots de sistema primero, luego las categorías de usuario (ordenadas), y `/opt/odoo/addons` al final.

## Alternativas consideradas

- **Mantener `requires_edition: enterprise` por-repo.** Rechazado: infiere la edición desde N banderas dispersas en vez de declararla una vez, y es ambiguo respecto de "necesito enterprise presente" (que es lo que ahora expresa `requires_enterprise`).
- **Enterprise como un layer más dentro de `layers:`.** Rechazado: enterprise es un singleton sin URL pública y con posición fija en la cadena; meterlo en la lista invitaba a declararlo dos veces o fuera de orden.
- **Dejar `category` como enum cerrado y sumar valores a mano.** Rechazado: hardcodea una taxonomía que no es del sistema sino del usuario; cada cliente nuevo obligaba a tocar el schema.
- **Blocklist de nombres reservados para `category`.** Rechazado por innecesario: el anidamiento bajo `/mnt/custom/` hace la colisión imposible, así que el blocklist sólo agregaría reglas y mensajes de error sin proteger de nada real.
- **Construir el `addons_path` en Python y pasarlo por `ContainerSpec`.** Rechazado (confirmado por auditoría no-op): el `addons_path` ya se resuelve bien en el entrypoint vía `odoo.conf`; duplicarlo en el core sumaba una segunda fuente de verdad.

## Consecuencias

- El manifiesto declara la intención una sola vez: la edición es estructural, el enterprise tiene un lugar propio y las categorías son del usuario. El sistema deja de imponer taxonomía.
- Agregar una categoría nueva (`adhoc`, `oca`, lo que sea) no toca ni el schema ni la imagen: `build_addons_path` la descubre al escanear `/mnt/custom/*`. La imagen deja de hornear una lista fija de roots.
- Se paga un breaking change acotado (remoción de `requires_edition`, forma nueva de `MOUNT_ROOTS` y del `mkdir` del Dockerfile), mitigado con error de migración accionable y notas de CHANGELOG.
- `backend/plan.py` deriva `Mount.root` de `container_path.parts[2]`, que con el anidamiento colapsa toda categoría custom a la etiqueta `"custom"`. Es inocuo hoy —`Mount.root` no lo consume nadie; los binds usan el `container_path` completo y anidado—, pero conviene revisarlo si algún consumidor futuro pretende distinguir categorías por esa etiqueta.

## Preguntas abiertas

- **Prioridad configurable del `addons_path` por categoría de usuario** (T2.6, parkeado, no bloqueante): hoy las categorías de usuario rankean *después* de los roots de sistema, sin override. Si en algún momento una categoría necesita precedencia sobre `community`/`enterprise` (p. ej. para pisar un módulo core con un fork), habría que exponer una prioridad declarativa. Se difiere hasta tener un caso real.
