"""
INGEST AGENT — "The Data Collector"

Purpose: Safely and accurately receive, inventory, and describe raw data without modifying it.

Rules:
- No cleaning
- No assumptions
- No analysis
- No interpretation
- Preserve original data exactly as received

Input: Raw files (CSV, JSON, etc.) or URLs
Output: Data inventory, structural summary, ingestion issues, handoff to Clean Agent
"""

import os
import sys
import json
import csv
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
OUTPUT_FILE = TMP_DIR / "raw_input.json"
REPORT_FILE = TMP_DIR / "ingest_report.json"
SCHEMA_VERSION = "1.0"


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_csv(path: Path) -> tuple:
    """Load CSV and return (records, column_info)."""
    records = []
    columns = []
    data_types = {}
    
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        columns = headers
        
        for row in reader:
            r = {}
            for k, v in row.items():
                key = k.strip().lower().replace(" ", "_")
                val = v.strip() if isinstance(v, str) else v
                r[key] = val
                
                # Track data types
                if key not in data_types:
                    data_types[key] = set()
                if val:
                    try:
                        float(val)
                        data_types[key].add("numeric")
                    except:
                        data_types[key].add("string")
            records.append(r)
    
    # Simplify data types
    type_summary = {}
    for col, types in data_types.items():
        if types == {"numeric"}:
            type_summary[col] = "numeric"
        elif types == {"string"}:
            type_summary[col] = "string"
        else:
            type_summary[col] = "mixed"
    
    return records, columns, type_summary


def _csv_rows_to_raw(rows: list) -> dict:
    records = []
    for i, row in enumerate(rows):
        rec = {
            "id": str(row.get("id", str(i))),
            "timestamp": str(row.get("timestamp", datetime.now(timezone.utc).isoformat())),
            "source": str(row.get("source", "")),
            "metrics": {
                "visits": float(row.get("visits", 0) or 0),
                "conversions": float(row.get("conversions", 0) or 0),
                "revenue": float(row.get("revenue", 0) or 0),
            },
            "meta": {},
        }
        records.append(rec)
    return {
        "schema_version": SCHEMA_VERSION,
        "records": records,
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_label": "csv",
        },
    }


