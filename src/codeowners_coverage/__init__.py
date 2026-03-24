"""CODEOWNERS coverage checking tool."""

__version__ = "0.3.0"

from .checker import CoverageChecker
from .config import Config
from .matcher import CodeOwnersPatternMatcher

__all__ = ["CoverageChecker", "Config", "CodeOwnersPatternMatcher"]
