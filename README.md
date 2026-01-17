# woai

AI 기반 코드 변경 분석, 테스트 시나리오 추천 및 코드 리뷰 GitHub Action

## 기능

- PR의 코드 변경사항을 자동으로 분석
- OpenAI o3-mini를 사용하여 통합 테스트 시나리오 생성
- AI 기반 코드 리뷰 (OpenAI / Claude 선택 가능)
- PR 설명 자동 생성 및 기존 설명에 추가
- 우선순위별 테스트 시나리오 추천
- PR 코멘트로 결과 자동 게시
- API 사용 비용 표시

## 사용 방법

### 1. 워크플로우 설정

프로젝트의 `.github/workflows/test-scenarios.yml` 파일 생성:

```yaml
name: Test Scenarios
on:
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write

jobs:
  scenarios:
    runs-on: ubuntu-latest
    steps:
      - uses: skswhwo/woai@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          language: ko
          generate-description: 'true'
```

### 2. Secrets 설정

프로젝트 Settings > Secrets and variables > Actions에서:
- `OPENAI_API_KEY`: OpenAI API 키

`GITHUB_TOKEN`은 자동으로 제공됩니다.

## 입력값

| 이름 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| `github-token` | O | - | GitHub 토큰 (PR 코멘트용) |
| `openai-api-key` | X | - | OpenAI API 키 |
| `anthropic-api-key` | X | - | Anthropic API 키 (Claude 사용 시) |
| `model` | X | `o3-mini` | 시나리오 생성에 사용할 모델 |
| `language` | X | `ko` | 출력 언어 (ko/en) |
| `max-files` | X | `50` | 분석할 최대 파일 수 |
| `mode` | X | `both` | 실행 모드: scenario / review / both |
| `review-engine` | X | `openai` | 리뷰 엔진: openai / claude |
| `review-model` | X | `gpt-4o` | 리뷰에 사용할 모델 |
| `generate-description` | X | `false` | PR 설명 자동 생성 여부 |

## 출력 예시

PR에 다음과 같은 코멘트가 생성됩니다:

```markdown
## 🧪 테스트 시나리오 추천

### 변경 요약
- 변경된 파일: 5개
- 영향받는 모듈: auth, payment

> 사용자 인증 로직에 2FA 지원이 추가되었습니다.

### 권장 테스트 시나리오

#### 🔴 높은 우선순위
1. **2FA 인증 플로우 테스트**
   - 설명: 새로 추가된 2FA 인증 기능 검증
   - 테스트 포인트:
     - OTP 생성 및 검증
     - 잘못된 OTP 입력 시 에러 처리
     - 세션 타임아웃 동작

---
💰 **API 비용**: $0.0023 (입력: 1,234 tokens, 출력: 567 tokens)
```

## 개발

### 로컬 테스트

```bash
cd woai

# 환경 변수 설정
export GITHUB_TOKEN=your_token
export OPENAI_API_KEY=your_key
export GITHUB_REPOSITORY=owner/repo
export GITHUB_EVENT_PATH=/path/to/event.json

# 실행
python src/main.py
```

### Docker 빌드

```bash
docker build -t woai .
docker run -e GITHUB_TOKEN=xxx -e OPENAI_API_KEY=xxx woai
```

## 라이선스

MIT
