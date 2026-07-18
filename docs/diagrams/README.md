# Renderizado Del Diagrama De Implementación Actual

`odoo-forge-current-implementation.mmd` es la fuente de verdad. Su archivo adjunto
`odoo-forge-current-implementation.mmd.svg` es derivado y solo debe cambiar ejecutando el
renderizador.

Antes de tocar esta carpeta:

- Empezá en [`../00-master-index.md`](../00-master-index.md) si necesitás contexto general.
- Leé [`../10-diagrams-maintenance-guide.md`](../10-diagrams-maintenance-guide.md) para reglas de autoridad, render y mantenimiento.

## Renderizar

Desde la raíz del repositorio, ejecutá:

```sh
docs/diagrams/render-current-implementation.sh
```

El script usa la imagen oficial de Mermaid CLI `11.16.0`, fijada a este índice OCI inmutable:

```text
ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.16.0@sha256:29077c6bd02f14bdfdd5fee552d9c00fe68d4fab3cd84952d21e2d1faf2fadaf
```

Docker es el runtime por defecto. Quienes usen Podman pueden preservar su user namespace con:

```sh
CONTAINER_RUNTIME=podman docs/diagrams/render-current-implementation.sh
```

En hosts donde `getenforce` devuelve `Enforcing`, el script agrega la opción `:Z` al bind mount
para Docker y Podman. Omite esa opción cuando SELinux está permissive, disabled o no existe, para
mantener el mismo comando portable a sistemas sin SELinux.

El script escribe con el UID/GID del host. Las configuraciones versionadas de Mermaid y Puppeteer
fijan el tema, fondo, stack de fuentes, semilla determinista de IDs Mermaid, viewport, device
scale y argumentos de lanzamiento de Chromium.

## Verificación

La verificación aislada del archivo generado renderiza a un sibling temporal y compara byte a byte:

```sh
docs/diagrams/render-current-implementation.sh --check
```

Usá ese comando como job dedicado de documentación en CI. Requiere Docker, o Podman mediante
`CONTAINER_RUNTIME`, y puede descargar la imagen si el digest exacto no está en caché. Nunca
resuelve un tag no fijado. Los tests unitarios ordinarios de Python no invocan este contenedor.

La igualdad byte a byte es el criterio de aceptación solo después de que dos renderizados
consecutivos demuestren que esta imagen fijada de Mermaid/Chromium emite SVG estable en el entorno
de ejecución. Si ese check falla entre renderizados idénticos, inspeccioná el diff antes de agregar
normalización. Normalizá solo metadata no semántica confirmada, documentá esa transformación acá y
dejala en el script de render; nunca edites a mano un SVG generado.

## Actualizar El Renderizador

1. Elegí una release concreta de `mermaid-js/mermaid-cli`.
2. Verificá el manifest correspondiente en GHCR y registrá su `Docker-Content-Digest`.
3. Actualizá tag y digest en `render-current-implementation.sh`.
4. Renderizá dos veces desde una fuente limpia y compará ambos SVG byte a byte.
5. Ejecutá `--check`, inspeccioná el diff y commiteá script, configuración, fuente y SVG generado como una sola unidad revisable.

El tag actual fue verificado contra la release oficial `11.16.0` y GHCR devolvió el digest OCI
index `sha256:29077c6bd02f14bdfdd5fee552d9c00fe68d4fab3cd84952d21e2d1faf2fadaf`.
