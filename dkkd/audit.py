"""Legacy store migration audit and reconciliation reporting.

Compares closed legacy stores against active stores using address matching
to determine which were migrated (same address, new entity) vs permanently
closed (no active store at that location).

Also generates a markdown audit report with format distribution and
legacy migration statistics for analyst consumption.
"""
from pathlib import Path
from datetime import datetime

from dkkd.geo import normalize_address_for_matching
from dkkd.paths import output_dir


def audit_legacy_migration(stores: list[dict]) -> dict:
    """Audit legacy closed stores against active stores via address matching.

    For each store classified as '<Brand> (Legacy/Closed)', normalize its
    address and check if any active store has the same (or substring-matching)
    normalized address. If so, the legacy store was migrated to WinCommerce;
    otherwise, it was permanently closed.

    Args:
        stores: Full list of classified store records

    Returns:
        Summary dict with migration/closure counts and sample closed locations.
    """
    active = [r for r in stores if r.get('Core_Operating_Store') == 'Yes']
    legacy_closed = [
        r for r in stores
        if str(r.get('Store_Brand_Format', '')).endswith(' (Legacy/Closed)')
    ]

    if not legacy_closed:
        return {
            'total_legacy_audited': 0,
            'migrated': 0,
            'permanently_closed': 0,
            'migrated_pct': 0.0,
            'closed_pct': 0.0,
            'closed_samples': [],
        }

    # Build set of normalized active addresses
    active_addrs = set()
    for r in active:
        norm = normalize_address_for_matching(r.get('Ho_Address', ''))
        if norm:
            active_addrs.add(norm)

    migrated = 0
    permanently_closed = 0
    closed_samples = []

    for r in legacy_closed:
        addr_norm = normalize_address_for_matching(r.get('Ho_Address', ''))
        if not addr_norm:
            permanently_closed += 1
            continue

        # Exact match
        matched = addr_norm in active_addrs
        # Substring match for fuzzy spatial comparison
        if not matched:
            for active_addr in active_addrs:
                if len(addr_norm) > 10 and (
                    addr_norm in active_addr or active_addr in addr_norm
                ):
                    matched = True
                    break

        if matched:
            migrated += 1
        else:
            permanently_closed += 1
            if len(closed_samples) < 10:
                closed_samples.append({
                    'Name': r.get('Name', ''),
                    'Address': r.get('Ho_Address', ''),
                    'GDT': r.get('Enterprise_Gdt_Code', ''),
                })

    total = len(legacy_closed)
    return {
        'total_legacy_audited': total,
        'migrated': migrated,
        'permanently_closed': permanently_closed,
        'migrated_pct': round(migrated / total * 100, 1),
        'closed_pct': round(permanently_closed / total * 100, 1),
        'closed_samples': closed_samples,
    }


def generate_audit_report(stores: list[dict], slug: str,
                           brands_dir: Path | None = None) -> Path:
    """Generate a markdown reconciliation report.

    The report includes:
    - Total record counts (full, core, non-core)
    - Format distribution table
    - Legacy migration audit results
    - Sample permanently closed locations

    Args:
        stores: Full list of classified store records
        slug: Brand slug
        brands_dir: Override brands directory

    Returns:
        Path to the generated markdown report.
    """
    import pandas as pd

    audit = audit_legacy_migration(stores)
    df = pd.DataFrame(stores)

    core = df[df['Core_Operating_Store'] == 'Yes']
    non_core = df[df['Core_Operating_Store'] != 'Yes']

    report_lines = [
        f"# {slug.replace('-', ' ').title()} Store Classification Audit Report",
        f"",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Data Source:** DKKD.gov.vn (Cục Đăng ký Kinh doanh)",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Count |",
        f"|---|---:|",
        f"| Total DKKD Records | {len(stores)} |",
        f"| Core Operating Stores | {len(core)} |",
        f"| Non-Operating / Closed | {len(non_core)} |",
        f"",
    ]

    # Format distribution for core operating stores
    report_lines += [
        f"## Format Distribution (Core Operating)",
        f"",
        f"| Store Type (MSN Report) | Count |",
        f"|---|---:|",
    ]
    if 'Store_Type_MSN' in core.columns and len(core) > 0:
        for fmt, count in core['Store_Type_MSN'].value_counts().items():
            report_lines.append(f"| {fmt} | {count} |")
    report_lines.append("")

    # Non-operating breakdown
    report_lines += [
        f"## Non-Operating Breakdown",
        f"",
        f"| Category | Count |",
        f"|---|---:|",
    ]
    if 'Store_Type_MSN' in non_core.columns and len(non_core) > 0:
        for fmt, count in non_core['Store_Type_MSN'].value_counts().items():
            report_lines.append(f"| {fmt} | {count} |")
    report_lines.append("")

    # Legacy migration audit
    report_lines += [
        f"## Legacy Migration Audit",
        f"",
        f"Compares {audit['total_legacy_audited']} legacy closed stores "
        f"against {len(core)} active stores using address-based spatial matching.",
        f"",
        f"| Metric | Count | Share |",
        f"|---|---:|---:|",
        f"| Total Legacy Audited | {audit['total_legacy_audited']} | 100% |",
        f"| Migrated (active at same address) | {audit['migrated']} | {audit['migrated_pct']}% |",
        f"| Permanently Closed | {audit['permanently_closed']} | {audit['closed_pct']}% |",
        f"",
    ]

    if audit['closed_samples']:
        report_lines.append("### Sample Permanently Closed Locations")
        report_lines.append("")
        for i, s in enumerate(audit['closed_samples'][:5], 1):
            report_lines.append(f"{i}. **{s['Name']}** — {s['Address']}")
        report_lines.append("")

    report_lines += [
        f"---",
        f"",
        f"*Report generated by `dkkd audit --brand {slug}`*",
    ]

    out = output_dir(slug, brands_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / f'{slug}_audit_report.md'
    report_path.write_text('\n'.join(report_lines), encoding='utf-8')

    print(f"Audit report generated: {report_path}")
    return report_path
