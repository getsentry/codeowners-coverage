"""Pattern matching for CODEOWNERS files using pathspec."""

from __future__ import annotations

from pathlib import Path
from typing import List

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
