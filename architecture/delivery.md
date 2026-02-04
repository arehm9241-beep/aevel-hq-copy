# SOP: Delivery

## Purpose

Send the final report payload to the configured destination: webhook (POST JSON) and/or write to `.tmp/` as artifact (e.g. report_summary.txt for email paste).

## Inputs

- **File**: `.tmp/report_output.json` — output of generate_report tool.
- **Environment**: `DELIVERY_WEBHOOK_URL` (optional). If not set, only local artifact is written.

## Outputs

- **HTTP**: If `DELIVERY_WEBHOOK_URL` set, POST report payload as JSON; respect 2xx as success.
- **File**: `.tmp/report_summary.txt` — human-readable summary (title, period, metrics, narrative) for copy-paste to email/Sheets.
- **Exit**: 0 if all configured deliveries succeed; non-zero if webhook returns non-2xx or write fails.

## Edge Cases

- Webhook URL not set: skip HTTP, only write .tmp/report_summary.txt.
- Webhook returns 4xx/5xx: fail, exit non-zero, log response body.
- Timeout: configurable via env (e.g. DELIVERY_TIMEOUT_SEC); default 10. Fail on timeout.
- report_output.json missing: exit non-zero before sending.

## Golden Rule

SOP updated before any change to send_payload.py behavior.
