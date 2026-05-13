from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from catanatron_arena.protocol.actions import SelectedAction


class AgentRuntime(Protocol):
    name: str
    max_invalid_retries: int

    def choose_action(self, observation: dict) -> SelectedAction:
        ...


@dataclass
class FirstActionAgent:
    name: str = "first_action"
    max_invalid_retries: int = 0

    def choose_action(self, observation: dict) -> SelectedAction:
        action_id = observation["legal_actions"][0]["id"]
        return SelectedAction(action_id=action_id, rationale="selected first legal action")


@dataclass
class RandomAgent:
    rng: random.Random
    name: str = "random"
    max_invalid_retries: int = 0

    def choose_action(self, observation: dict) -> SelectedAction:
        action = self.rng.choice(observation["legal_actions"])
        return SelectedAction(action_id=action["id"], rationale="selected random legal action")


def build_local_agent(spec: str, seed: int | None = None) -> AgentRuntime:
    if spec == "first_action":
        return FirstActionAgent()
    if spec == "random":
        return RandomAgent(random.Random(seed))
    raise ValueError(f"Unknown local agent spec: {spec}")
