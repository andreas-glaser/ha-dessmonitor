# Release Guide

## Pre-Release Steps

0. **Sync local `dev` with remote**
  ```bash
  git fetch origin
  git checkout dev
  git rebase origin/dev  # or `git pull --rebase`
  ```

1. **Ensure on `dev` branch**
  ```bash
  git checkout dev
  ```

2. **Run code quality checks**
   ```bash
   black custom_components/dessmonitor
   isort custom_components/dessmonitor
   flake8 custom_components/dessmonitor --max-line-length=127
   mypy custom_components/dessmonitor --ignore-missing-imports
   ```

3. **Update version files**
  - `custom_components/dessmonitor/manifest.json` → `"version": "X.Y.Z"`
  - `custom_components/dessmonitor/const.py` → `VERSION = "X.Y.Z"`
  - `VERSION` → `X.Y.Z`

4. **Update CHANGELOG.md**
   - Add section `## [X.Y.Z] - YYYY-MM-DD`
   - List changes under: Added/Changed/Fixed/Removed
   - Set the date with `date +%F` (ISO, YYYY-MM-DD)
   - Use git logs to gather changes since the last tag:
     ```bash
     # Determine last release tag
     last_tag=$(git describe --tags --abbrev=0)

     # Quick overview (oldest → newest)
     git log --reverse --oneline "${last_tag}..HEAD"

     # Detailed subject list to paste/categorize in the changelog
     git log --reverse --pretty=format:"- %s (%h) by %an" "${last_tag}..HEAD"

     # If you use conventional commits, triage by type
     git log --reverse --pretty=format:"%s" "${last_tag}..HEAD" \
       | grep -E '^(feat|fix|docs|refactor|chore|test|style):'
     ```
   - Optionally include a GitHub compare link in the changelog: `https://github.com/andreas-glaser/ha-dessmonitor/compare/${last_tag}...vX.Y.Z`
   - Update reference links at the bottom of `CHANGELOG.md`:
     - Change `[Unreleased]` to compare from the new tag: `.../compare/vX.Y.Z...HEAD`
     - Add a new reference for `[X.Y.Z]` comparing `${last_tag}...vX.Y.Z`

5. **Commit changes**
   ```bash
   git add -A
   git commit -m "chore: prepare release vX.Y.Z"
   ```

## Release Process

6. **Merge to main**
  ```bash
  git checkout main
  git merge dev --no-ff -m "Merge dev for vX.Y.Z release"
  ```

7. **Create & push tag with changelog message**
   ```bash
   # Create annotated tag with changelog excerpt
   # Use git log to copy the relevant items for the tag message as well
   git tag -a vX.Y.Z -m "Release vX.Y.Z

   ## Added
   - Feature 1
   - Feature 2
   
   ## Fixed  
   - Bug fix 1
   
   ## Changed
   - Improvement 1"
   
   git push origin main --tags
   ```

8. **GitHub Actions auto-creates release**
   - Workflow triggers on tag push
   - Creates ZIP package for HACS
   - Publishes GitHub release

9. **Verify GitHub Actions**
   ```bash
   # Check workflow status via CLI
   gh workflow view "Release"
   gh run list --workflow="Release" --limit 3
   ```
   - Or manually: https://github.com/andreas-glaser/ha-dessmonitor/actions

## Post-Release

10. **Sync dev with main**
  ```bash
  git checkout dev
  git merge main
  git push origin dev
  ```

## Version Bumping Rules
- **Patch (X.Y.Z+1)**: Bug fixes only
- **Minor (X.Y+1.0)**: New features, backwards compatible
- **Major (X+1.0.0)**: Breaking changes

## Files Modified Per Release
- `custom_components/dessmonitor/manifest.json`
- `custom_components/dessmonitor/const.py`
- `VERSION`
- `CHANGELOG.md`
- `README.md`
