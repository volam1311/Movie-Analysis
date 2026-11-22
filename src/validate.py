import json
import sys
from datetime import date
from pathlib import Path

from src.config import BRONZE, ROOT

DISCOVER_DIR = BRONZE / "discover"
MOVIE_DIR = BRONZE / "movie"
MANIFEST = BRONZE / "discover_manifest.json"
FAILURE_LOG = ROOT / "logs" / "detail_failures.txt"

REQUIRED_DETAIL_KEYS = ("id", "title", "genres")
MAX_FAILURE_FRACTION = 0.05  # a full-range crawl can have more than a handful of 404s

failures = []


def check(name, ok, detail):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")
    if not ok:
        failures.append(name)


def read_json(path):
    """Return parsed JSON, or None if the file is empty or invalid."""
    try:
        text = path.read_text()
        return json.loads(text) if text.strip() else None
    except (OSError, json.JSONDecodeError):
        return None


def parse_discover_name(path):
    gte_part, lte_part, page_part = path.stem.split("_")
    return (
        gte_part.split("=", 1)[1],
        lte_part.split("=", 1)[1],
        int(page_part.split("=", 1)[1]),
    )


def validate_discover():
    files = sorted(DISCOVER_DIR.glob("gte=*_page=*.json"))
    check("discover file count", bool(files), f"{len(files)} window page files")

    payloads = {}
    bad_json = []
    for f in files:
        data = read_json(f)
        if data is None:
            bad_json.append(f.name)
        else:
            payloads[f] = data
    check("discover JSON parses", not bad_json,
          f"invalid/empty: {bad_json}" if bad_json else f"{len(files)} files OK")

    windows = {}
    for path, data in payloads.items():
        gte, lte, page = parse_discover_name(path)
        windows.setdefault((gte, lte), []).append((page, path, data))

    missing_pages, wrong_page, empty_results = [], [], []
    for (gte, lte), items in sorted(windows.items()):
        total_pages = int(items[0][2].get("total_pages") or 0)
        have = {page for page, _, _ in items}
        missing = sorted(set(range(1, total_pages + 1)) - have)
        if missing:
            missing_pages.append(f"{gte}..{lte} missing {missing[:5]}")
        for page, path, data in items:
            if data.get("page") != page:
                wrong_page.append(f"{path.name} has page={data.get('page')}")
            if page < total_pages and not data.get("results"):
                empty_results.append(path.name)
    check("discover pages complete", not missing_pages,
          "; ".join(missing_pages[:5]) if missing_pages else f"{len(windows)} windows complete")
    check("discover page number", not wrong_page,
          "; ".join(wrong_page[:5]) if wrong_page else "filename matches 'page' field")
    check("discover results present", not empty_results,
          f"empty before last page: {empty_results[:5]}" if empty_results
          else "every page before the last has results")

    manifest = read_json(MANIFEST)
    if manifest is None:
        check("discover manifest", False, f"{MANIFEST.name} missing or invalid")
    else:
        manifest_names = {Path(item).name for item in manifest.get("files", [])}
        disk_names = {path.name for path in files}
        try:
            start = date.fromisoformat(manifest.get("release_start") or "")
            end = date.fromisoformat(manifest.get("release_end") or "")
            dates_ok = start <= end
        except ValueError:
            dates_ok = False
        complete = manifest.get("status") == "complete"
        ok = complete and dates_ok and manifest_names == disk_names and bool(disk_names)
        check("discover manifest", ok,
              f"status={manifest.get('status')}, "
              f"{manifest.get('release_start')}..{manifest.get('release_end')}, "
              f"files={len(manifest_names)}, extracted_at={manifest.get('extracted_at')}")

    ids = set()
    for data in payloads.values():
        ids |= {m["id"] for m in data.get("results", []) if "id" in m}
    return ids


def logged_failures():
    """Distinct movie ids in the failure log (it is appended across runs)."""
    if not FAILURE_LOG.exists():
        return {}
    failed = {}
    for line in FAILURE_LOG.read_text().splitlines():
        parts = line.strip().split("\t")
        if parts and parts[0].isdigit():
            failed[int(parts[0])] = parts[1] if len(parts) > 1 else "?"
    return failed


def validate_details(discover_ids):
    files = sorted(MOVIE_DIR.glob("movie_id=*.json"))
    check("details files exist", bool(files), f"{len(files)} files in {MOVIE_DIR.name}/")

    bad_json, id_mismatch, missing_keys = [], [], []
    detail_ids = set()
    for f in files:
        data = read_json(f)
        if data is None:
            bad_json.append(f.name)
            continue
        file_id = f.stem.split("=")[1]
        if str(data.get("id")) != file_id:
            id_mismatch.append(f"{f.name} has id={data.get('id')}")
        else:
            detail_ids.add(data["id"])
        absent = [k for k in REQUIRED_DETAIL_KEYS if k not in data]
        if absent:
            missing_keys.append(f"{f.name} missing {absent}")

    check("details JSON parses", not bad_json,
          f"invalid/empty: {bad_json[:10]}" if bad_json else f"{len(files)} files OK")
    check("details id matches filename", not id_mismatch,
          "; ".join(id_mismatch[:10]) if id_mismatch else "all filenames match JSON id")
    check("details required keys", not missing_keys,
          "; ".join(missing_keys[:10]) if missing_keys
          else f"all have {list(REQUIRED_DETAIL_KEYS)}")

    failed = logged_failures()
    failed_now = {i: s for i, s in failed.items() if i in discover_ids and i not in detail_ids}
    failure_limit = max(5, int(len(discover_ids) * MAX_FAILURE_FRACTION))
    check("details failure count", len(failed_now) <= failure_limit,
          f"{len(failed_now)} logged failures (max {failure_limit})"
          + (f": {list(failed_now)[:10]}" if failed_now else ""))

    unaccounted = sorted(discover_ids - detail_ids - set(failed_now))
    check("details cover discover ids", not unaccounted,
          f"{len(unaccounted)} ids with no file and no logged failure: {unaccounted[:10]}"
          if unaccounted
          else f"{len(detail_ids & discover_ids)}/{len(discover_ids)} ids have files, "
               f"{len(failed_now)} logged failures")


def main():
    print("validate bronze")
    discover_ids = validate_discover()
    validate_details(discover_ids)
    if failures:
        print(f"validate bronze: FAILED {len(failures)} check(s): {failures}")
        sys.exit(1)
    print("validate bronze: all checks PASS")


if __name__ == "__main__":
    main()
