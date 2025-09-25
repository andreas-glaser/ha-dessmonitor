# Git, Branching, and Tagging Guide

This guide explains the repository’s git setup, branching strategy, and tagging/release flow. It complements CONTRIBUTING.md and the Release/Commit guides.

## Branch Model

Branches used:
- `main`: stable, production-ready. Protected.
- `dev`: integration branch for upcoming release.
- `feature/*`: new features (e.g., `feature/add-battery-temp`).
- `fix/*`: bug fixes for next release (e.g., `fix/api-timeout`).
- `hotfix/*`: urgent fixes based off `main` (e.g., `hotfix/auth-failure`).
- `release/*`: stabilization before release (optional).

PR targets:
- Features and fixes → target `dev`.
- Hotfixes → target `main` and then forward-merge to `dev`.

## Local Git Setup

Initial configuration:
```bash
# Identity
git config --global user.name "Your Name"
git config --global user.email "you@example.com"

# Safer, cleaner history (recommended)
git config --global pull.rebase true
git config --global rebase.autoStash true
git config --global fetch.prune true

# Optional: sign commits/tags (if you use GPG/SSH signing)
# git config --global commit.gpgsign true
# git config --global tag.gpgSign true
```

Clone and track branches:
```bash
git clone git@github.com:andreas-glaser/ha-dessmonitor.git
cd ha-dessmonitor

# Ensure local tracking branch for dev
git fetch origin dev:dev
git checkout dev
```

Keep your fork up to date (if contributing via a fork):
```bash
# Add upstream once
git remote add upstream git@github.com:andreas-glaser/ha-dessmonitor.git

# Update your local main and dev
git fetch upstream
git checkout main && git rebase upstream/main
git checkout dev && git rebase upstream/dev

# Push synced branches to your fork
git push origin main
git push origin dev
```

## Working on Changes

Feature:
```bash
git checkout dev
git pull --rebase origin dev
git checkout -b feature/your-feature
# ...work, commit...
git push -u origin feature/your-feature
# Open PR → base: dev
```

Bug fix (non-urgent):
```bash
git checkout dev
git pull --rebase origin dev
git checkout -b fix/short-desc
# ...work, commit...
git push -u origin fix/short-desc
# Open PR → base: dev
```

Hotfix (urgent production fix):
```bash
git checkout main
git pull --rebase origin main
git checkout -b hotfix/short-desc
# ...work, commit...
git push -u origin hotfix/short-desc
# Open PR → base: main

# After merge, maintainers will forward-merge main → dev
```

## Version Bumping

Preferred: GitHub Action “Bump Version” (updates VERSION, manifest.json, and CHANGELOG):
1. Actions → “Bump Version” → choose bump type (patch/minor/major) and branch (`dev`).
2. Action commits the bump to `dev`.

Manual (local):
```bash
echo "1.2.3" > VERSION
yq eval -i -P '.version="1.2.3"' custom_components/dessmonitor/manifest.json
# Update CHANGELOG.md under [Unreleased]
git add VERSION custom_components/dessmonitor/manifest.json CHANGELOG.md
git commit -m "Bump version to 1.2.3"
```

## Tagging and Releases

Release tags follow SemVer with a `v` prefix: `vX.Y.Z`.

Create an annotated tag and push:
```bash
# Ensure dev is merged into main first
git checkout main
git pull --rebase origin main
git merge --no-ff dev -m "Merge dev for v1.2.3 release"
git push origin main

# Tag the release (annotated)
git tag -a v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3
```

What happens next:
- GitHub Action “Release” triggers on tag `v*.*.*`.
- CI validates CHANGELOG entry, updates VERSION/manifest.json (for manual dispatch case), builds ZIPs, and publishes the GitHub Release with assets.

Manual release (workflow dispatch):
```bash
# Actions → Release → Run workflow → version: v1.2.3
```

## Forward-Merging Hotfixes

After a hotfix is tagged from `main`, merge it back into `dev` to keep branches aligned:
```bash
git checkout dev
git pull --rebase origin dev
git merge --no-ff main -m "Merge main into dev after v1.2.3 hotfix"
git push origin dev
```

## Handy Commands

```bash
# See branch graph
git log --oneline --graph --decorate --all --date-order

# Clean stale local branches
git fetch -p
git branch --merged | grep -vE "\*|main|dev" | xargs -r git branch -d

# Abort a rebase if needed
git rebase --abort

# Resolve conflicts then continue
git add -A && git rebase --continue
```

