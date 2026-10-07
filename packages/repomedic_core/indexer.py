from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import Path

from repomedic_core.logging import get_logger

logger = get_logger(__name__)

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
}

TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".toml",
    ".yml",
    ".yaml",
    ".cfg",
    ".ini",
    ".txt",
}


@dataclass
class SymbolInfo:
    name: str
    kind: str
    file_path: str
    line: int
    end_line: int | None = None
    docstring: str | None = None


@dataclass
class IndexResult:
    file_tree: list[str]
    symbols: list[dict]
    file_count: int
    symbol_count: int


def list_source_files(root: Path, language: str = "python") -> list[Path]:
    extensions = {
        "python": {".py"},
        "typescript": {".ts", ".tsx", ".js", ".jsx"},
        "javascript": {".js", ".jsx", ".ts", ".tsx"},
    }.get(language, {".py"})

    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in extensions or path.suffix.lower() in TEXT_EXTENSIONS:
            if path.suffix.lower() in extensions:
                files.append(path)
    return sorted(files)


def build_file_tree(root: Path, limit: int = 500) -> list[str]:
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            rel = str(path.relative_to(root)).replace("\\", "/")
            entries.append(rel)
            if len(entries) >= limit:
                break
    return entries


def _extract_python_symbols(path: Path, root: Path) -> list[SymbolInfo]:
    rel = str(path.relative_to(root)).replace("\\", "/")
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except SyntaxError:
        return []

    symbols: list[SymbolInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(
                SymbolInfo(
                    name=node.name,
                    kind="function",
                    file_path=rel,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", None),
                    docstring=ast.get_docstring(node),
                )
            )
        elif isinstance(node, ast.ClassDef):
            symbols.append(
                SymbolInfo(
                    name=node.name,
                    kind="class",
                    file_path=rel,
                    line=node.lineno,
                    end_line=getattr(node, "end_lineno", None),
                    docstring=ast.get_docstring(node),
                )
            )
    return symbols


def _extract_ts_symbols_heuristic(path: Path, root: Path) -> list[SymbolInfo]:
    """Lightweight TS/JS symbol extraction without requiring native tree-sitter bindings."""
    rel = str(path.relative_to(root)).replace("\\", "/")
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    import re

    patterns = [
        (re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function"),
        (re.compile(r"^\s*(?:export\s+)?class\s+(\w+)"), "class"),
        (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\("), "function"),
        (re.compile(r"^\s*(?:export\s+)?interface\s+(\w+)"), "interface"),
        (re.compile(r"^\s*(?:export\s+)?type\s+(\w+)"), "type"),
    ]
    symbols: list[SymbolInfo] = []
    for idx, line in enumerate(lines, start=1):
        for pattern, kind in patterns:
            match = pattern.match(line)
            if match:
                symbols.append(
                    SymbolInfo(name=match.group(1), kind=kind, file_path=rel, line=idx)
                )
                break
    return symbols


def index_repository(root: Path, language: str = "python") -> IndexResult:
    root = Path(root)
    file_tree = build_file_tree(root)
    source_files = list_source_files(root, language)
    symbols: list[SymbolInfo] = []

    for path in source_files:
        if language == "python" and path.suffix == ".py":
            symbols.extend(_extract_python_symbols(path, root))
        else:
            symbols.extend(_extract_ts_symbols_heuristic(path, root))

    symbol_dicts = [asdict(s) for s in symbols]
    logger.info(
        "indexed_repository",
        root=str(root),
        files=len(file_tree),
        symbols=len(symbol_dicts),
        language=language,
    )
    return IndexResult(
        file_tree=file_tree,
        symbols=symbol_dicts,
        file_count=len(file_tree),
        symbol_count=len(symbol_dicts),
    )


def search_symbols(
    symbols: list[dict],
    query: str,
    limit: int = 25,
) -> list[dict]:
    q = query.lower().strip()
    if not q:
        return symbols[:limit]

    tokens = [t for t in q.replace("/", " ").replace(".", " ").split() if t]
    scored: list[tuple[int, dict]] = []
    for symbol in symbols:
        hay = f"{symbol.get('name', '')} {symbol.get('file_path', '')} {symbol.get('kind', '')}".lower()
        score = 0
        for token in tokens:
            if token in hay:
                score += 2 if token in symbol.get("name", "").lower() else 1
        if score:
            scored.append((score, symbol))
    scored.sort(key=lambda item: (-item[0], item[1].get("file_path", ""), item[1].get("line", 0)))
    return [s for _, s in scored[:limit]]


def read_file_snippet(root: Path, rel_path: str, start: int = 1, end: int | None = None) -> str:
    path = Path(root) / rel_path
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(rel_path)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = max(1, start)
    end = end or min(len(lines), start + 80)
    end = min(len(lines), end)
    numbered = [f"{i}: {lines[i - 1]}" for i in range(start, end + 1)]
    return "\n".join(numbered)


def keyword_search_files(root: Path, query: str, language: str = "python", limit: int = 20) -> list[dict]:
    q = query.lower()
    hits: list[dict] = []
    for path in list_source_files(root, language):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if q not in text.lower():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        for idx, line in enumerate(text.splitlines(), start=1):
            if q in line.lower():
                hits.append({"file_path": rel, "line": idx, "snippet": line.strip()[:240]})
                if len(hits) >= limit:
                    return hits
    return hits