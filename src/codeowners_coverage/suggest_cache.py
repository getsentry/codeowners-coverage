"""Disk-backed cache for the suggest command, enabling incremental restarts."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from .ollama_matcher import TeamSuggestion

CACHE_VERSION = 1


@dataclass
class CacheParams:
    """Parameters that affect cache validity."""

    ollama_model: str = ""
    lookback_commits: int = 100


@dataclass
class SuggestCache:
    """Persistent cache for suggest command intermediate results.

    Writes atomically after each mutation to survive crashes.
    Invalidates stale sections when parameters change.
    """

    path: Path
    params: CacheParams = field(default_factory=CacheParams)
    git_contributors: Dict[str, List[Tuple[str, int]]] = field(default_factory=dict)
    contributor_teams: Dict[str, List[str]] = field(default_factory=dict)
    llm_suggestions: Dict[str, TeamSuggestion] = field(default_factory=dict)
    _dirty: bool = field(default=False, repr=False)

    @classmethod
    def load(cls, path: str | Path) -> SuggestCache:
        """Load cache from disk, returning empty cache if file is missing or corrupt."""
        path = Path(path)
        if not path.exists():
            return cls(path=path)

        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return cls(path=path)

        if data.get("version") != CACHE_VERSION:
            return cls(path=path)

        params_raw = data.get("params", {})
        params = CacheParams(
            ollama_model=params_raw.get("ollama_model", ""),
            lookback_commits=params_raw.get("lookback_commits", 100),
        )

        git_contributors: Dict[str, List[Tuple[str, int]]] = {}
        for filepath, contribs in data.get("git_contributors", {}).items():
            git_contributors[filepath] = [(e, c) for e, c in contribs]

        contributor_teams: Dict[str, List[str]] = data.get("contributor_teams", {})

        llm_suggestions: Dict[str, TeamSuggestion] = {}
        for filepath, suggestion in data.get("llm_suggestions", {}).items():
            llm_suggestions[filepath] = TeamSuggestion(
                filepath=filepath,
                team=suggestion["team"],
                confidence=suggestion["confidence"],
                reasoning=suggestion["reasoning"],
                suggested_pattern=suggestion.get("suggested_pattern"),
            )

        return cls(
            path=path,
            params=params,
            git_contributors=git_contributors,
            contributor_teams=contributor_teams,
            llm_suggestions=llm_suggestions,
        )

    def save(self) -> None:
        """Atomically write cache to disk (write tmp + rename)."""
        data = {
            "version": CACHE_VERSION,
            "params": {
                "ollama_model": self.params.ollama_model,
                "lookback_commits": self.params.lookback_commits,
            },
            "git_contributors": {
                fp: [[email, count] for email, count in contribs]
                for fp, contribs in self.git_contributors.items()
            },
            "contributor_teams": self.contributor_teams,
            "llm_suggestions": {
                fp: {
                    "team": s.team,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                    "suggested_pattern": s.suggested_pattern,
                }
                for fp, s in self.llm_suggestions.items()
            },
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=".suggest-cache-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        self._dirty = False

    def invalidate_if_params_changed(
        self, ollama_model: str, lookback_commits: int
    ) -> List[str]:
        """Check params and invalidate stale sections. Returns list of messages."""
        messages: List[str] = []

        if self.params.ollama_model and self.params.ollama_model != ollama_model:
            messages.append(
                f"Model changed ({self.params.ollama_model} -> {ollama_model}), "
                f"clearing {len(self.llm_suggestions)} cached LLM suggestions"
            )
            self.llm_suggestions.clear()
            self._dirty = True

        if (
            self.params.lookback_commits
            and self.params.lookback_commits != lookback_commits
        ):
            messages.append(
                f"Lookback changed ({self.params.lookback_commits} -> {lookback_commits}), "
                f"clearing {len(self.git_contributors)} cached git results "
                f"and {len(self.llm_suggestions)} LLM suggestions"
            )
            self.git_contributors.clear()
            self.llm_suggestions.clear()
            self._dirty = True

        self.params.ollama_model = ollama_model
        self.params.lookback_commits = lookback_commits

        if self._dirty:
            self.save()

        return messages

    # -- git contributors --

    def get_git_contributors(self, filepath: str) -> List[Tuple[str, int]] | None:
        """Return cached contributors or None if not cached."""
        return self.git_contributors.get(filepath)

    def set_git_contributors(
        self, filepath: str, contributors: List[Tuple[str, int]]
    ) -> None:
        self.git_contributors[filepath] = contributors
        self._dirty = True

    # -- contributor teams --

    def get_contributor_teams(self) -> Dict[str, List[str]] | None:
        """Return cached teams map, or None if empty."""
        return self.contributor_teams if self.contributor_teams else None

    def set_contributor_teams(self, teams: Dict[str, List[str]]) -> None:
        self.contributor_teams = teams
        self._dirty = True

    # -- LLM suggestions --

    def get_llm_suggestion(self, filepath: str) -> TeamSuggestion | None:
        """Return cached suggestion or None if not cached."""
        return self.llm_suggestions.get(filepath)

    def set_llm_suggestion(self, filepath: str, suggestion: TeamSuggestion) -> None:
        self.llm_suggestions[filepath] = suggestion
        self._dirty = True

    def count_cached_suggestions(self, files: List[str]) -> int:
        """Count how many of the given files already have cached LLM suggestions."""
        return sum(1 for f in files if f in self.llm_suggestions)

    def flush_if_dirty(self) -> None:
        """Save to disk only if there are unsaved changes."""
        if self._dirty:
            self.save()
