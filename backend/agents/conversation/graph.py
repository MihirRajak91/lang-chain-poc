# agents/conversation/graph.py

from langgraph.graph import StateGraph, END
from .models import ConversationState
from .nodes import (
    chat_node,
    extractor_node,
    gap_check_node,
    fill_gap_node,
    confirm_node,
    done_node,
)
from .routers import route_after_gap_check

def build_graph() -> StateGraph:
    graph = StateGraph(ConversationState)

    graph.add_node("chat_node", chat_node)
    graph.add_node("extractor_node", extractor_node)
    graph.add_node("gap_check_node", gap_check_node)
    graph.add_node("fill_gap_node", fill_gap_node)
    graph.add_node("confirm_node", confirm_node)
    graph.add_node("done_node", done_node)

    # One graph invocation should handle exactly one user turn.
    graph.set_entry_point("extractor_node")
    graph.add_edge("extractor_node", "gap_check_node")

    graph.add_conditional_edges(
        "gap_check_node",
        route_after_gap_check,
        {
            "chat_node": "chat_node",
            "fill_gap_node": "fill_gap_node",
            "confirm_node": "confirm_node",
            "done_node": "done_node",
        },
    )

    graph.add_edge("chat_node", END)
    graph.add_edge("fill_gap_node", END)
    graph.add_edge("confirm_node", END)
    graph.add_edge("done_node", END)

    return graph.compile()
