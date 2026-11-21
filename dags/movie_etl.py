# EXAMPLE — shape of the DAG. Fill in the real module commands you already run.
from datetime import datetime, timedelta, timezone

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

LOCAL = timezone(timedelta(hours=10))

PROJECT = "/Users/mymac/Documents/DA Project/Movie Analysis"
PY = f'"{PROJECT}/.venv/bin/python"'
DBT = f'"{PROJECT}/.venv/bin/dbt"'

with DAG(
    dag_id="movie_etl",
    start_date=datetime(2026, 1, 1, tzinfo=LOCAL),
    schedule="0 6 * * 1",  # 06:00 every Monday, UTC+10
    catchup=False,
    tags=["movies"],
) as dag:
    extract = BashOperator(
        task_id="extract",
        bash_command=f'cd "{PROJECT}" && {PY} -m src.extract',
    )
    validate = BashOperator(
        task_id="validate_bronze",
        bash_command=f'cd "{PROJECT}" && {PY} -m src.validate',
    )
    load = BashOperator(
        task_id="load_raw",
        bash_command=f'cd "{PROJECT}" && {PY} -m src.load',
    )
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f'cd "{PROJECT}/movie_dbt" && {DBT} run',
    )
    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f'cd "{PROJECT}/movie_dbt" && {DBT} test',
    )
    publish_gold = BashOperator(
        task_id="publish_gold",
        bash_command=f'cd "{PROJECT}" && {PY} -m src.export_gold',
    )

    extract >> validate >> load >> dbt_run >> dbt_test >> publish_gold
