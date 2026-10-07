from __future__ import annotations

import traceback
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from repomedic_core.agent import run_repair_agent
from repomedic_core.config import get_settings
from repomedic_core.db import SyncSessionLocal
from repomedic_core.github_client import GitHubService
from repomedic_core.logging import configure_logging, get_logger
from repomedic_core.models import (
    AgentTrace,
    ChecklistItem,
    CodeIndex,
    EvidenceRecord,
    PatchAttempt,
    PatchPlan,
    PRSummary,
    RepairTask,
    TaskStatus,
)
from repomedic_core.queue import redis_settings

configure_logging(get_settings().log_level)
logger = get_logger(__name__)


STATUS_MAP = {
    "queued": TaskStatus.QUEUED,
    "cloning": TaskStatus.CLONING,
    "indexing": TaskStatus.INDEXING,
    "reproducing": TaskStatus.REPRODUCING,
    "planning": TaskStatus.PLANNING,
    "patching": TaskStatus.PATCHING,
    "verifying": TaskStatus.VERIFYING,
    "awaiting_review": TaskStatus.AWAITING_REVIEW,
    "failed": TaskStatus.FAILED,
}


def _persist_agent_result(task_id: UUID, state: dict) -> None:
    with SyncSessionLocal() as session:
        task = session.execute(
            select(RepairTask)
            .options(
                selectinload(RepairTask.issue),
                selectinload(RepairTask.checklist_items),
                selectinload(RepairTask.code_index),
                selectinload(RepairTask.patch_plan),
                selectinload(RepairTask.patch_attempts),
                selectinload(RepairTask.evidence),
                selectinload(RepairTask.traces),
                selectinload(RepairTask.pr_summary),
            )
            .where(RepairTask.id == task_id)
        ).scalar_one()

        status_key = state.get("status", "awaiting_review")
        task.status = STATUS_MAP.get(status_key, TaskStatus.AWAITING_REVIEW)
        task.workspace_path = state.get("workspace")
        task.commit_sha = state.get("commit_sha")
        task.error_message = state.get("error")

        checklist = state.get("checklist") or {}
        if task.issue is not None:
            task.issue.acceptance_criteria = checklist.get("criteria") or []

        # Replace checklist items
        for item in list(task.checklist_items):
            session.delete(item)
        for idx, criterion in enumerate(checklist.get("criteria") or []):
            session.add(
                ChecklistItem(
                    task_id=task.id,
                    ordinal=idx,
                    text=criterion.get("text", ""),
                    completed=bool(criterion.get("verified")),
                )
            )

        if task.code_index:
            session.delete(task.code_index)
        session.add(
            CodeIndex(
                task_id=task.id,
                file_tree=state.get("file_tree") or [],
                symbols=(state.get("symbols") or [])[:2000],
                file_count=len(state.get("file_tree") or []),
                symbol_count=len(state.get("symbols") or []),
            )
        )

        plan = state.get("patch_plan") or {}
        if task.patch_plan:
            session.delete(task.patch_plan)
        if plan:
            session.add(
                PatchPlan(
                    task_id=task.id,
                    summary=plan.get("summary", ""),
                    rationale=plan.get("rationale", ""),
                    steps=plan.get("steps") or [],
                    target_files=plan.get("target_files") or [],
                    risk_notes=plan.get("risk_notes"),
                )
            )

        patch_result = state.get("patch_result") or {}
        if patch_result:
            session.add(
                PatchAttempt(
                    task_id=task.id,
                    attempt_number=int(patch_result.get("attempt") or state.get("attempt") or 1),
                    unified_diff=patch_result.get("unified_diff") or "",
                    files_changed=patch_result.get("files_changed") or [],
                    success=bool(patch_result.get("ok")),
                    validation_errors=patch_result.get("errors") or [],
                )
            )

        for kind, payload in (
            ("reproduction", state.get("reproduction")),
            ("tests", state.get("test_result")),
            ("lint", state.get("lint_result")),
        ):
            if not payload:
                continue
            session.add(
                EvidenceRecord(
                    task_id=task.id,
                    kind=kind,
                    command=payload.get("command"),
                    exit_code=payload.get("exit_code"),
                    stdout=payload.get("stdout") or "",
                    stderr=payload.get("stderr") or "",
                    passed=payload.get("passed"),
                    meta={"timed_out": payload.get("timed_out", False)},
                )
            )

        for trace in state.get("traces") or []:
            session.add(
                AgentTrace(
                    task_id=task.id,
                    step=trace.get("step", "unknown"),
                    tool_name=trace.get("tool_name"),
                    input_payload=trace.get("input_payload") or {},
                    output_payload=trace.get("output_payload") or {},
                    duration_ms=trace.get("duration_ms"),
                )
            )

        summary = state.get("pr_summary") or {}
        if summary:
            if task.pr_summary:
                session.delete(task.pr_summary)
            session.add(
                PRSummary(
                    task_id=task.id,
                    title=summary.get("title", ""),
                    body=summary.get("body", ""),
                    test_plan=summary.get("test_plan") or [],
                )
            )

        session.commit()


