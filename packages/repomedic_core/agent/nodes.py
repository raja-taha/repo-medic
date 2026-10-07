from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from repomedic_core.config import get_settings
from repomedic_core.indexer import index_repository, keyword_search_files, read_file_snippet, search_symbols
from repomedic_core.llm import LLMClient, heuristic_checklist
from repomedic_core.logging import get_logger
from repomedic_core.patching import apply_proposal
from repomedic_core.sandbox import SandboxManager, detect_lint_command, detect_test_command
from repomedic_core.schemas import (
    PatchPlanSchema,
    PatchProposal,
    PRSummarySchema,
    RepairChecklist,
)

logger = get_logger(__name__)


def _trace(state: dict[str, Any], step: str, tool: str | None, inp: dict, out: dict, started: float) -> None:
    traces = list(state.get("traces") or [])
    traces.append(
        {
            "step": step,
            "tool_name": tool,
            "input_payload": inp,
            "output_payload": out,
            "duration_ms": int((time.time() - started) * 1000),
        }
    )
    state["traces"] = traces


def parse_acceptance(state: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    llm = LLMClient()
    title = state.get("issue_title", "")
    body = state.get("issue_body", "")
    language = state.get("language", "python")

    if llm.available:
        checklist = llm.complete_json(
            system=(
                "You convert GitHub issues into a concrete repair checklist. "
                "Extract measurable acceptance criteria. Do not invent product features."
            ),
            user=f"Title: {title}\n\nBody:\n{body}\n\nLanguage: {language}",
            schema=RepairChecklist,
        ).model_dump()
    else:
        checklist = heuristic_checklist(title, body, language)

    state["checklist"] = checklist
    state["status"] = "indexing"
    _trace(state, "parse_acceptance", "llm_or_heuristic", {"title": title}, checklist, started)
    return state


def index_code(state: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    workspace = Path(state["workspace"])
    result = index_repository(workspace, state.get("language", "python"))
    state["file_tree"] = result.file_tree
    state["symbols"] = result.symbols
    state["status"] = "reproducing"
    out = {"file_count": result.file_count, "symbol_count": result.symbol_count}
    _trace(state, "index_code", "indexer", {"workspace": str(workspace)}, out, started)
    return state


def search_relevant(state: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    workspace = Path(state["workspace"])
    language = state.get("language", "python")
    query_parts = [state.get("issue_title", "")]
    for item in (state.get("checklist") or {}).get("criteria", []):
        query_parts.append(item.get("text", ""))
    query = " ".join(query_parts)[:500]

    symbol_hits = search_symbols(state.get("symbols") or [], query, limit=15)
    file_hits = keyword_search_files(workspace, _primary_keyword(query), language, limit=15)
    # Enrich with snippets for top symbols
    enriched = []
    for hit in symbol_hits[:8]:
        try:
            snippet = read_file_snippet(
                workspace,
                hit["file_path"],
                start=max(1, hit.get("line", 1) - 5),
                end=(hit.get("line", 1) + 25),
            )
        except FileNotFoundError:
            snippet = None
        enriched.append({**hit, "snippet": snippet})

    state["relevant_hits"] = {"symbols": enriched, "files": file_hits, "query": query}
    _trace(
        state,
        "search_relevant",
        "code_search",
        {"query": query},
        {"symbol_hits": len(enriched), "file_hits": len(file_hits)},
        started,
    )
    return state


def _primary_keyword(query: str) -> str:
    stop = {"the", "and", "for", "with", "that", "this", "from", "into", "when", "should", "must"}
    tokens = [t.strip(".,()[]{}") for t in query.split() if len(t) > 3 and t.lower() not in stop]
    return tokens[0] if tokens else query[:40]


def reproduce(state: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    workspace = Path(state["workspace"])
    language = state.get("language", "python")
    sandbox = SandboxManager()
    cmd = detect_test_command(workspace, language)
    result = sandbox.run(workspace, cmd)
    state["reproduction"] = {
        "command": result.command,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "passed": result.passed,
        "timed_out": result.timed_out,
    }
    state["status"] = "planning"
    _trace(
        state,
        "reproduce",
        "sandbox",
        {"command": result.command},
        {"exit_code": result.exit_code, "passed": result.passed},
        started,
    )
    return state


def plan_patch(state: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    llm = LLMClient()
    context = {
        "title": state.get("issue_title"),
        "body": state.get("issue_body"),
        "checklist": state.get("checklist"),
        "relevant": state.get("relevant_hits"),
        "reproduction": {
            "command": (state.get("reproduction") or {}).get("command"),
            "exit_code": (state.get("reproduction") or {}).get("exit_code"),
            "stderr_tail": ((state.get("reproduction") or {}).get("stderr") or "")[-2000:],
            "stdout_tail": ((state.get("reproduction") or {}).get("stdout") or "")[-2000:],
        },
        "file_tree_sample": (state.get("file_tree") or [])[:80],
    }

    if llm.available:
        plan = llm.complete_json(
            system=(
                "You are RepoMedic, a careful software repair planner. "
                "Propose a minimal patch plan. Prefer existing APIs. Never invent files that are not in the tree."
            ),
            user=str(context),
            schema=PatchPlanSchema,
        ).model_dump()
    else:
        # Heuristic plan for offline/synthetic demos
        targets = []
        for hit in (state.get("relevant_hits") or {}).get("symbols", [])[:3]:
            targets.append(hit.get("file_path"))
        for hit in (state.get("relevant_hits") or {}).get("files", [])[:3]:
            targets.append(hit.get("file_path"))
        targets = list(dict.fromkeys([t for t in targets if t]))
        plan = {
            "summary": f"Investigate and fix: {state.get('issue_title')}",
            "rationale": "Synthetic-mode plan based on keyword/symbol hits.",
            "steps": [
                "Inspect relevant symbols and failing test output",
                "Apply a minimal fix in the implicated files",
                "Re-run tests and static checks",
            ],
            "target_files": targets or (state.get("file_tree") or [])[:3],
            "risk_notes": "Synthetic mode — replace with LLM planning when OPENAI_API_KEY is set.",
        }

    state["patch_plan"] = plan
    state["status"] = "patching"
    _trace(state, "plan_patch", "llm_or_heuristic", {"targets": plan.get("target_files")}, plan, started)
    return state


def generate_and_apply_patch(state: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    settings = get_settings()
    llm = LLMClient()
    workspace = Path(state["workspace"])
    attempt = int(state.get("attempt") or 1)

    # Keep context small so the model does not try to rewrite huge files.
    file_contexts = []
    for rel in (state.get("patch_plan") or {}).get("target_files", [])[:5]:
        try:
            content = read_file_snippet(workspace, rel, start=1, end=120)
            file_contexts.append({"path": rel, "content": content})
        except FileNotFoundError:
            continue

    body = (state.get("issue_body") or "")[:2500]
    try:
        if llm.available:
            proposal = llm.complete_json(
                system=(
                    "You are RepoMedic. Emit a MINIMAL surgical patch as JSON. "
                    f"Change at most {min(settings.max_files_changed, 5)} files. "
                    "For modify: set action=modify with unique old_str and new_str "
                    "(short contiguous snippets only — typically < 40 lines each). "
                    "For create: action=create with new_str as the full small new file. "
                    "Never return entire large source files in content. "
                    "Do not invent paths outside the provided file list unless creating a tiny test file."
                ),
                user=(
                    f"Issue: {state.get('issue_title')}\n\n"
                    f"Body:\n{body}\n\n"
                    f"Plan: {state.get('patch_plan')}\n\n"
                    f"Previous attempt failures: {state.get('patch_result')}\n\n"
                    f"Relevant file snippets:\n{json_ready(file_contexts)}"
                ),
                schema=PatchProposal,
                max_tokens=max(settings.llm_max_tokens, 8192),
                retries=2,
            )
        else:
            proposal = PatchProposal(
                files=[],
                explanation="No LLM key — skipping file edits in synthetic mode.",
            )

        applied = apply_proposal(workspace, proposal)
        state["patch_proposal"] = proposal.model_dump()
        state["patch_result"] = {
            "ok": applied.ok,
            "errors": applied.errors,
            "files_changed": applied.files_changed,
            "unified_diff": applied.unified_diff,
            "attempt": attempt,
            "explanation": proposal.explanation,
        }
        state["status"] = "verifying" if applied.ok or not proposal.files else "patching"
        files_touched = [f.path for f in proposal.files]
    except Exception as exc:  # noqa: BLE001
        logger.error("patch_generation_failed", error=str(exc))
        state["patch_result"] = {
            "ok": False,
            "errors": [str(exc)],
            "files_changed": [],
            "unified_diff": "",
            "attempt": attempt,
            "explanation": "",
        }
        # Continue to verify/review with failure evidence instead of crashing the job
        state["status"] = "verifying"
        state["error"] = str(exc)
        files_touched = []
        proposal = PatchProposal(files=[], explanation=str(exc))

    state["attempt"] = attempt
    _trace(
        state,
        "generate_and_apply_patch",
        "patcher",
        {"attempt": attempt, "files": files_touched},
        {"ok": (state.get("patch_result") or {}).get("ok"), "errors": (state.get("patch_result") or {}).get("errors")},
        started,
    )
    return state


def json_ready(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)[:12_000]


def verify(state: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    workspace = Path(state["workspace"])
    language = state.get("language", "python")
    sandbox = SandboxManager()

    test_cmd = detect_test_command(workspace, language)
    test_result = sandbox.run(workspace, test_cmd)
    state["test_result"] = {
        "command": test_result.command,
        "exit_code": test_result.exit_code,
        "stdout": test_result.stdout,
        "stderr": test_result.stderr,
        "passed": test_result.passed,
    }

    lint_cmd = detect_lint_command(workspace, language)
    if lint_cmd:
        lint_result = sandbox.run(workspace, lint_cmd)
        state["lint_result"] = {
            "command": lint_result.command,
            "exit_code": lint_result.exit_code,
            "stdout": lint_result.stdout,
            "stderr": lint_result.stderr,
            "passed": lint_result.passed,
        }
    else:
        state["lint_result"] = {"command": None, "passed": True, "stdout": "", "stderr": ""}

    settings = get_settings()
    patch_ok = (state.get("patch_result") or {}).get("ok", False)
    tests_ok = test_result.passed
    # In synthetic mode with empty patch, still move to review with evidence
    if settings.synthetic_mode or not LLMClient().available:
        state["status"] = "awaiting_review"
    elif patch_ok and tests_ok:
        state["status"] = "awaiting_review"
    elif int(state.get("attempt") or 1) < settings.max_patch_attempts:
        state["attempt"] = int(state.get("attempt") or 1) + 1
        state["status"] = "patching"
    else:
        state["status"] = "awaiting_review"
        state["error"] = state.get("error") or "Max patch attempts reached; submitting best effort for review"

    _trace(
        state,
        "verify",
        "sandbox",
        {"test_cmd": test_result.command},
        {"tests_passed": test_result.passed, "status": state["status"]},
        started,
    )
    return state


def write_pr_summary(state: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    llm = LLMClient()
    if llm.available:
        summary = llm.complete_json(
            system="Write a concise PR title/body and test plan for a human reviewer.",
            user=(
                f"Issue: {state.get('issue_title')}\n"
                f"Plan: {state.get('patch_plan')}\n"
                f"Diff:\n{(state.get('patch_result') or {}).get('unified_diff', '')[:8000]}\n"
                f"Tests: {state.get('test_result')}"
            ),
            schema=PRSummarySchema,
        ).model_dump()
    else:
        summary = {
            "title": f"fix: {state.get('issue_title')}",
            "body": (
                "## Summary\n"
                f"- Addresses `{state.get('owner')}/{state.get('repo')}#{state.get('issue_number')}`\n"
                f"- {(state.get('patch_plan') or {}).get('summary', '')}\n\n"
                "## Evidence\n"
                f"- Tests passed: {(state.get('test_result') or {}).get('passed')}\n"
                f"- Lint passed: {(state.get('lint_result') or {}).get('passed')}\n"
            ),
            "test_plan": [
                "Review the unified diff",
                "Confirm failing reproduction before the patch",
                "Re-run the project test suite",
            ],
        }
    state["pr_summary"] = summary
    if state.get("status") != "awaiting_review":
        state["status"] = "awaiting_review"
    _trace(state, "write_pr_summary", "llm_or_heuristic", {}, summary, started)
    return state