import re
from dataclasses import dataclass
from typing import List, Tuple
from git_analyzer import FileChange, PullRequestInfo


@dataclass
class ParsedChange:
    filename: str
    file_type: str
    module: str
    status: str
    functions_changed: List[str]
    classes_changed: List[str]
    summary: str


class CodeParser:
    FILE_TYPE_MAP = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript-react',
        '.jsx': 'javascript-react',
        '.java': 'java',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.php': 'php',
        '.cs': 'csharp',
        '.cpp': 'cpp',
        '.c': 'c',
        '.swift': 'swift',
        '.kt': 'kotlin',
    }

    def parse_changes(self, pr_info: PullRequestInfo) -> List[ParsedChange]:
        parsed = []
        for file in pr_info.files:
            parsed.append(self._parse_file(file))
        return parsed

    def _parse_file(self, file: FileChange) -> ParsedChange:
        file_type = self._get_file_type(file.filename)
        module = self._extract_module(file.filename)
        functions = self._extract_functions(file.patch, file_type) if file.patch else []
        classes = self._extract_classes(file.patch, file_type) if file.patch else []
        summary = self._generate_summary(file)

        return ParsedChange(
            filename=file.filename,
            file_type=file_type,
            module=module,
            status=file.status,
            functions_changed=functions,
            classes_changed=classes,
            summary=summary
        )

    def _get_file_type(self, filename: str) -> str:
        for ext, file_type in self.FILE_TYPE_MAP.items():
            if filename.endswith(ext):
                return file_type
        return 'unknown'

    def _extract_module(self, filename: str) -> str:
        parts = filename.split('/')
        if len(parts) > 1:
            return parts[0] if parts[0] not in ('src', 'lib', 'app') else parts[1] if len(parts) > 2 else parts[0]
        return 'root'

    def _extract_functions(self, patch: str, file_type: str) -> List[str]:
        functions = []
        patterns = {
            'python': r'^\+.*def\s+(\w+)\s*\(',
            'javascript': r'^\+.*(function\s+(\w+)|(\w+)\s*=\s*(?:async\s*)?\(|(\w+)\s*:\s*(?:async\s*)?\()',
            'typescript': r'^\+.*(function\s+(\w+)|(\w+)\s*=\s*(?:async\s*)?\(|(\w+)\s*:\s*(?:async\s*)?\()',
            'java': r'^\+.*(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(',
            'go': r'^\+.*func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(',
        }

        pattern = patterns.get(file_type, patterns.get('python'))
        if pattern:
            for line in patch.split('\n'):
                match = re.search(pattern, line)
                if match:
                    func_name = next((g for g in match.groups() if g), None)
                    if func_name and func_name not in functions:
                        functions.append(func_name)

        return functions[:10]  # Limit to 10 functions

    def _extract_classes(self, patch: str, file_type: str) -> List[str]:
        classes = []
        patterns = {
            'python': r'^\+.*class\s+(\w+)',
            'javascript': r'^\+.*class\s+(\w+)',
            'typescript': r'^\+.*(class|interface)\s+(\w+)',
            'java': r'^\+.*class\s+(\w+)',
            'go': r'^\+.*type\s+(\w+)\s+struct',
        }

        pattern = patterns.get(file_type, patterns.get('python'))
        if pattern:
            for line in patch.split('\n'):
                match = re.search(pattern, line)
                if match:
                    class_name = match.groups()[-1] if match.groups() else None
                    if class_name and class_name not in classes:
                        classes.append(class_name)

        return classes[:5]  # Limit to 5 classes

    def _generate_summary(self, file: FileChange) -> str:
        status_map = {
            'added': '신규 파일',
            'modified': '수정됨',
            'removed': '삭제됨',
            'renamed': '이름 변경됨'
        }
        status_text = status_map.get(file.status, file.status)
        return f"{status_text} (+{file.additions}/-{file.deletions})"

    def format_for_llm(self, changes: List[ParsedChange], pr_info: PullRequestInfo) -> str:
        output = []
        output.append(f"# PR 정보")
        output.append(f"- 제목: {pr_info.title}")
        output.append(f"- 브랜치: {pr_info.head_branch} → {pr_info.base_branch}")
        if pr_info.body:
            output.append(f"- 설명: {pr_info.body[:500]}")
        output.append("")

        output.append("# 커밋 메시지")
        for commit in pr_info.commits[:10]:
            output.append(f"- {commit.split(chr(10))[0]}")
        output.append("")

        output.append("# 변경된 파일")
        modules = {}
        for change in changes:
            if change.module not in modules:
                modules[change.module] = []
            modules[change.module].append(change)

        for module, module_changes in modules.items():
            output.append(f"\n## 모듈: {module}")
            for change in module_changes:
                output.append(f"\n### {change.filename} ({change.summary})")
                if change.classes_changed:
                    output.append(f"- 클래스: {', '.join(change.classes_changed)}")
                if change.functions_changed:
                    output.append(f"- 함수: {', '.join(change.functions_changed)}")

        output.append("\n# 코드 변경 상세")
        for file in pr_info.files:
            output.append(f"\n## {file.filename}")

            # 하이브리드: 전체 파일 있으면 사용, 없으면 diff + 주변 컨텍스트
            if file.content:
                output.append("(전체 파일)")
                output.append("```")
                output.append(file.content[:8000] if len(file.content) > 8000 else file.content)
                if len(file.content) > 8000:
                    output.append("... (truncated)")
                output.append("```")
                # diff도 함께 표시 (변경 위치 파악용)
                if file.patch:
                    output.append("\n변경된 부분 (diff):")
                    output.append("```diff")
                    patch = file.patch[:2000] if len(file.patch) > 2000 else file.patch
                    output.append(patch)
                    output.append("```")
            elif file.patch:
                output.append("(diff + 컨텍스트)")
                output.append("```diff")
                patch = self._expand_patch_context(file.patch)
                output.append(patch[:4000] if len(patch) > 4000 else patch)
                if len(patch) > 4000:
                    output.append("... (truncated)")
                output.append("```")

        return '\n'.join(output)

    def _expand_patch_context(self, patch: str) -> str:
        """diff의 컨텍스트를 확장 (이미 포함된 컨텍스트 라인 표시)"""
        # GitHub patch는 이미 앞뒤 3줄의 컨텍스트를 포함
        # 여기서는 추가 처리 없이 반환 (전체 파일이 없는 경우)
        return patch
