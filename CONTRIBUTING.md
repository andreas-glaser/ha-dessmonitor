# Contributing to DessMonitor Integration

Thank you for your interest in contributing to the DessMonitor Home Assistant integration!

## 🔗 Related Guides

- Commit Guide: `docs/COMMIT_GUIDE.md`
- Release Guide: `docs/RELEASE_GUIDE.md`
- Git/Branching & Tagging: `docs/GIT_GUIDE.md`

## 📋 Development Workflow

### Branching Strategy

We use a **Git Flow** inspired branching model:

```
main (production/stable)
├── dev (integration branch)
├── feature/* (new features)
├── fix/* (bug fixes)
├── hotfix/* (critical fixes)
└── release/* (release preparation)
```

**Branch Descriptions:**
- **`main`**: Production-ready releases only. Protected branch.
- **`dev`**: Integration branch for tested features. Default development branch.
- **`feature/*`**: Individual feature development (e.g., `feature/new-sensor-type`).
- **`fix/*`**: Bug fixes targeting the next release (e.g., `fix/timeout-handling`).
- **`hotfix/*`**: Critical bug fixes for production (e.g., `hotfix/auth-failure`).
- **`release/*`**: Release preparation and final testing (e.g., `release/1.1.0`).

### Development Setup

1. **Install development dependencies:**
   ```bash
   make install
   ```
   This creates a virtual environment and installs all required tools (Black, isort, flake8, mypy).

2. **Run code quality checks:**
   ```bash
   make check   # Check code without modifying
   make format  # Format code with Black and isort
   make lint    # Run all linting checks
   ```

   Scope local checks to changed files. For example:
   ```bash
   make format PYTHON_PATHS='custom_components/dessmonitor/local/discovery.py'
   make lint PYTHON_PATHS='custom_components/dessmonitor/local/discovery.py'
   PYTEST_ADDOPTS='tests/local/test_discovery.py -q' make test
   ```

### Development Process

1. **For new features:**
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feature/your-feature-name
   # ... develop your feature
   make check   # Run quality checks before committing
   git push origin feature/your-feature-name
   # Create PR to dev branch
   ```

2. **For bug fixes:**
   ```bash
   git checkout dev  
   git checkout -b fix/issue-description
   # ... fix the issue
   git push origin fix/issue-description
   # Create PR to dev branch
   ```

3. **For hotfixes (critical production fixes):**
   ```bash
   git checkout main
   git checkout -b hotfix/critical-fix
   # ... fix the critical issue
   git push origin hotfix/critical-fix
   # Create PR to main AND dev branches
   ```

## 🏷️ Versioning Strategy

We follow **Semantic Versioning (SemVer 2.0.0)**:

```
MAJOR.MINOR.PATCH (e.g., 1.2.3)
```

### Version Increment Rules

| Type | When to Increment | Examples |
|------|------------------|----------|
| **MAJOR** | Breaking changes | API changes requiring reconfiguration, removal of deprecated features, minimum HA version bumps |
| **MINOR** | New features (backward compatible) | New sensor types, new configuration options, enhanced functionality |
| **PATCH** | Bug fixes (backward compatible) | Bug fixes, performance improvements, documentation updates |

### Version Management

#### Automated Version Bumping

Use the GitHub Actions workflow to bump versions:

1. **Go to Actions** → **Bump Version**
2. **Choose bump type**: patch, minor, or major
3. **Select branch**: usually `dev`
4. **Run workflow**

This will:
- ✅ Calculate new version automatically
- ✅ Update `VERSION` file
- ✅ Update `manifest.json`
- ✅ Add changelog entry
- ✅ Commit changes

#### Manual Version Bumping

If you prefer manual control:

```bash
# Update VERSION file
echo "1.1.0" > VERSION

# Update manifest.json
yq eval -i -P '.version="1.1.0"' custom_components/dessmonitor/manifest.json