async def run_repair_job(ctx, task_id: str) -> dict:
    settings = get_settings()
    logger.info("repair_job_started", task_id=task_id)
    task_uuid = UUID(task_id)

    with SyncSessionLocal() as session:
        task = session.execute(
            select(RepairTask)
            .options(selectinload(RepairTask.issue))
            .where(RepairTask.id == task_uuid)
        ).scalar_one_or_none()
        if not task:
            logger.error("task_missing", task_id=task_id)
            return {"ok": False, "error": "missing"}
        task.status = TaskStatus.CLONING
        session.commit()
        owner, repo, issue_number = task.github_owner, task.github_repo, task.issue_number
        language = task.language
        issue_title = task.issue.title if task.issue else ""
        issue_body = task.issue.body if task.issue else ""
        issue_labels = task.issue.labels if task.issue else []

    workspace = settings.workspace_root / task_id / "repo"
    workspace.parent.mkdir(parents=True, exist_ok=True)

    try:
        if settings.synthetic_mode and not (settings.workspace_root / "fixtures" / "sample-python").exists():
            # Clone still attempted unless synthetic fixture path is used below
            pass

        fixture = settings.workspace_root / "fixtures" / "sample-python"
        use_fixture = settings.synthetic_mode or (owner == "local" and repo == "sample-python")
        if use_fixture and fixture.exists():
            import shutil

            if workspace.exists():
                shutil.rmtree(workspace)
            shutil.copytree(fixture, workspace)
            commit_sha = "synthetic"
        else:
            gh = GitHubService()
            commit_sha = gh.clone_repository(owner, repo, workspace)

        with SyncSessionLocal() as session:
            task = session.get(RepairTask, task_uuid)
            task.workspace_path = str(workspace)
            task.commit_sha = commit_sha
            task.status = TaskStatus.INDEXING
            session.commit()

        state = run_repair_agent(
            {
                "task_id": task_id,
                "owner": owner,
                "repo": repo,
                "issue_number": issue_number,
                "language": language,
                "issue_title": issue_title,
                "issue_body": issue_body,
                "issue_labels": issue_labels or [],
                "workspace": str(workspace),
                "commit_sha": commit_sha,
                "traces": [],
                "attempt": 1,
                "status": "indexing",
            }
        )
        _persist_agent_result(task_uuid, state)
        logger.info("repair_job_finished", task_id=task_id, status=state.get("status"))
        return {"ok": True, "status": state.get("status")}
    except Exception as exc:  # noqa: BLE001
        logger.error("repair_job_failed", task_id=task_id, error=str(exc), tb=traceback.format_exc())
        with SyncSessionLocal() as session:
            task = session.get(RepairTask, task_uuid)
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = str(exc)
                session.add(
                    EvidenceRecord(
                        task_id=task.id,
                        kind="error",
                        command=None,
                        exit_code=1,
                        stdout="",
                        stderr=traceback.format_exc(),
                        passed=False,
                        meta={"at": datetime.now(timezone.utc).isoformat()},
                    )
                )
                session.commit()
        return {"ok": False, "error": str(exc)}


class WorkerSettings:
    functions = [run_repair_job]
    redis_settings = redis_settings()
    max_jobs = 2
    job_timeout = 60 * 30
    keep_result = 60 * 60