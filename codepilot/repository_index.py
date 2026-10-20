"""Bounded, content-addressed Python repository context helpers."""

from __future__ import annotations

import ast
import hashlib
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codepilot.security import is_sensitive_file, redact_sensitive_text
from codepilot.tools.repo import PathPolicyError, resolve_repo_path


MAX_INDEX_FILES = 2_000
MAX_INDEX_FILE_BYTES = 1_000_000
MAX_INDEX_TOTAL_BYTES = 50_000_000
MAX_GUIDANCE_CHARS = 12_000
MAX_GUIDANCE_TOTAL_CHARS = 24_000
MAX_GUIDANCE_BYTES = 48_000
_INDEX_IGNORED_DIRS = {
    ".git",
    ".tmp",
    ".venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}


@dataclass(frozen=True)
class IndexedFile:
    path: str
    module: str
    sha256: str
    source: str


@dataclass(frozen=True)
class Symbol:
    path: str
    module: str
    name: str
    qualified_name: str
    kind: str
    line: int
    end_line: int
    sha256: str


@dataclass(frozen=True)
class CallReference:
    path: str
    caller: str
    target: str
    line: int
    sha256: str


@dataclass(frozen=True)
class PythonIndex:
    revision: str
    files: tuple[IndexedFile, ...]
    symbols: tuple[Symbol, ...]
    references: tuple[CallReference, ...]
    parse_errors: tuple[str, ...]


def load_project_instructions(repo_root: Path, path: str = ".") -> str:
    """Load applicable AGENTS.md files from repository root through target dir."""
    root = repo_root.resolve(strict=True)
    target = resolve_repo_path(root, path)
    directory = target if target.is_dir() else target.parent
    relative_directory = directory.relative_to(root)
    directories = [root]
    current = root
    for part in relative_directory.parts:
        current = current / part
        directories.append(current)

    sections: list[str] = []
    remaining = MAX_GUIDANCE_TOTAL_CHARS
    for directory in directories:
        guidance_path = directory / "AGENTS.md"
        if not guidance_path.is_file():
            continue
        try:
            safe_path = resolve_repo_path(root, guidance_path.relative_to(root).as_posix())
            if safe_path.stat().st_size > MAX_GUIDANCE_BYTES:
                continue
            raw = safe_path.read_bytes()
            content = redact_sensitive_text(
                raw.decode("utf-8", errors="replace")[:MAX_GUIDANCE_CHARS]
            )
        except (OSError, PathPolicyError):
            continue
        if not remaining:
            break
        content = content[:remaining]
        relative = safe_path.relative_to(root).as_posix()
        digest = hashlib.sha256(raw).hexdigest()
        sections.append(f"### {relative} (SHA-256: {digest})\n{content}")
        remaining -= len(content)

    if not sections:
        return "目标目录没有适用的 AGENTS.md。"
    return "\n\n".join(sections)


def get_python_index(context: Any) -> PythonIndex:
    """Return cached AST index; exact content digest invalidates changed files."""
    root: Path = context.repo_root.resolve(strict=True)
    raw_files: list[tuple[str, bytes]] = []
    total_bytes = 0
    ignored_dirs = {part.casefold() for part in _INDEX_IGNORED_DIRS}
    for candidate in root.rglob("*.py"):
        try:
            relative = candidate.relative_to(root)
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root):
                continue
            if any(part.casefold() in ignored_dirs for part in relative.parts):
                continue
            if is_sensitive_file(relative) or not resolved.is_file():
                continue
            size = resolved.stat().st_size
            if size > MAX_INDEX_FILE_BYTES or total_bytes + size > MAX_INDEX_TOTAL_BYTES:
                continue
            raw = resolved.read_bytes()
        except (OSError, RuntimeError):
            continue
        raw_files.append((relative.as_posix(), raw))
        total_bytes += len(raw)
        if len(raw_files) >= MAX_INDEX_FILES:
            break

    digest_builder = hashlib.sha256()
    for relative, raw in raw_files:
        digest_builder.update(relative.encode("utf-8"))
        digest_builder.update(b"\0")
        digest_builder.update(hashlib.sha256(raw).digest())
    revision = digest_builder.hexdigest()
    cached = getattr(context, "repository_index", None)
    if getattr(context, "repository_index_revision", None) == revision and cached is not None:
        return cached

    files: list[IndexedFile] = []
    symbols: list[Symbol] = []
    references: list[CallReference] = []
    parse_errors: list[str] = []
    for relative, raw in raw_files:
        file_digest = hashlib.sha256(raw).hexdigest()
        module = _module_name(relative)
        try:
            source = raw.decode("utf-8")
            tree = ast.parse(source, filename=relative)
        except (UnicodeDecodeError, SyntaxError) as exc:
            parse_errors.append(f"{relative}: {type(exc).__name__}")
            continue
        files.append(IndexedFile(relative, module, file_digest, source))
        visitor = _IndexVisitor(relative, module, file_digest, symbols, references)
        visitor.visit(tree)

    index = PythonIndex(
        revision=revision,
        files=tuple(files),
        symbols=tuple(symbols),
        references=tuple(references),
        parse_errors=tuple(parse_errors),
    )
    context.repository_index = index
    context.repository_index_revision = revision
    return index


