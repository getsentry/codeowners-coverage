"""Tests for the suggest cache (incremental/idempotent suggest)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeowners_coverage.ollama_matcher import TeamSuggestion
from codeowners_coverage.suggest_cache import (
    CacheParams,
    SuggestCache,
)


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    return tmp_path / "test-cache.json"


class TestSuggestCacheLoadSave:
    def test_load_missing_file(self, cache_path: Path) -> None:
        cache = SuggestCache.load(cache_path)
        assert cache.git_contributors == {}
        assert cache.llm_suggestions == {}
        assert cache.contributor_teams == {}

    def test_load_corrupt_file(self, cache_path: Path) -> None:
        cache_path.write_text("not json {{{")
        cache = SuggestCache.load(cache_path)
        assert cache.git_contributors == {}

    def test_load_wrong_version(self, cache_path: Path) -> None:
        cache_path.write_text(json.dumps({"version": 999}))
        cache = SuggestCache.load(cache_path)
        assert cache.git_contributors == {}

    def test_save_and_load_roundtrip(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        cache.set_git_contributors(
            "src/a.py", [("alice@ex.com", 5), ("bob@ex.com", 2)]
        )
        cache.set_contributor_teams(
            {"alice@ex.com": ["@frontend", "@platform"]}
        )
        cache.set_llm_suggestion(
            "src/a.py",
            TeamSuggestion(
                filepath="src/a.py",
                team="@frontend",
                confidence=0.9,
                reasoning="Frontend file",
            ),
        )
        cache.params = CacheParams(
            ollama_model="llama3.2", lookback_commits=100
        )
        cache.save()

        loaded = SuggestCache.load(cache_path)
        assert loaded.git_contributors["src/a.py"] == [
            ("alice@ex.com", 5),
            ("bob@ex.com", 2),
        ]
        assert loaded.contributor_teams == {
            "alice@ex.com": ["@frontend", "@platform"]
        }
        assert loaded.llm_suggestions["src/a.py"].team == "@frontend"
        assert loaded.llm_suggestions["src/a.py"].confidence == 0.9
        assert loaded.params.ollama_model == "llama3.2"
        assert loaded.params.lookback_commits == 100

    def test_save_creates_parent_directories(
        self, tmp_path: Path
    ) -> None:
        deep_path = tmp_path / "a" / "b" / "cache.json"
        cache = SuggestCache(path=deep_path)
        cache.set_git_contributors("f.py", [("x@y.com", 1)])
        cache.save()
        assert deep_path.exists()

    def test_atomic_save_does_not_leave_tmp(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        cache.set_git_contributors("f.py", [("x@y.com", 1)])
        cache.save()

        tmp_files = list(cache_path.parent.glob(".suggest-cache-*"))
        assert tmp_files == []


class TestCacheInvalidation:
    def test_no_invalidation_when_params_match(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        cache.params = CacheParams(
            ollama_model="llama3.2", lookback_commits=100
        )
        cache.set_llm_suggestion(
            "a.py",
            TeamSuggestion("a.py", "@t", 0.9, "r"),
        )
        cache.set_git_contributors("a.py", [("x@y.com", 1)])

        msgs = cache.invalidate_if_params_changed("llama3.2", 100)
        assert msgs == []
        assert "a.py" in cache.llm_suggestions
        assert "a.py" in cache.git_contributors

    def test_model_change_clears_llm_only(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        cache.params = CacheParams(
            ollama_model="llama3.2", lookback_commits=100
        )
        cache.set_llm_suggestion(
            "a.py",
            TeamSuggestion("a.py", "@t", 0.9, "r"),
        )
        cache.set_git_contributors("a.py", [("x@y.com", 1)])

        msgs = cache.invalidate_if_params_changed("mistral", 100)
        assert len(msgs) == 1
        assert "Model changed" in msgs[0]
        assert cache.llm_suggestions == {}
        assert "a.py" in cache.git_contributors

    def test_lookback_change_clears_git_and_llm(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        cache.params = CacheParams(
            ollama_model="llama3.2", lookback_commits=100
        )
        cache.set_llm_suggestion(
            "a.py",
            TeamSuggestion("a.py", "@t", 0.9, "r"),
        )
        cache.set_git_contributors("a.py", [("x@y.com", 1)])

        msgs = cache.invalidate_if_params_changed("llama3.2", 200)
        assert len(msgs) == 1
        assert "Lookback changed" in msgs[0]
        assert cache.llm_suggestions == {}
        assert cache.git_contributors == {}


class TestCacheGetSet:
    def test_git_contributors_miss(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        assert cache.get_git_contributors("missing.py") is None

    def test_git_contributors_hit(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        cache.set_git_contributors(
            "a.py", [("x@y.com", 3)]
        )
        assert cache.get_git_contributors("a.py") == [
            ("x@y.com", 3)
        ]

    def test_llm_suggestion_miss(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        assert cache.get_llm_suggestion("missing.py") is None

    def test_llm_suggestion_hit(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        s = TeamSuggestion("a.py", "@team", 0.8, "reason")
        cache.set_llm_suggestion("a.py", s)
        result = cache.get_llm_suggestion("a.py")
        assert result is not None
        assert result.team == "@team"

    def test_contributor_teams_empty_returns_none(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        assert cache.get_contributor_teams() is None

    def test_contributor_teams_populated(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        cache.set_contributor_teams({"a@b.com": ["@t1"]})
        assert cache.get_contributor_teams() == {
            "a@b.com": ["@t1"]
        }

    def test_count_cached_suggestions(
        self, cache_path: Path
    ) -> None:
        cache = SuggestCache(path=cache_path)
        cache.set_llm_suggestion(
            "a.py",
            TeamSuggestion("a.py", "@t", 0.9, "r"),
        )
        cache.set_llm_suggestion(
            "b.py",
            TeamSuggestion("b.py", "@t", 0.8, "r"),
        )

        assert cache.count_cached_suggestions(
            ["a.py", "b.py", "c.py"]
        ) == 2

    def test_flush_if_dirty(self, cache_path: Path) -> None:
        cache = SuggestCache(path=cache_path)
        cache.flush_if_dirty()
        assert not cache_path.exists()

        cache.set_git_contributors("a.py", [])
        cache.flush_if_dirty()
        assert cache_path.exists()
