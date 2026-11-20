import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

TOKEN = os.environ["READACCESS_TOKEN"]
BRONZE = ROOT / "data" / "bronze"
PAGE_CAP = 5