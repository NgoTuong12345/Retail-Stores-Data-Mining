"""CLI entrypoint for the DKKD multi-brand scraper.

Commands:
  dkkd run --brand <slug> --strategy <name> [--params k=v,k=v]
  dkkd loop --brand <slug>
  dkkd state --brand <slug>
  dkkd converged --brand <slug>
  dkkd export --brand <slug> [--format json|csv]
  dkkd brands
  dkkd strategies
  dkkd backtest --brand <slug>
  dkkd diff-snapshots --brand <slug> --since <git-rev>
  dkkd discover [--threshold <N>] [--dry-run]
  dkkd gold-report [--format csv|json]
  dkkd audit-stores --brand <slug> [--generate-only] [--batch-size N]
  dkkd pipeline [--staging-only]
"""
import argparse
import json
import sys
from pathlib import Path

from dkkd import config as cfg
from dkkd.engine import DkkdEngine
from dkkd.records import SweepState
from dkkd import state_report
from dkkd.convergence import converged
from dkkd.paths import brand_dir, state_json, DEFAULT_BRANDS_DIR

from dkkd.strategies import get as get_strategy, list_names


def parse_params(params_str: str) -> dict:
    """Parse 'k1=v1,k2=v2' into dict."""
    if not params_str:
        return {}
    result = {}
    for pair in params_str.split(','):
        if '=' in pair:
            k, v = pair.split('=', 1)
            result[k.strip()] = v.strip()
    return result


def cmd_run(args):
    """Run a single strategy phase."""
    brand_config = cfg.load(args.brand)
    strategy_fn = get_strategy(args.strategy)

    # Build current state from checkpoint
    from dkkd.transport import RequestsTransport
    transport = RequestsTransport()
    engine = DkkdEngine(brand_config, transport)
    engine.load_checkpoint()

    state = SweepState(store_map=engine.store_map, phase_history=_load_phase_history(args.brand))

    params = parse_params(args.params)
    probes = strategy_fn(brand_config, state, params)

    print(f'Strategy {args.strategy!r}: {len(probes)} probes')
    added = engine.sweep(probes, args.strategy)
    print(f'Added {added} new records (total: {len(engine.store_map)})')

    engine.save_checkpoint()

    # Update phase history
    state.phase_history.append({
        'strategy': args.strategy,
        'params': params,
        'probes': len(probes),
        'added': added,
        'total': len(engine.store_map),
    })

    # Write state report
    state.store_map = engine.store_map
    state_report.write(brand_config, state)


def cmd_loop(args):
    """Run the deterministic auto-loop."""
    from dkkd.loop import run_loop
    run_loop(args.brand, creative=args.creative)


def cmd_state(args):
    """Print current state report."""
    path = state_json(args.brand)
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            print(f.read())
    else:
        print(json.dumps({'error': f'No state found for brand {args.brand!r}'}, indent=2))


def cmd_converged(args):
    """Check convergence. Exit 0 if converged, 1 if not."""
    path = state_json(args.brand)
    if not path.exists():
        print('No state file found')
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    is_conv = data.get('convergence', {}).get('converged', False)
    reason = data.get('convergence', {}).get('rule', '')
    print(f'Converged: {is_conv} ({reason})')
    sys.exit(0 if is_conv else 1)


def cmd_export(args):
    """Export records to output directory."""
    brand_config = cfg.load(args.brand)
    from dkkd.transport import RequestsTransport
    engine = DkkdEngine(brand_config, RequestsTransport())
    loaded = engine.load_checkpoint()
    if loaded == 0:
        print('No records to export')
        return
    fmt = getattr(args, 'format', 'json') or 'json'
    path = engine.export(fmt)
    print(f'Exported {loaded} records to {path}')


def cmd_brands(args):
    """List available brands."""
    bd = DEFAULT_BRANDS_DIR
    if bd.exists():
        configs = sorted(bd.rglob('config.yaml'))
        for p in configs:
            print(p.parent.name)
    else:
        print('No brands directory found')


