import time
import requests
from urllib.parse import urlencode
from datetime import datetime, timezone
import json
from src.config import BRONZE, PAGE_CAP, ROOT, TOKEN

DISCOVER_URL = "https://api.themoviedb.org/3/discover/movie"
FILTERS = {
    "include_adult": False,
    "include_video": False, # exclude trailers and other videos
    "language": "en-US", # English movies only
    "sort_by": "popularity.desc",
    "primary_release_date.gte": "2018-01-01",
    "primary_release_date.lte": "2026-11-20",
}

def get_json(url, headers):
    for attempt in range(5):
        response = requests.get(url, headers=headers, timeout = 30)
        if response.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Gave up after retries: {url}")

def extract_discover():
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    discover_dir = BRONZE / "discover"
    discover_dir.mkdir(parents=True, exist_ok=True)
    
    written = []
    print(f"Extracting discover: {PAGE_CAP} pages")
    for page in range(1, PAGE_CAP + 1):
        params = {**FILTERS, "page": page}
        url = DISCOVER_URL + "?" + urlencode(params)
        try:
            payload = get_json(url, headers)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise RuntimeError(f"Discover page {page} failed with status {status}") from exc
        path = discover_dir / f"page={page:04d}.json"
        path.write_text(json.dumps(payload, indent=2))
        written.append(str(path))
        time.sleep(0.25)
    manifest = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "page_cap": PAGE_CAP,
        "filters": FILTERS,
        "files": written,
    }
    (BRONZE / "discover_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"extract discover: wrote {len(written)} files")
    return written

def fetch_detail(movie_id, headers, log_path):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    params = {"language": "en-US"}
    for attempt in range(5):
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if response.status_code == 200:
            return response.json()
        with log_path.open("a") as log:
            log.write(f"{movie_id}\t{response.status_code}\n")
        return None
    with log_path.open("a") as log:
        log.write(f"{movie_id}\t429\n")
    return None

def extract_details():
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "accept": "application/json",
    }
    movie_dir = BRONZE / "movie"
    movie_dir.mkdir(parents=True, exist_ok=True)
    log_path = ROOT / "logs" / "detail_failures.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    movie_ids = []
    for path in sorted((BRONZE / "discover").glob("page=*.json")):
        payload = json.loads(path.read_text())
        for movie in payload["results"]:
            movie_id = movie["id"]
            if movie_id not in seen:
                seen.add(movie_id)
                movie_ids.append(movie_id)
    skipped = 0
    written = 0
    failed = 0
    print(f"extract details: {len(movie_ids)} ids")
    for movie_id in movie_ids:
        path = movie_dir / f"movie_id={movie_id}.json"
        if path.exists():
            skipped += 1
            continue
        payload = fetch_detail(movie_id, headers, log_path)
        if payload is None:
            failed += 1
            continue
        path.write_text(json.dumps(payload))
        written += 1
        time.sleep(0.25)
    print(f"extract details: wrote {written}, skipped {skipped}, failed {failed}")
    return written
    

def main():
    extract_discover()
    extract_details()

if __name__ == "__main__":
    main()