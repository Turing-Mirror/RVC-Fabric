"""Opt-in read-only full downloads and Range checks; run manually from the product root."""
import concurrent.futures
import datetime
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / "User_Data/e2e-ms-all"
SOURCES = {
    "rvc_cnb": "https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/index.json",
    "gsv_cnb": "https://cnb.cool/Turing-Mirror/GPT-SoVITS-Fabric-Releases/-/git/raw/main/index.json",
    "gsv_web": "https://www.turingmirror.com/releases/gpt-sovits-fabric/index.json",
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RVCFabric/1.8.2"


def save(name, value):
    (WORK / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def request(url, **headers):
    return Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity", **headers})


def public_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def raw_headers(response):
    return {
        key: public_url(value) if key.lower() == "location" else value
        for key, value in response.headers.items()
        if key.lower() not in {"set-cookie", "cookie", "authorization", "proxy-authorization"}
    }


def entries(node, path=""):
    if isinstance(node, dict):
        urls = node.get("urls")
        first = urls[0] if isinstance(urls, list) and urls else None
        if not first:
            first = node.get("url") or node.get("pack_url")
        if isinstance(first, str) and urlsplit(first).hostname == "modelscope.cn":
            yield {"path": path, "url": first, "expected_bytes": node.get("size_bytes"),
                   "sha256": node.get("sha256"), "name": node.get("name")}
        for key, value in node.items():
            yield from entries(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from entries(value, f"{path}/{index}")


def range_check(row):
    result = dict(row)
    try:
        try:
            response = urlopen(request(row["url"], Range="bytes=0-0"), timeout=45)
        except HTTPError as error:
            response = error
        with response:
            body = response.read(1024)
            result.update(status=response.status,
                          content_range=response.headers.get("Content-Range", ""),
                          received_bytes=len(body),
                          final_url_without_query=public_url(response.geturl()))
            match = re.fullmatch(r"bytes 0-0/(\d+)", result["content_range"])
            result["pass"] = bool(response.status == 206 and len(body) == 1 and match
                                  and int(match[1]) == row["expected_bytes"])
            if not result["pass"]:
                result.update(headers=raw_headers(response), body_hex=body.hex(),
                              body_text=body.decode("utf-8", errors="replace"))
    except Exception as error:
        result.update(pass_=False, error=repr(error))
        result["pass"] = result.pop("pass_")
    return result


def full_pymss(label, data):
    candidates = [(key, item) for key, extra in data["extras"].items() if "pymss" in key
                  for item in extra["files"] if item.get("size_bytes", 0) > 0]
    key, item = min(candidates, key=lambda pair: pair[1]["size_bytes"])
    url = item["urls"][0]
    result = {"catalog": label, "catalog_url": SOURCES[label], "key": key,
              "name": item["name"], "actual_url": url,
              "expected_bytes": item["size_bytes"], "expected_sha256": item["sha256"]}
    dest = WORK / f"{label}-pymss.bin"
    try:
        digest = hashlib.sha256()
        count = 0
        with urlopen(request(url), timeout=60) as response, dest.open("wb") as output:
            result.update(status=response.status,
                          final_url_without_query=public_url(response.geturl()))
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                count += len(chunk)
        result.update(bytes=count, sha256=digest.hexdigest())
        result["pass"] = (200 <= result["status"] < 300 and count == item["size_bytes"]
                          and digest.hexdigest() == item["sha256"]
                          and urlsplit(url).hostname == "modelscope.cn")
    except Exception as error:
        result.update({"pass": False, "error": repr(error)})
        if isinstance(error, HTTPError):
            result.update(status=error.code, headers=raw_headers(error),
                          body_text=error.read(4096).decode("utf-8", errors="replace"))
    finally:
        if dest.exists():
            dest.unlink()
        result["download_deleted"] = not dest.exists()
    print("FULL_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    results = {"started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "catalogs": [], "full_downloads": [], "ranges": []}
    all_rows = []
    for label, url in SOURCES.items():
        try:
            with urlopen(request(url + "?_=" + str(time.time_ns()), **{"Cache-Control": "no-cache"}),
                         timeout=60) as response:
                body = response.read()
                status = response.status
            data = json.loads(body)
            (WORK / f"{label}.json").write_bytes(body)
            rows = list(entries(data))
            # Each catalog is checked independently. Identical URLs within it share one request.
            unique = {}
            for row in rows:
                entry = unique.setdefault((row["url"], row["expected_bytes"]), {**row, "paths": []})
                entry["paths"].append(row["path"])
            all_rows.extend({"catalog": label, **row} for row in unique.values())
            info = {"catalog": label, "url": url, "status": status, "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(), "modelscope_entries": len(rows),
                    "unique_range_requests": len(unique), "pass": True}
            results["catalogs"].append(info)
            print("CATALOG_RESULT " + json.dumps(info), flush=True)
            if label.startswith("gsv_"):
                results["full_downloads"].append(full_pymss(label, data))
        except Exception as error:
            row = {"catalog": label, "url": url, "pass": False, "error": repr(error)}
            results["catalogs"].append(row)
            print("CATALOG_RESULT " + json.dumps(row), flush=True)
    save("python-results.json", results)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(range_check, row) for row in all_rows]
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            results["ranges"].append(row)
            if not row["pass"]:
                print("RANGE_FAILURE " + json.dumps(row, ensure_ascii=False), flush=True)
            if len(results["ranges"]) % 10 == 0 or len(results["ranges"]) == len(all_rows):
                print(f"RANGE_PROGRESS {len(results['ranges'])}/{len(all_rows)} "
                      f"passed={sum(r['pass'] for r in results['ranges'])}", flush=True)
                save("python-results.json", results)
    results["ranges"].sort(key=lambda row: (row["catalog"], row["path"]))
    results["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save("python-results.json", results)
    for label in SOURCES:
        rows = [r for r in results["ranges"] if r["catalog"] == label]
        print(f"RANGE_SUMMARY {label} total={len(rows)} passed={sum(r['pass'] for r in rows)}", flush=True)
    passed = (len(results["catalogs"]) == 3 and len(results["full_downloads"]) == 2
              and all(row["pass"] for key in ["catalogs", "full_downloads", "ranges"]
                      for row in results[key]))
    print(f"PYTHON_RESULT pass={passed}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
