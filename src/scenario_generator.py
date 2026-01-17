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
            return """당신은 QA 테스트 전문가입니다. 코드 변경사항을 분석하여 테스트 시나리오를 추천합니다.

**중요:** 기술 용어 대신 사용자 관점의 언어를 사용하세요.

**응답 형식 (컴팩트하게, 불필요한 빈 줄 없이):**

## 🧪 테스트 시나리오
> **핵심 변경사항**: (한 문장 요약)

### 🔴 높은 우선순위
- [ ] **시나리오명** - 간단한 설명
  <details><summary>테스트 방법</summary>
  1. 테스트 단계 1
  2. 테스트 단계 2
  </details>

### 🟡 중간 우선순위
(같은 형식)

### 🟢 낮은 우선순위
(같은 형식)

**유의사항:** 빈 줄 최소화, 시나리오는 체크박스로 시작, 상세 내용은 details 태그 사용"""
        else:
            return """You are a software testing expert. Analyze code changes and recommend test scenarios.

**Response format (compact, minimal blank lines):**

## 🧪 Test Scenarios
> **Key Changes**: (one sentence summary)

### 🔴 High Priority
- [ ] **Scenario Name** - brief description
  <details><summary>Test Steps</summary>
  1. Test step 1
  2. Test step 2
  </details>

### 🟡 Medium Priority
(same format)

### 🟢 Low Priority
(same format)

**Guidelines:** Minimize blank lines, use checkboxes, wrap details in details tag"""

    def _get_user_prompt(self, code_context: str) -> str:
        if self.language == 'ko':
            return f"""다음 코드 변경사항을 분석하고 테스트 시나리오를 추천해주세요.

{code_context}

**중요**: 컴팩트하게 작성 (빈 줄 최소화), 체크박스 사용, details 태그로 상세 내용 감싸기"""
        else:
            return f"""Analyze the following code changes and recommend test scenarios.

{code_context}

**Important**: Keep it compact (minimal blank lines), use checkboxes, wrap details in details tag"""

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
