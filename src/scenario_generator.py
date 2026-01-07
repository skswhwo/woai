import os
from dataclasses import dataclass
from typing import List, Tuple
from llm_client import LLMClient, LLMResponse


@dataclass
class TestScenario:
    priority: str  # high, medium, low
    name: str
    description: str
    test_points: List[str]
    affected_modules: List[str]


@dataclass
class ScenarioResult:
    summary: str
    scenarios: List[TestScenario]
    affected_modules: List[str]
    files_count: int
    llm_response: LLMResponse


class ScenarioGenerator:
    def __init__(self, llm_client: LLMClient, language: str = 'ko'):
        self.llm_client = llm_client
        self.language = language

    def generate(self, code_context: str, files_count: int) -> ScenarioResult:
        system_prompt = self._get_system_prompt()
        user_prompt = self._get_user_prompt(code_context)

        response = self.llm_client.generate(system_prompt, user_prompt)
        scenarios, modules = self._parse_response(response.content)

        return ScenarioResult(
            summary=self._extract_summary(response.content),
            scenarios=scenarios,
            affected_modules=modules,
            files_count=files_count,
            llm_response=response
        )

    def _get_system_prompt(self) -> str:
        if self.language == 'ko':
            return """당신은 QA 테스트 전문가입니다.
코드 변경사항을 분석하여 QA팀이나 기획자도 이해할 수 있는 테스트 시나리오를 추천해야 합니다.

**중요: 기술 용어 대신 사용자 관점의 언어를 사용하세요.**
- ❌ "isValidGrade 함수가 13까지 유효한 범위로 변경"
- ✅ "대학생 학년(13학년)을 선택했을 때 정상 동작하는지 확인"

**응답 형식 (정확히 따라주세요):**

## 핵심 변경사항
(한 문장으로 요약)

## 영향받는 기능
- 기능1
- 기능2

## 테스트 시나리오

### 🔴 높은 우선순위

• 시나리오: (시나리오 이름)
  - 설명: (무엇을 테스트하는지 쉽게 설명)
  - 테스트 방법:
    ▪ (구체적인 테스트 단계 1)
    ▪ (구체적인 테스트 단계 2)

### 🟡 중간 우선순위
(같은 형식)

### 🟢 낮은 우선순위
(같은 형식)

**시나리오 작성 시 유의사항:**
- 실제 사용자가 하는 행동으로 설명 (예: "회원가입 버튼 클릭 후...")
- 코드나 함수명 대신 기능명 사용
- "~했을 때 ~가 되어야 한다" 형식 권장"""
        else:
            return """You are a software testing expert.
Analyze code changes and recommend integration test scenarios.

Response format:
1. First, write a one-sentence summary of the key changes.
2. List affected modules.
3. Present test scenarios by priority:
   - High: Core business logic, data integrity, security
   - Medium: Feature functionality, error handling
   - Low: UI, performance, edge cases

Include for each scenario:
- Scenario name
- Description
- Specific test points (items to verify)"""

    def _get_user_prompt(self, code_context: str) -> str:
        if self.language == 'ko':
            return f"""다음 코드 변경사항을 분석하고 통합 테스트 시나리오를 추천해주세요.

{code_context}

위 변경사항에 대해:
1. 핵심 변경사항 요약
2. 영향받는 모듈 목록
3. 우선순위별 테스트 시나리오 (높음/중간/낮음)

마크다운 형식으로 응답해주세요."""
        else:
            return f"""Analyze the following code changes and recommend integration test scenarios.

{code_context}

For the above changes, provide:
1. Summary of key changes
2. List of affected modules
3. Test scenarios by priority (High/Medium/Low)

Respond in markdown format."""

    def _parse_response(self, content: str) -> Tuple[List[TestScenario], List[str]]:
        scenarios = []
        modules = []

        lines = content.split('\n')
        current_priority = 'medium'
        current_scenario = None
        in_test_points = False

        for i, line in enumerate(lines):
            line_lower = line.lower()
            stripped = line.strip()

            # Detect priority sections
            if '높은 우선순위' in line or 'high priority' in line_lower or '**높은' in line:
                current_priority = 'high'
                continue
            elif '중간 우선순위' in line or 'medium priority' in line_lower or '**중간' in line:
                current_priority = 'medium'
                continue
            elif '낮은 우선순위' in line or 'low priority' in line_lower or '**낮은' in line:
                current_priority = 'low'
                continue

            # Extract modules (• 로 시작하는 모듈 목록)
            if '영향받는 모듈' in line or '2. 영향' in line:
                # 다음 몇 줄에서 모듈 추출
                for j in range(i+1, min(i+10, len(lines))):
                    module_line = lines[j].strip()
                    if module_line.startswith('•') or module_line.startswith('-'):
                        module = module_line.lstrip('•-').strip()
                        if module and '모듈' in module:
                            modules.append(module.split('(')[0].strip())
                    elif module_line.startswith('3.') or module_line.startswith('**'):
                        break
                continue

            # Detect scenario (• 시나리오: 또는 - 시나리오 이름: 형식)
            if '시나리오' in stripped and ':' in stripped:
                # "• 시나리오:", "- 시나리오:", "- 시나리오 이름:" 등 처리
                if current_scenario:
                    scenarios.append(current_scenario)

                name = stripped.split(':', 1)[1].strip() if ':' in stripped else stripped
                current_scenario = TestScenario(
                    priority=current_priority,
                    name=name,
                    description='',
                    test_points=[],
                    affected_modules=[]
                )
                in_test_points = False
                continue

            # Detect description
            if current_scenario and ('- 설명:' in stripped or '  - 설명:' in line):
                desc = stripped.split(':', 1)[1].strip() if ':' in stripped else ''
                current_scenario.description = desc
                continue

            # Detect test points section
            if current_scenario and ('테스트 포인트' in stripped or '테스트 방법' in stripped):
                in_test_points = True
                continue

            # Extract test points (▪ 로 시작)
            if current_scenario and in_test_points:
                if stripped.startswith('▪') or stripped.startswith('•') or stripped.startswith('-'):
                    point = stripped.lstrip('▪•-').strip()
                    if point:
                        current_scenario.test_points.append(point)
                elif stripped.startswith('• 시나리오') or stripped.startswith('**') or stripped.startswith('---'):
                    in_test_points = False

        if current_scenario:
            scenarios.append(current_scenario)

        return scenarios, modules

    def _extract_summary(self, content: str) -> str:
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('-') and len(line) > 20:
                return line[:200]
        return "코드 변경사항 분석 완료"
