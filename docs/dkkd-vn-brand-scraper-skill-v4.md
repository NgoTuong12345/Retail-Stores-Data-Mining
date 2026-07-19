# DKKD-VN Brand Scraper Skill (v4)

Site: https://dichvuthongtin.dkkd.gov.vn/inf/default.aspx
Endpoint: POST /inf/Public/Srv.aspx/GetSearch
Final CO.OP FOOD result: 478 unique stores (converged in v3; v4 adds structural analysis and corrections).

**v4 changelog:**
- §11 `City_Id` table corrected — 4 of top 8 rows were wrong in v3 (81, 127, 128, 138).
- §4.5 added — parsing the two formats of `Enterprise_Gdt_Code`.
- §6-O extended — parent-MST sweep from Gdt_Code left-side, not just Enterprise_Code prefixes.
- §6-J revised — mechanism explanation for `+N` and dynamic probe cap.
- §7 dedup rule reworded for clarity.

## 1. What this site is

Vietnam's National Business Registration Information Portal (Bộ Kế hoạch & Đầu tư / Cục Quản lý Đăng ký Kinh doanh). Public search page backed by an Apache Solr index over the business registry. The homepage has a text search that posts to `/inf/Public/Srv.aspx/GetSearch` and returns up to 10 JSON rows per call. Detail pages are reCAPTCHA-gated — we never touch them.

## 2. Minimum viable client

All scraping is done from the browser console via `XMLHttpRequest`. No Selenium / Playwright (the site fingerprints headless automation).

### 2.1 Required headers
```
POST /inf/Public/Srv.aspx/GetSearch HTTP/1.1
Content-Type: application/json; charset=utf-8
X-Requested-With: XMLHttpRequest
```

### 2.2 Required payload (loose JSON)
```json
{ "searchField": "<keyword>", "h": "<token>" }
```

### 2.3 Token `h`
The `h` field is a server-issued anti-replay token rendered into the homepage HTML at `#ctl00_hdParameter`. It rotates per page load and expires after a few minutes of idle. Refresh by re-fetching the homepage and parsing the hidden input.

```js
window.__refreshH = async () => {
  const r = await fetch('/inf/default.aspx', { cache: 'no-store', credentials: 'same-origin' });
  const html = await r.text();
  const m = html.match(/id="ctl00_hdParameter"[^>]*value="([^"]+)"/);
  if (!m) throw new Error('h token not found');
  window.__H = m[1];
  return window.__H;
};
```

Refresh cadence: call once at start, and again every ~500 queries or when responses start returning `d: null`.

## 3. Core helpers

```js
window.__sleep = ms => new Promise(r => setTimeout(r, ms));

window.__search = (kw, extra = {}) => new Promise((res, rej) => {
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/inf/Public/Srv.aspx/GetSearch', true);
  xhr.setRequestHeader('Content-Type', 'application/json; charset=utf-8');
  xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
  xhr.onload = () => {
    try {
      const j = JSON.parse(xhr.responseText);
      let d = j.d;
      if (typeof d === 'string' && d) d = JSON.parse(d);   // legacy form
      res(Array.isArray(d) ? d : []);
    } catch (e) { rej(e); }
  };
  xhr.onerror = () => rej(new Error('xhr error'));
  xhr.send(JSON.stringify({ searchField: kw, h: window.__H, ...extra }));
});

// Retry wrapper: refreshes h on empty response
window.__searchSafe = async (kw, extra) => {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const rows = await window.__search(kw, extra);
      if (rows.length) return rows;
      if (attempt === 0) await window.__refreshH();
      await window.__sleep(200);
    } catch (e) {
      await window.__sleep(500);
      try { await window.__refreshH(); } catch (_) {}
    }
  }
  return [];
};
```

## 4. Brand filter & ingester

The CRITICAL bug that silently cost us 50+ rows: the API returns `Name`, NOT `Title`. Use both `Name` and `Name_F` (ASCII-folded variant) when filtering.

```js
window.__RE_CF = /CO[\.\,\-]?\s*OP\s*FOOD|COOPFOOD/i;   // CO.OP FOOD example
window.__CF = window.__CF || new Map();   // dedupe by Id

window.__ingest = rows => {
  for (const r of rows) {
    if (!r || !r.Id) continue;
    const n = (r.Name || '') + ' ' + (r.Name_F || '');
    if (!window.__RE_CF.test(n)) continue;
    window.__CF.set(r.Id, r);
  }
};
```

