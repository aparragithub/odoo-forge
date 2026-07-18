# Mapa De `sp-data-environments`

## Qué es este documento

Es una guía de continuación segura para el change activo `openspec/changes/sp-data-environments/`, centrada en el problema que resuelve, sus dependencias duras y las superficies del repo que probablemente impacta.

## Por qué importa

Importa porque `sp-data-environments` es el único change vivo del árbol OpenSpec y además depende de varias foundations ya aceptadas y de otras todavía bloqueadas. Sin este mapa, es fácil reabrir scope histórico o empezar implementación antes de tiempo.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras sepan qué parte del trabajo ya está decidida, qué sigue bloqueado y cuál es el punto de continuación más seguro.

## Cómo ayuda al sistema

Ayuda al sistema porque conecta el portfolio, el change activo, las specs aceptadas y los módulos reales del repo en una sola vista de continuidad operativa.

## Leer Después De...

Leé esto después de [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md). Siguiente lectura: [09-portfolio-and-evidence-crosswalk.md](09-portfolio-and-evidence-crosswalk.md), y después [10-diagrams-maintenance-guide.md](10-diagrams-maintenance-guide.md).

## Ruta Rápida

> Importante: `sp-data-environments` no es el primer paso MVP de la secuencia actual. El siguiente outcome práctico es `SP-DEVELOPER-ONBOARDING`, y `.scratch/dev-onboarding/spec.md` mapea primariamente a `forge onboard <cliente>` dentro de ese subproyecto.

1. Empezá por `openspec/changes/sp-data-environments/proposal.md` para el outcome visible.
2. Confirmá el enfoque técnico en `openspec/changes/sp-data-environments/design.md`.
3. Revisá `tasks.md` antes de tocar código: el propio change sigue bloqueado por handoffs.
4. Contrastá estado y dependencias contra `docs/specs/platform/portfolio.json`.

## Ubicación En La Secuencia Actual

1. Primero va el MVP local: hacer corrible una instancia Odoo real sobre las foundations locales ya aceptadas.
2. Después va `SP-DEVELOPER-ONBOARDING` con `forge onboard <cliente>` y BD fresca local.
3. Recién después siguen `CAP-RESOURCE-OWNERSHIP`, `WF-DATA-COPY` y `SP-CONTROL-PLANE-AUTHORITY` como enablers necesarios.
4. Solo cuando esos handoffs estén aceptados corresponde retomar implementación de `sp-data-environments`.

## Qué problema resuelve

`sp-data-environments` busca entregar entornos de datos administrados para desarrollo, QA y automatización sin exponer copias incoherentes ni datos no anonimizados por defecto.

| Problema actual | Riesgo actual | Resultado buscado |
| --- | --- | --- |
| Hoy PostgreSQL vive embebido dentro del backend Docker local | La base y el filestore no tienen identidad y linaje gestionados como una sola unidad | Tratar base de datos + filestore como un entorno lógico coherente |
| No existe workflow neutral al provider para provisionar, clonar, anonimizar y compensar | Un fallo o retry puede dejar cleanup incompleto o ownership ambiguo | Operaciones idempotentes, fail-closed y con evidencia durable |
| No existe autoridad de control plane para referencias y linaje | No hay publicación autoritativa de un entorno usable | Registrar referencias y linaje sin almacenar bytes de datos |

## Qué ya está decidido

| Decisión | Estado | Alcance real |
| --- | --- | --- |
| `DPROV-DB` | Decidida | El primer adapter de base de datos es Docker PostgreSQL |
| Política de anonimización `DD` | Decidida | Los datos no productivos se anonimizan por defecto; excepciones requieren evidencia y aprobación |
| Política de activación `DG` | Decidida | Las capabilities y cambios habilitadores se entregan como prerrequisitos independientes |

Importante: que `DPROV-DB` esté resuelta NO significa que `sp-data-environments` esté listo para implementación completa. La selección del primer adapter no reemplaza los handoffs de aceptación pendientes.

## Dependencias y foundations necesarias

La propuesta y la spec del change dejan estas dependencias como gates obligatorios:

| Dependencia | Tipo en `portfolio.json` | Estado actual | Por qué importa |
| --- | --- | --- | --- |
| `CHG-FIRST-DATABASE-ADAPTER` | `sdd_change` | `achieved` | Entrega el primer adapter de base de datos y su evidencia inicial |
| `PORT-DATABASE-PROVIDER` | `port` | `achieved` | Define el contrato neutral al provider |
| `CAP-CREDENTIALS` | `prerequisite` | `achieved` | Permite materialización segura de credenciales |
| `CAP-DATA-ARTIFACTS` | `prerequisite` | `achieved` | Da el contrato para referencias y validación de artifacts de datos |
| `WF-DATA-COPY` | `workflow` | `proposed` | Sigue bloqueado; coordina copia coherente y reglas de datos |
| `INT-DATABASE-RUNTIME-CUTOVER` | `integration` | `proposed` | Evita ownership duplicado entre backend local y adapter de base de datos |
| `CAP-DURABLE-OPERATIONS` | `prerequisite` | `achieved` | Aporta identidad durable, replay y compensación segura |
| `CAP-RESOURCE-OWNERSHIP` | `prerequisite` | `proposed` | Sigue bloqueado; define ownership y cleanup residual |
| `SP-CONTROL-PLANE-AUTHORITY` | `sp` | `proposed` | Sigue bloqueado; hace autoritativas referencias, linaje y visibilidad |

