from __future__ import annotations

from repomedic_core.models import RepairTask
from repomedic_core.schemas import TaskDetail, TaskSummary


def to_task_summary(task: RepairTask) -> TaskSummary:
    return TaskSummary(
        id=task.id,
        github_owner=task.github_owner,
        github_repo=task.github_repo,
        issue_number=task.issue_number,
        issue_url=task.issue_url,
        language=task.language,
        status=task.status,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
        issue_title=task.issue.title if task.issue else None,
    )


def to_task_detail(task: RepairTask) -> TaskDetail:
    summary = to_task_summary(task)
    code_stats = None
    if task.code_index:
        code_stats = {
            "file_count": task.code_index.file_count,
            "symbol_count": task.code_index.symbol_count,
        }
    return TaskDetail(
        **summary.model_dump(),
        workspace_path=task.workspace_path,
        commit_sha=task.commit_sha,
        issue=task.issue,
        checklist_items=sorted(task.checklist_items, key=lambda c: c.ordinal),
        patch_plan=task.patch_plan,
        patch_attempts=sorted(task.patch_attempts, key=lambda p: p.attempt_number),
        evidence=sorted(task.evidence, key=lambda e: e.created_at),
        traces=sorted(task.traces, key=lambda t: t.created_at),
        pr_summary=task.pr_summary,
        review=task.review,
        code_index_stats=code_stats,
    )