import argparse
import time
import requests
from urllib.parse import urlencode
from datetime import date, datetime, timedelta, timezone
import json
from src.config import BRONZE, MIN_VOTE_COUNT, RELEASE_START, ROOT, TOKEN

DISCOVER_URL = "https://api.themoviedb.org/3/discover/movie"
TMDB_MAX_PAGES = 500  # Discover rejects any page above this
MANIFEST = BRONZE / "discover_manifest.json"


def build_filters(min_votes=MIN_VOTE_COUNT):
    return {
        "include_adult": False,
        "include_video": False,  # exclude trailers and other videos
        "language": "en-US",
        "sort_by": "popularity.desc",
        "vote_count.gte": min_votes,
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

def fetch_discover_page(gte, lte, page, headers, filters):
    params = {
        **filters,
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


def write_atomic(path, payload):
    """Write JSON via a temp file, so an interrupted run never leaves half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(path)


def read_saved(path):
    """Return the saved page, or None if it is missing or unreadable."""
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def get_page(gte, lte, page, headers, filters, discover_dir, written):
    """Reuse a page saved by an interrupted run of the same crawl, else fetch it."""
    path = discover_dir / f"gte={gte}_lte={lte}_page={page:04d}.json"
    payload = read_saved(path)
    if payload is None:
        payload = fetch_discover_page(gte, lte, page, headers, filters)
        write_atomic(path, payload)
        time.sleep(0.25)
    written.append(str(path))
    return payload


def crawl_window(gte, lte, headers, filters, discover_dir, written):
    path = discover_dir / f"gte={gte}_lte={lte}_page=0001.json"
    first = read_saved(path)
    fetched = first is None
    if fetched:
        first = fetch_discover_page(gte, lte, 1, headers, filters)
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
        crawl_window(gte, mid.isoformat(), headers, filters, discover_dir, written)
        crawl_window((mid + timedelta(days=1)).isoformat(), lte, headers, filters,
                     discover_dir, written)
        return

    total_pages = int(first.get("total_pages") or 0)
    if total_pages == 0:
        print(f"discover {gte}..{lte}: 0 pages")
        return

    if fetched:
        write_atomic(path, first)
    written.append(str(path))
    print(f"discover {gte}..{lte}: page 1/{total_pages}")
    for page in range(2, total_pages + 1):
        get_page(gte, lte, page, headers, filters, discover_dir, written)
        if page == total_pages or page % 25 == 0:
            print(f"discover {gte}..{lte}: page {page}/{total_pages}")


def start_or_resume(release_start, filters, fresh):
    """Return the crawl's end date, resuming an unfinished crawl with the same settings.

    The end date is frozen in the manifest when a crawl starts, so a resume next
    day splits the date range the same way and reuses the saved pages.
    """
    discover_dir = BRONZE / "discover"
    state = read_saved(MANIFEST) or {}
    if (
        not fresh
        and state.get("status") == "in_progress"
        and state.get("release_start") == release_start
        and state.get("filters") == filters
    ):
        print(f"resuming unfinished crawl started {state.get('started_at')}")
        return date.fromisoformat(state["release_end"])

    # New crawl: pages from any earlier crawl (other dates or filters) would mix
    # into this one, so clear them. They are re-fetchable raw API responses.
    old = list(discover_dir.glob("*.json")) + list(discover_dir.glob("*.tmp"))
    for path in old:
        path.unlink()
    if old:
        print(f"new crawl: removed {len(old)} pages from the previous crawl")
    release_end = date.today()
    write_atomic(MANIFEST, {
        "status": "in_progress",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "release_start": release_start,
        "release_end": release_end.isoformat(),
        "filters": filters,
        "files": [],
    })
    return release_end


def extract_discover(release_start=RELEASE_START, min_votes=MIN_VOTE_COUNT, fresh=False):
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    discover_dir = BRONZE / "discover"
    discover_dir.mkdir(parents=True, exist_ok=True)

    start = date.fromisoformat(release_start)
    if start > date.today():
        raise SystemExit(f"start {release_start} is after today {date.today().isoformat()}")
    filters = build_filters(min_votes)
    release_end = start_or_resume(start.isoformat(), filters, fresh)
    state = read_saved(MANIFEST)

    written = []
    print(f"extract discover: {start.isoformat()} through {release_end.isoformat()}, "
          f"vote_count >= {min_votes}")
    crawl_window(start.isoformat(), release_end.isoformat(), headers, filters,
                 discover_dir, written)

    state.update({
        "status": "complete",
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "files": written,
    })
    write_atomic(MANIFEST, state)
    print(f"extract discover: {len(written)} files")
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
    parser.add_argument(
        "--min-votes",
        type=int,
        default=MIN_VOTE_COUNT,
        help=f"Keep movies with at least this many TMDB votes (default {MIN_VOTE_COUNT}).",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start a new crawl even if an unfinished one can be resumed.",
    )
    args = parser.parse_args()
    extract_discover(args.start, args.min_votes, args.fresh)
    extract_details()

if __name__ == "__main__":
    main()