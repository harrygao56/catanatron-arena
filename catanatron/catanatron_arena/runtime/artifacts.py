from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AttemptArtifacts:
    root: Path
    prompt_path: Path
    observation_path: Path
    legal_actions_path: Path
    decision_meta_path: Path
    events_path: Path
    outcome_path: Path
    output_copy_path: Path
    error_path: Path

    def refs(self, game_dir: Path) -> dict[str, str]:
        refs = {
            "prompt": self.prompt_path,
            "observation": self.observation_path,
            "legal_actions": self.legal_actions_path,
            "decision_meta": self.decision_meta_path,
            "events": self.events_path,
            "outcome": self.outcome_path,
        }
        if self.output_copy_path.exists():
            refs["output"] = self.output_copy_path
        if self.error_path.exists():
            refs["error"] = self.error_path
        return {key: _rel(path, game_dir) for key, path in refs.items()}


@dataclass
class RuntimeArtifacts:
    game_dir: Path
    color: str

    @property
    def seat_dir(self) -> Path:
        return self.game_dir / "runtime" / self.color

    @property
    def stderr_path(self) -> Path:
        return self.seat_dir / "pi.stderr.log"

    @property
    def session_events_path(self) -> Path:
        return self.seat_dir / "events.jsonl"

    def prepare(self) -> None:
        (self.seat_dir / "decisions").mkdir(parents=True, exist_ok=True)

    def attempt(self, decision_index: int, attempt: int) -> AttemptArtifacts:
        root = (
            self.seat_dir
            / "decisions"
            / f"turn_{decision_index:06d}_attempt_{attempt:03d}"
        )
        root.mkdir(parents=True, exist_ok=True)
        return AttemptArtifacts(
            root=root,
            prompt_path=root / "prompt.txt",
            observation_path=root / "current_observation.json",
            legal_actions_path=root / "legal_actions.json",
            decision_meta_path=root / "decision_meta.json",
            events_path=root / "agent_events.jsonl",
            outcome_path=root / "outcome.json",
            output_copy_path=root / "choice.json",
            error_path=root / "error.json",
        )

    def seat_refs(self) -> dict[str, str]:
        refs = {
            "stderr": self.stderr_path,
            "events": self.session_events_path,
        }
        return {key: _rel(path, self.game_dir) for key, path in refs.items()}


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, sort_keys=True) + "\n")


def copy_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copy2(source, destination)


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root))
