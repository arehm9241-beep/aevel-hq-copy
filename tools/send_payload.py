"""
DELIVER AGENT — "The Final Mile"

Purpose: Package and distribute outputs in the correct format, channel, and tone.

Rules:
- No content changes
- No interpretation
- Preserve content integrity
- Ensure accessibility and clarity

Input: Final report, audience requirements
Output: Deployed artifact (PDF, dashboard, email, API payload), delivery confirmation
"""

import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

TMP_DIR = Path(__file__).resolve().parent.parent / ".tmp"
INPUT_FILE = TMP_DIR / "report_output.json"
SUMMARY_FILE = TMP_DIR / "report_summary.txt"
REPORT_FILE = TMP_DIR / "deliver_report.json"


def send_payload() -> dict:
    """
    Run the Deliver Agent.
    Returns a structured report following the strict agent output format.
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize report structure
    report = {
        "agent": "DELIVER",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "delivery_format": {
            "medium": [],
            "audience": "business stakeholders"
        },
        "final_assets": {
            "files_produced": []
        },
        "distribution_method": {
            "channels": [],
            "access_controls": "none specified"
        },
        "delivery_confirmation": {
            "status": "pending",
            "timestamp": None,
            "details": []
        }
    }
    
    # === CHECK INPUT FILE ===
    if not INPUT_FILE.is_file():
        report["status"] = "error"
        report["delivery_confirmation"]["status"] = "failed"
        report["delivery_confirmation"]["details"].append(
            "report_output.json not found. Run Report Agent first."
        )
        _save_report(report)
        return report
    
    # === LOAD REPORT DATA ===
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        report["status"] = "error"
        report["delivery_confirmation"]["status"] = "failed"
        report["delivery_confirmation"]["details"].append(f"Invalid JSON: {str(e)}")
        _save_report(report)
        return report
    
    # === DELIVERY CONFIGURATION ===
    timeout = int(os.environ.get("DELIVERY_TIMEOUT_SEC", "10") or "10")
    webhook = (os.environ.get("DELIVERY_WEBHOOK_URL") or "").strip()
    
    delivery_success = True
    
    # === WEBHOOK DELIVERY ===
    if webhook:
        report["distribution_method"]["channels"].append("webhook")
        report["delivery_format"]["medium"].append("JSON API payload")
        
        try:
            body = json.dumps(payload).encode("utf-8")
            req = Request(
                webhook,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Aevel-Pipeline/1.0",
                    "X-Aevel-Agent": "DELIVER"
                },
                method="POST",
            )
            with urlopen(req, timeout=timeout) as resp:
                status_code = resp.status
                if status_code >= 400:
                    delivery_success = False
                    report["delivery_confirmation"]["details"].append(
                        f"Webhook returned HTTP {status_code}"
                    )
                else:
                    report["delivery_confirmation"]["details"].append(
                        f"Webhook delivery successful (HTTP {status_code})"
                    )
        except (HTTPError, URLError) as e:
            delivery_success = False
            report["delivery_confirmation"]["details"].append(
                f"Webhook delivery failed: {str(e)}"
            )
        except Exception as e:
            delivery_success = False
            report["delivery_confirmation"]["details"].append(
                f"Webhook error: {str(e)}"
            )
    
    # === LOCAL FILE DELIVERY ===
    report["distribution_method"]["channels"].append("local_file")
    report["delivery_format"]["medium"].append("Plain text summary")
    report["delivery_format"]["medium"].append("JSON report")
    
    # Build human-readable summary
    title = payload.get("title", "Analytics Report")
    period = payload.get("period", "")
    metrics = payload.get("metrics", {})
    executive_summary = payload.get("executive_summary", payload.get("narrative", ""))
    by_source = payload.get("by_source", [])
    insights = payload.get("insights", [])
    risks = payload.get("risks_limitations", [])
    
    lines = [
        "=" * 60,
        title.upper(),
        "=" * 60,
        "",
        f"Period: {period}",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "-" * 60,
        "EXECUTIVE SUMMARY",
        "-" * 60,
        "",
        executive_summary,
        "",
        "-" * 60,
        "KEY METRICS",
        "-" * 60,
        "",
        f"  Visits:          {metrics.get('visits', 0):,.0f}",
        f"  Conversions:     {metrics.get('conversions', 0):,.0f}",
        f"  Revenue:         ${metrics.get('revenue', 0):,.2f}",
        f"  Conversion Rate: {metrics.get('conversion_rate', 0):.2f}%",
        f"  Revenue/Visit:   ${metrics.get('revenue_per_visit', 0):.2f}",
        "",
    ]
    
    # Source breakdown
    if by_source:
        lines.extend([
            "-" * 60,
            "PERFORMANCE BY SOURCE",
            "-" * 60,
            "",
        ])
        
        # Header
        lines.append(f"{'Source':<15} {'Visits':>10} {'Conv':>8} {'Revenue':>12} {'CVR':>8}")
        lines.append("-" * 55)
        
        for src in by_source:
            lines.append(
                f"{src['source']:<15} {src['visits']:>10,.0f} {src['conversions']:>8,.0f} ${src['revenue']:>10,.2f} {src.get('conversion_rate', 0):>7.2f}%"
            )
        lines.append("")
    
    # Key Insights
    if insights:
        lines.extend([
            "-" * 60,
            "KEY INSIGHTS",
            "-" * 60,
            "",
        ])
        for i, insight in enumerate(insights, 1):
            if isinstance(insight, dict):
                lines.append(f"{i}. {insight.get('insight', '')}")
                narrative = insight.get('narrative', '')
                if narrative:
                    lines.append(f"   {narrative}")
                lines.append("")
            else:
                lines.append(f"{i}. {insight}")
                lines.append("")
    
    # Risks & Limitations
    if risks:
        lines.extend([
            "-" * 60,
            "RISKS & LIMITATIONS",
            "-" * 60,
            "",
        ])
        for risk in risks:
            lines.append(f"  • {risk}")
        lines.append("")
    
    lines.extend([
        "-" * 60,
        "END OF REPORT",
        "-" * 60,
        "",
        "This report was generated by the Aevel Analytics Pipeline.",
        "Agents: INGEST → CLEAN → ANALYZE → REPORT → DELIVER"
    ])
    
    # Write text summary
    summary_content = "\n".join(lines)
    try:
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            f.write(summary_content)
        report["final_assets"]["files_produced"].append({
            "filename": "report_summary.txt",
            "path": str(SUMMARY_FILE),
            "format": "plain text",
            "size_bytes": len(summary_content.encode("utf-8"))
        })
        report["delivery_confirmation"]["details"].append(
            f"Text summary written to {SUMMARY_FILE.name}"
        )
    except Exception as e:
        delivery_success = False
        report["delivery_confirmation"]["details"].append(
            f"Failed to write summary: {str(e)}"
        )
    
    # Include JSON report in assets
    report["final_assets"]["files_produced"].append({
        "filename": "report_output.json",
        "path": str(INPUT_FILE),
        "format": "JSON",
        "size_bytes": INPUT_FILE.stat().st_size if INPUT_FILE.is_file() else 0
    })
    
    # === FINALIZE ===
    report["delivery_confirmation"]["status"] = "success" if delivery_success else "partial"
    report["delivery_confirmation"]["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    if not webhook:
        report["delivery_confirmation"]["details"].append(
            "No DELIVERY_WEBHOOK_URL configured. Only local artifacts produced."
        )
    
    report["status"] = "success" if delivery_success else "partial"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_report(report)
    
    return report


def _save_report(report: dict):
    """Save the structured report to file."""
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def get_exit_code(report: dict) -> int:
    """Convert report status to exit code."""
    if report.get("status") == "success":
        return 0
    elif report.get("status") == "partial":
        return 0  # Partial success is still success
    else:
        return 1


if __name__ == "__main__":
    report = send_payload()
    print(json.dumps(report, indent=2))
    sys.exit(get_exit_code(report))
