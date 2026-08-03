from datetime import datetime, timedelta

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

DBT_DIR = "/opt/airflow/homelab/dbt_project"
DBT_BIN = "/home/airflow/dbt_venv/bin/dbt"

default_args = {
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="dbt_build",
    description="Run dbt build on the homelab DuckDB warehouse",
    start_date=datetime(2026, 8, 1),
    # UTC 18:00 = JST 03:00。Airflow の cron は UTC 基準で動く
    schedule="0 18 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["dbt", "duckdb"],
) as dag:
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {DBT_DIR} && {DBT_BIN} build",
    )
