"""Tests for Ollama LLM matcher functionality."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from codeowners_coverage.ollama_matcher import OllamaLLMMatcher


@pytest.fixture
def mock_ollama() -> None:
    """Mock Ollama availability check."""
    with patch("ollama.list", return_value=[]):
        yield


def test_filter_relevant_teams(mock_ollama: None) -> None:
    """Test filtering relevant teams from contributor mapping."""
    matcher = OllamaLLMMatcher()

    contributor_teams = {
        "alice@example.com": ["@frontend-team", "@platform-team"],
        "bob@example.com": ["@frontend-team"],
    }

    common, other = matcher._filter_relevant_teams(contributor_teams)

    assert "@frontend-team" in common
    assert "@platform-team" in other


def test_filter_relevant_teams_empty(mock_ollama: None) -> None:
    """Test filtering with empty contributor teams."""
    matcher = OllamaLLMMatcher()

    common, other = matcher._filter_relevant_teams({})

    assert common == []
    assert other == []


def test_parse_response_valid_json(mock_ollama: None) -> None:
    """Test parsing valid JSON response."""
    matcher = OllamaLLMMatcher()

    response = (
        '{"team": "@frontend-team", "pattern": "src/**", '
        '"confidence": 0.95, "reasoning": "Clear frontend file"}'
    )
    suggestion = matcher._parse_response("src/file.tsx", response)

    assert suggestion.filepath == "src/file.tsx"
    assert suggestion.team == "@frontend-team"
    assert suggestion.confidence == 0.95
    assert suggestion.reasoning == "Clear frontend file"
    assert suggestion.suggested_pattern == "src/**"


def test_parse_response_with_markdown(mock_ollama: None) -> None:
    """Test parsing JSON wrapped in markdown code blocks."""
    matcher = OllamaLLMMatcher()

    response = '```json\n{"team": "@backend-team", "confidence": 0.8, "reasoning": "API file"}\n```'
    suggestion = matcher._parse_response("src/api.py", response)

    assert suggestion.team == "@backend-team"
    assert suggestion.confidence == 0.8


def test_parse_response_invalid_json(mock_ollama: None) -> None:
    """Test handling of invalid JSON response."""
    matcher = OllamaLLMMatcher()

    response = "This is not JSON"
    suggestion = matcher._parse_response("src/file.py", response)

    assert suggestion.team == "@unknown"
    assert suggestion.confidence == 0.0
    assert "Failed to parse" in suggestion.reasoning


def test_match_file_to_team(mock_ollama: None) -> None:
    """Test file to team matching."""
    matcher = OllamaLLMMatcher()

    mock_response = {
        "message": {
            "content": '{"team": "@frontend-team", "confidence": 0.9, "reasoning": "Frontend component"}'
        }
    }

    with patch("ollama.chat", return_value=mock_response):
        suggestion = matcher.match_file_to_team(
            filepath="src/components/Button.tsx",
            contributors=[("alice@example.com", 5)],
            contributor_teams={"alice@example.com": ["@frontend-team"]},
            existing_patterns=None,
        )

    assert suggestion.filepath == "src/components/Button.tsx"
    assert suggestion.team == "@frontend-team"
    assert suggestion.confidence == 0.9


def test_parse_response_extracts_suggested_pattern(mock_ollama: None) -> None:
    """Test that suggested_pattern is extracted from the LLM response."""
    matcher = OllamaLLMMatcher()

    response = (
        '{"team": "@backend-team", "pattern": "src/api/**", '
        '"confidence": 0.8, "reasoning": "API endpoint"}'
    )
    suggestion = matcher._parse_response("src/api/v1/users.py", response)

    assert suggestion.suggested_pattern == "src/api/**"


def test_parse_response_missing_pattern_field(mock_ollama: None) -> None:
    """suggested_pattern is None when the LLM omits it."""
    matcher = OllamaLLMMatcher()

    response = '{"team": "@team-a", "confidence": 0.9, "reasoning": "ok"}'
    suggestion = matcher._parse_response("src/file.py", response)

    assert suggestion.suggested_pattern is None


def test_parse_response_allowlist_valid(mock_ollama: None) -> None:
    """Team in allowlist passes validation."""
    matcher = OllamaLLMMatcher()

    response = '{"team": "@frontend-team", "confidence": 0.9, "reasoning": "ok"}'
    suggestion = matcher._parse_response(
        "src/file.tsx", response, allowed_teams=["@frontend-team", "@backend-team"]
    )

    assert suggestion.team == "@frontend-team"
    assert suggestion.confidence == 0.9


def test_parse_response_allowlist_rejects_invalid(mock_ollama: None) -> None:
    """Team not in allowlist gets rejected to @unknown with 0 confidence."""
    matcher = OllamaLLMMatcher()

    response = '{"team": "@invented-team", "confidence": 0.9, "reasoning": "ok"}'
    suggestion = matcher._parse_response(
        "src/file.tsx", response, allowed_teams=["@frontend-team", "@backend-team"]
    )

    assert suggestion.team == "@unknown"
    assert suggestion.confidence == 0.0
    assert "@invented-team" in suggestion.reasoning
    assert "not in the team allowlist" in suggestion.reasoning


def test_parse_response_allowlist_fuzzy_org_prefix(mock_ollama: None) -> None:
    """LLM outputting @team-name should match @org/team-name in allowlist."""
    matcher = OllamaLLMMatcher()

    response = '{"team": "@team-frontend", "confidence": 0.9, "reasoning": "ok"}'
    suggestion = matcher._parse_response(
        "src/file.tsx", response,
        allowed_teams=["@getsentry/team-frontend", "@getsentry/team-backend"],
    )

    assert suggestion.team == "@getsentry/team-frontend"
    assert suggestion.confidence == 0.9


def test_parse_response_allowlist_fuzzy_reverse(mock_ollama: None) -> None:
    """LLM outputting @org/team should match @team in allowlist."""
    matcher = OllamaLLMMatcher()

    response = '{"team": "@getsentry/team-frontend", "confidence": 0.85, "reasoning": "ok"}'
    suggestion = matcher._parse_response(
        "src/file.tsx", response,
        allowed_teams=["@team-frontend", "@team-backend"],
    )

    assert suggestion.team == "@team-frontend"
    assert suggestion.confidence == 0.85


def test_parse_response_allowlist_case_insensitive(mock_ollama: None) -> None:
    """Team matching should be case-insensitive."""
    matcher = OllamaLLMMatcher()

    response = '{"team": "@Team-Frontend", "confidence": 0.9, "reasoning": "ok"}'
    suggestion = matcher._parse_response(
        "src/file.tsx", response,
        allowed_teams=["@getsentry/team-frontend"],
    )

    assert suggestion.team == "@getsentry/team-frontend"
    assert suggestion.confidence == 0.9


def test_parse_response_no_allowlist_allows_anything(mock_ollama: None) -> None:
    """Without an allowlist, any team is accepted."""
    matcher = OllamaLLMMatcher()

    response = '{"team": "@any-team", "confidence": 0.9, "reasoning": "ok"}'
    suggestion = matcher._parse_response("src/file.py", response, allowed_teams=None)

    assert suggestion.team == "@any-team"
    assert suggestion.confidence == 0.9


def test_build_prompt(mock_ollama: None) -> None:
    """Test prompt building."""
    matcher = OllamaLLMMatcher()

    contributors = [("alice@example.com", 10), ("bob@example.com", 5)]
    contributor_teams = {
        "alice@example.com": ["@frontend-team"],
        "bob@example.com": ["@frontend-team"],
    }

    prompt = matcher._build_prompt(
        filepath="src/file.tsx",
        contributors=contributors,
        contributor_teams=contributor_teams,
        existing_patterns=None,
    )

    assert "src/file.tsx" in prompt
    assert "alice@example.com" in prompt
    assert "10 commits" in prompt
    assert "@frontend-team" in prompt


def test_build_prompt_includes_allowlist(mock_ollama: None) -> None:
    """Prompt should include team allowlist when provided."""
    matcher = OllamaLLMMatcher()

    prompt = matcher._build_prompt(
        filepath="src/file.tsx",
        contributors=[],
        contributor_teams={},
        existing_patterns=None,
        allowed_teams=["@team-a", "@team-b", "@team-c"],
    )

    assert "MUST choose from ONLY these teams" in prompt
    assert "@team-a" in prompt
    assert "@team-b" in prompt
    assert "@team-c" in prompt


def test_build_prompt_no_allowlist(mock_ollama: None) -> None:
    """Prompt should not mention allowlist when None."""
    matcher = OllamaLLMMatcher()

    prompt = matcher._build_prompt(
        filepath="src/file.tsx",
        contributors=[],
        contributor_teams={},
        existing_patterns=None,
        allowed_teams=None,
    )

    assert "MUST choose" not in prompt


def test_build_prompt_includes_pattern_instructions(mock_ollama: None) -> None:
    """Prompt should ask for directory-level patterns."""
    matcher = OllamaLLMMatcher()

    prompt = matcher._build_prompt(
        filepath="src/components/button.tsx",
        contributors=[],
        contributor_teams={},
        existing_patterns=None,
    )

    assert '"pattern"' in prompt
    assert "directory-level patterns" in prompt


def test_match_file_passes_allowlist(mock_ollama: None) -> None:
    """match_file_to_team should pass allowed_teams through to the prompt and parse."""
    matcher = OllamaLLMMatcher()

    mock_response = {
        "message": {
            "content": (
                '{"team": "@frontend-team", "pattern": "src/components/**", '
                '"confidence": 0.9, "reasoning": "Frontend component"}'
            )
        }
    }

    with patch("ollama.chat", return_value=mock_response):
        suggestion = matcher.match_file_to_team(
            filepath="src/components/Button.tsx",
            contributors=[("alice@example.com", 5)],
            contributor_teams={"alice@example.com": ["@frontend-team"]},
            existing_patterns=None,
            allowed_teams=["@frontend-team", "@backend-team"],
        )

    assert suggestion.team == "@frontend-team"
    assert suggestion.suggested_pattern == "src/components/**"
