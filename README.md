# B.L.A.S.T. Analytics

Production-ready data analytics and marketing automation pipeline. B.L.A.S.T. protocol and A.N.T. 3-layer architecture. Render free-tier deployable; Gemini Free for routing only; zero paid APIs.

## Repo structure

```
├── app.py
├── requirements.txt
├── render.yaml
├── .env.example
├── README.md
├── gemini.md
├── task_plan.md
├── findings.md
├── progress.md
├── architecture/
├── navigation/
├── tools/
└── .tmp/
```

## Quick start

1. Clone repo; copy `.env.example` to `.env`.
2. Set `GEMINI_API_KEY` (free tier) if using router classification. Set `DATA_SOURCE_PATH` or `DATA_SOURCE_URL` for pipeline.
3. `pip install -r requirements.txt`
4. `python app.py` — app runs on port 10000 (or `PORT`).
5. `GET /health` — verify env and connections.
6. `POST /trigger` — run full pipeline (or pass `action` in body for single step).

## Deploy on Render

1. New Web Service; connect this repo.
2. Build: `pip install -r requirements.txt`; Start: `gunicorn app:app`.
3. Add env vars in Dashboard: `GEMINI_API_KEY`, `DATA_SOURCE_PATH` or `DATA_SOURCE_URL`, optional `DELIVERY_WEBHOOK_URL`.
4. Cron: use Render cron or external scheduler to `POST /trigger` on schedule.

## Testing

Run API persistence and scoping tests (no pytest required):

```bash
python -m unittest tests.test_api_persistence -v
```

Uses a temporary DB; verifies workspace, flowcharts, tasks, notes, events, community notes, and activity logging.

## Admin & email (Zoho Mail)

- **Admin** (`/admin`): Password-protected area to control which emails are sent and to whom. Set `ADMIN_PASSWORD` in `.env` (no default).
- **Zoho Mail**: Notifications (task assigned, due soon, digest) are sent from `hello.aevel@zohomail.com` (free Zoho). Set `ZOHO_EMAIL` and `ZOHO_PASSWORD` in `.env`. SMTP: `smtp.zoho.com:465` (SSL).

## Architecture

- **Layer 1** `architecture/`: SOPs (ingestion, analytics, marketing, delivery, error_handling). SOPs updated before code.
- **Layer 2** `navigation/`: Router uses Gemini Free only — routes and formats; no calculations or schema changes.
- **Layer 3** `tools/`: Python, deterministic, atomic; intermediates in `.tmp/`.

## Conventions

- Schemas and invariants: `gemini.md`.
- No paid APIs; Gemini Free only.
- Fail-fast: health check fails if required env or URL unreachable.
