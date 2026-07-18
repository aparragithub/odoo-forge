# Cruce De Specs A Módulos

## Qué es este documento

Es el cruce entre specs aceptadas, capabilities, módulos reales de `src/`, adapters concretos, tests y flujos visibles para usuarios.

## Por qué importa

Importa porque traduce lenguaje de OpenSpec y portfolio a puntos reales de implementación. Sin este puente, es fácil leer una spec correcta pero tocar los archivos equivocados.

## Por qué existe

Existe para acelerar trazabilidad técnica: desde una capability aceptada hasta el código, los adapters y las pruebas que deben cambiar juntos.

## Cómo ayuda al sistema

Ayuda al sistema porque alinea intención, implementación y verificación, y permite retomar cambios sin reconstruir manualmente la relación entre spec y módulo.

## Leer Después De...

Leé esto después de [06-docs-and-openspec-lifecycle.md](06-docs-and-openspec-lifecycle.md). Siguiente lectura: [08-sp-data-environments-map.md](08-sp-data-environments-map.md). Si primero necesitás orientación general, volvé a [01-repository-map.md](01-repository-map.md). Si el cambio cae dentro del core puro, complementalo con [03-src-core-map.md](03-src-core-map.md).

## Cómo Leer Este Cruce

1. Empezá por la capability/spec aceptada bajo `openspec/specs/**`.
2. Localizá los módulos core de `src/odoo_forge/` que son dueños de la semántica.
3. Verificá qué adapter package ejecuta el side effect.
4. Tocá primero los tests de la columna correspondiente antes de mover wiring CLI o docs de estado.

## Capacidades De Runtime Ya Aterrizadas

| Capability / spec aceptada | Módulos `src/` principales | Adapter packages | Tests principales | Flujos visibles impactados |
| --- | --- | --- | --- | --- |
| `openspec/specs/manifest/spec.md` | `src/odoo_forge/manifest/schema.py`, `composition.py`, `locking.py`, `lockfile.py`, `drift.py`, `projection.py`, `resolution.py` | `src/odoo_forge_git`, `src/odoo_forge_workspace`, `src/odoo_forge_registry`, `src/odoo_forge_cli` | `tests/manifest/`, `tests/cli/test_validate.py`, `tests/cli/test_lock.py`, `tests/cli/test_project.py`, `tests/cli/test_unlock.py` | `forge validate`, `forge lock`, `forge project`, `forge unlock` |
| `openspec/specs/local-backend/spec.md` | `src/odoo_forge/backend/plan.py`, `status.py`, `errors.py`, `src/odoo_forge/ports/backend_provider.py`, partes de `src/odoo_forge/manifest/projection.py` | `src/odoo_forge_docker`, `src/odoo_forge_workspace`, `src/odoo_forge_cli` | `tests/backend/test_plan.py`, `tests/backend/test_status.py`, `tests/ports/test_backend_provider.py`, `tests/adapters/test_docker_provider.py`, `tests/adapters/test_docker_provider_integration.py`, `tests/cli/test_backend.py` | `forge run`, `forge status`, `forge stop`, `forge logs`, `forge exec` |
| `openspec/specs/image-registry-provider/spec.md` | `src/odoo_forge/image_registry/reference.py`, `types.py`, `errors.py`, `src/odoo_forge/ports/image_registry_provider.py`, `src/odoo_forge/ports/published_artifact_resolver.py` | `src/odoo_forge_registry`, `src/odoo_forge_cli` | `tests/ports/test_image_registry_provider.py`, `tests/ports/test_published_artifact_resolver.py`, `tests/adapters/test_registry_provider.py`, `tests/adapters/test_published_artifact_resolver.py`, `tests/cli/test_image_registry.py` | `forge image-resolve`, `forge image-publish`, `forge image-pull`, `forge image-exists`, locking de artifacts `registry://` |
| `openspec/specs/database-provider/spec.md` | `src/odoo_forge/database/types.py`, `errors.py`, `readiness.py`, `src/odoo_forge/ports/database_provider.py` | `src/odoo_forge_postgres_docker` | `tests/database/test_types.py`, `tests/database/test_errors.py`, `tests/database/test_readiness.py`, `tests/ports/test_database_provider.py`, `tests/adapters/test_postgres_docker_provider.py` | Foundation de lifecycle de base de datos; todavía no hay command CLI canónico expuesto |
| `openspec/specs/docker-postgresql-database-adapter/spec.md` | `src/odoo_forge/database/*`, `src/odoo_forge/ports/database_provider.py` | `src/odoo_forge_postgres_docker/provider.py`, `secret_injection.py`, `target_handoffs.py`, `authority.py` | `tests/adapters/test_postgres_docker_provider.py`, `tests/adapters/test_postgres_docker_provider_integration.py`, `tests/adapters/test_postgres_docker_secret_injection.py`, `tests/adapters/test_postgres_docker_authority.py` | Flujo aislado de `DatabaseProvider` sobre Docker; no hace cutover del runtime local actual |
| `openspec/specs/docker-database-ownership-authority/spec.md` | `src/odoo_forge/database/types.py`, contratos de ownership en el core | `src/odoo_forge_postgres_docker/authority.py`, partes de `provider.py` | `tests/adapters/test_postgres_docker_authority.py`, cobertura relacionada en `tests/adapters/test_postgres_docker_provider.py` | Recovery, rollback y cleanup seguros para recursos Docker propiedad del adapter |
| `openspec/specs/credential-materialization/spec.md` | `src/odoo_forge/credentials/types.py`, `materialization.py`, `errors.py` | `src/odoo_forge_docker/credential_injection.py`, `src/odoo_forge_postgres_docker/secret_injection.py`, `target_handoffs.py` | `tests/credentials/test_materialization.py`, `tests/adapters/test_docker_provider.py`, `tests/adapters/test_postgres_docker_secret_injection.py` | Inyección de secretos en `forge run` y en el adapter PostgreSQL sin exponer plaintext |
| `openspec/specs/data-artifacts/spec.md` | `src/odoo_forge/data_artifacts/contracts.py`, `types.py` | `src/odoo_forge_postgres_docker/target_handoffs.py`, partes de `provider.py` | `tests/data_artifacts/test_contracts.py`, cobertura de restore en `tests/adapters/test_postgres_docker_provider.py` e integración | Restore-set opaco consumido por el adapter PostgreSQL; todavía sin flujo CLI general de restore |
| `openspec/specs/project-catalog-resolution/spec.md` | `src/odoo_forge/project_catalog/resolver.py`, `models.py`, `interfaces.py`, `validation.py` | ninguno canónico todavía; futuro consumer desde CLI o control-plane | `tests/project_catalog/test_resolver.py` | Capability foundation para futuros flujos de onboarding / environment request; sin command visible hoy |
| `openspec/specs/durable-operations/spec.md` | `src/odoo_forge/durable_operations/service.py`, `types.py`, `errors.py`, `src/odoo_forge/ports/durable_operation_store.py`, `durable_operation_recovery.py` | ninguno canónico todavía; futuro backing store fuera del core | `tests/durable_operations/test_service.py`, `tests/durable_operations/test_types.py`, `tests/ports/test_durable_operation_store.py` | Foundation para workflows largos o crash-sensitive; no expuesta hoy como flujo CLI directo |
| `openspec/specs/tenancy-contract/spec.md` | hoy no tiene módulos runtime dedicados en `src/`; actúa como contrato de plataforma para trabajo futuro | ninguno actual | sin suite dedicada en `tests/` todavía | Impacta diseño futuro de consumers SP-3, SP-4 y SP-8; no modifica commands actuales |

