-- Data-environment authority schema.
-- DDL only: additive and non-destructive, with no down-migration entry point.
CREATE TABLE IF NOT EXISTS public.data_environment_registry (
    environment_id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    lifecycle TEXT NOT NULL,
    policy_ref TEXT NOT NULL,
    relationships JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS public.raw_data_grants (
    operation_id TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    grantor TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL,
    audit_reference TEXT NOT NULL,
    PRIMARY KEY (operation_id, environment_id)
);
