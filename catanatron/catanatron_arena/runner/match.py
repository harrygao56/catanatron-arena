from __future__ import annotations

import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from catanatron.game import Game, TURNS_LIMIT
from catanatron.models.map import NumberPlacement, build_map
from catanatron.models.player import Color, Player

from catanatron_arena.agents.local import AgentRuntime
from catanatron_arena.protocol.actions import (
    InvalidActionSelection,
    MapType,
    SelectedAction,
    validate_selected_action,
)
from catanatron_arena.protocol.observation import build_observation
from catanatron_arena.replay.recorder import ReplayRecorder


DEFAULT_COLORS = (Color.RED, Color.BLUE, Color.ORANGE, Color.WHITE)


@dataclass(frozen=True)
class MatchConfig:
    map_type: MapType = "BASE"
    number_placement: NumberPlacement = "official_spiral"
    seed: int | None = None
    vps_to_win: int = 10
    max_turns: int = TURNS_LIMIT
    max_decisions: int = TURNS_LIMIT * 20
    default_invalid_retries: int = 3
    write_observations: bool = True


@dataclass(frozen=True)
class MatchResult:
    game_id: str
    winner: str | None
    turns: int
    decisions: int
    replay_path: Path
    failed: bool = False
    failure_reason: str | None = None


def run_match(
    agents: Sequence[AgentRuntime],
    output_dir: Path,
    config: MatchConfig | None = None,
) -> MatchResult:
    config = config or MatchConfig()
    if len(agents) < 2 or len(agents) > 4:
        raise ValueError("Arena matches require 2 to 4 agents")

    colors = DEFAULT_COLORS[: len(agents)]
    players = [Player(color) for color in colors]
    game = Game(
        players,
        seed=config.seed,
        catan_map=build_map(config.map_type, config.number_placement),
        number_placement=config.number_placement,
        vps_to_win=config.vps_to_win,
    )
    runtimes_by_color = {color: agent for color, agent in zip(colors, agents)}

    recorder = ReplayRecorder(output_dir, write_observations=config.write_observations)
    recorder.start_game(
        game,
        {
            "map_type": config.map_type,
            "number_placement": config.number_placement,
            "vps_to_win": config.vps_to_win,
            "max_turns": config.max_turns,
            "max_decisions": config.max_decisions,
            "agents": [agent.name for agent in agents],
            "agent_by_color": {
                color.value: runtimes_by_color[color].name for color in colors
            },
        },
    )

    workspace_root = output_dir.resolve() / "games" / game.id

    with ExitStack() as stack:
        for color, agent in runtimes_by_color.items():
            if hasattr(agent, "start") and hasattr(agent, "stop"):
                agent.start(
                    game_id=game.id,
                    color=color.value,
                    workspace_root=workspace_root,
                )
                stack.callback(agent.stop)

        decision_index = 0
        while game.winning_color() is None and game.state.num_turns < config.max_turns:
            if decision_index >= config.max_decisions:
                break

            color = game.state.current_color()
            runtime = runtimes_by_color[color]
            observation = build_observation(game, config.map_type, decision_index)

            max_retries = getattr(runtime, "max_invalid_retries", config.default_invalid_retries)
            attempts: list[dict] = []
            started = time.monotonic()
            for attempt_index in range(max_retries + 1):
                selected = None
                try:
                    if hasattr(runtime, "choose_action_from_game"):
                        selected = runtime.choose_action_from_game(game, config.map_type)
                    else:
                        selected = runtime.choose_action(observation, attempt=attempt_index + 1)
                    action = validate_selected_action(game, selected.action_id, config.map_type)
                    status = "ok" if attempt_index == 0 else "ok_after_retry"
                    error = None
                    break
                except InvalidActionSelection as exc:
                    attempts.append(
                        {
                            "attempt": attempt_index + 1,
                            "selected_action_id": selected.action_id if selected else None,
                            "rationale": selected.rationale if selected else None,
                            "error": str(exc),
                        }
                    )
                    if attempt_index == max_retries:
                        latency_ms = (time.monotonic() - started) * 1000
                        reason = (
                            f"{runtime.name} failed to select a valid action after "
                            f"{max_retries + 1} attempt(s)"
                        )
                        recorder.record_failed_decision(
                            observation,
                            attempts,
                            latency_ms,
                            "invalid_action_failed",
                            reason,
                        )
                        replay_path = recorder.fail_game(game, reason)
                        return MatchResult(
                            game_id=game.id,
                            winner=None,
                            turns=game.state.num_turns,
                            decisions=decision_index + 1,
                            replay_path=replay_path,
                            failed=True,
                            failure_reason=reason,
                        )

            latency_ms = (time.monotonic() - started) * 1000

            action_record = game.execute(action)
            recorder.record_decision(
                observation,
                selected,
                action,
                action_record,
                latency_ms,
                status,
                error,
            )
            decision_index += 1

        replay_path = recorder.finish_game(game)
        winner = game.winning_color()
        return MatchResult(
            game_id=game.id,
            winner=winner.value if winner else None,
            turns=game.state.num_turns,
            decisions=decision_index,
            replay_path=replay_path,
        )
