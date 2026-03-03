"""CLI interface for codeowners-coverage."""

from __future__ import annotations

import json
import sys
from typing import List, Tuple

import click

from .checker import CoverageChecker
from .config import Config


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """CODEOWNERS coverage checking tool."""
    pass


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output JSON format")
@click.option("--files", multiple=True, help="Specific files to check")
@click.option("--config", default=".codeowners-config.yml", help="Config file path")
def check(output_json: bool, files: Tuple[str, ...], config: str) -> None:
    """
    Check CODEOWNERS coverage.

    Validates that all files in the repository have CODEOWNERS coverage.
    Files in the baseline are allowed to be uncovered.
    New uncovered files will cause the check to fail.
    """
    try:
        cfg = Config.load(config)
        checker = CoverageChecker(cfg)

        file_list: List[str] | None = list(files) if files else None
        result = checker.check_coverage(file_list)

        if output_json:
            click.echo(json.dumps(result, indent=2))
        else:
            _print_human_readable_result(result)

        # Exit with error if there are new uncovered files
        if result["uncovered_files"]:
            sys.exit(1)

        # Exit with code 2 if baseline can be reduced (positive signal)
        # Check if any baseline files are now covered
        baseline_set = set(result["baseline_files"])
        current_uncovered = checker.generate_baseline(file_list)
        current_uncovered_set = set(current_uncovered)

        if len(baseline_set - current_uncovered_set) > 0:
            if not output_json:
                removable_files = sorted(baseline_set - current_uncovered_set)
                click.echo(f"\n🎉 Great news! {len(removable_files)} files can be removed from the baseline:")
                for f in removable_files[:10]:  # Show first 10
                    click.echo(f"  - {f}")
                if len(removable_files) > 10:
                    click.echo(f"  ... and {len(removable_files) - 10} more")
                click.echo("\nThese files now have CODEOWNERS coverage! Update the baseline:")
                click.echo("  codeowners-coverage baseline")
            sys.exit(2)

    except FileNotFoundError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--config", default=".codeowners-config.yml", help="Config file path")
@click.option("--files", multiple=True, help="Specific files to check")
def baseline(config: str, files: Tuple[str, ...]) -> None:
    """
    Generate or update baseline file of uncovered files.

    Creates a baseline of all currently uncovered files. This allows
    incremental improvement by preventing new uncovered files while
    allowing existing gaps.
    """
    try:
        cfg = Config.load(config)
        checker = CoverageChecker(cfg)

        file_list: List[str] | None = list(files) if files else None
        baseline_files = checker.generate_baseline(file_list)

        # Write baseline
        checker.write_baseline(baseline_files)

        click.echo(f"✅ Baseline written to {cfg.baseline_path}")
        click.echo(f"📊 {len(baseline_files)} uncovered files in baseline")

        if baseline_files:
            click.echo(f"\n💡 Goal: Reduce this list to zero by adding CODEOWNERS coverage")

    except FileNotFoundError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)


def _print_human_readable_result(result: dict) -> None:
    """Print coverage check result in human-readable format."""
    total = result["total_files"]
    covered = result["covered_files"]
    uncovered = result["uncovered_files"]
    baseline = result["baseline_files"]
    percentage = result["coverage_percentage"]

    if uncovered:
        click.echo("❌ CODEOWNERS Coverage Check Failed\n")
        click.echo(f"The following {len(uncovered)} files lack CODEOWNERS coverage:")
        for f in uncovered:
            click.echo(f"  - {f}")
        click.echo("\nPlease add these files to .github/CODEOWNERS with appropriate owners.")
        click.echo("\n💡 Need help? Check the team mapping in the CODEOWNERS file")
        click.echo(f"\n📊 Current status: {len(baseline)} files in baseline (unchanged)")
    else:
        click.echo(f"✅ CODEOWNERS Coverage: {percentage:.1f}% ({covered}/{total} files covered)")
        if baseline:
            click.echo(f"\n💡 Baseline: {len(baseline)} files still need coverage")
