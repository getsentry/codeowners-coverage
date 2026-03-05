"""Directory-level pattern consolidation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class Pattern:
    """A consolidated CODEOWNERS pattern."""

    pattern: str
    teams: List[str]
    file_count: int
    confidence: float


class DirectoryConsolidator:
    """Find optimal directory-level patterns from file-level suggestions."""

    def __init__(self, min_coverage: float = 0.8) -> None:
        """
        Initialize consolidator.

        Args:
            min_coverage: Minimum fraction of files in a directory that must
                         share the same owner to consolidate (default: 0.8)
        """
        self.min_coverage = min_coverage

    def consolidate(
        self,
        file_owners: Dict[str, List[str]],
    ) -> List[Pattern]:
        """
        Consolidate file-level ownership into directory patterns.

        Strategy:
        1. Build directory tree with file counts
        2. For each directory, check if >= min_coverage files share owner
        3. If yes, consolidate to directory pattern
        4. Work bottom-up to prefer highest-level patterns

        Args:
            file_owners: Dict mapping filepath → list of team owners

        Returns:
            List of consolidated patterns, sorted by specificity
        """
        if not file_owners:
            return []

        # Build directory → (owner → file_count) mapping
        dir_ownership: Dict[str, Dict[tuple[str, ...], List[str]]] = defaultdict(
            lambda: defaultdict(list)
        )

        for filepath, teams in file_owners.items():
            # Sort teams for consistent tuple keys
            teams_tuple = tuple(sorted(teams))

            # Add file to its directory and all parent directories
            path = Path(filepath)
            directories = [str(path.parent)] if path.parent != Path(".") else ["."]

            # Also add all parent directories
            current = path.parent
            while current != Path(".") and current != Path("/"):
                directories.append(str(current))
                current = current.parent

            for directory in directories:
                dir_ownership[directory][teams_tuple].append(filepath)

        # Find consolidation opportunities
        patterns = []

        # Sort directories by depth (deeper first for bottom-up processing)
        sorted_dirs = sorted(
            dir_ownership.keys(),
            key=lambda d: len(Path(d).parts),
            reverse=True,
        )

        covered_files = set()

        for directory in sorted_dirs:
            ownership_counts = dir_ownership[directory]

            # Find most common owner in this directory
            total_files = sum(len(files) for files in ownership_counts.values())
            most_common_owner = None
            max_count = 0

            for owner_tuple, files in ownership_counts.items():
                # Only count files not yet covered by a more specific pattern
                uncovered_files = [f for f in files if f not in covered_files]
                count = len(uncovered_files)

                if count > max_count:
                    max_count = count
                    most_common_owner = owner_tuple

            if not most_common_owner:
                continue

            # Check if this owner covers enough files
            coverage = max_count / total_files if total_files > 0 else 0

            if coverage >= self.min_coverage and max_count > 0:
                # Create pattern for this directory
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

                # Mark these files as covered
                for owner_tuple, files in ownership_counts.items():
                    if owner_tuple == most_common_owner:
                        covered_files.update(files)

        # Add patterns for individual files that weren't consolidated
        for filepath, teams in file_owners.items():
            if filepath not in covered_files:
                patterns.append(
                    Pattern(
                        pattern=filepath,
                        teams=teams,
                        file_count=1,
                        confidence=1.0,
                    )
                )

        # Sort by specificity (more specific patterns first)
        # Specificity: file patterns > directory patterns > root patterns
        def pattern_specificity(p: Pattern) -> tuple[int, bool]:
            # Count path components (more = more specific)
            parts = len(Path(p.pattern.rstrip("/**")).parts)
            # Files (no **) are more specific than directories
            is_directory = "**" in p.pattern
            return (-parts, is_directory)

        patterns.sort(key=pattern_specificity)

        return patterns
