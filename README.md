# tempo-tracker-references

Reference image library for the [Toronto Tempo card tracker](https://github.com/AnthonyTurgelis/tempo-tracker). Used by the tracker UI to display "what does this card actually look like" alongside each card's edit modal.

## Folder structure

```
base-photos/<player>/<year>-<product-slug>-<card#>.jpg
  └─ The unique photo each card uses. Resolves "which card is this?"
     Example: base-photos/sabally/2025-prizm-wnba-117.jpg

parallels/<product-slug>/<variant-slug>.jpg
  └─ The texture/pattern of each parallel. Resolves "which variant?"
     Example: parallels/prizm-wnba/snakeskin.jpg

screenshots/
  └─ Original eBay photos from card purchases. Useful for context when
     individual references aren't yet uploaded.
```

## How automation works

`scripts/build_references.py` reads `references-manifest.json` and downloads each entry's image. It runs on GitHub Actions (full internet access — no scraping restrictions).

For each entry, the script tries in order:
1. The explicit `url` if specified (preferred — most stable)
2. Each `alt_urls` fallback
3. The `search` query — runs an eBay search, picks the first listing, scrapes its `s-l1600` stock photo

The action commits any new images back to the repo. Idempotent: existing files are skipped.

## Trigger the automation

**Web UI:** Actions tab → "Build Reference Library" → "Run workflow"
- `mode: fill-missing` (default) — only download missing files
- `mode: refresh-all` — re-download everything

**Auto-trigger:** Pushing changes to `references-manifest.json` re-runs the action.

## Adding more cards

Edit `references-manifest.json` and add an entry:

```json
"base-photos/sabally/2025-prizm-wnba-117.jpg": {
  "search": "Nyara Sabally 2025 Panini Prizm WNBA 117 base"
}
```

Push the change. The action runs automatically and commits the downloaded image.

## Slug conventions

- Player slug: lowercase last name (`sabally`, `harrison`, `nye`)
- Product slug: see `PRODUCT_SLUG` in `scripts/build_references.py`
- Variant slug: lowercase, hyphenated, "Prizms" suffix stripped
  - "Silver Prizms" → `silver`
  - "Snakeskin Prizms" → `snakeskin`
  - "Pink Lava Refractors" → `pink-lava-refractors`
  - "Sunburst" → `sunburst`
- Card number slug: lowercased, special chars to hyphens
  - "117" → `117`
  - "2K6-19" → `2k6-19`
  - "BOA-KR" → `boa-kr`

## Tracker integration

The tracker's `ReferenceImagePanel` component fetches images from `raw.githubusercontent.com/AnthonyTurgelis/tempo-tracker-references/main/...` whenever a card's edit modal is opened. Missing images show a graceful "Upload" link.

No tracker rebuild needed when references update — they're loaded directly from raw.githubusercontent.
