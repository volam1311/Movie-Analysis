import duckdb
from src.config import BRONZE, ROOT

DB_PATH = ROOT / "data" / "warehouse.duckdb"

def main():
    # Same id in two files: keep the row from the first filename.
    glob = str(BRONZE / "movie" / "*.json")
    conn = duckdb.connect(str(DB_PATH))
    try:
        conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
        conn.execute(
            """
            CREATE OR REPLACE TABLE raw.movie_detail AS
            SELECT * EXCLUDE (filename), current_timestamp AS loaded_at
            FROM read_json_auto(?, union_by_name = true, filename = true)
            QUALIFY row_number() OVER (PARTITION BY id ORDER BY filename) = 1
            """,
            [glob],
        )
        rows = conn.execute("SELECT count(*) FROM raw.movie_detail").fetchone()[0]
        print(f"load raw.movie_detail: {rows} rows")
    finally:
        conn.close()

if __name__ == "__main__":
    main()