# Update CHANGELOG.md (add your changes)
# Then commit
git add VERSION custom_components/dessmonitor/manifest.json CHANGELOG.md
git commit -m "Bump version to 1.1.0"
```

Note: The manual snippet requires `yq` to be installed locally.

## 🚀 Release Process

### Standard Release (from dev)

1. **Ensure dev branch is ready:**
   ```bash
   git checkout dev
   git pull origin dev
   # Verify all tests pass
   ```

2. **Create release branch:**
   ```bash
   git checkout -b release/1.1.0
   ```

3. **Final preparations:**
   - Update CHANGELOG.md with final release notes
   - Test the integration thoroughly
   - Fix any last-minute issues

4. **Merge to main:**
   ```bash
   git checkout main
   git pull origin main
   git merge release/1.1.0
   git push origin main
   ```

5. **Create release (automated):**
   - **Go to Actions** → **Release**
   - **Run workflow** with version `1.1.0`
   - This will create GitHub release with ZIP files

6. **Merge back to dev:**
   ```bash
   git checkout dev
   git merge release/1.1.0
   git push origin dev
   git branch -d release/1.1.0
   ```

### Hotfix Release (from main)

1. **Create hotfix branch:**
   ```bash
   git checkout main
   git checkout -b hotfix/1.0.1
   ```

2. **Fix the critical issue and test**

3. **Merge to main:**
   ```bash
   git checkout main  
   git merge hotfix/1.0.1
   git push origin main
   ```

4. **Create release:**
   - Use GitHub Actions Release workflow

5. **Merge to dev:**
   ```bash
   git checkout dev
   git merge hotfix/1.0.1
   git push origin dev
   git branch -d hotfix/1.0.1
   ```

## 📝 Changelog Management

We use [Keep a Changelog](https://keepachangelog.com/) format.

### Adding Changes

When making changes, update `CHANGELOG.md` under `## [Unreleased]`:

```markdown
## [Unreleased]

### Added
- New sensor for inverter temperature monitoring

### Changed  
- Improved error handling for API timeouts

### Fixed
- Fixed duplicate sensor creation issue
```

### Categories

- **Added**: New features
- **Changed**: Changes in existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Now removed features
- **Fixed**: Bug fixes
- **Security**: Vulnerability fixes

## 🧪 Testing Requirements

Before submitting a PR:

1. **All GitHub Actions must pass:**
   - ✅ Hassfest validation
   - ✅ HACS validation  
   - ✅ Tests (linting, formatting)

2. **Run the test suite:**
   ```bash
   make install   # installs dev + test dependencies (one-time)
   make test      # run the pytest suite
   make test-cov  # run with a coverage report
   ```
   Tests live in `tests/` and run against a real Home Assistant core via
   [`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
   (pinned in `requirements_test.txt`; pytest settings are in `pyproject.toml`).
   Add tests for any behaviour you change, and keep the suite green.

3. **Test your changes locally:**
   - Install in a Home Assistant test environment
   - Verify existing functionality still works
   - Test new features thoroughly

4. **Code quality:**
   - Follow existing code patterns
   - Add appropriate logging
   - Handle errors gracefully
   - Update documentation as needed

### Pre-Commit Checks

Run code quality checks before pushing:

```bash
make check   # Run all checks without modifying code
make format  # Auto-format code with Black and isort
```

Or manually (see `docs/COMMIT_GUIDE.md` for details):

```bash
black custom_components/dessmonitor
isort custom_components/dessmonitor
flake8 custom_components/dessmonitor --max-line-length=127
mypy custom_components/dessmonitor --ignore-missing-imports
```

## 🎯 Pull Request Guidelines

### PR Titles

Use conventional commit format:
- `feat: add battery temperature sensor`
- `fix: resolve authentication timeout issue`  
- `docs: update README installation instructions`
- `refactor: improve error handling in API client`

### PR Description

Include:
- **What** was changed and **why**
- **How** to test the changes
- **Screenshots** if UI changes
- **Breaking changes** if any
- **Closes** #issue-number if applicable

### Review Process

1. **Automated checks** must pass
2. **Code review** by maintainers  
3. **Testing** in real environment
4. **Approval** and merge to target branch

## 🤝 Community Guidelines

- **Be respectful** and constructive
- **Search existing issues** before creating new ones
- **Provide detailed** bug reports and feature requests
- **Test thoroughly** before submitting PRs
- **Follow the established** patterns and conventions

### PR Target Branch

- Target `dev` for features and regular fixes (`feature/*`, `fix/*`).
- Hotfix PRs target `main` and will be forward-merged back to `dev` by maintainers.

Thank you for contributing to making DessMonitor integration better! 🎉
