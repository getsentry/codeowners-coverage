# Justfile for codeowners-coverage package

# Default recipe - show available commands
default:
    @just --list

# Install package in development mode
install:
    uv pip install -e ".[dev]"

# Run all tests
test:
    uv run pytest tests/ -v

# Run tests with coverage report
test-cov:
    uv run pytest tests/ -v --cov=src/codeowners_coverage --cov-report=term-missing --cov-report=html

# Run type checking
typecheck:
    uv run mypy src/

# Run linting
lint:
    uv run ruff check src/ tests/

# Fix linting issues automatically
lint-fix:
    uv run ruff check --fix src/ tests/

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

# Build the package using uv (faster)
build: clean
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
    uv run ruff format src/ tests/

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

# Check Ollama installation and setup
ollama-check:
    @echo "Checking Ollama installation..."
    @command -v ollama >/dev/null 2>&1 || (echo "❌ Ollama not installed. Visit https://ollama.ai/" && exit 1)
    @echo "✓ Ollama installed"
    @curl -s http://localhost:11434 >/dev/null 2>&1 || (echo "❌ Ollama not running. Start with: ollama serve" && exit 1)
    @echo "✓ Ollama running"
    @ollama list | grep -q llama3.2 || (echo "⚠️  llama3.2 not found. Pull with: ollama pull llama3.2" && exit 1)
    @echo "✓ llama3.2 model available"
    @echo "✅ Ollama ready for use"

# Setup Ollama for codeowners-coverage
ollama-setup:
    @echo "Setting up Ollama for codeowners-coverage..."
    @command -v ollama >/dev/null 2>&1 || (echo "Please install Ollama from https://ollama.ai/" && exit 1)
    @echo "Pulling llama3.2 model (this may take a few minutes)..."
    ollama pull llama3.2
    @echo "✅ Ollama setup complete"

# Run the suggest command (requires Ollama)
suggest: ollama-check
    @echo "Running CODEOWNERS suggestions..."
    codeowners-coverage suggest
