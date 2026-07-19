# DKKD Retail Store Scraper

## What this is

Vietnam's government keeps a public business registry
([dichvuthongtin.dkkd.gov.vn](https://dichvuthongtin.dkkd.gov.vn)) where every
company has to register each physical location it operates. This project
reads that registry and turns it into a clean, usable map of where ~300
Vietnamese retail brands actually have stores — fashion, F&B, electronics,
gold, pharma, and more.

## What you get

For each brand, a spreadsheet-ready dataset with:

- Store address, city/district/ward
- Estimated opening date
- Whether the location looks like an active storefront, a warehouse, or a
  back-office (not every registration is a real shop)
- A best-guess read on whether it's open or closed, from indirect evidence
  (`Operating` / `Closed`) — every store starts `Unverified` by default, and
  only real per-store confirmation (solving the registry's CAPTCHA to read
  its actual business-status page) counts as ground truth

Results live under `brands/<industry>/<subsector>/<brand>/output/` as CSV and
Excel files — no database or special tooling needed to open them.

Sample rows (Bách Hóa Xanh, `output/bach-hoa-xanh_standard_schema.csv`):

| DKKD Internal ID | DKKD Enterprise ID | Store Brand | Store Type | Est. Opening | District | Province/City | Full Address |
|---|---|---|---|---|---|---|---|
| 2672036 | 0013119074 | Bách Hóa Xanh | Retail | 2015-11-19 | Quận Tân Phú | Thành phố Hồ Chí Minh | 267 Thoại Ngọc Hầu, Phường Phú Thạnh, Quận Tân Phú, Thành phố Hồ Chí Minh, Việt Nam |
| 5160119 | 0018417243 | Bách Hóa Xanh | Retail | 2018-08-07 | Thành phố Thủ Dầu Một | Tỉnh Bình Dương | 141 đường Trần Văn Ơn, Phường Phú Hòa, Thành phố Thủ Dầu Một, Tỉnh Bình Dương, Việt Nam |
| 5271263 | 0018664674 | Bách Hóa Xanh | Retail | 2018-09-22 | Thành phố Biên Hoà | Tỉnh Đồng Nai | 68A Khu phố 3, Phường An Bình, Thành phố Biên Hoà, Tỉnh Đồng Nai, Việt Nam |

## How it works, in plain terms

1. **Search the registry.** The government's search tool only returns 10
   results at a time and can't be paged through, so the scraper runs many
   different searches (brand name spelled different ways, known parent
   companies, etc.) until it stops finding anything new.
2. **Clean it up.** Not every registration is a real store — some are
   warehouses or head offices. A rules-based pass sorts out real storefronts,
   fills in likely opening dates, and figures out whether a location is still
   open.
3. **Package it.** The cleaned results are exported per brand as CSV/Excel,
   and also combined across all brands into one queryable dataset for
   cross-brand analysis.

## Methodology: an agentic search loop

The registry's search tool only returns 10 results per query with no
pagination, so finding "all of a brand's stores" takes many rounds of
searching, not one query. The scraper loops — try a strategy, see what's
new, pick the next strategy based on that — until three rounds in a row turn
up nothing, which is the signal a brand is fully covered. For the hardest
brands, an AI agent takes over the tail end of that loop, deciding what to
try next itself. Full details in `AGENTS.md` and `docs/wiki/`.

## Where to look

- `brands/` — one folder per brand, config + results.
- `docs/wiki/` — write-ups on specific problems (how opening dates are
  guessed, how duplicates are removed, how "still open" is decided).
- `AGENTS.md` — full technical operating manual, for anyone (human or AI)
  running or extending the scraper itself.


