import os
import json
from typing import Optional, List, Dict, Tuple
from github import Github
from review_generator import ReviewResult, ReviewComment


class GitHubReviewer:
    REVIEW_MARKER = '<!-- ai-code-review -->'

    # Map severity to emoji
    SEVERITY_EMOJI = {
        'critical': ':rotating_light:',
        'suggestion': ':bulb:',
        'nitpick': ':pencil2:'
    }

    def __init__(self, github_token: str):
        self.github = Github(github_token)

    def post_review(
        self,
        repo_name: str,
        pr_number: int,
        result: ReviewResult,
        language: str = 'ko'
    ) -> Optional[str]:
        repo = self.github.get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        # Get the latest commit SHA for the review
        commits = list(pr.get_commits())
        if not commits:
            return None
        latest_commit = commits[-1]

        # Build review comments for GitHub API
        review_comments, fallback_comments = self._build_review_comments(pr, result.comments)

        # Map approval to GitHub event
        event_map = {
            'approve': 'APPROVE',
            'request_changes': 'REQUEST_CHANGES',
            'comment': 'COMMENT'
        }
        event = event_map.get(result.approval, 'COMMENT')

        # Build review body (include fallback comments)
        review_body = self._format_review_body(result, language, fallback_comments)

        # Delete previous AI review if exists
        self._delete_previous_review(pr)

        # Create review
        try:
            if review_comments:
                review = pr.create_review(
                    commit=latest_commit,
                    body=review_body,
                    event=event,
                    comments=review_comments
                )
            else:
                # If no line comments, just post a comment
                review = pr.create_review(
                    commit=latest_commit,
                    body=review_body,
                    event=event
                )
            return review.html_url if hasattr(review, 'html_url') else None
        except Exception as e:
            # Fallback: post as issue comment if review fails
            comment = pr.create_issue_comment(review_body)
            return comment.html_url

    def _build_review_comments(
        self,
        pr,
        comments: List[ReviewComment]
    ) -> Tuple[List[Dict], List[ReviewComment]]:
        """Build review comments with correct line positions for GitHub API.

        Returns:
            Tuple of (review_comments for line comments, fallback_comments for body)
        """
        review_comments = []
        fallback_comments = []

        # Get file patches to map line numbers
        pr_files = {f.filename: f for f in pr.get_files()}

        for comment in comments:
            if not comment.path or not comment.line:
                fallback_comments.append(comment)
                continue

            pr_file = pr_files.get(comment.path)
            if not pr_file or not pr_file.patch:
                fallback_comments.append(comment)
                continue

            # Calculate the position in the diff
            position = self._get_diff_position(pr_file.patch, comment.line)
            if position is None:
                fallback_comments.append(comment)
                continue

            emoji = self.SEVERITY_EMOJI.get(comment.severity, '')
            formatted_comment = f"{emoji} **[{comment.severity.upper()}]** {comment.comment}"

            review_comments.append({
                'path': comment.path,
                'position': position,
                'body': formatted_comment
            })

        return review_comments, fallback_comments

    def _get_diff_position(self, patch: str, target_line: int) -> Optional[int]:
        """
        Calculate the position in the diff for a given line number.
        Position is 1-indexed, counting only lines in the diff (including context).
        """
        if not patch:
            return None

        lines = patch.split('\n')
        position = 0
        current_line = 0

        for line in lines:
            if line.startswith('@@'):
                # Parse hunk header: @@ -start,count +start,count @@
                import re
                match = re.search(r'\+(\d+)', line)
                if match:
                    current_line = int(match.group(1)) - 1
                continue

            position += 1

            if line.startswith('-'):
                # Deleted line, doesn't affect new file line numbers
                continue
            elif line.startswith('+'):
                current_line += 1
                if current_line == target_line:
                    return position
            else:
                # Context line
                current_line += 1
                if current_line == target_line:
                    return position

        return None

    def _format_review_body(
        self,
        result: ReviewResult,
        language: str,
        fallback_comments: List[ReviewComment] = None
    ) -> str:
        lines = [self.REVIEW_MARKER]
        lines.append('')

        if language == 'ko':
            lines.append('## :robot: AI 코드 리뷰')
            lines.append('')
            lines.append(f'**요약:** {result.summary}')
            lines.append('')

            # Count by severity
            critical_count = sum(1 for c in result.comments if c.severity == 'critical')
            suggestion_count = sum(1 for c in result.comments if c.severity == 'suggestion')
            nitpick_count = sum(1 for c in result.comments if c.severity == 'nitpick')

            lines.append('### 리뷰 통계')
            lines.append(f'- :rotating_light: Critical: {critical_count}')
            lines.append(f'- :bulb: Suggestion: {suggestion_count}')
            lines.append(f'- :pencil2: Nitpick: {nitpick_count}')
            lines.append('')

            # Fallback comments (couldn't be posted as line comments)
            if fallback_comments:
                lines.append('### 상세 코멘트')
                lines.append('')
                for comment in fallback_comments:
                    emoji = self.SEVERITY_EMOJI.get(comment.severity, '')
                    lines.append(f'{emoji} **[{comment.severity.upper()}]** `{comment.path}:{comment.line}`')
                    lines.append(f'> {comment.comment}')
                    lines.append('')

            # Cost info
            llm_resp = result.llm_response
            lines.append('---')
            lines.append(
                f':chart_with_upwards_trend: 분석 파일: {result.files_count}개 | '
                f':moneybag: API 비용: ${llm_resp.cost_usd:.4f} '
                f'(입력: {llm_resp.prompt_tokens:,}, 출력: {llm_resp.completion_tokens:,} tokens)'
            )
        else:
            lines.append('## :robot: AI Code Review')
            lines.append('')
            lines.append(f'**Summary:** {result.summary}')
            lines.append('')

            # Count by severity
            critical_count = sum(1 for c in result.comments if c.severity == 'critical')
            suggestion_count = sum(1 for c in result.comments if c.severity == 'suggestion')
            nitpick_count = sum(1 for c in result.comments if c.severity == 'nitpick')

            lines.append('### Review Statistics')
            lines.append(f'- :rotating_light: Critical: {critical_count}')
            lines.append(f'- :bulb: Suggestion: {suggestion_count}')
            lines.append(f'- :pencil2: Nitpick: {nitpick_count}')
            lines.append('')

            # Fallback comments (couldn't be posted as line comments)
            if fallback_comments:
                lines.append('### Detailed Comments')
                lines.append('')
                for comment in fallback_comments:
                    emoji = self.SEVERITY_EMOJI.get(comment.severity, '')
                    lines.append(f'{emoji} **[{comment.severity.upper()}]** `{comment.path}:{comment.line}`')
                    lines.append(f'> {comment.comment}')
                    lines.append('')

            # Cost info
            llm_resp = result.llm_response
            lines.append('---')
            lines.append(
                f':chart_with_upwards_trend: Files analyzed: {result.files_count} | '
                f':moneybag: API Cost: ${llm_resp.cost_usd:.4f} '
                f'(input: {llm_resp.prompt_tokens:,}, output: {llm_resp.completion_tokens:,} tokens)'
            )

        return '\n'.join(lines)

    def _delete_previous_review(self, pr):
        """Delete previous AI review comments."""
        try:
            for comment in pr.get_issue_comments():
                if self.REVIEW_MARKER in comment.body:
                    comment.delete()
                    break
        except Exception:
            pass  # Ignore errors when deleting

    def post_from_env(self, result: ReviewResult, language: str = 'ko') -> Optional[str]:
        repo_name = os.environ.get('GITHUB_REPOSITORY')
        event_path = os.environ.get('GITHUB_EVENT_PATH')

        if not repo_name or not event_path:
            return None

        with open(event_path) as f:
            event = json.load(f)

        pr_number = event.get('pull_request', {}).get('number')
        if not pr_number:
            return None

        return self.post_review(repo_name, pr_number, result, language)
