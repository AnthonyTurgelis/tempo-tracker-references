# Identification Workflow

This document describes how Claude (in chat) identifies cards from photos
the user pastes, and produces ready-to-commit output for the tracker.

It is the **operating manual** for any chat session involving card
identification. Read this first if you're a new chat and the user has just
pasted card photos.

---

## TL;DR — the workflow at a glance

1. User pastes one or more photos into chat
2. Claude reads `PARALLEL_GUIDE.md` and uses the candidate folders in this
   repo to identify each card
3. Claude writes a chat response with **two parts**:
   - **Part 1**: Walk through each card with reasoning + reference cite
   - **Part 2**: Paste-able bootstrap block ready to drop into the tracker
4. User commits the bootstrap block to their tracker source file
5. Tracker auto-applies on next page load (BOOTSTRAPS array, idempotent
   id-based merge)

---

## Reference assets you have

When identifying cards, you have these resources in this repo:

- **`PARALLEL_GUIDE.md`** — Full parallel checklist by year + product, plus
  the 4 high-priority identification rules (serial-overrides-texture,
  rotation awareness, back-photo-is-same-card, cite references)
- **`base-photos/<player>/<year>-<product>-<card#>/candidate-*.jpg`** —
  Up to 8 candidate photos of the same exact card. Use to confirm "is this
  Sabally #117 from 2025 Prizm?"
- **`parallels/<product>/<variant>/candidate-*.jpg`** — Up to 15 candidate
  photos of the parallel pattern across many different cards. Use to
  confirm "is this Snakeskin or Ice?"
- **`screenshots/`** — Original eBay screenshots from past purchases for
  context if needed
