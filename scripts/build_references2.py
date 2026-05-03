#!/usr/bin/env python3
"""Reference library downloader. Reads references-manifest.json and populates each entry's image."""
import argparse, json, re, sys, time
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests
except ImportError:
    print("requests not installed; run: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "references-manifest.json"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept": "text/html,image/webp,image/jpeg,image/png,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
TIMEOUT = 25

def is_image_bytes(content):
    if len(content) < 200:
        return False
    return content[:3] == b"\xff\xd8\xff" or content[:8] == b"\x89PNG\r\n\x1a\n" or content[:4] == b"RIFF" or content[:3] == b"GIF"

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            return r
        print(f"   X {url[:80]} -> status={r.status_code}")
    except requests.RequestException as e:
        print(f"   X {url[:80]} -> {e}")
    return None

def download_image(url):
    r = fetch(url)
    if r and is_image_bytes(r.content):
        return r.content
    return None

def search_ebay_for_image(query):
    search_url = f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(query)}&_sacat=212"
    r = fetch(search_url)
    if not r:
        return None
    item_match = re.search(r'href="(https://www\.ebay\.com/itm/\d+[^"]*)"', r.text)
    if not item_match:
        item_match = re.search(r'href="(https://www\.ebay\.com/p/\d+[^"]*)"', r.text)
    if not item_match:
        print(f"   X No listing found for: {query}")
        return None
    listing_url = item_match.group(1).split("?")[0]
    time.sleep(0.7)
    r2 = fetch(listing_url)
    if not r2:
        return None
    img_matches = re.findall(r'https://i\.ebayimg\.com/images/g/[^/"\s]+/s-l1600\.jpg', r2.text)
    if img_matches:
        return img_matches[0]
    img_matches = re.findall(r'https://i\.ebayimg\.com/images/g/([^/"\s]+)/s-l\d+\.(?:jpg|webp)', r2.text)
    if img_matches:
        return f"https://i.ebayimg.com/images/g/{img_matches[0]}/s-l1600.jpg"
    return None

def resolve(spec):
    urls = []
    if spec.get("url") and not spec["url"].startswith("REPLACE"):
        urls.append(spec["url"])
    urls.extend(spec.get("alt_urls", []))
    for url in urls:
        content = download_image(url)
        if content:
            return content
        time.sleep(0.4)
    if spec.get("search"):
        print(f"   ...searching eBay: {spec['search']}")
        url = search_ebay_for_image(spec["search"])
        if url:
            print(f"   ...found: {url}")
            content = download_image(url)
            if content:
                return content
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fill-missing", "refresh-all"], default="fill-missing")
    args = ap.parse_args()
    if not MANIFEST_PATH.exists():
        print(f"No manifest at {MANIFEST_PATH}.")
        sys.exit(0)
    manifest = json.loads(MANIFEST_PATH.read_text())
    entries = {k: v for k, v in manifest.items() if not k.startswith("_") and isinstance(v, dict)}
    print(f"Manifest entries: {len(entries)}, mode: {args.mode}\n")
    new, skipped, failed = 0, 0, []
    for target_path, spec in entries.items():
        full_target = REPO_ROOT / target_path
        if args.mode == "fill-missing" and full_target.exists():
            skipped += 1
            continue
        full_target.parent.mkdir(parents=True, exist_ok=True)
        print(f"-> {target_path}")
        content = resolve(spec)
        if content:
            full_target.write_bytes(content)
            print(f"   OK saved ({len(content)} bytes)\n")
            new += 1
        else:
            failed.append(target_path)
            print(f"   X all sources failed\n")
        time.sleep(0.5)
    print(f"\n=== Summary: {new} new, {skipped} already existed, {len(failed)} failed ===")
    if failed:
        print("\nFailed (consider adding explicit url in manifest):")
        for f in failed:
            print(f"  - {f}")

if __name__ == "__main__":
    main()
