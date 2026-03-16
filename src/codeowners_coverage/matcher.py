"""Pattern matching for CODEOWNERS files using pathspec."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pathspec


class CodeOwnersPatternMatcher:
    """Match file paths against CODEOWNERS patterns."""

    def __init__(self, codeowners_path: str) -> None:
        """
        Load and parse CODEOWNERS file.

        Args:
            codeowners_path: Path to the CODEOWNERS file
        """
        self.codeowners_path = codeowners_path
        self.patterns = self._parse_codeowners(codeowners_path)
        # Use gitignore for gitignore-style patterns
        self.spec = pathspec.PathSpec.from_lines("gitignore", self.patterns)
        # NEW: Store ownership mappings (pattern → owners)
        self.pattern_owners: Dict[str, List[str]] = self._parse_owners(codeowners_path)

    def _parse_codeowners(self, path: str) -> List[str]:
        """
        Extract patterns from CODEOWNERS file.

        The CODEOWNERS format is:
        pattern @owner1 @owner2

        We only care about the patterns, not the owners.

        Args:
            path: Path to CODEOWNERS file

        Returns:
            List of patterns extracted from the file
        """
        patterns = []
        codeowners_file = Path(path)

        if not codeowners_file.exists():
            raise FileNotFoundError(f"CODEOWNERS file not found: {path}")

        with open(codeowners_file) as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Pattern is first token, owners follow
                parts = line.split()
                if parts:
                    pattern = parts[0]
                    patterns.append(pattern)

        return patterns

    def matches(self, filepath: str) -> bool:
        """
        Check if filepath is covered by any CODEOWNERS pattern.

        Args:
            filepath: File path to check (relative to repo root)

        Returns:
            True if the file matches any CODEOWNERS pattern
        """
        return self.spec.match_file(filepath)

    def get_matching_pattern(self, filepath: str) -> str | None:
        """
        Get the first pattern that matches the given filepath.

        Args:
            filepath: File path to check (relative to repo root)

        Returns:
            The matching pattern, or None if no match
        """
        for pattern in self.patterns:
            pattern_spec = pathspec.PathSpec.from_lines("gitignore", [pattern])
            if pattern_spec.match_file(filepath):
                return pattern
        return None

    def _parse_owners(self, path: str) -> Dict[str, List[str]]:
        """
        Extract pattern → owners mapping from CODEOWNERS file.

        The CODEOWNERS format is:
        pattern @owner1 @owner2

        Args:
            path: Path to CODEOWNERS file

        Returns:
            Dict mapping pattern → list of owners
        """
        pattern_owners: Dict[str, List[str]] = {}
        codeowners_file = Path(path)

        if not codeowners_file.exists():
            return pattern_owners

        with open(codeowners_file) as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Pattern is first token, owners follow
                parts = line.split()
                if len(parts) >= 2:
                    pattern = parts[0]
                    owners = parts[1:]  # All tokens after pattern are owners
                    pattern_owners[pattern] = owners

        return pattern_owners

    def get_all_teams(self) -> List[str]:
        """
        Get deduplicated, sorted list of all team/owner names used in CODEOWNERS.

        Returns:
            Sorted list of unique owner identifiers (e.g. @team-name)
        """
        teams: set[str] = set()
        for owners in self.pattern_owners.values():
            teams.update(owners)
        return sorted(teams)

    def get_owners_for_file(self, filepath: str) -> List[str] | None:
        """
        Get owners for a specific file.

        Args:
            filepath: File path to check (relative to repo root)

        Returns:
            List of owners for the file, or None if no match
        """
        pattern = self.get_matching_pattern(filepath)
        if pattern:
            return self.pattern_owners.get(pattern)
        return None
