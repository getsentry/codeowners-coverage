"""GitHub API client for team data."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import requests


@dataclass
class TeamValidationError:
    """A team referenced in CODEOWNERS that failed validation."""

    team: str  # e.g. @getsentry/enterprise
    line_numbers: List[int] = field(default_factory=list)
    reason: str = ""


class GitHubClient:
    """GitHub API client for team data."""

    def __init__(self, token: str | None = None, org: str | None = None) -> None:
        """
        Initialize GitHub client.

        Args:
            token: GitHub API token (required for API access)
            org: Organization name (auto-detected from git remote if None)
        """
        self.token = token
        self.org = org or self.detect_org_from_remote()
        self.base_url = "https://api.github.com"
        self._team_cache: Dict[str, List[str]] = {}  # team_slug → member emails
        self._teams_list: List[str] | None = None  # Cached team list

        if not self.token:
            raise ValueError(
                "GitHub Personal Access Token is required. "
                "Create one at https://github.com/settings/tokens with 'read:org' scope. "
                "Set GITHUB_TOKEN env var or pass --github-token."
            )

    def detect_org_from_remote(self) -> str:
        """
        Parse organization name from git remote.

        Supports formats:
        - git@github.com:myorg/repo.git
        - https://github.com/myorg/repo.git

        Returns:
            Organization name

        Raises:
            ValueError: If unable to parse org from remote
        """
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=True,
            )
            remote_url = result.stdout.strip()

            # Try SSH format: git@github.com:org/repo.git
            ssh_match = re.match(r"git@github\.com:([^/]+)/", remote_url)
            if ssh_match:
                return ssh_match.group(1)

            # Try HTTPS format: https://github.com/org/repo.git
            https_match = re.match(r"https://github\.com/([^/]+)/", remote_url)
            if https_match:
                return https_match.group(1)

            raise ValueError(f"Unable to parse org from remote URL: {remote_url}")

        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to get git remote: {e}")

    def list_teams(self) -> List[str]:
        """
        Fetch all teams in organization.

        API call: GET /orgs/{org}/teams

        Returns:
            List of team slugs

        Raises:
            requests.HTTPError: If API call fails
        """
        if self._teams_list is not None:
            return self._teams_list

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        url = f"{self.base_url}/orgs/{self.org}/teams"
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        teams = response.json()
        self._teams_list = [team["slug"] for team in teams]
        return self._teams_list

    def get_team_members(self, team_slug: str) -> List[str]:
        """
        Get member emails for a team.

        API call: GET /orgs/{org}/teams/{team_slug}/members

        Returns:
            List of member emails

        Raises:
            requests.HTTPError: If API call fails
        """
        # Check cache first
        if team_slug in self._team_cache:
            return self._team_cache[team_slug]

        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        url = f"{self.base_url}/orgs/{self.org}/teams/{team_slug}/members"
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        members = response.json()

        # Extract emails from members
        # Note: GitHub API doesn't always expose emails directly
        # We'll use login as fallback and try to get email from user endpoint
        emails = []
        for member in members:
            user_email = self._get_user_email(member["login"])
            if user_email:
                emails.append(user_email)

        # Cache the result
        self._team_cache[team_slug] = emails
        return emails

    def _get_user_email(self, username: str) -> str | None:
        """
        Get user's email from their profile.

        API call: GET /users/{username}

        Returns:
            User's email if available, None otherwise
        """
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        url = f"{self.base_url}/users/{username}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        user_data = response.json()
        # Email might not be public
        return user_data.get("email") or f"{username}@users.noreply.github.com"

    def validate_teams(
        self,
        teams_with_lines: Dict[str, List[int]],
    ) -> List[TeamValidationError]:
        """
        Validate that all @org/team entries in CODEOWNERS exist.

        Only validates entries in @org/team format (skips individual @usernames).
        Fetches the full team list upfront, then checks each slug against it.

        Note: Secret teams not visible to the token will appear as not found.
        The token needs read:org scope (and SSO authorization if applicable).

        Args:
            teams_with_lines: Mapping of owner string → line numbers (from matcher)

        Returns:
            List of TeamValidationError for any teams not found
        """
        errors: List[TeamValidationError] = []

        org_teams = {
            owner: lines
            for owner, lines in teams_with_lines.items()
            if "/" in owner.lstrip("@")
        }
        if not org_teams:
            return errors

        visible_slugs = self._list_visible_team_slugs()

        for owner, line_numbers in sorted(org_teams.items()):
            _, team_slug = owner.lstrip("@").split("/", 1)

            if team_slug not in visible_slugs:
                errors.append(
                    TeamValidationError(
                        team=owner,
                        line_numbers=line_numbers,
                        reason="team not found in organization",
                    )
                )

        return errors

    def _list_visible_team_slugs(self) -> Set[str]:
        """
        Fetch all team slugs visible to the authenticated token.

        Includes public teams and private/secret teams the token has access to.
        Uses pagination to retrieve all teams.
        """
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

        slugs: Set[str] = set()
        page = 1
        while True:
            url = f"{self.base_url}/orgs/{self.org}/teams"
            response = requests.get(url, headers=headers, params={"per_page": 100, "page": page})
            if response.status_code == 403:
                raise PermissionError(
                    "token lacks read:org scope — skipping team validation"
                )
            response.raise_for_status()
            teams = response.json()
            if not teams:
                break
            for team in teams:
                slugs.add(team["slug"])
            if len(teams) < 100:
                break
            page += 1

        return slugs

    def build_contributor_team_map(
        self,
        contributor_emails: Set[str],
    ) -> Dict[str, List[str]]:
        """
        Map contributor emails to their teams.

        Args:
            contributor_emails: Set of unique contributor emails from git history

        Returns:
            Dict mapping email → list of teams (with @ prefix)

        Strategy:
        1. Fetch all teams (one API call, cached)
        2. For each team, fetch members (N API calls, but cached)
        3. Build reverse mapping: email → teams
        """
        # Get all teams
        teams = self.list_teams()

        # Build email → teams mapping
        email_to_teams: Dict[str, List[str]] = {email: [] for email in contributor_emails}

        for team_slug in teams:
            team_members = self.get_team_members(team_slug)

            # Add this team to each matching contributor
            for email in contributor_emails:
                if email in team_members:
                    # Add @ prefix to team name for CODEOWNERS format
                    email_to_teams[email].append(f"@{team_slug}")

        return email_to_teams
