from __future__ import annotations

from typing import Any


DEFAULT_CRISIS_NODE_LIMIT = 160
DEFAULT_CRISIS_HISTORY_LIMIT = 256
DEFAULT_CRISIS_EDGE_LIMIT = 384
DEFAULT_QUEUE_LIMIT = 512


def _node_priority(item: tuple[str, dict[str, Any]]) -> tuple[int, float, int, str]:
    crisis_id, node = item
    active = 1 if node.get("phase") != "resolved" else 0
    intensity = float(node.get("intensity", 0.0) or 0.0)
    tick_started = int(node.get("tick_started", 0) or 0)
    return (active, intensity, tick_started, crisis_id)


def compact_world_metadata(
    metadata: dict[str, Any],
    *,
    current_tick: int,
    crisis_node_limit: int = DEFAULT_CRISIS_NODE_LIMIT,
    crisis_history_limit: int = DEFAULT_CRISIS_HISTORY_LIMIT,
    crisis_edge_limit: int = DEFAULT_CRISIS_EDGE_LIMIT,
    queue_limit: int = DEFAULT_QUEUE_LIMIT,
) -> dict[str, int]:
    """Bound persistent simulation metadata before serializing world snapshots.

    WORLD ENGINE intentionally keeps long-lived beliefs and strategic memory, but
    event/crisis histories and delayed queues must not grow without bounds in the
    persistent live-world timeline. The function mutates metadata in place and
    returns compaction counters for telemetry/tests.
    """

    stats = {
        "crisis_nodes_removed": 0,
        "crisis_history_removed": 0,
        "crisis_edges_removed": 0,
        "pending_forecasts_removed": 0,
        "delayed_effects_removed": 0,
    }

    graph = metadata.get("crisis_graph")
    if isinstance(graph, dict):
        nodes = graph.get("nodes")
        if isinstance(nodes, dict) and len(nodes) > crisis_node_limit:
            ranked = sorted(nodes.items(), key=_node_priority, reverse=True)
            keep_items = ranked[:crisis_node_limit]
            keep_ids = {key for key, _ in keep_items}
            stats["crisis_nodes_removed"] = len(nodes) - len(keep_items)
            graph["nodes"] = {key: value for key, value in keep_items}

            history = graph.get("history")
            if isinstance(history, list):
                history = [
                    row
                    for row in history
                    if not isinstance(row, dict)
                    or str(row.get("crisis_id", "")) in keep_ids
                ]
                graph["history"] = history

            edges = graph.get("edges")
            if isinstance(edges, list):
                graph["edges"] = [
                    edge
                    for edge in edges
                    if not isinstance(edge, dict)
                    or (
                        (
                            not str(edge.get("from", "")).startswith("crisis:")
                            or str(edge.get("from", "")) in keep_ids
                        )
                        and (
                            not str(edge.get("to", "")).startswith("crisis:")
                            or str(edge.get("to", "")) in keep_ids
                        )
                    )
                ]

        history = graph.get("history")
        if isinstance(history, list) and len(history) > crisis_history_limit:
            stats["crisis_history_removed"] = len(history) - crisis_history_limit
            graph["history"] = history[-crisis_history_limit:]

        edges = graph.get("edges")
        if isinstance(edges, list) and len(edges) > crisis_edge_limit:
            stats["crisis_edges_removed"] = len(edges) - crisis_edge_limit
            graph["edges"] = edges[-crisis_edge_limit:]

    pending = metadata.get("pending_forecasts")
    if isinstance(pending, list) and len(pending) > queue_limit:
        # Keep the forecasts due soonest, then newest origins when due dates tie.
        pending = sorted(
            pending,
            key=lambda row: (
                int(row.get("due_tick", current_tick + 999999))
                if isinstance(row, dict)
                else current_tick + 999999,
                -int(row.get("origin_tick", 0))
                if isinstance(row, dict)
                else 0,
            ),
        )
        stats["pending_forecasts_removed"] = len(pending) - queue_limit
        metadata["pending_forecasts"] = pending[:queue_limit]

    delayed = metadata.get("delayed_effects")
    if isinstance(delayed, list) and len(delayed) > queue_limit:
        delayed = sorted(
            delayed,
            key=lambda row: (
                int(row.get("due_tick", current_tick + 999999))
                if isinstance(row, dict)
                else current_tick + 999999
            ),
        )
        stats["delayed_effects_removed"] = len(delayed) - queue_limit
        metadata["delayed_effects"] = delayed[:queue_limit]

    metadata["compaction"] = {
        "tick": int(current_tick),
        **stats,
        "crisis_nodes": len(
            metadata.get("crisis_graph", {}).get("nodes", {})
            if isinstance(metadata.get("crisis_graph"), dict)
            else {}
        ),
    }
    return stats
