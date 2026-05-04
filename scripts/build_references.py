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
        with DDGS(timeout=20) as ddgs_cli
