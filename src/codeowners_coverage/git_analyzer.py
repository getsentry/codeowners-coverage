"""Git history analysis for contributor extraction."""

from __future__ import annotations

import subprocess
from collections import Counter
from typing import Dict, List, Tuple


class GitHistoryAnalyzer:
    """Analyze git history to find contributors."""

    def __init__(self, lookback_commits: int = 100) -> None:
        """
        Configure git history analysis.

        Args:
            lookback_commits: How many commits to analyze per file
        """
        self.lookback_commits = lookback_commits

    def get_file_contributors(self, filepath: str) -> List[Tuple[str, int]]:
        """
        Get contributors for a file from git history.

        Uses git log --follow to track file renames and extracts
        contributor emails with commit counts.

        Args:
            filepath: Path to file (relative to repo root)

        Returns:
            List of (email, commit_count) tuples, sorted by commit count desc
        """
        try:
            # Use git log with --follow to track renames
            # Format: email only (%ae)
            result = subprocess.run(
                [
                    "git",
                    "log",
                    "--follow",
                    f"-n{self.lookback_commits}",
                    "--format=%ae",
                    "--",
                    filepath,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            if not result.stdout.strip():
                # No git history for this file
                return []

            # Count commits per contributor
            emails = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
            email_counts = Counter(emails)

            # Return sorted by commit count (descending)
            return sorted(email_counts.items(), key=lambda x: x[1], reverse=True)

        except Exception:
            # File doesn't exist or git command failed
            return []

    def get_bulk_contributors(self, filepaths: List[str]) -> Dict[str, List[Tuple[str, int]]]:
        """
        Efficiently get contributors for many files.

        Note: This calls get_file_contributors per file. Could be optimized
        with batched git commands, but this is simpler and sufficient for now.

        Args:
            filepaths: List of file paths to analyze

        Returns:
            Dict mapping filepath → list of (email, commit_count) tuples
        """
        result = {}
        for filepath in filepaths:
            contributors = self.get_file_contributors(filepath)
            if contributors:  # Only include files with git history
                result[filepath] = contributors
        return result
