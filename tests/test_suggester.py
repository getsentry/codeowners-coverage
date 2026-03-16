"""Tests for ownership suggester functionality."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
from unittest.mock import MagicMock

from codeowners_coverage.config import Config
from codeowners_coverage.directory_consolidator import (
    DirectoryConsolidator,
    FileOwnership,
    Pattern,
)
from codeowners_coverage.git_analyzer import GitHistoryAnalyzer
from codeowners_coverage.ollama_matcher import (
    OllamaLLMMatcher,
    TeamSuggestion,
)
from codeowners_coverage.suggest_cache import SuggestCache
from codeowners_coverage.suggester import OwnershipSuggester


def _mock_git_analyzer(
    mapping: dict[str, List[Tuple[str, int]]],
) -> MagicMock:
    """Build a git analyzer mock that returns per-file contributors."""
    analyzer = MagicMock(spec=GitHistoryAnalyzer)
    analyzer.get_file_contributors.side_effect = (
        lambda fp: mapping.get(fp, [])
    )
    return analyzer


def test_suggest_for_uncovered_files_empty() -> None:
    """Test suggestion with no files."""
    config = Config()
    git_analyzer = _mock_git_analyzer({})
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

    git_analyzer = _mock_git_analyzer({
        "src/file1.py": [("alice@example.com", 10)],
        "src/file2.py": [("bob@example.com", 5)],
    })

    llm_matcher = MagicMock(spec=OllamaLLMMatcher)

    def mock_match(
        filepath, contributors, contributor_teams,
        existing_patterns, allowed_teams=None,
    ):
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

    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = [
        Pattern(
            pattern="src/**",
            teams=["@frontend-team"],
            file_count=2,
            confidence=0.85,
        )
    ]

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
    )

    result = suggester.suggest_for_uncovered_files(
        ["src/file1.py", "src/file2.py"]
    )

    assert result.total_files == 2
    assert result.files_with_suggestions == 2
    assert len(result.patterns) == 1
    assert result.patterns[0].pattern == "src/**"


def test_suggest_filters_low_confidence() -> None:
    """Test that low confidence suggestions are filtered out."""
    config = Config()

    git_analyzer = _mock_git_analyzer({
        "src/file1.py": [("alice@example.com", 10)],
    })

    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.return_value = TeamSuggestion(
        filepath="src/file1.py",
        team="@unknown",
        confidence=0.3,
        reasoning="Unclear ownership",
    )

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

    assert result.files_with_suggestions == 0


def test_suggest_skips_cached_llm_suggestions(
    tmp_path: Path,
) -> None:
    """Cached LLM suggestions should not trigger new LLM calls."""
    config = Config()
    cache_path = tmp_path / "cache.json"
    cache = SuggestCache(path=cache_path)

    cache.set_git_contributors(
        "src/file1.py", [("alice@example.com", 10)]
    )
    cache.set_git_contributors("src/file2.py", [])
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

    git_analyzer = _mock_git_analyzer({})
    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.return_value = TeamSuggestion(
        filepath="src/file2.py",
        team="@fresh-team",
        confidence=0.8,
        reasoning="Fresh result",
    )

    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = []

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

    assert llm_matcher.match_file_to_team.call_count == 1
    called_filepath = (
        llm_matcher.match_file_to_team.call_args[1]["filepath"]
    )
    assert called_filepath == "src/file2.py"

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

    cache.set_git_contributors(
        "src/file1.py", [("alice@example.com", 10)]
    )
    cache.save()
    cache = SuggestCache.load(cache_path)

    git_analyzer = _mock_git_analyzer({
        "src/file2.py": [("bob@example.com", 5)],
    })

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

    # get_file_contributors should only be called for file2
    assert git_analyzer.get_file_contributors.call_count == 1
    git_analyzer.get_file_contributors.assert_called_once_with(
        "src/file2.py"
    )


def test_suggest_without_cache_works() -> None:
    """Suggester should work fine with cache=None."""
    config = Config()

    git_analyzer = _mock_git_analyzer({
        "a.py": [("x@y.com", 1)],
    })

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

    git_analyzer = _mock_git_analyzer({
        "a.py": [("x@y.com", 1)],
        "b.py": [("x@y.com", 1)],
    })

    call_count = 0

    def mock_match(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
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

    final = SuggestCache.load(cache_path)
    assert len(final.llm_suggestions) == 2


def test_suggest_uses_config_allowlist() -> None:
    """When config has team_allowlist, it should be passed to the LLM."""
    config = Config(team_allowlist=["@team-a", "@team-b"])

    git_analyzer = _mock_git_analyzer({
        "src/file1.py": [("alice@example.com", 10)],
    })

    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.return_value = TeamSuggestion(
        filepath="src/file1.py",
        team="@team-a",
        confidence=0.9,
        reasoning="ok",
    )

    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = []

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
    )

    suggester.suggest_for_uncovered_files(["src/file1.py"])

    call_kwargs = llm_matcher.match_file_to_team.call_args
    assert call_kwargs[1]["allowed_teams"] == [
        "@team-a", "@team-b",
    ]


def test_suggest_derives_allowlist_from_codeowners() -> None:
    """Without config allowlist, teams should come from CODEOWNERS."""
    config = Config(team_allowlist=None)

    git_analyzer = _mock_git_analyzer({
        "src/file1.py": [("alice@example.com", 10)],
    })

    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.return_value = TeamSuggestion(
        filepath="src/file1.py",
        team="@existing-team",
        confidence=0.9,
        reasoning="ok",
    )

    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = []

    from codeowners_coverage.matcher import CodeOwnersPatternMatcher

    matcher = MagicMock(spec=CodeOwnersPatternMatcher)
    matcher.pattern_owners = {
        "src/**": ["@existing-team", "@other-team"],
    }
    matcher.get_all_teams.return_value = [
        "@existing-team", "@other-team",
    ]

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
        matcher=matcher,
    )

    suggester.suggest_for_uncovered_files(["src/file1.py"])

    call_kwargs = llm_matcher.match_file_to_team.call_args
    assert call_kwargs[1]["allowed_teams"] == [
        "@existing-team", "@other-team",
    ]


def test_suggest_passes_fileownership_to_consolidator() -> None:
    """Consolidator should receive FileOwnership with suggested_pattern."""
    config = Config()

    git_analyzer = _mock_git_analyzer({
        "src/deep/nested/file.py": [("alice@example.com", 10)],
    })

    llm_matcher = MagicMock(spec=OllamaLLMMatcher)
    llm_matcher.match_file_to_team.return_value = TeamSuggestion(
        filepath="src/deep/nested/file.py",
        team="@team-a",
        confidence=0.9,
        reasoning="ok",
        suggested_pattern="src/deep/**",
    )

    consolidator = MagicMock(spec=DirectoryConsolidator)
    consolidator.consolidate.return_value = []

    suggester = OwnershipSuggester(
        config=config,
        git_analyzer=git_analyzer,
        github_client=None,
        llm_matcher=llm_matcher,
        consolidator=consolidator,
    )

    suggester.suggest_for_uncovered_files(
        ["src/deep/nested/file.py"]
    )

    call_args = consolidator.consolidate.call_args[0][0]
    assert "src/deep/nested/file.py" in call_args
    ownership = call_args["src/deep/nested/file.py"]
    assert isinstance(ownership, FileOwnership)
    assert ownership.teams == ["@team-a"]
    assert ownership.suggested_pattern == "src/deep/**"
