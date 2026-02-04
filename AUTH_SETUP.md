# Authentication Setup — Email/Password with Database

## What Was Added

✅ **Email/password authentication** (no Google OAuth)
✅ **SQLite database** for users and data (stored in `.tmp/app.db`)
✅ **User-specific data** — each user sees only their own tasks, notes, and events
✅ **Login/Register pages** — simple forms
✅ **Session management** — users stay logged in
✅ **Password hashing** — secure password storage

## How It Works

1. **Users register** with email/password (min 6 characters)
2. **Passwords are hashed** using Werkzeug (never stored in plain text)
3. **Each user's data is isolated** — tasks, notes, events are filtered by user_id
4. **Sessions** keep users logged in (stored in Flask session)
5. **Database** is SQLite (works on Render free tier, no extra setup)

## Database Schema

- **users**: id, email, password_hash, created_at
- **tasks**: id, user_id, text, done, created_at
- **notes**: id, user_id, title, body, created_at
- **events**: id, user_id, date, title, created_at

## New Routes

- `GET/POST /login` — Login page
- `GET/POST /register` — Registration page
- `POST /logout` — Logout (clears session)
- All dashboard routes now require login (`@login_required`)

## Updated Files

- `app.py` — Complete rewrite with auth and database
- `requirements.txt` — Added `flask-login` and `werkzeug`
- `templates/login.html` — New login page
- `templates/register.html` — New registration page
- `templates/base.html` — Added user email and logout button

## Security Notes

- **Secret key**: Set `SECRET_KEY` environment variable in Render for production
- **Password hashing**: Uses Werkzeug's `generate_password_hash` / `check_password_hash`
- **SQL injection**: Protected by parameterized queries
- **Session security**: Flask sessions are signed with secret key

## Deployment

1. Push changes to GitHub
2. Render will auto-deploy
3. Database is created automatically on first run
4. Users can register/login immediately

## Environment Variables (Optional)

- `SECRET_KEY` — Set a strong random string for production (defaults to dev key)

## Testing Locally

```bash
python app.py
# Visit http://localhost:10000
# Click "Register" to create account
# Login and use the dashboard
```

## Benefits

✅ No Google OAuth setup needed
✅ Users own their data
✅ Simple email/password auth
✅ Works on Render free tier
✅ Database persists (until Render restarts on free tier)
