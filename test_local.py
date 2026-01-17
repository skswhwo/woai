#!/usr/bin/env python3
"""
로컬 테스트 스크립트
실제 GitHub PR 또는 로컬 git diff를 분석합니다.

사용법:
  # 리뷰 테스트 (OpenAI)
  OPENAI_API_KEY=sk-xxx python test_local.py --local --mode review

  # 리뷰 테스트 (Claude)
  ANTHROPIC_API_KEY=sk-xxx python test_local.py --local --mode review --engine claude

  # 시나리오 테스트
  OPENAI_API_KEY=sk-xxx python test_local.py --local --mode scenario

  # 둘 다 테스트
  OPENAI_API_KEY=sk-xxx python test_local.py --local --mode both

  # PR 분석
  GITHUB_TOKEN=xxx OPENAI_API_KEY=xxx python test_local.py --repo owner/repo --pr 123

  # 로컬 git diff 분석 (현재 브랜치 vs main)
  python test_local.py --local --base main

  # 특정 커밋 범위 분석
  python test_local.py --local --base HEAD~3

  # Dry run (API 호출 없이 파싱만)
  python test_local.py --local --dry-run
"""
import argparse
import os
import sys
import subprocess

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from git_analyzer import GitAnalyzer, PullRequestInfo, FileChange
from code_parser import CodeParser
from llm_client import LLMClient, create_client
from scenario_generator import ScenarioGenerator
from review_generator import ReviewGenerator


def get_local_diff(base: str = 'main') -> PullRequestInfo:
    """로컬 git diff를 PullRequestInfo 형태로 변환"""

    # Get current branch
    result = subprocess.run(
        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
        capture_output=True, text=True
    )
    current_branch = result.stdout.strip()

    # Get commit messages
    result = subprocess.run(
        ['git', 'log', f'{base}..HEAD', '--pretty=format:%s'],
        capture_output=True, text=True
    )
    commits = result.stdout.strip().split('\n') if result.stdout.strip() else []

    # Get changed files with numstat for accurate counts
    result = subprocess.run(
        ['git', 'diff', '--numstat', base],
        capture_output=True, text=True
    )

    # Get status info
    status_result = subprocess.run(
        ['git', 'diff', '--name-status', base],
        capture_output=True, text=True
    )
    status_map_raw = {}
    for line in status_result.stdout.strip().split('\n'):
        if line:
            parts = line.split('\t')
            if len(parts) >= 2:
                file_status = {'A': 'added', 'M': 'modified', 'D': 'removed', 'R': 'renamed'}.get(parts[0][0], 'modified')
                status_map_raw[parts[-1]] = file_status

    files = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) < 3:
            continue

        additions = int(parts[0]) if parts[0] != '-' else 0
        deletions = int(parts[1]) if parts[1] != '-' else 0
        filename = parts[2]

        status = status_map_raw.get(filename, 'modified')

        # Get diff for file
        diff_result = subprocess.run(
            ['git', 'diff', base, '--', filename],
            capture_output=True, text=True
        )
        patch = diff_result.stdout

        files.append(FileChange(
            filename=filename,
            status=status,
            additions=additions,
            deletions=deletions,
            patch=patch
        ))

    return PullRequestInfo(
        number=0,
        title=f"Local changes: {current_branch} vs {base}",
        body=f"Commits: {len(commits)}",
        base_branch=base,
        head_branch=current_branch,
        commits=commits,
        files=files
    )


def run_scenario_test(pr_info, code_context, openai_api_key, model, language):
    """테스트 시나리오 생성 테스트"""
    print("\n" + "="*60)
    print("🧪 테스트 시나리오 생성")
    print("="*60)

    llm_client = LLMClient(openai_api_key, model)
    generator = ScenarioGenerator(llm_client, language)

    try:
        result = generator.generate(code_context, len(pr_info.files))
    except Exception as e:
        print(f"\n❌ LLM 호출 실패: {e}")
        return

    print(f"\n📊 분석 정보: 변경된 파일 {result.files_count}개")
    print(f"💰 API 비용: ${result.llm_response.cost_usd:.4f}")
    print(f"   (입력: {result.llm_response.prompt_tokens:,}, 출력: {result.llm_response.completion_tokens:,} tokens)\n")
    print(result.llm_response.content)


def run_review_test(pr_info, code_context, engine, review_model, api_key, language):
    """코드 리뷰 테스트"""
    print("\n" + "="*60)
    print(f"🔍 코드 리뷰 ({engine}/{review_model})")
    print("="*60)

    llm_client = create_client(engine, api_key, review_model)
    generator = ReviewGenerator(llm_client, language)

    try:
        result = generator.generate(code_context, len(pr_info.files))
    except Exception as e:
        print(f"\n❌ LLM 호출 실패: {e}")
        return

    print(f"\n📊 리뷰 코멘트: {len(result.comments)}개")
    print(f"📋 승인 상태: {result.approval}")
    print(f"💰 API 비용: ${result.llm_response.cost_usd:.4f}")
    print(f"   (입력: {result.llm_response.prompt_tokens:,}, 출력: {result.llm_response.completion_tokens:,} tokens)")

    print(f"\n📝 요약: {result.summary}")

    if result.comments:
        print("\n🔍 리뷰 코멘트:")
        print("-"*40)
        for i, comment in enumerate(result.comments, 1):
            severity_emoji = {'critical': '🔴', 'suggestion': '🟡', 'nitpick': '🟢'}.get(comment.severity, '⚪')
            print(f"\n{i}. {severity_emoji} [{comment.severity.upper()}] {comment.path}:{comment.line}")
            print(f"   {comment.comment}")
    else:
        print("\n✅ 리뷰 코멘트가 없습니다.")


