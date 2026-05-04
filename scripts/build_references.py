#!/usr/bin/env python3
"""
Reference library downloader v5 — multiple candidates per entry.

Each manifest entry now writes to a FOLDER, not a single file. The folder
contains up to N candidate images so we can cross-reference against actual
card photos.

Folder structure:
  base-photos/<player>/<year>-<product>-<card#>/candidate-001.jpg ... candidate-010.jpg
  parallels/<product>/<variant>/candidate-001.jpg ... candidate-015.jpg

Manifest entry format (NEW):
  "<folder-path>/": {
    "search": "main query",
    "extra_searches": ["alt query 1", "alt query 2"],   // optional
    "min_candidates": 5,
    "max_candidates": 15
  }

For parallels especially, multiple search queries are run with DIFFERENT
players to populate the same folder with diverse examples of the same
parallel. This lets us compare textures across cards.
"""
import argparse, io, json, os, random, re, sys, time
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests
    from PIL import Image
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"Missing dep: {e}. Run: pip install requests pillow beautifulsoup4 ddgs", file=sys.stderr)
    sys.exit(1)

try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False
    print("WARNING: ddgs not installed.", file=sys.stderr)

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "references-manifest.json"

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def headers():
    return {"User-Agent": random.choice(UAS), "Accept": "text/html,image/*,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}

TIMEOUT = 25
DEFAULT_MIN_CANDIDATES = 3
DEFAULT_MAX_CANDIDATES = 10

def fetch(url, retries=1):
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers=headers(), timeout=TIMEOUT, allow_redirects=True)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
        time.sleep(1.0 * (i + 1))
    return None

def validate(content):
    if not content or len(content) < 1500:
        return (False, 0, "too small")
    head = content[:8]
    if not (head[:3] == b"\xff\xd8\xff" or head == b"\x89PNG\r\n\x1a\n" or head[:4] == b"RIFF" or head[:3] == b"GIF"):
        return (False, 0, "not image")
    try:
        img = Image.open(io.BytesIO(content))
        w, h = img.size
    except Exception as e:
        return (False, 0, f"PIL fail: {e}")
    if w < 200 or h < 200:
        return (False, 0, f"too small {w}x{h}")
    aspect = w / h
    if 0.55 <= aspect <= 0.95:
        s = 100 - abs(aspect - 0.71) * 100
    elif 1.05 <= aspect <= 1.8:
        s = 50 - abs(aspect - 1.4) * 30
    else:
        s = 5
    s += min(40, (w * h) / 12000)
    return (True, int(s), f"{w}x{h} ar={aspect:.2f} s={int(s)}")

def download_and_score(url):
    r = fetch(url)
    if not r:
        return (None, 0, "fetch fail")
    ok, score, reason = validate(r.content)
    return (r.content if ok else None, score, reason)

def search_via_ddgs(query, max_results=20):
    if not HAS_DDGS:
        return []
    try:
        with DDGS(timeout=20) as ddgs_client:
            results = ddgs_client.images(query, max_results=max_results, safesearch="off", region="us-en")
            return [r.get("image") or r.get("thumbnail") for r in results if r.get("image") or r.get("thumbnail")]
    except Exception as e:
        print(f"     ! ddgs error: {type(e).__name__}: {str(e)[:80]}")
        return []

def search_bing_async(query, max_results=20):
    url = f"https://www.bing.com/images/async?q={quote_plus(query)}&first=1&mmasync=1"
    r = fetch(url)
    if not r:
        return []
    try:
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []
    urls = []
    for a in soup.find_all("a"):
        m = a.get("m")
        if not m:
            continue
        try:
            data = json.loads(m)
            murl = data.get("murl")
            if murl:
                urls.append(murl)
                if len(urls) >= max_results:
                    break
        except (json.JSONDecodeError, TypeError):
            continue
    return urls

