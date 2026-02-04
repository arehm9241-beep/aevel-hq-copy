# Render setup / start command

Recommended start command (for Render service):
  gunicorn app:app --bind 0.0.0.0:\

Notes:
- Make sure gunicorn is listed in requirements.txt.
- Add any required environment variables on Render (copy from the original Render service):
  - SECRET_KEY, DATABASE_URL, REDIS_URL, etc. (see .env.example)
- If your app uses a specific Python version, set it in Render or add a runtime.txt.

See RENDER_DEPLOY.md in the repo for full instructions.
