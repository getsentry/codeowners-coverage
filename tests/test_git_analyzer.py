"""Tests for git history analysis functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from codeowners_coverage.git_analyzer import GitHistoryAnalyzer


def test_get_file_contributors_success() -> None:
    """Test successful extraction of file contributors."""
    analyzer = GitHistoryAnalyzer(lookback_commits=100)

    mock_result = MagicMock()
    mock_result.stdout = "alice@example.com\nalice@example.com\nbob@example.com\n"

    with patch("subprocess.run", return_value=mock_result):
        contributors = analyzer.get_file_contributors("src/file.py")

    assert len(contributors) == 2
    assert contributors[0] == ("alice@example.com", 2)
    assert contributors[1] == ("bob@example.com", 1)


def test_get_file_contributors_no_history() -> None:
    """Test file with no git history."""
    analyzer = GitHistoryAnalyzer()

    mock_result = MagicMock()
    mock_result.stdout = ""

    with patch("subprocess.run", return_value=mock_result):
        contributors = analyzer.get_file_contributors("src/file.py")

    assert contributors == []


def test_get_file_contributors_git_error() -> None:
    """Test handling of git command failure."""
    analyzer = GitHistoryAnalyzer()

    with patch("subprocess.run", side_effect=Exception("git not found")):
        contributors = analyzer.get_file_contributors("src/file.py")

    assert contributors == []


def test_get_bulk_contributors() -> None:
    """Test bulk contributor extraction."""
    analyzer = GitHistoryAnalyzer()

    # Mock get_file_contributors
    def mock_get_contributors(filepath: str) -> list:
        if filepath == "file1.py":
            return [("alice@example.com", 5)]
        elif filepath == "file2.py":
            return [("bob@example.com", 3)]
        else:
            return []

    with patch.object(analyzer, "get_file_contributors", side_effect=mock_get_contributors):
        result = analyzer.get_bulk_contributors(["file1.py", "file2.py", "file3.py"])

    assert len(result) == 2
    assert result["file1.py"] == [("alice@example.com", 5)]
    assert result["file2.py"] == [("bob@example.com", 3)]
    assert "file3.py" not in result