## Qué módulos, specs y docs probablemente impacta

### Superficies de código probables

| Superficie | Tipo de impacto esperado |
| --- | --- |
| `src/odoo_forge/data_environments/` | Nuevos modelos y servicio puro del outcome |
| `src/odoo_forge/ports/data_environment_dependencies.py` | Nuevo facade de dependencias aceptadas |
| `src/odoo_forge/backend/plan.py` | Revisión futura del ownership de PostgreSQL y filestore |
| `src/odoo_forge_docker/provider.py` | Conservación de garantías actuales durante cutover |
| `src/odoo_forge_cli/main.py` | Eventual borde operador/control-plane cuando haya wiring autorizado |
| `tests/data_environments/` | Nuevas pruebas de modelos, transiciones, orquestación y recovery |

### Specs y contratos relacionados

| Superficie | Relación con el change |
| --- | --- |
| `openspec/changes/sp-data-environments/specs/managed-data-environments/spec.md` | Contrato de outcome del change activo |
| `openspec/specs/database-provider/spec.md` | Foundation aceptada que no debe reabrirse informalmente |
| `openspec/specs/docker-postgresql-database-adapter/spec.md` | Implementación aceptada del primer adapter |
| `openspec/specs/durable-operations/spec.md` | Prerrequisito aceptado para retry, recovery y compensación |
| `openspec/specs/data-artifacts/spec.md` | Prerrequisito aceptado para referencias de restore/copy |
| `openspec/specs/credential-materialization/spec.md` | Prerrequisito aceptado para secretos |

### Docs y portfolio relacionados

| Superficie | Relación con el change |
| --- | --- |
| `docs/specs/platform/portfolio.json` | Estado canónico de dependencias, decisiones, gaps y evidencia |
| [09-portfolio-and-evidence-crosswalk.md](09-portfolio-and-evidence-crosswalk.md) | Explica dónde registrar hechos y cómo validarlos |
| `docs/diagrams/odoo-forge-current-implementation.mmd` | Muestra el estado actual, no el outcome completo futuro |
| `docs/diagrams/odoo-forge-complete-platform.mmd` | Muestra la dirección objetivo donde este outcome encaja |

## Por qué importa para el roadmap

`sp-data-environments` importa al roadmap porque es el sucesor outcome-first de la parte de ciclo de vida de entornos que antes estaba mezclada dentro del histórico `SP-2`. En la práctica:

1. Reúne necesidades de desarrollo, QA y automatización alrededor de un resultado usable y auditable.
2. Obliga a cerrar dependencias transversales reales en vez de esconderlas dentro de un cambio monolítico.
3. Conecta runtime local, datos, durable operations y control plane bajo una política segura por defecto.

Eso NO lo convierte en el primer flujo MVP. En la secuencia vigente, el primer flujo usuario-valioso es el onboarding local del dev; `sp-data-environments` queda como outcome posterior una vez resueltos copy, ownership y authority.

## Puntos de continuación más seguros

| Si necesitás continuar... | Punto más seguro |
| --- | --- |
| Confirmar estado actual | `docs/specs/platform/portfolio.json` para revisar `status`, `gaps` y `evidence` |
| Continuar el flujo `forge onboard <cliente>` | `.scratch/dev-onboarding/spec.md` y la entrada `SP-DEVELOPER-ONBOARDING` en `docs/specs/platform/portfolio.json` |
| Continuar trabajo documental del change | `openspec/changes/sp-data-environments/proposal.md`, `design.md` y `tasks.md` |
| Empezar implementación del core puro cuando los gates estén aceptados | `src/odoo_forge/data_environments/` y `tests/data_environments/` |
| Verificar qué NO debe tocarse todavía | `src/odoo_forge_cli/`, control-plane adapters y wiring final mientras `CAP-RESOURCE-OWNERSHIP`, `WF-DATA-COPY` y `SP-CONTROL-PLANE-AUTHORITY` sigan propuestos |

## Qué evitar

- No reabrir documentos históricos de `SP-2` como si fueran la autoridad activa.
- No asumir que el primer adapter aceptado ya resuelve copy, lineage o control plane.
- No tratar `.scratch/dev-onboarding/spec.md` como si perteneciera primariamente a `sp-data-environments`.
- No empezar wiring visible o integración final mientras falte evidencia aceptada de `CAP-RESOURCE-OWNERSHIP`, `WF-DATA-COPY` y `SP-CONTROL-PLANE-AUTHORITY`.
- No tratar la base de datos sola como entorno completo: la propuesta exige coherencia entre base y filestore.
