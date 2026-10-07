from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID


class AgentState(TypedDict, total=False):
    task_id: str
    owner: str
    repo: str
    issue_number: int
    language: str
    issue_title: str
    issue_body: str
    issue_labels: list[str]
    workspace: str
    commit_sha: str
    checklist: dict[str, Any]
    file_tree: list[str]
    symbols: list[dict[str, Any]]
    relevant_hits: list[dict[str, Any]]
    reproduction: dict[str, Any]
    patch_plan: dict[str, Any]
    patch_proposal: dict[str, Any]
    patch_result: dict[str, Any]
    test_result: dict[str, Any]
    lint_result: dict[str, Any]
    pr_summary: dict[str, Any]
    traces: list[dict[str, Any]]
    error: str
    status: str
    attempt: int