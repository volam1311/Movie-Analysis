"""Publish the dbt marts (DuckDB schema `marts`) to Databricks `<catalog>.<schema>`.

Run only after `dbt test` passes. Each run replaces the tables; it never appends
and never changes values.
"""
import datetime as dt
import logging
import math
import os

import certifi
import duckdb
from databricks import sql as dbsql

from src.config import ROOT
from src.load import DB_PATH  # importing src.config (via src.load) also loads .env

LOG_PATH = ROOT / "logs" / "publish_gold.log"

TABLES = ("fact_movie", "bridge_movie_genre", "dim_date", "dim_language")
BATCH_SIZE = 500  # rows per INSERT statement

# DuckDB type -> Databricks type. Anything else fails loudly instead of guessing.
TYPE_MAP = {
    "BOOLEAN": "BOOLEAN",
    "INTEGER": "INT",
    "BIGINT": "BIGINT",
    "DOUBLE": "DOUBLE",
    "VARCHAR": "STRING",
    "DATE": "DATE",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMP",
}

REQUIRED_ENV = (
    "DATABRICKS_SERVER_HOSTNAME",
    "DATABRICKS_HTTP_PATH",
    "DATABRICKS_TOKEN",
    "DATABRICKS_CATALOG",
    "DATABRICKS_SCHEMA",
)


def setup_log():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler(),
        ],
        force=True,
    )
    logging.getLogger("databricks.sql").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def read_env():
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing environment variables: {', '.join(missing)}")
    return {name: os.environ[name] for name in REQUIRED_ENV}


def quote_ident(name):
    return f"`{name.replace('`', '``')}`"


def sql_literal(value):
    """Render a Python value as a Databricks SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):  # check before int: bool is a subclass of int
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "NULL"
        return repr(value)
    if isinstance(value, dt.datetime):
        return f"TIMESTAMP '{value.isoformat(sep=' ')}'"
    if isinstance(value, dt.date):
        return f"DATE '{value.isoformat()}'"
    if isinstance(value, str):
        # Databricks treats backslash as an escape character inside string literals.
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    raise TypeError(f"unsupported value type {type(value).__name__}: {value!r}")


def read_marts():
    """Read every mart into memory, then release the DuckDB file lock."""
    marts = {}
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        for table in TABLES:
            exists = conn.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'marts' AND table_name = ?",
                [table],
            ).fetchone()[0]
            if not exists:
                raise SystemExit(
                    f"marts.{table} not found in DuckDB. Run `dbt build` first "
                    "(and check the generate_schema_name macro)."
                )
            columns = conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'marts' AND table_name = ? ORDER BY ordinal_position",
                [table],
            ).fetchall()
            rows = conn.execute(f"SELECT * FROM marts.{table}").fetchall()
            marts[table] = (columns, rows)
    finally:
        conn.close()
    return marts


def databricks_type(table, column, duck_type):
    if duck_type in TYPE_MAP:
        return TYPE_MAP[duck_type]
    if duck_type.startswith("DECIMAL"):
        return duck_type
    raise SystemExit(f"{table}.{column}: no Databricks mapping for DuckDB type {duck_type}")


def publish_table(cursor, target, table, columns, rows):
    column_defs = ", ".join(
        f"{quote_ident(name)} {databricks_type(table, name, duck_type)}"
        for name, duck_type in columns
    )
    cursor.execute(f"CREATE OR REPLACE TABLE {target} ({column_defs})")

    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        values = ",\n".join(
            "(" + ", ".join(sql_literal(v) for v in row) + ")" for row in batch
        )
        cursor.execute(f"INSERT INTO {target} VALUES\n{values}")

    cursor.execute(f"SELECT count(*) FROM {target}")
    published = cursor.fetchone()[0]
    if published != len(rows):
        raise SystemExit(f"{target}: row count mismatch (DuckDB {len(rows)}, Databricks {published})")
    print(f"publish {target}: {published} rows")


def main():
    # python.org builds on macOS ship with no default CA file, so Databricks
    # looks like a self-signed certificate. Point verification at certifi.
    os.environ["SSL_CERT_FILE"] = certifi.where()
    os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

    setup_log()
    log = logging.getLogger("publish_gold")
    log.info("publish started; errors also go to %s", LOG_PATH)
    log.info("TLS certificates: %s", certifi.where())
    try:
        env = read_env()
        marts = read_marts()
        counts = ", ".join(f"{name}={len(rows)}" for name, (_, rows) in marts.items())
        log.info("read DuckDB marts: %s", counts)
        log.info(
            "connecting to host %s path %s catalog %s schema %s",
            env["DATABRICKS_SERVER_HOSTNAME"],
            env["DATABRICKS_HTTP_PATH"],
            env["DATABRICKS_CATALOG"],
            env["DATABRICKS_SCHEMA"],
        )

        catalog = quote_ident(env["DATABRICKS_CATALOG"])
        schema = quote_ident(env["DATABRICKS_SCHEMA"])

        conn = dbsql.connect(
            server_hostname=env["DATABRICKS_SERVER_HOSTNAME"],
            http_path=env["DATABRICKS_HTTP_PATH"],
            access_token=env["DATABRICKS_TOKEN"],
        )
        try:
            with conn.cursor() as cursor:
                log.info("session open; creating schema %s.%s", env["DATABRICKS_CATALOG"], env["DATABRICKS_SCHEMA"])
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
                for table in TABLES:
                    columns, rows = marts[table]
                    target = f"{catalog}.{schema}.{quote_ident(table)}"
                    log.info("replacing %s (%s rows)", target, len(rows))
                    publish_table(cursor, target, table, columns, rows)
        finally:
            conn.close()
        log.info("publish finished")
    except SystemExit as exc:
        log.error("%s", exc)
        raise
    except Exception:
        log.exception("publish failed")
        raise


if __name__ == "__main__":
    main()