def deduplicate(content_list):
    """Hash-based dedup of byte content."""
    import hashlib
    seen = set()
    out = []
    for c in content_list:
        h = hashlib.md5(c).hexdigest()
        if h not in seen:
            seen.add(h)
            out.append(c)
    return out

def resolve_to_folder(folder_path, spec):
    """Save up to max_candidates valid card images into folder_path. Returns count saved."""
    folder = REPO_ROOT / folder_path
    folder.mkdir(parents=True, exist_ok=True)

    min_c = spec.get("min_candidates", DEFAULT_MIN_CANDIDATES)
    max_c = spec.get("max_candidates", DEFAULT_MAX_CANDIDATES)
    score_threshold = spec.get("min_score", 100)

    queries = []
    if spec.get("search"):
        queries.append(spec["search"])
    queries.extend(spec.get("extra_searches", []))
    if not queries:
        return 0

    explicit_urls = []
    if spec.get("url") and not spec["url"].startswith("REPLACE"):
        explicit_urls.append(spec["url"])
    explicit_urls.extend(spec.get("alt_urls", []))

    saved_contents = []
    candidate_urls = list(explicit_urls)

    # Run each search query and collect URLs
    for q in queries:
        if len(saved_contents) >= max_c:
            break
        for engine_name, search_fn in [("ddgs", search_via_ddgs), ("bing-async", search_bing_async)]:
            print(f"     ▸ {engine_name}: {q}")
            urls = search_fn(q, max_results=15)
            print(f"     ▸ {engine_name} returned {len(urls)} urls")
            candidate_urls.extend(urls)
            # If ddgs gave us plenty, skip bing-async for this query
            if engine_name == "ddgs" and len(urls) >= 10:
                break

    # Try each URL, keeping ones that score above threshold
    seen_urls = set()
    for url in candidate_urls:
        if len(saved_contents) >= max_c:
            break
        if url in seen_urls:
            continue
        seen_urls.add(url)
        time.sleep(0.2)
        content, score, reason = download_and_score(url)
        if content and score >= score_threshold:
            saved_contents.append(content)
            print(f"     ✓ #{len(saved_contents)}: {reason}")

    # Dedup by content hash (image search engines often return same image multiple times)
    saved_contents = deduplicate(saved_contents)

    # Write to disk
    for i, content in enumerate(saved_contents, 1):
        target = folder / f"candidate-{i:03d}.jpg"
        target.write_bytes(content)

    print(f"     ★ saved {len(saved_contents)} unique candidates to {folder_path}")
    return len(saved_contents)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fill-missing", "refresh-all"], default="fill-missing")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if not MANIFEST_PATH.exists():
        print("No manifest")
        sys.exit(0)

    manifest = json.loads(MANIFEST_PATH.read_text())
    entries = {k: v for k, v in manifest.items() if not k.startswith("_") and isinstance(v, dict)}
    print(f"v5 downloader · {len(entries)} entries · mode={args.mode} · ddgs={HAS_DDGS}\n")

    new, skipped, failed = 0, 0, []
    proc = 0
    for path, spec in entries.items():
        if args.limit and proc >= args.limit:
            print(f"\n[limit reached]")
            break
        # Each entry maps to a folder
        folder_path = path.rstrip("/")
        full_folder = REPO_ROOT / folder_path
        # Skip if folder exists and has at least min_candidates
        min_c = spec.get("min_candidates", DEFAULT_MIN_CANDIDATES)
        if args.mode == "fill-missing" and full_folder.exists():
            existing = len(list(full_folder.glob("candidate-*.jpg")))
            if existing >= min_c:
                skipped += 1
                continue
        proc += 1
        print(f"\n→ [{proc}] {folder_path}/")
        count = resolve_to_folder(folder_path, spec)
        if count > 0:
            new += 1
        else:
            failed.append(folder_path)
            print(f"   ✗ no candidates saved")

    print(f"\n{'='*60}\nSummary: {new} folders populated · {skipped} already existed · {len(failed)} failed")
    if failed:
        print(f"\nFAILED ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")

if __name__ == "__main__":
    main()
