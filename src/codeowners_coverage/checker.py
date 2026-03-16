"""Core coverage checking logic for CODEOWNERS."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set

import pathspec

from .config import Config
from .matcher import CodeOwnersPatternMatcher

_GLOB_CHARS = frozenset("*?[")


def _is_glob_pattern(entry: str) -> bool:
    return any(c in entry for c in _GLOB_CHARS)


@dataclass
class BaselineSpec:
    """Holds baseline entries split into literal paths and glob patterns."""

    literals: Set[str] = field(default_factory=set)
    glob_patterns: List[str] = field(default_factory=list)
    glob_spec: pathspec.PathSpec = field(
        default_factory=lambda: pathspec.PathSpec.from_lines("gitignore", [])
    )

    def matches(self, filepath: str) -> bool:
        return filepath in self.literals or self.glob_spec.match_file(filepath)

    def get_unused_entries(self, uncovered_files: List[str]) -> List[str]:
        """Return baseline entries that match zero uncovered files."""
        uncovered_set = set(uncovered_files)
        unused: List[str] = []
        for lit in sorted(self.literals):
            if lit not in uncovered_set:
                unused.append(lit)
        for pattern in self.glob_patterns:
            spec = pathspec.PathSpec.from_lines("gitignore", [pattern])
            if not any(spec.match_file(f) for f in uncovered_set):
                unused.append(pattern)
        return unused


class CoverageChecker:
    """Check CODEOWNERS coverage for repository files."""

    def __init__(self, config: Config) -> None:
        """
        Initialize coverage checker.

        Args:
            config: Configuration object
        """
        self.config = config
        self.matcher = CodeOwnersPatternMatcher(config.codeowners_path)
        self.exclusions = pathspec.PathSpec.from_lines("gitignore", config.exclusions)

    def get_repository_files(self) -> List[str]:
        """
        Get all files in repository using git ls-files.

        Returns:
            List of file paths relative to repository root
        """
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = result.stdout.strip().split("\n")
        # Filter out empty strings
        return [f for f in files if f]

    def _load_baseline(self) -> BaselineSpec:
        """
        Load baseline file of allowed uncovered files.

        Entries without glob metacharacters (*, ?, [) are treated as literal
        paths for exact matching.  Entries containing glob metacharacters are
        matched using gitignore-style pattern matching via pathspec.

        Returns:
            BaselineSpec with literal paths and compiled glob patterns
        """
        baseline_path = Path(self.config.baseline_path)

        if not baseline_path.exists():
            return BaselineSpec()

        literals: Set[str] = set()
        glob_patterns: List[str] = []

        with open(baseline_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if _is_glob_pattern(line):
                    glob_patterns.append(line)
                else:
                    literals.add(line)

        glob_spec = pathspec.PathSpec.from_lines("gitignore", glob_patterns)
        return BaselineSpec(literals=literals, glob_patterns=glob_patterns, glob_spec=glob_spec)

    def check_coverage(self, files: List[str] | None = None) -> Dict[str, object]:
        """
        Check which files lack CODEOWNERS coverage.

        Args:
            files: Optional list of specific files to check.
                   If None, checks all repository files.

        Returns:
            Dictionary with coverage statistics:
            {
                "total_files": int,
                "covered_files": int,
                "uncovered_files": [list of uncovered file paths],
                "baseline_files": [list of baseline file paths],
                "coverage_percentage": float
            }
        """
        if files is None:
            files = self.get_repository_files()

        # Filter excluded files
        filtered_files = [f for f in files if not self.exclusions.match_file(f)]

        # Check coverage
        uncovered = [f for f in filtered_files if not self.matcher.matches(f)]

        # Load baseline
        baseline = self._load_baseline()

        # Separate new uncovered files from baseline files
        new_uncovered = [f for f in uncovered if not baseline.matches(f)]
        baseline_files = [f for f in uncovered if baseline.matches(f)]

        # Calculate coverage
        total_files = len(filtered_files)
        covered_files = total_files - len(uncovered)
        coverage_percentage = (covered_files / total_files * 100) if total_files > 0 else 100.0

        return {
            "total_files": total_files,
            "covered_files": covered_files,
            "uncovered_files": new_uncovered,
            "baseline_files": baseline_files,
            "coverage_percentage": coverage_percentage,
        }

    def generate_baseline(self, files: List[str] | None = None) -> List[str]:
        """
        Generate a baseline of all currently uncovered files.

        Args:
            files: Optional list of specific files to check.
                   If None, checks all repository files.

        Returns:
            List of uncovered file paths (sorted)
        """
        if files is None:
            files = self.get_repository_files()

        # Filter excluded files
        filtered_files = [f for f in files if not self.exclusions.match_file(f)]

        # Check coverage
        uncovered = [f for f in filtered_files if not self.matcher.matches(f)]

        return sorted(uncovered)

    def write_baseline(self, baseline_files: List[str]) -> None:
        """
        Write baseline file.

        Preserves existing glob patterns that still match at least one
        uncovered file.  Literal paths covered by a preserved glob are
        omitted to avoid duplication.

        Args:
            baseline_files: List of file paths to write to baseline
        """
        baseline_path = Path(self.config.baseline_path)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)

        existing = self._load_baseline()
        uncovered_set = set(baseline_files)

        kept_globs: List[str] = []
        for pattern in existing.glob_patterns:
            spec = pathspec.PathSpec.from_lines("gitignore", [pattern])
            if any(spec.match_file(f) for f in uncovered_set):
                kept_globs.append(pattern)

        if kept_globs:
            kept_glob_spec = pathspec.PathSpec.from_lines("gitignore", kept_globs)
            literal_files = [f for f in baseline_files if not kept_glob_spec.match_file(f)]
        else:
            literal_files = list(baseline_files)

        with open(baseline_path, "w") as f:
            f.write("# CODEOWNERS Coverage Baseline\n")
            f.write("# Files lacking CODEOWNERS coverage (sorted)\n")
            f.write("# Goal: Reduce this list to zero\n")
            f.write("#\n")
            f.write("# Generated by: codeowners-coverage baseline\n")
            f.write("#\n")
            f.write("# Glob patterns (*, ?, [) are supported for matching groups of files.\n")
            f.write("# Example: docs/** or *.txt\n")
            f.write("#\n")
            f.write("\n")

            if kept_globs:
                for pattern in kept_globs:
                    f.write(f"{pattern}\n")
                f.write("\n")

            for filepath in literal_files:
                f.write(f"{filepath}\n")
