import os
from dataclasses import dataclass
from typing import Optional, List
from github import Github


@dataclass
class FileChange:
    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    patch: Optional[str]


@dataclass
class PullRequestInfo:
    number: int
    title: str
    body: Optional[str]
    base_branch: str
    head_branch: str
    commits: List[str]
    files: List["FileChange"]


class GitAnalyzer:
    def __init__(self, github_token: str):
        self.github = Github(github_token)

    def get_pr_info(self, repo_name: str, pr_number: int, max_files: int = 20) -> PullRequestInfo:
        repo = self.github.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        commits = [commit.commit.message for commit in pr.get_commits()]

        files = []
        for i, file in enumerate(pr.get_files()):
            if i >= max_files:
                break
            files.append(FileChange(
                filename=file.filename,
                status=file.status,
                additions=file.additions,
                deletions=file.deletions,
                patch=file.patch if hasattr(file, 'patch') else None
            ))

        return PullRequestInfo(
            number=pr.number,
            title=pr.title,
            body=pr.body,
            base_branch=pr.base.ref,
            head_branch=pr.head.ref,
            commits=commits,
            files=files
        )

    def get_pr_from_env(self, max_files: int = 20) -> Optional[PullRequestInfo]:
        repo_name = os.environ.get('GITHUB_REPOSITORY')
        event_path = os.environ.get('GITHUB_EVENT_PATH')

        if not repo_name or not event_path:
            return None

        import json
        with open(event_path) as f:
            event = json.load(f)

        pr_number = event.get('pull_request', {}).get('number')
        if not pr_number:
            return None

        return self.get_pr_info(repo_name, pr_number, max_files)