def cmd_strategies(args):
    """List available strategies."""
    for name in list_names():
        print(name)


def cmd_postprocess(args):
    """Run the post-scrape classification pipeline."""
    from dkkd.postprocess import run_pipeline
    skip_dates = getattr(args, 'skip_date_calibration', False)
    cap = getattr(args, 'cap', None)
    dpi_file = getattr(args, 'dpi_status_file', None)
    masothue_status = getattr(args, 'masothue_status', False)
    summary = run_pipeline(args.brand, skip_date_calibration=skip_dates, cap=cap,
                           dpi_status_file=dpi_file, masothue_status=masothue_status)
    print(f"\nPipeline complete: {summary['core_operating']} core operating stores")


def cmd_audit_tax(args):
    """Query GDT taxpayer portal for scraped MSTs and cache results."""
    import time
    import re
    import json
    import os
    import tempfile
    from pathlib import Path
    from dkkd.paths import checkpoint_json
    from dkkd.taxpayer import TaxpayerClient, load_status_cache, save_status_cache
    from dkkd.config import load as load_config
    
    config = load_config(args.brand)
    msts = set(config.seed_parent_msts or [])
    
    cp_path = checkpoint_json(args.brand)
    if cp_path.exists():
        with open(cp_path, 'r', encoding='utf-8') as f:
            pairs = json.load(f)
        records = [item[1] if isinstance(item, list) else item for item in pairs]
        
        # Extract distinct base 10-digit parent MSTs
        mst_pattern = re.compile(r'^\d{10}')
        for r in records:
            gdt = r.get('Enterprise_Gdt_Code') or ''
            m = mst_pattern.match(gdt)
            if m:
                msts.add(m.group(0))
            code = r.get('Enterprise_Code') or ''
            m = mst_pattern.match(code)
            if m:
                msts.add(m.group(0))
                
    # Filter out local registration codes starting with '00'
    msts = {m for m in msts if not m.startswith('00') and len(m) == 10}
    
    print(f"Found {len(msts)} distinct valid GDT tax codes to audit.")
    if not msts:
        print("No valid tax codes to audit. Exiting.")
        return
        
    cache = load_status_cache(args.brand)
    client = TaxpayerClient()
    
    # Filter list of MSTs to query
    to_query = sorted([m for m in msts if m not in cache or args.force])
    print(f"Remaining to query: {len(to_query)}")
    
    for i, mst in enumerate(to_query):
        print(f"\n[{i+1}/{len(to_query)}] Auditing MST: {mst}")
        
        # Captcha loop for this MST
        success = False
        attempts = 0
        while not success and attempts < 5:
            attempts += 1
            print("  Fetching captcha...")
            captcha = client.get_captcha()
            if not captcha or 'content' not in captcha or 'key' not in captcha:
                print("  Failed to fetch captcha. Retrying in 5s...")
                time.sleep(5)
                continue
                
            # Save captcha SVG to temporary scratch file
            scratch_dir = Path(tempfile.gettempdir()) / "dkkd_scratch"
            scratch_dir.mkdir(parents=True, exist_ok=True)
            captcha_path = scratch_dir / "captcha.svg"
            with open(captcha_path, "w", encoding="utf-8") as f:
                f.write(captcha['content'])
                
            # Attempt to open captcha automatically for the user
            print(f"  Captcha saved to: {captcha_path}")
            if os.name == 'nt':
                try:
                    os.startfile(captcha_path)
                except Exception:
                    pass
            
            cvalue = input(f"  Please open the captcha image and enter the code: ").strip()
            if not cvalue:
                print("  Empty captcha entered. Retrying...")
                continue
                
            res = client.query_taxpayer_status(mst, ckey=captcha['key'], cvalue=cvalue)
            
            if res and "error_type" in res:
                if res["error_type"] == "invalid_captcha":
                    print("  Invalid CAPTCHA code. Let's try again.")
                    continue
                elif res["error_type"] == "rate_limit":
                    print("  Rate limited by GDT. Sleeping for 15s before retry...")
                    time.sleep(15)
                    attempts -= 1 # Don't count rate limit as a failed captcha solve attempt
                    continue
                    
            if res:
                cache[mst] = res
                save_status_cache(args.brand, cache)
                print(f"  SUCCESS: {res['status']} ({res['name']})")
                success = True
            else:
                # If it's a 404 or other non-captcha error, GDT doesn't have this MST
                cache[mst] = {"status": "Not Found on GDT Portal", "name": "", "raw_data": None, "checked_at": time.asctime()}
                save_status_cache(args.brand, cache)
                print("  Result: Not Found on GDT Portal")
                success = True
                
            time.sleep(1.5) # Politeness delay
            
    print("\nAudit complete.")


