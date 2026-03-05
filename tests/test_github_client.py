"""Tests for GitHub API client functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codeowners_coverage.github_client import GitHubClient


def test_detect_org_from_remote_ssh() -> None:
    """Test org detection from SSH remote URL."""
    mock_result = MagicMock()
    mock_result.stdout = "git@github.com:myorg/myrepo.git\n"

    with patch("subprocess.run", return_value=mock_result):
        client = GitHubClient(token="fake_token")

    assert client.org == "myorg"


def test_detect_org_from_remote_https() -> None:
    """Test org detection from HTTPS remote URL."""
    mock_result = MagicMock()
    mock_result.stdout = "https://github.com/myorg/myrepo.git\n"

    with patch("subprocess.run", return_value=mock_result):
        client = GitHubClient(token="fake_token")

    assert client.org == "myorg"


def test_list_teams() -> None:
    """Test fetching team list."""
    mock_result = MagicMock()
    mock_result.stdout = "git@github.com:myorg/repo.git\n"

    with patch("subprocess.run", return_value=mock_result):
        client = GitHubClient(token="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"slug": "frontend-team"},
        {"slug": "backend-team"},
    ]

    with patch("requests.get", return_value=mock_response):
        teams = client.list_teams()

    assert teams == ["frontend-team", "backend-team"]


def test_list_teams_caching() -> None:
    """Test that team list is cached."""
    mock_result = MagicMock()
    mock_result.stdout = "git@github.com:myorg/repo.git\n"

    with patch("subprocess.run", return_value=mock_result):
        client = GitHubClient(token="fake_token")

    mock_response = MagicMock()
    mock_response.json.return_value = [{"slug": "team1"}]

    with patch("requests.get", return_value=mock_response) as mock_get:
        # First call
        teams1 = client.list_teams()
        # Second call should use cache
        teams2 = client.list_teams()

    assert teams1 == teams2
    assert mock_get.call_count == 1  # Only called once


def test_build_contributor_team_map() -> None:
    """Test building contributor to team mapping."""
    mock_result = MagicMock()
    mock_result.stdout = "git@github.com:myorg/repo.git\n"

    with patch("subprocess.run", return_value=mock_result):
        client = GitHubClient(token="fake_token")

    # Mock list_teams
    client._teams_list = ["frontend-team", "backend-team"]

    # Mock get_team_members
    def mock_get_members(team_slug: str) -> list:
        if team_slug == "frontend-team":
            return ["alice@example.com", "bob@example.com"]
        elif team_slug == "backend-team":
            return ["bob@example.com", "charlie@example.com"]
        return []

    with patch.object(client, "get_team_members", side_effect=mock_get_members):
        result = client.build_contributor_team_map(
            {"alice@example.com", "bob@example.com", "charlie@example.com"}
        )

    assert result["alice@example.com"] == ["@frontend-team"]
    assert set(result["bob@example.com"]) == {"@frontend-team", "@backend-team"}
    assert result["charlie@example.com"] == ["@backend-team"]


def test_missing_token() -> None:
    """Test that missing token raises error."""
    with pytest.raises(ValueError, match="GitHub Personal Access Token is required"):
        GitHubClient(token=None, org="myorg")
