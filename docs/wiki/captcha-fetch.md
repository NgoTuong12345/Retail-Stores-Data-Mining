# Per-Store Detail Fetch (EnterpriseInfo + CAPTCHA)

**Status:** active
**Last updated:** 2026-06-30

**TL;DR:** Authoritative per-store detail (name, status, MST, legal form, `FOUNDING_DATE`,
rep, address) lives behind a reCAPTCHA on `EnterpriseInfo.aspx`. No automated bypass works;
the script navigates and extracts, the user solves each CAPTCHA manually. Chrome+CDP raises
the 🐴 anti-bot flag and forces image challenges — Scrapling/Camoufox (no CDP) avoids the flag.
This is the only source of real legal-founding dates (see [date-inference](date-inference.md)),
and the only source of a *verified* operating status — every license is unverified by default
until this fetch confirms it (see AGENTS.md's "Terminology" section and
[status-resolution](status-resolution.md)).

## Current understanding

<!-- STUB — fill progressively. -->

## Current solution

<!-- STUB -->

## Open Problems

| id | problem | status | impact |
|---|---|---|---|
| — | (none recorded yet) | — | — |

## Ruled out / dead ends

<!-- STUB: automated CAPTCHA bypass (none works); Chrome+CDP (raises 🐴 flag + image challenges). -->

## Progression Log

- 2026-06-30: page created as a stub.

## Links

- Code / tools: `scratch/bh_fetch.py` (browser-harness; user solves CAPTCHA), Scrapling/Camoufox fetcher
- Data: `brands/**/output/enterprise_details.json`
- Source docs: `docs/archive/superpowers/specs/2026-06-30-fetch-business-details-design.md`,
  `docs/archive/superpowers/specs/2026-06-30-avoid-image-challenge-strategy-design.md`
- Memory slugs: `enterprise-detail-bypass`, `horse-emoji-detection`, `recaptcha-image-challenge`

## Validate / reproduce

<!-- STUB -->