def cmd_backtest(args):
    """Run the MSN back-test reconciliation."""
    from dkkd.backtest import run_backtest
    run_backtest(args.brand)


def cmd_diff_snapshots(args):
    """Diff a past checkpoint.json revision against the current on-disk one."""
    from dkkd.snapshot_diff import run_diff
    result = run_diff(args.brand, args.since)
    print(
        f"[{args.brand}] since {args.since}: "
        f"new={len(result['new_ids']['genuinely_new'])} "
        f"discovered={len(result['new_ids']['newly_discovered'])} "
        f"vanished={len(result['vanished_ids'])} "
        f"relocated={len(result['relocations'])} "
        f"status_changed={len(result['status_changes'])} "
        f"renamed={len(result['renamed'])}"
    )


def cmd_audit(args):
    """Run the legacy migration audit."""
    from dkkd.paths import checkpoint_json
    from dkkd.audit import generate_audit_report

    cp_path = checkpoint_json(args.brand)
    with open(cp_path, 'r', encoding='utf-8') as f:
        pairs = json.load(f)
    stores = [item[1] if isinstance(item, list) else item for item in pairs]

    report_path = generate_audit_report(stores, args.brand)
    print(f"Audit report generated: {report_path}")


def cmd_reconcile(args):
    """Run store reconciliation mapping."""
    from dkkd.reconcile import run_reconciliation
    from dkkd.paths import brand_dir
    crawled_path = Path(args.crawled)
    if not crawled_path.exists():
        print(f"Error: crawled store file not found: {crawled_path}")
        sys.exit(1)
    
    brand_path = brand_dir(args.brand)
    output_dir = brand_path / 'output'
    run_reconciliation(args.brand, crawled_path, output_dir)



def _load_phase_history(slug: str) -> list[dict]:
    """Load phase history from state.json if it exists."""
    path = state_json(slug)
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('phase_history', [])
    return []


def cmd_discover(args):
    """Run the gold chain discovery sweep."""
    from dkkd.sectors.gold.orchestrator import run_discovery
    summary = run_discovery(
        threshold=args.threshold,
        dry_run=args.dry_run,
    )
    print(f"\nDiscovery summary:")
    print(f"  Total records: {summary['total_records']}")
    print(f"  Parent MST clusters: {summary['total_clusters']}")
    print(f"  Known MSTs filtered: {summary['known_msts_filtered']}")
    print(f"  Candidate chains: {summary['candidates']}")
    if summary['candidate_details']:
        print(f"\n  Candidates:")
        for mst, detail in summary['candidate_details'].items():
            print(f"    {mst}: {detail['branch_count']} branches — {detail['sample_name']}")


def cmd_gold_report(args):
    """Generate consolidated gold sector report."""
    from dkkd.sectors.gold.report import generate_gold_report
    from dkkd.paths import DEFAULT_BRANDS_DIR
    fmt = getattr(args, 'format', 'csv') or 'csv'
    paths = generate_gold_report(brands_dir=DEFAULT_BRANDS_DIR, fmt=fmt)
    for p in paths:
        print(f"Generated: {p}")


