# homelab-data-platform

A local-first modern data stack built from scratch on Apple Silicon:
dbt + DuckDB + Airflow + MetricFlow semantic layer, with intentionally
dirty synthetic data to study how metric definitions fail in practice.

The goal is not "it runs" but "why it was designed this way" - every
significant decision is recorded as an ADR under `docs/decisions/`.

## Architecture

```text
CSV (synthetic, seeded)
      |
      v
  dbt sources          external_location, not seeds
      |                (enables source freshness checks)
      v
  staging (view)       quality issues are FLAGGED, never removed
      |                is_valid_id / is_late_arrival / is_latest_snapshot
      v
  mart (table)         thin mart: no aggregation, no joins
      |                dim_account + fct_subscription / fct_message_event / fct_revenue
      v
  semantic layer       MetricFlow: entities, dimensions, measures
      |                joins are declared here, not in mart
      v
  mf query             deterministic SQL generation
```

Airflow (Docker, LocalExecutor) runs `dbt build` daily at 03:00 JST.

## Design principles

**Thin mart, thick semantic layer.** The mart layer produces reliable
tables and nothing else - no aggregation, no joins. Joins are declared
as entities in the semantic layer, so one definition serves every query
shape.

**Dirty data is flagged, not cleaned.** Staging models mark quality
problems with boolean columns and pass every row through. Removing bad
rows would hide the fact that they exist. Exclusion is a decision for
the consuming layer, not a silent default.

**Reproducible synthetic data.** All generators use fixed seeds, so
anyone can reproduce byte-identical CSVs and observe the same failures.

## What this project demonstrates

The semantic layer prevented one class of error and failed to prevent
another.

Revenue snapshots are structurally protected against double counting.
The fact table keeps every snapshot of every month, so a naive
`SUM(revenue_amount)` overcounts. The filter lives inside the measure
definition, so no query through the semantic layer can bypass it.

Currency mixing is not protected. JPY and USD are summed without
conversion, producing a plausible but meaningless total - with no error
and no warning.

The difference: row selection can be encoded in a definition, while
unit semantics cannot - it requires external information the definition
does not have. This is a concrete counterexample to "a solid definition
makes metrics safe."

See `docs/decisions/` for the full reasoning.

## Reproduce

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and Docker.

```bash
# 1. Generate the synthetic CSVs (seeded, deterministic)
cd data_generation
uv sync
uv run python -m generators.account_master
uv run python -m generators.subscription
uv run python -m generators.message_event
uv run python -m generators.revenue_monthly

# 2. Install dbt and MetricFlow
uv tool install dbt-core==1.11.8 \
  --with dbt-duckdb==1.10.1 \
  --with "dbt-metricflow[dbt-duckdb]"

# 3. Configure ~/.dbt/profiles.yml
#    profile: dbt_project / type: duckdb / path: warehouse.duckdb

# 4. Build
cd ../dbt_project
dbt build

# 5. Query metrics
export DBT_PROFILES_DIR=~/.dbt
mf list metrics
mf query --metrics ctr --group-by account__industry
mf query --metrics revenue_amount --group-by revenue_record__currency
```

The last query is the interesting one - it shows the currency problem
described above.

To run the orchestration layer:

```bash
cd airflow
docker compose up -d          # UI on 127.0.0.1:8081
```

## Metrics

| Metric | Type | Notes |
|---|---|---|
| `subscription_count` | simple | All rows, including orphaned account ids |
| `delivered_count` | simple | Long-format table: filtered by event type |
| `clicked_count` | simple | Same |
| `ctr` | ratio | clicked / delivered |
| `revenue_amount` | simple | Latest snapshot only; currency NOT converted |

## Project structure

| Path | Contents |
|---|---|
| `dbt_project/` | sources to staging to mart to semantic layer |
| `data_generation/` | Seeded synthetic data generators |
| `airflow/` | Airflow 3.3 on Docker Compose, LocalExecutor |
| `docs/decisions/` | Architecture Decision Records |
| `docs/analysis/` | Analysis reports |

## Tech stack

| Layer | Tool | Version |
|---|---|---|
| Transformation | dbt-core + dbt-duckdb | 1.11.8 / 1.10.1 |
| Warehouse | DuckDB | 1.5 |
| Orchestration | Apache Airflow | 3.3.0 |
| Semantic layer | MetricFlow | 0.14.0 |

## Domain

Synthetic data for a fictional messaging SaaS: accounts, subscriptions,
message delivery events (long format), and monthly revenue with
snapshot history. All data is generated, not derived from any real
system.

## License

MIT
