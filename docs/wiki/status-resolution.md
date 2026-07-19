# Operating-Status Resolution (3-state)

**Status:** active
**Last updated:** 2026-07-20

**TL;DR:** Verified vs. unverified is the primary axis (see AGENTS.md's "Terminology"
section). Every license is **unverified by default** — that includes anything the
ladder below infers as Operating/Closed, since it's a confidence-scored guess, not
a captcha-confirmed fact. A license only becomes **verified** once its
EnterpriseInfo.aspx detail page has been fetched past the reCAPTCHA gate (the
`dkkd-fetch-details` skill). What follows is *how* the unverified inference — the
3-state `Operating_Status` (Operating / Closed / Unverified) — gets made via a
locator-driven evidence ladder: per-store operating status is not bulk-retrievable
from DKKD (paid/auth-gated), so the locator pin is the primary signal, with masothue,
Format-A branch-name city matching, and DPI dissolution lists as supporting sources.
Active status is only propagated with per-store evidence; otherwise a store lands on
Unverified rather than being falsely promoted.

## Current understanding

Every DKKD record starts as a **license** — a registration filed with the registry,
not evidence of an open store. `Core_Operating_Store` and `Operating_Status` are how
a license gets promoted to "store" (see CLAUDE.md/AGENTS.md's "Terminology" section
for the license-vs-store definition this page assumes throughout). Both fields are
still an **unverified** inference regardless of what value they hold — see the
Terminology section's verified/unverified framing.

Two resolution paths exist, selected by `config.classification.operating_status.enabled`:

- **Opt-in brands** (`_resolve_optin` in `dkkd/operating_status.py`): a 7-rung
  evidence ladder, first match wins —
  1. Corporate/Logistics name → Closed
  2. Structural: parent-MST dissolution propagation → Closed
  3. Ceased status phrases (chấm dứt, giải thể, tạm ngừng, ...) → Closed
  4. Locator pin match (Unique / Shared_Co-located) → **Operating** (`Core_Operating_Store=Yes`)
  5. Structural: address-supersession by a newer record → Closed
  6. Own-MST GDT-active status, not a seed parent MST → **Operating** (`Core_Operating_Store=Yes`)
  7. Otherwise → **Unverified** (`licensed-unverified`) — still just a license, `Core_Operating_Store=No`
- **Legacy/non-opt-in brands** (`_resolve_legacy`): binary derivation from whatever
  `Core_Operating_Store` classification already set — Yes → Operating, No → Closed.
  No Unverified state; these brands never had the evidence ladder run.

Only rungs 4 and 6 ever set `Core_Operating_Store = 'Yes'`. Everything else — Closed
*and* Unverified — is `'No'`. This is deliberate: an unverified license must never be
silently counted as an operating store.

## Current solution

`resolve_operating_status()` mutates each record's `Operating_Status`,
`Operating_Evidence`, and `Core_Operating_Store` in place during `postprocess`
Stage 4. `load_locator_pins()` reads confirmed matches from
`output/{slug}_store_mapping.csv` (written by the `dkkd-fetch-details` /
locator-matching flow) — a brand with no mapping file simply has an empty
locator-pin set, so opt-in brands with no fetched details fall through to
rung 7 (Unverified) for everything, which is correct: no evidence, no promotion.

## Open Problems

| id | problem | status | impact |
|---|---|---|---|
| — | (none recorded yet) | — | — |

## Ruled out / dead ends

<!-- STUB -->

## Progression Log

- 2026-06-30: page created as a stub.
- 2026-07-07: filled "Current understanding"/"Current solution" with the 7-rung
  ladder and the license-vs-store framing (see AGENTS.md's Terminology section).

## Links

- Code: `dkkd/operating_status.py`, `dkkd/enrich.py` (`refine_entity_statuses`,
  `resolve_format_a_branch_statuses`, `refine_statuses_from_dpi`), `dkkd/postprocess.py`
- Tests: `tests/test_operating_status.py`, `tests/test_postprocess_3state.py`
- Source docs: `docs/archive/superpowers/specs/2026-06-29-operating-status-3state-design.md`
- Memory slugs: `dkkd-per-store-status-sourcing`, `operating-status-3state-plan`

## Validate / reproduce

<!-- STUB -->
