"""
CLEAN AGENT — "The Data Sanitizer"

Purpose: Transform raw data into analysis-ready data while preserving meaning.

Rules:
- No business interpretation
- No insights
- No conclusions
- All assumptions must be logged
- Do NOT silently drop data

Input: Ingest Agent output, raw datasets
Output: Cleaned datasets, cleaning log, assumptions made, handoff to Analyze Agent
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
INPUT_FILE = TMP_DIR / "raw_input.json"
OUTPUT_FILE = TMP_DIR / "cleaned_data.json"
REPORT_FILE = TMP_DIR / "clean_report.json"
SCHEMA_VERSION = "1.0"


def _float(val, default=0.0):
    """Safe float conversion."""
    try:
        return float(val) if val is not None and val != "" else default
    except (TypeError, ValueError):
        return default


def _is_valid_record(r: dict) -> tuple:
    """Check if record is valid, return (is_valid, issues)."""
    issues = []
    if not isinstance(r, dict):
        return False, ["Record is not a dictionary"]
    return True, issues


def clean() -> dict:
    """
    Run the Clean Agent.
    Returns a structured report following the strict agent output format.
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize report structure
    report = {
        "agent": "CLEAN",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cleaning_summary": {
            "total_rows_before": 0,
            "total_rows_after": 0,
            "fields_modified": []
        },
        "cleaning_actions": {
            "missing_data_handling": [],
            "duplicates_handling": [],
            "format_standardization": [],
            "validation_rules_applied": []
        },
        "assumptions_decisions": {
            "assumptions_made": [],
            "data_removed": []
        },
        "clean_datasets": {
            "names": [],
            "locations": []
        },
        "handoff": {
            "analysis_ready_datasets": [],
            "known_limitations": []
        }
    }
    
    # === CHECK INPUT FILE ===
    if not INPUT_FILE.is_file():
        report["status"] = "error"
        report["handoff"]["known_limitations"].append("raw_input.json not found. Run Ingest Agent first.")
        _save_report(report)
        return report
    
    # === LOAD RAW DATA ===
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        report["status"] = "error"
        report["handoff"]["known_limitations"].append(f"Invalid JSON in raw_input.json: {str(e)}")
        _save_report(report)
        return report
    
    records_in = raw.get("records", [])
    report["cleaning_summary"]["total_rows_before"] = len(records_in)
    
    # === CLEANING PROCESS ===
    records_out = []
    validation_errors = 0
    missing_values_count = 0
    duplicates_removed = 0
    seen_ids = set()
    
    for i, r in enumerate(records_in):
        # Validate record structure
        is_valid, issues = _is_valid_record(r)
        if not is_valid:
            validation_errors += 1
            report["assumptions_decisions"]["data_removed"].append({
                "row": i,
                "reason": issues[0] if issues else "Invalid record structure"
            })
            continue
        
        # Extract and normalize fields
        record_id = str(r.get("id", str(i)))
        
        # Handle duplicates
        if record_id in seen_ids:
            duplicates_removed += 1
            report["assumptions_decisions"]["data_removed"].append({
                "row": i,
                "reason": f"Duplicate ID: {record_id}"
            })
            continue
        seen_ids.add(record_id)
        
        # Normalize timestamp
        timestamp = r.get("timestamp")
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()
            missing_values_count += 1
        
        # Normalize source
        source = str(r.get("source", "")).strip()
        if not source:
            source = "unknown"
            missing_values_count += 1
        
        # Extract and validate metrics
        metrics = r.get("metrics") if isinstance(r.get("metrics"), dict) else {}
        
        visits = _float(metrics.get("visits"), 0)
        conversions = _float(metrics.get("conversions"), 0)
        revenue = _float(metrics.get("revenue"), 0)
        
        # Validate numeric ranges (flag but don't remove)
        if visits < 0:
            report["cleaning_actions"]["validation_rules_applied"].append(
                f"Row {i}: Negative visits ({visits}) set to 0"
            )
            visits = 0
        if conversions < 0:
            report["cleaning_actions"]["validation_rules_applied"].append(
                f"Row {i}: Negative conversions ({conversions}) set to 0"
            )
            conversions = 0
        if revenue < 0:
            report["cleaning_actions"]["validation_rules_applied"].append(
                f"Row {i}: Negative revenue ({revenue}) set to 0"
            )
            revenue = 0
        
        # Validate conversions <= visits
        if conversions > visits and visits > 0:
            report["handoff"]["known_limitations"].append(
                f"Row {i}: Conversions ({conversions}) exceeds visits ({visits}) - data anomaly"
            )
        
        # Build cleaned record
        rec = {
            "id": record_id,
            "timestamp": str(timestamp),
            "source": source.lower(),  # Standardize to lowercase
            "visits": visits,
            "conversions": conversions,
            "revenue": revenue,
        }
        records_out.append(rec)
    
    # === LOG CLEANING ACTIONS ===
    if missing_values_count > 0:
        report["cleaning_actions"]["missing_data_handling"].append(
            f"Imputed {missing_values_count} missing values with defaults"
        )
        report["assumptions_decisions"]["assumptions_made"].append(
            "Missing timestamps set to current time"
        )
        report["assumptions_decisions"]["assumptions_made"].append(
            "Missing source values set to 'unknown'"
        )
    
    if duplicates_removed > 0:
        report["cleaning_actions"]["duplicates_handling"].append(
            f"Removed {duplicates_removed} duplicate records (by ID)"
        )
    
    if validation_errors > 0:
        report["cleaning_actions"]["validation_rules_applied"].append(
            f"Rejected {validation_errors} invalid record structures"
        )
    
    # Standard format actions
    report["cleaning_actions"]["format_standardization"] = [
        "Flattened nested metrics object to top-level fields",
        "Standardized source values to lowercase",
        "Converted all numeric fields to float type",
        "Ensured all IDs are string type"
    ]
    
    report["cleaning_summary"]["fields_modified"] = [
        "metrics.visits → visits (flattened)",
        "metrics.conversions → conversions (flattened)",
        "metrics.revenue → revenue (flattened)",
        "source (lowercased)"
    ]
    
    # === BUILD OUTPUT ===
    data = {
        "schema_version": SCHEMA_VERSION,
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
        "cleaned_by": "CLEAN_AGENT",
        "record_count": len(records_out),
        "records": records_out,
        "cleaning_metadata": {
            "rows_before": report["cleaning_summary"]["total_rows_before"],
            "rows_after": len(records_out),
            "validation_errors": validation_errors,
            "duplicates_removed": duplicates_removed,
            "missing_values_imputed": missing_values_count
        }
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    # === FINALIZE REPORT ===
    report["cleaning_summary"]["total_rows_after"] = len(records_out)
    report["clean_datasets"]["names"].append("cleaned_data.json")
    report["clean_datasets"]["locations"].append(str(OUTPUT_FILE))
    report["handoff"]["analysis_ready_datasets"].append("cleaned_data.json")
    
    if len(records_out) == 0:
        report["handoff"]["known_limitations"].append("No valid records after cleaning")
    
    report["status"] = "success"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_report(report)
    
    return report


def _save_report(report: dict):
    """Save the structured report to file."""
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def get_exit_code(report: dict) -> int:
    """Convert report status to exit code."""
    return 0 if report.get("status") == "success" else 1


if __name__ == "__main__":
    report = clean()
    print(json.dumps(report, indent=2))
    sys.exit(get_exit_code(report))
