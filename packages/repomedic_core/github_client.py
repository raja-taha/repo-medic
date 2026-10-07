from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import git
from github import Auth, Github, GithubException

from repomedic_core.config import get_settings
from repomedic_core.logging import get_logger

logger = get_logger(__name__)

ISSUE_URL_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)",
    re.IGNORECASE,
)


@dataclass
class IssueData:
    owner: str
    repo: str
    number: int
    title: str
    body: str
    labels: list[str]
    author: str | None
    html_url: str
    raw: dict


def parse_issue_url(url: str) -> tuple[str, str, int]:
    match = ISSUE_URL_RE.search(str(url))
    if not match:
        raise ValueError(f"Invalid GitHub issue URL: {url}")
    return match.group("owner"), match.group("repo"), int(match.group("number"))


class GitHubService:
    def __init__(self, token: str | None = None) -> None:
        settings = get_settings()
        self.token = token or settings.github_token
        self._client: Github | None = None

    @property
    def client(self) -> Github:
        if self._client is None:
            if self.token:
                self._client = Github(auth=Auth.Token(self.token))
            else:
                self._client = Github()
        return self._client

    def fetch_issue(self, owner: str, repo: str, number: int) -> IssueData:
        try:
            repository = self.client.get_repo(f"{owner}/{repo}")
            issue = repository.get_issue(number)
        except GithubException as exc:
            raise RuntimeError(f"Failed to fetch issue {owner}/{repo}#{number}: {exc}") from exc

        labels = [label.name for label in issue.labels]
        return IssueData(
            owner=owner,
            repo=repo,
            number=number,
            title=issue.title or "",
            body=issue.body or "",
            labels=labels,
            author=issue.user.login if issue.user else None,
            html_url=issue.html_url,
            raw={
                "id": issue.id,
                "number": issue.number,
                "state": issue.state,
                "labels": labels,
            },
        )

    def clone_repository(
        self,
        owner: str,
        repo: str,
        dest: Path,
        depth: int = 1,
    ) -> str:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            repository = git.Repo(dest)
            return repository.head.commit.hexsha

        if self.token:
            url = f"https://x-access-token:{self.token}@github.com/{owner}/{repo}.git"
        else:
            url = f"https://github.com/{owner}/{repo}.git"

        logger.info("cloning_repository", owner=owner, repo=repo, dest=str(dest))
        repository = git.Repo.clone_from(url, dest, depth=depth)
        # Rewrite remote to avoid leaking token in .git/config
        if self.token:
            repository.remotes.origin.set_url(f"https://github.com/{owner}/{repo}.git")
        return repository.head.commit.hexsha

    def create_draft_pr(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> str | None:
        settings = get_settings()
        if not settings.allow_auto_pr:
            logger.info("auto_pr_disabled")
            return None
        repository = self.client.get_repo(f"{owner}/{repo}")
        pr = repository.create_pull(title=title, body=body, head=head, base=base, draft=True)
        return pr.html_url


def sanitize_repo_name(name: str) -> str:
    parsed = urlparse(name)
    if parsed.path:
        return parsed.path.strip("/")
    return name.strip("/")