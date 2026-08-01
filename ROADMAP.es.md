# Hoja de ruta

Esta página es una proyección legible para las personas del estado canónico del
producto en [`docs/specs/platform/portfolio.json`](docs/specs/platform/portfolio.json).
Cuando ambos difieren, prevalece el portfolio.

odoo-forge es mantenido por una sola persona y **no incluye fechas**. Los niveles
siguientes expresan orden e intención, no promesas.

## ✅ Operativo hoy

Todo esto se puede utilizar ahora mismo, de principio a fin:

| Capacidad | Qué aporta |
| --- | --- |
| Núcleo de manifests | `project.yaml` validado y compuesto en una definición efectiva del proyecto |
| Resolución de fuentes | Cada ref de Git declarada fijada a un SHA de commit exacto (`project.lock`), con detección de drift |
| Proyección del workspace | Manifests fijados materializados en disco bajo raíces de montaje fijas, respaldados por Git |
| Backend local | Odoo + PostgreSQL provisionados en Docker local a partir del estado materializado (`run` / `status` / `stop` / `destroy` / `logs`) |
| Registry de imágenes | Operaciones de GHCR: resolución a digest, publicación, precarga y comprobaciones de existencia, además de la fábrica de imágenes base |
| Materialización de credenciales | Credenciales Enterprise respaldadas por SOPS/age, con comprobaciones de `doctor` y rotación de claves |
| Incorporación de desarrolladores | `onboard` valida y materializa entradas locales, o resuelve un cliente conocido por el catálogo a una instancia en ejecución |

## 🧱 Construido, todavía no conectado

Estas bases están implementadas y probadas, pero todavía no se exponen como
workflows administrados de principio a fin:

- **Artefactos de datos** — primitivas de captura y restauración para el contenido de bases de datos, incluido el enmascaramiento de dumps
- **Operaciones durables** — registros reanudables de operaciones de larga duración
- **Propiedad de recursos** — autoridad sobre qué actor posee cada recurso de runtime
- **Contrato de tenancy** — límites de cliente y modelo de cuotas
- **Catálogo de proyectos** — el índice que permite que `onboard <client>` resuelva un cliente a su manifest

Se vuelven visibles para los usuarios cuando los subproyectos siguientes las consumen.

## 🔜 Próximo

El subproyecto planificado más cercano, en etapa de propuesta:

- **Entornos de datos administrados** (`SP-DATA-ENVIRONMENTS`) — solicitar un entorno
  de base de datos (vacío, copia enmascarada o artefacto restaurado) como un flujo
  administrado en lugar de mediante comandos ejecutados a mano. Este es el primer
  consumidor de las bases de artefactos de datos, operaciones durables y propiedad.

## 🎯 Estado objetivo

Dirección, en el orden previsto; cada elemento depende de las capas anteriores:

1. **Especificación de despliegue neutral al provider** — describir un despliegue sin nombrar Docker, EC2 ni Kubernetes
2. **Despliegue remoto** — los mismos manifests provisionados en destinos remotos (EC2, Kubernetes, Fargate)
3. **Autoridad del control plane + solicitudes de entornos** — un servicio que sea propietario de las instancias, no solo una CLI
4. **Acceso a la plataforma (RBAC)** — roles e identidad para equipos, no para un único operador
5. **Automatización de entregas** — flujos de build, publicación y despliegue impulsados por CI
6. **Gobernanza de producción, ciclo de vida de recursos y recuperación de datos** — las disciplinas operativas en torno a datos reales de clientes
7. **UI de operaciones** — una superficie web una vez que los flujos subyacentes sean estables

## Fuera de alcance (por ahora)

- Reemplazar las propias herramientas de Odoo (odoo-bin, scaffolding de módulos)
- Administrar la configuración de Odoo a nivel de aplicación más allá de los aspectos del despliegue
- Abstracción multicloud más allá del límite de la especificación de despliegue

## Cómo se mantiene esta página

Cada nivel corresponde a campos `status` del portfolio (`achieved`, `proposed`,
`decided`). Cuando se completa un subproyecto, pasa de *Próximo*/*Estado objetivo*
a *Operativo hoy* aquí, en el mismo PR que archiva su change.
