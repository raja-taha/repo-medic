from __future__ import annotations

import difflib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from repomedic_core.config import get_settings
from repomedic_core.logging import get_logger
from repomedic_core.schemas import FileEdit, PatchProposal

logger = get_logger(__name__)

FORBIDDEN_PATH_PARTS = {
    ".git",
    "node_modules",
    ".env",
    "venv",
    ".venv",
}


@dataclass
class PatchValidation:
    ok: bool
    errors: list[str]
    files_changed: list[str]
    unified_diff: str


def _is_safe_path(root: Path, rel_path: str) -> bool:
    try:
        full = (root / rel_path).resolve()
        full.relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    parts = Path(rel_path).parts
    if any(part in FORBIDDEN_PATH_PARTS for part in parts):
        return False
    if any(part.startswith(".env") for part in parts):
        return False
    return True


def validate_proposal(root: Path, proposal: PatchProposal) -> PatchValidation:
    settings = get_settings()
    errors: list[str] = []
    files: list[str] = []

    if not proposal.files:
        errors.append("Patch proposal contains no file edits")
    if len(proposal.files) > settings.max_files_changed:
        errors.append(
            f"Too many files changed ({len(proposal.files)} > {settings.max_files_changed})"
        )

    for edit in proposal.files:
        if not _is_safe_path(root, edit.path):
            errors.append(f"Unsafe or out-of-bounds path: {edit.path}")
            continue
        files.append(edit.path)
        if edit.action in {"modify", "create"} and edit.content is None:
            errors.append(f"Missing content for {edit.action}: {edit.path}")
        if edit.action == "modify":
            target = root / edit.path
            if not target.exists():
                errors.append(f"Cannot modify missing file: {edit.path}")

    return PatchValidation(ok=not errors, errors=errors, files_changed=files, unified_diff="")


def apply_proposal(root: Path, proposal: PatchProposal) -> PatchValidation:
    root = Path(root)
    validation = validate_proposal(root, proposal)
    if not validation.ok:
        return validation

    before_snapshots: dict[str, str | None] = {}
    for edit in proposal.files:
        path = root / edit.path
        if path.exists() and path.is_file():
            before_snapshots[edit.path] = path.read_text(encoding="utf-8", errors="ignore")
        else:
            before_snapshots[edit.path] = None

    try:
        for edit in proposal.files:
            _apply_edit(root, edit)
    except Exception as exc:  # noqa: BLE001
        # Best-effort rollback
        for rel, content in before_snapshots.items():
            path = root / rel
            if content is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(content, encoding="utf-8")
        return PatchValidation(
            ok=False,
            errors=[f"Failed to apply patch: {exc}"],
            files_changed=[],
            unified_diff="",
        )

    diff = build_unified_diff(root, before_snapshots)
    settings = get_settings()
    if len(diff.encode("utf-8")) > settings.max_diff_bytes:
        # Rollback oversized patch
        for rel, content in before_snapshots.items():
            path = root / rel
            if content is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_text(content, encoding="utf-8")
        return PatchValidation(
            ok=False,
            errors=[f"Diff exceeds max size ({settings.max_diff_bytes} bytes)"],
            files_changed=[],
            unified_diff="",
        )

    return PatchValidation(
        ok=True,
        errors=[],
        files_changed=list(before_snapshots.keys()),
        unified_diff=diff,
    )


def _apply_edit(root: Path, edit: FileEdit) -> None:
    path = root / edit.path
    if edit.action == "delete":
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(edit.content or "", encoding="utf-8")


def build_unified_diff(root: Path, before_snapshots: dict[str, str | None]) -> str:
    chunks: list[str] = []
    for rel, before in sorted(before_snapshots.items()):
        path = root / rel
        after = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else None
        before_lines = (before or "").splitlines(keepends=True)
        after_lines = (after or "").splitlines(keepends=True)
        from_file = f"a/{rel}" if before is not None else "/dev/null"
        to_file = f"b/{rel}" if after is not None else "/dev/null"
        diff = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=from_file,
            tofile=to_file,
        )
        text = "".join(diff)
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def git_diff(workspace: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "--no-color"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout
    except OSError:
        return ""


def write_diff_file(workspace: Path, diff: str, name: str = "repomedic.patch") -> Path:
    out = Path(workspace).parent / name
    out.write_text(diff, encoding="utf-8")
    return out