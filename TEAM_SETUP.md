# Team Collaboration Setup Guide

## Option 1: GitHub + Render (Recommended)

### Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Create a new repository (e.g., `blast-analytics`)
3. **Don't** initialize with README (you already have one)

### Step 2: Push Your Code to GitHub

```bash
cd C:\Users\Akaya\blast-analytics-repo

# Initialize git (if not done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit: BLAST Analytics dashboard"

# Add GitHub remote (replace YOUR_USERNAME and REPO_NAME)
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git

# Push
git branch -M main
git push -u origin main
```

### Step 3: Add Team Members to GitHub

1. Go to your repo → **Settings** → **Collaborators**
2. Click **Add people**
3. Enter GitHub usernames/emails
4. They'll get an invite email

### Step 4: Deploy on Render (Free Tier)

1. Go to https://render.com and sign up/login
2. Click **New** → **Web Service**
3. Connect your GitHub account
4. Select your `blast-analytics` repository
5. Configure:
   - **Name**: `blast-analytics` (or your choice)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
6. Add environment variables (in Render dashboard):
   - `GEMINI_API_KEY` (optional, for AI routing)
   - `DATA_SOURCE_PATH` or `DATA_SOURCE_URL` (optional)
   - `DELIVERY_WEBHOOK_URL` (optional)
7. Click **Create Web Service**

### Step 5: Share Render URL with Team

- Render gives you a URL like: `https://blast-analytics.onrender.com`
- Share this URL with your team
- Everyone can access the dashboard at this URL

### Step 6: Team Workflow

**For code changes:**
1. Team members clone: `git clone https://github.com/YOUR_USERNAME/REPO_NAME.git`
2. Make changes locally
3. Push to GitHub: `git push`
4. Render auto-deploys (or manual deploy from Render dashboard)

**For using the app:**
- Everyone uses the Render URL
- Data (tasks, notes, events) is stored in `.tmp/` on Render (shared across team)
- Note: Render free tier sleeps after inactivity; first request wakes it up (~30 seconds)

---

## Option 2: GitHub Only (Code Collaboration)

If you only need code collaboration (not a live shared app):

1. Follow **Step 1-3** above (GitHub setup)
2. Team clones and runs locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/REPO_NAME.git
   cd REPO_NAME
   pip install -r requirements.txt
   python app.py
   ```
3. Each person runs on their own `localhost:10000`
4. Data is local (not shared)

---

## Option 3: Shared Server (VPS/Cloud)

If you want persistent data and no sleep:

1. Use a VPS (DigitalOcean, Linode, AWS EC2 free tier)
2. Install Python, clone repo, run with `gunicorn` + nginx
3. Share IP/domain with team
4. Data persists on server disk

---

## Quick Start Commands

```bash
# Initialize git repo
cd C:\Users\Akaya\blast-analytics-repo
git init
git add .
git commit -m "Initial commit"

# Connect to GitHub (replace URL)
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
git branch -M main
git push -u origin main

# Team members clone
git clone https://github.com/YOUR_USERNAME/REPO_NAME.git
cd REPO_NAME
pip install -r requirements.txt
python app.py
```

---

## Notes

- **`.env` file**: Never commit this (already in `.gitignore`)
- **`.tmp/` data**: On Render free tier, data resets if the service restarts
- **Team access**: GitHub for code, Render URL for live app
- **Free tier limits**: Render free tier sleeps after ~15 min inactivity
