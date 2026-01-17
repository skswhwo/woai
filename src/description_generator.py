import json
import re
from dataclasses import dataclass
from typing import Union
from llm_client import LLMClient, LLMResponse


@dataclass
class DescriptionResult:
    summary: str
    changes: list
    test_impact: str
    llm_response: LLMResponse


class DescriptionGenerator:
    def __init__(self, llm_client: Union['LLMClient', 'AnthropicClient'], language: str = 'ko'):
        self.llm_client = llm_client
        self.language = language

    def generate(self, code_context: str, files_count: int) -> DescriptionResult:
        system_prompt = self._get_system_prompt()
        user_prompt = self._get_user_prompt(code_context)

        response = self.llm_client.generate(system_prompt, user_prompt)
        desc_data = self._parse_response(response.content)

        return DescriptionResult(
            summary=desc_data.get('summary', ''),
            changes=desc_data.get('changes', []),
            test_impact=desc_data.get('test_impact', ''),
            llm_response=response
        )

    def _get_system_prompt(self) -> str:
        if self.language == 'ko':
            return """당신은 Pull Request 설명을 작성하는 전문가입니다.
코드 변경사항을 분석하여 명확하고 간결한 PR 설명을 작성해야 합니다.

## 작성 기준
1. **요약**: 변경사항의 핵심을 1-2문장으로 설명
2. **주요 변경사항**: 구체적인 변경 내용을 bullet point로 정리
3. **테스트 영향**: 테스트가 필요한 부분 설명

## 응답 형식 (반드시 JSON으로 응답)
```json
{
  "summary": "변경사항 요약 (1-2문장)",
  "changes": [
    "변경사항 1",
    "변경사항 2"
  ],
  "test_impact": "테스트 영향 및 확인 필요 사항"
}
```

## 주의사항
- 기술적으로 정확하게 작성
- 불필요한 내용 제외, 핵심만 간결하게
- 응답은 반드시 JSON 형식이어야 합니다"""
        else:
            return """You are an expert at writing Pull Request descriptions.
Analyze code changes and write clear, concise PR descriptions.

## Writing Guidelines
1. **Summary**: Explain the core changes in 1-2 sentences
2. **Key Changes**: List specific changes as bullet points
3. **Test Impact**: Describe areas that need testing

## Response Format (Must respond in JSON)
```json
{
  "summary": "Summary of changes (1-2 sentences)",
  "changes": [
    "Change 1",
    "Change 2"
  ],
  "test_impact": "Test impact and areas to verify"
}
```

## Notes
- Be technically accurate
- Keep it concise, focus on essentials
- Response must be in JSON format"""

    def _get_user_prompt(self, code_context: str) -> str:
        if self.language == 'ko':
            return f"""다음 Pull Request의 코드 변경사항을 분석하여 PR 설명을 작성해주세요.

{code_context}

위 변경사항에 대해 JSON 형식으로 PR 설명을 작성해주세요."""
        else:
            return f"""Analyze the following Pull Request code changes and write a PR description.

{code_context}

Write a PR description in JSON format for the above changes."""

    def _parse_response(self, content: str) -> dict:
        content = content.strip()

        # Remove markdown code blocks if present
        if content.startswith('```'):
            lines = content.split('\n')
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
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

            return {
                'summary': '',
                'changes': [],
                'test_impact': ''
            }

    def format_description(self, result: DescriptionResult) -> str:
        """Format the description result as markdown to append to PR."""
        lines = []
        lines.append('')
        lines.append('---')
        lines.append('')

        if self.language == 'ko':
            lines.append('## 설명')
            lines.append('')
            lines.append(f'### 요약')
            lines.append(result.summary)
            lines.append('')
            lines.append('### 주요 변경사항')
            for change in result.changes:
                lines.append(f'- {change}')
            lines.append('')
            if result.test_impact:
                lines.append('### 테스트 영향')
                lines.append(result.test_impact)
                lines.append('')
        else:
            lines.append('## Description')
            lines.append('')
            lines.append(f'### Summary')
            lines.append(result.summary)
            lines.append('')
            lines.append('### Key Changes')
            for change in result.changes:
                lines.append(f'- {change}')
            lines.append('')
            if result.test_impact:
                lines.append('### Test Impact')
                lines.append(result.test_impact)
                lines.append('')

        return '\n'.join(lines)
