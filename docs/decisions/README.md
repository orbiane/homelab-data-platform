# Architecture Decision Records

| ADR | Title | Date |
|---|---|---|
| [001](ADR-001-revenue-grain.md) | Revenue fact grain includes snapshot_date | 2026-07-05 |
| [002](ADR-002-raw-ingestion.md) | Raw ingestion via external_location, not seeds | 2026-07-05 |
| [003](ADR-003-time-dimension.md) | Semantic layer time axis is dt (processing date) | 2026-08-31 |
| [004](ADR-004-latest-snapshot-filter.md) | Latest snapshot filter lives in the semantic model | 2026-08-31 |
| [005](ADR-005-quality-flags-and-currency.md) | No quality-flag exclusion; currency mixing left unresolved | 2026-08-31 |
| [006](ADR-006-generated-data-version.md) | Pin generated data by sha256; current CSVs are the baseline | 2026-10-28 |
| [007](ADR-007-definition-change-guard.md) | Definition changes must cite a human decision memo | 2026-11-06 |
| [008](ADR-008-autonomous-loop.md) | Work is defined in NEXT.md; an unattended loop opens PRs; the owner approves by merging | 2026-11-08 |
| [009](ADR-009-build-then-analyze.md) | Build everything first, evaluate afterwards; provisional decisions are recorded | 2026-11-08 |

ADR numbers reserved by work orders (written when that work is done): 010 = the second baseline data version (V2), 011 = the power-data project design (P1), 012 = the nightly watch (W2). Work PRs do not edit this index; it is updated after merging (ADR-009).

ADR-005 is the one worth reading if you only read one.
