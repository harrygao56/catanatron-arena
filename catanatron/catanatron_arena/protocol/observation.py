from __future__ import annotations

from typing import Any

from catanatron.features import create_sample

from catanatron_arena.protocol.actions import MapType, jsonable, legal_action_json


def build_observation(
    game,
    map_type: MapType,
    decision_index: int,
    recent_action_limit: int = 12,
) -> dict[str, Any]:
    """Build a redacted decision packet for the currently prompted player."""
    seat_color = game.state.current_color()
    features = create_sample(game, seat_color)
    recent_records = game.state.action_records[-recent_action_limit:]

    return {
        "game_id": game.id,
        "decision_index": decision_index,
        "current_prompt": game.state.current_prompt.value,
        "seat_color": seat_color.value,
        "seating_order": [color.value for color in game.state.colors],
        "turn_index": game.state.num_turns,
        "features": jsonable(features),
        "legal_actions": legal_action_json(game, map_type),
        "recent_actions": [
            {
                "color": record.action.color.value,
                "type": record.action.action_type.value,
                "value": jsonable(record.action.value),
                "result": jsonable(record.result),
            }
            for record in recent_records
        ],
    }
