# Findings — Constraints, Research, Assumptions

## Discovery Questions (Verbatim)

1. **North Star**: What single outcome defines success?  
   **Answer**: A small team can run scheduled analytics pipelines that ingest data, clean/analyze it, and deliver formatted reports to a configured destination (webhook or artifact), using only free-tier infrastructure and Gemini Free for routing/formatting.

2. **Integrations**: What external services are required?  
   **Answer**: None mandatory. Optional: HTTP/HTTPS URLs for data source and webhook delivery. Gemini Free API for navigation layer only. No paid third-party analytics or marketing APIs.

3. **Source of Truth**: Where does raw data live?  
   **Answer**: Configurable via env: local file path (e.g. `DATA_SOURCE_PATH`) or URL (`DATA_SOURCE_URL`). Default: `.tmp/raw_input.json` or equivalent for demo.

4. **Delivery Payload**: Where does final output go?  
   **Answer**: Configurable: (1) Webhook URL (`DELIVERY_WEBHOOK_URL`), (2) Local artifact in `.tmp/` (e.g. `report_output.json`, `report_summary.txt`). Reports are structured for downstream use (Sheets, email, dashboards).

5. **Behavior Rules**: Tone, constraints, and "do-not" rules?  
   **Answer**: Professional tone. Constraints: deterministic logic in tools only; LLM may not perform calculations or modify schemas. Do not: use paid APIs, reference "Antigravity" in any asset, guess business logic, or allow LLM to replace tool behavior.

6. **Data-First Rule**: Define strict JSON input/output schemas; store in gemini.md; no coding before schema confirmation.  
   **Answer**: Schemas defined in gemini.md; implementation follows those schemas.

7. **Research**: Identify common open-source patterns for analytics pipelines and marketing reporting; do not include paid tools.  
   **Answer**: Pattern: ingest → clean → analyze → report → deliver. Use CSV/JSON file-based or HTTP polling; open formats; cron or webhook trigger; no proprietary paid SDKs.

---

## Constraints

- **Render free tier**: No persistent disk; use .tmp/ for session intermediates; 512MB–1GB memory; sleep after idle.
- **Gemini Free only**: No paid Gemini or other LLM APIs.
- **Zero paid APIs**: All integrations must work with free tiers or local/file-based inputs.
- **Python 3.10+**: For tools and app.
- **No schema changes by LLM**: Schemas in gemini.md are authoritative; router only routes and formats.

---

## Research Notes

- **Analytics pipelines**: ETL pattern (Extract → Transform → Load) maps to ingest → clean → analyze → report → send_payload.
- **Marketing reporting**: Summary metrics (counts, totals, simple aggregations) plus human-readable narrative; output as JSON and plain text for email/Sheets.
- **Open-source patterns**: Environment-based config; health-check endpoint; idempotent tools; .tmp/ for intermediates; fail-fast on missing env or unreachable URLs when required.

---

## Assumptions

- Team has or will create a Gemini API key (free tier) and set `GEMINI_API_KEY` in Render env.
- Data source is either a local path (e.g. uploaded or mounted) or a public/authenticated URL returning JSON or CSV.
- Delivery webhook accepts POST with JSON body; no custom auth required for minimal setup (optional headers via env if needed).
- Render cron or external cron hits the app’s trigger endpoint on a schedule.
- `.tmp/` is writable; contents are not required to persist across free-tier restarts.
