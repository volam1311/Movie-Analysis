import json
from pathlib import Path

import duckdb
from src.config import BRONZE, ROOT

DB_PATH = ROOT / "data" / "warehouse.duckdb"


def current_detail_files():
    """Detail files for movies in the current Discover crawl.

    data/bronze/movie/ keeps details from earlier crawls (so re-runs skip them),
    which can include movies outside the current dates or vote filter.
    """
    ids = set()
    for path in (BRONZE / "discover").glob("gte=*_page=*.json"):
        ids |= {movie["id"] for movie in json.loads(path.read_text())["results"]}
    files = [BRONZE / "movie" / f"movie_id={movie_id}.json" for movie_id in sorted(ids)]
    return [str(path) for path in files if path.exists()]


def main():
    files = current_detail_files()
    if not files:
        raise SystemExit("load: no detail files for the current crawl")
    # One NDJSON file, schema inferred from every row. read_json over thousands of
    # files with union_by_name runs DuckDB out of memory, and without it the schema
    # comes from a sample and mistypes nested fields like genres.
    combined = ROOT / "data" / "movie_detail.ndjson"
    with combined.open("w") as out:
        for path in files:
            out.write(json.dumps(json.loads(Path(path).read_text())) + "\n")
    conn = duckdb.connect(str(DB_PATH))
    try:
        conn.execute("CREATE SCHEMA IF NOT EXISTS raw")
        conn.execute(
            """
            CREATE OR REPLACE TABLE raw.movie_detail AS
            SELECT *, current_timestamp AS loaded_at
            FROM read_json_auto(?, format = 'newline_delimited', sample_size = -1)
            """,
            [str(combined)],
        )
        rows = conn.execute("SELECT count(*) FROM raw.movie_detail").fetchone()[0]
        print(f"load raw.movie_detail: {rows} rows from {len(files)} files")
    finally:
        conn.close()
        combined.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
