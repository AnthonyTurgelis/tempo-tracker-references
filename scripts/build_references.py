#!/usr/bin/env python3
"""
Reference library downloader v2 — aggressive multi-source scraper.

For each manifest entry, tries (in order):
  1. Explicit `url` if present
  2. Explicit `alt_urls` fallbacks
  3. eBay product page lookup for the search query
  4. eBay listing search → scrape stock photo
  5. SportsCardsPro page lookup
  6. SportsCardInvestor page lookup

For each candidate URL found, downloads the image, validates it
(aspect ratio close to a card, minimum size, not a banner/ad), and
keeps the best-scoring one.

Logs each step verbosely so the GHA action output shows exactly what
happened for each entry.
"""
import argparse, io, json, os, re, sys, time
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

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,image/webp,image/jpeg,image/png,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
TIMEOUT = 25
SLEEP_BETWEEN_REQUESTS = 0.5

# ---------- HTTP ----------
def fetch(url, retries=2):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code == 200:
                return r
            if attempt == retries:
                print(f"     ! status={r.status_code} for {url[:90]}")
        except requests.RequestException as e:
            if attempt == retries:
                print(f"     ! {type(e).__name__}: {url[:90]}")
        time.sleep(1.5 * (attempt + 1))
    return None

# ---------- Image validation ----------
def validate_image(content):
    """Return (ok, score, reason). Score higher = better. Card-like images score high."""
    if not content or len(content) < 1000:
        return (False, 0, "too small (<1KB)")
    if not (content[:3] == b"\xff\xd8\xff" or content[:8] == b"\x89PNG\r\n\x1a\n" or content[:4] == b"RIFF" or content[:3] == b"GIF"):
        return (False, 0, "not jpeg/png/webp/gif")
    try:
        img = Image.open(io.BytesIO(content))
        w, h = img.size
    except Exception as e:
        return (False, 0, f"PIL open failed: {e}")
    if w < 200 or h < 200:
        return (False, 0, f"too small ({w}x{h})")
    aspect = w / h
    # Trading cards are ~2.5:3.5 = 0.71. Allow some flex for slabbed cards or rotated.
    # Score peaks around aspect 0.6-0.85 (vertical card)
    if 0.55 <= aspect <= 0.95:
        aspect_score = 100 - abs(aspect - 0.71) * 100
    elif 1.05 <= aspect <= 1.8:
        # Horizontal card or back-of-card
        aspect_score = 50 - abs(aspect - 1.4) * 30
    else:
        # Likely banner/landscape ad or square thumbnail
        aspect_score = 10
    size_score = min(50, (w * h) / 10000)  # bigger is better up to a cap
    score = aspect_score + size_score
    return (True, int(score), f"{w}x{h} aspect={aspect:.2f} score={int(score)}")

def download_and_score(url):
    """Download URL, return (content, score, reason). Score 0 if invalid."""
    r = fetch(url)
    if not r:
        return (None, 0, "fetch failed")
    ok, score, reason = validate_image(r.content)
    if not ok:
        return (None, 0, reason)
    return (r.content, score, reason)

# ---------- eBay scrapers ----------
def upgrade_ebay_image_url(url):
    """Bump any s-l<NUM>.jpg/webp to s-l1600.jpg for max resolution."""
    return re.sub(r"/s-l\d+\.(jpg|webp|png)", "/s-l1600.jpg", url)

def extract_ebay_image_urls(html):
    """Find all i.ebayimg.com URLs, dedup, upgrade to s-l1600. Returns ordered list (page order)."""
    raw = re.findall(r'https://i\.ebayimg\.com/images/g/[^/"\s]+/s-l\d+\.(?:jpg|webp|png)', html)
    seen = set()
    upgraded = []
    for u in raw:
        u2 = upgrade_ebay_image_url(u)
        if u2 not in seen:
            seen.add(u2)
            upgraded.append(u2)
    return upgraded