## Capacidades De Gobernanza Y Documentación

| Capability / spec aceptada | Módulos `src/` principales | Packages o tools relacionadas | Tests principales | Flujos visibles impactados |
| --- | --- | --- | --- | --- |
| `openspec/specs/platform-portfolio-documentation-integrity/spec.md` | sin impacto principal en `src/`; gobierna verdad documental y estado de portfolio | `docs/tools/platform_portfolio/validate.py`, `docs/specs/platform/portfolio.json` | `docs/tools/platform_portfolio/test_validate.py` | Validación de integridad de portfolio/documentación; no agrega commands `forge` |
| `openspec/specs/platform-subproject-governance/spec.md` | sin impacto principal en `src/`; define autoridad de planning/portfolio | docs de portfolio y roadmap | validación indirecta vía tooling/documentación | Scope y ownership de artifacts de plataforma, no runtime code |

## Pistas Rápidas De Mantenimiento

| Si cambia... | Empezá por... | Después verificá... |
| --- | --- | --- |
| Semántica de `project.yaml` o `project.lock` | `src/odoo_forge/manifest/` | `tests/manifest/` y `openspec/specs/manifest/spec.md` |
| Montajes, env o lifecycle del backend local | `src/odoo_forge/backend/` y `src/odoo_forge_docker/` | `tests/backend/`, `tests/adapters/`, `tests/cli/test_backend.py`, `openspec/specs/local-backend/spec.md` |
| Operaciones de image registry o resolución de artifacts publicados | `src/odoo_forge/image_registry/` y `src/odoo_forge_registry/` | `tests/ports/`, `tests/adapters/`, `tests/cli/test_image_registry.py`, `openspec/specs/image-registry-provider/spec.md` |
| Contracts neutrales de database lifecycle | `src/odoo_forge/database/` y `src/odoo_forge/ports/database_provider.py` | `tests/database/`, `tests/ports/test_database_provider.py`, `openspec/specs/database-provider/spec.md` |
| Implementación Docker PostgreSQL aislada | `src/odoo_forge_postgres_docker/` | tests adapter `test_postgres_docker_*` y la spec Docker correspondiente |
| Reglas de credenciales o restore artifacts | `src/odoo_forge/credentials/` o `src/odoo_forge/data_artifacts/` | tests específicos de capability y adapters consumidores |
| Gobernanza documental o estado del portfolio | `docs/specs/platform/portfolio.json` y `docs/tools/platform_portfolio/validate.py` | `openspec/specs/platform-portfolio-documentation-integrity/spec.md` |

## Límites Que Conviene Recordar

- `manifest`, `local-backend` e `image-registry-provider` sí impactan flujos CLI visibles hoy.
- `database-provider`, `docker-postgresql-database-adapter`, `credential-materialization`, `data-artifacts`, `project-catalog-resolution` y `durable-operations` están aceptadas como foundations, pero varias todavía no tienen un command `forge` canónico expuesto.
- `tenancy-contract` y las specs de gobernanza/documentación hoy condicionan diseño y autoridad más que wiring de runtime.
- Cuando una capability no tiene consumer CLI actual, cambiá primero el contrato core y sus tests; no inventes wiring visible sin autoridad explícita en spec o roadmap activo.
