"""Ollama LLM-based file-to-team matching."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Tuple

try:
    import ollama
except ImportError:
    ollama = None  # type: ignore[assignment]


@dataclass
class TeamSuggestion:
    """Suggested team ownership for a file."""

    filepath: str
    team: str
    confidence: float
    reasoning: str
    suggested_pattern: str | None = None


class OllamaLLMMatcher:
    """Use local Ollama LLM to intelligently match files to teams."""

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
    ) -> None:
        """
        Initialize Ollama client.

        Args:
            model: Ollama model to use (default: llama3.2)
            base_url: Ollama API endpoint

        Raises:
            Exception: If unable to connect to Ollama
        """
        if ollama is None:
            raise ImportError(
                "The 'ollama' package is required for the suggest command. "
                "Install it with: pip install codeowners-coverage[suggest]"
            )

        self.model = model
        self.base_url = base_url

        try:
            ollama.list()
        except Exception as e:
            raise Exception(
                f"Unable to connect to Ollama at {base_url}. "
                f"Is Ollama running? Error: {e}"
            )

    def match_file_to_team(
        self,
        filepath: str,
        contributors: List[Tuple[str, int]],
        contributor_teams: Dict[str, List[str]],
        existing_patterns: Dict[str, List[str]] | None = None,
        allowed_teams: List[str] | None = None,
    ) -> TeamSuggestion:
        """
        Use LLM to suggest team ownership with focused context.

        Args:
            filepath: File to assign ownership
            contributors: List of (email, commit_count) tuples
            contributor_teams: Mapping of contributor emails to their teams
            existing_patterns: Optional CODEOWNERS patterns for context
            allowed_teams: If provided, the LLM must pick from this list

        Returns:
            TeamSuggestion with team(s), confidence, reasoning
        """
        prompt = self._build_prompt(
            filepath, contributors, contributor_teams, existing_patterns, allowed_teams
        )

        # Call Ollama
        response = ollama.chat(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are helping assign CODEOWNERS for a repository. "
                    "Respond ONLY with valid JSON in the exact format requested.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        # Parse response
        return self._parse_response(
            filepath, response["message"]["content"], allowed_teams
        )

    def _build_prompt(
        self,
        filepath: str,
        contributors: List[Tuple[str, int]],
        contributor_teams: Dict[str, List[str]],
        existing_patterns: Dict[str, List[str]] | None,
        allowed_teams: List[str] | None = None,
    ) -> str:
        """
        Build optimized prompt with only relevant teams.

        Args:
            filepath: File path
            contributors: List of (email, commit_count) tuples
            contributor_teams: Email → teams mapping
            existing_patterns: Optional pattern → teams mapping
            allowed_teams: If provided, restrict team choices to this list

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            f"File: {filepath}",
            "",
        ]

        # Add contributors section
        if contributors:
            prompt_parts.append("Contributors (from git history):")
            for email, commit_count in contributors:
                teams = contributor_teams.get(email, [])
                if teams:
                    teams_str = ", ".join(teams)
                    prompt_parts.append(
                        f"- {email}: {commit_count} commits, member of [{teams_str}]"
                    )
                else:
                    prompt_parts.append(f"- {email}: {commit_count} commits, no teams found")
            prompt_parts.append("")

            # Find common teams
            common_teams, other_teams = self._filter_relevant_teams(contributor_teams)
            if common_teams:
                prompt_parts.append(f"All contributors are on: {', '.join(common_teams)}")
            if other_teams:
                prompt_parts.append(f"Additional teams: {', '.join(other_teams)}")
            prompt_parts.append("")
        else:
            prompt_parts.append("Contributors: (no git history - newly added file)")
            prompt_parts.append("")

        # Add team allowlist constraint
        if allowed_teams:
            prompt_parts.append(
                "IMPORTANT: You MUST choose from ONLY these teams: "
                + ", ".join(allowed_teams)
            )
            prompt_parts.append(
                "Do NOT invent new team names. Pick the closest match from the list above."
            )
            prompt_parts.append("")

        # Add existing patterns for context
        if existing_patterns:
            prompt_parts.append("Existing CODEOWNERS patterns (for context):")
            for pattern, teams in list(existing_patterns.items())[:10]:
                teams_str = " ".join(teams)
                prompt_parts.append(f"- {pattern} → {teams_str}")
            prompt_parts.append("")

        # Add instructions
        prompt_parts.extend(
            [
                "Based on the file path, contributors, and their team memberships, "
                "which team should own this file?",
                "",
                "Also suggest the best CODEOWNERS directory pattern for this file.",
                "Rules for the pattern:",
                "- Prefer directory-level patterns (ending with /**) over individual file paths.",
                "- Identify the logical component or feature boundary in the path.",
                '  For example, "static/app/components/searchQueryBuilder/tokens/filter/'
                'parsers/duration/grammar.pegjs"',
                '  should use pattern "static/app/components/searchQueryBuilder/**"',
                '  and "tests/sentry/notifications/test_apps.py" should use '
                '"tests/sentry/notifications/**".',
                "- Only use an individual file pattern for root-level files (depth 0-1) like "
                '"CLAUDE.md" or "migrations_lockfile.txt".',
                "",
                "Respond with JSON only (no markdown, no explanation):",
                "{",
                '  "team": "@team-name",',
                '  "pattern": "suggested/directory/**",',
                '  "confidence": 0.0-1.0,',
                '  "reasoning": "brief explanation"',
                "}",
            ]
        )

        return "\n".join(prompt_parts)

    def _filter_relevant_teams(
        self,
        contributor_teams: Dict[str, List[str]],
    ) -> Tuple[List[str], List[str]]:
        """
        Find teams common to all contributors and other teams.

        Args:
            contributor_teams: Email → teams mapping

        Returns:
            (common_teams, other_teams)
        """
        if not contributor_teams:
            return ([], [])

        # Get all teams across all contributors
        all_teams_lists = [teams for teams in contributor_teams.values() if teams]

        if not all_teams_lists:
            return ([], [])

        # Find intersection (teams all contributors are on)
        common = set(all_teams_lists[0])
        for teams in all_teams_lists[1:]:
            common &= set(teams)

        # Find union (all teams mentioned)
        all_teams = set()
        for teams in all_teams_lists:
            all_teams.update(teams)

        # Other teams = all teams - common teams
        other = all_teams - common

        return (sorted(common), sorted(other))

    @staticmethod
    def _normalize_team(team: str) -> str:
        """Strip '@' and any 'org/' prefix for fuzzy comparison."""
        t = team.lstrip("@").lower()
        if "/" in t:
            t = t.split("/", 1)[1]
        return t

    def _resolve_team(
        self,
        team: str,
        allowed_teams: List[str],
    ) -> str | None:
        """Match a team name against the allowlist, tolerating org-prefix differences.

        Returns the canonical allowlist entry if a match is found, else None.
        """
        if team in allowed_teams:
            return team

        norm = self._normalize_team(team)
        for canonical in allowed_teams:
            if self._normalize_team(canonical) == norm:
                return canonical

        return None

    def _parse_response(
        self,
        filepath: str,
        response: str,
        allowed_teams: List[str] | None = None,
    ) -> TeamSuggestion:
        """
        Parse LLM response into structured suggestion.

        Args:
            filepath: Original file path
            response: LLM response string
            allowed_teams: If provided, validate team against this list

        Returns:
            TeamSuggestion object

        Raises:
            ValueError: If response cannot be parsed
        """
        try:
            response = response.strip()

            # Remove markdown code blocks if present
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines)

            data = json.loads(response)

            team = data.get("team", "@unknown")
            confidence = float(data.get("confidence", 0.0))
            reasoning = data.get("reasoning", "No reasoning provided")
            suggested_pattern: str | None = data.get("pattern")

            # Validate team against allowlist (fuzzy on org prefix)
            if allowed_teams:
                resolved = self._resolve_team(team, allowed_teams)
                if resolved:
                    team = resolved
                else:
                    reasoning = (
                        f"LLM suggested '{team}' which is not in "
                        f"the team allowlist. "
                        f"Original reasoning: {reasoning}"
                    )
                    team = "@unknown"
                    confidence = 0.0

            return TeamSuggestion(
                filepath=filepath,
                team=team,
                confidence=confidence,
                reasoning=reasoning,
                suggested_pattern=suggested_pattern,
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return TeamSuggestion(
                filepath=filepath,
                team="@unknown",
                confidence=0.0,
                reasoning=f"Failed to parse LLM response: {e}",
            )
