"""Command-line runner for the Jev Data Quality Gate project."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import pandas as pd
from jev_data_gate import analyse_rows, deterministic_action, live_jev_decision, offline_decision
from download_dataset import main as download_uci

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "sample_online_retail.csv"
UCI_FILE = ROOT / "data" / "raw" / "Online Retail.xlsx"

def load_source(source: str, rows: int) -> pd.DataFrame:
    if source == "sample":
        return pd.read_csv(SAMPLE, dtype={"InvoiceNo":"string", "StockCode":"string", "CustomerID":"string"})
    if source == "uci":
        if not UCI_FILE.exists():
            download_uci()
        # Strings are identifiers, not numeric measures; preserve invoice/stock codes.
        return pd.read_excel(UCI_FILE, nrows=(rows or None), dtype={"InvoiceNo":"string", "StockCode":"string", "CustomerID":"string"})
    raise ValueError(f"Unsupported source: {source}")

def json_default(value):
    if hasattr(value, "item"): return value.item()
    if hasattr(value, "isoformat"): return value.isoformat()
    return str(value)

def main() -> None:
    parser = argparse.ArgumentParser(description="Profile an Online Retail batch and route data-quality decisions.")
    parser.add_argument("--source", choices=["sample", "uci"], default="sample", help="sample fixture or download/read real UCI dataset")
    parser.add_argument("--rows", type=int, default=0, help="number of UCI rows to read; 0 means all; ignored for sample")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline", help="offline is clearly-labelled demo logic; live calls Jev")
    parser.add_argument("--outdir", default="outputs", help="directory for output CSV and JSON files")
    parser.add_argument("--model", default=None, help="pin Jev model version, defaults to JEV_MODEL env or jev-1.13.0")
    args = parser.parse_args()
    if args.rows < 0:
        parser.error("--rows must be zero (all UCI rows) or a positive integer")
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)

    df = load_source(args.source, args.rows)
    row_flags, profile = analyse_rows(df)
    profile["input_source"] = args.source
    profile["mode"] = args.mode
    if args.mode == "live":
        if not os.getenv("TYPESAFE_API_KEY"):
            raise SystemExit("TYPESAFE_API_KEY is missing. Set it in your shell before using --mode live.")
        jev = live_jev_decision(profile, model=args.model)
    else:
        jev = offline_decision(profile)
    gate = deterministic_action(profile, jev)

    # Keep row-level reasons human-readable and preserve original fields for audit.
    hard_bad = row_flags[row_flags["is_hard_invalid"]].copy()
    clean = row_flags[~row_flags["is_hard_invalid"]].copy()
    # JSON metadata plus decision, and row-level outputs suitable for a small ETL.
    payload = {"profile": profile, "jev_decision": jev, "gate": gate, "row_counts": {"input": int(len(df)), "clean_remainder": int(len(clean)), "quarantined": int(len(hard_bad))}}
    (outdir / "batch_report.json").write_text(json.dumps(payload, indent=2, default=json_default), encoding="utf-8")
    clean.to_csv(outdir / "silver_candidate.csv", index=False)
    hard_bad.to_csv(outdir / "quarantine.csv", index=False)
    pd.DataFrame([{"decision_source":jev.get("decision_source"),"model":jev.get("model"),"primary_issue":jev.get("primary_issue"),"issue_confidence":jev.get("issue_confidence"),"safe_to_promote_probability":jev.get("safe_to_promote_probability"),"severity_label":jev.get("severity_label"),"action":gate.get("action"),"input_rows":len(df),"quarantined_rows":len(hard_bad),"clean_remainder_rows":len(clean)}]).to_csv(outdir / "decision_summary.csv", index=False)

    print("\n=== JEV DATA QUALITY GATE ===")
    print(f"Source: {args.source}; mode: {args.mode}")
    print(f"Rows profiled: {len(df):,}")
    print(f"Hard-invalid rows: {profile['hard_invalid_rows']:,} ({profile['hard_invalid_pct']:.2f}%)")
    print(f"Missing CustomerID: {profile['missing_customer_id_rows']:,}; missing Description: {profile['missing_description_rows']:,}")
    print(f"Cancellation rows: {profile['cancellation_rows']:,}; exact duplicate repeat rows: {profile['exact_duplicate_repeat_rows']:,}")
    print(f"Decision source: {jev.get('decision_source')}; primary issue: {jev.get('primary_issue')}; severity: {jev.get('severity_label')}")
    if args.mode == "offline": print("NOTE: OFFLINE RULES ONLY; no Jev API was called and no model result is claimed.")
    print(f"Gate action: {gate['action']}")
    print(f"Outputs: {outdir.resolve()}")

if __name__ == "__main__":
    main()
