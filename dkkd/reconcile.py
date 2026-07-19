import json
import re
import pandas as pd
from pathlib import Path
from difflib import SequenceMatcher
from dkkd.paths import checkpoint_json
from dkkd.utils import fold_ascii

# Synonym mappings
SYNONYMS = {
    r'\btang tre|tang tret|lau tret|tang 1|lau 1|tang 01\b': 'floor1',
    r'\bthap|block|bldg|toa\b': 'block',
    r'\bvinhomes grand park|vgp\b': 'phuoc thien',
    r'\bvinhomes central park\b': 'tan cang',
}

# Stop words to remove
STOP_WORDS = [
    r'\bphuong\b', r'\bquan\b', r'\bduong\b', r'\btp\b', r'\bthanh pho\b', 
    r'\bho chi minh\b', r'\bhcm\b', r'\bviet nam\b', r'\bvietnam\b', 
    r'\bp\b', r'\bq\b', r'\bdist\b', r'\bward\b', r'\bstreet\b'
]

def clean_address(addr: str) -> str:
    if not isinstance(addr, str):
        return ""
    addr = fold_ascii(addr)

    for pat, rep in SYNONYMS.items():
        addr = re.sub(pat, rep, addr)
    for stop in STOP_WORDS:
        addr = re.sub(stop, '', addr)
    addr = re.sub(r'[\s,\.\-]+', ' ', addr)
    return ' '.join(addr.split())

def extract_house_numbers(addr: str) -> set[str]:
    """Return all house numbers in addr, including both ends of a hyphenated
    range ('416-418 Nguyễn Văn Nghi' -> {'416', '418'}; '37 Bùi Viện' -> {'37'}).
    """
    if not isinstance(addr, str):
        return set()
    addr = fold_ascii(addr).replace(',', ' ').replace('.', ' ')

    tokens = addr.split()
    ignored_prefixes = {
        'block', 'toa', 'tang', 'lau', 'lo', 'phong', 'can', 'ho', 'landmark',
        's', 'l', 'gh', 'ap', 'kiosk', 'canho', 'tret',
        'phuong', 'p', 'quan', 'q', 'dist', 'district', 'ward', 'w'
    }

    for i, tok in enumerate(tokens):
        m = re.match(r'^(\d+)[a-z]?(?:-(\d+)[a-z]?)?(?:/\d+)?$', tok)
        if m:
            if i > 0:
                prev = tokens[i - 1]
                if prev in ignored_prefixes:
                    continue
            nums = {m.group(1)}
            if m.group(2):
                nums.add(m.group(2))
            return nums
    return set()

def extract_tower_code(addr: str) -> str | None:
    if not isinstance(addr, str):
        return None
    addr = fold_ascii(addr)

    # Match S2.03, S5.01, MP2, GH3, Landmark 1
    m = re.search(r'\b(s\d+\.?\d*|mp\d+|gh\d+|landmark\s*\d+|l\d+)\b', addr)
    if m:
        return m.group(1).replace(' ', '')
    return None

