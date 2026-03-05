"""Tests for directory consolidation functionality."""

from __future__ import annotations

from codeowners_coverage.directory_consolidator import DirectoryConsolidator


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
    """Test that mixed ownership doesn't consolidate."""
    consolidator = DirectoryConsolidator(min_coverage=0.8)

    file_owners = {
        "src/mixed/file1.tsx": ["@frontend-team"],
        "src/mixed/file2.py": ["@backend-team"],
        "src/mixed/file3.tsx": ["@frontend-team"],
    }

    patterns = consolidator.consolidate(file_owners)

    # Should not consolidate (only 2/3 = 66% < 80%)
    # Each file should have its own pattern
    assert len(patterns) == 3


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
