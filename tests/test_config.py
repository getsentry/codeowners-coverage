"""Tests for configuration loading."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from codeowners_coverage.config import Config


def test_default_config() -> None:
    """Test default configuration values."""
    config = Config()

    assert config.codeowners_path == ".github/CODEOWNERS"
    assert config.baseline_path == ".github/codeowners-coverage-baseline.txt"
    assert isinstance(config.exclusions, list)


def test_load_missing_config() -> None:
    """Test loading config when file doesn't exist."""
    config = Config.load("/nonexistent/config.yml")

    # Should return default config
    assert config.codeowners_path == ".github/CODEOWNERS"
    assert config.baseline_path == ".github/codeowners-coverage-baseline.txt"
    assert config.exclusions == Config.default_exclusions()


def test_load_config_from_yaml() -> None:
    """Test loading configuration from YAML file."""
    yaml_content = """
codeowners_path: "custom/CODEOWNERS"
baseline_path: "custom/baseline.txt"
exclusions:
  - "*.log"
  - "temp/**"
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yml") as f:
        f.write(yaml_content)
        temp_config = f.name

    config = Config.load(temp_config)

    assert config.codeowners_path == "custom/CODEOWNERS"
    assert config.baseline_path == "custom/baseline.txt"
    assert "*.log" in config.exclusions
    assert "temp/**" in config.exclusions

    Path(temp_config).unlink()


def test_load_partial_config() -> None:
    """Test loading config with only some values specified."""
    yaml_content = """
codeowners_path: "my/CODEOWNERS"
"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yml") as f:
        f.write(yaml_content)
        temp_config = f.name

    config = Config.load(temp_config)

    # Custom value
    assert config.codeowners_path == "my/CODEOWNERS"

    # Default values
    assert config.baseline_path == ".github/codeowners-coverage-baseline.txt"
    assert config.exclusions == Config.default_exclusions()

    Path(temp_config).unlink()


def test_load_empty_yaml() -> None:
    """Test loading empty YAML file."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yml") as f:
        f.write("")
        temp_config = f.name

    config = Config.load(temp_config)

    # Should use all defaults
    assert config.codeowners_path == ".github/CODEOWNERS"
    assert config.baseline_path == ".github/codeowners-coverage-baseline.txt"
    assert config.exclusions == Config.default_exclusions()

    Path(temp_config).unlink()


def test_default_exclusions() -> None:
    """Test that default exclusions include common patterns."""
    exclusions = Config.default_exclusions()

    # Python artifacts
    assert "**/__pycache__/**" in exclusions
    assert "**/*.pyc" in exclusions
    assert ".venv/**" in exclusions

    # JavaScript artifacts
    assert "node_modules/**" in exclusions
    assert "dist/**" in exclusions

    # Version control
    assert ".git/**" in exclusions
