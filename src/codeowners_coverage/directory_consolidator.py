"""Directory-level pattern consolidation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Pattern:
    """A consolidated CODEOWNERS pattern."""

    pattern: str
    teams: List[str]
    file_count: int
    confidence: float


@dataclass
class FileOwnership:
    """Ownership info for a single file, optionally with an LLM-suggested pattern."""

    teams: List[str]
    suggested_pattern: Optional[str] = None


class DirectoryConsolidator:
    """Find optimal directory-level patterns from file-level suggestions."""

    def __init__(
        self,
        min_coverage: float = 0.8,
        max_single_file_depth: int = 1,
    ) -> None:
        """
        Initialize consolidator.

        Args:
            min_coverage: Minimum fraction of files in a directory that must
                         share the same owner to consolidate (default: 0.8)
            max_single_file_depth: Maximum directory depth at which a file may
                         receive its own individual pattern. Files deeper than
                         this are always grouped into a directory pattern.
                         Depth 0 = root, depth 1 = one directory deep, etc.
        """
        self.min_coverage = min_coverage
        self.max_single_file_depth = max_single_file_depth

    def consolidate(
        self,
        file_owners: Dict[str, FileOwnership] | Dict[str, List[str]],
    ) -> List[Pattern]:
        """
        Consolidate file-level ownership into directory patterns.

        Strategy:
        1. Build directory tree with file counts
        2. For each directory, check if >= min_coverage files share owner
        3. If yes, consolidate to directory pattern
        4. Work bottom-up to prefer highest-level patterns
        5. For remaining unconsolidated files:
           a. Use LLM-suggested patterns when available
           b. Group deep files by a heuristic parent directory
           c. Only allow individual file patterns for shallow files

        Args:
            file_owners: Dict mapping filepath to either a list of teams
                        (legacy) or a FileOwnership object with teams
                        and optional suggested_pattern.

        Returns:
            List of consolidated patterns, sorted by specificity
        """
        if not file_owners:
            return []

        normalized = self._normalize_input(file_owners)

        # Phase 1: standard directory-based consolidation
        patterns, covered_files = self._consolidate_by_directory(normalized)

        # Phase 2: handle unconsolidated files
        remaining = {
            fp: info for fp, info in normalized.items() if fp not in covered_files
        }
        if remaining:
            extra = self._consolidate_remaining(remaining)
            patterns.extend(extra)

        patterns.sort(key=self._pattern_specificity)
        return patterns

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_input(
        file_owners: Dict[str, FileOwnership] | Dict[str, List[str]],
    ) -> Dict[str, FileOwnership]:
        """Accept both legacy list-of-teams and new FileOwnership dicts."""
        normalized: Dict[str, FileOwnership] = {}
        for fp, val in file_owners.items():
            if isinstance(val, FileOwnership):
                normalized[fp] = val
            else:
                normalized[fp] = FileOwnership(teams=val)
        return normalized

    def _consolidate_by_directory(
        self,
        file_owners: Dict[str, FileOwnership],
    ) -> tuple[List[Pattern], set[str]]:
        """Phase 1: standard directory-threshold consolidation (unchanged logic)."""
        dir_ownership: Dict[str, Dict[tuple[str, ...], List[str]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for filepath, info in file_owners.items():
            teams_tuple = tuple(sorted(info.teams))
            path = Path(filepath)

            directories: set[str] = set()
            if path.parent == Path("."):
                directories.add(".")
            else:
                current = path.parent
                while current != Path(".") and current != Path("/"):
                    directories.add(str(current))
                    current = current.parent

            for directory in directories:
                dir_ownership[directory][teams_tuple].append(filepath)

        patterns: List[Pattern] = []
        sorted_dirs = sorted(
            dir_ownership.keys(),
            key=lambda d: len(Path(d).parts),
            reverse=True,
        )

        covered_files: set[str] = set()

        for directory in sorted_dirs:
            ownership_counts = dir_ownership[directory]
            total_files = sum(len(files) for files in ownership_counts.values())
            most_common_owner = None
            max_count = 0

            for owner_tuple, files in ownership_counts.items():
                uncovered_files = [f for f in files if f not in covered_files]
                count = len(uncovered_files)
                if count > max_count:
                    max_count = count
                    most_common_owner = owner_tuple

            if not most_common_owner:
                continue

            coverage = max_count / total_files if total_files > 0 else 0

            if coverage >= self.min_coverage and max_count >= 2:
                if directory == ".":
                    pattern_str = "*"
                else:
                    pattern_str = f"{directory}/**"

                patterns.append(
                    Pattern(
                        pattern=pattern_str,
                        teams=list(most_common_owner),
                        file_count=max_count,
                        confidence=coverage,
                    )
                )

                for owner_tuple, files in ownership_counts.items():
                    if owner_tuple == most_common_owner:
                        covered_files.update(files)

        return patterns, covered_files

    def _consolidate_remaining(
        self,
        remaining: Dict[str, FileOwnership],
    ) -> List[Pattern]:
        """
        Phase 2: handle files not consolidated by the directory pass.

        1. Group by LLM-suggested pattern + team when available.
        2. For deep files without a suggested pattern, pick a heuristic
           parent directory.
        3. Only allow bare file patterns for shallow files.
        """
        patterns: List[Pattern] = []

        # Bucket by (suggested_pattern, teams_tuple) for files that have a suggestion
        suggested_buckets: Dict[
            tuple[str, tuple[str, ...]], List[str]
        ] = defaultdict(list)
        no_suggestion: Dict[str, FileOwnership] = {}

        for filepath, info in remaining.items():
            if info.suggested_pattern:
                key = (info.suggested_pattern, tuple(sorted(info.teams)))
                suggested_buckets[key].append(filepath)
            else:
                no_suggestion[filepath] = info

        # Emit patterns for suggested-pattern groups
        for (pattern, teams_tuple), files in suggested_buckets.items():
            patterns.append(
                Pattern(
                    pattern=pattern,
                    teams=list(teams_tuple),
                    file_count=len(files),
                    confidence=1.0,
                )
            )

        # Handle files with no suggested pattern
        for filepath, info in no_suggestion.items():
            depth = len(Path(filepath).parts) - 1  # depth 0 = root file

            if depth <= self.max_single_file_depth:
                # Shallow file -- individual pattern is fine
                patterns.append(
                    Pattern(
                        pattern=filepath,
                        teams=info.teams,
                        file_count=1,
                        confidence=1.0,
                    )
                )
            else:
                # Deep file -- use a heuristic parent directory
                parent = self._find_grouping_directory(filepath)
                patterns.append(
                    Pattern(
                        pattern=f"{parent}/**",
                        teams=info.teams,
                        file_count=1,
                        confidence=0.7,
                    )
                )

        # Deduplicate directory patterns: merge entries that share pattern+teams
        patterns = self._merge_patterns(patterns)
        return patterns

    @staticmethod
    def _find_grouping_directory(filepath: str) -> str:
        """
        Find the best grouping directory for a deeply nested file.

        Heuristic: use the first 3 path components (or fewer if the path is
        shorter).  For example:
          "static/app/components/searchQueryBuilder/tokens/.../grammar.pegjs"
          → "static/app/components"
          "tests/sentry/notifications/test_apps.py"
          → "tests/sentry/notifications"
        """
        parts = Path(filepath).parts
        # Exclude the filename itself
        dir_parts = parts[:-1]
        # Use up to 3 directory components (adjustable)
        limit = min(3, len(dir_parts))
        return str(Path(*dir_parts[:limit])) if limit > 0 else "."

    @staticmethod
    def _merge_patterns(patterns: List[Pattern]) -> List[Pattern]:
        """Merge patterns that share the same pattern string and teams."""
        merged: Dict[tuple[str, tuple[str, ...]], Pattern] = {}
        for p in patterns:
            key = (p.pattern, tuple(sorted(p.teams)))
            if key in merged:
                existing = merged[key]
                merged[key] = Pattern(
                    pattern=p.pattern,
                    teams=p.teams,
                    file_count=existing.file_count + p.file_count,
                    confidence=min(existing.confidence, p.confidence),
                )
            else:
                merged[key] = p
        return list(merged.values())

    @staticmethod
    def _pattern_specificity(p: Pattern) -> tuple[int, bool]:
        """Sort key: more specific patterns first."""
        parts = len(Path(p.pattern.rstrip("/**")).parts)
        is_directory = "**" in p.pattern
        return (-parts, is_directory)
