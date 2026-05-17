from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from catanatron.gym.envs.action_space import to_action_space
from catanatron.players.mcts import MCTSPlayer
from catanatron.players.minimax import AlphaBetaPlayer, SameTurnAlphaBetaPlayer
from catanatron.players.playouts import GreedyPlayoutsPlayer
from catanatron.players.search import VictoryPointPlayer
from catanatron.players.value import ValueFunctionPlayer
from catanatron.players.weighted_random import WeightedRandomPlayer

from catanatron_arena.protocol.actions import SelectedAction


class AgentRuntime(Protocol):
    name: str
    max_invalid_retries: int

    def choose_action(self, observation: dict, attempt: int = 1) -> SelectedAction:
        ...


@dataclass
class FirstActionAgent:
    name: str = "first_action"
    max_invalid_retries: int = 0

    def choose_action(self, observation: dict, attempt: int = 1) -> SelectedAction:
        action_id = observation["legal_actions"][0]["id"]
        return SelectedAction(action_id=action_id, rationale="selected first legal action")


@dataclass
class RandomAgent:
    rng: random.Random
    name: str = "random"
    max_invalid_retries: int = 0

    def choose_action(self, observation: dict, attempt: int = 1) -> SelectedAction:
        action = self.rng.choice(observation["legal_actions"])
        return SelectedAction(action_id=action["id"], rationale="selected random legal action")


def build_local_agent(spec: str, seed: int | None = None) -> AgentRuntime:
    code, params = _parse_spec(spec)
    if spec == "first_action":
        return FirstActionAgent()
    if code == "random":
        return RandomAgent(random.Random(seed))
    if code in ("weighted_random", "weighted", "w"):
        return CatanatronPlayerAgent(WeightedRandomPlayer, "weighted_random")
    if code in ("victory_point", "vp"):
        return CatanatronPlayerAgent(VictoryPointPlayer, "victory_point")
    if code in ("value", "value_function", "f"):
        return CatanatronPlayerAgent(ValueFunctionPlayer, "value")
    if code in ("mcts", "m"):
        num_simulations = _int_param(params, 0, 10)
        prunning = _bool_param(params, 1, False)
        return CatanatronPlayerAgent(
            MCTSPlayer,
            f"mcts:{num_simulations}:{int(prunning)}",
            args=(num_simulations, prunning),
        )
    if code in ("greedy", "g"):
        num_playouts = _int_param(params, 0, 10)
        return CatanatronPlayerAgent(
            GreedyPlayoutsPlayer,
            f"greedy:{num_playouts}",
            args=(num_playouts,),
        )
    if code in ("alphabeta", "alpha_beta", "ab"):
        depth = _int_param(params, 0, 2)
        prunning = _bool_param(params, 1, True)
        return CatanatronPlayerAgent(
            AlphaBetaPlayer,
            f"ab:{depth}:{int(prunning)}",
            args=(depth, prunning),
        )
    if code in ("same_turn_alphabeta", "same_turn_alpha_beta", "sab"):
        depth = _int_param(params, 0, 2)
        prunning = _bool_param(params, 1, True)
        return CatanatronPlayerAgent(
            SameTurnAlphaBetaPlayer,
            f"sab:{depth}:{int(prunning)}",
            args=(depth, prunning),
        )
    raise ValueError(f"Unknown local agent spec: {spec}")


@dataclass
class CatanatronPlayerAgent:
    player_cls: type
    name: str
    args: tuple = ()
    max_invalid_retries: int = 0

    def choose_action(self, observation: dict, attempt: int = 1) -> SelectedAction:
        raise RuntimeError(f"{self.name} requires trusted game-state access")

    def choose_action_from_game(self, game, map_type: str) -> SelectedAction:
        color = game.state.current_color()
        player = self.player_cls(color, *self.args)
        action = player.decide(game, game.playable_actions)
        action_id = to_action_space(action, game.state.colors, map_type)
        return SelectedAction(
            action_id=action_id,
            rationale=f"{self.name} selected {action.action_type.value}",
        )


def _parse_spec(spec: str) -> tuple[str, list[str]]:
    parts = spec.split(":")
    return parts[0], parts[1:]


def _int_param(params: list[str], index: int, default: int) -> int:
    if index >= len(params) or params[index] == "":
        return default
    return int(params[index])


def _bool_param(params: list[str], index: int, default: bool) -> bool:
    if index >= len(params) or params[index] == "":
        return default
    value = params[index].lower()
    if value in ("1", "true", "yes", "y"):
        return True
    if value in ("0", "false", "no", "n"):
        return False
    raise ValueError(f"Invalid boolean parameter: {params[index]}")
