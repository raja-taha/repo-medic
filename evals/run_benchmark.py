#!/usr/bin/env python3
"""Offline RepoMedic evaluation over curated fixture scenarios."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from repomedic_core.agent.nodes import index_code, parse_acceptance, reproduce, search_relevant
from repomedic_core.indexer import index_repository
from repomedic_core.llm import heuristic_checklist
from repomedic_core.patching import validate_proposal
from repomedic_core.schemas import FileEdit, PatchProposal


def load_dataset() -> list[dict]:
    path = Path(__file__).parent / "datasets" / "curated_issues.json"
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_path(name: str | None) -> Path | None:
    if not name:
        return None
    return ROOT / "workspaces" / "fixtures" / name


def grade(case: dict) -> dict:
    if case.get("skip"):
        return {"id": case["id"], "passed": True, "skipped": True, "reason": "skipped"}

    fixture = fixture_path(case.get("fixture"))
    grader = case.get("grader", "default")

    if grader == "path_safety":
        assert fixture is not None
        proposal = PatchProposal(
            files=[FileEdit(path=".env", action="create", content="SECRET=1\n")],
            explanation="probe",
        )
        result = validate_proposal(fixture, proposal)
        ok = (not result.ok) and any("Unsafe" in e or ".env" in e for e in result.errors)
        return {"id": case["id"], "passed": ok, "detail": result.errors}

    if grader == "index_symbols":
        assert fixture is not None
        indexed = index_repository(fixture, case.get("language", "python"))
        names = {s["name"] for s in indexed.symbols}
        ok = all(sig in names for sig in case.get("success_signals", []))
        return {"id": case["id"], "passed": ok, "detail": sorted(names)}

    if grader == "pre_patch_fail":
        assert fixture is not None
        state = {
            "workspace": str(fixture),
            "language": case.get("language", "python"),
            "traces": [],
        }
        state = reproduce(state)
        ok = not bool((state.get("reproduction") or {}).get("passed"))
        return {"id": case["id"], "passed": ok, "detail": state.get("reproduction")}

    # default: checklist + retrieval quality
    assert fixture is not None
    state = {
        "issue_title": case["title"],
        "issue_body": case["body"],
        "language": case.get("language", "python"),
        "workspace": str(fixture),
        "traces": [],
    }
    state = parse_acceptance(state)
    state = index_code(state)
    state = search_relevant(state)

    checklist_text = json.dumps(state.get("checklist") or {}).lower()
    hits = state.get("relevant_hits") or {}
    hit_blob = json.dumps(hits).lower()
    signals = [s.lower() for s in case.get("success_signals", [])]
    matched = [s for s in signals if s in checklist_text or s in hit_blob]
    ok = (len(matched) >= max(1, len(signals) // 2)) if signals else True

    # Also ensure heuristic checklist works deterministically
    heuristic = heuristic_checklist(case["title"], case["body"], case.get("language", "python"))
    ok = ok and bool(heuristic.get("criteria"))

    return {
        "id": case["id"],
        "passed": ok,
        "matched_signals": matched,
        "symbol_hits": len(hits.get("symbols") or []),
    }


def main() -> int:
    cases = load_dataset()
    results = [grade(case) for case in cases]
    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    report = {
        "metric": "task_support_success",
        "passed": passed,
        "total": total,
        "rate": round(passed / total, 3) if total else 0.0,
        "results": results,
    }
    out = Path(__file__).parent / "last_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())