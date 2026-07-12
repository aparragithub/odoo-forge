## Native Review Policy

- Change: `CAP-PROJECT-CATALOG`
- Lineage: `cap-project-catalog-v4`
- Mode: `ordinary`
- Risk tier: `STANDARD`
- Initial lens set: `readability`
- Review scope: current repository changes for the authored project-catalog slice plus its OpenSpec artifacts in the parallel worktree.
- Review constraints: read-only review, no product-code edits, no remediation unless a bounded native review finding requires it.
- Verification binding: final approval is bound to `openspec/changes/CAP-PROJECT-CATALOG/verify-report.md` and must reuse existing verify evidence rather than rerunning unrelated phases.
