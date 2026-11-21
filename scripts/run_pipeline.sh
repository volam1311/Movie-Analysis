#!/usr/bin/env bash
# Run the whole pipeline in order, stopping at the first failure.
# Same steps as dags/movie_etl.py. Used by the Docker image and GitHub Actions.
#
# Run from anywhere; paths are resolved from this script's location.
# Set SKIP_PUBLISH=1 to stop after dbt (no Databricks writes).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() { echo; echo "==> $*"; }

step "extract (TMDB -> data/bronze)"
python -m src.extract

step "validate bronze"
python -m src.validate

step "load (bronze -> DuckDB raw)"
python -m src.load

# dbt build = run + test in dependency order; a failing test skips downstream models
# and exits non-zero, so publish never sees untested tables.
step "dbt build (staging + marts + tests)"
(cd movie_dbt && dbt build --profiles-dir .)

if [[ "${SKIP_PUBLISH:-0}" == "1" ]]; then
    step "publish skipped (SKIP_PUBLISH=1)"
    exit 0
fi

step "publish gold (DuckDB marts -> Databricks)"
python -m src.export_gold

step "pipeline finished"
