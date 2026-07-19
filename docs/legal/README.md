# DKKD Legal Reference

Primary-source Vietnamese legal texts that explain *why* DKKD.gov's data schema and business-registration
patterns look the way they do — not secondary commentary. Full verbatim text, not summaries, since exact
article wording matters for interpreting schema edge cases correctly.

Two things this collection explains:
1. **`enterprise-registration/`** — the registration-law chain behind `Enterprise_Code`, `Enterprise_Gdt_Code`
   formats A/B, and the legal distinction between head office / branch (chi nhánh) / business location
   (địa điểm kinh doanh) that the classification pipeline relies on.
2. **`administrative-reform/`** — the boundary-reform law chain behind `City_Id`/`District_Id`/`Ward_Id`
   discontinuities. See the `vietnam-admin-reform-timeline` memory for the full historical pattern
   (1976/1991/1997/2004/2008/2025) — these documents are the primary sources for the two reforms that
   actually appear in DKKD's own ID history (2008, 2025).

## enterprise-registration/

| File | Document | Status |
|---|---|---|
| `ldn59_2020_luat_doanh_nghiep.md` | Luật Doanh nghiệp số 59/2020/QH14 | **Current** (2021-01-01–) |
| `nd168_2025_dang_ky_doanh_nghiep.md` | Nghị định 168/2025/NĐ-CP | **Current** (2025-07-01–) |
| `nd01_2021_dang_ky_doanh_nghiep_SUPERSEDED.md` | Nghị định 01/2021/NĐ-CP | Superseded 2025-07-01 by ND168; historical reference for pre-2025-07-01 records |
| `tt01_2021_huong_dan_dang_ky_doanh_nghiep_SUPERSEDED.md` | Thông tư 01/2021/TT-BKHĐT | Superseded 2025-07-01; historical |
| `tt02_2023_sua_doi_tt01_2021_SUPERSEDED.md` | Thông tư 02/2023/TT-BKHĐT | Superseded 2025-07-01; historical |
| `tt68_2025_bieu_mau_dang_ky_doanh_nghiep.md` | Thông tư 68/2025/TT-BTC | **Current** (2025-07-01–). The implementing/form circular for Nghị định 168 — issued by Bộ Tài chính, not Bộ KH&ĐT, since MPI was merged into MOF in the 2025 restructuring; that ministry change is why it didn't surface under the old "TT-BKHĐT" naming pattern initially. 80 enterprise-registration forms (Phụ lục I) + 28 household-business forms (Phụ lục II), attached as separate files, not embedded in the circular's own text. |

## administrative-reform/

| File | Document | Status |
|---|---|---|
| `luat72_2025_to_chuc_chinh_quyen_dia_phuong.md` | Luật số 72/2025/QH15 (Tổ chức chính quyền địa phương) | **Current** (2025-06-16–). Điều 51 khoản 3 is the exact provision abolishing district-level government from 2025-07-01. |
| `nq15_2008_dieu_chinh_dia_gioi_ha_noi.md` | Nghị quyết 15/2008/QH12 | Historical — legal basis for the 2008-08-01 Hà Tây→Hà Nội `City_Id` discontinuity |
| `qd124_2004_ma_don_vi_hanh_chinh_HISTORICAL_REFERENCE.md` | Quyết định 124/2004/QĐ-TTg | GSO admin-unit code standard — **reference/contrast only**, not DKKD's own ID scheme (see CLAUDE.md), and superseded in substance by the 2025 reform |
| `nq202_2025_sap_xep_don_vi_hanh_chinh_cap_tinh.md` | Nghị quyết 202/2025/QH15 (63→34 province merger) | **OCR Completed / Verbatim Text** — Transcribed from the 5 scanned page JPGs in `nq202_2025_scanned_pages/`. This is the legal instrument behind the 2025 `City_Id` renumbering. |
| `vietnam-admin-reform-timeline.md` | Lịch sử Cải cách Địa giới Hành chính | **Reference Guide / System Memory** — Documents the historical boundary-reform waves (1976/1991/1997/2004/2008/2025) and their impact on DKKD `City_Id` and `District_Id` discontinuities. |


## Retrieval notes

- thuvienphapluat.vn blocks plain fetches (403) but works with a browser User-Agent + Referer header
  via `curl`; xaydungchinhsach.chinhphu.vn (a chinhphu.vn subsite) is fetch-friendly directly.
- All non-scanned documents above are full verbatim text extracted from the source HTML (not
  AI-summarized), retrieved 2026-07-06.
