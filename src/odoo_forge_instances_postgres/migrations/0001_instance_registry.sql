-- Instance registry schema.
-- DDL only: additive and non-destructive, with no down-migration entry point.
-- Reverting this file's code must never destroy control-plane data.
CREATE TABLE IF NOT EXISTS public.instance_registry (
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    resource_identifier TEXT NOT NULL,
    resource_kind TEXT NOT NULL,
    resource_ownership TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, instance_id)
);