Row fields observed:

`__type, Id, Name, Name_F, Short_Name, Enterprise_Code, Enterprise_Gdt_Code, Status, City_Id, District_Id, Ward_Id, Ho_Address, Ho_Address_F, Legal_First_Name`

## 4.5 Understanding the ID fields (new in v4)

Analyzed from the converged 478-row CO.OP FOOD export. Apply the same parsing to any brand scrape.

### 4.5.1 `Id` — NBRP internal primary key
6–8 digit integer (range 390,325 – 12,608,127 in this dataset). Auto-increment. Not a public identifier; only useful as the row key inside the portal. Always dedupe on this.

### 4.5.2 `Enterprise_Code` — the MST (tax code / ERC)
10 characters, zero-padded with leading `00`. The real MST starts at position 3. All 478 unique in this dataset.

Top prefixes (after the `00` padding): `17, 18, 19, 20, 23, 35, 36`. VN MSTs are **sequentially issued, not province-coded** — prefix just reflects registration vintage (lower = older).

### 4.5.3 `Enterprise_Gdt_Code` — two formats, parse them separately

This field looks uniform but has **two incompatible formats** that encode different things:

**Format A — 5-digit sequential counter** (`00001` – `00279`, 342 / 478 rows)
- Used for ĐỊA ĐIỂM KINH DOANH (business-location) records.
- Pure counter scoped to parent enterprise. **No parent link encoded in the value itself** — you must join via name or address.

