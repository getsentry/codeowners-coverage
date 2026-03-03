# Justfile for codeowners-coverage package

# Default recipe - show available commands
default:
    @just --list

# Install package in development mode
install:
    uv pip install -e ".[dev]"

# Run all tests
test:
    pytest tests/ -v

# Run tests with coverage report
test-cov:
    pytest tests/ -v --cov=src/codeowners_coverage --cov-report=term-missing --cov-report=html

# Run type checking
typecheck:
    mypy src/

# Run linting
lint:
    ruff check src/ tests/

# Fix linting issues automatically
lint-fix:
    ruff check --fix src/ tests/

# Run all checks (tests, typecheck, lint)
check: test typecheck lint

# Clean build artifacts
clean:
    rm -rf dist/
    rm -rf build/
    rm -rf *.egg-info
    rm -rf .pytest_cache
    rm -rf .mypy_cache
    rm -rf htmlcov
    rm -rf .coverage
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Build the package
build: clean
    python -m build

# Build the package using uv (faster)
build-uv: clean
    uv build

# Publish to Test PyPI
publish-test: build
    @echo "Publishing to Test PyPI..."
    twine upload --repository testpypi dist/*

# Publish to production PyPI
publish: build
    @echo "Publishing to PyPI..."
    @echo "Are you sure? This will publish version $(grep '^version' pyproject.toml | cut -d'"' -f2) to production PyPI."
    @echo "Press Ctrl+C to cancel, or Enter to continue..."
    @read _
    twine upload dist/*

# Install from Test PyPI (for testing)
install-test:
    pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ codeowners-coverage

# Bump version (patch)
bump-patch:
    @echo "Current version: $(grep '^version' pyproject.toml | cut -d'"' -f2)"
    @echo "Bumping patch version..."
    # This is a placeholder - consider using bump2version or similar tool

# Bump version (minor)
bump-minor:
    @echo "Current version: $(grep '^version' pyproject.toml | cut -d'"' -f2)"
    @echo "Bumping minor version..."
    # This is a placeholder - consider using bump2version or similar tool

# Bump version (major)
bump-major:
    @echo "Current version: $(grep '^version' pyproject.toml | cut -d'"' -f2)"
    @echo "Bumping major version..."
    # This is a placeholder - consider using bump2version or similar tool

# Format code
format:
    ruff format src/ tests/

# Run the CLI locally (check command)
run-check:
    codeowners-coverage check

# Run the CLI locally (baseline command)
run-baseline:
    codeowners-coverage baseline

# Install build tools
install-tools:
    pip install build twine

# Full release workflow (test, build, publish)
release: check build publish
    @echo "✅ Package published successfully!"

# Test release workflow (test, build, publish to test PyPI)
release-test: check build publish-test
    @echo "✅ Package published to Test PyPI successfully!"
