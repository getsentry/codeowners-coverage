# CODEOWNERS Coverage

A tool to measure and enforce CODEOWNERS coverage in your repository.

## Prerequisites

- Python 3.9+
- Git repository
- **Ollama** (for `suggest` command) - [Install from ollama.ai](https://ollama.ai/)

### Ollama Setup (Optional - for AI-powered suggestions)

The `suggest` command uses a local LLM (Ollama) to intelligently match files to teams based on git history.

1. Install Ollama: https://ollama.ai/
2. Pull the default model:
   ```bash
   ollama pull llama3.2
   ```
3. Ensure Ollama is running:
   ```bash
   ollama serve  # Runs on http://localhost:11434
   ```
4. Verify setup:
   ```bash
   just ollama-check
   # or manually:
   curl http://localhost:11434
   ```

**Quick setup:**
```bash
just ollama-setup  # Downloads and configures Ollama model
```

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

### Suggest CODEOWNERS entries (AI-powered)

Use local LLM to intelligently suggest team ownership based on git history.

**GitHub Token Setup:**

1. Create a Personal Access Token at https://github.com/settings/tokens
2. Choose either:
   - **Classic Token**: Select `read:org` scope
   - **Fine-grained Token**: Grant "Read-only" access to "Organization permissions > Members"
3. Export the token:
   ```bash
   export GITHUB_TOKEN=ghp_your_token_here
   ```

**Usage:**

```bash
# Basic usage (requires GITHUB_TOKEN env var)
# By default, includes both new uncovered files AND baseline files
export GITHUB_TOKEN=ghp_xxxxx
codeowners-coverage suggest

# Or with justfile
just suggest

# Only suggest for new uncovered files (exclude baseline)
codeowners-coverage suggest --no-baseline

# Auto-apply suggestions (creates backup)
codeowners-coverage suggest --apply

# Export as diff for review
codeowners-coverage suggest --format=diff > suggestions.patch

# Configure Ollama model
codeowners-coverage suggest --ollama-model llama3.2

# Adjust directory consolidation threshold
codeowners-coverage suggest --min-coverage 0.9  # 90% consistency required
```

**How it works:**
1. Finds all uncovered files (both new and baseline by default)
2. Analyzes git history to find contributors per file
3. Fetches GitHub teams and maps contributors to teams
4. Uses local LLM to intelligently suggest ownership
5. Consolidates to high-level directory patterns when appropriate

**Requirements:**
- Ollama running locally (setup: `just ollama-setup`)
- GitHub Personal Access Token (set via `GITHUB_TOKEN` env var)
  - Token type: Classic PAT or Fine-grained PAT
  - Required scope: `read:org` (to read organization teams and members)
  - Token holder must be a member of the organization
  - Create at: https://github.com/settings/tokens
- Git repository with commit history

**Note:** By default, suggestions include both new uncovered files AND baseline files. Use `--no-baseline` to only suggest for new uncovered files.

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

# Suggestion settings (for 'suggest' command)
github_token: ${GITHUB_TOKEN}  # GitHub Personal Access Token (needs read:org scope)
github_org: mycompany  # Auto-detected from git remote if omitted
ollama_model: llama3.2  # Ollama model to use
ollama_base_url: http://localhost:11434  # Ollama API endpoint
suggestion_min_coverage: 0.8  # Min % for directory consolidation
suggestion_lookback_commits: 100  # How far back to analyze git history
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
- **AI-Powered Suggestions**: Use local LLM (Ollama) to intelligently suggest CODEOWNERS entries based on git history and team membership
- **Smart Consolidation**: Automatically groups file-level suggestions into high-level directory patterns
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

# Check Ollama setup
just ollama-check

# Setup Ollama (downloads model)
just ollama-setup

# Run suggest command
just suggest

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
