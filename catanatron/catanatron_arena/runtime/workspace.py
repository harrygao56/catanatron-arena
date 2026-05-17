"""Per-seat per-game workspace layout for sandboxed model agents.

Each seat in an arena match gets its own workspace directory that is mounted
into a Docker container for the lifetime of one game. The host writes
per-decision observation files into the workspace; the agent's tool extension
writes attempt outputs back into the same directory. After the game the
workspace is destroyed (or archived for debugging).

Layout::

    <root>/
      AGENTS.md
      current_observation.json        # rewritten each decision
      legal_actions.json              # rewritten each decision
      current_decision.json           # rewritten each decision
      observations/
        turn_000000.json              # historical record per decision
      outputs/
        turn_000000_attempt_001.json  # agent writes; host validates
      .pi/
        sessions/
        extensions/
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_AGENTS_MD = """\
# Catanatron Arena Agent

You are playing one game of Settlers of Catan through the Catanatron Arena
benchmark. The game engine runs on the host. You run inside an isolated
container and choose one legal action per decision.

## Per-decision protocol

For each decision the host writes the following files inside this workspace
(your working directory inside the container):

- `current_observation.json` — your player-view of the game state.
- `legal_actions.json` — the list of legal actions you may choose from.
- `current_decision.json` — metadata: `decision_index`, `attempt`,
  `seat_color`, and the absolute container path of the file the
  `choose_action` tool should write to (`output_path`).

You must respond by calling the `choose_action` tool with:

- `action_id` — an integer that matches an `id` in `legal_actions.json`.
- `rationale` — a short explanation of why you chose this action.

The host validates `action_id` against the engine's legal actions. If the
action is invalid, you will be re-prompted in the same session with the same
`legal_actions.json` and a brief explanation; each decision allows a limited
number of attempts.

## Workspace lifetime

This directory persists for the entire game and is destroyed when the game
ends. There is no cross-game memory. You may create scratch files (notes,
`memory.md`, etc.) to help yourself across turns within this game.

## What you cannot see

- Opponents' resource cards, development cards, or hidden hands.
- Deck order or future dice rolls.
- The raw engine `Game` or `State` objects.
"""


@dataclass(frozen=True)
class SeatWorkspace:
    """Path layout for one seat's per-game workspace."""

    color: str
    root: Path
    container_root: str = "/workspace"

    def container_path(self, host_path: Path) -> str:
        """Translate a host path inside this workspace to its in-container path."""
        relative = host_path.relative_to(self.root).as_posix()
        return f"{self.container_root.rstrip('/')}/{relative}"

    @property
    def agents_md_path(self) -> Path:
        return self.root / "AGENTS.md"

    @property
    def observations_dir(self) -> Path:
        return self.root / "observations"

    @property
    def outputs_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def pi_dir(self) -> Path:
        return self.root / ".pi"

    @property
    def pi_sessions_dir(self) -> Path:
        return self.pi_dir / "sessions"

    @property
    def pi_extensions_dir(self) -> Path:
        return self.pi_dir / "extensions"

    @property
    def current_observation_path(self) -> Path:
        return self.root / "current_observation.json"

    @property
    def legal_actions_path(self) -> Path:
        return self.root / "legal_actions.json"

    @property
    def current_decision_path(self) -> Path:
        return self.root / "current_decision.json"

    def observation_path(self, decision_index: int) -> Path:
        return self.observations_dir / f"turn_{decision_index:06d}.json"

    def output_path(self, decision_index: int, attempt: int) -> Path:
        return self.outputs_dir / f"turn_{decision_index:06d}_attempt_{attempt:03d}.json"

    def write_decision_files(
        self,
        observation: dict,
        attempt: int,
    ) -> Path:
        """Write the four per-decision files. Returns the host path of the
        expected output file. Paths exposed to the agent in
        `current_decision.json` are container paths (e.g. `/workspace/...`)
        so the agent never sees host-side filesystem locations.
        """
        decision_index = observation["decision_index"]
        legal_actions = observation.get("legal_actions", [])
        host_output_path = self.output_path(decision_index, attempt)

        _write_json(self.observation_path(decision_index), observation)
        _write_json(self.current_observation_path, observation)
        _write_json(self.legal_actions_path, legal_actions)
        _write_json(
            self.current_decision_path,
            {
                "decision_index": decision_index,
                "attempt": attempt,
                "seat_color": self.color,
                "output_path": self.container_path(host_output_path),
            },
        )
        return host_output_path

    def read_attempt_output(self, decision_index: int, attempt: int) -> dict:
        """Read and parse the agent's output file for a given decision/attempt."""
        path = self.output_path(decision_index, attempt)
        return json.loads(path.read_text(encoding="utf-8"))


def create_seat_workspace(
    root: Path,
    color: str,
    agents_md: str | None = None,
    pi_extension_path: Path | None = None,
    container_root: str = "/workspace",
) -> SeatWorkspace:
    """Create a fresh workspace for one seat in one game.

    Fails if `root` already exists, to make the per-game lifetime explicit.
    `container_root` is the path the workspace is bind-mounted to inside the
    agent's container; it is used when writing agent-facing path references.
    """
    root.mkdir(parents=True, exist_ok=False)
    ws = SeatWorkspace(color=color, root=root, container_root=container_root)
    ws.observations_dir.mkdir()
    ws.outputs_dir.mkdir()
    ws.pi_sessions_dir.mkdir(parents=True)
    ws.pi_extensions_dir.mkdir(parents=True)
    ws.agents_md_path.write_text(agents_md or DEFAULT_AGENTS_MD, encoding="utf-8")
    if pi_extension_path is not None:
        shutil.copy2(pi_extension_path, ws.pi_extensions_dir / pi_extension_path.name)
    return ws


def destroy_seat_workspace(
    workspace: SeatWorkspace,
    archive_to: Path | None = None,
) -> None:
    """Tear down a workspace after the game. Optionally archive it first."""
    if not workspace.root.exists():
        return
    if archive_to is not None:
        archive_to.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(workspace.root), str(archive_to))
        return
    shutil.rmtree(workspace.root)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
