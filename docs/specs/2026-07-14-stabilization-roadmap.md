# Hoja De Ruta De Estabilización 2026-07-14

> **Documento de secuencia e historia preservada.** La fuente estructural y canónica para estado,
> dependencias, evidencia y handoffs es [`docs/specs/platform/portfolio.json`](platform/portfolio.json).
> La serie de mantenimiento vigente empieza en [`docs/00-master-index.md`](../00-master-index.md).
> Los changes archivados en `openspec/changes/archive/` se preservan como evidencia y no se
> reescriben para simular actualidad.

**Estado de vigencia:** roadmap fechada, útil como contexto de estabilización y secuencia de revisión.

## Estado Relevante

| Area | State | Evidence |
|---|---|---|
| Real-Docker baseline | Complete | Archived `stabilize-real-docker-baseline` verification report |
| Manifest layer and override semantics | Complete | Archived `decide-manifest-layer-override-semantics` change |
| Backend materialized-state planning | Complete | Archived `make-backend-planning-consume-materialized-state` change |
| First Docker PostgreSQL adapter | Complete and archived as superseded planning | `2026-07-15-CHG-DATABASE-ADAPTER-VERIFICATION-CLOSURE/verify-report.md` and `S62` |
| Unit 4 registry, Git, and workspace runtime-risk recheck | Separate future scope | Requires its own bounded SDD change |
| Local example Odoo runtime | Practical MVP achieved | `docs/22-example-runtime-guide.md` documents the runnable local flow |

`S62` resolves to the preserved real-Docker receipt in
[`CHG-FIRST-DATABASE-ADAPTER/apply-progress.md`](../../openspec/changes/archive/2026-07-16-CHG-FIRST-DATABASE-ADAPTER/apply-progress.md).
The archived closure independently records five passing real-Docker adapter scenarios.

## Inventario OpenSpec Vigente

Este inventario debe reflejar únicamente directorios no archivados bajo `openspec/changes/`.

| Change vivo | Clasificación | Siguiente paso correcto |
|---|---|---|
| [`sp-data-environments`](../../openspec/changes/sp-data-environments/proposal.md) | Activo pero bloqueado | Mantenerlo como único change vivo, sin tomarlo como próximo paso MVP; reanudar solo cuando `WF-DATA-COPY`, `CAP-RESOURCE-OWNERSHIP` y `SP-CONTROL-PLANE-AUTHORITY` tengan evidencia aceptada. |

`sp-data-environments` sigue siendo el único change activo del árbol vivo; esta roadmap no cambia sus prerequisitos, pero sí aclara que no es el siguiente outcome práctico a implementar.

`refresh-platform-roadmap-after-stabilization` ya no forma parte del inventario activo: quedó archivado en [`archive/2026-07-17-refresh-platform-roadmap-after-stabilization/`](../../openspec/changes/archive/2026-07-17-refresh-platform-roadmap-after-stabilization/). Lo mismo aplica a `fix-roadmap-refresh-verification-closure`, preservado bajo [`archive/2026-07-16-fix-roadmap-refresh-verification-closure/`](../../openspec/changes/archive/2026-07-16-fix-roadmap-refresh-verification-closure/).

`CHG-FIRST-DATABASE-ADAPTER` está archivado como superseded. Su cierre trazable sigue en [`archive/2026-07-16-CHG-FIRST-DATABASE-ADAPTER/archive-report.md`](../../openspec/changes/archive/2026-07-16-CHG-FIRST-DATABASE-ADAPTER/archive-report.md).

## Qué Sigue Ahora

1. Tratar como logrado el primer MVP técnico práctico: una instancia Odoo local real y corrible sobre el baseline ya aceptado de Docker, PostgreSQL y credenciales. La guía operativa quedó en [`docs/22-example-runtime-guide.md`](../22-example-runtime-guide.md).
2. Implementar `SP-DEVELOPER-ONBOARDING` como próximo SDD y siguiente outcome práctico visible con `forge onboard <cliente>`, apoyado en `CAP-PROJECT-CATALOG`, `CAP-SOURCE`, `CAP-WORKSPACE`, `CAP-LOCAL-BACKEND`, `CAP-CREDENTIALS` y los adapters locales ya aceptados.
3. Después cerrar los enablers transversales que siguen faltando para datos administrados: `CAP-RESOURCE-OWNERSHIP`, `WF-DATA-COPY` y `SP-CONTROL-PLANE-AUTHORITY`.
4. Recién después retomar `SP-DATA-ENVIRONMENTS` como outcome posterior de entornos de datos administrados.

`.scratch/dev-onboarding/spec.md` debe leerse como spec primaria de `SP-DEVELOPER-ONBOARDING`, no como avance primario de `SP-DATA-ENVIRONMENTS`.

## Secuencia De Lectura Actual

1. Usá `portfolio.json` para claims actuales de estado, dependencias y evidencia.
2. Usá [`docs/00-master-index.md`](../00-master-index.md) y la serie `01` a `21` para navegación de mantenimiento.
3. Tratá esta roadmap como contexto de estabilización e historial de secuencia, no como fuente autoritativa de trabajo OpenSpec vivo.
4. Tomá `SP-DEVELOPER-ONBOARDING` como próximo SDD y siguiente outcome práctico, y `sp-data-environments` como change vivo posterior, todavía bloqueado.
5. No inicies implementación de `sp-data-environments` mientras sigan faltando sus handoffs aceptados.

## No Objetivos Explícitos

- Rewriting archived OpenSpec, verification reports, receipts, or dated roadmaps.
- Treating achieved provider-neutral contracts as runtime integration.
- Folding Unit 4, runtime cutover, coordinated data copy, control-plane authority, or managed
  environments into the current documentation change.
- Starting `sp-data-environments` while it remains blocked.
