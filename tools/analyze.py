"""
ANALYZE AGENT — "The Intelligence Engine"

Purpose: Extract patterns, relationships, metrics, and signals from clean data.

Rules:
- No storytelling
- No formatting for humans
- No recommendations unless explicitly requested
- Do NOT omit uncertainty or limitations

Input: Clean datasets, known limitations
Output: Metrics, statistical results, findings, handoff to Report Agent
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
import math

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
INPUT_FILE = TMP_DIR / "cleaned_data.json"
OUTPUT_FILE = TMP_DIR / "analytics_result.json"
REPORT_FILE = TMP_DIR / "analyze_report.json"
SCHEMA_VERSION = "1.0"


def _mean(values: list) -> float:
    """Calculate mean of a list."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std_dev(values: list) -> float:
    """Calculate standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


def _percentile(values: list, p: float) -> float:
    """Calculate percentile (0-100)."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def analyze() -> dict:
    """
    Run the Analyze Agent.
    Returns a structured report following the strict agent output format.
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize report structure
    report = {
        "agent": "ANALYZE",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "analytical_objectives": {
            "questions_answered": []
        },
        "methods_used": {
            "techniques": [],
            "models": [],
            "assumptions": []
        },
        "key_findings": [],
        "confidence_limitations": {
            "confidence_levels": {},
            "known_biases": []
        },
        "handoff": {
            "results_to_communicate": [],
            "visuals_recommended": []
        }
    }
    
    # === CHECK INPUT FILE ===
    if not INPUT_FILE.is_file():
        report["status"] = "error"
        report["confidence_limitations"]["known_biases"].append(
            "cleaned_data.json not found. Run Clean Agent first."
        )
        _save_report(report)
        return report
    
    # === LOAD CLEAN DATA ===
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        report["status"] = "error"
        report["confidence_limitations"]["known_biases"].append(f"Invalid JSON: {str(e)}")
        _save_report(report)
        return report
    
    records = data.get("records", [])
    
    if not records:
        report["status"] = "success"
        report["key_findings"].append({
            "finding": "No data to analyze",
            "supporting_metrics": {"record_count": 0}
        })
        report["confidence_limitations"]["known_biases"].append("Empty dataset")
        _save_report(report)
        _save_output({
            "schema_version": SCHEMA_VERSION,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "record_count": 0,
            "totals": {},
            "by_source": [],
            "summary": "No data available for analysis"
        })
        return report
    
    # === DEFINE ANALYTICAL OBJECTIVES ===
    report["analytical_objectives"]["questions_answered"] = [
        "What are the total visits, conversions, and revenue?",
        "What is the conversion rate overall and by source?",
        "Which sources contribute most to revenue?",
        "What is the time period covered?",
        "What are the statistical distributions of key metrics?"
    ]
    
    report["methods_used"]["techniques"] = [
        "Descriptive statistics (sum, mean, std dev, percentiles)",
        "Segmentation by source",
        "Conversion rate calculation",
        "Time range extraction",
        "Revenue per visit analysis"
    ]
    
    report["methods_used"]["assumptions"] = [
        "All records represent independent observations",
        "Timestamps are accurate and in ISO format",
        "Revenue is in consistent currency units"
    ]
    
    # === COMPUTE TOTALS ===
    totals = {"visits": 0.0, "conversions": 0.0, "revenue": 0.0}
    by_source = defaultdict(lambda: {"visits": 0.0, "conversions": 0.0, "revenue": 0.0, "records": 0})
    timestamps = []
    
    all_visits = []
    all_conversions = []
    all_revenue = []
    
    for r in records:
        v = float(r.get("visits", 0) or 0)
        c = float(r.get("conversions", 0) or 0)
        rev = float(r.get("revenue", 0) or 0)
        src = str(r.get("source", "") or "").strip() or "unknown"
        
        totals["visits"] += v
        totals["conversions"] += c
        totals["revenue"] += rev
        
        by_source[src]["visits"] += v
        by_source[src]["conversions"] += c
        by_source[src]["revenue"] += rev
        by_source[src]["records"] += 1
        
        all_visits.append(v)
        all_conversions.append(c)
        all_revenue.append(rev)
        
        ts = r.get("timestamp")
        if ts:
            timestamps.append(ts)
    
    # === TIME PERIOD ===
    period_start = min(timestamps) if timestamps else None
    period_end = max(timestamps) if timestamps else None
    
    # === CONVERSION RATES ===
    overall_cvr = (totals["conversions"] / totals["visits"] * 100) if totals["visits"] > 0 else 0
    revenue_per_visit = totals["revenue"] / totals["visits"] if totals["visits"] > 0 else 0
    
    # === BY SOURCE ANALYSIS ===
    by_source_list = []
    for src, metrics in sorted(by_source.items(), key=lambda x: x[1]["revenue"], reverse=True):
        cvr = (metrics["conversions"] / metrics["visits"] * 100) if metrics["visits"] > 0 else 0
        rpv = metrics["revenue"] / metrics["visits"] if metrics["visits"] > 0 else 0
        pct_revenue = (metrics["revenue"] / totals["revenue"] * 100) if totals["revenue"] > 0 else 0
        
        by_source_list.append({
            "source": src,
            "visits": metrics["visits"],
            "conversions": metrics["conversions"],
            "revenue": metrics["revenue"],
            "records": metrics["records"],
            "conversion_rate": round(cvr, 2),
            "revenue_per_visit": round(rpv, 2),
            "pct_of_total_revenue": round(pct_revenue, 2)
        })
    
    # === STATISTICAL DISTRIBUTIONS ===
    stats = {
        "visits": {
            "sum": totals["visits"],
            "mean": round(_mean(all_visits), 2),
            "std_dev": round(_std_dev(all_visits), 2),
            "min": min(all_visits) if all_visits else 0,
            "max": max(all_visits) if all_visits else 0,
            "p25": round(_percentile(all_visits, 25), 2),
            "p50": round(_percentile(all_visits, 50), 2),
            "p75": round(_percentile(all_visits, 75), 2)
        },
        "conversions": {
            "sum": totals["conversions"],
            "mean": round(_mean(all_conversions), 2),
            "std_dev": round(_std_dev(all_conversions), 2),
            "min": min(all_conversions) if all_conversions else 0,
            "max": max(all_conversions) if all_conversions else 0,
            "p25": round(_percentile(all_conversions, 25), 2),
            "p50": round(_percentile(all_conversions, 50), 2),
            "p75": round(_percentile(all_conversions, 75), 2)
        },
        "revenue": {
            "sum": totals["revenue"],
            "mean": round(_mean(all_revenue), 2),
            "std_dev": round(_std_dev(all_revenue), 2),
            "min": min(all_revenue) if all_revenue else 0,
            "max": max(all_revenue) if all_revenue else 0,
            "p25": round(_percentile(all_revenue, 25), 2),
            "p50": round(_percentile(all_revenue, 50), 2),
            "p75": round(_percentile(all_revenue, 75), 2)
        }
    }
    
    # === KEY FINDINGS ===
    report["key_findings"] = [
        {
            "finding": "Total Performance Metrics",
            "supporting_metrics": {
                "total_visits": totals["visits"],
                "total_conversions": totals["conversions"],
                "total_revenue": round(totals["revenue"], 2),
                "overall_conversion_rate": f"{round(overall_cvr, 2)}%",
                "revenue_per_visit": f"${round(revenue_per_visit, 2)}"
            }
        },
        {
            "finding": f"Data covers {len(records)} records across {len(by_source)} sources",
            "supporting_metrics": {
                "record_count": len(records),
                "source_count": len(by_source),
                "period_start": period_start,
                "period_end": period_end
            }
        },
        {
            "finding": f"Top revenue source: {by_source_list[0]['source'] if by_source_list else 'N/A'}",
            "supporting_metrics": by_source_list[0] if by_source_list else {}
        }
    ]
    
    # Find highest converting source
    if by_source_list:
        best_cvr = max(by_source_list, key=lambda x: x["conversion_rate"])
        report["key_findings"].append({
            "finding": f"Highest conversion rate: {best_cvr['source']} at {best_cvr['conversion_rate']}%",
            "supporting_metrics": best_cvr
        })
    
    # === CONFIDENCE & LIMITATIONS ===
    sample_size = len(records)
    if sample_size < 30:
        report["confidence_limitations"]["confidence_levels"]["statistical_significance"] = "Low (n < 30)"
        report["confidence_limitations"]["known_biases"].append(
            "Small sample size limits statistical confidence"
        )
    elif sample_size < 100:
        report["confidence_limitations"]["confidence_levels"]["statistical_significance"] = "Medium (30 ≤ n < 100)"
    else:
        report["confidence_limitations"]["confidence_levels"]["statistical_significance"] = "High (n ≥ 100)"
    
    report["confidence_limitations"]["confidence_levels"]["data_completeness"] = "High" if sample_size > 0 else "None"
    
    # === HANDOFF ===
    report["handoff"]["results_to_communicate"] = [
        "Total performance metrics (visits, conversions, revenue)",
        "Conversion rate analysis",
        "Source-level breakdown with rankings",
        "Statistical distributions"
    ]
    
    report["handoff"]["visuals_recommended"] = [
        "Bar chart: Revenue by source",
        "Bar chart: Conversion rate by source",
        "Table: Source performance comparison",
        "Summary metrics cards"
    ]
    
    # === BUILD OUTPUT ===
    summary = f"Total visits: {totals['visits']:.0f}, conversions: {totals['conversions']:.0f}, revenue: ${totals['revenue']:.2f}. Overall CVR: {overall_cvr:.2f}%"
    
    output = {
        "schema_version": SCHEMA_VERSION,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "computed_by": "ANALYZE_AGENT",
        "period_start": period_start,
        "period_end": period_end,
        "record_count": len(records),
        "source_count": len(by_source),
        "totals": totals,
        "rates": {
            "conversion_rate": round(overall_cvr, 2),
            "revenue_per_visit": round(revenue_per_visit, 2)
        },
        "statistics": stats,
        "by_source": by_source_list,
        "summary": summary
    }
    
    _save_output(output)
    
    # === FINALIZE ===
    report["status"] = "success"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_report(report)
    
    return report


def _save_report(report: dict):
    """Save the structured report to file."""
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def _save_output(output: dict):
    """Save analytics output to file."""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)


def get_exit_code(report: dict) -> int:
    """Convert report status to exit code."""
    return 0 if report.get("status") == "success" else 1


if __name__ == "__main__":
    report = analyze()
    print(json.dumps(report, indent=2))
    sys.exit(get_exit_code(report))
