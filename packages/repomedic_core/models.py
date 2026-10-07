from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from repomedic_core.db import Base


class TaskStatus(str, enum.Enum):
    QUEUED = "queued"
    CLONING = "cloning"
    INDEXING = "indexing"
    REPRODUCING = "reproducing"
    PLANNING = "planning"
    PATCHING = "patching"
    VERIFYING = "verifying"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewDecisionType(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


class RepairTask(Base):
    __tablename__ = "repair_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    github_repo: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_url: Mapped[str | None] = mapped_column(String(512))
    language: Mapped[str] = mapped_column(String(32), default="python")
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", values_callable=lambda x: [e.value for e in x]),
        default=TaskStatus.QUEUED,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    workspace_path: Mapped[str | None] = mapped_column(String(1024))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    issue: Mapped[IssueSnapshot | None] = relationship(back_populates="task", uselist=False)
    checklist_items: Mapped[list[ChecklistItem]] = relationship(back_populates="task")
    code_index: Mapped[CodeIndex | None] = relationship(back_populates="task", uselist=False)
    patch_plan: Mapped[PatchPlan | None] = relationship(back_populates="task", uselist=False)
    patch_attempts: Mapped[list[PatchAttempt]] = relationship(back_populates="task")
    evidence: Mapped[list[EvidenceRecord]] = relationship(back_populates="task")
    traces: Mapped[list[AgentTrace]] = relationship(back_populates="task")
    review: Mapped[ReviewDecision | None] = relationship(back_populates="task", uselist=False)
    pr_summary: Mapped[PRSummary | None] = relationship(back_populates="task", uselist=False)

    @property
    def full_repo(self) -> str:
        return f"{self.github_owner}/{self.github_repo}"


class IssueSnapshot(Base):
    __tablename__ = "issue_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_tasks.id", ondelete="CASCADE"), unique=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    labels: Mapped[list] = mapped_column(JSONB, default=list)
    author: Mapped[str | None] = mapped_column(String(255))
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    acceptance_criteria: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[RepairTask] = relationship(back_populates="issue")


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_tasks.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_note: Mapped[str | None] = mapped_column(Text)

    task: Mapped[RepairTask] = relationship(back_populates="checklist_items")


class CodeIndex(Base):
    __tablename__ = "code_indexes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_tasks.id", ondelete="CASCADE"), unique=True
    )
    file_tree: Mapped[list] = mapped_column(JSONB, default=list)
    symbols: Mapped[list] = mapped_column(JSONB, default=list)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    symbol_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[RepairTask] = relationship(back_populates="code_index")


class PatchPlan(Base):
    __tablename__ = "patch_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_tasks.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    target_files: Mapped[list] = mapped_column(JSONB, default=list)
    risk_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[RepairTask] = relationship(back_populates="patch_plan")


class PatchAttempt(Base):
    __tablename__ = "patch_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_tasks.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    unified_diff: Mapped[str] = mapped_column(Text, default="")
    files_changed: Mapped[list] = mapped_column(JSONB, default=list)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_errors: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[RepairTask] = relationship(back_populates="patch_attempts")


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_tasks.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    command: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    passed: Mapped[bool | None] = mapped_column(Boolean)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[RepairTask] = relationship(back_populates="evidence")


class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_tasks.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(128))
    input_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[RepairTask] = relationship(back_populates="traces")


class PRSummary(Base):
    __tablename__ = "pr_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_tasks.id", ondelete="CASCADE"), unique=True
    )
    title: Mapped[str] = mapped_column(String(512), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    test_plan: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[RepairTask] = relationship(back_populates="pr_summary")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_tasks.id", ondelete="CASCADE"), unique=True
    )
    decision: Mapped[ReviewDecisionType] = mapped_column(
        Enum(
            ReviewDecisionType,
            name="review_decision_type",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    reviewer: Mapped[str] = mapped_column(String(255), default="human")
    comments: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped[RepairTask] = relationship(back_populates="review")