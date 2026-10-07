from pathlib import Path

from repomedic_core.agent.nodes import index_code, parse_acceptance, search_relevant
from repomedic_core.config import get_settings


def test_offline_acceptance_and_index(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_MODE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    fixture = Path(__file__).resolve().parents[1] / "workspaces" / "fixtures" / "sample-python"
    state = {
        "issue_title": "divide by zero should raise",
        "issue_body": "When b is 0, divide must raise ZeroDivisionError instead of returning 0.",
        "language": "python",
        "workspace": str(fixture),
        "traces": [],
    }
    state = parse_acceptance(state)
    assert state["checklist"]["criteria"]
    state = index_code(state)
    assert state["symbols"]
    state = search_relevant(state)
    assert state["relevant_hits"]["symbols"] or state["relevant_hits"]["files"]
    get_settings.cache_clear()