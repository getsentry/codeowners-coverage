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

# Bump version helper — updates pyproject.toml and __init__.py
[private]
bump part:
    #!/usr/bin/env -S uv run python3
    import re, pathlib
    pyproject = pathlib.Path("pyproject.toml")
    init = pathlib.Path("src/codeowners_coverage/__init__.py")
    match = re.search(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"', pyproject.read_text(), re.M)
    if not match:
        raise SystemExit("Could not find version in pyproject.toml")
    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
    old = f"{major}.{minor}.{patch}"
    part = "{{ part }}"
    if part == "patch":
        patch += 1
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise SystemExit(f"Unknown part: {part}")
    new = f"{major}.{minor}.{patch}"
    pyproject.write_text(re.sub(r'^(version\s*=\s*)"[^"]+"', rf'\1"{new}"', pyproject.read_text(), count=1, flags=re.M))
    init.write_text(re.sub(r'^(__version__\s*=\s*)"[^"]+"', rf'\1"{new}"', init.read_text(), count=1, flags=re.M))
    print(f"Bumped version: {old} → {new}")

# Bump version (patch): 0.1.0 → 0.1.1
bump-patch: (bump "patch")

# Bump version (minor): 0.1.0 → 0.2.0
bump-minor: (bump "minor")

# Bump version (major): 0.1.0 → 1.0.0
bump-major: (bump "major")

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
