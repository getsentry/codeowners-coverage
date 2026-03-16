"""Main orchestrator for generating CODEOWNERS suggestions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import click

from .config import Config
from .directory_consolidator import DirectoryConsolidator, FileOwnership, Pattern
from .git_analyzer import GitHistoryAnalyzer
from .github_client import GitHubClient
from .matcher import CodeOwnersPatternMatcher
from .ollama_matcher import OllamaLLMMatcher, TeamSuggestion
from .suggest_cache import SuggestCache


@dataclass
class SuggestionResult:
    """Result of ownership suggestion process."""

    patterns: List[Pattern]
    file_suggestions: Dict[str, TeamSuggestion]
    total_files: int
    files_with_suggestions: int


class OwnershipSuggester:
    """Main orchestrator for generating ownership suggestions."""

    def __init__(
        self,
        config: Config,
        git_analyzer: GitHistoryAnalyzer,
        github_client: GitHubClient | None,
        llm_matcher: OllamaLLMMatcher,
        consolidator: DirectoryConsolidator,
        matcher: CodeOwnersPatternMatcher | None = None,
        cache: SuggestCache | None = None,
    ) -> None:
        """
        Initialize suggester with all components.

        Args:
            config: Configuration object
            git_analyzer: Git history analyzer
            github_client: GitHub API client (optional, for team validation)
            llm_matcher: Ollama LLM matcher
            consolidator: Directory consolidator
            matcher: Optional CODEOWNERS matcher for context
            cache: Optional disk-backed cache for incremental runs
        """
        self.config = config
        self.git_analyzer = git_analyzer
        self.github_client = github_client
        self.llm_matcher = llm_matcher
        self.consolidator = consolidator
        self.matcher = matcher
        self.cache = cache

    def suggest_for_uncovered_files(
        self,
        files: List[str],
        progress_callback: Callable[[int, int, str, TeamSuggestion], None]
        | None = None,
    ) -> SuggestionResult:
        """
        Generate ownership suggestions for uncovered files.

        Flow:
        1. Get contributors from git history (local, cached)
        2. Build contributor -> teams mapping via GitHub API (cached)
        3. Use LLM to match files -> teams (cached per file)
        4. Consolidate to directory patterns
        5. Return suggestions with confidence scores

        Args:
            files: List of file paths to suggest ownership for
            progress_callback: Optional (current, total, filepath, suggestion)
                callback invoked after each LLM result

        Returns:
            SuggestionResult with patterns and suggestions
        """
        if not files:
            return SuggestionResult(
                patterns=[],
                file_suggestions={},
                total_files=0,
                files_with_suggestions=0,
            )

        # Step 1: Analyze git history (with cache)
        file_contributors = self._get_contributors_cached(files)

        # Step 2: Build contributor -> teams mapping (with cache)
        contributor_teams = self._get_teams_cached(file_contributors)

        # Step 3: Get existing patterns for context and resolve team allowlist
        existing_patterns: Dict[str, List[str]] | None = None
        allowed_teams: List[str] | None = self.config.team_allowlist
        if self.matcher:
            existing_patterns = self.matcher.pattern_owners
            if allowed_teams is None:
                allowed_teams = self.matcher.get_all_teams() or None

        # Step 4: Use LLM to suggest ownership (with cache)
        file_suggestions, file_owners = self._get_llm_suggestions_cached(
            files,
            file_contributors,
            contributor_teams,
            existing_patterns,
            progress_callback,
            allowed_teams,
        )

        # Step 5: Consolidate to directory patterns
        patterns = self.consolidator.consolidate(file_owners)

        return SuggestionResult(
            patterns=patterns,
            file_suggestions=file_suggestions,
            total_files=len(files),
            files_with_suggestions=len(file_owners),
        )

    def _get_contributors_cached(
        self, files: List[str]
    ) -> Dict[str, List[Tuple[str, int]]]:
        """Get git contributors, using cache for hits.

        Processes files one at a time so progress is visible and
        the cache is flushed periodically to survive interrupts.
        """
        result: Dict[str, List[Tuple[str, int]]] = {}
        uncached: List[str] = []

        for filepath in files:
            if self.cache:
                cached = self.cache.get_git_contributors(filepath)
                if cached is not None:
                    if cached:
                        result[filepath] = cached
                    continue
            uncached.append(filepath)

        cached_count = len(files) - len(uncached)
        if not uncached:
            if self.cache:
                click.echo(
                    f"   Git history: {len(files)} cached (all)"
                )
            return result

        if cached_count > 0:
            click.echo(
                f"   Git history: {cached_count} cached, "
                f"fetching {len(uncached)}..."
            )
        else:
            click.echo(
                f"   Git history: fetching {len(uncached)} "
                f"files..."
            )

        flush_interval = 50
        for i, filepath in enumerate(uncached, 1):
            contributors = (
                self.git_analyzer.get_file_contributors(filepath)
            )
            if contributors:
                result[filepath] = contributors

            if self.cache:
                self.cache.set_git_contributors(
                    filepath, contributors
                )
                if i % flush_interval == 0:
                    self.cache.flush_if_dirty()
                    click.echo(
                        f"   Git history: [{i}/{len(uncached)}]"
                    )

        # Final flush for the remainder
        if self.cache:
            self.cache.flush_if_dirty()

        click.echo(
            f"   Git history: [{len(uncached)}/{len(uncached)}] "
            f"done"
        )

        return result

    def _get_teams_cached(
        self,
        file_contributors: Dict[str, List[Tuple[str, int]]],
    ) -> Dict[str, List[str]]:
        """Build contributor->teams map, using cache when available."""
        if not self.github_client:
            return {}

        if self.cache:
            cached_teams = self.cache.get_contributor_teams()
            if cached_teams is not None:
                click.echo(
                    f"   Team mapping: {len(cached_teams)} "
                    f"contributors cached"
                )
                return cached_teams

        all_contributors: set[str] = set()
        for contributors in file_contributors.values():
            for email, _ in contributors:
                all_contributors.add(email)

        click.echo(
            f"   Team mapping: fetching for "
            f"{len(all_contributors)} contributors..."
        )

        contributor_teams = self.github_client.build_contributor_team_map(
            all_contributors
        )

        click.echo("   Team mapping: done")

        if self.cache:
            self.cache.set_contributor_teams(contributor_teams)
            self.cache.flush_if_dirty()

        return contributor_teams

    def _get_llm_suggestions_cached(
        self,
        files: List[str],
        file_contributors: Dict[str, List[Tuple[str, int]]],
        contributor_teams: Dict[str, List[str]],
        existing_patterns: Dict[str, List[str]] | None,
        progress_callback: Callable[
            [int, int, str, TeamSuggestion], None
        ]
        | None,
        allowed_teams: List[str] | None = None,
    ) -> tuple[Dict[str, TeamSuggestion], Dict[str, FileOwnership]]:
        """Run LLM suggestions with per-file caching and progress."""
        file_suggestions: Dict[str, TeamSuggestion] = {}
        file_owners: Dict[str, FileOwnership] = {}

        total = len(files)
        for idx, filepath in enumerate(files, 1):
            # Check cache first
            if self.cache:
                cached = self.cache.get_llm_suggestion(filepath)
                if cached is not None:
                    file_suggestions[filepath] = cached
                    if (
                        cached.confidence >= 0.5
                        and cached.team != "@unknown"
                    ):
                        file_owners[filepath] = FileOwnership(
                            teams=[cached.team],
                            suggested_pattern=cached.suggested_pattern,
                        )
                    continue

            contributors = file_contributors.get(filepath, [])

            suggestion = self.llm_matcher.match_file_to_team(
                filepath=filepath,
                contributors=contributors,
                contributor_teams=contributor_teams,
                existing_patterns=existing_patterns,
                allowed_teams=allowed_teams,
            )

            file_suggestions[filepath] = suggestion

            if (
                suggestion.confidence >= 0.5
                and suggestion.team != "@unknown"
            ):
                file_owners[filepath] = FileOwnership(
                    teams=[suggestion.team],
                    suggested_pattern=suggestion.suggested_pattern,
                )

            # Persist immediately after each LLM call
            if self.cache:
                self.cache.set_llm_suggestion(filepath, suggestion)
                self.cache.flush_if_dirty()

            if progress_callback:
                progress_callback(idx, total, filepath, suggestion)

        return file_suggestions, file_owners