def project_map(context: Any, max_chars: int = 12_000) -> str:
    index = get_python_index(context)
    groups = Counter(Path(item.path).parts[0] if len(Path(item.path).parts) > 1 else "(root)" for item in index.files)
    symbol_counts = Counter(
        Path(symbol.path).parts[0] if len(Path(symbol.path).parts) > 1 else "(root)"
        for symbol in index.symbols
    )
    lines = [
        f"Python 项目图：{len(index.files)} 个可解析文件，{len(index.symbols)} 个类/函数，"
        f"{len(index.references)} 个调用点。",
        f"内容版本 SHA-256：{index.revision}",
        "模块分布（顶层目录）：",
    ]
    for name, count in groups.most_common(80):
        lines.append(f"- {name}/：{count} 个 Python 文件，{symbol_counts[name]} 个定义")
    if index.parse_errors:
        lines.append(f"未解析文件：{len(index.parse_errors)}；首项：{index.parse_errors[0]}")
    return _truncate("\n".join(lines), max_chars)


def search_symbols(context: Any, query: str, limit: int = 50) -> str:
    index = get_python_index(context)
    needle = query.casefold()
    matches = [
        symbol for symbol in index.symbols
        if needle in symbol.name.casefold() or needle in symbol.qualified_name.casefold()
    ][:limit]
    if not matches:
        return f"没有匹配符号：{query}\n内容版本 SHA-256：{index.revision}"
    lines = [f"内容版本 SHA-256：{index.revision}", "匹配定义："]
    lines.extend(
        f"- {symbol.kind} {symbol.qualified_name} — {symbol.path}:{symbol.line}-"
        f"{symbol.end_line} [文件 SHA-256: {symbol.sha256}]"
        for symbol in matches
    )
    return _truncate("\n".join(lines), 12_000)


def find_references(context: Any, symbol_name: str, limit: int = 100) -> str:
    index = get_python_index(context)
    needle = symbol_name.rsplit(".", 1)[-1]
    matches = [
        item for item in index.references
        if item.target == needle or item.target.endswith("." + needle)
    ][:limit]
    lines = [f"内容版本 SHA-256：{index.revision}", f"调用 {needle} 的位置："]
    if not matches:
        lines.append("没有找到静态调用点；动态调用、反射和别名可能无法由 AST 识别。")
    else:
        lines.extend(
            f"- {item.path}:{item.line} {item.caller} -> {item.target} "
            f"[文件 SHA-256: {item.sha256}]"
            for item in matches
        )
    return _truncate("\n".join(lines), 12_000)


def suggest_test_paths(context: Any, limit: int = 30) -> str:
    root: Path = context.repo_root.resolve(strict=True)
    index = get_python_index(context)
    changed = _changed_python_paths(root)
    test_files = [
        file for file in index.files
        if "tests" in Path(file.path).parts
        and (Path(file.path).name.startswith("test_") or Path(file.path).name.endswith("_test.py"))
    ]
    if not changed:
        return "当前没有未提交的 Python 文件差异；目标测试建议为空。"

    candidate_tests: dict[str, str] = {}
    changed_modules = {_module_name(path) for path in changed}
    changed_symbols = {
        symbol.name for symbol in index.symbols if symbol.path in changed
    }
    for test in test_files:
        if test.path in changed:
            candidate_tests[test.path] = "test file is itself changed"
            continue
        try:
            tree = ast.parse(test.source, filename=test.path)
        except SyntaxError:
            continue
        imported_modules: set[str] = set()
        imported_names: set[str] = set()
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module)
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Call):
                called_names.add(_call_target(node.func).rsplit(".", 1)[-1])
        if any(
            module in imported_modules
            or any(imported.startswith(module + ".") or module.startswith(imported + ".") for imported in imported_modules)
            for module in changed_modules
        ):
            candidate_tests[test.path] = "imports a changed module"
        elif changed_symbols.intersection(imported_names | called_names):
            candidate_tests[test.path] = "imports or calls a changed symbol"

    if not candidate_tests:
        candidate_tests = {test.path: "fallback: no static dependency match" for test in test_files}
    selected = list(candidate_tests.items())[:limit]
    lines = [
        f"变更 Python 文件：{', '.join(changed)}",
        "静态候选测试（启发式建议，非完整依赖证明）：",
    ]
    lines.extend(f"- {path} — {reason}" for path, reason in selected)
    lines.append("运行候选测试后，仍必须运行任务配置的完整测试套件。")
    return "\n".join(lines)


def _changed_python_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "*.py"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _module_name(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _call_target(node: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts)) or "<dynamic>"


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... 已截断"


class _IndexVisitor(ast.NodeVisitor):
    def __init__(self, path: str, module: str, digest: str, symbols: list[Symbol], references: list[CallReference]) -> None:
        self.path = path
        self.module = module
        self.digest = digest
        self.symbols = symbols
        self.references = references
        self.scope: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._definition(node, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._definition(node, "function")

    visit_AsyncFunctionDef = visit_FunctionDef

    def _definition(self, node: ast.ClassDef | ast.FunctionDef, kind: str) -> None:
        self.scope.append(node.name)
        qualified = ".".join([self.module, *self.scope]).strip(".")
        self.symbols.append(
            Symbol(
                path=self.path,
                module=self.module,
                name=node.name,
                qualified_name=qualified,
                kind=kind,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno),
                sha256=self.digest,
            )
        )
        for child in node.body:
            self.visit(child)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        self.references.append(
            CallReference(
                path=self.path,
                caller=".".join([self.module, *self.scope]).strip(".") or self.module,
                target=_call_target(node.func),
                line=node.lineno,
                sha256=self.digest,
            )
        )
        self.generic_visit(node)
