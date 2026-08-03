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

-- Lineage/receipt evidence for authoritative registrations. Additive and
-- nullable: legacy rows written before this evidence existed keep NULL
-- values rather than fabricated legacy evidence.
ALTER TABLE public.instance_registry
    ADD COLUMN IF NOT EXISTS operation_id TEXT,
    ADD COLUMN IF NOT EXISTS request_digest TEXT,
    ADD COLUMN IF NOT EXISTS owned_resource_ids TEXT[],
    ADD COLUMN IF NOT EXISTS live_proof_expected BOOLEAN;

CREATE UNIQUE INDEX IF NOT EXISTS instance_registry_operation_id_key
    ON public.instance_registry (operation_id)
    WHERE operation_id IS NOT NULL;
