#!/usr/bin/env python3
"""Create a synthetic repair task against the bundled Python fixture."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


async def main() -> None:
    payload = {
        "github_owner": "local",
        "github_repo": "sample-python",
        "issue_number": 1,
        "language": "python",
        "synthetic": True,
        "issue_title": "divide by zero should raise ZeroDivisionError",
        "issue_body": (
            "Acceptance criteria:\n"
            "- Calling divide(1, 0) must raise ZeroDivisionError\n"
            "- Existing divide(10, 2) behavior stays 5\n"
            "- Unit tests must pass"
        ),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(f"{API}/api/v1/tasks", json=payload)
        res.raise_for_status()
        data = res.json()
        print(json.dumps({"task_id": data["id"], "status": data["status"]}, indent=2))
        print(f"Review UI: http://localhost:3000/tasks/{data['id']}")


if __name__ == "__main__":
    # Ensure fixture path exists for synthetic worker mode
    fixture = Path(__file__).resolve().parents[1] / "workspaces" / "fixtures" / "sample-python"
    if not fixture.exists():
        raise SystemExit(f"Missing fixture at {fixture}")
    asyncio.run(main())