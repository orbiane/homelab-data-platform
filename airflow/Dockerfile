FROM apache/airflow:3.3.0

USER airflow

# dbt は Airflow 本体と依存が衝突しうるので独立 venv に隔離する
RUN python -m venv /home/airflow/dbt_venv && \
    /home/airflow/dbt_venv/bin/pip install --no-cache-dir \
        "dbt-core==1.11.8" \
        "dbt-duckdb==1.10.1"
