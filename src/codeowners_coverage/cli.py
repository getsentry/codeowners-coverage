"""CLI interface for codeowners-coverage."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

import click

from .checker import CoverageChecker
from .config import Config
from .directory_consolidator import DirectoryConsolidator
from .git_analyzer import GitHistoryAnalyzer
from .github_client import GitHubClient, TeamValidationError
from .matcher import CodeOwnersPatternMatcher
from .ollama_matcher import OllamaLLMMatcher, TeamSuggestion
from .suggest_cache import SuggestCache
from .suggester import OwnershipSuggester, SuggestionResult
from . import __version__


@click.group()
@click.version_option(version=__version__)
def cli() -> None:
    """CODEOWNERS coverage checking tool."""
    pass


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output JSON format")
@click.option("--files", multiple=True, help="Specific files to check")
@click.option("--config", default=".codeowners-config.yml", help="Config file path")
@click.option(
    "--github-token", envvar="GITHUB_TOKEN",
    help="GitHub token for team validation (needs read:org scope). "
    "Auto-provided in GitHub Actions via GITHUB_TOKEN env var.",
)
def check(
    output_json: bool,
    files: Tuple[str, ...],
    config: str,
    github_token: str | None,
) -> None:
    """
    Check CODEOWNERS coverage.

    Validates that all files in the repository have CODEOWNERS coverage.
    Files in the baseline are allowed to be uncovered.
    New uncovered files will cause the check to fail.

    When a GitHub token is provided (or GITHUB_TOKEN env var is set),
    also validates that every team referenced in CODEOWNERS exists and
    has at least one member.
    """
    try:
        cfg = Config.load(config)
        checker = CoverageChecker(cfg)

        file_list: List[str] | None = list(files) if files else None
        result = checker.check_coverage(file_list)

        # --- Team validation ---
        team_errors: List[TeamValidationError] = []
        token = github_token or cfg.github_token

        if token:
            try:
                matcher = CodeOwnersPatternMatcher(cfg.codeowners_path)
                github_client = GitHubClient(token=token, org=cfg.github_org)
                teams_with_lines = matcher.get_teams_with_lines()
                click.echo("🔍 Validating CODEOWNERS teams...")
                team_errors = github_client.validate_teams(teams_with_lines)
            except FileNotFoundError:
                pass  # CODEOWNERS missing — coverage check will also report it
            except ValueError as e:
                click.echo(f"⚠️  Team validation skipped: {e}", err=True)
            except PermissionError as e:
                click.echo(f"⚠️  Team validation skipped: {e}")
            except Exception as e:
                click.echo(f"⚠️  Team validation failed: {e}", err=True)
        else:
            if not output_json:
                click.echo(
                    "ℹ️  Team validation skipped (no GitHub token). "
                    "Set GITHUB_TOKEN or pass --github-token to enable.",
                    err=True,
                )

        if output_json:
            json_result = dict(result)
            json_result["team_errors"] = [
                {
                    "team": e.team,
                    "line_numbers": e.line_numbers,
                    "reason": e.reason,
                }
                for e in team_errors
            ]
            click.echo(json.dumps(json_result, indent=2))
        else:
            _print_human_readable_result(result)
            if team_errors:
                _print_team_validation_errors(team_errors)

        # Exit with error if there are new uncovered files or invalid teams
        if result["uncovered_files"] or team_errors:
            sys.exit(1)

        # Exit with code 2 if baseline can be reduced (positive signal)
        # Check if any baseline entries (literal paths or glob patterns)
        # no longer match any uncovered files
        loaded_baseline = checker._load_baseline()
        baseline_matched = cast(List[str], result["baseline_files"])
        unused_entries = loaded_baseline.get_unused_entries(baseline_matched)

        if unused_entries:
            if not output_json:
                click.echo(f"\n🎉 Great news! {len(unused_entries)} baseline entries can be removed:")
                for entry in unused_entries[:10]:
                    click.echo(f"  - {entry}")
                if len(unused_entries) > 10:
                    click.echo(f"  ... and {len(unused_entries) - 10} more")
                click.echo("\nThese entries now have CODEOWNERS coverage! Update the baseline:")
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
            click.echo("\n💡 Goal: Reduce this list to zero by adding CODEOWNERS coverage")

    except FileNotFoundError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--validate/--no-validate", default=True,
    help="Validate teams via GitHub API",
)
@click.option(
    "--min-coverage", default=0.8, type=float,
    help="Min coverage for directory consolidation",
)
@click.option(
    "--github-token", envvar="GITHUB_TOKEN",
    help="GitHub Personal Access Token (needs read:org scope)",
)
@click.option("--org", help="GitHub organization (auto-detected if not provided)")
@click.option("--apply", is_flag=True, help="Auto-apply suggestions to CODEOWNERS")
@click.option(
    "--format", "output_format",
    type=click.Choice(["interactive", "json", "diff"]),
    default="interactive", help="Output format",
)
@click.option("--ollama-model", default="llama3.2", help="Ollama model to use")
@click.option(
    "--ollama-url", default="http://localhost:11434",
    help="Ollama API endpoint",
)
@click.option(
    "--lookback", default=100, type=int,
    help="Number of commits to analyze",
)
@click.option(
    "--include-baseline/--no-baseline", default=True,
    help="Include baseline files in suggestions",
)
@click.option(
    "--config", default=".codeowners-config.yml",
    help="Config file path",
)
@click.option(
    "--cache-file", default=None,
    help="Cache file path (default: from config or "
    ".codeowners-suggest-cache.json)",
)
@click.option(
    "--no-cache", is_flag=True,
    help="Disable caching (fresh run)",
)
@click.option(
    "--clear-cache", is_flag=True,
    help="Delete existing cache before starting",
)
def suggest(
    validate: bool,
    min_coverage: float,
    github_token: str | None,
    org: str | None,
    apply: bool,
    output_format: str,
    ollama_model: str,
    ollama_url: str,
    lookback: int,
    include_baseline: bool,
    config: str,
    cache_file: str | None,
    no_cache: bool,
    clear_cache: bool,
) -> None:
    """
    Suggest CODEOWNERS entries for uncovered files using AI.

    Uses git history and local LLM (Ollama) to intelligently
    suggest team ownership. Results are cached incrementally so
    the command can be interrupted and restarted safely.

    By default, includes both new uncovered files AND baseline
    files. Use --no-baseline to only suggest for new uncovered
    files.

    Requires Ollama to be installed and running.
    """
    try:
        # Load config
        cfg = Config.load(config)

        # Override with CLI options
        cfg.github_token = github_token or cfg.github_token
        cfg.github_org = org or cfg.github_org
        cfg.suggestion_min_coverage = min_coverage
        cfg.ollama_model = ollama_model
        cfg.ollama_base_url = ollama_url
        cfg.suggestion_lookback_commits = lookback

        # Get uncovered files
        checker = CoverageChecker(cfg)
        result = checker.check_coverage()
        new_uncovered = cast(List[str], result["uncovered_files"])
        baseline_files = cast(List[str], result["baseline_files"])

        # Combine based on include_baseline flag
        if include_baseline:
            all_uncovered_files = new_uncovered + baseline_files
        else:
            all_uncovered_files = new_uncovered

        if not all_uncovered_files:
            click.echo("✅ All files have CODEOWNERS coverage!")
            sys.exit(0)

        click.echo(
            f"🔍 Found {len(all_uncovered_files)} uncovered files"
        )
        if new_uncovered:
            click.echo(
                f"   • {len(new_uncovered)} new uncovered files"
            )
        if baseline_files and include_baseline:
            click.echo(
                f"   • {len(baseline_files)} baseline files (included)"
            )
        elif baseline_files and not include_baseline:
            click.echo(
                f"   • {len(baseline_files)} baseline files (excluded)"
            )

        # Set up cache
        cache = _setup_cache(
            cfg, cache_file, no_cache, clear_cache,
            ollama_model, lookback, all_uncovered_files,
        )

        click.echo(
            "📊 Analyzing git history and team membership..."
        )

        # Initialize components
        git_analyzer = GitHistoryAnalyzer(
            lookback_commits=cfg.suggestion_lookback_commits
        )

        github_client = None
        if validate:
            if not cfg.github_token:
                click.echo(
                    "⚠️  GitHub Personal Access Token "
                    "not provided.",
                    err=True,
                )
                click.echo(
                    "   Create one at "
                    "https://github.com/settings/tokens "
                    "with 'read:org' scope.",
                    err=True,
                )
                click.echo(
                    "   Set via GITHUB_TOKEN env var "
                    "or --github-token flag.",
                    err=True,
                )
                click.echo(
                    "   Running without team validation "
                    "(degraded mode)."
                )
            else:
                try:
                    github_client = GitHubClient(
                        token=cfg.github_token,
                        org=cfg.github_org,
                    )
                    click.echo(
                        f"✓ Connected to GitHub "
                        f"(org: {github_client.org})"
                    )
                except Exception as e:
                    click.echo(
                        f"⚠️  GitHub connection failed: {e}",
                        err=True,
                    )
                    click.echo(
                        "   Running without team validation "
                        "(degraded mode)."
                    )

        try:
            llm_matcher = OllamaLLMMatcher(
                model=cfg.ollama_model,
                base_url=cfg.ollama_base_url,
            )
            click.echo(
                f"✓ Connected to Ollama "
                f"(model: {cfg.ollama_model})"
            )
        except Exception as e:
            click.echo(
                f"❌ Failed to connect to Ollama: {e}",
                err=True,
            )
            click.echo(
                "   Is Ollama running? "
                "Check: http://localhost:11434"
            )
            sys.exit(1)

        consolidator = DirectoryConsolidator(
            min_coverage=cfg.suggestion_min_coverage
        )

        # Try to load existing CODEOWNERS for context
        matcher = None
        try:
            matcher = CodeOwnersPatternMatcher(
                cfg.codeowners_path
            )
        except FileNotFoundError:
            click.echo("⚠️  No existing CODEOWNERS file found")

        # Report team allowlist
        if output_format == "interactive":
            if cfg.team_allowlist:
                click.echo(
                    f"✓ Team allowlist (config): "
                    f"{len(cfg.team_allowlist)} teams"
                )
            elif matcher:
                teams = matcher.get_all_teams()
                if teams:
                    click.echo(
                        f"✓ Team allowlist (from CODEOWNERS): "
                        f"{len(teams)} teams"
                    )

        # Create suggester
        suggester = OwnershipSuggester(
            config=cfg,
            git_analyzer=git_analyzer,
            github_client=github_client,
            llm_matcher=llm_matcher,
            consolidator=consolidator,
            matcher=matcher,
            cache=cache,
        )

        # Generate suggestions
        click.echo("\n🤖 Generating suggestions with AI...")
        suggestions = suggester.suggest_for_uncovered_files(
            all_uncovered_files,
            progress_callback=_suggest_progress,
        )

        # Output results
        if output_format == "json":
            _print_suggestions_json(suggestions)
        elif output_format == "diff":
            _print_suggestions_diff(suggestions)
        else:
            _print_suggestions_interactive(suggestions)

        # Apply if requested
        if apply:
            _apply_suggestions(cfg, suggestions)

    except FileNotFoundError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _setup_cache(
    cfg: Config,
    cache_file: str | None,
    no_cache: bool,
    clear_cache: bool,
    ollama_model: str,
    lookback: int,
    files: List[str],
) -> SuggestCache | None:
    """Load or initialize the suggest cache."""
    if no_cache:
        click.echo("   Cache: disabled (--no-cache)")
        return None

    cache_path = cache_file or cfg.suggest_cache_path

    if clear_cache:
        p = Path(cache_path)
        if p.exists():
            p.unlink()
            click.echo(f"   Cache: cleared {cache_path}")
        else:
            click.echo("   Cache: nothing to clear")

    cache = SuggestCache.load(cache_path)

    messages = cache.invalidate_if_params_changed(
        ollama_model, lookback
    )
    for msg in messages:
        click.echo(f"   ⚠️  {msg}")

    cached = cache.count_cached_suggestions(files)
    remaining = len(files) - cached
    if cached > 0:
        click.echo(
            f"   Cache: {cached}/{len(files)} files already "
            f"processed, {remaining} remaining"
        )
    else:
        click.echo(f"   Cache: {cache_path} (empty or new)")

    return cache


def _suggest_progress(
    current: int,
    total: int,
    filepath: str,
    suggestion: TeamSuggestion,
) -> None:
    """Print progress for each LLM suggestion."""
    conf = f"{suggestion.confidence:.2f}"
    click.echo(
        f"   [{current}/{total}] {filepath} "
        f"-> {suggestion.team} ({conf})"
    )


def _print_suggestions_interactive(suggestions: SuggestionResult) -> None:
    """Print suggestions in interactive format."""
    click.echo(f"\n📋 Generated {len(suggestions.patterns)} suggested patterns:")
    click.echo(f"   ({suggestions.files_with_suggestions}/{suggestions.total_files} files have confident suggestions)\n")

    for pattern in suggestions.patterns:
        teams_str = " ".join(pattern.teams)
        confidence_pct = pattern.confidence * 100
        click.echo(f"  {pattern.pattern:<50} {teams_str}")
        click.echo(f"    ↳ {pattern.file_count} files, {confidence_pct:.0f}% confidence\n")


def _print_suggestions_json(suggestions: SuggestionResult) -> None:
    """Print suggestions as JSON."""
    output = {
        "patterns": [
            {
                "pattern": p.pattern,
                "teams": p.teams,
                "file_count": p.file_count,
                "confidence": p.confidence,
            }
            for p in suggestions.patterns
        ],
        "total_files": suggestions.total_files,
        "files_with_suggestions": suggestions.files_with_suggestions,
    }
    click.echo(json.dumps(output, indent=2))


def _print_suggestions_diff(suggestions: SuggestionResult) -> None:
    """Print suggestions as diff format."""
    click.echo("# Suggested CODEOWNERS entries")
    click.echo("# Generated by codeowners-coverage suggest")
    click.echo(f"# Date: {datetime.now().isoformat()}\n")

    for pattern in suggestions.patterns:
        teams_str = " ".join(pattern.teams)
        confidence_pct = pattern.confidence * 100
        click.echo(f"# {pattern.file_count} files, {confidence_pct:.0f}% confidence")
        click.echo(f"{pattern.pattern} {teams_str}\n")


def _apply_suggestions(cfg: Config, suggestions: SuggestionResult) -> None:
    """Apply suggestions to CODEOWNERS file."""
    codeowners_path = Path(cfg.codeowners_path)

    # Create backup
    if codeowners_path.exists():
        backup_path = f"{cfg.codeowners_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        import shutil
        shutil.copy(codeowners_path, backup_path)
        click.echo(f"\n💾 Backup created: {backup_path}")

    # Append suggestions
    with open(codeowners_path, "a") as f:
        f.write("\n# AI-generated suggestions\n")
        f.write(f"# Generated by codeowners-coverage suggest on {datetime.now().isoformat()}\n\n")

        for pattern in suggestions.patterns:
            teams_str = " ".join(pattern.teams)
            confidence_pct = pattern.confidence * 100
            f.write(f"# {pattern.file_count} files, {confidence_pct:.0f}% confidence\n")
            f.write(f"{pattern.pattern} {teams_str}\n\n")

    click.echo(f"✅ Suggestions applied to {cfg.codeowners_path}")


def _print_team_validation_errors(errors: List[TeamValidationError]) -> None:
    """Print team validation errors in human-readable format."""
    click.echo(f"\n❌ CODEOWNERS Team Validation Failed\n")
    click.echo(f"The following {len(errors)} team(s) are invalid:\n")
    for error in errors:
        lines_str = ", ".join(str(n) for n in error.line_numbers)
        line_label = "line" if len(error.line_numbers) == 1 else "lines"
        click.echo(f"  {error.team} ({line_label}: {lines_str})")
        click.echo(f"    reason: {error.reason}")
    click.echo()


def _print_human_readable_result(result: Dict[str, Any]) -> None:
    """Print coverage check result in human-readable format."""
    total = result["total_files"]
    covered = result["covered_files"]
    uncovered = result["uncovered_files"]
    baseline = result["baseline_files"]
    percentage = result["coverage_percentage"]

    effective_pct = ((total - len(uncovered)) / total * 100) if total > 0 else 100.0

    if uncovered:
        click.echo("❌ CODEOWNERS Coverage Check Failed\n")
        click.echo(f"The following {len(uncovered)} files lack CODEOWNERS coverage:")
        for f in uncovered:
            click.echo(f"  - {f}")
        click.echo("\nPlease add these files to .github/CODEOWNERS with appropriate owners.")
        click.echo("\n💡 Need help? Check the team mapping in the CODEOWNERS file")
    else:
        click.echo("✅ CODEOWNERS Coverage Check Passed")

    click.echo(f"\n📊 Coverage: {percentage:.1f}% total ({covered}/{total} files covered)")
    if baseline:
        click.echo(f"   Excluding baseline: {effective_pct:.1f}% ({total - len(uncovered)}/{total} files)")
        click.echo(f"   Baseline: {len(baseline)} files still need coverage")
