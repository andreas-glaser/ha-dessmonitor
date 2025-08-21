# Release Guide

## Pre-Release Steps

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

7. **Create & push tag**
   ```bash
   git tag vX.Y.Z
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
   gh run list --workflow=release.yml
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