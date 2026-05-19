from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Literal

from catanatron.game import is_valid_action
from catanatron.gym.envs.action_space import from_action_space, to_action_space
from catanatron.models.enums import Action
from catanatron.models.player import Color

MapType = Literal["BASE", "TOURNAMENT", "MINI"]


class InvalidActionSelection(ValueError):
    """Raised when a selected action id is not legal for the current decision."""

    def __init__(self, message: str, runtime_refs: dict[str, str] | None = None):
        super().__init__(message)
        self.runtime_refs = runtime_refs or {}


@dataclass(frozen=True)
class SelectedAction:
    action_id: int
    rationale: str | None = None
    runtime_refs: dict[str, str] | None = None


def legal_action_json(game, map_type: MapType) -> list[dict[str, Any]]:
    """Return legal actions as stable Gym ids plus model-friendly metadata."""
    player_colors = game.state.colors
    return [
        {
            "id": to_action_space(action, player_colors, map_type),
            "type": action.action_type.value,
            "value": jsonable(action.value),
            "label": action_label(action),
        }
        for action in game.playable_actions
    ]


def validate_selected_action(game, action_id: int, map_type: MapType) -> Action:
    """Map an action id back to a Catanatron action and require it to be legal."""
    try:
        action = from_action_space(
            action_id,
            game.state.current_color(),
            game.state.colors,
            map_type,
        )
    except IndexError as exc:
        raise InvalidActionSelection(f"Action id {action_id} is outside action space") from exc

    if not is_valid_action(game.playable_actions, game.state, action):
        raise InvalidActionSelection(f"Action id {action_id} maps to illegal action {action}")

    return action


def action_to_json(action: Action) -> dict[str, Any]:
    return {
        "color": action.color.value,
        "type": action.action_type.value,
        "value": jsonable(action.value),
    }


def action_record_to_json(action_record) -> dict[str, Any]:
    return {
        "action": action_to_json(action_record.action),
        "result": jsonable(action_record.result),
    }


def jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(jsonable(key)): jsonable(item) for key, item in value.items()}
    return value


def action_label(action: Action) -> str:
    value = _format_value(action.value)
    action_name = action.action_type.value.replace("_", " ").title()
    if value is None:
        return action_name
    return f"{action_name}: {value}"


def _format_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Color):
        return value.value
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return ", ".join(str(_format_value(item)) for item in value)
    return str(value)
