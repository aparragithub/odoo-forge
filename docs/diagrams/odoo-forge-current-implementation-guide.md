# Odoo Forge actual explicado simple

> **Límite de implementación (nota canónica).** Mermaid es la fuente autoritativa y el SVG es
> derivado: se genera con el flujo fijado documentado en el
> [`README.md`](../../README.md), nunca se edita a mano. Las rutas sólidas representan
> implementaciones operativas. El adaptador aislado Docker PostgreSQL implementa
> `DatabaseProvider`; catálogo de proyectos, credenciales, artefactos de datos y operaciones
> durables siguen siendo fundamentos neutrales sin un flujo operativo administrado conectado.
> Tenancy, entornos de datos administrados, control plane, backends remotos, RBAC y UI web son
> estado objetivo, no capacidades actuales.

Este documento explica el diagrama `odoo-forge-current-implementation.mmd` en palabras simples. La idea central es esta: una persona usa el comando `forge`, y `forge` coordina distintas partes del sistema para leer un proyecto Odoo, resolver versiones, preparar el código, levantar contenedores y trabajar con imágenes.

## Estado actual y fuentes

Leé este documento como una guía de lo que está entregado hoy. Para estado, dependencias y evidencia
de aceptación, la fuente de verdad es el
[`portfolio.json`](../specs/platform/portfolio.json). La
[hoja de ruta de estabilización](../specs/2026-07-14-stabilization-roadmap.md) ordena el trabajo
activo, incluido este [cambio OpenSpec](../../openspec/changes/refresh-platform-roadmap-after-stabilization/proposal.md);
`sp-data-environments` sigue bloqueado. El diagrama de plataforma completa es una referencia de
estado objetivo/histórica: no describe componentes desplegados hoy.

## Resumen rápido

El proyecto está armado en capas:

1. El usuario ejecuta `forge`.
2. La CLI recibe el comando y decide qué necesita hacer.
3. El núcleo del sistema calcula planes y valida información, sin hablar directamente con herramientas externas.
4. Los puertos definen qué necesita el núcleo del mundo exterior.
5. Los adaptadores ejecutan el trabajo real con `git`, Docker, GHCR y el sistema de archivos.
6. El resultado queda en archivos locales, repositorios, contenedores o imágenes publicadas.

## Actores

| Actor | Qué hace |
| --- | --- |
| Developer | Es la persona que usa `forge` desde la terminal. Puede validar el proyecto, bloquear versiones, preparar el workspace, desbloquear una capa, levantar Odoo o consultar el estado. |
| CLI `forge` | Es la puerta de entrada. Recibe comandos humanos y los transforma en acciones internas. |
| Herramientas externas | Son `git`, Docker, GHCR y el sistema de archivos. Hacen el trabajo físico fuera del código puro del proyecto. |

## Componentes principales

### Developer

Es quien inicia todo. No interactúa directamente con las piezas internas del sistema. Usa comandos como `forge lock`, `forge project`, `forge run`, `forge status` o `forge image-*`.

### CLI: `forge`

Es la interfaz de consola. Su trabajo es recibir el comando, leer los parámetros y llamar a la parte correcta del sistema.

Pensalo como una recepción: el usuario llega con un pedido, y la CLI lo deriva al área que corresponde.

## Comandos disponibles en la CLI

Estos son los comandos que hoy expone `forge`. La lista está agrupada por intención, no por orden interno del código.

### Revisar y fijar el proyecto

| Comando | Para qué sirve | Ejemplo mental |
| --- | --- | --- |
| `forge validate` | Revisa que `project.yaml` sea válido y detecta si hay diferencias contra `project.lock` o el workspace local. | “¿Mi proyecto está bien descrito y coincide con lo que tengo en disco?” |
| `forge lock` | Resuelve las versiones declaradas y escribe `project.lock` con referencias exactas. | “Congelá las versiones para que todos usen lo mismo.” |

Flujo típico:

1. Escribís o actualizás `project.yaml`.
2. Ejecutás `forge validate` para detectar errores básicos.
3. Ejecutás `forge lock` para generar o actualizar `project.lock`.
4. Volvés a ejecutar `forge validate` si querés confirmar que todo quedó consistente.

