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
    content: Optional[str] = None  # 전체 파일 내용 (하이브리드 컨텍스트용)


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

    def get_pr_info(self, repo_name: str, pr_number: int, max_files: int = 50) -> PullRequestInfo:
        repo = self.github.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        commits = [commit.commit.message for commit in pr.get_commits()]

        files = []
        for i, file in enumerate(pr.get_files()):
            if i >= max_files:
                break

            # 파일 content 가져오기 (삭제된 파일 제외)
            content = None
            if file.status != 'removed':
                content = self._get_file_content(repo, file.filename, pr.head.sha)

            files.append(FileChange(
                filename=file.filename,
                status=file.status,
                additions=file.additions,
                deletions=file.deletions,
                patch=file.patch if hasattr(file, 'patch') else None,
                content=content
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

    def _get_file_content(self, repo, filename: str, ref: str) -> Optional[str]:
        """파일 전체 내용을 가져옴 (500줄 이하인 경우에만)"""
        try:
            content_file = repo.get_contents(filename, ref=ref)
            if content_file.encoding == 'base64':
                import base64
                content = base64.b64decode(content_file.content).decode('utf-8')
                # 500줄 이하인 경우에만 반환
                if content.count('\n') <= 500:
                    return content
            return None
        except Exception:
            return None

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
