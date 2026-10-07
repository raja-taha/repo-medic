from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from repomedic_core.models import ReviewDecisionType, TaskStatus


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class CreateTaskRequest(BaseModel):
    github_owner: str = Field(..., min_length=1, max_length=255)
    github_repo: str = Field(..., min_length=1, max_length=255)
    issue_number: int = Field(..., ge=1)
    language: str = Field(default="python", pattern="^(python|typescript|javascript)$")
    issue_title: str | None = None
    issue_body: str | None = None
    synthetic: bool = False


class CreateTaskFromUrlRequest(BaseModel):
    issue_url: HttpUrl
    language: str = Field(default="python", pattern="^(python|typescript|javascript)$")


class ChecklistItemOut(BaseModel):
    id: UUID
    ordinal: int
    text: str
    completed: bool
    evidence_note: str | None = None

    model_config = {"from_attributes": True}


class IssueOut(BaseModel):
    title: str
    body: str
    labels: list[Any] = []
    author: str | None = None
    acceptance_criteria: list[Any] = []

    model_config = {"from_attributes": True}


class PatchPlanOut(BaseModel):
    summary: str
    rationale: str
    steps: list[Any] = []
    target_files: list[Any] = []
    risk_notes: str | None = None

    model_config = {"from_attributes": True}


class PatchAttemptOut(BaseModel):
    id: UUID
    attempt_number: int
    unified_diff: str
    files_changed: list[Any] = []
    success: bool
    validation_errors: list[Any] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class EvidenceOut(BaseModel):
    id: UUID
    kind: str
    command: str | None = None
    exit_code: int | None = None
    stdout: str
    stderr: str
    passed: bool | None = None
    meta: dict[str, Any] = {}
    created_at: datetime

    model_config = {"from_attributes": True}


class TraceOut(BaseModel):
    id: UUID
    step: str
    tool_name: str | None = None
    input_payload: dict[str, Any] = {}
    output_payload: dict[str, Any] = {}
    duration_ms: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PRSummaryOut(BaseModel):
    title: str
    body: str
    test_plan: list[Any] = []

    model_config = {"from_attributes": True}


class ReviewOut(BaseModel):
    decision: ReviewDecisionType
    reviewer: str
    comments: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskSummary(BaseModel):
    id: UUID
    github_owner: str
    github_repo: str
    issue_number: int
    issue_url: str | None = None
    language: str
    status: TaskStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    issue_title: str | None = None

    model_config = {"from_attributes": True}


class TaskDetail(TaskSummary):
    workspace_path: str | None = None
    commit_sha: str | None = None
    issue: IssueOut | None = None
    checklist_items: list[ChecklistItemOut] = []
    patch_plan: PatchPlanOut | None = None
    patch_attempts: list[PatchAttemptOut] = []
    evidence: list[EvidenceOut] = []
    traces: list[TraceOut] = []
    pr_summary: PRSummaryOut | None = None
    review: ReviewOut | None = None
    code_index_stats: dict[str, Any] | None = None


class ReviewRequest(BaseModel):
    decision: ReviewDecisionType
    comments: str | None = None
    reviewer: str = "human"


class DiffResponse(BaseModel):
    task_id: UUID
    attempt_number: int | None = None
    unified_diff: str
    files_changed: list[Any] = []
    success: bool = False


class SymbolHit(BaseModel):
    name: str
    kind: str
    file_path: str
    line: int
    snippet: str | None = None


class AcceptanceCriterion(BaseModel):
    id: str
    text: str
    verified: bool = False


class RepairChecklist(BaseModel):
    criteria: list[AcceptanceCriterion]
    reproduction_hint: str | None = None
    language: str = "python"


class PatchPlanSchema(BaseModel):
    summary: str
    rationale: str
    steps: list[str]
    target_files: list[str]
    risk_notes: str | None = None


class FileEdit(BaseModel):
    """Surgical edit. Prefer search/replace over rewriting whole files."""

    path: str
    action: str = Field(pattern="^(modify|create|delete)$")
    # For modify: exact substring to find (must be unique in the file)
    old_str: str | None = None
    # For modify: replacement text; for create: full new-file contents
    new_str: str | None = None
    # Legacy/full-rewrite fallback (avoid — easily truncates JSON)
    content: str | None = None


class PatchProposal(BaseModel):
    files: list[FileEdit] = Field(default_factory=list, max_length=8)
    explanation: str


class PRSummarySchema(BaseModel):
    title: str
    body: str
    test_plan: list[str]