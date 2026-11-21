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