from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.serializers import to_task_detail, to_task_summary
from repomedic_core.db import get_db
from repomedic_core.github_client import GitHubService, parse_issue_url
from repomedic_core.models import (
    IssueSnapshot,
    RepairTask,
    ReviewDecision,
    ReviewDecisionType,
    TaskStatus,
)
from repomedic_core.queue import enqueue_repair_task
from repomedic_core.schemas import (
    CreateTaskFromUrlRequest,
    CreateTaskRequest,
    DiffResponse,
    ReviewRequest,
    TaskDetail,
    TaskSummary,
)

router = APIRouter()


TASK_LOAD = (
    selectinload(RepairTask.issue),
    selectinload(RepairTask.checklist_items),
    selectinload(RepairTask.code_index),
    selectinload(RepairTask.patch_plan),
    selectinload(RepairTask.patch_attempts),
    selectinload(RepairTask.evidence),
    selectinload(RepairTask.traces),
    selectinload(RepairTask.pr_summary),
    selectinload(RepairTask.review),
)


async def _get_task(db: AsyncSession, task_id: UUID) -> RepairTask:
    result = await db.execute(select(RepairTask).options(*TASK_LOAD).where(RepairTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/tasks", response_model=TaskDetail, status_code=201)
async def create_task(
    payload: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> TaskDetail:
    title = payload.issue_title
    body = payload.issue_body or ""
    labels: list[str] = []
    author = None
    issue_url = f"https://github.com/{payload.github_owner}/{payload.github_repo}/issues/{payload.issue_number}"
    raw: dict = {}

    if not payload.synthetic and not payload.issue_title:
        try:
            issue = GitHubService().fetch_issue(
                payload.github_owner, payload.github_repo, payload.issue_number
            )
            title = issue.title
            body = issue.body
            labels = issue.labels
            author = issue.author
            issue_url = issue.html_url
            raw = issue.raw
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif not title:
        title = f"Synthetic issue #{payload.issue_number}"

    task = RepairTask(
        github_owner=payload.github_owner,
        github_repo=payload.github_repo,
        issue_number=payload.issue_number,
        issue_url=issue_url,
        language=payload.language,
        status=TaskStatus.QUEUED,
    )
    db.add(task)
    await db.flush()

    db.add(
        IssueSnapshot(
            task_id=task.id,
            title=title or "",
            body=body,
            labels=labels,
            author=author,
            raw_payload=raw,
            acceptance_criteria=[],
        )
    )
    await db.commit()

    try:
        await enqueue_repair_task(str(task.id))
    except Exception as exc:  # noqa: BLE001
        # Allow API to create tasks even if Redis is briefly unavailable
        task.error_message = f"Queued locally; worker enqueue failed: {exc}"
        await db.commit()

    task = await _get_task(db, task.id)
    return to_task_detail(task)


@router.post("/tasks/from-url", response_model=TaskDetail, status_code=201)
async def create_task_from_url(
    payload: CreateTaskFromUrlRequest,
    db: AsyncSession = Depends(get_db),
) -> TaskDetail:
    owner, repo, number = parse_issue_url(str(payload.issue_url))
    return await create_task(
        CreateTaskRequest(
            github_owner=owner,
            github_repo=repo,
            issue_number=number,
            language=payload.language,
        ),
        db=db,
    )


@router.get("/tasks", response_model=list[TaskSummary])
async def list_tasks(
    status: TaskStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[TaskSummary]:
    stmt = (
        select(RepairTask)
        .options(selectinload(RepairTask.issue))
        .order_by(RepairTask.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(RepairTask.status == status)
    result = await db.execute(stmt)
    return [to_task_summary(t) for t in result.scalars().all()]


@router.get("/tasks/{task_id}", response_model=TaskDetail)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)) -> TaskDetail:
    return to_task_detail(await _get_task(db, task_id))


@router.get("/tasks/{task_id}/diff", response_model=DiffResponse)
async def get_diff(task_id: UUID, db: AsyncSession = Depends(get_db)) -> DiffResponse:
    task = await _get_task(db, task_id)
    if not task.patch_attempts:
        raise HTTPException(status_code=404, detail="No patch attempts yet")
    latest = max(task.patch_attempts, key=lambda p: p.attempt_number)
    return DiffResponse(
        task_id=task.id,
        attempt_number=latest.attempt_number,
        unified_diff=latest.unified_diff,
        files_changed=latest.files_changed,
        success=latest.success,
    )


@router.get("/tasks/{task_id}/diff/raw")
async def get_diff_raw(task_id: UUID, db: AsyncSession = Depends(get_db)) -> PlainTextResponse:
    task = await _get_task(db, task_id)
    if not task.patch_attempts:
        raise HTTPException(status_code=404, detail="No patch attempts yet")
    latest = max(task.patch_attempts, key=lambda p: p.attempt_number)
    return PlainTextResponse(
        content=latest.unified_diff or "",
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="repomedic-{task_id}.patch"'
        },
    )


@router.post("/tasks/{task_id}/review", response_model=TaskDetail)
async def review_task(
    task_id: UUID,
    payload: ReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> TaskDetail:
    task = await _get_task(db, task_id)
    if task.status not in {TaskStatus.AWAITING_REVIEW, TaskStatus.FAILED}:
        raise HTTPException(
            status_code=400,
            detail=f"Task status {task.status.value} is not reviewable",
        )

    if task.review:
        task.review.decision = payload.decision
        task.review.comments = payload.comments
        task.review.reviewer = payload.reviewer
    else:
        db.add(
            ReviewDecision(
                task_id=task.id,
                decision=payload.decision,
                comments=payload.comments,
                reviewer=payload.reviewer,
            )
        )

    if payload.decision == ReviewDecisionType.APPROVED:
        task.status = TaskStatus.APPROVED
    elif payload.decision == ReviewDecisionType.REJECTED:
        task.status = TaskStatus.REJECTED
    else:
        task.status = TaskStatus.AWAITING_REVIEW

    await db.commit()
    return to_task_detail(await _get_task(db, task_id))


@router.post("/tasks/{task_id}/retry", response_model=TaskDetail)
async def retry_task(task_id: UUID, db: AsyncSession = Depends(get_db)) -> TaskDetail:
    task = await _get_task(db, task_id)
    if task.status not in {
        TaskStatus.FAILED,
        TaskStatus.REJECTED,
        TaskStatus.AWAITING_REVIEW,
    }:
        raise HTTPException(status_code=400, detail="Task cannot be retried in current status")
    task.status = TaskStatus.QUEUED
    task.error_message = None
    await db.commit()
    await enqueue_repair_task(str(task.id))
    return to_task_detail(await _get_task(db, task_id))