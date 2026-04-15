# homelab-data-platform

A hands-on learning project: building a modern data stack with dbt, DuckDB, Airflow, and Semantic Layer on a local Apple Silicon cluster.

## Architecture

TODO: Add architecture diagram after Phase 5-1 completion.

## Project Structure

- `dbt_project/` — dbt models (raw → staging → mart → semantic layer)
- `data_generation/` — Synthetic data generation scripts (Messaging SaaS domain)
- `airflow/` — Workflow orchestration (DAGs)
- `cube/` — Cube Core evaluation
- `agent/` — LLM agent integration
- `docs/` — Design decisions (ADR) and analysis reports

## Domain

Simulated Messaging SaaS platform data — accounts, friends, message deliveries, segments, and engagement metrics.

## Tech Stack

- **Transformation**: dbt-core + dbt-duckdb
- **Database**: DuckDB (local, zero-config)
- **Orchestration**: Apache Airflow (Docker)
- **Semantic Layer**: dbt Semantic Layer (MetricFlow)
- **LLM Integration**: MCP Server + local LLM (Ollama)
