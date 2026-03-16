"""Tests for coverage checker functionality."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from codeowners_coverage.checker import BaselineSpec, CoverageChecker
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

    assert isinstance(baseline, BaselineSpec)
    assert baseline.literals == set()
    assert baseline.glob_patterns == []


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

    assert baseline.literals == {"uncovered1.txt", "uncovered2.txt"}
    assert baseline.glob_patterns == []

    Path(temp_baseline).unlink()


def test_load_baseline_returns_baseline_spec(config: Config) -> None:
    """Test that _load_baseline returns a BaselineSpec instance."""
    checker = CoverageChecker(config)
    baseline = checker._load_baseline()

    assert isinstance(baseline, BaselineSpec)
    assert baseline.literals == {"uncovered1.txt", "uncovered2.txt"}
    assert baseline.glob_patterns == []


def test_baseline_with_glob_patterns(config: Config) -> None:
    """Test that glob patterns in baseline match files."""
    content = """# Baseline with globs
*.txt
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        temp_baseline = f.name

    config.baseline_path = temp_baseline
    checker = CoverageChecker(config)

    files = ["file1.py", "uncovered.txt", "notes.txt", "new_file.md"]

    with patch.object(checker, "get_repository_files", return_value=files):
        result = checker.check_coverage()

    assert "uncovered.txt" in result["baseline_files"]
    assert "notes.txt" in result["baseline_files"]
    assert "new_file.md" in result["uncovered_files"]
    assert "uncovered.txt" not in result["uncovered_files"]

    Path(temp_baseline).unlink()


def test_baseline_with_mixed_entries(config: Config) -> None:
    """Test baseline with both literal paths and glob patterns."""
    content = """# Mixed baseline
specific_file.cfg
legacy/**
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        temp_baseline = f.name

    config.baseline_path = temp_baseline
    checker = CoverageChecker(config)

    files = [
        "file1.py",
        "specific_file.cfg",
        "legacy/old.md",
        "legacy/deep/readme.txt",
        "new_uncovered.txt",
    ]

    with patch.object(checker, "get_repository_files", return_value=files):
        result = checker.check_coverage()

    assert "specific_file.cfg" in result["baseline_files"]
    assert "legacy/old.md" in result["baseline_files"]
    assert "legacy/deep/readme.txt" in result["baseline_files"]
    assert "new_uncovered.txt" in result["uncovered_files"]

    Path(temp_baseline).unlink()


def test_baseline_glob_no_false_positives(config: Config) -> None:
    """Test that glob patterns don't match unrelated files."""
    content = """*.txt
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        temp_baseline = f.name

    config.baseline_path = temp_baseline
    checker = CoverageChecker(config)

    baseline = checker._load_baseline()

    assert baseline.matches("notes.txt")
    assert baseline.matches("sub/dir/deep.txt")
    assert not baseline.matches("file.py")
    assert not baseline.matches("file.txt.bak")

    Path(temp_baseline).unlink()


def test_baseline_glob_directory_pattern(config: Config) -> None:
    """Test that directory glob patterns match nested files."""
    content = """docs/**
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(content)
        temp_baseline = f.name

    config.baseline_path = temp_baseline
    checker = CoverageChecker(config)

    baseline = checker._load_baseline()

    assert baseline.matches("docs/guide.md")
    assert baseline.matches("docs/api/reference.md")
    assert not baseline.matches("src/docs.py")
    assert not baseline.matches("other/file.txt")

    Path(temp_baseline).unlink()


def test_baseline_unused_entries() -> None:
    """Test get_unused_entries identifies removable literals and glob patterns."""
    import pathspec as ps

    spec = BaselineSpec(
        literals={"old.txt", "still_uncovered.txt"},
        glob_patterns=["legacy/**", "archive/*.dat"],
        glob_spec=ps.PathSpec.from_lines("gitignore", ["legacy/**", "archive/*.dat"]),
    )

    uncovered = ["still_uncovered.txt", "legacy/code.py"]

    unused = spec.get_unused_entries(uncovered)

    assert "old.txt" in unused
    assert "still_uncovered.txt" not in unused
    assert "archive/*.dat" in unused
    assert "legacy/**" not in unused


def test_baseline_spec_matches_literals_exactly() -> None:
    """Test that literal entries use exact matching, not pattern matching."""
    import pathspec as ps

    spec = BaselineSpec(
        literals={"uncovered.txt"},
        glob_patterns=[],
        glob_spec=ps.PathSpec.from_lines("gitignore", []),
    )

    assert spec.matches("uncovered.txt")
    assert not spec.matches("subdir/uncovered.txt")


def test_write_baseline_includes_glob_hint(config: Config) -> None:
    """Test that written baseline file mentions glob support."""
    checker = CoverageChecker(config)

    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        temp_baseline_path = f.name

    checker.config.baseline_path = temp_baseline_path
    checker.write_baseline(["file.txt"])

    with open(temp_baseline_path) as f:
        content = f.read()

    assert "Glob patterns" in content
    assert "docs/**" in content or "*.txt" in content

    Path(temp_baseline_path).unlink()


def test_write_baseline_preserves_active_globs(config: Config) -> None:
    """Test that write_baseline keeps glob patterns that still match uncovered files."""
    existing_content = """# Baseline
*.txt
legacy/**
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(existing_content)
        temp_baseline = f.name

    config.baseline_path = temp_baseline
    checker = CoverageChecker(config)

    checker.write_baseline(["notes.txt", "readme.txt", "legacy/old.cfg", "other.dat"])

    with open(temp_baseline) as f:
        content = f.read()

    assert "*.txt" in content
    assert "legacy/**" in content
    # notes.txt and readme.txt are covered by *.txt, should not appear as literals
    entries = [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
    assert "notes.txt" not in entries
    assert "readme.txt" not in entries
    # legacy/old.cfg is covered by legacy/**, should not appear as literal
    assert "legacy/old.cfg" not in entries
    # other.dat is NOT covered by any glob, must appear as literal
    assert "other.dat" in entries

    Path(temp_baseline).unlink()


def test_write_baseline_drops_inactive_globs(config: Config) -> None:
    """Test that write_baseline removes glob patterns that match no uncovered files."""
    existing_content = """# Baseline
*.txt
archive/**
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(existing_content)
        temp_baseline = f.name

    config.baseline_path = temp_baseline
    checker = CoverageChecker(config)

    # No archive/ files remain uncovered
    checker.write_baseline(["notes.txt", "other.dat"])

    with open(temp_baseline) as f:
        content = f.read()

    assert "*.txt" in content
    assert "archive/**" not in content
    entries = [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
    assert "other.dat" in entries

    Path(temp_baseline).unlink()


def test_write_baseline_no_existing_file(config: Config) -> None:
    """Test that write_baseline works when no baseline file exists yet."""
    import os

    temp_dir = tempfile.mkdtemp()
    new_path = os.path.join(temp_dir, "new_baseline.txt")

    config.baseline_path = new_path
    checker = CoverageChecker(config)

    checker.write_baseline(["a.txt", "b.cfg"])

    with open(new_path) as f:
        content = f.read()

    assert "a.txt" in content
    assert "b.cfg" in content

    Path(new_path).unlink()
    Path(temp_dir).rmdir()
