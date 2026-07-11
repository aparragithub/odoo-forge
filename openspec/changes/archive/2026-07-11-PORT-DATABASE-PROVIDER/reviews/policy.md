## Native Review Policy

- Change: `PORT-DATABASE-PROVIDER`
- Lineage: `port-database-provider`
- Mode: `ordinary_4r`
- Risk tier: `HOT-PATH-TIER-3`
- Initial lens set: `risk`, `readability`, `reliability`, `resilience`
- Review scope: current repository changes for the authored provider/database slice plus its OpenSpec artifacts, with only the explicit intended-untracked manifest admitted into the candidate tree.
- Review constraints: read-only review, no product-code edits, no remediation unless a bounded native review finding requires it.
- Verification binding: final approval is bound to `openspec/changes/PORT-DATABASE-PROVIDER/verify-report.md` and must reuse existing verify evidence rather than rerunning planning or unrelated phases.
