# Render Deployment Guide

## Step-by-Step: Deploy to Render (Free Tier)

### Prerequisites
- GitHub account
- Render account (free at https://render.com)
- Your code pushed to GitHub (see TEAM_SETUP.md if needed)

---

## Step 1: Push Code to GitHub

If you haven't already:

```bash
cd C:\Users\Akaya\blast-analytics-repo

# Initialize git (if not done)
git init
git add .
git commit -m "Initial commit: BLAST Analytics dashboard"

# Create repo on GitHub.com, then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

---

## Step 2: Sign Up / Log In to Render

1. Go to **https://render.com**
2. Sign up with GitHub (recommended) or email
3. Verify your email if needed

---

## Step 3: Create New Web Service

1. Click **New +** → **Web Service**
2. Connect your GitHub account (if not already connected)
3. Select your repository (`blast-analytics` or whatever you named it)
4. Click **Connect**

---

## Step 4: Configure Service

Render should auto-detect settings from `render.yaml`, but verify:

**Basic Settings:**
- **Name**: `blast-analytics` (or your choice)
- **Region**: Choose closest to you/team
- **Branch**: `main` (or `master`)

**Build & Deploy:**
- **Environment**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app`

**Advanced Settings (optional):**
- **Auto-Deploy**: `Yes` (deploys on every push to main)

---

## Step 5: Add Environment Variables

Click **Environment** tab and add:

### Recommended (login + admin + email):
- **SECRET_KEY** — Keep your existing one (needed for sessions). Don’t add a duplicate.
- **ADMIN_PASSWORD** — Password to access `/admin` (control which emails are sent and to whom).
- **ZOHO_EMAIL** — `hello.aevel@zohomail.com` (sender address).
- **ZOHO_PASSWORD** — Your Zoho Mail password. If you get “535 Authentication failed”, use an [App Password](https://accounts.zoho.com/home#security/app_passwords) from Zoho (not your normal password; required if 2FA is on).

### Optional (for full features):

**For AI routing:**
- Key: `GEMINI_API_KEY`
- Value: Your Gemini API key (get free at https://aistudio.google.com/apikey)

**For data pipeline:**
- Key: `DATA_SOURCE_PATH` OR `DATA_SOURCE_URL`
- Value: Path to file or URL to data source

**For webhook delivery:**
- Key: `DELIVERY_WEBHOOK_URL`
- Value: Your webhook endpoint URL

**Note:** `PYTHON_VERSION` and `DELIVERY_TIMEOUT_SEC` are already set in `render.yaml`.

---

## Step 6: Deploy

1. Click **Create Web Service**
2. Render will:
   - Clone your repo
   - Run `pip install -r requirements.txt`
   - Start `gunicorn app:app`
3. Wait 2-5 minutes for first deploy
4. You'll see a URL like: `https://blast-analytics.onrender.com`

---

## Step 7: Test Your Deployment

Open your Render URL:
- `https://YOUR-APP-NAME.onrender.com` → Redirects to login
- `https://YOUR-APP-NAME.onrender.com/dashboard` → Dashboard (after login)
- `https://YOUR-APP-NAME.onrender.com/admin` → Admin (password from `ADMIN_PASSWORD`)
- `https://YOUR-APP-NAME.onrender.com/health` → Health check API

---

## Step 8: Share with Team

1. Share the Render URL with your team
2. Everyone can access the dashboard at that URL
3. Tasks, notes, and calendar events are **shared** (stored on Render's server)

---

## Important Notes

### Free Tier Limits:
- **Sleep**: App sleeps after ~15 minutes of inactivity
- **Wake time**: First request after sleep takes ~30-60 seconds
- **Hours**: 750 free hours/month (enough for 24/7 if you keep it active)
- **Data**: `.tmp/` files reset on deploy/restart (tasks/notes/events may be lost)

### To Keep App Awake (Optional):
- Use a cron service (like cron-job.org) to ping `/health` every 10 minutes
- Or upgrade to Render paid plan ($7/month) for always-on

### Updating Your App:
1. Push changes to GitHub: `git push`
2. Render auto-deploys (if auto-deploy is on)
3. Or manually click **Manual Deploy** → **Deploy latest commit**

---

## Troubleshooting

**App won't start:**
- Check **Logs** tab in Render dashboard
- Common issues: Missing dependencies, wrong start command, port binding

**Dashboard shows errors:**
- Check browser console (F12)
- Verify environment variables are set correctly

**Data disappears:**
- Normal on free tier restarts
- Consider upgrading or using external database for persistence

**Slow first load:**
- Normal after sleep (cold start)
- Subsequent loads are fast

---

## Next Steps

- Add team members to GitHub repo (Settings → Collaborators)
- They can push code changes
- Everyone uses the same Render URL for the live app