- **`SCRAPING_NOTES.md`** — How the reference library is built and updated
  (you don't need this for identification, only for repo maintenance)

---

## Identification process — per card

### 1. Read PARALLEL_GUIDE.md first

Always start by re-reading `PARALLEL_GUIDE.md`. The 4 high-priority rules
catch the most common mistakes:

1. **Serial numbers override texture** — if you see "23/199" cleanly, look
   it up in the print-run table, don't second-guess from the pattern alone
2. **Watch for rotated numbers** — "61" might be "19" upside down
3. **Back photos = same card, not a new one** — count distinct fronts
4. **Cite reference paths** — every call gets a `parallels/.../candidate-X.jpg`

### 2. Identify the card

For each card, work through this decision tree:

```
1. Can I read the player's name on the card?            → narrows to ~1 player
2. Can I read the year + product (logo, team era)?      → narrows to ~150 cards
3. Can I read the card number?                          → narrows to 1 unique card
4. Is there a visible serial (e.g. "23/199")?           → locks parallel
5. If no serial, what's the dominant texture/color?     → narrows parallel options
6. Cross-reference against `parallels/.../candidate-*.jpg`  → confirms or rejects
```

If the photo doesn't show identifying details (cropped, blurry, glare),
say so explicitly and ask the user to clarify or re-shoot.

### 3. Confidence levels

Assign one of three levels to every call:

- **HIGH (>90% confident)** — Card identifiers visible AND parallel
  unambiguously matches a reference. Commit confidently.
- **MEDIUM (70–90%)** — Card identifiers visible, parallel call is
  plausible but not certain. Show side-by-side reasoning.
- **LOW (<70%)** — Something's missing. Ask user to clarify or mark
  for verify-on-receipt.

### 4. Cite your work

Every call must reference at least one specific candidate file:

✓ Good: "Matched against `parallels/prizm-wnba/snakeskin/candidate-003.jpg`
— scale pattern angle and color tint match cleanly"

✗ Bad: "This looks like Snakeskin to me"

The user can audit your work by opening the same file. That trust is the
whole point of the reference library.

---

## Output format — the two-part response

### Part 1 — Identification narrative

Walk through each photo / card. For multi-card photos (eBay grid screenshots),
use grid coordinates `(row, col)` to identify each card.

````markdown
## Identification: <one-line description of batch>

**Image 1** — Sykes lot, 9 cards in 3×3 grid

- (1,1) clean, no parallel pattern, Atlanta Dream era jersey
  → 2020 Panini Prizm WNBA, Brittney Sykes, #42, Base
  ✓ ref `base-photos/sykes/2020-prizm-wnba-42/candidate-002.jpg`
  HIGH confidence

- (1,2) full vertical rainbow refraction across photo, no border tint
  → 2020 Panini Prizm WNBA, Brittney Sykes, #42, Hyper Prizms
  ✓ ref `parallels/prizm-wnba/hyper/candidate-001.jpg` — diagonal stripes match
  ✓ ref `base-photos/sykes/2020-prizm-wnba-42/candidate-002.jpg` — base photo confirms it's #42
  HIGH confidence

- (1,3) ⚠️ texture pattern visible but ambiguous
  Could be: Ice Prizms (sharp angular shards) OR Snakeskin (round scales)
  → leaning Ice based on shard angularity, but MEDIUM confidence (70%)
  ✓ ref `parallels/prizm-wnba/ice/candidate-001.jpg` (close match)
  ✓ ref `parallels/prizm-wnba/snakeskin/candidate-005.jpg` (less match — scales rounder than photo shows)
  → calling it Ice but flag for verify-on-receipt

[...continues for all images, all cards in each image...]

## Summary
- 9 cards identified across 7 photos
- 8 HIGH confidence, 1 MEDIUM (Image 1 (1,3))
- 0 cards skipped — all 9 fronts accounted for
- Image 5 was a back of card showing "/199" serial → applied to Image 4 (1,1) as Blue Prizms
````

### Part 2 — Paste-able bootstrap block

After the narrative, give the user a code block they can copy-paste into
their tracker's `BOOTSTRAPS` array. Use `id` format `ebay-batch-YYYY-MM-DD-<slug>`
or `comc-batch-YYYY-MM-DD` etc.

````markdown
## Ready to apply

Paste this entry into the `BOOTSTRAPS` array in `tyler_black_tracker.jsx`
(or `toronto_tempo_tracker.html`) just above the closing `];`:

```javascript
{
  id: 'ebay-batch-2026-05-03-sykes',
  label: 'eBay batch 2026-05-03 — Sykes 9-card lot',
  cardMatches: [
    // Image 1 (1,1) — Base
    { match: { player: 'sykes', year: 2020, product: 'Panini Prizm WNBA',
               cardNumber: '42', variant: 'Base' },
      status: 'in_transit',
      details: { price: '', date: '2026-05-03',
                 notes: 'Image 1 (1,1) — ref base-photos/sykes/2020-prizm-wnba-42/candidate-002.jpg' } },

    // Image 1 (1,2) — Hyper
    { match: { player: 'sykes', year: 2020, product: 'Panini Prizm WNBA',
               cardNumber: '42', variant: 'Hyper Prizms' },
      status: 'in_transit',
      details: { price: '', date: '2026-05-03',
                 notes: 'Image 1 (1,2) — ref parallels/prizm-wnba/hyper/candidate-001.jpg' } },

    // [...all other cards...]
  ],
  reviewNeeded: [
    { label: 'Image 1 (1,3) — Ice vs Snakeskin (70% conf)',
      context: 'Pattern looks angular, leaning Ice. Verify on receipt.' }
  ]
}
```

**To apply:**
1. Open your tracker source file
2. Find `const BOOTSTRAPS = [` near the top of the file
3. Paste the new entry just before the closing `];`
4. Save & commit
5. The tracker will auto-apply on next page load (idempotent — won't double-apply)
````

---

## Special cases

### When the user uploads a back photo

A back photo is showing a serial number from a card whose front is
already in the batch. Do not count it as a new card. Use the serial to
upgrade the parallel call of the matching front photo.

Pattern:
- Front photo (1,1): looks like solid blue tint → could be Blue Prizms (numbered) or Blue Velocity (unnumbered)
- Back photo: shows "47/199" → confirms Blue Prizms /199
- → Upgrade (1,1) call from MEDIUM "Blue something" to HIGH "Blue Prizms /199"

### When the user mentions a price for the lot

Split the price evenly across cards in the lot unless they specify otherwise.
Notes field gets `"part of $X.XX N-card lot"` so context is preserved.

### When a card isn't in the seed checklist

Some real cards aren't catalogued on TCDB (retailer exclusives, pre-production
proofs, etc.). For these, output a `customCards` entry instead of a `cardMatches`
entry. Custom IDs in the 90000s are reserved for bootstrap-managed customs.

```javascript
customCards: [
  { id: 90020, player: 'sykes', year: 2025, product: 'Panini Prizm WNBA',
    cardNumber: '121', team: 'Seattle Storm',
    variant: "Logo Dick's Sporting Goods Exclusive",
    notes: 'Retailer-exclusive parallel — not on TCDB' }
]
```

Then in `cardMatches`, optionally reference this id for status/details.

### When you genuinely can't identify a card

Don't guess. Output:

```
- (2,1) UNABLE TO IDENTIFY
  Visible: dark jersey, blurry surface, no readable card #
  → Need clearer photo or context (which lot? which player?)
```

User will provide better info or excuse it as not in this batch.

---

## Things to never do

- **Never invent card numbers or print runs.** If you can't read it, say so.
- **Never call a card without checking at least one reference image.** That's
  the entire purpose of the library.
- **Never count back photos as separate cards.** See Rule 3 in PARALLEL_GUIDE.md.
- **Never quietly upgrade a MEDIUM call to HIGH** without showing the
  comparison. The user trusts your confidence levels.
- **Never skip the bootstrap block.** Even if the user says "just identify",
  put the paste-able block at the end. Saves them transcription work.

---

## Reference library coverage check

If during identification you find a parallel that isn't in the repo
(`parallels/<product>/<variant>/` doesn't exist), tell the user. They can
add it to `references-manifest.json` and re-run the GitHub Action to
populate it. The library should grow with usage patterns.

```
Note: I don't have a reference folder for `parallels/donruss/dragon/`.
Add this entry to references-manifest.json:

  "parallels/donruss/dragon/": {
    "search": "Donruss WNBA Dragon card",
    "extra_searches": [
      "Donruss WNBA Dragon Caitlin Clark",
      "Donruss WNBA Dragon Angel Reese"
    ],
    "min_candidates": 4,
    "max_candidates": 12
  }

Then trigger the workflow with mode=fill-missing to populate it.
```

---

## Last updated

2026-05-03 — initial version after building Bulk Identify tab and
populating reference library to 151 entries.
