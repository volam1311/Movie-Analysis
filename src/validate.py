import json
import sys

from src.config import BRONZE, PAGE_CAP, ROOT

DISCOVER_DIR = BRONZE / "discover"
MOVIE_DIR = BRONZE / "movie"
MANIFEST = BRONZE / "discover_manifest.json"
FAILURE_LOG = ROOT / "logs" / "detail_failures.txt"

REQUIRED_DETAIL_KEYS = ("id", "title", "genres")
MAX_DETAIL_FAILURES = 5  # "a handful"

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


def validate_discover():
    files = sorted(DISCOVER_DIR.glob("page=*.json"))
    check("discover file count", len(files) == PAGE_CAP,
          f"{len(files)} files, expected PAGE_CAP={PAGE_CAP}")

    expected_names = {f"page={p:04d}.json" for p in range(1, PAGE_CAP + 1)}
    missing = sorted(expected_names - {f.name for f in files})
    check("discover pages complete", not missing,
          f"missing {missing}" if missing else f"pages 1..{PAGE_CAP} present")

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

    wrong_page, empty_results = [], []
    for f, data in payloads.items():
        file_page = int(f.stem.split("=")[1])
        if data.get("page") != file_page:
            wrong_page.append(f"{f.name} has page={data.get('page')}")
        last_page = min(PAGE_CAP, data.get("total_pages", PAGE_CAP))
        if file_page < last_page and not data.get("results"):
            empty_results.append(f.name)
    check("discover page number", not wrong_page,
          "; ".join(wrong_page) if wrong_page else "filename matches 'page' field")
    check("discover results present", not empty_results,
          f"empty before last page: {empty_results}" if empty_results
          else "every page before the last has results")

    manifest = read_json(MANIFEST)
    if manifest is None:
        check("discover manifest", False, f"{MANIFEST.name} missing or invalid")
    else:
        ok = manifest.get("page_cap") == PAGE_CAP and len(manifest.get("files", [])) == PAGE_CAP
        check("discover manifest", ok,
              f"page_cap={manifest.get('page_cap')}, files={len(manifest.get('files', []))}, "
              f"extracted_at={manifest.get('extracted_at')}")

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
    check("details failure count", len(failed_now) <= MAX_DETAIL_FAILURES,
          f"{len(failed_now)} logged failures (max {MAX_DETAIL_FAILURES})"
          + (f": {failed_now}" if failed_now else ""))

    unaccounted = sorted(discover_ids - detail_ids - set(failed_now))
    check("details cover discover ids", not unaccounted,
          f"{len(unaccounted)} ids with no file and no logged failure: {unaccounted[:10]}"
          if unaccounted
          else f"{len(detail_ids & discover_ids)}/{len(discover_ids)} ids have files, "
               f"{len(failed_now)} logged failures")


def main():
    print(f"validate bronze: PAGE_CAP={PAGE_CAP}")
    discover_ids = validate_discover()
    validate_details(discover_ids)
    if failures:
        print(f"validate bronze: FAILED {len(failures)} check(s): {failures}")
        sys.exit(1)
    print("validate bronze: all checks PASS")


if __name__ == "__main__":
    main()
