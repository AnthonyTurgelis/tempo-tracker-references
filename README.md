# tempo-tracker-references

Reference image library + identification guides for card collection trackers.
Used by Claude (in chat) when identifying cards from photos, and by tracker
UIs when displaying reference images alongside card edit modals.

## What's in this repo

| File | Purpose |
|---|---|
| **`WORKFLOW.md`** | **Read this first.** How Claude identifies cards from photos and outputs paste-able tracker updates. |
| `PARALLEL_GUIDE.md` | Visual identification rules — parallel checklists by year+product, decision trees, confusion pairs, 4 high-priority rules |
| `BOOTSTRAP_TEMPLATE.md` | Concrete template Claude fills in to deliver bootstrap blocks |
| `SCRAPING_NOTES.md` | How the reference library is built (only relevant for repo maintenance) |
| `references-manifest.json` | Source of truth for what cards/parallels exist in the library |
| `scripts/build_references.py` | Downloader script run by GitHub Actions |
| `.github/workflows/build-references.yml` | CI workflow that populates folders |
| `base-photos/` | Up to 8 candidate images per card (player/year/product/#) |
| `parallels/` | Up to 15 candidate images per parallel pattern (across many players/cards) |
| `screenshots/` | Original eBay screenshots for context |

## Folder structure

```
base-photos/<player>/<year>-<product-slug>-<card#>/candidate-001.jpg ... candidate-008.jpg
  └─ Up to 8 photos OF THE SAME EXACT CARD. Used to confirm
     "is this Sabally #117 from 2025 Prizm?"
     Example: base-photos/sabally/2025-prizm-wnba-117/candidate-003.jpg

parallels/<product-slug>/<variant-slug>/candidate-001.jpg ... candidate-015.jpg
  └─ Up to 15 photos showing the SAME PARALLEL PATTERN across many cards.
     Used to confirm "is this Snakeskin or Ice?"
     Example: parallels/prizm-wnba/snakeskin/candidate-007.jpg

screenshots/
  └─ Original eBay photos from card purchases for context
```

## Identifying cards from photos

When the user pastes card photos into chat, Claude follows the workflow in
`WORKFLOW.md`. The summary:

1. Read `PARALLEL_GUIDE.md` for the 4 high-priority rules
2. For each card, work through the decision tree (player → year → product → # → serial → texture)
3. Cross-reference against folders in `base-photos/` and `parallels/`
4. Output Part 1 (narrative with reference cites) + Part 2 (paste-able bootstrap block)

## Building the reference library

`scripts/build_references.py` reads `references-manifest.json` and downloads
candidate images using the `ddgs` Python library (aggregates DuckDuckGo, Bing,
Google, Yahoo). Runs on GitHub Actions.

For each manifest entry:
1. Tries explicit `url` if specified (preferred — most stable)
2. Tries `alt_urls` fallbacks
3. Runs `search` query + `extra_searches` (multiple player names for parallels)
4. Validates each result with PIL, scores by aspect ratio (cards are ~0.71)
5. Deduplicates by content hash
6. Saves up to N candidates per folder

The action commits new images back to the repo. Idempotent: existing folders
with enough candidates are skipped (unless `mode=refresh-all`).

### Trigger the automation

**Web UI:** Actions tab → "Build Reference Library" → "Run workflow"
- `mode: fill-missing` (default) — populate folders that don't yet have enough candidates
- `mode: refresh-all` — re-download everything from scratch

**Auto-trigger:** Pushing changes to `references-manifest.json` or
`scripts/build_references.py` re-runs the action.

## Adding a new card or parallel

Edit `references-manifest.json` and add an entry:

```json
"base-photos/sabally/2025-prizm-wnba-117/": {
  "search": "Nyara Sabally 2025 Panini Prizm WNBA 117",
  "extra_searches": [
    "Nyara Sabally 2025 Panini Prizm WNBA #117",
    "Nyara Sabally 2025 Panini Prizm WNBA 117 base"
  ],
  "min_candidates": 3,
  "max_candidates": 8
}
```

For parallels, query multiple players to get diverse examples:

```json
"parallels/prizm-wnba/snakeskin/": {
  "search": "Panini Prizm WNBA Snakeskin Prizms card",
  "extra_searches": [
    "Panini Prizm WNBA Snakeskin Caitlin Clark",
    "Panini Prizm WNBA Snakeskin Angel Reese",
    "Panini Prizm WNBA Snakeskin A'ja Wilson",
    "Panini Prizm WNBA Snakeskin Sabrina Ionescu"
  ],
  "min_candidates": 5,
  "max_candidates": 15
}
```

Push the change. The action runs automatically and commits the downloaded images.

## Slug conventions

- **Player slug**: lowercase last name (`sabally`, `harrison`, `nye`)
- **Product slug**: see `PRODUCT_SLUG` in `scripts/build_references.py`
- **Variant slug**: lowercase, hyphenated, "Prizms" suffix stripped
  - "Silver Prizms" → `silver`
  - "Snakeskin Prizms" → `snakeskin`
  - "Pink Lava Refractors" → `pink-lava-refractors`
  - "Sunburst" → `sunburst`
- **Card number slug**: lowercased, special chars to hyphens
  - "117" → `117`
  - "2K6-19" → `2k6-19`
  - "BOA-KR" → `boa-kr`

## Tracker integration

The tracker's `ReferenceImagePanel` React component fetches images from
`raw.githubusercontent.com/AnthonyTurgelis/tempo-tracker-references/main/...`
whenever a card's edit modal is opened. Currently uses the first candidate
(`candidate-001.jpg`) per folder.

No tracker rebuild needed when references update — they're loaded directly
from raw.githubusercontent at runtime.

## Coverage status

Last manifest update: 151 entries (29 base-photo card folders + 122 parallel
folders covering Prizm WNBA, Prizm Monopoly, Revolution, Origins, Select,
Donruss, Bowman U Best/Chrome).
