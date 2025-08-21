# Commit Guide

## Pre-Commit Checks

1. **Review changes**
   ```bash
   git status
   git diff
   git diff --staged
   ```

2. **Run code quality**
   ```bash
   black custom_components/dessmonitor
   isort custom_components/dessmonitor
   flake8 custom_components/dessmonitor --max-line-length=127
   ```

## Commit Process

3. **Stage files**
   ```bash
   git add <specific_files>
   # or
   git add -p  # interactive staging
   ```

4. **Create commit**
   ```bash
   git commit -m "<type>: <description>"
   ```

## Commit Message Format

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code formatting (black, isort)
- `refactor`: Code restructuring
- `test`: Test additions/changes
- `chore`: Build, config, dependencies

**Examples:**
- `feat: add battery temperature sensor`
- `fix: handle API timeout errors`
- `docs: update installation steps`
- `refactor: simplify sensor creation logic`
- `chore: bump version to 1.2.0`

## Rules
- Use imperative mood ("add" not "added")
- No period at end
- No AI/Claude references
- No emoji unless codebase uses them

## Multi-line Format (when needed)
```bash
git commit -m "type: short summary" -m "
- Detail 1
- Detail 2
- Fixes #123"
```