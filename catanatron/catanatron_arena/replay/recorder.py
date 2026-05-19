from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from catanatron_arena.protocol.actions import action_record_to_json, action_to_json, jsonable


@dataclass
class ReplayRecorder:
    output_dir: Path
    write_observations: bool = True
    game_dir: Path | None = None
    replay: dict[str, Any] = field(default_factory=dict)

    def start_game(self, game, config: dict[str, Any]) -> None:
        self.game_dir = self.output_dir / "games" / game.id
        (self.game_dir / "observations").mkdir(parents=True, exist_ok=True)
        self.replay = {
            "schema_version": 1,
            "game_id": game.id,
            "seed": game.seed,
            "config": jsonable(config),
            "seating_order": [color.value for color in game.state.colors],
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
        error: str | None = None,
    ) -> None:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before record_decision")

        decision_index = observation["decision_index"]
        observation_ref = self._write_observation(observation, decision_index)

        self.replay["decisions"].append(
            {
                "decision_index": decision_index,
                "observation_ref": observation_ref,
                "seat_color": observation["seat_color"],
                "current_prompt": observation["current_prompt"],
                "legal_action_ids": [item["id"] for item in observation["legal_actions"]],
                "selected_action_id": selected.action_id,
                "rationale": selected.rationale,
                "mapped_action": action_to_json(action),
                "action_record": action_record_to_json(action_record),
                "latency_ms": latency_ms,
                "status": status,
                "error": error,
                "runtime_refs": selected.runtime_refs,
            }
        )

    def record_failed_decision(
        self,
        observation: dict[str, Any],
        attempts: list[dict[str, Any]],
        latency_ms: float,
        status: str,
        error: str,
    ) -> None:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before record_failed_decision")

        decision_index = observation["decision_index"]
        observation_ref = self._write_observation(observation, decision_index)

        self.replay["decisions"].append(
            {
                "decision_index": decision_index,
                "observation_ref": observation_ref,
                "seat_color": observation["seat_color"],
                "current_prompt": observation["current_prompt"],
                "legal_action_ids": [item["id"] for item in observation["legal_actions"]],
                "attempts": attempts,
                "latency_ms": latency_ms,
                "status": status,
                "error": error,
                "runtime_refs": _attempt_runtime_refs(attempts),
            }
        )

    def finish_game(self, game) -> Path:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before finish_game")

        self.replay["final"] = {
            "winner": game.winning_color().value if game.winning_color() else None,
            "turns": game.state.num_turns,
            "num_decisions": len(self.replay["decisions"]),
            "victory_points": _victory_points(game),
        }
        replay_path = self.game_dir / "replay.json"
        replay_path.write_text(json.dumps(self.replay, indent=2, sort_keys=True), encoding="utf-8")
        return replay_path

    def _write_observation(self, observation: dict[str, Any], decision_index: int) -> str | None:
        if self.game_dir is None:
            raise RuntimeError("start_game must be called before writing observations")
        if not self.write_observations:
            return None

        observation_path = self.game_dir / "observations" / f"turn_{decision_index:06d}.json"
        observation_path.write_text(json.dumps(observation, indent=2, sort_keys=True), encoding="utf-8")
        return str(observation_path.relative_to(self.game_dir))

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
        replay_path = self.game_dir / "replay.json"
        replay_path.write_text(json.dumps(self.replay, indent=2, sort_keys=True), encoding="utf-8")
        return replay_path


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
