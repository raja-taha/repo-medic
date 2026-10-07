from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from repomedic_core.config import get_settings
from repomedic_core.db import get_db
from repomedic_core.logging import get_logger
from repomedic_core.models import IssueSnapshot, RepairTask, TaskStatus
from repomedic_core.queue import enqueue_repair_task

router = APIRouter()
logger = get_logger(__name__)


def _verify_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    if not secret:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature)


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    settings = get_settings()
    body = await request.body()
    if not _verify_signature(body, x_hub_signature_256, settings.github_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(body.decode("utf-8"))
    if x_github_event != "issues":
        return {"ok": True, "ignored": True, "event": x_github_event}

    action = payload.get("action")
    if action not in {"opened", "reopened", "labeled"}:
        return {"ok": True, "ignored": True, "action": action}

    issue = payload.get("issue") or {}
    repo = payload.get("repository") or {}
    labels = [lbl.get("name") for lbl in issue.get("labels", []) if lbl.get("name")]
    # Only auto-queue when labeled with repomedic (or always on opened)
    if action == "labeled" and "repomedic" not in labels:
        return {"ok": True, "ignored": True, "reason": "missing repomedic label"}

    owner = (repo.get("owner") or {}).get("login") or repo.get("full_name", "").split("/")[0]
    name = repo.get("name")
    number = issue.get("number")
    if not owner or not name or not number:
        raise HTTPException(status_code=400, detail="Malformed webhook payload")

    language = "python"
    if "typescript" in labels or "javascript" in labels:
        language = "typescript" if "typescript" in labels else "javascript"

    task = RepairTask(
        github_owner=owner,
        github_repo=name,
        issue_number=int(number),
        issue_url=issue.get("html_url"),
        language=language,
        status=TaskStatus.QUEUED,
    )
    db.add(task)
    await db.flush()
    db.add(
        IssueSnapshot(
            task_id=task.id,
            title=issue.get("title") or "",
            body=issue.get("body") or "",
            labels=labels,
            author=(issue.get("user") or {}).get("login"),
            raw_payload=payload,
            acceptance_criteria=[],
        )
    )
    await db.commit()
    await enqueue_repair_task(str(task.id))
    logger.info("webhook_task_created", task_id=str(task.id), repo=f"{owner}/{name}", issue=number)
    return {"ok": True, "task_id": str(task.id)}