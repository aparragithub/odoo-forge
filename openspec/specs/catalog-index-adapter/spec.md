# Catalog Index Adapter Specification

## Purpose

Define the concrete adapter that implements the `CatalogIndex` Protocol
(`odoo_forge.project_catalog.interfaces.CatalogIndex`) against a declarative
catalog source, plus its composition-root wiring. This gives
`ProjectCatalogResolver` its first real caller without changing resolver
behavior.

## Requirements

### Requirement: Concrete CatalogIndex Adapter

The system MUST provide a concrete class in a new top-level package (e.g.
`src/odoo_forge_catalog/`) that structurally satisfies `CatalogIndex` and
implements `find_matches(request: ProjectCatalogRequest) -> list[CatalogRecord]`
by reading from a declarative catalog source. The adapter MUST NOT perform
resolution, ambiguity handling, or defaulting logic — it MUST return every
matching record as-is and let `ProjectCatalogResolver` own tie-breaking and
failure classification.

#### Scenario: Structural conformance via isinstance

- GIVEN an instance of the concrete catalog adapter
- WHEN checked with `isinstance(adapter, CatalogIndex)`
- THEN the check MUST pass without explicit inheritance from the Protocol

#### Scenario: Matching request returns matching records

- GIVEN a catalog source containing one record whose identifiers satisfy a
  normalized `ProjectCatalogRequest`
- WHEN `find_matches(request)` is called
- THEN it MUST return a list containing exactly that `CatalogRecord`

#### Scenario: Non-matching request returns an empty list

- GIVEN a catalog source with no record matching the supplied request
  identifiers
- WHEN `find_matches(request)` is called
- THEN it MUST return an empty list, never raise, and never fabricate a
  record

#### Scenario: Ambiguous match passes through unresolved

- GIVEN a catalog source containing more than one record matching the
  supplied request identifiers
- WHEN `find_matches(request)` is called
- THEN it MUST return all matching records without picking a winner,
  leaving ambiguity classification to `ProjectCatalogResolver`

### Requirement: Composition-Root Factory

The CLI composition root MUST expose a `_make_catalog_index()` factory in
`src/odoo_forge_cli/_composition.py` that constructs and returns the
concrete adapter, following the same shape as `_make_workspace_provider` /
`_make_backend_provider`. Callers MUST depend only on the `CatalogIndex`
Protocol type, never on the concrete adapter class.

#### Scenario: Factory returns a protocol-conforming instance

- GIVEN `_make_catalog_index()` is called with no arguments
- WHEN the returned value is checked with `isinstance(result, CatalogIndex)`
- THEN the check MUST pass

### Requirement: Import Boundary Isolation

The new adapter package MUST be registered in `pyproject.toml` in all three
required spots: `[tool.hatch.build.targets.wheel].packages`,
`[tool.importlinter].root_packages`, and a dedicated forbidden-import
contract preventing `odoo_forge` (core) from importing the adapter package.
`odoo_forge` MUST continue to depend only on the `CatalogIndex` Protocol.

#### Scenario: import-linter enforces purity

- GIVEN the updated `pyproject.toml` import-linter configuration
- WHEN CI runs `lint-imports`
- THEN all contracts are kept, including the new one forbidding `odoo_forge`
  from importing the catalog adapter package
