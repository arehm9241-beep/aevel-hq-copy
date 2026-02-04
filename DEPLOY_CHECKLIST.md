# Render Deployment Checklist

## ✅ Pre-Deployment

- [ ] Code is pushed to GitHub
- [ ] `render.yaml` exists (✅ already in repo)
- [ ] `requirements.txt` has gunicorn (✅ already included)
- [ ] `app.py` is ready (✅ already configured)

## 🚀 Deployment Steps

1. [ ] Go to https://render.com and sign up/login
2. [ ] Click **New +** → **Web Service**
3. [ ] Connect GitHub account
4. [ ] Select your repository
5. [ ] Verify settings (auto-detected from `render.yaml`):
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app`
6. [ ] Add environment variables (optional):
   - [ ] `GEMINI_API_KEY` (for AI features)
   - [ ] `DATA_SOURCE_PATH` or `DATA_SOURCE_URL` (for pipeline)
   - [ ] `DELIVERY_WEBHOOK_URL` (for webhooks)
7. [ ] Click **Create Web Service**
8. [ ] Wait 2-5 minutes for deploy
9. [ ] Copy your Render URL (e.g., `https://blast-analytics.onrender.com`)

## ✅ Post-Deployment

- [ ] Test dashboard: `YOUR-URL/dashboard`
- [ ] Test calendar: `YOUR-URL/calendar`
- [ ] Test tasks: `YOUR-URL/tasks`
- [ ] Test notes: `YOUR-URL/notes`
- [ ] Test AI: `YOUR-URL/ai`
- [ ] Test health: `YOUR-URL/health`

## 📤 Share with Team

- [ ] Share Render URL with team members
- [ ] Add team to GitHub repo (Settings → Collaborators)
- [ ] Everyone can now:
  - Access live app at Render URL
  - Push code changes via GitHub

## 💡 Pro Tips

- **Keep app awake**: Set up cron-job.org to ping `/health` every 10 minutes
- **Auto-deploy**: Enable in Render settings (deploys on every git push)
- **Monitor**: Check Logs tab in Render dashboard for errors
- **Data persistence**: Free tier resets `.tmp/` on restart (tasks/notes/events may be lost)

---

**Ready?** Follow `RENDER_DEPLOY.md` for detailed instructions!
