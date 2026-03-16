"""Tests for directory consolidation functionality."""

from __future__ import annotations

from codeowners_coverage.directory_consolidator import (
    DirectoryConsolidator,
    FileOwnership,
)


# ------------------------------------------------------------------
# Legacy list-of-teams interface (backward-compatible)
# ------------------------------------------------------------------


def test_consolidate_simple_directory() -> None:
    """Test consolidation of files in same directory with same owner."""
    consolidator = DirectoryConsolidator(min_coverage=0.8)

    file_owners = {
        "src/frontend/file1.tsx": ["@frontend-team"],
        "src/frontend/file2.tsx": ["@frontend-team"],
        "src/frontend/file3.tsx": ["@frontend-team"],
    }

    patterns = consolidator.consolidate(file_owners)

    # Should consolidate to directory pattern
    assert any(p.pattern == "src/frontend/**" for p in patterns)
    assert any(p.teams == ["@frontend-team"] for p in patterns)


def test_consolidate_mixed_ownership() -> None:
    """Test that mixed ownership doesn't consolidate at directory level."""
    consolidator = DirectoryConsolidator(min_coverage=0.8)

    file_owners = {
        "src/mixed/file1.tsx": ["@frontend-team"],
        "src/mixed/file2.py": ["@backend-team"],
        "src/mixed/file3.tsx": ["@frontend-team"],
    }

    patterns = consolidator.consolidate(file_owners)

    # Should not consolidate (only 2/3 = 66% < 80%)
    # Files are deep (depth 2), so they get heuristic directory patterns
    assert len(patterns) >= 1
    # No individual file patterns since depth > 1
    assert all("**" in p.pattern for p in patterns)


def test_consolidate_nested_directories() -> None:
    """Test consolidation with nested directory structure."""
    consolidator = DirectoryConsolidator(min_coverage=0.8)

    file_owners = {
        "src/api/v1/endpoint1.py": ["@backend-team"],
        "src/api/v1/endpoint2.py": ["@backend-team"],
        "src/api/v2/endpoint3.py": ["@backend-team"],
        "src/api/v2/endpoint4.py": ["@backend-team"],
    }

    patterns = consolidator.consolidate(file_owners)

    # Should consolidate to highest level directory
    assert any("src/api" in p.pattern for p in patterns)


def test_consolidate_empty_input() -> None:
    """Test consolidation with no files."""
    consolidator = DirectoryConsolidator()

    patterns = consolidator.consolidate({})

    assert patterns == []


def test_consolidate_confidence_scores() -> None:
    """Test that confidence scores are calculated correctly."""
    consolidator = DirectoryConsolidator(min_coverage=0.8)

    file_owners = {
        "src/dir/file1.py": ["@team1"],
        "src/dir/file2.py": ["@team1"],
        "src/dir/file3.py": ["@team1"],
        "src/dir/file4.py": ["@team1"],
        "src/dir/file5.py": ["@team2"],  # 1 different
    }

    patterns = consolidator.consolidate(file_owners)

    # Should still consolidate (4/5 = 80%)
    consolidated = [p for p in patterns if "**" in p.pattern]
    assert len(consolidated) > 0
    assert consolidated[0].confidence == 0.8


def test_consolidate_multiple_teams() -> None:
    """Test consolidation with files owned by multiple teams."""
    consolidator = DirectoryConsolidator(min_coverage=0.8)

    file_owners = {
        "src/shared/file1.py": ["@team1", "@team2"],
        "src/shared/file2.py": ["@team1", "@team2"],
        "src/shared/file3.py": ["@team1", "@team2"],
    }

    patterns = consolidator.consolidate(file_owners)

    # Should consolidate with both teams
    assert any(
        p.pattern == "src/shared/**" and set(p.teams) == {"@team1", "@team2"}
        for p in patterns
    )


# ------------------------------------------------------------------
# Deep file grouping / max_single_file_depth
# ------------------------------------------------------------------


def test_deep_file_gets_directory_pattern() -> None:
    """Deeply nested files should never get individual file patterns."""
    consolidator = DirectoryConsolidator(min_coverage=0.8, max_single_file_depth=1)

    file_owners = {
        "static/app/components/searchQueryBuilder/tokens/filter/parsers/duration/grammar.pegjs": [
            "@frontend-team"
        ],
    }

    patterns = consolidator.consolidate(file_owners)

    assert len(patterns) == 1
    p = patterns[0]
    # Must be a directory pattern, not the individual file
    assert "**" in p.pattern
    assert p.teams == ["@frontend-team"]
    # Should group at a reasonable depth (first 3 dir components)
    assert p.pattern == "static/app/components/**"


