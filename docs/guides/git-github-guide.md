# Git & GitHub Quick Guide

> How to commit changes and push to GitHub for the Jarvis project.

---

## Prerequisites

- Git installed (`git --version` to verify)
- SSH key added to your GitHub account (see [GitHub SSH setup](https://docs.github.com/en/authentication/connecting-to-github-with-ssh))
- Remote configured: `git remote -v` should show your GitHub repo

## The 3-Step Workflow

Every time you want to save your changes to GitHub:

```bash
git add .                    # 1. Stage all changes
git commit -m "your message" # 2. Create a commit (local snapshot)
git push                     # 3. Upload to GitHub
```

That's it. The most common mistake is running `git push` without `git commit` first — push only uploads **committed** snapshots, not uncommitted files.

## Step-by-Step

### 1. Check what changed

```bash
git status                   # Shows modified/new/deleted files
git diff                     # Shows line-by-line changes (unstaged)
git diff --cached            # Shows line-by-line changes (staged)
```

### 2. Stage files

```bash
git add .                    # Stage everything
git add scripts/rag/agent.py # Stage a specific file
git add docs/                # Stage an entire folder
```

### 3. Commit

```bash
git commit -m "docs: reorganize docs structure and update for recent changes"
```

**Commit message format** (Conventional Commits):

```
<type>: <short description>

Types:
  feat:     New feature
  fix:      Bug fix
  docs:     Documentation only
  refactor: Code restructuring (no behavior change)
  chore:    Maintenance (deps, configs)
  test:     Adding or updating tests
```

For Jarvis, prefix with the task number if available:

```bash
git commit -m "[TASK-42] feat: add wiki fetch page details with links"
```

### 4. Push to GitHub

```bash
git push                     # Push current branch to remote
git push -u origin main      # First push (sets tracking)
```

## Common Scenarios

### "I made changes but `git push` says 'Everything up-to-date'"

You forgot to commit. Run:

```bash
git add .
git commit -m "your message"
git push
```

### "I want to see what will be committed"

```bash
git diff --cached --stat     # Summary: files and line counts
git diff --cached            # Full diff of staged changes
```

### "I want to undo my last commit (not pushed yet)"

```bash
git reset --soft HEAD~1      # Undo commit, keep changes staged
```

### "I want to discard all uncommitted changes"

```bash
git checkout -- .            # Discard all unstaged changes (DESTRUCTIVE)
```

### "Remote has changes I don't have"

```bash
git pull --rebase            # Fetch + rebase your commits on top
git push
```

### "I want to see commit history"

```bash
git log --oneline -10        # Last 10 commits, one line each
git log --oneline --graph    # With branch visualization
```

## SSH Key Setup (One-Time)

If `git push` gives `Permission denied (publickey)`:

### 1. Generate a key (if you don't have one)

```bash
ssh-keygen -t ed25519 -C "your@email.com"
```

Press Enter for all prompts (default location, no passphrase is fine).

### 2. Copy your public key

```bash
cat ~/.ssh/id_ed25519.pub
```

### 3. Add to GitHub

1. Go to https://github.com/settings/keys
2. Click **"New SSH key"**
3. Paste the key, give it a name, click **"Add SSH key"**

### 4. Test

```bash
ssh -T git@github.com
# Expected: "Hi username! You've successfully authenticated..."
```

## Jarvis Repo Setup

```bash
cd c:\jarvis
git init                                          # Only once
git remote add origin git@github.com:medavisyin/jarvis-yin.git  # Only once
git add .
git commit -m "initial commit"
git push -u origin main                           # First push
```

After initial setup, the daily workflow is just:

```bash
git add .
git commit -m "what you changed"
git push
```

## Quick Reference Card

| Command | What it does |
|---------|-------------|
| `git status` | Show what's changed |
| `git add .` | Stage all changes |
| `git commit -m "msg"` | Save a snapshot locally |
| `git push` | Upload to GitHub |
| `git pull` | Download from GitHub |
| `git log --oneline -5` | Show recent commits |
| `git diff` | Show unstaged changes |
| `git diff --cached` | Show staged changes |
| `git remote -v` | Show remote URL |
| `ssh -T git@github.com` | Test SSH connection |
