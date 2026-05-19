from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from catanatron.json import GameEncoder

from catanatron_arena.protocol.actions import (
    action_record_to_json,
    action_to_json,
    jsonable,
)


@dataclass
class ReplayRecorder:
    output_dir: Path
    write_observations: bool = True
    game_dir: Path | None = None
    replay: dict[str, Any] = field(default_factory=dict)

    def start_game(self, game, config: dict[str, Any]) -> None:
        self.game_dir = self.output_dir / "games" / game.id
        (self.game_dir / "decisions").mkdir(parents=True, exist_ok=True)
        (self.game_dir / "observations").mkdir(parents=True, exist_ok=True)
        (self.game_dir / "states").mkdir(parents=True, exist_ok=True)
        self.replay = {
            "schema_version": 2,
            "game_id": game.id,
            "seed": game.seed,
            "config": jsonable(config),
            "seating_order": [color.value for color in game.state.colors],
            "initial_state_ref": self._write_state(game, 0),
            "decisions": [],
            "final": None,
        }

    def record_decision(
        self,
        observation: dict[str, Any],
        selected,
        action,
        action_record,
        latency_ms: float,
        status: str,
        game=None,
        error: str | None = None,
    ) -> None:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before record_decision")

        decision_index = observation["decision_index"]
        observation_ref = self._write_observation(observation, decision_index)
        state_before_ref = _state_ref(decision_index)
        state_after_ref = (
            self._write_state(game, decision_index + 1) if game is not None else None
        )
        selected_action_label = _selected_action_label(
            observation.get("legal_actions", []),
            selected.action_id,
        )

        summary = {
            "decision_index": decision_index,
            "decision_ref": _decision_ref(decision_index),
            "observation_ref": observation_ref,
            "state_before_ref": state_before_ref,
            "state_after_ref": state_after_ref,
            "seat_color": observation["seat_color"],
            "current_prompt": observation["current_prompt"],
            "legal_action_ids": [item["id"] for item in observation["legal_actions"]],
            "selected_action_id": selected.action_id,
            "selected_action_label": selected_action_label,
            "rationale": selected.rationale,
            "mapped_action": action_to_json(action),
            "action_record": action_record_to_json(action_record),
            "latency_ms": latency_ms,
            "status": status,
            "error": error,
            "runtime_refs": selected.runtime_refs,
        }
        detail = {
            **summary,
            "observation": jsonable(observation),
            "legal_actions": jsonable(observation["legal_actions"]),
            "selected": {
                "action_id": selected.action_id,
                "label": selected_action_label,
                "rationale": selected.rationale,
            },
            "agent": self._agent_payload(selected.runtime_refs),
        }

        self._write_decision_detail(decision_index, detail)
        self.replay["decisions"].append(summary)

    def record_failed_decision(
        self,
        observation: dict[str, Any],
        attempts: list[dict[str, Any]],
        latency_ms: float,
        status: str,
        error: str,
    ) -> None:
        if self.game_dir is None:
            raise RuntimeError(
                "start_game must be called before record_failed_decision"
            )

        decision_index = observation["decision_index"]
        observation_ref = self._write_observation(observation, decision_index)
        runtime_refs = _attempt_runtime_refs(attempts)

        summary = {
            "decision_index": decision_index,
            "decision_ref": _decision_ref(decision_index),
            "observation_ref": observation_ref,
            "state_before_ref": _state_ref(decision_index),
            "state_after_ref": None,
            "seat_color": observation["seat_color"],
            "current_prompt": observation["current_prompt"],
            "legal_action_ids": [item["id"] for item in observation["legal_actions"]],
            "attempts": attempts,
            "latency_ms": latency_ms,
            "status": status,
            "error": error,
            "runtime_refs": runtime_refs,
        }
        detail = {
            **summary,
            "observation": jsonable(observation),
            "legal_actions": jsonable(observation["legal_actions"]),
            "agent": self._attempts_payload(runtime_refs),
        }

        self._write_decision_detail(decision_index, detail)
        self.replay["decisions"].append(summary)

    def finish_game(self, game) -> Path:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before finish_game")

        self.replay["final"] = {
            "winner": game.winning_color().value if game.winning_color() else None,
            "turns": game.state.num_turns,
            "num_decisions": len(self.replay["decisions"]),
            "victory_points": _victory_points(game),
        }
        return self._write_indexes()

    def _write_observation(
        self, observation: dict[str, Any], decision_index: int
    ) -> str | None:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before writing observations")
        if not self.write_observations:
            return None

        observation_path = (
            self.game_dir / "observations" / f"turn_{decision_index:06d}.json"
        )
        observation_path.write_text(
            json.dumps(observation, indent=2, sort_keys=True), encoding="utf-8"
        )
        return str(observation_path.relative_to(self.game_dir))

    def _write_state(self, game, state_index: int) -> str:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before writing states")

        state_path = self.game_dir / _state_ref(state_index)
        state_path.write_text(
            json.dumps(game, cls=GameEncoder, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return str(state_path.relative_to(self.game_dir))

    def _write_decision_detail(
        self, decision_index: int, detail: dict[str, Any]
    ) -> str:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before writing decisions")

        decision_path = self.game_dir / _decision_ref(decision_index)
        decision_path.write_text(
            json.dumps(detail, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return str(decision_path.relative_to(self.game_dir))

    def _agent_payload(
        self, runtime_refs: dict[str, str] | None
    ) -> dict[str, Any] | None:
        if not runtime_refs:
            return None
        return _read_runtime_refs(self.game_dir, runtime_refs)

    def _attempts_payload(
        self,
        runtime_refs: dict[str, dict[str, str]] | None,
    ) -> dict[str, Any] | None:
        if not runtime_refs:
            return None
        return {
            attempt: _read_runtime_refs(self.game_dir, refs)
            for attempt, refs in runtime_refs.items()
        }

    def _write_indexes(self) -> Path:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before writing indexes")

        replay_path = self.game_dir / "replay.json"
        replay_path.write_text(
            json.dumps(self.replay, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        viewer = {
            "schema_version": 1,
            "replay_schema_version": self.replay["schema_version"],
            "game_id": self.replay["game_id"],
            "seed": self.replay["seed"],
            "config": self.replay["config"],
            "seating_order": self.replay["seating_order"],
            "initial_state_ref": self.replay["initial_state_ref"],
            "final": self.replay["final"],
            "timeline": [
                _viewer_timeline_item(decision) for decision in self.replay["decisions"]
            ],
        }
        viewer_path = self.game_dir / "viewer.json"
        viewer_path.write_text(
            json.dumps(viewer, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return replay_path

    def fail_game(self, game, reason: str) -> Path:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before fail_game")

        self.replay["final"] = {
            "winner": None,
            "turns": game.state.num_turns,
            "num_decisions": len(self.replay["decisions"]),
            "victory_points": _victory_points(game),
            "failed": True,
            "failure_reason": reason,
        }
        return self._write_indexes()


def _victory_points(game) -> dict[str, int]:
    points = {}
    for index, color in enumerate(game.state.colors):
        points[color.value] = game.state.player_state[f"P{index}_ACTUAL_VICTORY_POINTS"]
    return points


def _attempt_runtime_refs(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    refs = {
        str(attempt["attempt"]): attempt["runtime_refs"]
        for attempt in attempts
        if attempt.get("runtime_refs")
    }
    return refs or None


def _state_ref(state_index: int) -> str:
    return f"states/state_{state_index:06d}.json"


def _decision_ref(decision_index: int) -> str:
    return f"decisions/decision_{decision_index:06d}.json"


def _selected_action_label(
    legal_actions: list[dict[str, Any]], action_id: int
) -> str | None:
    for action in legal_actions:
        if action.get("id") == action_id:
            return action.get("label")
    return None


def _viewer_timeline_item(decision: dict[str, Any]) -> dict[str, Any]:
    item = {
        "decision_index": decision["decision_index"],
        "decision_ref": decision["decision_ref"],
        "state_before_ref": decision["state_before_ref"],
        "state_after_ref": decision["state_after_ref"],
        "seat_color": decision["seat_color"],
        "current_prompt": decision["current_prompt"],
        "selected_action_id": decision.get("selected_action_id"),
        "selected_action_label": decision.get("selected_action_label"),
        "mapped_action": decision.get("mapped_action"),
        "action_record": decision.get("action_record"),
        "latency_ms": decision["latency_ms"],
        "status": decision["status"],
        "error": decision["error"],
    }
    if "attempts" in decision:
        item["attempts"] = decision["attempts"]
    return item


def _read_runtime_refs(
    game_dir: Path | None,
    runtime_refs: dict[str, str],
) -> dict[str, Any]:
    if game_dir is None:
        return {}

    payload: dict[str, Any] = {"refs": runtime_refs}
    for key, ref in runtime_refs.items():
        path = _safe_ref_path(game_dir, ref)
        if path is None or not path.exists() or not path.is_file():
            payload[key] = None
            continue
        if path.suffix == ".jsonl":
            payload[key] = _read_jsonl(path)
        elif path.suffix == ".json":
            payload[key] = _read_json(path)
        else:
            payload[key] = path.read_text(encoding="utf-8")
    return payload


def _safe_ref_path(game_dir: Path, ref: str) -> Path | None:
    path = Path(ref)
    if path.is_absolute() or ".." in path.parts:
        return None
    return game_dir / path


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_jsonl(path: Path) -> list[Any]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            items.append({"type": "malformed_jsonl", "raw": line})
    return items