### Preparar el código local

| Comando | Para qué sirve | Ejemplo mental |
| --- | --- | --- |
| `forge project` | Materializa el proyecto en el filesystem usando `project.lock`. Baja o prepara los repositorios necesarios en las rutas esperadas. | “Armame el workspace local con todas las capas.” |
| `forge unlock --layer <capa> --repo <repo>` | Convierte un checkout de sólo lectura en una copia editable para poder trabajar sobre esa capa. | “Necesito modificar este repo de una capa inferior.” |

Flujo típico:

1. Ya tenés `project.lock` generado.
2. Ejecutás `forge project`.
3. El sistema prepara el workspace local.
4. Si necesitás tocar una capa que normalmente es de sólo lectura, ejecutás `forge unlock`.

### Ejecutar Odoo localmente

| Comando | Para qué sirve | Ejemplo mental |
| --- | --- | --- |
| `forge run` | Levanta la instancia local con Docker: Odoo + PostgreSQL. | “Arrancá el proyecto.” |
| `forge status` | Muestra si los contenedores principales están corriendo y listos. | “¿Está vivo?” |
| `forge stop` | Detiene y elimina contenedores/red, pero conserva los volúmenes importantes. | “Apagalo sin borrar los datos persistentes.” |
| `forge logs --role odoo` | Muestra logs del contenedor de Odoo. También puede pedir PostgreSQL con `--role postgres`. | “Mostrame qué está pasando.” |
| `forge exec -- <comando>` | Ejecuta un comando dentro del contenedor de Odoo. | “Corré esto adentro de Odoo.” |

Flujo típico:

1. Ejecutás `forge run`.
2. Consultás `forge status` para ver si Odoo y PostgreSQL están listos.
3. Si algo falla, usás `forge logs --role odoo` o `forge logs --role postgres`.
4. Si necesitás correr algo dentro del contenedor, usás `forge exec -- <comando>`.
5. Cuando terminás, ejecutás `forge stop`.

### Trabajar con imágenes

| Comando | Para qué sirve | Ejemplo mental |
| --- | --- | --- |
| `forge image-resolve --ref <imagen>` | Convierte una referencia de imagen soportada en una referencia fija por digest. | “Decime la versión exacta e inmutable de esta imagen.” |
| `forge image-publish --ref <imagen>` | Publica una imagen ya construida y devuelve su digest. | “Subí esta imagen y dame su referencia exacta.” |
| `forge image-pull --ref <digest>` | Descarga una imagen por digest al Docker local. | “Traé esta imagen exacta a mi máquina.” |
| `forge image-exists --ref <digest>` | Verifica si una imagen por digest existe en el registry. | “¿Esta imagen existe allá?” |

Estos comandos no levantan Odoo por sí solos. Sólo trabajan con imágenes. Después `forge run` puede usar una imagen digest-backed con `--odoo-image-ref`.

## Secuencia recomendada para un developer

Para alguien que entra al proyecto, el recorrido más simple sería:

1. `forge validate`
2. `forge lock`
3. `forge project`
4. `forge run`
5. `forge status`
6. `forge logs --role odoo` si necesita revisar errores
7. `forge stop` cuando termina

No todos los comandos se usan todos los días. Los comandos de imágenes suelen ser más de plataforma o mantenimiento; los comandos de `project`, `run`, `status`, `logs` y `stop` son los más cercanos al flujo diario de desarrollo.

### Núcleo puro: `odoo_forge`

Es el cerebro del sistema. Se llama “puro” porque no debería depender directamente de Docker, `git`, GHCR ni de comandos externos.

Su trabajo es decidir qué debería pasar, no hacerlo físicamente.

Por ejemplo, el núcleo puede decir: “para este proyecto necesito estos repositorios, estas rutas y esta imagen”. Pero no clona el repo ni corre Docker por sí mismo.

## Partes del núcleo

