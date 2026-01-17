import os
import json
from typing import Optional, List
from github import Github
from scenario_generator import ScenarioResult


class GitHubCommenter:
    COMMENT_MARKER = '<!-- woai -->'
    DESCRIPTION_MARKER = '<!-- woai-description -->'

    def __init__(self, github_token: str):
        self.github = Github(github_token)

    def post_comment(self, repo_name: str, pr_number: int, result: ScenarioResult, language: str = 'ko') -> str:
        repo = self.github.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        comment_body = self._format_comment(result, language)

        # Delete previous comment if exists
        for comment in pr.get_issue_comments():
            if self.COMMENT_MARKER in comment.body:
                comment.delete()
                break

        # Post new comment
        new_comment = pr.create_issue_comment(comment_body)
        return new_comment.html_url

    def _format_comment(self, result: ScenarioResult, language: str) -> str:
        lines = [self.COMMENT_MARKER]

        # LLM 원본 응답 그대로 사용
        lines.append(result.llm_response.content)

        # Cost info
        llm_resp = result.llm_response
        lines.append("\n---")
        if language == 'ko':
            lines.append(
                f"📊 변경된 파일: {result.files_count}개 | "
                f"💰 API 비용: ${llm_resp.cost_usd:.4f} "
                f"(입력: {llm_resp.prompt_tokens:,}, 출력: {llm_resp.completion_tokens:,} tokens)"
            )
        else:
            lines.append(
                f"📊 Changed files: {result.files_count} | "
                f"💰 API Cost: ${llm_resp.cost_usd:.4f} "
                f"(input: {llm_resp.prompt_tokens:,}, output: {llm_resp.completion_tokens:,} tokens)"
            )

        return '\n'.join(lines)

    def _format_scenario(self, num: int, scenario, language: str) -> List[str]:
        lines = [f"\n{num}. **{scenario.name}**"]
        if scenario.description:
            desc_label = "설명" if language == 'ko' else "Description"
            lines.append(f"   - {desc_label}: {scenario.description}")
        if scenario.test_points:
            points_label = "테스트 포인트" if language == 'ko' else "Test Points"
            lines.append(f"   - {points_label}:")
            for point in scenario.test_points[:5]:
                lines.append(f"     - {point}")
        return lines

    def post_from_env(self, result: ScenarioResult, language: str = 'ko') -> Optional[str]:
        repo_name = os.environ.get('GITHUB_REPOSITORY')
        event_path = os.environ.get('GITHUB_EVENT_PATH')

        if not repo_name or not event_path:
            return None

        with open(event_path) as f:
            event = json.load(f)

        pr_number = event.get('pull_request', {}).get('number')
        if not pr_number:
            return None

        return self.post_comment(repo_name, pr_number, result, language)

    def update_pr_description(
        self,
        repo_name: str,
        pr_number: int,
        description_text: str
    ) -> Optional[str]:
        """Append AI-generated description to existing PR body."""
        repo = self.github.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        current_body = pr.body or ''

        # Remove previous AI description if exists
        if self.DESCRIPTION_MARKER in current_body:
            marker_idx = current_body.find(self.DESCRIPTION_MARKER)
            current_body = current_body[:marker_idx].rstrip()

        # Append new description
        new_body = current_body + '\n\n' + self.DESCRIPTION_MARKER + '\n' + description_text

        pr.edit(body=new_body)
        return pr.html_url

    def update_pr_description_from_env(self, description_text: str) -> Optional[str]:
        repo_name = os.environ.get('GITHUB_REPOSITORY')
        event_path = os.environ.get('GITHUB_EVENT_PATH')

        if not repo_name or not event_path:
            return None

        with open(event_path) as f:
            event = json.load(f)

        pr_number = event.get('pull_request', {}).get('number')
        if not pr_number:
            return None

        return self.update_pr_description(repo_name, pr_number, description_text)
