# DKKD Problem Wiki

A flat, LLM-readable knowledge base of self-contained **problem pages**. Each page is a
*living problem record* — current understanding, the shipped solution, an Open-Problems
register, what's been **ruled out**, and a dated Progression Log — so future sessions
**solve and improve each problem progressively** instead of re-deriving findings or
re-trying dead ends.

This wiki is a navigable summary + tracker. It **links to** the canonical deep docs
(`AGENTS.md`, `docs/dkkd_database_hierarchy.md`, the dated `docs/*.md` references, code, memory)
— it does not duplicate them.

## How to use it

1. **Before working a known problem,** read its page top-to-bottom. Check **Open Problems**
   and **Ruled out** first — they tell you what's unsolved and what not to retry.
2. **When you learn something,** append a dated entry to that page's **Progression Log**
   (what changed, why, what you ruled out) and update **Open Problems**.
3. **To add a new problem,** copy [`_TEMPLATE.md`](_TEMPLATE.md), fill the header + sections,
   and add a row to the registry + any open problems to the table below.

## Problem registry

| page | status | one-liner | last updated |
|---|---|---|---|
| [date-inference](date-inference.md) | active | `Establishment_Date` = activation estimate; `Date_Confidence` rates founding-usability; ~2010 floor | 2026-06-30 |
| [status-resolution](status-resolution.md) | active | verified (captcha-confirmed) vs. unverified (ladder-inferred) is the primary axis; the 3-state Operating/Closed/Unverified ladder is locator-driven | 2026-07-20 |
| [captcha-fetch](captcha-fetch.md) | active | per-store EnterpriseInfo fetch; manual CAPTCHA; the only real-founding source | 2026-06-30 |
| [dedup](dedup.md) | stable | dedupe on `Id` only; filter on `Name`/`Name_F` not `Title` | 2026-06-30 |
| [scraping-amplifiers](scraping-amplifiers.md) | stable | keyword-diversity ladder; converge on 3 zero-yield phases | 2026-07-19 |
| [gdt-format-patterns](gdt-format-patterns.md) | active | Format A (counter) vs Format B (branch) GDT registration; MST fragmentation ratio drives `hierarchy_walk` caps | 2026-07-19 |
| [session-timeout](session-timeout.md) | stable | 20-min DKKD session timeout modal; selectors + keep-alive snippets | 2026-07-19 |

## Open problems (all pages)

| id | page | problem | status |
|---|---|---|---|
| P1 | date-inference | `exact` tier ships activation dates with no `Date_Basis` column to exclude them as non-founding | open |
| P2 | date-inference | an Id-axis-decoupled brand could earn a false `high` (suffix-axis cap is a proxy) | open(untested) |
| P3 | date-inference | pre-~2010 founding unrecoverable from `Id`/`ngay_hd` (system floor) | unrecoverable |
| P4 | date-inference | non-PNJ brand CSVs stale vs current model until a `postprocess` refresh | open |
| P5 | date-inference | sparse / Format-A stores always `low` (unvalidated) | wontfix |

## Conventions

- **Page status:** `stable` (solved, low-churn) · `active` (in use, evolving) · `open`
  (unsolved core problem) · `floor` (bounded by an external system limit).
- **Open-problem status:** `open` · `open(untested)` · `mitigated` · `unrecoverable` · `wontfix`.
- **Confidence tags** on non-obvious claims: `[empirical]` (measured in our data) ·
  `[documented]` (in a project doc / regulation) · `[inferred]` (reasoned, unverified).
- **Page lifecycle:** `stub → active → stable`. A stub has the header + empty section
  skeleton + Links; fill it progressively.
