"""Tests for coverage checker functionality."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from codeowners_coverage.checker import CoverageChecker
from codeowners_coverage.config import Config


@pytest.fixture
def temp_codeowners() -> Path:
    """Create a temporary CODEOWNERS file."""
    content = """*.py @python-team
*.js @js-team
docs/* @docs-team
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix="_CODEOWNERS") as f:
        f.write(content)
        return Path(f.name)


@pytest.fixture
def temp_baseline() -> Path:
    """Create a temporary baseline file."""
    content = """# Baseline
uncovered1.txt
uncovered2.txt
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix="_baseline.txt") as f:
        f.write(content)
        return Path(f.name)


@pytest.fixture
def config(temp_codeowners: Path, temp_baseline: Path) -> Config:
    """Create a test configuration."""
    return Config(
        codeowners_path=str(temp_codeowners),
        baseline_path=str(temp_baseline),
        exclusions=["*.pyc", "__pycache__/**"],
    )


def test_check_coverage_all_covered(config: Config) -> None:
    """Test coverage check when all files are covered."""
    checker = CoverageChecker(config)

    files = ["file1.py", "file2.js", "docs/guide.md"]

    with patch.object(checker, "get_repository_files", return_value=files):
        result = checker.check_coverage()

    assert result["total_files"] == 3
    assert result["covered_files"] == 3
    assert result["uncovered_files"] == []
    assert result["coverage_percentage"] == 100.0


def test_check_coverage_with_uncovered(config: Config) -> None:
    """Test coverage check with uncovered files."""
    checker = CoverageChecker(config)

    files = ["file1.py", "file2.js", "uncovered.txt"]

    with patch.object(checker, "get_repository_files", return_value=files):
        result = checker.check_coverage()

    assert result["total_files"] == 3
    assert result["covered_files"] == 2
    assert "uncovered.txt" in result["uncovered_files"]
    assert result["coverage_percentage"] == pytest.approx(66.67, rel=0.1)


def test_check_coverage_with_baseline(config: Config) -> None:
    """Test that baseline files are separated from new uncovered files."""
    checker = CoverageChecker(config)

    # Include files from baseline
    files = ["file1.py", "uncovered1.txt", "uncovered2.txt", "new_uncovered.txt"]

    with patch.object(checker, "get_repository_files", return_value=files):
        result = checker.check_coverage()

    # Baseline files should be in baseline_files
    assert "uncovered1.txt" in result["baseline_files"]
    assert "uncovered2.txt" in result["baseline_files"]

    # New uncovered files should be in uncovered_files
    assert "new_uncovered.txt" in result["uncovered_files"]
    assert "new_uncovered.txt" not in result["baseline_files"]


def test_check_coverage_with_exclusions(config: Config) -> None:
    """Test that excluded files are not counted."""
    checker = CoverageChecker(config)

    files = ["file1.py", "file2.pyc", "__pycache__/cache.py"]

    with patch.object(checker, "get_repository_files", return_value=files):
        result = checker.check_coverage()

    # Only file1.py should be counted (pyc and pycache are excluded)
    assert result["total_files"] == 1
    assert result["covered_files"] == 1


def test_check_coverage_specific_files(config: Config) -> None:
    """Test checking coverage for specific files only."""
    checker = CoverageChecker(config)

    # Check only specific files
    files = ["file1.py", "uncovered.txt"]
    result = checker.check_coverage(files=files)

    assert result["total_files"] == 2
    assert result["covered_files"] == 1
    assert "uncovered.txt" in result["uncovered_files"]


def test_generate_baseline(config: Config) -> None:
    """Test baseline generation."""
    checker = CoverageChecker(config)

    files = ["file1.py", "file2.js", "uncovered1.txt", "uncovered2.txt"]

    with patch.object(checker, "get_repository_files", return_value=files):
        baseline = checker.generate_baseline()

    # Should return sorted uncovered files
    assert baseline == ["uncovered1.txt", "uncovered2.txt"]


def test_write_baseline(config: Config) -> None:
    """Test writing baseline file."""
    checker = CoverageChecker(config)

    baseline_files = ["uncovered1.txt", "uncovered2.txt", "uncovered3.txt"]

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        temp_baseline_path = f.name

    # Update config to use temp path
    checker.config.baseline_path = temp_baseline_path

    checker.write_baseline(baseline_files)

    # Verify file was written
    with open(temp_baseline_path) as f:
        content = f.read()

    assert "uncovered1.txt" in content
    assert "uncovered2.txt" in content
    assert "uncovered3.txt" in content

    # Verify it has comments
    assert "# CODEOWNERS Coverage Baseline" in content

    Path(temp_baseline_path).unlink()


def test_load_baseline_missing_file() -> None:
    """Test loading baseline when file doesn't exist."""
    config = Config(
        codeowners_path="tests/fixtures/sample_codeowners",
        baseline_path="/nonexistent/baseline.txt",
        exclusions=[],
    )

    checker = CoverageChecker(config)
    baseline = checker._load_baseline()

    # Should return empty set
    assert baseline == set()


def test_empty_repository(config: Config) -> None:
    """Test coverage check on empty repository."""
    checker = CoverageChecker(config)

    with patch.object(checker, "get_repository_files", return_value=[]):
        result = checker.check_coverage()

    assert result["total_files"] == 0
    assert result["covered_files"] == 0
    assert result["coverage_percentage"] == 100.0


def test_baseline_with_comments(config: Config) -> None:
    """Test that baseline file comments are ignored."""
    # Create baseline with comments
    content = """# This is a comment
uncovered1.txt
# Another comment
uncovered2.txt

# Empty line above
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        temp_baseline = f.name

    config.baseline_path = temp_baseline
    checker = CoverageChecker(config)

    baseline = checker._load_baseline()

    assert baseline == {"uncovered1.txt", "uncovered2.txt"}

    Path(temp_baseline).unlink()
