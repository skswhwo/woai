import json
import re
from dataclasses import dataclass
from typing import List, Optional, Union
from llm_client import LLMClient, LLMResponse


@dataclass
class ReviewComment:
    path: str
    line: int
    severity: str  # critical, suggestion, nitpick
    comment: str


@dataclass
class ReviewResult:
    summary: str
    comments: List[ReviewComment]
    approval: str  # approve, request_changes, comment
    files_count: int
    llm_response: LLMResponse


class ReviewGenerator:
    def __init__(self, llm_client: Union['LLMClient', 'AnthropicClient'], language: str = 'ko'):
        self.llm_client = llm_client
        self.language = language

    def generate(self, code_context: str, files_count: int) -> ReviewResult:
        system_prompt = self._get_system_prompt()
        user_prompt = self._get_user_prompt(code_context)

        response = self.llm_client.generate(system_prompt, user_prompt)
        review_data = self._parse_response(response.content)

        return ReviewResult(
            summary=review_data.get('summary', 'Code review completed'),
            comments=[
                ReviewComment(
                    path=c.get('path', ''),
                    line=c.get('line', 0),
                    severity=c.get('severity', 'suggestion'),
                    comment=c.get('comment', '')
                )
                for c in review_data.get('comments', [])
            ],
            approval=review_data.get('approval', 'comment'),
            files_count=files_count,
            llm_response=response
        )

    def _get_system_prompt(self) -> str:
        if self.language == 'ko':
            return """당신은 숙련된 코드 리뷰어입니다.
Pull Request의 코드 변경사항을 분석하여 코드 품질, 버그, 보안, 성능 등의 관점에서 리뷰를 수행해야 합니다.

## 리뷰 기준
1. **버그/오류**: 논리적 오류, null 참조, 예외 처리 누락
2. **보안**: 인증/권한 누락, 입력 검증, SQL 인젝션, XSS 등
3. **성능**: 비효율적 알고리즘, 불필요한 반복, 메모리 누수
4. **코드 품질**: 가독성, 중복 코드, 네이밍, 복잡도
5. **베스트 프랙티스**: 언어/프레임워크별 권장 패턴

## 심각도 분류
- **critical**: 반드시 수정 필요 (버그, 보안 취약점, 데이터 손실 가능성)
- **suggestion**: 개선 권장 (성능, 가독성, 유지보수성)
- **nitpick**: 사소한 개선 (스타일, 네이밍 등)

## 응답 형식 (반드시 JSON으로 응답)
```json
{
  "summary": "전체 리뷰 요약 (1-2문장)",
  "comments": [
    {
      "path": "파일 경로",
      "line": 라인 번호,
      "severity": "critical|suggestion|nitpick",
      "comment": "리뷰 내용"
    }
  ],
  "approval": "approve|request_changes|comment"
}
```

## 주의사항
- 변경된 코드 라인에만 코멘트를 달아주세요
- 라인 번호는 파일 내 실제 라인 번호입니다
- 불필요하게 많은 코멘트는 피하고 중요한 이슈에 집중하세요
- approval은 critical 이슈가 있으면 "request_changes", 없으면 "approve" 또는 "comment"
- 응답은 반드시 JSON 형식이어야 합니다 (마크다운 코드블록 없이)
- **summary와 comment는 반드시 한국어로 작성하세요**"""
        else:
            return """You are an experienced code reviewer.
Analyze Pull Request code changes and review from perspectives of code quality, bugs, security, and performance.

## Review Criteria
1. **Bugs/Errors**: Logic errors, null references, missing exception handling
2. **Security**: Missing auth/authorization, input validation, SQL injection, XSS
3. **Performance**: Inefficient algorithms, unnecessary loops, memory leaks
4. **Code Quality**: Readability, code duplication, naming, complexity
5. **Best Practices**: Language/framework recommended patterns

## Severity Classification
- **critical**: Must fix (bugs, security vulnerabilities, data loss risk)
- **suggestion**: Recommended improvement (performance, readability, maintainability)
- **nitpick**: Minor improvement (style, naming, etc.)

## Response Format (Must respond in JSON)
```json
{
  "summary": "Overall review summary (1-2 sentences)",
  "comments": [
    {
      "path": "file path",
      "line": line number,
      "severity": "critical|suggestion|nitpick",
      "comment": "Review comment"
    }
  ],
  "approval": "approve|request_changes|comment"
}
```

## Notes
- Only comment on changed lines
- Line number is the actual line number in the file
- Avoid excessive comments, focus on important issues
- approval should be "request_changes" if there are critical issues, otherwise "approve" or "comment"
- Response must be in JSON format (without markdown code blocks)"""

    def _get_user_prompt(self, code_context: str) -> str:
        if self.language == 'ko':
            return f"""다음 Pull Request의 코드 변경사항을 리뷰해주세요.

{code_context}

위 변경사항에 대해 JSON 형식으로 코드 리뷰를 제공해주세요.
응답은 반드시 유효한 JSON이어야 합니다."""
        else:
            return f"""Please review the following Pull Request code changes.

{code_context}

Provide a code review in JSON format for the above changes.
Response must be valid JSON."""

    def _parse_response(self, content: str) -> dict:
        # Try to extract JSON from the response
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith('```'):
            lines = content.split('\n')
            # Find the start and end of the JSON block
            start_idx = 0
            end_idx = len(lines)
            for i, line in enumerate(lines):
                if line.startswith('```') and i == 0:
                    start_idx = 1
                elif line.startswith('```') and i > 0:
                    end_idx = i
                    break
            content = '\n'.join(lines[start_idx:end_idx])

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to find JSON object in the content
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            # Return default structure if parsing fails
            return {
                'summary': 'Code review parsing failed',
                'comments': [],
                'approval': 'comment'
            }
