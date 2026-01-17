import os
import json
import logging
from typing import Optional, List, Dict, Tuple
from github import Github
from review_generator import ReviewResult, ReviewComment

logger = logging.getLogger(__name__)


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

        logger.info(f"Total comments: {len(result.comments)}, Line comments: {len(review_comments)}, Fallback: {len(fallback_comments)}")
        for rc in review_comments:
            logger.info(f"Line comment: {rc['path']} (position {rc['position']}) - {rc.get('body', '')[:50]}...")

        # Map approval to GitHub event
        # Note: GitHub Actions cannot APPROVE PRs, so we use COMMENT instead
        event_map = {
            'approve': 'COMMENT',  # GitHub Actions doesn't have permission to approve
            'request_changes': 'REQUEST_CHANGES',
            'comment': 'COMMENT'
        }
        event = event_map.get(result.approval, 'COMMENT')

        # Build review body (fallback 코멘트만 본문에 표시)
        review_body = self._format_review_body(result, language, fallback_comments)

        # Delete previous AI review if exists
        self._delete_previous_review(pr)

        # Create review
        try:
            if review_comments:
                logger.info(f"Posting review with {len(review_comments)} line comments...")
                review = pr.create_review(
                    commit=latest_commit,
                    body=review_body,
                    event=event,
                    comments=review_comments
                )
                logger.info("Review with line comments posted successfully")
            else:
                logger.info("No line comments, posting review body only")
                review = pr.create_review(
                    commit=latest_commit,
                    body=review_body,
                    event=event
                )
            return review.html_url if hasattr(review, 'html_url') else None
        except Exception as e:
            logger.error(f"Failed to post review with line comments: {e}")
            # Fallback: post as issue comment if review fails
            comment = pr.create_issue_comment(review_body)
            return comment.html_url

    def _build_review_comments(
        self,
        pr,
        comments: List[ReviewComment]
    ) -> Tuple[List[Dict], List[ReviewComment]]:
        """Build review comments with line numbers for GitHub API.

        Returns:
            Tuple of (review_comments for line comments, fallback_comments for body)
        """
        review_comments = []
        fallback_comments = []

        # Get file patches to check if line is in diff
        pr_files = {f.filename: f for f in pr.get_files()}

        for comment in comments:
            if not comment.path or not comment.line:
                logger.debug(f"Comment missing path or line: {comment}")
                fallback_comments.append(comment)
                continue

            pr_file = pr_files.get(comment.path)
            if not pr_file or not pr_file.patch:
                logger.debug(f"File not found or no patch: {comment.path}")
                fallback_comments.append(comment)
                continue

            # Calculate position in diff
            position = self._get_diff_position(pr_file.patch, comment.line)
            if position is None:
                logger.debug(f"Could not calculate position for {comment.path}:{comment.line}")
                fallback_comments.append(comment)
                continue

            emoji = self.SEVERITY_EMOJI.get(comment.severity, '')
            formatted_comment = f"{emoji} **[{comment.severity.upper()}]** {comment.comment}"

            # position 방식 사용 (더 안정적)
            review_comments.append({
                'path': comment.path,
                'position': position,
                'body': formatted_comment
            })
            logger.debug(f"Added line comment: {comment.path}:{comment.line} -> position {position}")

        return review_comments, fallback_comments

    def _is_line_in_diff(self, patch: str, target_line: int) -> bool:
        """Check if a line number is within the diff hunks."""
        if not patch:
            return False

        import re
        for match in re.finditer(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', patch):
            start_line = int(match.group(1))
            count = int(match.group(2)) if match.group(2) else 1
            end_line = start_line + count - 1  # Fixed: inclusive end
            if start_line <= target_line <= end_line:
                logger.debug(f"Line {target_line} is in diff hunk ({start_line}-{end_line})")
                return True

        logger.debug(f"Line {target_line} NOT in any diff hunk")
        return False

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

            # 모든 코멘트를 접어서 표시
            if result.comments:
                lines.append('<details>')
                lines.append('<summary><strong>상세 코멘트 보기</strong></summary>')
                lines.append('')
                lines.append('| 파일 | 라인 | 심각도 | 코멘트 |')
                lines.append('|------|------|--------|--------|')
                for comment in result.comments:
                    emoji = self.SEVERITY_EMOJI.get(comment.severity, '')
                    # 코멘트 내용에서 | 문자 이스케이프
                    safe_comment = comment.comment.replace('|', '\\|').replace('\n', ' ')
                    lines.append(f'| `{comment.path}` | {comment.line} | {emoji} {comment.severity} | {safe_comment} |')
                lines.append('')
                lines.append('</details>')
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

            # 모든 코멘트를 접어서 표시
            if result.comments:
                lines.append('<details>')
                lines.append('<summary><strong>View Detailed Comments</strong></summary>')
                lines.append('')
                lines.append('| File | Line | Severity | Comment |')
                lines.append('|------|------|----------|---------|')
                for comment in result.comments:
                    emoji = self.SEVERITY_EMOJI.get(comment.severity, '')
                    safe_comment = comment.comment.replace('|', '\\|').replace('\n', ' ')
                    lines.append(f'| `{comment.path}` | {comment.line} | {emoji} {comment.severity} | {safe_comment} |')
                lines.append('')
                lines.append('</details>')
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
