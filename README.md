# CODEOWNERS Coverage

A tool to measure and enforce CODEOWNERS coverage in your repository.

## Installation

```bash
pip install codeowners-coverage
```

## Usage

### Check coverage

```bash
codeowners-coverage check
```

### Generate baseline

```bash
codeowners-coverage baseline
```

### Configuration

Create a `.codeowners-config.yml` file in your repository root:

```yaml
# Path to CODEOWNERS file
codeowners_path: ".github/CODEOWNERS"

# Path to baseline file
baseline_path: ".github/codeowners-coverage-baseline.txt"

# File patterns to exclude from coverage checking
exclusions:
  - "**/__pycache__/**"
  - "**/*.pyc"
  - "node_modules/**"
  - "dist/**"
  - ".venv/**"
```

## GitHub Actions Integration

Add a workflow to check CODEOWNERS coverage on pull requests:

```yaml
name: CODEOWNERS Coverage
on: [pull_request]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install codeowners-coverage
      - run: codeowners-coverage check
```

## Features

- **Pattern Matching**: Supports all CODEOWNERS patterns (wildcards, globstars, etc.)
- **Baseline Support**: Track progress incrementally with a baseline allowlist
- **Configurable**: Customize exclusions and paths via YAML config
- **Fast**: Uses `pathspec` library for efficient pattern matching
- **GitHub Actions Ready**: Easy integration with CI/CD pipelines

## Development

### Using just (recommended)

This project includes a `justfile` with common development commands:

```bash
# Install package in development mode
just install

# Run all tests
just test

# Run tests with coverage report
just test-cov

# Run type checking
just typecheck

# Run linting
just lint

# Run all checks (tests, typecheck, lint)
just check

# Clean build artifacts
just clean

# Build the package
just build

# Or build with uv (faster)
just build-uv

# Format code
just format

# Publish to Test PyPI
just publish-test

# Publish to production PyPI
just publish

# Full release workflow
just release
```

### Manual commands

```bash
# Install in development mode
uv pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov

# Build package
python -m build

# Publish to PyPI
twine upload dist/*
```

## License

Apache-2.0