def cmd_pipeline(args):
    """Build the dashboard's staging Parquet + serving DuckDB from all sources."""
    from dkkd import etl
    if args.staging_only:
        print(f"Building staging Parquet -> {etl.DEFAULT_STAGING_DIR}")
        etl.build_staging(verbose=True)
    else:
        print(f"Building dashboard pipeline -> {etl.DEFAULT_SERVING_DB_PATH}")
        etl.run_pipeline(verbose=True)
        print(f"\nDone. Query {etl.DEFAULT_SERVING_DB_PATH} directly with duckdb.")


def cmd_export_schema(args):
    """Export the standardized cross-brand output schema CSV."""
    from dkkd.schema_export import export_standard_schema
    out_path = export_standard_schema(args.brand)
    print(f"Standard schema exported → {out_path}")
    print(f"  Excel-safe copy (open this one, not the .csv, to avoid leading-zero "
          f"corruption) → {out_path.with_suffix('.xlsx')}")


def cmd_audit_stores(args):
    """Generate audit_sheet.json and optionally LLM-classify unclassified stores."""
    from dkkd.audit_stores import audit_brand, DEFAULT_BATCH
    batch_size = getattr(args, 'batch_size', DEFAULT_BATCH) or DEFAULT_BATCH
    generate_only = getattr(args, 'generate_only', False)

    print(f"Auditing stores for brand: {args.brand}")
    summary = audit_brand(
        args.brand,
        batch_size=batch_size,
        generate_only=generate_only,
        verbose=True,
    )
    print(f"\nSummary: keep={summary['keep']} reject={summary['reject']} "
          f"review={summary['review']} unclassified={summary['unclassified']}")
    if summary['reject']:
        print(f"  → Run 'dkkd postprocess --brand {args.brand}' to apply rejections.")



