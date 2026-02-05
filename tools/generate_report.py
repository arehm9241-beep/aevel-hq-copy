"""
REPORT AGENT — "The Story Architect"

Purpose: Convert analytical outputs into clear, structured, human-readable narratives.

Rules:
- No new analysis
- No data manipulation
- No exaggeration
- Do NOT alter metrics
- Do NOT introduce new conclusions
- Do NOT hide uncertainty

Input: Analytical results, metrics, charts suggestions
Output: Written report, executive summary, visual guidance, handoff to Deliver Agent
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
INPUT_FILE = TMP_DIR / "analytics_result.json"
OUTPUT_FILE = TMP_DIR / "report_output.json"
REPORT_FILE = TMP_DIR / "report_agent_report.json"
SCHEMA_VERSION = "1.0"


def _format_number(n: float, prefix: str = "", suffix: str = "") -> str:
    """Format number with optional prefix/suffix."""
    if n >= 1_000_000:
        return f"{prefix}{n/1_000_000:.1f}M{suffix}"
    elif n >= 1_000:
        return f"{prefix}{n/1_000:.1f}K{suffix}"
    else:
        return f"{prefix}{n:.0f}{suffix}"


def _format_currency(n: float) -> str:
    """Format as currency."""
    if n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    elif n >= 1_000:
        return f"${n/1_000:.2f}K"
    else:
        return f"${n:.2f}"


def generate_report(title: str = "", period: str = "") -> dict:
    """
    Run the Report Agent.
    Returns a structured report following the strict agent output format.
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize report structure
    report = {
        "agent": "REPORT",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": "",
        "data_overview": {},
        "key_insights": [],
        "risks_limitations": [],
        "recommended_visuals": [],
        "handoff": {
            "final_assets": [],
            "audience_type": "business stakeholders"
        }
    }
    
    # === CHECK INPUT FILE ===
    if not INPUT_FILE.is_file():
        report["status"] = "error"
        report["risks_limitations"].append("analytics_result.json not found. Run Analyze Agent first.")
        _save_report(report)
        return report
    
    # === LOAD ANALYTICS DATA ===
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        report["status"] = "error"
        report["risks_limitations"].append(f"Invalid JSON: {str(e)}")
        _save_report(report)
        return report
    
    totals = data.get("totals", {})
    by_source = data.get("by_source", [])
    rates = data.get("rates", {})
    statistics = data.get("statistics", {})
    period_start = data.get("period_start", "")
    period_end = data.get("period_end", "")
    record_count = data.get("record_count", 0)
    source_count = data.get("source_count", 0)
    
    # === DETERMINE TITLE AND PERIOD ===
    if not title:
        title = "Analytics Performance Report"
    if not period:
        if period_start and period_end:
            period = f"{period_start[:10]} to {period_end[:10]}"
        else:
            period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # === DATA OVERVIEW ===
    report["data_overview"] = {
        "report_title": title,
        "period_covered": period,
        "records_analyzed": record_count,
        "sources_included": source_count,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # === EXECUTIVE SUMMARY ===
    total_visits = totals.get("visits", 0)
    total_conversions = totals.get("conversions", 0)
    total_revenue = totals.get("revenue", 0)
    cvr = rates.get("conversion_rate", 0)
    rpv = rates.get("revenue_per_visit", 0)
    
    top_source = by_source[0] if by_source else None
    
    exec_lines = [
        f"This report analyzes {_format_number(record_count)} records across {source_count} traffic sources for the period {period}.",
        "",
        f"**Total Performance:**",
        f"- Visits: {_format_number(total_visits)}",
        f"- Conversions: {_format_number(total_conversions)}",
        f"- Revenue: {_format_currency(total_revenue)}",
        f"- Conversion Rate: {cvr:.2f}%",
        f"- Revenue per Visit: ${rpv:.2f}",
    ]
    
    if top_source:
        exec_lines.extend([
            "",
            f"**Top Performing Source:** {top_source['source'].title()}",
            f"- Contributed {top_source.get('pct_of_total_revenue', 0):.1f}% of total revenue",
            f"- Conversion rate of {top_source.get('conversion_rate', 0):.2f}%"
        ])
    
    report["executive_summary"] = "\n".join(exec_lines)
    
    # === KEY INSIGHTS ===
    # Insight 1: Overall Performance
    report["key_insights"].append({
        "insight": "Overall Performance Summary",
        "supporting_evidence": {
            "total_visits": total_visits,
            "total_conversions": total_conversions,
            "total_revenue": total_revenue,
            "conversion_rate": f"{cvr:.2f}%"
        },
        "narrative": f"The analyzed period generated {_format_currency(total_revenue)} in revenue from {_format_number(total_visits)} visits, achieving a {cvr:.2f}% conversion rate."
    })
    
    # Insight 2: Source Performance
    if by_source:
        top_3 = by_source[:3]
        report["key_insights"].append({
            "insight": "Top Revenue Sources",
            "supporting_evidence": {
                "top_sources": [{"name": s["source"], "revenue": s["revenue"], "pct": s.get("pct_of_total_revenue", 0)} for s in top_3]
            },
            "narrative": f"The top {len(top_3)} sources ({', '.join(s['source'].title() for s in top_3)}) account for {sum(s.get('pct_of_total_revenue', 0) for s in top_3):.1f}% of total revenue."
        })
        
        # Find best converting source
        best_cvr_source = max(by_source, key=lambda x: x.get("conversion_rate", 0))
        report["key_insights"].append({
            "insight": "Conversion Rate Leader",
            "supporting_evidence": {
                "source": best_cvr_source["source"],
                "conversion_rate": best_cvr_source.get("conversion_rate", 0),
                "visits": best_cvr_source.get("visits", 0)
            },
            "narrative": f"{best_cvr_source['source'].title()} leads in conversion rate at {best_cvr_source.get('conversion_rate', 0):.2f}%, indicating high-quality traffic from this source."
        })
    
    # Insight 3: Statistical Distribution (if available)
    if statistics:
        visit_stats = statistics.get("visits", {})
        if visit_stats:
            report["key_insights"].append({
                "insight": "Traffic Distribution",
                "supporting_evidence": {
                    "mean_visits": visit_stats.get("mean", 0),
                    "median_visits": visit_stats.get("p50", 0),
                    "std_dev": visit_stats.get("std_dev", 0)
                },
                "narrative": f"Average visits per record: {visit_stats.get('mean', 0):.0f} (median: {visit_stats.get('p50', 0):.0f}). Standard deviation of {visit_stats.get('std_dev', 0):.0f} indicates {'high' if visit_stats.get('std_dev', 0) > visit_stats.get('mean', 1) else 'moderate'} variability."
            })
    
    # === RISKS & LIMITATIONS ===
    report["risks_limitations"] = []
    
    if record_count < 30:
        report["risks_limitations"].append(
            f"Small sample size ({record_count} records) limits statistical confidence. Findings should be validated with additional data."
        )
    
    if source_count == 1:
        report["risks_limitations"].append(
            "Data from single source only. Cross-source comparisons not possible."
        )
    
    if total_revenue == 0:
        report["risks_limitations"].append(
            "No revenue recorded in dataset. Revenue-based insights unavailable."
        )
    
    if not report["risks_limitations"]:
        report["risks_limitations"].append(
            "No significant data quality issues identified. Standard analytical assumptions apply."
        )
    
    # === RECOMMENDED VISUALS ===
    report["recommended_visuals"] = [
        {
            "type": "metrics_cards",
            "description": "Summary cards showing total visits, conversions, revenue, and conversion rate",
            "priority": "high"
        },
        {
            "type": "bar_chart",
            "description": "Revenue by source (horizontal bar chart, sorted descending)",
            "priority": "high"
        },
        {
            "type": "bar_chart",
            "description": "Conversion rate by source",
            "priority": "medium"
        },
        {
            "type": "table",
            "description": "Full source breakdown with all metrics",
            "priority": "medium"
        }
    ]
    
    # === BUILD OUTPUT PAYLOAD ===
    output = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "REPORT_AGENT",
        "title": title,
        "period": period,
        "executive_summary": report["executive_summary"],
        "metrics": {
            "visits": total_visits,
            "conversions": total_conversions,
            "revenue": total_revenue,
            "conversion_rate": cvr,
            "revenue_per_visit": rpv
        },
        "by_source": by_source,
        "insights": report["key_insights"],
        "risks_limitations": report["risks_limitations"],
        "recommended_visuals": report["recommended_visuals"],
        "narrative": report["executive_summary"],
        "format": "json"
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    
    # === HANDOFF ===
    report["handoff"]["final_assets"] = ["report_output.json"]
    report["handoff"]["audience_type"] = "business stakeholders"
    
    # === FINALIZE ===
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
    title = ""
    period = ""
    if len(sys.argv) > 1:
        title = sys.argv[1]
    if len(sys.argv) > 2:
        period = sys.argv[2]
    report = generate_report(title=title, period=period)
    print(json.dumps(report, indent=2))
    sys.exit(get_exit_code(report))
