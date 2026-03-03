# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`codeowners-coverage` is a Python CLI tool that measures and enforces CODEOWNERS coverage in Git repositories. It ensures all files have designated owners by checking files against CODEOWNERS patterns and supports incremental improvement through baseline tracking.

## Development Commands

### Using just (recommended)
```bash
just install          # Install package in development mode with uv
just test            # Run all tests with pytest
just test-cov        # Run tests with coverage report
just typecheck       # Run mypy type checking
just lint            # Run ruff linting
just lint-fix        # Auto-fix linting issues
just format          # Format code with ruff
just check           # Run all checks (test + typecheck + lint)
just build           # Build package with python -m build
just build-uv        # Build package with uv (faster)
just clean           # Remove all build artifacts
```

### Manual commands
```bash
# Development setup
uv pip install -e ".[dev]"

# Testing
pytest tests/ -v                                              # Run tests
pytest tests/ -v --cov=src/codeowners_coverage --cov-report=term-missing  # With coverage
pytest tests/test_specific.py::test_function -v              # Run specific test

# Quality checks
mypy src/                                   # Type checking
ruff check src/ tests/                      # Linting
ruff check --fix src/ tests/                # Auto-fix linting
ruff format src/ tests/                     # Format code

# CLI usage
codeowners-coverage check                   # Check coverage (fails on new uncovered files)
codeowners-coverage baseline                # Generate/update baseline file
```

## Architecture

### Core Components

1. **CLI Layer** (`cli.py`): Click-based command interface with two main commands:
   - `check`: Validates coverage, distinguishes between baseline vs new uncovered files
   - `baseline`: Generates snapshot of current uncovered files for incremental improvement

2. **Configuration** (`config.py`): YAML-based config with defaults
   - Defines CODEOWNERS path, baseline path, and exclusion patterns
   - Provides sensible defaults for Python and JavaScript build artifacts

3. **Pattern Matching** (`matcher.py`): Wraps `pathspec` library
   - Parses CODEOWNERS file to extract patterns (ignores owner assignments)
   - Uses gitignore-style pattern matching for compatibility

4. **Coverage Checking** (`checker.py`): Core business logic
   - Uses `git ls-files` to enumerate repository files
   - Filters files through exclusion patterns and CODEOWNERS patterns
   - Separates uncovered files into "baseline" (allowed) and "new" (blocking)

### Data Flow

```
git ls-files → exclusion filter → coverage check → baseline comparison → result
                                        ↓
                                CODEOWNERS patterns (pathspec)
```

### Exit Codes
- 0: All files covered (or only baseline files uncovered)
- 1: New uncovered files found (blocks CI)
- 2: Baseline can be reduced (files now covered, suggests running `baseline` command)

## Testing

The test suite uses pytest with coverage tracking. Tests are organized by module:
- `test_config.py`: Configuration loading and defaults
- `test_matcher.py`: CODEOWNERS pattern matching logic
- `test_checker.py`: Coverage checking and baseline management

Tests run against Python 3.9, 3.10, 3.11, and 3.12 in CI.

## Key Constraints

- **Git dependency**: Uses `git ls-files` to enumerate repository files (requires Git repository)
- **Pattern matching**: Relies on `pathspec` library for gitignore-style pattern matching
- **CODEOWNERS format**: Expects standard GitHub CODEOWNERS format: `pattern @owner1 @owner2`
- **Baseline format**: Plain text file with one filepath per line (supports comments starting with #)