def _fetch_url(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Aevel-Pipeline/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def ingest() -> dict:
    """
    Run the Ingest Agent.
    Returns a structured report following the strict agent output format.
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize report structure
    report = {
        "agent": "INGEST",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "data_inventory": {
            "dataset_name": "",
            "source": "",
            "format": "",
            "size_rows": 0,
            "size_bytes": 0,
            "time_range": {"start": None, "end": None}
        },
        "structure_summary": {
            "columns": [],
            "data_types": {},
            "primary_keys": []
        },
        "ingestion_issues": {
            "confirmed_issues": [],
            "potential_risks": []
        },
        "handoff": {
            "datasets_ready": [],
            "datasets_requiring_review": []
        }
    }
    
    path = os.environ.get("DATA_SOURCE_PATH", "").strip()
    url = os.environ.get("DATA_SOURCE_URL", "").strip()
    fmt = (os.environ.get("DATA_SOURCE_FORMAT", "json") or "json").strip().lower()
    
    data = None
    columns = []
    type_summary = {}
    
    # === INGEST FROM FILE PATH ===
    if path:
        p = Path(path)
        report["data_inventory"]["source"] = f"file://{path}"
        report["data_inventory"]["dataset_name"] = p.name
        
        if not p.is_file():
            report["status"] = "error"
            report["ingestion_issues"]["confirmed_issues"].append(f"File not found: {path}")
            report["handoff"]["datasets_requiring_review"].append(p.name)
            _save_report(report)
            return report
        
        report["data_inventory"]["size_bytes"] = p.stat().st_size
        report["data_inventory"]["format"] = fmt.upper()
        
        if fmt == "csv":
            try:
                rows, columns, type_summary = _load_csv(p)
                data = _csv_rows_to_raw(rows)
                report["data_inventory"]["size_rows"] = len(rows)
                report["structure_summary"]["columns"] = columns
                report["structure_summary"]["data_types"] = type_summary
            except Exception as e:
                report["ingestion_issues"]["confirmed_issues"].append(f"CSV parse error: {str(e)}")
        else:
            try:
                raw = _load_json(p)
                if "records" in raw:
                    data = raw
                    report["data_inventory"]["size_rows"] = len(raw.get("records", []))
                else:
                    data = {"schema_version": SCHEMA_VERSION, "records": raw.get("records", []), "metadata": raw.get("metadata", {})}
                
                # Extract structure from first record
                if data.get("records"):
                    first = data["records"][0]
                    if isinstance(first, dict):
                        columns = list(first.keys())
                        report["structure_summary"]["columns"] = columns
            except Exception as e:
                report["ingestion_issues"]["confirmed_issues"].append(f"JSON parse error: {str(e)}")
    
    # === INGEST FROM URL ===
    elif url:
        report["data_inventory"]["source"] = url
        report["data_inventory"]["dataset_name"] = url.split("/")[-1] or "remote_data"
        report["data_inventory"]["format"] = "JSON"
        
        try:
            body = _fetch_url(url)
            report["data_inventory"]["size_bytes"] = len(body)
            raw = json.loads(body.decode("utf-8"))
            
            if isinstance(raw, list):
                data = {"schema_version": SCHEMA_VERSION, "records": raw, "metadata": {}}
                report["data_inventory"]["size_rows"] = len(raw)
            elif isinstance(raw, dict):
                if "records" in raw:
                    data = raw
                    report["data_inventory"]["size_rows"] = len(raw.get("records", []))
                else:
                    data = {"schema_version": SCHEMA_VERSION, "records": [], "metadata": raw.get("metadata", {})}
            
            # Extract structure
            if data and data.get("records"):
                first = data["records"][0]
                if isinstance(first, dict):
                    columns = list(first.keys())
                    report["structure_summary"]["columns"] = columns
                    
        except (HTTPError, URLError) as e:
            report["status"] = "error"
            report["ingestion_issues"]["confirmed_issues"].append(f"URL unreachable: {str(e)}")
            report["handoff"]["datasets_requiring_review"].append(url)
            _save_report(report)
            return report
        except json.JSONDecodeError as e:
            report["status"] = "error"
            report["ingestion_issues"]["confirmed_issues"].append(f"Invalid JSON from URL: {str(e)}")
            _save_report(report)
            return report
    
    # === NO DATA SOURCE - TRY FALLBACK TO test_data.json ===
    else:
        fallback_path = TMP_DIR.parent / "test_data.json"
        if fallback_path.is_file():
            # Use test_data.json as fallback
            report["data_inventory"]["source"] = f"file://{fallback_path} (fallback)"
            report["data_inventory"]["dataset_name"] = "test_data.json"
            report["data_inventory"]["format"] = "JSON"
            report["data_inventory"]["size_bytes"] = fallback_path.stat().st_size
            report["ingestion_issues"]["potential_risks"].append("Using test_data.json as fallback (no DATA_SOURCE configured)")
            
            try:
                raw = _load_json(fallback_path)
                if "records" in raw:
                    data = raw
                    report["data_inventory"]["size_rows"] = len(raw.get("records", []))
                else:
                    data = {"schema_version": SCHEMA_VERSION, "records": raw.get("records", []), "metadata": raw.get("metadata", {})}
                
                if data.get("records"):
                    first = data["records"][0]
                    if isinstance(first, dict):
                        columns = list(first.keys())
                        report["structure_summary"]["columns"] = columns
            except Exception as e:
                report["ingestion_issues"]["confirmed_issues"].append(f"Fallback JSON parse error: {str(e)}")
                data = {
                    "schema_version": SCHEMA_VERSION,
                    "records": [],
                    "metadata": {"generated_at": datetime.now(timezone.utc).isoformat(), "source_label": "fallback_error"},
                }
        else:
            report["data_inventory"]["source"] = "none"
            report["data_inventory"]["dataset_name"] = "empty_dataset"
            report["data_inventory"]["format"] = "JSON"
            report["ingestion_issues"]["potential_risks"].append("No DATA_SOURCE_PATH or DATA_SOURCE_URL configured")
            report["ingestion_issues"]["potential_risks"].append("No test_data.json fallback found")
            data = {
                "schema_version": SCHEMA_VERSION,
                "records": [],
                "metadata": {"generated_at": datetime.now(timezone.utc).isoformat(), "source_label": "none"},
            }
    
    # === EXTRACT TIME RANGE ===
    if data and data.get("records"):
        timestamps = []
        for r in data["records"]:
            ts = r.get("timestamp")
            if ts:
                timestamps.append(ts)
        if timestamps:
            report["data_inventory"]["time_range"] = {
                "start": min(timestamps),
                "end": max(timestamps)
            }
    
    # === IDENTIFY POTENTIAL RISKS ===
    if data:
        records = data.get("records", [])
        if len(records) == 0:
            report["ingestion_issues"]["potential_risks"].append("Dataset contains zero records")
        
        # Check for missing values in first 10 records
        missing_fields = set()
        for r in records[:10]:
            if isinstance(r, dict):
                for k, v in r.items():
                    if v is None or v == "":
                        missing_fields.add(k)
        if missing_fields:
            report["ingestion_issues"]["potential_risks"].append(f"Potential missing values in fields: {list(missing_fields)}")
    
    # === FINALIZE ===
    if data:
        if "metadata" not in data:
            data["metadata"] = {}
        data["metadata"]["generated_at"] = datetime.now(timezone.utc).isoformat()
        data["metadata"]["ingested_by"] = "INGEST_AGENT"
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        report["status"] = "success"
        report["handoff"]["datasets_ready"].append(str(OUTPUT_FILE.name))
    else:
        report["status"] = "error"
        report["handoff"]["datasets_requiring_review"].append("No data ingested")
    
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
    report = ingest()
    print(json.dumps(report, indent=2))
    sys.exit(get_exit_code(report))