def main():
    parser = argparse.ArgumentParser(description='woai - Local Test')
    parser.add_argument('--repo', help='GitHub repository (owner/repo)')
    parser.add_argument('--pr', type=int, help='PR number')
    parser.add_argument('--local', action='store_true', help='Use local git diff')
    parser.add_argument('--base', default='main', help='Base branch for local diff (default: main)')
    parser.add_argument('--mode', choices=['scenario', 'review', 'both'], default='both',
                       help='Test mode (default: both)')
    parser.add_argument('--engine', choices=['openai', 'claude'], default='openai',
                       help='Review engine (default: openai)')
    parser.add_argument('--model', default='o3-mini', help='Scenario model (default: o3-mini)')
    parser.add_argument('--review-model', default=None,
                       help='Review model (default: gpt-4o or claude-3-5-sonnet-20241022)')
    parser.add_argument('--language', default='ko', choices=['ko', 'en'],
                       help='Output language (default: ko)')
    parser.add_argument('--max-files', type=int, default=20, help='Max files to analyze')
    parser.add_argument('--dry-run', action='store_true', help='Parse only, no API calls')

    args = parser.parse_args()

    # Set default review model
    if args.review_model:
        review_model = args.review_model
    elif args.engine == 'claude':
        review_model = 'claude-3-5-sonnet-20241022'
    else:
        review_model = 'gpt-4o'

    # Check API keys
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    anthropic_api_key = os.environ.get('ANTHROPIC_API_KEY')

    needs_openai = args.mode in ('scenario', 'both') or (args.mode in ('review', 'both') and args.engine == 'openai')
    needs_anthropic = args.mode in ('review', 'both') and args.engine == 'claude'

    if not args.dry_run:
        if needs_openai and not openai_api_key:
            print("❌ Error: OPENAI_API_KEY 환경변수를 설정해주세요")
            print("   export OPENAI_API_KEY=your_key")
            sys.exit(1)
        if needs_anthropic and not anthropic_api_key:
            print("❌ Error: ANTHROPIC_API_KEY 환경변수를 설정해주세요")
            print("   export ANTHROPIC_API_KEY=your_key")
            sys.exit(1)

    # Get PR info
    if args.local:
        print(f"📂 로컬 git diff 분석 중... (base: {args.base})")
        pr_info = get_local_diff(args.base)
    elif args.repo and args.pr:
        github_token = os.environ.get('GITHUB_TOKEN')
        if not github_token:
            print("❌ Error: GITHUB_TOKEN 환경변수를 설정해주세요")
            sys.exit(1)
        print(f"🔍 PR #{args.pr} 분석 중... ({args.repo})")
        analyzer = GitAnalyzer(github_token)
        pr_info = analyzer.get_pr_info(args.repo, args.pr, args.max_files)
    else:
        print("❌ Error: --local 또는 --repo/--pr 옵션을 지정해주세요")
        parser.print_help()
        sys.exit(1)

    print(f"\n📋 분석 대상: {pr_info.title}")
    print(f"   브랜치: {pr_info.head_branch} → {pr_info.base_branch}")
    print(f"   변경 파일: {len(pr_info.files)}개")
    print(f"   커밋: {len(pr_info.commits)}개")
    print(f"   모드: {args.mode}")
    if args.mode in ('review', 'both'):
        print(f"   리뷰 엔진: {args.engine}/{review_model}")

    if not pr_info.files:
        print("\n⚠️  변경된 파일이 없습니다.")
        sys.exit(0)

    print("\n📝 변경된 파일:")
    for f in pr_info.files[:10]:
        print(f"   - {f.filename} ({f.status}, +{f.additions}/-{f.deletions})")
    if len(pr_info.files) > 10:
        print(f"   ... 외 {len(pr_info.files) - 10}개")

    # Parse code
    print("\n🔧 코드 분석 중...")
    parser_obj = CodeParser()
    parsed_changes = parser_obj.parse_changes(pr_info)
    code_context = parser_obj.format_for_llm(parsed_changes, pr_info)

    if args.dry_run:
        print("\n📝 코드 컨텍스트 (LLM에 전달될 내용):")
        print("-"*40)
        print(code_context[:3000])
        if len(code_context) > 3000:
            print(f"\n... (총 {len(code_context)} 글자)")
        print("\n✅ Dry run 완료")
        return

    # Run tests
    if args.mode in ('scenario', 'both'):
        run_scenario_test(pr_info, code_context, openai_api_key, args.model, args.language)

    if args.mode in ('review', 'both'):
        api_key = anthropic_api_key if args.engine == 'claude' else openai_api_key
        run_review_test(pr_info, code_context, args.engine, review_model, api_key, args.language)

    print("\n" + "="*60)
    print("✅ 테스트 완료!")
    print("="*60)


if __name__ == '__main__':
    main()
