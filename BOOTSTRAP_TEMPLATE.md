# Bootstrap Template

Copy this template when generating Part 2 of an identification response.
Fill in `<BRACKETED>` placeholders. Delete sections that don't apply.

---

## Standard template

```javascript
{
  // CHANGE: unique batch id, format ebay-batch-YYYY-MM-DD-<slug>
  // YYYY-MM-DD is the purchase date or batch date, slug describes the lot
  id: 'ebay-batch-<YYYY-MM-DD>-<slug>',

  // CHANGE: human-readable label
  label: '<source> batch <date> — <description, e.g. "Sykes 9-card lot, $9.99">',

  // CHANGE: only include this section if the batch has cards not in the
  // seed checklist (retailer exclusives, pre-production proofs, etc.)
  // Custom IDs must be in the 90000s, unique across all bootstraps
  customCards: [
    { id: <90000+sequential>, player: '<player_key>', year: <YYYY>,
      product: '<exact product name>', cardNumber: '<#>',
      team: '<team>', variant: '<exact variant name>',
      notes: '<reason this is a custom — e.g. "Retailer-exclusive, not on TCDB"' }
  ],

  // CHANGE: one entry per identified card
  // Match block is keyed by (player, year, product, cardNumber, variant) — must
  // match canonical fields in SEED_CARDS exactly or the bootstrap warns and skips.
  cardMatches: [
    // Image N (R,C) — short description
    { match: { player: '<key>', year: <YYYY>, product: '<exact product>',
               cardNumber: '<#>', variant: '<exact variant>' },
      status: '<not_owned|in_transit|owned>',
      details: {
        price: '<dollars only, no $, blank if unknown>',
        date: '<YYYY-MM-DD>',
        notes: 'Image <N> (<R>,<C>) — ref <reference path>'
      }
    },
    // [...repeat for each card...]
  ],

  // CHANGE: include this section ONLY if any cards need physical verification
  // (low-confidence calls, ambiguous parallels, unreadable serials, etc.)
  reviewNeeded: [
    { label: 'Image <N> (<R>,<C>) — <ambiguity description>',
      context: '<what to verify on receipt>' }
  ]
}
```

---

## Worked example — typical eBay batch

For an example response after identifying a Sykes 9-card lot from eBay
on 2026-05-03:

```javascript
{
  id: 'ebay-batch-2026-05-03-sykes',
  label: 'eBay batch 2026-05-03 — Sykes 9-card Prizm rainbow lot, $14.99',
  cardMatches: [
    // Image 1 (1,1) — base
    { match: { player: 'sykes', year: 2020, product: 'Panini Prizm WNBA',
               cardNumber: '42', variant: 'Base' },
      status: 'in_transit',
      details: { price: '1.66', date: '2026-05-03',
                 notes: 'Image 1 (1,1) — ref base-photos/sykes/2020-prizm-wnba-42/candidate-002.jpg · part of $14.99 9-card lot' } },

    // Image 1 (1,2) — Hyper
    { match: { player: 'sykes', year: 2020, product: 'Panini Prizm WNBA',
               cardNumber: '42', variant: 'Hyper Prizms' },
      status: 'in_transit',
      details: { price: '1.66', date: '2026-05-03',
                 notes: 'Image 1 (1,2) — ref parallels/prizm-wnba/hyper/candidate-001.jpg · part of $14.99 9-card lot' } },

    // Image 1 (1,3) — Ice (LOW conf — verify on receipt)
    { match: { player: 'sykes', year: 2020, product: 'Panini Prizm WNBA',
               cardNumber: '42', variant: 'Ice Prizms' },
      status: 'in_transit',
      details: { price: '1.66', date: '2026-05-03',
                 notes: 'Image 1 (1,3) — REVIEW NEEDED: leaning Ice but could be Snakeskin · part of $14.99 9-card lot' } },

    // [... 6 more entries ...]
  ],
  reviewNeeded: [
    { label: 'Image 1 (1,3) — Sykes 2020 Prizm #42 Ice vs Snakeskin (70% conf)',
      context: 'Pattern looks angular, leaning Ice based on shard sharpness. Verify on receipt — if scales appear rounder/more organic in person, change variant to "Snakeskin Prizms".' }
  ]
}
```

---

## Filed values reference

### `player`

The lowercase last-name key used throughout the tracker. Common keys for
the Tempo tracker:

```
sabally, sykes, harrison, nurse, rice, fagbenle, nye, wallace
```

For Tyler Black tracker, the player is always `tyler_black` — single-player
tracker.

### `product` (exact strings — must match SEED_CARDS exactly)

```
Panini Prizm WNBA
Panini Prizm Monopoly WNBA
Panini Revolution WNBA
Panini Origins WNBA
Panini Select WNBA
Donruss WNBA
Bowman University Best
Bowman University Chrome
Bowman University Inception
Topps Chrome McDonald's All American
```

### `variant` (must match SEED_CARDS exactly)

Common variants — see PARALLEL_GUIDE.md for the full list per product+year:

```
Base
Silver Prizms
Hyper Prizms
Ice Prizms
Snakeskin Prizms
Pulsar Prizms
Red Prizms
Blue Prizms
Green Prizms
Mojo Prizms
Gold Prizms
Lava
Holo
My House Press Proof
... etc
```

If you're not sure which exact variant string to use, search the user's
tracker source file for `variant:` examples to match the convention.

### `status`

```
not_owned    — default; not yet acquired
in_transit   — purchased but not received
owned        — physically received
```

### `details.price`

String, dollars only, no `$`. E.g. `"1.66"` not `"$1.66"`. Empty string
`""` if unknown. For lots, divide total by card count.

### `details.date`

ISO format `YYYY-MM-DD`. Use the **purchase date**, not today.

### `details.notes`

Free-form. Always include:
1. The image and grid coordinate(s): `"Image 1 (1,2)"`
2. The reference path used: `"ref parallels/prizm-wnba/hyper/candidate-001.jpg"`
3. Lot context if applicable: `"part of $X.XX N-card lot"`
4. Review flags if low confidence: `"REVIEW NEEDED: Ice vs Snakeskin"`

---

## Don't break things

These rules prevent the tracker from corrupting on apply:

- **`id` must be globally unique.** Re-using a bootstrap id won't re-apply
  it (idempotent), so don't reuse one if you actually want it to run.
- **Custom card `id` must be in 90000s and not collide with existing
  customs.** Search the existing BOOTSTRAPS for max custom id, increment.
- **`match` block fields must EXACTLY match SEED_CARDS.** A typo in
  `product` or `variant` causes a silent skip with a warning logged.
- **Don't put `id` in `cardMatches`.** The resolver uses `match` fields to
  find the seed card's id at apply-time. Hard-coding ids breaks if the
  checklist ever shifts.
- **Don't overwrite existing user data.** The bootstrap apply logic is
  non-destructive — it skips any field the user has already set. So a
  reapplied bootstrap won't clobber manually-edited prices/serials.

---

## Last updated

2026-05-03
