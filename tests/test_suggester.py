"""Tests for ownership suggester functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from codeowners_coverage.config import Config
from codeowners_coverage.directory_consolidator import (
    DirectoryConsolidator,
    Pattern,
)
from codeowners_coverage.git_analyzer import GitHistoryAnalyzer
from codeowners_coverage.ollama_matcher import (
    OllamaLLMMatcher,
    TeamSuggestion,
)
from codeowners_coverage.suggest_cache import SuggestCache
from codeowners_coverage.suggester import OwnershipSuggester


def test_suggest_for_uncovered_files_empty() -> None:
    """Test suggestion with no files."""
    config = Config()
    git_analyzer = MagicMock(spec=GitHistoryAnalyzer)
    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    consolidator = MagicMock(spec=DirectoryConsolidator)

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
    )

    result = suggester.suggest_for_uncovered_files([])

    assert result.total_files == 0
    assert result.files_with_suggestions == 0
    assert result.patterns == []


def test_suggest_for_uncovered_files_with_suggestions() -> None:
    """Test suggestion generation for files."""
    config = Config()

    # Mock git analyzer
    git_analyzer = MagicMock(spec=GitHistoryAnalyzer)
    git_analyzer.get_bulk_contributors.return_value = {
        "src/file1.py": [("alice@example.com", 10)],
        "src/file2.py": [("bob@example.com", 5)],
    }

    # Mock LLM matcher
    llm_matcher = MagicMock(spec=OllamaLLMMatcher)

    def mock_match(filepath, contributors, contributor_teams, existing_patterns):
        if filepath == "src/file1.py":
            return TeamSuggestion(
                filepath=filepath,
                team="@frontend-team",
                confidence=0.9,
                reasoning="Frontend file",
            )
        else:
            return TeamSuggestion(
                filepath=filepath,
                team="@backend-team",
                confidence=0.8,
                reasoning="Backend file",
            )

    llm_matcher.match_file_to_team.side_effect = mock_match

    # Mock consolidator
    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = [
        Pattern(pattern="src/**", teams=["@frontend-team"], file_count=2, confidence=0.85)
    ]

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
    )

    result = suggester.suggest_for_uncovered_files(["src/file1.py", "src/file2.py"])

    assert result.total_files == 2
    assert result.files_with_suggestions == 2
    assert len(result.patterns) == 1
    assert result.patterns[0].pattern == "src/**"


def test_suggest_filters_low_confidence() -> None:
    """Test that low confidence suggestions are filtered out."""
    config = Config()

    # Mock git analyzer
    git_analyzer = MagicMock(spec=GitHistoryAnalyzer)
    git_analyzer.get_bulk_contributors.return_value = {
        "src/file1.py": [("alice@example.com", 10)],
    }

    # Mock LLM matcher with low confidence
    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.return_value = TeamSuggestion(
        filepath="src/file1.py",
        team="@unknown",
        confidence=0.3,  # Low confidence
        reasoning="Unclear ownership",
    )

    # Mock consolidator
    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = []

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
    )

    result = suggester.suggest_for_uncovered_files(["src/file1.py"])

    # Should not include low confidence suggestion
    assert result.files_with_suggestions == 0


def test_suggest_skips_cached_llm_suggestions(
    tmp_path: Path,
) -> None:
    """Cached LLM suggestions should not trigger new LLM calls."""
    config = Config()
    cache_path = tmp_path / "cache.json"
    cache = SuggestCache(path=cache_path)

    # Pre-populate cache with a suggestion for file1
    cache.set_git_contributors(
        "src/file1.py", [("alice@example.com", 10)]
    )
    cache.set_llm_suggestion(
        "src/file1.py",
        TeamSuggestion(
            filepath="src/file1.py",
            team="@cached-team",
            confidence=0.95,
            reasoning="From cache",
        ),
    )
    cache.save()

    git_analyzer = MagicMock(spec=GitHistoryAnalyzer)
    git_analyzer.get_bulk_contributors.return_value = {}

    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.return_value = TeamSuggestion(
        filepath="src/file2.py",
        team="@fresh-team",
        confidence=0.8,
        reasoning="Fresh result",
    )

    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = []

    # Reload cache from disk to simulate restart
    cache = SuggestCache.load(cache_path)

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
        cache=cache,
    )

    result = suggester.suggest_for_uncovered_files(
        ["src/file1.py", "src/file2.py"]
    )

    # LLM should only be called for file2 (file1 was cached)
    assert llm_matcher.match_file_to_team.call_count == 1
    called_filepath = (
        llm_matcher.match_file_to_team.call_args[1]["filepath"]
    )
    assert called_filepath == "src/file2.py"

    # Both files should appear in suggestions
    assert "src/file1.py" in result.file_suggestions
    assert "src/file2.py" in result.file_suggestions
    assert (
        result.file_suggestions["src/file1.py"].team
        == "@cached-team"
    )
    assert (
        result.file_suggestions["src/file2.py"].team
        == "@fresh-team"
    )


def test_suggest_skips_cached_git_contributors(
    tmp_path: Path,
) -> None:
    """Cached git contributors should not trigger new git calls."""
    config = Config()
    cache_path = tmp_path / "cache.json"
    cache = SuggestCache(path=cache_path)

    # Pre-populate git cache for file1
    cache.set_git_contributors(
        "src/file1.py", [("alice@example.com", 10)]
    )
    cache.save()
    cache = SuggestCache.load(cache_path)

    git_analyzer = MagicMock(spec=GitHistoryAnalyzer)
    # Only file2 should be fetched from git
    git_analyzer.get_bulk_contributors.return_value = {
        "src/file2.py": [("bob@example.com", 5)]
    }

    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.return_value = TeamSuggestion(
        filepath="",
        team="@team",
        confidence=0.7,
        reasoning="r",
    )

    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = []

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
        cache=cache,
    )

    suggester.suggest_for_uncovered_files(
        ["src/file1.py", "src/file2.py"]
    )

    # get_bulk_contributors should only be called with file2
    git_analyzer.get_bulk_contributors.assert_called_once_with(
        ["src/file2.py"]
    )


def test_suggest_without_cache_works(
) -> None:
    """Suggester should work fine with cache=None."""
    config = Config()

    git_analyzer = MagicMock(spec=GitHistoryAnalyzer)
    git_analyzer.get_bulk_contributors.return_value = {
        "a.py": [("x@y.com", 1)]
    }

    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.return_value = TeamSuggestion(
        filepath="a.py",
        team="@team",
        confidence=0.9,
        reasoning="r",
    )

    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = []

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
        cache=None,
    )

    result = suggester.suggest_for_uncovered_files(["a.py"])
    assert result.total_files == 1
    assert result.files_with_suggestions == 1


def test_suggest_cache_persists_after_each_llm_call(
    tmp_path: Path,
) -> None:
    """Cache should be flushed to disk after each LLM call."""
    config = Config()
    cache_path = tmp_path / "cache.json"
    cache = SuggestCache(path=cache_path)

    git_analyzer = MagicMock(spec=GitHistoryAnalyzer)
    git_analyzer.get_bulk_contributors.return_value = {
        "a.py": [("x@y.com", 1)],
        "b.py": [("x@y.com", 1)],
    }

    call_count = 0

    def mock_match(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        # After the first LLM call, the cache file should exist
        if call_count == 2:
            assert cache_path.exists()
            reloaded = SuggestCache.load(cache_path)
            assert len(reloaded.llm_suggestions) == 1
        return TeamSuggestion(
            filepath=kwargs["filepath"],
            team="@team",
            confidence=0.9,
            reasoning="r",
        )

    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.side_effect = mock_match

    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = []

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
        cache=cache,
    )

    suggester.suggest_for_uncovered_files(["a.py", "b.py"])

    # After completion, both should be in cache on disk
    final = SuggestCache.load(cache_path)
    assert len(final.llm_suggestions) == 2
