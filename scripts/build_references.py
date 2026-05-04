#!/usr/bin/env python3
"""
Reference library downloader v4 — uses the `ddgs` library.
Research findings: see SCRAPING_NOTES.md
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
    print("WARNING: ddgs not installed; only Bing async will be used.", file=sys.stderr)

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
SLEEP = 0.5

def fetch(url, retries=2):
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers=headers(), timeout=TIMEOUT, allow_redirects=True)
            if r.status_code == 200:
                return r
            if i == retries:
                print(f"     ! status={r.status_code} {url[:80]}")
        except requests.RequestException as e:
            if i == retries:
                print(f"     ! {type(e).__name__}")
        time.sleep(1.5 * (i + 1))
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

def search_via_ddgs(query, max_results=15):
    if not HAS_DDGS:
        return []
    try:
        with DDGS(timeout=20) as ddgs_client:
            results = ddgs_client.images(query, max_results=max_results, safesearch="off", region="us-en")
            return [r.get("image") or r.get("thumbnail") for r in results if r.get("image") or r.get("thumbnail")]
    except Exception as e:
        print(f"     ! ddgs error: {type(e).__name__}: {str(e)[:80]}")
        return []

def search_bing_async(query, max_results=15):
    url = f"https://www.bing.com/images/async?q={quote_plus(query)}&first=1&mmasync=1"
    r = fetch(url)
    if not r:
        return []
    try:
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"     ! bs4 fail: {e}")
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

def resolve(spec):
    candidates = []
    explicit_urls = []
    if spec.get("url") and not spec["url"].startswith("REPLACE"):
        explicit_urls.append(spec["url"])
    explicit_urls.extend(spec.get("alt_urls", []))
    for url in explicit_urls:
        content, score, reason = download_and_score(url)
        if content:
            print(f"     ✓ explicit: {reason}")
            candidates.append((content, score + 30, "explicit"))
        else:
            print(f"     ✗ explicit: {reason}")

    query = spec.get("search")
    have_great_match = lambda: candidates and max(c[1] for c in candidates) >= 110
    if query and not have_great_match():
        for engine_name, search_fn in [("ddgs", search_via_ddgs), ("bing-async", search_bing_async)]:
            if have_great_match():
                break
            print(f"     ▸ {engine_name}: {query}")
            try:
                urls = search_fn(query, max_results=10)
            except Exception as e:
                print(f"     ! {engine_name} crashed: {e}")
                urls = []
            print(f"     ▸ {engine_name} returned {len(urls)} urls")
            tried = 0
            for u in urls:
                if tried >= 6:
                    break
                tried += 1
                time.sleep(0.3)
                content, score, reason = download_and_score(u)
                if content:
                    print(f"     ✓ {engine_name} #{tried}: {reason}")
                    candidates.append((content, score, engine_name))
                    if score >= 110:
                        break

    if not candidates:
        return None
    candidates.sort(key=lambda c: -c[1])
    best = candidates[0]
    print(f"     ★ best: score={best[1]} from {best[2]} ({len(candidates)} candidates total)")
    return best[0]

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
    print(f"v4 downloader · {len(entries)} entries · mode={args.mode} · ddgs={HAS_DDGS}\n")

    new, skipped, failed = 0, 0, []
    proc = 0
    for path, spec in entries.items():
        if args.limit and proc >= args.limit:
            print(f"\n[limit reached]")
            break
        full = REPO_ROOT / path
        if args.mode == "fill-missing" and full.exists():
            skipped += 1
            continue
        proc += 1
        print(f"\n→ [{proc}] {path}")
        full.parent.mkdir(parents=True, exist_ok=True)
        content = resolve(spec)
        if content:
            full.write_bytes(content)
            print(f"   ✓ saved {len(content)}b")
            new += 1
        else:
            failed.append(path)
            print(f"   ✗ all sources failed")
        time.sleep(SLEEP)

    print(f"\n{'='*60}\nSummary: {new} new · {skipped} existed · {len(failed)} failed")
    if failed:
        print(f"\nFAILED ({len(failed)}):")
        for f in failed:
            print(f"  - {f}")

if __name__ == "__main__":
    main()
