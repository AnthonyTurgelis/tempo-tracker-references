#!/usr/bin/env python3
"""
Reference library downloader v3 — multi-source, GHA-friendly.

eBay blocks GitHub Actions IP ranges with 403s. This version uses image search
engines as the primary source, which work fine from GHA:
  1. Explicit url / alt_urls
  2. Bing Image Search (HTML scraping, very reliable)
  3. DuckDuckGo Image Search (JSON API, no key needed)

For each candidate URL, downloads, validates with PIL (size, aspect ratio),
and keeps the best-scoring image.
"""
import argparse, io, json, os, random, re, sys, time
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests
    from PIL import Image
except ImportError:
    print("Install deps: pip install requests pillow", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "references-manifest.json"

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

def headers():
    return {
        "User-Agent": random.choice(UAS),
        "Accept": "text/html,application/xhtml+xml,image/webp,image/jpeg,image/png,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

TIMEOUT = 25
SLEEP = 0.6

def fetch(url, retries=2):
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers=headers(), timeout=TIMEOUT, allow_redirects=True)
            if r.status_code == 200:
                return r
            if i == retries:
                print(f"     ! status={r.status_code} for {url[:90]}")
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

def download(url):
    r = fetch(url)
    if not r:
        return (None, 0, "fetch fail")
    ok, score, reason = validate(r.content)
    return (r.content if ok else None, score, reason)

def bing_image_search(query, max_urls=10):
    url = f"https://www.bing.com/images/search?q={quote_plus(query)}&first=1&form=HDRSC2"
    r = fetch(url)
    if not r:
        return []
    urls = re.findall(r'"murl":"([^"]+)"', r.text)
    urls = [u.replace("\\u002f", "/").replace("\\/", "/") for u in urls]
    seen = set()
    out = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= max_urls:
            break
    return out

def ddg_image_search(query, max_urls=10):
    s = requests.Session()
    s.headers.update(headers())
    try:
        r = s.get("https://duckduckgo.com/", params={"q": query}, timeout=TIMEOUT)
        m = re.search(r'vqd=["\']([\d-]+)["\']', r.text) or re.search(r'vqd=([\d-]+)&', r.text)
        if not m:
            return []
        vqd = m.group(1)
        time.sleep(0.5)
        r2 = s.get("https://duckduckgo.com/i.js", params={
            "l": "us-en", "o": "json", "q": query, "vqd": vqd, "f": ",,,,,", "p": "1"
        }, timeout=TIMEOUT)
        if r2.status_code != 200:
            return []
        data = r2.json()
        return [item.get("image") for item in data.get("results", []) if item.get("image")][:max_urls]
    except Exception as e:
        print(f"     ! ddg: {e}")
        return []

def resolve(spec):
    candidates = []
    urls = []
    if spec.get("url") and not spec["url"].startswith("REPLACE"):
        urls.append(spec["url"])
    urls.extend(spec.get("alt_urls", []))
    for url in urls:
        content, score, reason = download(url)
        if content:
            print(f"     ✓ explicit: {reason}")
            candidates.append((content, score + 30, "explicit"))
        else:
            print(f"     ✗ explicit: {reason}")

    query = spec.get("search")
    if query and (not candidates or max(c[1] for c in candidates) < 100):
        for engine_name, search_fn in [("bing", bing_image_search), ("ddg", ddg_image_search)]:
            print(f"     ▸ {engine_name}: {query}")
            try:
                urls = search_fn(query, max_urls=8)
            except Exception as e:
                print(f"     ! {engine_name} crashed: {e}")
                urls = []
            print(f"     ▸ {engine_name} returned {len(urls)} urls")
            tested = 0
            for u in urls:
                if tested >= 5:
                    break
                time.sleep(0.4)
                content, score, reason = download(u)
                if content:
                    print(f"     ✓ {engine_name}: {reason} {u[:60]}")
                    candidates.append((content, score, engine_name))
                tested += 1
            if any(c[1] >= 100 for c in candidates):
                break

    if not candidates:
        return None
    candidates.sort(key=lambda c: -c[1])
    best = candidates[0]
    print(f"     ★ best: score={best[1]} from {best[2]}")
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
    print(f"v3 downloader · {len(entries)} entries · mode={args.mode}\n")

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
