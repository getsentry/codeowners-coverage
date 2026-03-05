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

    response = '{"team": "@frontend-team", "confidence": 0.95, "reasoning": "Clear frontend file"}'
    suggestion = matcher._parse_response("src/file.tsx", response)

    assert suggestion.filepath == "src/file.tsx"
    assert suggestion.team == "@frontend-team"
    assert suggestion.confidence == 0.95
    assert suggestion.reasoning == "Clear frontend file"


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
