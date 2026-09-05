.PHONY: help lint format check test test-cov install clean

# Override to scope formatting and lint checks to changed Python files.
PYTHON_PATHS ?= custom_components/dessmonitor

# Default target
help:
	@echo "DessMonitor Development Tools"
	@echo ""
	@echo "Usage:"
	@echo "  make install    - Install development dependencies"
	@echo "  make format     - Format code with Black and isort"
	@echo "  make lint       - Run all linting checks (Black, isort, flake8, mypy)"
	@echo "  make check      - Run lint checks without modifying files"
	@echo "  make test       - Run the test suite (pytest)"
	@echo "  make test-cov   - Run the test suite with a coverage report"
	@echo "  make clean      - Clean up temporary files"
	@echo ""

# Install development dependencies
install:
	@echo "Installing development dependencies..."
	@python3 -m venv .venv || true
	@.venv/bin/pip install --upgrade pip
	@.venv/bin/pip install black isort flake8 mypy
	@echo "Installing test dependencies (Home Assistant test harness)..."
	@.venv/bin/pip install -r requirements_test.txt
	@echo "✅ Dependencies installed. Activate with: source .venv/bin/activate"

# Format code
format:
	@echo "🎨 Formatting code with Black..."
	@.venv/bin/black $(PYTHON_PATHS)
	@echo ""
	@echo "📦 Sorting imports with isort..."
	@.venv/bin/isort $(PYTHON_PATHS)
	@echo ""
	@echo "✅ Code formatted successfully!"

# Run all linting checks
lint: check

# Check code without modifying
check:
	@echo "🔍 Running code quality checks..."
	@echo ""
	@echo "=== Black (code formatting) ==="
	@.venv/bin/black --check --diff $(PYTHON_PATHS) || (echo "❌ Black formatting issues found. Run 'make format' to fix." && exit 1)
	@echo "✅ Black: PASSED"
	@echo ""
	@echo "=== isort (import sorting) ==="
	@.venv/bin/isort --check-only --diff $(PYTHON_PATHS) || (echo "❌ Import sorting issues found. Run 'make format' to fix." && exit 1)
	@echo "✅ isort: PASSED"
	@echo ""
	@echo "=== flake8 (syntax errors) ==="
	@.venv/bin/flake8 $(PYTHON_PATHS) --count --select=E9,F63,F7,F82 --show-source --statistics || (echo "❌ flake8: FAILED" && exit 1)
	@echo "✅ flake8 (critical): PASSED"
	@echo ""
	@echo "=== flake8 (code quality) ==="
	@.venv/bin/flake8 $(PYTHON_PATHS) --count --max-complexity=10 --max-line-length=127 --statistics --exit-zero
	@echo "✅ flake8 (quality): PASSED (warnings allowed)"
	@echo ""
	@echo "=== mypy (type checking) ==="
	@.venv/bin/mypy $(PYTHON_PATHS) --ignore-missing-imports || echo "⚠️  mypy: Completed with warnings"
	@echo ""
	@echo "🎉 All critical checks passed!"

# Run tests
test:
	@echo "🧪 Running tests..."
	@.venv/bin/pytest
	@echo ""
	@echo "✅ Tests passed!"

# Run tests with a coverage report for the integration
test-cov:
	@echo "🧪 Running tests with coverage..."
	@.venv/bin/pytest --cov=custom_components/dessmonitor --cov-report=term-missing
	@echo ""

# Clean temporary files
clean:
	@echo "🧹 Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf build dist .coverage htmlcov 2>/dev/null || true
	@echo "✅ Cleanup complete!"
