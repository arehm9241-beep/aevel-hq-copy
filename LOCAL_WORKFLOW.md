# Local workflow — push updates to GitHub (Render deploys from here)

Your Render web app is connected to this repo. When you push to GitHub, Render will redeploy.

## One-time (if not done)

- **Git identity** (if git asks who you are):
  ```powershell
  git config --global user.name "Your Name"
  git config --global user.email "your-email@example.com"
  ```
- **GitHub auth**: Push will open browser or prompt for GitHub login (HTTPS). Or use a [Personal Access Token](https://github.com/settings/tokens) as password when prompted.

## Daily workflow

From the repo folder in PowerShell:

```powershell
cd "c:\Users\Akaya\AiRelated\aevel-hq-copy"

# 1. Get latest from GitHub (if others push or you edited on GitHub)
git pull origin master

# 2. Make your changes in code/UI/config...

# 3. Stage, commit, and push (Render will deploy after push)
git add -A
git commit -m "Short description of what you changed"
git push origin master
```

## Branches

- Default branch is **master**. Render is likely set to deploy from `master`. Push to `master` to update the live site.
- To push a different branch: `git push origin <branch-name>`.

## Quick reference

| Goal              | Command                    |
|-------------------|----------------------------|
| Pull latest       | `git pull origin master`   |
| See status        | `git status`               |
| Push your commits | `git push origin master`   |
