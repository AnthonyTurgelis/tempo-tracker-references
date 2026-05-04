# Image Scraping Research Notes

This document captures everything learned while building the reference image
scraper. Kept in the repo so we never have to re-research it.

## What sources work from GitHub Actions runners?

| Source | Status | Notes |
|---|---|---|
| eBay (`ebay.com`, `i.ebayimg.com`) | ❌ 403 blocked | GHA IP ranges are blocked at edge. `host_not_allowed` returned. Confirmed via direct curl from runner logs. |
| Bing standard `/images/search` | ⚠️ Inconsistent | Returns 200, but the old `"murl":"..."` JSON-in-HTML pattern is largely gone. Returns 0 URLs in production. |
| Bing async `/images/async` | ✅ Works | Different format: image data is in `<a m="...">` JSON attributes. Use BeautifulSoup, not regex. URL pattern: `https://www.bing.com/images/async?q={query}&first=1&mmasync=1` |
| DuckDuckGo `/i.js` direct | ⚠️ Brittle | Requires fetching a `vqd` token first (regex from homepage), then calling i.js. DDG rotates token format and rate-limits cloud IPs aggressively. |
| `ddgs` Python library | ✅ Best | https://github.com/deedy5/ddgs · MIT · no API key · aggregates from DDG+Bing+Google+Yahoo · maintained · handles tokens internally |
| Google `/images` direct | ❌ Hard-blocked | Aggressive bot detection, requires real browser fingerprinting. |
| Yandex Images | ⚠️ Possible | Requires JavaScript rendering. Not viable from simple HTTP. |
| TCDB (`tcdb.com`) | ❌ Cloudflare | Returns 403 to most automated user-agents. |
| COMC (`comc.com`) | ❌ Server-side block | Known to actively prevent scraping. |
| Beckett (`beckett.com`) | ❌ Cloudflare | 403s. |
| Generic image URL fetch | ✅ Usually works | Once you have a direct image URL from any source, downloading it is generally fine. |

## The right approach

Use the `ddgs` library as primary. It abstracts away the constantly-changing
search-engine internals and aggregates results from multiple backends. When
one backend stalls, others pick up. As of January 2026 it's actively
maintained and handles GHA-runner IPs gracefully.

```python
from ddgs import DDGS
with DDGS(timeout=20) as ddgs:
    results = ddgs.images(query, max_results=15, safesearch="off", region="us-en")
    for r in results:
        url = r.get("image") or r.get("thumbnail")
        # download and validate
```

Backup: hit Bing's `/images/async` endpoint directly with BeautifulSoup.

```python
import requests
from bs4 import BeautifulSoup
import json

r = requests.get(f"https://www.bing.com/images/async?q={query}&first=1&mmasync=1",
                 headers={"User-Agent": "Mozilla/5.0 ..."})
soup = BeautifulSoup(r.text, "html.parser")
for a in soup.find_all("a"):
    m = a.get("m")
    if m:
        data = json.loads(m)
        url = data.get("murl")  # main image URL (full size)
```

## Image validation

Trading cards have a distinctive 2.5×3.5 inch ratio (~0.71 aspect). When
search returns banners, logos, ads, or other non-card images, filter them
out by:

1. Reject if dimensions <200x200 (banners and tiny thumbnails)
2. Score peak around aspect 0.71 (vertical card)
3. Secondary acceptable range: 1.4 aspect (horizontal card or scan)
4. Reject square (likely avatar) or extreme aspects

```python
def score(width, height):
    aspect = width / height
    if 0.55 <= aspect <= 0.95:
        return 100 - abs(aspect - 0.71) * 100  # peaks at ~95 for perfect card
    elif 1.05 <= aspect <= 1.8:
        return 50 - abs(aspect - 1.4) * 30      # peaks at ~50 for horizontal
    return 5  # unlikely to be a card
```

For best result quality, query several candidates (5-6 from each engine)
and keep the highest-scoring one rather than just the first match.

## Manifest design

Each entry has a `search` field used as the search query. Override with
explicit `url` when a specific image is wanted (always wins). Store
research-time discoveries as `url` so the search step is skipped on future
runs:

```json
"base-photos/sabally/2025-prizm-wnba-117.jpg": {
  "search": "Nyara Sabally 2025 Panini Prizm WNBA 117 base"
}
```

## Failure modes seen

- **Empty manifest** — script exits cleanly
- **All search engines return 0 URLs** — usually means temporary rate limit;
  retry after waiting (or reduce concurrency)
- **GHA Python version mismatch** — always use `python -m pip` not bare `pip`
- **`pip install requests` only** — the script needs requests + pillow + ddgs +
  beautifulsoup4 (the workflow `Install dependencies` step must list all four)

## Links

- ddgs library: https://github.com/deedy5/ddgs
- Bing async endpoint reference: https://scrape.do/blog/bing-scraping/
- Why eBay blocks GHA: GitHub Actions uses Azure-hosted runner IP space,
  which is in the standard datacenter IP block list for most major sites.