def main(argv=None):
    """Main CLI entrypoint."""
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
    parser = argparse.ArgumentParser(prog='dkkd', description='DKKD Multi-Brand Scraper')
    subparsers = parser.add_subparsers(dest='command')

    # run
    p_run = subparsers.add_parser('run', help='Run a single strategy phase')
    p_run.add_argument('--brand', required=True)
    p_run.add_argument('--strategy', required=True)
    p_run.add_argument('--params', default='')
    p_run.set_defaults(func=cmd_run)

    # loop
    p_loop = subparsers.add_parser('loop', help='Run deterministic auto-loop')
    p_loop.add_argument('--brand', required=True)
    p_loop.add_argument('--creative', action='store_true', default=False,
                        help='Run creative amplifier phases after deterministic loop')
    p_loop.set_defaults(func=cmd_loop)

    # state
    p_state = subparsers.add_parser('state', help='Print current state report')
    p_state.add_argument('--brand', required=True)
    p_state.set_defaults(func=cmd_state)

    # converged
    p_conv = subparsers.add_parser('converged', help='Check convergence (exit 0/1)')
    p_conv.add_argument('--brand', required=True)
    p_conv.set_defaults(func=cmd_converged)

    # export
    p_export = subparsers.add_parser('export', help='Export records')
    p_export.add_argument('--brand', required=True)
    p_export.add_argument('--format', default='json', choices=['json', 'csv'])
    p_export.set_defaults(func=cmd_export)

    # brands
    p_brands = subparsers.add_parser('brands', help='List available brands')
    p_brands.set_defaults(func=cmd_brands)

    # strategies
    p_strats = subparsers.add_parser('strategies', help='List available strategies')
    p_strats.set_defaults(func=cmd_strategies)

    # postprocess
    p_post = subparsers.add_parser('postprocess', help='Run post-scrape classification pipeline')
    p_post.add_argument('--brand', required=True)
    p_post.add_argument('--skip-date-calibration', action='store_true',
                        help='Skip masothue.com date lookups (use existing dates)')
    p_post.add_argument('--cap', type=int, help='Override active store cap')
    p_post.add_argument('--dpi-status-file', type=str, help='Path to DPI monthly dissolution Excel/CSV dump file')
    p_post.add_argument('--masothue-status', action='store_true',
                        help='Sweep masothue.com for per-store operating status (slow network pass)')
    p_post.set_defaults(func=cmd_postprocess)

    # audit
    p_audit = subparsers.add_parser('audit', help='Run legacy migration audit')
    p_audit.add_argument('--brand', required=True)
    p_audit.set_defaults(func=cmd_audit)

    # backtest
    p_backtest = subparsers.add_parser('backtest', help='Run MSN back-test reconciliation')
    p_backtest.add_argument('--brand', required=True)
    p_backtest.set_defaults(func=cmd_backtest)

    # diff-snapshots
    p_diff = subparsers.add_parser(
        'diff-snapshots',
        help='Diff a past checkpoint.json git revision against the current on-disk one',
    )
    p_diff.add_argument('--brand', required=True)
    p_diff.add_argument('--since', required=True,
                        help='Git rev of the older checkpoint.json snapshot (not defaulted — '
                             'not every commit touching checkpoint.json is a real month apart)')
    p_diff.set_defaults(func=cmd_diff_snapshots)

    # reconcile
    p_rec = subparsers.add_parser('reconcile', help='Run store reconciliation mapping')
    p_rec.add_argument('--brand', required=True)
    p_rec.add_argument('--crawled', required=True, help='Path to crawled store CSV')
    p_rec.set_defaults(func=cmd_reconcile)

    # export-schema
    p_export_schema = subparsers.add_parser(
        'export-schema', help='Export the standardized cross-brand output schema CSV')
    p_export_schema.add_argument('--brand', required=True)
    p_export_schema.set_defaults(func=cmd_export_schema)

    # audit-tax
    p_audit_tax = subparsers.add_parser('audit-tax', help='Audit scraped MST taxpayer status at GDT')
    p_audit_tax.add_argument('--brand', required=True)
    p_audit_tax.add_argument('--force', action='store_true', help='Force re-audit already-cached MSTs')
    p_audit_tax.set_defaults(func=cmd_audit_tax)


    # discover
    p_discover = subparsers.add_parser('discover', help='Run gold chain discovery sweep')
    p_discover.add_argument('--threshold', type=int, default=3,
                            help='Min branches to qualify as chain (default: 3)')
    p_discover.add_argument('--dry-run', action='store_true',
                            help='Show candidates without writing config files')
    p_discover.set_defaults(func=cmd_discover)

    # gold-report
    p_gold = subparsers.add_parser('gold-report', help='Generate consolidated gold sector report')
    p_gold.add_argument('--format', default='csv', choices=['csv', 'json'],
                        help='Output format (default: csv)')
    p_gold.set_defaults(func=cmd_gold_report)

    # pipeline
    p_pipe = subparsers.add_parser(
        'pipeline', help='Build dashboard staging Parquet + serving DuckDB from all sources')
    p_pipe.add_argument('--staging-only', action='store_true',
                        help='Only rebuild staging Parquet, skip the serving DB')
    p_pipe.set_defaults(func=cmd_pipeline)

    # audit-stores
    p_as = subparsers.add_parser(
        'audit-stores',
        help='LLM-audit store records for false positives (generates audit_sheet.json)',
    )
    p_as.add_argument('--brand', required=True, help='Brand slug')
    p_as.add_argument('--generate-only', action='store_true',
                      help='Only create/update audit_sheet.json; skip LLM classification')
    p_as.add_argument('--batch-size', type=int, default=None,
                      help='Records per LLM batch (default: 20)')
    p_as.set_defaults(func=cmd_audit_stores)

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
