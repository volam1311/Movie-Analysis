import argparse
import time
import requests
from urllib.parse import urlencode
from datetime import date, datetime, timedelta, timezone
import json
from src.config import BRONZE, RELEASE_START, ROOT, TOKEN

DISCOVER_URL = "https://api.themoviedb.org/3/discover/movie"
TMDB_MAX_PAGES = 500  # Discover rejects any page above this
FILTERS = {
    "include_adult": False,
    "include_video": False,  # exclude trailers and other videos
    "language": "en-US",
    "sort_by": "popularity.desc",
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

def fetch_discover_page(gte, lte, page, headers):
    params = {
        **FILTERS,
        "primary_release_date.gte": gte,
        "primary_release_date.lte": lte,
        "page": page,
    }
    url = DISCOVER_URL + "?" + urlencode(params)
    try:
        return get_json(url, headers)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        raise RuntimeError(
            f"Discover {gte}..{lte} page {page} failed with status {status}"
        ) from exc


def window_is_capped(payload):
    total_pages = int(payload.get("total_pages") or 0)
    total_results = int(payload.get("total_results") or 0)
    return total_pages >= TMDB_MAX_PAGES or total_results > TMDB_MAX_PAGES * 20


def save_page(discover_dir, gte, lte, page, payload, written):
    path = discover_dir / f"gte={gte}_lte={lte}_page={page:04d}.json"
    path.write_text(json.dumps(payload))
    written.append(str(path))


def crawl_window(gte, lte, headers, discover_dir, written):
    first = fetch_discover_page(gte, lte, 1, headers)
    time.sleep(0.25)
    if window_is_capped(first):
        start = date.fromisoformat(gte)
        end = date.fromisoformat(lte)
        if start >= end:
            raise RuntimeError(
                f"Discover {gte}..{lte} exceeds {TMDB_MAX_PAGES} pages and cannot be split"
            )
        mid = start + (end - start) // 2
        print(f"splitting {gte}..{lte}: {first.get('total_results')} results")
        crawl_window(gte, mid.isoformat(), headers, discover_dir, written)
        crawl_window((mid + timedelta(days=1)).isoformat(), lte, headers, discover_dir, written)
        return

    total_pages = int(first.get("total_pages") or 0)
    if total_pages == 0:
        print(f"discover {gte}..{lte}: 0 pages")
        return

    save_page(discover_dir, gte, lte, 1, first, written)
    print(f"discover {gte}..{lte}: page 1/{total_pages}")
    for page in range(2, total_pages + 1):
        payload = fetch_discover_page(gte, lte, page, headers)
        save_page(discover_dir, gte, lte, page, payload, written)
        time.sleep(0.25)
        if page == total_pages or page % 25 == 0:
            print(f"discover {gte}..{lte}: page {page}/{total_pages}")


def extract_discover(release_start=RELEASE_START):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    discover_dir = BRONZE / "discover"
    discover_dir.mkdir(parents=True, exist_ok=True)

    start = date.fromisoformat(release_start)
    release_end = date.today()
    if start > release_end:
        raise SystemExit(f"start {release_start} is after today {release_end.isoformat()}")

    written = []
    print(f"extract discover: {start.isoformat()} through {release_end.isoformat()}")
    crawl_window(start.isoformat(), release_end.isoformat(), headers, discover_dir, written)

    manifest = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "release_start": start.isoformat(),
        "release_end": release_end.isoformat(),
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
    for path in sorted((BRONZE / "discover").glob("gte=*_page=*.json")):
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start",
        default=RELEASE_START,
        help="First primary release date, YYYY-MM-DD. The end date is always today.",
    )
    args = parser.parse_args()
    extract_discover(args.start)
    extract_details()

if __name__ == "__main__":
    main()