| Componente | Explicación simple |
| --- | --- |
| Manifest schema | Define cómo debe verse el archivo `project.yaml`. Ese archivo describe el proyecto Odoo: versión, capas, repositorios y configuración. |
| Onion composition | Ordena las capas del proyecto como una cebolla: base, enterprise, OCA, localización y cliente. Sirve para saber qué va primero y qué depende de qué. |
| Lockfile resolution | Convierte referencias flexibles en versiones exactas. Por ejemplo, transforma una rama o tag en un commit concreto. |
| Workspace projection | Decide cómo se debe materializar el código en la máquina del developer. Es decir, qué carpetas se crean, qué repositorios se bajan y dónde quedan. |
| Backend plan | Arma el plan para ejecutar Odoo a partir del estado materializado validado. Define contenedores, volúmenes, puertos e imágenes. |
| Status parsing | Interpreta la información que devuelve Docker para decir si una instancia está corriendo, detenida o no existe. |
| Image registry refs/errors | Normaliza nombres de imágenes y errores relacionados con imágenes. Ayuda a trabajar con referencias a imágenes de forma consistente. |
| Drift validation | Compara la intención del proyecto con lo que realmente existe. Sirve para detectar desvíos entre `project.yaml`, `project.lock` y el workspace. |
| Project catalog | Resuelve y valida un catálogo de proyectos como fundamento de dominio, todavía sin flujo operativo conectado. |

## Puertos

Los puertos son contratos. No hacen el trabajo directamente; dicen qué necesita el núcleo.

Esto es importante porque permite cambiar la implementación sin romper el corazón del sistema. Por ejemplo, hoy se usa Docker local, pero en el futuro podría existir otro backend.

| Puerto | Para qué sirve |
| --- | --- |
| SourceProvider | Resolver código fuente desde repositorios. |
| WorkspaceProvider | Crear o revisar el workspace local. |
| BackendProvider | Ejecutar, detener, consultar logs o correr comandos en una instancia. |
| ImageRegistryProvider | Publicar, resolver, verificar o descargar imágenes desde un registry. |
| DatabaseProvider | Administrar el ciclo de vida de una base de datos mediante un adaptador seleccionado. |

## Adaptadores implementados

Los adaptadores son las piezas que sí hablan con herramientas reales.

| Adaptador | Qué conecta |
| --- | --- |
| `odoo_forge_git` / `GitSourceProvider` | Conecta el puerto de código fuente con `git` y repositorios remotos. |
| `odoo_forge_workspace` / `GitWorkspaceProvider` | Materializa el workspace usando operaciones de Git y filesystem. |
| `odoo_forge_docker` / `DockerBackendProvider` | Ejecuta Odoo y PostgreSQL usando Docker local. |
| `odoo_forge_postgres_docker` / `DockerPostgresqlDatabaseProvider` | Implementa el ciclo de vida aislado de PostgreSQL para `DatabaseProvider`, sin redirigir el backend local. |
| `odoo_forge_registry` / `GhcrImageRegistryProvider` | Trabaja con imágenes en GHCR usando Docker y `buildx`. |

## Herramientas externas

| Herramienta | Qué aporta |
| --- | --- |
| `git / repositories` | Guarda y entrega el código fuente de las capas del proyecto. |
| `docker CLI / daemon` | Levanta contenedores, redes y volúmenes. |
| GHCR via Docker/buildx | Registry donde se publican o consultan imágenes. |
| Materialized workspace | Carpeta local donde queda el código listo para trabajar. |
| `project.lock` | Archivo que fija versiones exactas para que el proyecto sea reproducible. |

## Secuencia general

La secuencia más importante es esta:

1. El developer ejecuta un comando `forge`.
2. La CLI identifica qué comando se pidió.
3. La CLI llama a una parte del núcleo puro.
4. El núcleo calcula un resultado o un plan.
5. Si hace falta tocar el mundo exterior, el núcleo usa un puerto.
6. El puerto es implementado por un adaptador concreto.
7. El adaptador llama a `git`, Docker, GHCR o al filesystem.
8. El resultado vuelve hacia la CLI.
9. La CLI muestra un resultado entendible al developer.

## Flujo end-to-end: preparar un proyecto local

Este flujo representa el camino típico para dejar un proyecto listo en la máquina del developer.

