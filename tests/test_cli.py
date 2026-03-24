"""Tests for CLI functionality."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from codeowners_coverage.cli import cli


def test_check_dirty_baseline_without_flag_exits_2() -> None:
    """Test that check exits with code 2 when baseline is dirty (default behavior)."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CODEOWNERS file
        codeowners_path = Path(tmpdir) / "CODEOWNERS"
        codeowners_path.write_text("*.py @python-team\n")

        # Create baseline with an entry that now has coverage
        baseline_path = Path(tmpdir) / "baseline.txt"
        baseline_path.write_text("covered.py\n")

        # Create config
        config_path = Path(tmpdir) / ".codeowners-config.yml"
        config_path.write_text(
            f"codeowners_path: {codeowners_path}\n"
            f"baseline_path: {baseline_path}\n"
            f"exclusions: []\n"
        )

        # Mock get_repository_files to return empty (all files covered)
        with patch(
            "codeowners_coverage.checker.CoverageChecker.get_repository_files",
            return_value=["covered.py"],
        ):
            result = runner.invoke(cli, ["check", "--config", str(config_path)])

        # Should exit with code 2 (baseline can be reduced)
        assert result.exit_code == 2
        assert "baseline entries can be removed" in result.output


def test_check_dirty_baseline_with_flag_exits_0() -> None:
    """Test that check exits with code 0 when baseline is dirty but flag is set."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CODEOWNERS file
        codeowners_path = Path(tmpdir) / "CODEOWNERS"
        codeowners_path.write_text("*.py @python-team\n")

        # Create baseline with an entry that now has coverage
        baseline_path = Path(tmpdir) / "baseline.txt"
        baseline_path.write_text("covered.py\n")

        # Create config
        config_path = Path(tmpdir) / ".codeowners-config.yml"
        config_path.write_text(
            f"codeowners_path: {codeowners_path}\n"
            f"baseline_path: {baseline_path}\n"
            f"exclusions: []\n"
        )

        # Mock get_repository_files to return covered files
        with patch(
            "codeowners_coverage.checker.CoverageChecker.get_repository_files",
            return_value=["covered.py"],
        ):
            result = runner.invoke(
                cli, ["check", "--config", str(config_path), "--allow-dirty-baseline"]
            )

        # Should exit with code 0 (success despite dirty baseline)
        assert result.exit_code == 0
        assert "baseline entries can be removed" in result.output


def test_check_clean_baseline_with_flag_exits_0() -> None:
    """Test that check exits with code 0 when baseline is clean (with or without flag)."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CODEOWNERS file
        codeowners_path = Path(tmpdir) / "CODEOWNERS"
        codeowners_path.write_text("*.py @python-team\n")

        # Create empty baseline
        baseline_path = Path(tmpdir) / "baseline.txt"
        baseline_path.write_text("")

        # Create config
        config_path = Path(tmpdir) / ".codeowners-config.yml"
        config_path.write_text(
            f"codeowners_path: {codeowners_path}\n"
            f"baseline_path: {baseline_path}\n"
            f"exclusions: []\n"
        )

        # Mock get_repository_files to return covered files
        with patch(
            "codeowners_coverage.checker.CoverageChecker.get_repository_files",
            return_value=["covered.py"],
        ):
            result = runner.invoke(
                cli, ["check", "--config", str(config_path), "--allow-dirty-baseline"]
            )

        # Should exit with code 0
        assert result.exit_code == 0
        assert "baseline entries can be removed" not in result.output


def test_check_json_output_includes_unused_baseline_entries() -> None:
    """Test that JSON output includes unused_baseline_entries field."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CODEOWNERS file
        codeowners_path = Path(tmpdir) / "CODEOWNERS"
        codeowners_path.write_text("*.py @python-team\n")

        # Create baseline with entries that now have coverage
        baseline_path = Path(tmpdir) / "baseline.txt"
        baseline_path.write_text("covered1.py\ncovered2.py\n")

        # Create config
        config_path = Path(tmpdir) / ".codeowners-config.yml"
        config_path.write_text(
            f"codeowners_path: {codeowners_path}\n"
            f"baseline_path: {baseline_path}\n"
            f"exclusions: []\n"
        )

        # Mock get_repository_files to return covered files
        with patch(
            "codeowners_coverage.checker.CoverageChecker.get_repository_files",
            return_value=["covered1.py", "covered2.py"],
        ):
            result = runner.invoke(
                cli, ["check", "--config", str(config_path), "--json"]
            )

        # Parse JSON output
        output = json.loads(result.output)

        # Should include unused_baseline_entries
        assert "unused_baseline_entries" in output
        assert "covered1.py" in output["unused_baseline_entries"]
        assert "covered2.py" in output["unused_baseline_entries"]


def test_check_new_uncovered_takes_precedence_over_dirty_baseline() -> None:
    """Test that new uncovered files cause exit 1 even with --allow-dirty-baseline."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CODEOWNERS file
        codeowners_path = Path(tmpdir) / "CODEOWNERS"
        codeowners_path.write_text("*.py @python-team\n")

        # Create baseline with an entry that now has coverage
        baseline_path = Path(tmpdir) / "baseline.txt"
        baseline_path.write_text("covered.py\n")

        # Create config
        config_path = Path(tmpdir) / ".codeowners-config.yml"
        config_path.write_text(
            f"codeowners_path: {codeowners_path}\n"
            f"baseline_path: {baseline_path}\n"
            f"exclusions: []\n"
        )

        # Mock get_repository_files to return covered + new uncovered file
        with patch(
            "codeowners_coverage.checker.CoverageChecker.get_repository_files",
            return_value=["covered.py", "new_uncovered.txt"],
        ):
            result = runner.invoke(
                cli, ["check", "--config", str(config_path), "--allow-dirty-baseline"]
            )

        # Should exit with code 1 (new uncovered files)
        assert result.exit_code == 1
        assert "new_uncovered.txt" in result.output


def test_check_json_output_with_clean_baseline() -> None:
    """Test that JSON output includes empty unused_baseline_entries when baseline is clean."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CODEOWNERS file
        codeowners_path = Path(tmpdir) / "CODEOWNERS"
        codeowners_path.write_text("*.py @python-team\n")

        # Create baseline with entries still uncovered
        baseline_path = Path(tmpdir) / "baseline.txt"
        baseline_path.write_text("still_uncovered.txt\n")

        # Create config
        config_path = Path(tmpdir) / ".codeowners-config.yml"
        config_path.write_text(
            f"codeowners_path: {codeowners_path}\n"
            f"baseline_path: {baseline_path}\n"
            f"exclusions: []\n"
        )

        # Mock get_repository_files to return baseline file (still uncovered)
        with patch(
            "codeowners_coverage.checker.CoverageChecker.get_repository_files",
            return_value=["covered.py", "still_uncovered.txt"],
        ):
            result = runner.invoke(
                cli, ["check", "--config", str(config_path), "--json"]
            )

        # Parse JSON output
        output = json.loads(result.output)

        # Should include empty unused_baseline_entries
        assert "unused_baseline_entries" in output
        assert output["unused_baseline_entries"] == []
        assert result.exit_code == 0
