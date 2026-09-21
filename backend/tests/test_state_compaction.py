from app.state_compaction import compact_world_metadata


def test_compact_world_metadata_bounds_long_lived_state():
    metadata = {
        "crisis_graph": {
            "nodes": {
                f"crisis:{index}": {
                    "phase": "resolved" if index < 80 else "escalating",
                    "intensity": (index % 100) / 100,
                    "tick_started": index,
                }
                for index in range(240)
            },
            "history": [
                {"crisis_id": f"crisis:{index % 240}", "tick": index}
                for index in range(900)
            ],
            "edges": [
                {
                    "from": f"crisis:{index % 240}",
                    "to": f"actor:{index % 10}",
                    "tick": index,
                }
                for index in range(1200)
            ],
        },
        "pending_forecasts": [
            {"target": f"A:{index}", "due_tick": 100 + index, "origin_tick": index}
            for index in range(700)
        ],
        "delayed_effects": [
            {"target": "A", "due_tick": 100 + index}
            for index in range(700)
        ],
    }

    stats = compact_world_metadata(metadata, current_tick=100)

    graph = metadata["crisis_graph"]
    assert len(graph["nodes"]) <= 160
    assert len(graph["history"]) <= 256
    assert len(graph["edges"]) <= 384
    assert len(metadata["pending_forecasts"]) <= 512
    assert len(metadata["delayed_effects"]) <= 512
    assert stats["crisis_nodes_removed"] > 0
    assert metadata["compaction"]["tick"] == 100


def test_compaction_keeps_small_state_unchanged():
    metadata = {
        "crisis_graph": {
            "nodes": {
                "crisis:1": {
                    "phase": "escalating",
                    "intensity": 0.7,
                    "tick_started": 4,
                }
            },
            "history": [{"crisis_id": "crisis:1", "tick": 4}],
            "edges": [],
        },
        "pending_forecasts": [],
        "delayed_effects": [],
    }

    stats = compact_world_metadata(metadata, current_tick=4)

    assert "crisis:1" in metadata["crisis_graph"]["nodes"]
    assert all(value == 0 for value in stats.values())
