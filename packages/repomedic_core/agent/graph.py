from __future__ import annotations

from typing import Any

from repomedic_core.agent import nodes
from repomedic_core.logging import get_logger

logger = get_logger(__name__)


def run_repair_agent(initial_state: dict[str, Any]) -> dict[str, Any]:
    """
    Execute the RepoMedic repair loop.

    Uses LangGraph when available; otherwise falls back to a deterministic
    sequential pipeline with the same node functions (keeps local/dev simple).
    """
    try:
        return _run_with_langgraph(initial_state)
    except Exception as exc:  # noqa: BLE001
        logger.warning("langgraph_unavailable_fallback", error=str(exc))
        return _run_sequential(initial_state)


def _run_sequential(state: dict[str, Any]) -> dict[str, Any]:
    state = dict(state)
    state.setdefault("traces", [])
    state.setdefault("attempt", 1)

    pipeline = [
        nodes.parse_acceptance,
        nodes.index_code,
        nodes.search_relevant,
        nodes.reproduce,
        nodes.plan_patch,
    ]
    for step in pipeline:
        state = step(state)
        if state.get("error"):
            state["status"] = "failed"
            return state

    # Patch + verify with retries handled inside verify status
    while True:
        state = nodes.generate_and_apply_patch(state)
        state = nodes.verify(state)
        if state.get("status") != "patching":
            break

    state = nodes.write_pr_summary(state)
    return state


def _run_with_langgraph(initial_state: dict[str, Any]) -> dict[str, Any]:
    from langgraph.graph import END, StateGraph

    from repomedic_core.agent.state import AgentState

    graph = StateGraph(AgentState)
    graph.add_node("parse_acceptance", nodes.parse_acceptance)
    graph.add_node("index_code", nodes.index_code)
    graph.add_node("search_relevant", nodes.search_relevant)
    graph.add_node("reproduce", nodes.reproduce)
    graph.add_node("plan_patch", nodes.plan_patch)
    graph.add_node("generate_and_apply_patch", nodes.generate_and_apply_patch)
    graph.add_node("verify", nodes.verify)
    graph.add_node("write_pr_summary", nodes.write_pr_summary)

    graph.set_entry_point("parse_acceptance")
    graph.add_edge("parse_acceptance", "index_code")
    graph.add_edge("index_code", "search_relevant")
    graph.add_edge("search_relevant", "reproduce")
    graph.add_edge("reproduce", "plan_patch")
    graph.add_edge("plan_patch", "generate_and_apply_patch")
    graph.add_edge("generate_and_apply_patch", "verify")

    def _route_after_verify(state: AgentState) -> str:
        if state.get("status") == "patching":
            return "generate_and_apply_patch"
        return "write_pr_summary"

    graph.add_conditional_edges(
        "verify",
        _route_after_verify,
        {
            "generate_and_apply_patch": "generate_and_apply_patch",
            "write_pr_summary": "write_pr_summary",
        },
    )
    graph.add_edge("write_pr_summary", END)

    app = graph.compile()
    result = app.invoke(initial_state)
    return dict(result)