def test_shallow_file_gets_file_pattern() -> None:
    """Root-level files should keep individual file patterns."""
    consolidator = DirectoryConsolidator(min_coverage=0.8, max_single_file_depth=1)

    file_owners = {
        "CLAUDE.md": ["@platform-team"],
    }

    patterns = consolidator.consolidate(file_owners)

    assert len(patterns) == 1
    assert patterns[0].pattern == "CLAUDE.md"
    assert patterns[0].teams == ["@platform-team"]


def test_depth_one_file_gets_file_pattern() -> None:
    """Files at depth 1 (one directory deep) keep individual patterns with default settings."""
    consolidator = DirectoryConsolidator(min_coverage=0.8, max_single_file_depth=1)

    file_owners = {
        "scripts/deploy.sh": ["@infra-team"],
    }

    patterns = consolidator.consolidate(file_owners)

    assert len(patterns) == 1
    assert patterns[0].pattern == "scripts/deploy.sh"


def test_depth_two_file_gets_directory_pattern() -> None:
    """Files at depth 2 (two dirs deep) get grouped with default max_single_file_depth=1."""
    consolidator = DirectoryConsolidator(min_coverage=0.8, max_single_file_depth=1)

    file_owners = {
        "tests/sentry/notifications/test_apps.py": ["@alerts-notifications"],
    }

    patterns = consolidator.consolidate(file_owners)

    assert len(patterns) == 1
    p = patterns[0]
    assert "**" in p.pattern
    assert p.teams == ["@alerts-notifications"]


def test_max_single_file_depth_adjustable() -> None:
    """max_single_file_depth=2 allows depth-2 files to have individual patterns."""
    consolidator = DirectoryConsolidator(min_coverage=0.8, max_single_file_depth=2)

    file_owners = {
        "tests/sentry/test_main.py": ["@backend-team"],
    }

    patterns = consolidator.consolidate(file_owners)

    assert len(patterns) == 1
    # depth is 2 (tests/sentry/), equals threshold, so individual pattern
    assert patterns[0].pattern == "tests/sentry/test_main.py"


# ------------------------------------------------------------------
# LLM-suggested patterns via FileOwnership
# ------------------------------------------------------------------


def test_suggested_pattern_used_for_unconsolidated_files() -> None:
    """LLM-suggested patterns should be used when files can't be directory-consolidated."""
    consolidator = DirectoryConsolidator(min_coverage=0.8)

    file_owners = {
        "static/app/components/sqb/tokens/filter/grammar.pegjs": FileOwnership(
            teams=["@frontend-team"],
            suggested_pattern="static/app/components/sqb/**",
        ),
        "static/app/components/sqb/tokens/filter/utils.ts": FileOwnership(
            teams=["@frontend-team"],
            suggested_pattern="static/app/components/sqb/**",
        ),
    }

    patterns = consolidator.consolidate(file_owners)

    # The two files share the same suggested pattern, so they should be merged
    sqb = [p for p in patterns if "sqb" in p.pattern]
    assert len(sqb) >= 1
    assert sqb[0].teams == ["@frontend-team"]
    assert sqb[0].file_count >= 2 or sqb[0].pattern.endswith("/**")


def test_suggested_pattern_groups_different_dirs() -> None:
    """Files from different subdirs but same suggested pattern get grouped."""
    consolidator = DirectoryConsolidator(min_coverage=0.8)

    file_owners = {
        "src/feature/sub1/a.py": FileOwnership(
            teams=["@team-a"],
            suggested_pattern="src/feature/**",
        ),
        "src/feature/sub2/b.py": FileOwnership(
            teams=["@team-a"],
            suggested_pattern="src/feature/**",
        ),
    }

    patterns = consolidator.consolidate(file_owners)

    feature_patterns = [p for p in patterns if p.pattern == "src/feature/**"]
    assert len(feature_patterns) >= 1
    assert feature_patterns[0].teams == ["@team-a"]


def test_mixed_fileownership_and_list() -> None:
    """consolidate() should accept both FileOwnership and plain list values."""
    consolidator = DirectoryConsolidator(min_coverage=0.8)

    file_owners = {
        "src/a/file1.py": ["@team-a"],
        "src/a/file2.py": FileOwnership(teams=["@team-a"]),
        "src/a/file3.py": ["@team-a"],
    }

    patterns = consolidator.consolidate(file_owners)

    assert any(p.pattern == "src/a/**" for p in patterns)


def test_heuristic_grouping_depth() -> None:
    """Heuristic grouping uses first 3 dir components for very deep paths."""
    consolidator = DirectoryConsolidator(min_coverage=0.8, max_single_file_depth=1)

    file_owners = {
        "a/b/c/d/e/f/g.py": ["@team-x"],
    }

    patterns = consolidator.consolidate(file_owners)

    assert len(patterns) == 1
    assert patterns[0].pattern == "a/b/c/**"
