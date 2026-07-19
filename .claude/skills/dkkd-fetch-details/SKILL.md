---
name: dkkd-fetch-details
description: Fetch per-store business details (name, operating status, MST, legal form, established date, rep, address) from DKKD EnterpriseInfo.aspx using browser-harness (default) or Scrapling/Camoufox (fallback). Use when the search-API Status field is insufficient and you need authoritative per-store detail. The user solves each reCAPTCHA manually; everything else is automated.
---

# DKKD Fetch Details

## When to use

Use when you need per-store **business detail / operating status** from the EnterpriseInfo page — i.e. the search API's `Status` field is `None`/insufficient and stores are stuck `Unverified`, or you're spot-checking `Date_Confidence`/`duplication_status` classifications against ground truth. Triggers: "fetch business details", "get operating status per store", "scrape EnterpriseInfo", "verify with real captcha data".

This is the **only** path that turns a license from unverified to verified (AGENTS.md's "Terminology" section) — every license is unverified by default, including ones the 7-rung evidence ladder (`dkkd/operating_status.py`) already inferred as Operating/Closed from locator pins or GDT signals.

## Default method: browser-harness

**As of 2026-07-02, browser-harness (CDP) is the default** — validated end-to-end fetching 30+ BHX stores in one session. The 🐴 anti-bot flag *does* appear (see Updated facts below) but it does **not** block the workflow.

Search + navigate to a store's EnterpriseInfo page:
```python
sid = "12824489"
goto_url("https://dichvuthongtin.dkkd.gov.vn/inf/default.aspx")  # new_tab() only for the very first navigation of a session
wait_for_load()
js("""
document.getElementById('ctl00_FldSearch').value = 'id:%s';
var h=document.getElementById('ctl00_FldSearchID'); if(h) h.value='%s';
document.getElementById('ctl00_btnSearch').click();
""" % (sid, sid))
```

Extract fields once the CAPTCHA is solved and the page has rendered (empty `name` means CAPTCHA is still blocking — screenshot and ask the user to solve it):
```python
EXTRACT_JS = r"""
(function(){
  function get(id){var el=document.getElementById(id);return el?(el.textContent||'').replace(/\s+/g,' ').trim():'';}
  return JSON.stringify({
    name:get('ctl00_C_NAMEFld'), status:get('ctl00_C_STATUSNAMEFld'),
    mst:get('ctl00_C_ENTERPRISE_GDT_CODEFld'), legal_form:get('ctl00_C_ENTERPRISE_TYPEFld'),
    established:get('ctl00_C_FOUNDING_DATE'), rep:get('ctl00_C_REPRESENTATIVE'),
    address:get('ctl00_C_HO_ADDRESS')
  });
})()
"""
data = json.loads(js(EXTRACT_JS))
```

**Batching multiple stores (the actual working pattern):** write one Python loop inside a single browser-harness heredoc that iterates the id list, navigates, polls the extraction JS every ~3s up to a per-store timeout (~120s), saves incrementally to `enterprise_details.json` (read-modify-write, so partial progress survives), and `break`s out (not crashes) on a timeout so one stuck CAPTCHA doesn't kill the whole batch. Run it via Bash `run_in_background` — batches of 10-15 stores take anywhere from seconds (session stays "trusted", zero CAPTCHAs) to several minutes (a CAPTCHA appears and the user needs to solve it). Full example: see the transcript from 2026-07-02, or reconstruct from the pattern above + a `for sid in remaining:` wrapper with a `time.sleep(3)` poll loop and a `save_result()` helper that re-reads/writes the JSON file each time.

**Do NOT eagerly poll before the user has had a chance to solve the very first CAPTCHA of a session** — screenshot, tell them a CAPTCHA is up, and wait for their explicit go-ahead. Once the user has confirmed the flow works and asks you to "continue automatically" / "don't make me say done every time", switch to the full auto-poll-and-continue loop described above — that's an explicit escalation the user grants, not a default to assume.

If a CDP call times out (`TimeoutError` in `_ipc.py`), the session went stale — call `ensure_real_tab()` and retry; this recovers cleanly and is not a sign of a wedged browser.

## Updated facts (2026-07-02, supersedes prior CDP guidance)

- **The 🐴 horse-emoji anti-bot flag DOES appear under browser-harness/CDP** (confirmed: title showed `🐴 Trang chủ` / `🐴 Thông tin cơ bản` on every page). This matches [[horse-emoji-detection]] — it is real and not fixable within CDP.
- **But it does NOT block the workflow the way earlier sessions assumed.** In practice: the very first CAPTCHA of a session showed the *easy checkbox* (not an image challenge), and once solved, the site's trust/session cookie persisted across dozens of subsequent fetches with **zero further CAPTCHA prompts** — 10 stores in a row, then 13 more, then 6 more, all auto-extracted with no human interaction needed. CAPTCHAs reappeared only intermittently afterward (consistent with [[recaptcha-image-challenge]]'s IP-reputation model, not a horse-flag consequence).
- **Net effect: browser-harness is a fully viable default for this task**, contradicting the older "do NOT use browser-harness/Chrome for this, do NOT re-chase" guidance in [[horse-emoji-detection]] and [[enterprise-detail-bypass]] — that guidance was accurate for what it tested at the time, but the outcome in practice (CAPTCHA frequency, session persistence) is much better than it predicted. Use browser-harness first; fall back to Scrapling/Camoufox (below) only if a session gets stuck in a hard image-challenge loop that `ensure_real_tab()` doesn't clear.
- **The CAPTCHA cannot be bypassed either way.** The EnterpriseInfo detail is server-gated on every host; reading without solving returns a 612-byte gate. The user must solve each one that actually appears.

## Fallback method: Scrapling/Camoufox — NOT IMPLEMENTED

`scraper/fetch_details.py` does not exist in this repo. Only the design doc under
`docs/archive/superpowers/specs/` survives. **browser-harness is the only working path**
for this skill today. If a browser-harness session gets stuck with the site consistently
forcing image challenges, there is currently no fallback runner — retry with
`ensure_real_tab()` or wait for the user to clear the challenge.

## Output

`brands/<...>/<slug>/output/enterprise_details.json` — keyed by store Id, each with
`name, status, mst, legal_form, established, rep, address, url, captcha, store_id`.
**Resumable regardless of method:** stores already saved with a `name` are skipped. The
target id list is `unverified_ids.json` in the same dir — append targeted ids there
(don't overwrite; preserve any pending ids from earlier sessions) rather than replacing it.

## Use with /goal

`/goal fetch all <slug> business details` → invoke this skill, run the loop (browser-harness
by default), and treat success as `enterprise_details.json` covering every id in
`unverified_ids.json`. The user solves CAPTCHAs as they appear; the loop is resumable
across runs and methods (a partial Scrapling run and a partial browser-harness run both
write to the same `enterprise_details.json`).

## References

- `docs/archive/superpowers/specs/` — design doc for this workflow, including the never-built Scrapling/Camoufox fallback
- memory: enterprise-detail-bypass, horse-emoji-detection, recaptcha-image-challenge, feedback-browserharness-default