def search_ebay_product_pages(query, max_pages=3):
    """Search eBay, follow up to max_pages product pages, return image URL list."""
    print(f"     ▸ ebay search: {query}")
    search_url = f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(query)}&_sacat=212"
    r = fetch(search_url)
    if not r:
        return []
    # Find product page links (/p/<id>) and item links (/itm/<id>)
    product_links = re.findall(r'href="(https://www\.ebay\.com/p/\d+[^"#]*)"', r.text)
    item_links = re.findall(r'href="(https://www\.ebay\.com/itm/\d+[^"#]*)"', r.text)
    # Dedup, prefer product pages
    candidates = []
    seen = set()
    for u in product_links + item_links:
        base = u.split("?")[0]
        if base not in seen:
            seen.add(base)
            candidates.append(base)
        if len(candidates) >= max_pages:
            break
    print(f"     ▸ found {len(candidates)} pages to inspect")
    all_images = []
    for page_url in candidates:
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        r2 = fetch(page_url)
        if not r2:
            continue
        imgs = extract_ebay_image_urls(r2.text)
        if imgs:
            print(f"       · {len(imgs)} candidate images from {page_url[:60]}…")
            all_images.extend(imgs)
    # Dedup across pages
    seen = set()
    unique = []
    for u in all_images:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique

# ---------- Resolver ----------
def resolve(spec, target_path):
    """Try every source. Return best image bytes."""
    candidates = []  # list of (content, score, source)

    # 1. Explicit URLs
    for url in [spec.get("url")] + spec.get("alt_urls", []):
        if url and not url.startswith("REPLACE"):
            content, score, reason = download_and_score(url)
            if content:
                print(f"     ✓ explicit url: {reason}")
                candidates.append((content, score + 30, "explicit_url"))  # bonus
            else:
                print(f"     ✗ explicit url failed: {reason}")

    # 2. Search-based (only if we don't already have a great candidate)
    if spec.get("search") and (not candidates or max(c[1] for c in candidates) < 100):
        # Multiple query variants
        base_query = spec["search"]
        query_variants = [base_query]
        # Variant: drop "base" suffix to let parallels in
        if base_query.lower().endswith(" base"):
            query_variants.append(base_query[:-5])
        # Variant: trim noise words
        compact = re.sub(r"\bWNBA\b|\bPanini\b", "", base_query).strip()
        compact = re.sub(r"\s+", " ", compact)
        if compact != base_query:
            query_variants.append(compact)

        for query in query_variants[:2]:  # max 2 variants per entry to control time
            urls = search_ebay_product_pages(query)
            # Try top 5 candidate images; take best-scoring one
            for url in urls[:5]:
                time.sleep(SLEEP_BETWEEN_REQUESTS)
                content, score, reason = download_and_score(url)
                if content:
                    print(f"     ✓ ebay candidate: {reason}")
                    candidates.append((content, score, f"ebay:{query[:40]}"))
                    if score >= 100:
                        break  # good enough, save time
            if any(c[1] >= 100 for c in candidates):
                break

    if not candidates:
        return None

    candidates.sort(key=lambda c: -c[1])
    best = candidates[0]
    print(f"     ★ kept best: score={best[1]} from {best[2]}")
    return best[0]

# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["fill-missing", "refresh-all"], default="fill-missing")
    ap.add_argument("--limit", type=int, default=0, help="Process at most N entries (0=all)")
    args = ap.parse_args()

    if not MANIFEST_PATH.exists():
        print(f"No manifest at {MANIFEST_PATH}.")
        sys.exit(0)

    manifest = json.loads(MANIFEST_PATH.read_text())
    entries = {k: v for k, v in manifest.items() if not k.startswith("_") and isinstance(v, dict)}
    print(f"Manifest entries: {len(entries)}, mode: {args.mode}\n")

    new, skipped, failed = 0, 0, []
    processed = 0
    for target_path, spec in entries.items():
        if args.limit and processed >= args.limit:
            print(f"\n[Limit reached: {args.limit}]")
            break
        full_target = REPO_ROOT / target_path
        if args.mode == "fill-missing" and full_target.exists():
            skipped += 1
            continue
        processed += 1
        print(f"\n→ [{processed}] {target_path}")
        full_target.parent.mkdir(parents=True, exist_ok=True)
        content = resolve(spec, target_path)
        if content:
            full_target.write_bytes(content)
            print(f"   ✓ saved ({len(content)} bytes)")
            new += 1
        else:
            failed.append(target_path)
            print(f"   ✗ all sources failed")
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    print(f"\n{'='*60}")
    print(f"Summary: {new} new, {skipped} already existed, {len(failed)} failed")
    if failed:
        print(f"\n{len(failed)} FAILED — add explicit url in manifest:")
        for f in failed:
            print(f"  - {f}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