def run_reconciliation(brand_slug: str, crawled_csv_path: str, output_dir: Path, brands_dir: Path | None = None):
    crawled_df = pd.read_csv(crawled_csv_path)

    checkpoint_file = checkpoint_json(brand_slug, brands_dir)

    with open(checkpoint_file, "r", encoding="utf-8") as f:
        dkkd_data = json.load(f)
    dkkd_stores = [item[1] if isinstance(item, list) else item for item in dkkd_data]
    
    # Standardize DKKD structures — include ALL records (both Format A and B)
    dkkd_list = []
    for r in dkkd_stores:
        addr = r.get('Ho_Address', '')
        gdt = str(r.get('Enterprise_Gdt_Code') or '')
        dkkd_list.append({
            'record': r,
            'clean_addr': clean_address(addr),
            'tower': extract_tower_code(addr),
            'house_nos': extract_house_numbers(addr),
            'gdt': gdt,
            'enterprise_code': str(r.get('Enterprise_Code') or ''),
        })
        
    # Build lookup indices for tax code matching
    # Format B: Enterprise_Gdt_Code like "0313330856-045" → full code lookup
    gdt_code_index = {}
    # Format A: Enterprise_Gdt_Code like "00202" → 5-digit counter lookup
    gdt_counter_index = {}
    # Enterprise_Code: 10-digit parent MST lookup
    enterprise_code_index = {}
    for item in dkkd_list:
        r = item['record']
        gdt = item['gdt']
        ecode = item['enterprise_code']
        if gdt:
            gdt_code_index[gdt] = item
            # Also index bare counter for Format A (5-digit, no hyphen)
            if len(gdt) == 5 and gdt.isdigit():
                gdt_counter_index[gdt] = item
        if ecode:
            enterprise_code_index[ecode] = item
        
    # Check if receipt tax code column exists
    has_receipt_code = 'receipt_tax_code' in crawled_df.columns
    
    matches = {} # crawled_idx -> dkkd_id
    matched_dkkd = set()
    
    if has_receipt_code:
        # EXACT MATCH BY TAX CODE — supports all 3 formats from the design spec
        for idx, row in crawled_df.iterrows():
            code = str(row['receipt_tax_code']).strip().replace(' ', '')
            if not code or code == 'nan':
                continue
            
            matched_item = None
            
            # Parse the receipt tax code
            if '-' in code:
                # Hyphenated: could be "0313330856-045" (Format B) or "0309129418-00202" (Format A)
                parts = code.split('-')
                parent_mst = parts[0]
                suffix = parts[-1]
                
                # Try exact full-code match first (Format B branch)
                if code in gdt_code_index:
                    matched_item = gdt_code_index[code]
                # Try Format A: parent MST + 5-digit counter suffix
                elif len(suffix) == 5 and suffix in gdt_counter_index:
                    matched_item = gdt_counter_index[suffix]
                    
            elif len(code) == 13 and code.isdigit():
                # Continuous 13-digit: split as 10+3 → Format B branch
                branch_code = f"{code[:10]}-{code[10:]}"
                if branch_code in gdt_code_index:
                    matched_item = gdt_code_index[branch_code]
                    
            elif len(code) == 15 and code.isdigit():
                # Continuous 15-digit: split as 10+5 → Format A counter
                counter = code[10:]
                if counter in gdt_counter_index:
                    matched_item = gdt_counter_index[counter]
                    
            elif len(code) == 10 and code.isdigit():
                # 10-digit parent MST → parent fallback
                if code in enterprise_code_index:
                    matched_item = enterprise_code_index[code]
                    
            if matched_item:
                rid = matched_item['record']['Id']
                matches[idx] = rid
                matched_dkkd.add(rid)
    else:
        # FUZZY ADDRESS MATCHING WITH CONSTRAINTS
        all_pairs = []
        for idx, row in crawled_df.iterrows():
            c_addr = str(row.get('new_address') or '') + ' ' + str(row.get('old_address') or '')
            c_clean = clean_address(c_addr)
            c_tower = extract_tower_code(c_addr)
            c_houses = extract_house_numbers(c_addr)

            c_words = set(c_clean.split())

            for item in dkkd_list:
                r = item['record']
                # Blocker checks
                if c_tower and item['tower'] and c_tower != item['tower']:
                    continue
                # Only enforce house number check if no tower code is present in either address
                if not c_tower and not item['tower']:
                    if c_houses and item['house_nos']:
                        c_norm = {h.lstrip('0') or '0' for h in c_houses}
                        d_norm = {h.lstrip('0') or '0' for h in item['house_nos']}
                        if not (c_norm & d_norm):
                            continue
                    
                # Score
                d_words = set(item['clean_addr'].split())
                jaccard = len(c_words.intersection(d_words)) / len(c_words.union(d_words)) if c_words else 0
                ratio = SequenceMatcher(None, c_clean, item['clean_addr']).ratio()
                
                score = (0.4 * jaccard) + (0.6 * ratio)
                if c_tower and item['tower'] and c_tower == item['tower']:
                    score += 0.3
                if score > 0.45:
                    all_pairs.append((score, idx, r['Id']))
                    
        # Greedy selection
        all_pairs.sort(key=lambda x: x[0], reverse=True)
        for score, idx, rid in all_pairs:
            if idx not in matches and rid not in matched_dkkd:
                matches[idx] = rid
                matched_dkkd.add(rid)
                
    # Generate Output Mapping CSV
    mapped_rows = []
    co_locations = {}
    for idx, row in crawled_df.iterrows():
        rid = matches.get(idx)
        d_rec = next((r['record'] for r in dkkd_list if r['record']['Id'] == rid), None) if rid else None
        
        match_type = 'Parent_Fallback'
        if rid:
            match_type = 'Unique'
            if rid not in co_locations:
                co_locations[rid] = []
            co_locations[rid].append(idx)
            
        mapped_rows.append({
            'store_id': row.get('store_code') or row.get('store_id'),
            'store_name': row.get('store_name'),
            'physical_address': row.get('new_address') or row.get('old_address'),
            'receipt_tax_code': row.get('receipt_tax_code', ''),
            'dkkd_id': rid or '',
            'dkkd_registered_name': d_rec['Name'] if d_rec else '',
            'dkkd_registered_address': d_rec['Ho_Address'] if d_rec else '',
            'match_type': match_type
        })
        
    # Standardize match_type for co-locations
    for rid, indices in co_locations.items():
        if len(indices) > 1:
            for idx in indices:
                mapped_rows[idx]['match_type'] = 'Shared_Co-located'
                
    mapped_df = pd.DataFrame(mapped_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    mapped_df.to_csv(output_dir / f"{brand_slug}_store_mapping.csv", index=False, encoding="utf-8-sig")
    
    # Generate Report MD
    unique_count = sum(1 for m in mapped_rows if m['match_type'] == 'Unique')
    shared_count = sum(1 for m in mapped_rows if m['match_type'] == 'Shared_Co-located')
    fallback_count = sum(1 for m in mapped_rows if m['match_type'] == 'Parent_Fallback')

    # Recall: fraction of crawled storefronts that matched a DKKD record at all
    # (fallback matches are corporate-parent guesses, not a store-level match, so
    # they're excluded from the numerator).
    matched_count = unique_count + shared_count
    recall_pct = (100 * matched_count / len(crawled_df)) if len(crawled_df) else 0.0

    report_content = f"""# Reconciliation Report: {brand_slug.upper()}

## Summary Statistics
*   **Total physical storefronts visited/crawled:** {len(crawled_df)}
*   **Unique 1-to-1 matches in DKKD:** {unique_count}
*   **Co-located / Shared registered IDs:** {shared_count}
*   **Direct Corporate Parent fallbacks:** {fallback_count}
*   **Recall:** {matched_count}/{len(crawled_df)} = **{recall_pct:.1f}%** matched to a DKKD record{" — ⚠️ below the 90% design target; treat as a known matcher-coverage gap, not something to tune around" if recall_pct < 90 else ""}

## Multi-Store Shared Registered IDs
"""
    shared_ids = {m['dkkd_id'] for m in mapped_rows if m['match_type'] == 'Shared_Co-located'}
    if shared_ids:
        for rid in shared_ids:
            d_rec = next(r['record'] for r in dkkd_list if r['record']['Id'] == rid)
            report_content += f"\n### DKKD Registered ID: {rid} ({d_rec.get('Enterprise_Gdt_Code')})\n"
            report_content += f"*   **Registered Name:** {d_rec['Name']}\n"
            report_content += f"*   **Registered Address:** {d_rec['Ho_Address']}\n"
            report_content += "*   **Operating Physical Stores:**\n"
            for m in mapped_rows:
                if m['dkkd_id'] == rid:
                    report_content += f"    - Code {m['store_id']}: {m['store_name']} | Address: {m['physical_address']}\n"
    else:
        report_content += "\n*No multiple storefronts are sharing a single registered ID.*\n"
        
    with open(output_dir / f"{brand_slug}_reconciliation_report.md", "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"Reconciliation files written to {output_dir}")
