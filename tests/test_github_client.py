"""Tests for GitHub API client functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from codeowners_coverage.github_client import GitHubClient, TeamValidationError


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


def _make_client() -> GitHubClient:
    """Create a GitHubClient with a mocked git remote."""
    mock_result = MagicMock()
    mock_result.stdout = "git@github.com:myorg/repo.git\n"
    with patch("subprocess.run", return_value=mock_result):
        return GitHubClient(token="fake_token")


def _mock_teams_list_response(slugs: list[str]) -> MagicMock:
    """Build a mock response for the org teams list endpoint."""
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = [{"slug": s} for s in slugs]
    return response


def _mock_team_members_response(members: list[dict]) -> MagicMock:
    """Build a mock response for GET .../teams/{slug}/members."""
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = members
    return response


def test_validate_teams_all_valid() -> None:
    """Test validate_teams when all teams exist and have members."""
    client = _make_client()

    with patch(
        "requests.get",
        side_effect=[
            _mock_teams_list_response(["backend"]),
            _mock_team_members_response([{"login": "alice"}]),
        ],
    ):
        errors = client.validate_teams({"@myorg/backend": [5]})

    assert errors == []


def test_validate_teams_missing_team() -> None:
    """Test validate_teams when a team is not in the org."""
    client = _make_client()

    with patch("requests.get", return_value=_mock_teams_list_response(["other-team"])):
        errors = client.validate_teams({"@myorg/ghost-team": [42]})

    assert len(errors) == 1
    assert errors[0].team == "@myorg/ghost-team"
    assert errors[0].line_numbers == [42]
    assert "not found" in errors[0].reason


def test_validate_teams_skips_individual_users() -> None:
    """Test that @username entries (no slash) are not validated via API."""
    client = _make_client()

    with patch("requests.get") as mock_get:
        errors = client.validate_teams({"@jsmith": [3], "@alice": [7]})

    assert errors == []
    mock_get.assert_not_called()


def test_validate_teams_multiple_errors() -> None:
    """Test validate_teams with a mix of valid and invalid teams."""
    client = _make_client()

    with patch(
        "requests.get",
        side_effect=[
            _mock_teams_list_response(["good-team"]),
            _mock_team_members_response([{"login": "alice"}]),
        ],
    ):
        errors = client.validate_teams({
            "@myorg/good-team": [1],
            "@myorg/bad-team": [53],
        })

    assert len(errors) == 1
    assert errors[0].team == "@myorg/bad-team"


def test_validate_teams_empty_team() -> None:
    """Test validate_teams when a team exists but has no members."""
    client = _make_client()

    with patch(
        "requests.get",
        side_effect=[
            _mock_teams_list_response(["empty-team"]),
            _mock_team_members_response([]),
        ],
    ):
        errors = client.validate_teams({"@myorg/empty-team": [10]})

    assert len(errors) == 1
    assert errors[0].team == "@myorg/empty-team"
    assert "no members" in errors[0].reason


def test_validate_teams_pagination() -> None:
    """Test that validate_teams fetches all pages."""
    client = _make_client()

    # First page: full (100 teams)
    page1 = MagicMock()
    page1.status_code = 200
    page1.raise_for_status = MagicMock()
    page1.json.return_value = [{"slug": f"team-{i}"} for i in range(100)]

    # Second page: partial (signals last page)
    page2 = MagicMock()
    page2.status_code = 200
    page2.raise_for_status = MagicMock()
    page2.json.return_value = [{"slug": "my-team"}]

    with patch(
        "requests.get",
        side_effect=[
            page1,
            page2,
            _mock_team_members_response([{"login": "someone"}]),
        ],
    ):
        errors = client.validate_teams({"@myorg/my-team": [1]})

    assert errors == []