1. El developer tiene un `project.yaml`.
2. Ejecuta `forge lock`.
3. La CLI llama a `Lockfile resolution`.
4. El núcleo usa `SourceProvider`.
5. El adaptador `GitSourceProvider` consulta los repositorios con `git`.
6. Se genera `project.lock` con versiones exactas.
7. Luego el developer ejecuta `forge project`.
8. La CLI llama a `Workspace projection`.
9. El núcleo decide qué repositorios y carpetas hacen falta.
10. `WorkspaceProvider` usa `GitWorkspaceProvider`.
11. Se crea el workspace local materializado.
12. El developer queda con el código listo para inspeccionar y trabajar.

## Flujo end-to-end: levantar Odoo localmente

Este flujo explica qué pasa cuando se quiere ejecutar una instancia local.

1. El developer ejecuta `forge run`.
2. La CLI llama a `Backend plan`.
3. El núcleo calcula qué necesita Docker: imagen, contenedor de Odoo, contenedor de PostgreSQL, volúmenes y mounts.
4. El núcleo pasa ese plan al `BackendProvider`.
5. El adaptador `DockerBackendProvider` ejecuta comandos Docker.
6. Docker puede usar el workspace local como código montado.
7. Docker puede descargar imágenes desde GHCR si las necesita.
8. La instancia queda corriendo localmente.
9. El developer puede consultar `forge status`, `forge logs`, `forge exec` o detener con `forge stop`.

## Flujo end-to-end: trabajar con imágenes

Este flujo cubre comandos `image-*`.

1. El developer ejecuta un comando como `forge image-resolve`, `forge image-publish`, `forge image-exists` o `forge image-pull`.
2. La CLI llama a la parte de referencias de imágenes del núcleo.
3. El núcleo valida y normaliza la referencia de imagen.
4. El núcleo usa `ImageRegistryProvider`.
5. El adaptador `GhcrImageRegistryProvider` llama a Docker o `docker buildx`.
6. GHCR responde con información de la imagen, un digest, o confirma si existe.
7. La CLI muestra el resultado.

## Por qué el sistema está separado así

La separación existe para que el proyecto no quede atado a una sola herramienta.

Hoy hay Docker local, Git y GHCR. Pero el diseño permite que mañana haya otros proveedores sin reescribir todo.

La regla simple es:

| Capa | Responsabilidad |
| --- | --- |
| CLI | Hablar con la persona. |
| Núcleo | Pensar, validar y planificar. |
| Puertos | Definir qué necesita el núcleo. |
| Adaptadores | Hablar con herramientas reales. |
| Herramientas externas | Ejecutar el trabajo físico. |

## Ejemplo mental simple

Imaginá que querés construir una casa.

La CLI es quien recibe tu pedido.

El núcleo es el arquitecto: lee los planos, revisa reglas y decide qué hay que hacer.

Los puertos son contratos: “necesito comprar materiales”, “necesito contratar electricidad”, “necesito levantar paredes”.

Los adaptadores son los proveedores reales: la ferretería, el electricista, el albañil.

Docker, Git y GHCR son las herramientas y servicios que hacen el trabajo concreto.

Así, si cambiás de ferretería, no cambiás el plano de la casa.

## Qué ya está desarrollado hoy

Según el diagrama actual, ya existe:

1. Una CLI `forge`.
2. Un núcleo con manifest, lockfile, composición, proyección, planificación desde estado materializado, backend local, estado e imágenes.
3. Puertos para código fuente, workspace, backend, imágenes y bases de datos.
4. Adaptadores concretos para Git, workspace local, Docker, Docker PostgreSQL y GHCR.
5. Integración con herramientas externas como `git`, Docker, GHCR, filesystem y `project.lock`.
6. Fundamentos neutrales para catálogo de proyectos, credenciales, artefactos de datos y operaciones durables; sus consumidores administrados todavía no están conectados.

## Qué no muestra este diagrama

Este diagrama representa lo desarrollado actualmente. No muestra todavía la visión completa de plataforma con control plane, RBAC, UI web, múltiples backends remotos, flujos administrados de datos o CI/CD completo.

Para ese estado objetivo está el diagrama de plataforma completa:
[`odoo-forge-complete-platform.mmd`](odoo-forge-complete-platform.mmd).
