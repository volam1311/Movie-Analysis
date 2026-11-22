import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

TOKEN = os.environ["READACCESS_TOKEN"]
BRONZE = ROOT / "data" / "bronze"
# Default first release date. Any YYYY-MM-DD is valid.
# The extract end date is always the day the command runs.
RELEASE_START = "2018-01-01"
# Keep only movies with at least this many TMDB votes. Drops the long tail of
# obscure titles that have no budget/revenue data. About 9.7k movies from 2018
# at 50 (vs 16.7k at 20); lower it and the run takes longer.
MIN_VOTE_COUNT = 50
