"""Configuration loading for codeowners-coverage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass
class Config:
    """Configuration for codeowners-coverage."""

    codeowners_path: str = ".github/CODEOWNERS"
    baseline_path: str = ".github/codeowners-coverage-baseline.txt"
    exclusions: List[str] = field(default_factory=list)

    # Suggestion-related settings (for 'suggest' command)
    github_token: str | None = None
    github_org: str | None = None
    suggestion_min_coverage: float = 0.8
    ollama_model: str = "llama3.2"
    ollama_base_url: str = "http://localhost:11434"
    suggestion_lookback_commits: int = 100
    suggest_cache_path: str = ".codeowners-suggest-cache.json"

    @classmethod
    def load(cls, config_path: str = ".codeowners-config.yml") -> Config:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to the configuration file

        Returns:
            Config object with loaded settings
        """
        config_file = Path(config_path)

        if not config_file.exists():
            # Return default configuration with default exclusions
            return cls(exclusions=cls.default_exclusions())

        with open(config_file) as f:
            data = yaml.safe_load(f) or {}

        return cls(
            codeowners_path=data.get("codeowners_path", cls.codeowners_path),
            baseline_path=data.get("baseline_path", cls.baseline_path),
            exclusions=data.get("exclusions", cls.default_exclusions()),
            # Suggestion settings
            github_token=data.get("github_token"),
            github_org=data.get("github_org"),
            suggestion_min_coverage=data.get("suggestion_min_coverage", 0.8),
            ollama_model=data.get("ollama_model", "llama3.2"),
            ollama_base_url=data.get("ollama_base_url", "http://localhost:11434"),
            suggestion_lookback_commits=data.get("suggestion_lookback_commits", 100),
            suggest_cache_path=data.get(
                "suggest_cache_path", ".codeowners-suggest-cache.json"
            ),
        )

    @staticmethod
    def default_exclusions() -> List[str]:
        """
        Default exclusion patterns.

        These are common build artifacts and dependency directories
        that typically don't need CODEOWNERS coverage.

        Returns:
            List of default exclusion patterns
        """
        return [
            # Python artifacts
            "**/__pycache__/**",
            "**/*.pyc",
            "**/*.pyo",
            "**/*.egg-info/**",
            ".venv/**",
            ".tox/**",
            ".pytest_cache/**",
            ".mypy_cache/**",
            # JavaScript artifacts
            "node_modules/**",
            "dist/**",
            "build/**",
            "**/coverage/**",
            # Version control
            ".git/**",
            # Build outputs
            "htmlcov/**",
            ".coverage",
        ]
