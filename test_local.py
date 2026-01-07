#!/usr/bin/env python3
"""
로컬 테스트 스크립트
실제 GitHub PR 또는 로컬 git diff를 분석합니다.

사용법:
  # PR 분석
  python test_local.py --repo owner/repo --pr 123

  # 로컬 git diff 분석 (현재 브랜치 vs main)
  python test_local.py --local --base main

  # 특정 커밋 범위 분석
  python test_local.py --local --base HEAD~3
"""
import argparse
import os
import sys
import subprocess

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from git_analyzer import GitAnalyzer, PullRequestInfo, FileChange
from code_parser import CodeParser
from llm_client import LLMClient
from scenario_generator import ScenarioGenerator


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

    # Get changed files
    result = subprocess.run(
        ['git', 'diff', '--name-status', base],
        capture_output=True, text=True
    )

    files = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            continue

        status_map = {'A': 'added', 'M': 'modified', 'D': 'removed', 'R': 'renamed'}
        status = status_map.get(parts[0][0], 'modified')
        filename = parts[-1]

        # Get diff for file
        diff_result = subprocess.run(
            ['git', 'diff', base, '--', filename],
            capture_output=True, text=True
        )
        patch = diff_result.stdout

        # Count additions/deletions
        additions = len([l for l in patch.split('\n') if l.startswith('+') and not l.startswith('+++')])
        deletions = len([l for l in patch.split('\n') if l.startswith('-') and not l.startswith('---')])

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


def main():
    parser = argparse.ArgumentParser(description='Test Scenario Extractor - Local Test')
    parser.add_argument('--repo', help='GitHub repository (owner/repo)')
    parser.add_argument('--pr', type=int, help='PR number')
    parser.add_argument('--local', action='store_true', help='Use local git diff')
    parser.add_argument('--base', default='main', help='Base branch for local diff (default: main)')
    parser.add_argument('--model', default='o3-mini', help='OpenAI model (default: o3-mini)')
    parser.add_argument('--language', default='ko', help='Output language (default: ko)')
    parser.add_argument('--max-files', type=int, default=20, help='Max files to analyze')

    args = parser.parse_args()

    # Check API key
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    if not openai_api_key:
        print("Error: OPENAI_API_KEY 환경변수를 설정해주세요")
        print("  export OPENAI_API_KEY=your_key")
        sys.exit(1)

    # Get PR info
    if args.local:
        print(f"📂 로컬 git diff 분석 중... (base: {args.base})")
        pr_info = get_local_diff(args.base)
    elif args.repo and args.pr:
        github_token = os.environ.get('GITHUB_TOKEN')
        if not github_token:
            print("Error: GITHUB_TOKEN 환경변수를 설정해주세요")
            sys.exit(1)
        print(f"🔍 PR #{args.pr} 분석 중... ({args.repo})")
        analyzer = GitAnalyzer(github_token)
        pr_info = analyzer.get_pr_info(args.repo, args.pr, args.max_files)
    else:
        print("Error: --local 또는 --repo/--pr 옵션을 지정해주세요")
        parser.print_help()
        sys.exit(1)

    print(f"\n📋 분석 대상: {pr_info.title}")
    print(f"   브랜치: {pr_info.head_branch} → {pr_info.base_branch}")
    print(f"   변경 파일: {len(pr_info.files)}개")
    print(f"   커밋: {len(pr_info.commits)}개")

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

    # Generate scenarios
    print(f"\n🤖 {args.model}로 테스트 시나리오 생성 중...")
    llm_client = LLMClient(openai_api_key, args.model)
    generator = ScenarioGenerator(llm_client, args.language)

    try:
        result = generator.generate(code_context, len(pr_info.files))
    except Exception as e:
        print(f"\n❌ LLM 호출 실패: {e}")
        sys.exit(1)

    # Print results - LLM 원본 응답 그대로 출력
    print("\n" + "="*60)
    print("🧪 테스트 시나리오 추천")
    print("="*60)
    print(f"\n📊 분석 정보: 변경된 파일 {result.files_count}개\n")
    print(result.llm_response.content)

    # Cost info
    resp = result.llm_response
    print("\n" + "-"*60)
    print(f"💰 API 비용: ${resp.cost_usd:.4f}")
    print(f"   입력: {resp.prompt_tokens:,} tokens")
    print(f"   출력: {resp.completion_tokens:,} tokens")
    print("="*60)


if __name__ == '__main__':
    main()