**Format B — 14-char `<parent_MST>-<branch_NNN>`** (134 / 478 rows)
- Pattern regex: `^(\d{10})-(\d{3})$`
- Used for CHI NHÁNH (branch) records.
- Encodes the parent-child hierarchy **explicitly**.
- In this dataset, 126 / 134 point to parent `0309129418` (Công ty TNHH MTV Thực phẩm Saigon Co.op). Branch suffixes run `001` – `146`.
- Important: `Enterprise_Code` (branch's own MST) ≠ the MST embedded in Gdt_Code (parent MST). Zero overlap across all 134 rows.

Parsing helper:

```js
window.__parseGdt = (gdt) => {
  if (!gdt) return { format: 'empty' };
  if (/^\d{5}$/.test(gdt)) return { format: 'counter', seq: parseInt(gdt, 10) };
  const m = /^(\d{10})-(\d{3})$/.exec(gdt);
  if (m) return { format: 'branch', parentMst: m[1], branchSeq: parseInt(m[2], 10) };
  return { format: 'other', raw: gdt };
};
```

Post-processing pattern after convergence:

```js
// Extract all parent MSTs seen in 14-char Gdt_Codes
const parents = new Set();
for (const r of window.__CF.values()) {
  const p = window.__parseGdt(r.Enterprise_Gdt_Code);
  if (p.format === 'branch') parents.add(p.parentMst);
}
console.log('Parent MSTs discovered:', [...parents]);
// Feed these back into Strategy O (see §6-O).
```

### 4.5.4 Geographic IDs — NBRP-internal, not GSO codes

`City_Id`, `District_Id`, `Ward_Id` are the portal's internal foreign keys, **not** Vietnam's General Statistics Office (GSO) statistical codes. Don't assume they map to anything public.

- `City_Id`: 16 unique values in this dataset, range 81–142. Corrected mapping in §11.
- `District_Id`: populated on only 360 / 478 rows. Consistent with the July 2025 two-tier admin reform that eliminated the district level — new records skip it.
- `Ward_Id`: 5-digit, 300 unique, range 11,516 – 38,253. Populated on all 478. Now the primary sub-province key.

## 5. The hard API ceiling (discovered in v3)

**The endpoint returns a maximum of 10 rows per query.** Not 1000, not 100 — exactly 10. There is NO pagination, offset, page, skip, start, from, limit, take, top, pageSize, or rows parameter that works. All silently ignored.

Therefore, the ONLY way to scrape the full brand footprint is to issue many diverse keywords and union the 10-row top-N slices.

Sort-like parameters (`sort`, `sortField`, `sortBy`, `orderBy`, `SortField`, `SortBy`, `OrderBy`) DO change the 10-row slice, but only cycle ~25 distinct rows for any given brand keyword — the candidate pool is small and already exhausted by keyword diversity.

Filter-like parameters (`cityId`, `City_Id`, `province`, `fq`) appear to change output but actually do not filter — mixed-city rows still appear. Not usable.

## 6. The Amplifier Ladder (all strategies, in order of discovery & yield)

Goal of each amplifier: issue a batch of distinct keywords, union the 10-row responses, dedupe by `Id`, keep rows whose `Name` matches the brand regex.

### A. Brand-variant spellings
Try every plausible spelling/spacing/punctuation of the brand:
`CO.OP FOOD`, `COOP FOOD`, `Co.op Food`, `Coop Food`, `Co-op Food`, `CO,OP FOOD`, `COOPFOOD`, `Co.opFood`, `CoOpFood`, `CoopFoods`.

### B. Numeric address probes
Many store names are `"<BRAND> <number> <street>"`. Probe integers:
- Dense N=1..999 with `BRAND N` and bare `N`
- Sparse N=1000..5000 stride 7
- Stride-13 above that up to ~20000 for apartment/complex numbers

### C. Region / province two-letter codes
Vietnamese two-letter region codes: HN, HCM, BD, BH, BR, CT, DN, LA, TN, VT, TH, PY, HT, LO, AG, BG, BP, CM, HP, HY, KT, LD, ND, NA, NB, PT, QB, QN, ST, SG, TB, TG, TV, VL, YB, DL, GL, KH, QG, QT, TT, DB, HB, HG, LS, SL, DP.
Run each LOWERCASE and UPPERCASE — case sensitivity matters (see §7).

### D. Bigram/trigram drill-down
After first pass, tokenize all collected Name/Name_F/Ho_Address fields and feed back the rare bigrams (frequency 1-3) as queries.

### E. Parent-name phrase triangulation
For SGC-style subsidiaries, query the parent entity name with and without diacritics: `Saigon Co.op`, `SAIGONCOOP`, `LIÊN HIỆP HỢP TÁC XÃ`, `LHHTX`, `SGC`.

### F. 2-letter alphabet sweeps (both cases)
- Lowercase: iterate all `aa`..`zz` (676 probes).
- UPPERCASE: iterate `AA`..`ZZ`. **These surface different rows** — `BL` uppercase found 2 Bạc Liêu stores that lowercase `bl` missed.

### G. Unicode-diacritic Vietnamese word sweep (BIG yield)
This was the single biggest breakthrough. The tokenizer is diacritic-aware — folded-ASCII tokens and Unicode tokens index differently. Run a curated list of Vietnamese monosyllables in NFC form:

`Trường, Liên, Đăng, Tình, Làng, Mặn, Ngỗ, Vườn, Xóm, Tài, Cái, Gỗ, Cả, Phú, Bình, Tân, Thảo, Tịnh, Mẫn, Hương, Quốc, Sông, Huyên, Dương, Hưởng, Ngọc, Trầm, Hồng, Bích, ...`

Diacritic tokens routinely find rows that their ASCII-folded equivalents miss (and vice-versa). **Always run BOTH.**

### H. Vietnamese district / ward name sweep
Provinces are ~63; districts ~700; wards ~10k. Use the top 200-300 district names (plus folded-ASCII variants) as keywords: `Nha Be`, `Tan Tru`, `Cat Lai`, etc.

### I. Legal-rep name mining
Extract `Legal_First_Name` tokens from current collected rows. For CO.OP FOOD, top reps were PHẠM NỮ ÁNH HUYÊN (377 of 478), NGÔ TRIỀU DƯƠNG (29), VÕ THỊ NGỌC HƯỜNG (19). Querying individual tokens (`quoc`, `huong`, `song`) surfaced 6 new rows. Always try first-name tokens both folded and Unicode.

### J. Special-character Solr escape `+N` (BIG yield — mechanism clarified in v4)
The most exotic discovery. Prepending `+` to a digit sequence triggers a Solr required-term operator and returns a COMPLETELY DIFFERENT top-10.

**Why it works (v4 analysis):** Solr tokenizes the numeric tails embedded in `Enterprise_Gdt_Code` — both the 5-digit counter (`00001`–`00279`) and the 3-digit branch suffix after the hyphen (`001`–`146`). `+N` is a required-term match against those integer tokens, which is why the slice rotates so dramatically.

**Dynamic probe cap (new in v4):** instead of blindly probing `+1`..`+5000`, do a first pass with `+1`..`+50`, parse the collected `Enterprise_Gdt_Code` values, then set the probe ceiling to `max(max_counter, max_branch_suffix) × 1.2`. For CO.OP FOOD that's `max(279, 146) × 1.2 ≈ 335`, so `+1`..`+335` is sufficient. Anything beyond ~500 is wasted calls.

Other special chars tested (`-N *N ^N %N ~N /N &N #N @N !N ?N =N |N <N >N`) over N=1..100 = 0 hits. Only `+` behaves as a Solr escape.

### K. UPPERCASE acronym probes
`KDC`, `CC`, `CH`, `CN`, `CTY`, `DVT`, `TMDV`, `CHCF`, `CHTM`, `VPDD` — small but real yield (`KDC`=+3, `CC`=+2).

### L. Ho_Address token mining
Tokenize every `Ho_Address` / `Ho_Address_F` on collected rows, extract rare tokens (frequency ≤ 3, length ≥ 3, non-stopword), feed back as queries. For CO.OP FOOD this yielded 0 new on top of earlier sweeps but proved convergence.

### M. Compound diacritic bigrams
Pair successful Unicode tokens: `Trường + Liên`, `Vườn + Xóm`, `BRAND + Tài`, etc. 0 new for CO.OP FOOD but a useful sanity check.

### N. Brand siblings & phrasings
If the brand is part of a family (`Co.opmart`, `Cheers`, `Co.opXtra`), query siblings — sometimes a misclassified store surfaces. Also probe Vietnamese retail phrasings: `Chi nhánh`, `Cửa hàng`, `Địa điểm kinh doanh`, `VPDD`, `CN`, `CH`, `CHTM`, `TMDV`.

### O. Enterprise code sweep (extended in v4)
**Old behavior (v3):** collect all `Enterprise_Code` values, extract 3-7 digit prefixes, feed top prefixes back as queries. For CO.OP FOOD this yielded 0 new — likely because Solr strips leading zeros during tokenization, making `00xx` prefix matches degenerate.

**Extended behavior (v4):** also extract **parent MSTs** from the left side of 14-char `Enterprise_Gdt_Code` entries (pattern `^(\d{10})-\d{3}$`). These are literal 10-digit strings that Solr does tokenize. For CO.OP FOOD this yields `0309129418`, `0305767459`, `0302271510`, `0310178586`, `0314077109`, `0305781598`, `0308425100`, `0305757161` — 8 parent MSTs to probe.

```js
// v4 Strategy O implementation
window.__sweepParentMsts = async () => {
  const mstSet = new Set();
  for (const r of window.__CF.values()) {
    const m = /^(\d{10})-\d{3}$/.exec(r.Enterprise_Gdt_Code || '');
    if (m) mstSet.add(m[1]);
  }
  console.log(`Probing ${mstSet.size} parent MSTs...`);
  for (const mst of mstSet) {
    const rows = await window.__searchSafe(mst);
    window.__ingest(rows);
    await window.__sleep(60);
  }
};
```

Worth running on every brand — this is an untested angle for most brand sweeps.

### P. Sort-flip cache-buster
Append any unknown param (e.g. `sortField: Id`, `sortBy: Name desc`, `orderBy: Id desc`) to re-roll the 10-row slice for the same keyword. Cycles through ~25 distinct rows per keyword. Useful as a final polish pass.

## 7. Cross-cutting rules

- **Case matters.** `bl` and `BL` return different results. Always run lowercase AND UPPERCASE.
- **Diacritics matter.** `truong` and `Trường` return different results. Always run folded-ASCII AND Unicode-diacritic.
- **Filter on `Name`, not `Title`.** API field is `Name`. Using `Title` silently drops every row.
- **Dedupe by `Id`.** (v4 clarification) `Enterprise_Code` is typically unique per entity, but `Enterprise_Gdt_Code` embeds the parent MST in 14-char-format rows — so the same 10-digit MST can appear as the "own code" for one row and as the "parent code inside Gdt" for many others. Don't build dedup logic on any code field; `Id` is the only safe key.
- **10-row cap is absolute.** No pagination. Brute-force breadth is the only strategy.
- **Throttle to ~40-100 ms** between calls; pause 200 ms every 40-60 calls to avoid rate-limit drops.
- **Refresh `h` every ~500 calls** or when responses start returning `d: null`.
- **Run long sweeps as background async IIFEs** — CDP's Runtime.evaluate times out at 45 s.
- **Persist state to localStorage** periodically. Clean old `__CF_v*_baseline` entries before saving to avoid `QuotaExceededError`.

## 8. Background sweep pattern

```js
window.__sweep = (probes, tag) => {
  const S = window['__s' + tag] = { i: 0, total: probes.length, hits: {}, done: false, errs: 0 };
  (async () => {
    for (let i = 0; i < probes.length; i++) {
      S.i = i;
      try {
        const before = window.__CF.size;
        const rows = await window.__searchSafe(probes[i]);
        window.__ingest(rows);
        const added = window.__CF.size - before;
        if (added > 0) S.hits[probes[i]] = added;
      } catch(e) { S.errs++; }
      await window.__sleep(i % 40 === 39 ? 200 : 40);
      if (i % 500 === 499) { try { await window.__refreshH(); } catch(_){} }
    }
    S.done = true;
    S.after = window.__CF.size;
  })();
  return 'sweep ' + tag + ' launched: ' + probes.length;
};
```

Poll by reading `window.__s<tag>.i / .total / .done / .hits`.

## 9. Persistence pattern

```js
window.__save = (ver) => {
  // drop old versions to avoid QuotaExceededError
  Object.keys(localStorage)
    .filter(k => k.startsWith('__CF_v') && k !== ('__CF_v' + ver + '_baseline'))
    .forEach(k => { try { localStorage.removeItem(k); } catch(_){} });
  localStorage.setItem('__CF_v' + ver + '_baseline', JSON.stringify([...window.__CF.entries()]));
};

window.__load = (ver) => {
  const raw = localStorage.getItem('__CF_v' + ver + '_baseline');
  if (!raw) return 0;
  window.__CF = new Map(JSON.parse(raw));
  return window.__CF.size;
};
```

## 10. XLS export pattern (Excel-compatible HTML table)

```js
window.__exportXls = (filename) => {
  const rows = [...window.__CF.values()];
  const keys = [...new Set(rows.flatMap(r => Object.keys(r)))].filter(k => k !== '__type');
  const esc = s => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  let html = '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="UTF-8"></head><body><table border="1">';
  html += '<tr>' + keys.map(k => '<th>' + esc(k) + '</th>').join('') + '</tr>';
  for (const r of rows) html += '<tr>' + keys.map(k => '<td>' + esc(r[k]) + '</td>').join('') + '</tr>';
  html += '</table></body></html>';
  const blob = new Blob([html], { type: 'application/vnd.ms-excel' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 10000);
};
```

## 11. CO.OP FOOD convergence curve (case study)

| Version | Rows | Δ   | Milestone |
|---------|------|-----|-----------|
| v1      | 277  | —   | Initial brand-variants only |
| v2      | 288  | +11 | API-response format fix + `CO,OP FOOD` |
| v3      | 342  | +54 | Token-cooldown + `COOPFOOD` no-space |
| v4-sweep      | 361  | +19 | Bigrams + parent-phrase + apartment drill-down |
| v6      | 409  | +48 | **Name-vs-Title filter fix** + dense numeric 1-999 |
| v7      | 422  | +13 | District names + ALL-CAPS 2-letter (`BL`) + legal-rep mining |
| v8      | 451  | +29 | **Unicode diacritic Vietnamese words** (`Trường`, `Liên`, `Đăng`, `Tình`, `Làng`) |
| v9      | 478  | +27 | **`+N` Solr-escape prefix** (`+1`, `+3`, `+192`) + `Vườn`/`Xóm`/`Tài` |
| v10     | 478  | 0   | **Converged** — exotic angles (sort flips, pagination probes, city filter) confirmed ceiling |

### Final city breakdown (corrected in v4)

v3's table had 4 wrong province labels. Verified by parsing `Ho_Address` text:

| City_Id | Province (corrected)       | Rows | v3 said |
|---------|---------------------------|------|---------|
| 122     | Hồ Chí Minh               | 380  | HCMC ✓ |
| 81      | **Hà Nội**                | 19   | Long An ❌ |
| 138     | **Cần Thơ**               | 19   | Đồng Nai ❌ |
| 127     | **Bình Dương**            | 14   | BR-VT ❌ |
| 128     | **Đồng Nai**              | 13   | Bình Dương ❌ |
| 116     | Phú Yên                   | 11   | Phú Yên ✓ |
| 108     | Hà Tĩnh                   | 5    | Hà Tĩnh ✓ |
| 106     | Thanh Hóa                 | 3    | — |
| 129     | Bình Thuận                | 3    | — |
| 126     | Tây Ninh                  | 2    | — |
| 84      | Hưng Yên                  | 2    | — |
| 141     | Sóc Trăng                 | 2    | — |
| 142     | Bạc Liêu                  | 2    | — |
| 82      | Hải Phòng                 | 1    | — |
| 131     | Long An                   | 1    | — |
| 135     | Vĩnh Long                 | 1    | — |

Note: addresses reflect a mix of pre- and post-July-2025 provincial merger naming (e.g. Dĩ An still shown under "Tỉnh Bình Dương" on older records, under "Thành phố Hồ Chí Minh" on newer ones). The `City_Id` itself predates the merger.

## 12. Reusable template for a new brand

1. **Set the regex.** Design `__RE_CF` to capture the brand plus all plausible spacings/punctuations/concatenations.
2. **Seed pass.** Query all brand-variant spellings and union results.
3. **Numeric pass.** `BRAND N` for N=1..999 dense, N=1000..5000 stride 7.
4. **Region-code pass.** 2-letter codes lowercase AND uppercase.
5. **2-letter alphabet pass.** `aa`..`zz` lowercase AND `AA`..`ZZ` uppercase.
6. **Unicode-diacritic pass.** Full Vietnamese monosyllable dictionary (NFC form).
7. **District / ward pass.** Folded + Unicode district names.
8. **Address-token mining pass.** Tokenize collected Ho_Address, feed back rare tokens.
9. **Legal-rep mining pass.** Tokenize Legal_First_Name, feed back tokens folded + Unicode.
10. **`+N` Solr-escape pass.** Start with `+1`..`+50`. Then parse collected `Enterprise_Gdt_Code` values with `__parseGdt`, find `max(counter, branch_suffix)`, and run `+1`..`+(max × 1.2)`.
11. **Enterprise code sweep (v4).** Run `__sweepParentMsts()` to probe every parent MST extracted from 14-char Gdt_Codes. Also try 3-7 digit prefixes of `Enterprise_Code` as a secondary polish (low yield).
12. **Sort-flip polish.** Re-run top brand queries with `sortField: Id`, `sortBy: Name desc`, `orderBy: Id desc` to squeeze last rows.
13. **Convergence check.** When 3 consecutive amplifiers yield 0, stop. Export.

Expected cost: ~5000-15000 queries, ~10-30 minutes wall-clock, depending on brand footprint.

## 13. What DOES NOT work (don't waste time)

- Pagination/offset params (`offset`, `start`, `skip`, `page`, `from`, `limit`, `take`, `top`, `pageSize`, `rows`) — silently ignored.
- City/District filter params (`cityId`, `City_Id`, `province`, `fq: City_Id:X`) — appear to flip order but don't filter.
- Solr field-qualified queries (`Name:FOOD`, `City_Id:122`, `*:*`) — parsed as literal text and return nothing.
- Wildcard queries (`*Food`, `Ph*`, `*mart`) — treated literally, return 0.
- Most special-char prefixes (`-N *N ^N %N ~N /N &N #N @N !N`) — 0 new.
- Empty searchField — returns `d: null`.
- Queries with only punctuation (`.`, `,`) — return 0.
- **Enterprise_Code prefix sweep `00xx`** (v4 note) — Solr strips leading zeros during tokenization, so matching on padded prefixes is degenerate. Sweep the parent MSTs from Gdt_Code instead.

## 14. Ethical & legal guardrails

- Public endpoint, public data, no login required.
- Respect the 10-row cap (don't probe for higher).
- Never touch the reCAPTCHA-gated detail page.
- Throttle to be a good citizen (~15 req/sec peak, with pauses).
- Do not redistribute personal data (Legal_First_Name) beyond your internal analysis.

---

_Document version: v4. Last updated: 2026-04-23. Author: collaborative Claude + user iterative session. v4 adds ID-field analysis (§4.5), corrected City_Id mapping (§11), extended Strategy O with parent-MST sweep (§6-O), dynamic `+N` probe cap (§6-J), and clarified dedup rule (§7)._
