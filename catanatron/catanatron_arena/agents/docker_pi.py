"""Docker + Pi agent: one container per seat per game.

Wires together the runtime pieces (`SeatWorkspace`, `DockerRuntime`,
`PiRpcClient`, `PiEventReader`, `await_decision_output`) into an
`AgentRuntime`-compatible agent. The match runner calls `start()` before
the game and `stop()` after; per-decision behavior happens in
`choose_action(observation, attempt)`.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from catanatron_arena.protocol.actions import InvalidActionSelection, SelectedAction
from catanatron_arena.runtime import (
    DEFAULT_PI_EXTENSION_PATH,
    ContainerSpec,
    DockerRuntime,
    EnvVar,
    PiEventReader,
    PiRpcClient,
    SeatWorkspace,
    await_decision_output,
    create_seat_workspace,
    destroy_seat_workspace,
    workspace_mount,
)


DEFAULT_ENV_PASSTHROUGH = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")
DEFAULT_IMAGE = "catanatron-arena-agent:latest"


@dataclass(frozen=True)
class DockerPiAgentConfig:
    provider: str
    model: str
    image: str = DEFAULT_IMAGE
    move_timeout_seconds: float = 30.0
    max_invalid_retries: int = 2
    cpus: float | None = 2.0
    memory_mb: int | None = 2048
    network: str | None = None
    env_passthrough: tuple[str, ...] = DEFAULT_ENV_PASSTHROUGH
    name: str | None = None


def _agent_name(config: DockerPiAgentConfig) -> str:
    return config.name or f"pi:{config.provider}/{config.model}"


class DockerPiAgent:
    """One-game agent owning a container, a Pi RPC session, and a workspace."""

    def __init__(self, config: DockerPiAgentConfig):
        self.config = config
        self.name = _agent_name(config)
        self.max_invalid_retries = config.max_invalid_retries
        self._workspace: SeatWorkspace | None = None
        self._container: DockerRuntime | None = None
        self._pi: PiRpcClient | None = None
        self._reader: PiEventReader | None = None
        self._color: str | None = None

    def start(self, *, game_id: str, color: str, workspace_root: Path) -> None:
        if self._workspace is not None:
            raise RuntimeError(f"{self.name} already started")
        self._color = color
        self._workspace = create_seat_workspace(
            workspace_root / color,
            color=color,
            pi_extension_path=DEFAULT_PI_EXTENSION_PATH,
        )
        spec = ContainerSpec(
            image=self.config.image,
            name=f"catanatron-arena-{game_id}-{color}",
            workdir=self._workspace.container_root,
            bind_mounts=(workspace_mount(self._workspace),),
            env=tuple(EnvVar(name=k) for k in self.config.env_passthrough),
            cpus=self.config.cpus,
            memory_mb=self.config.memory_mb,
            network=self.config.network,
        )
        self._container = DockerRuntime(spec)
        self._container.start()
        pi_proc = self._container.exec(
            self._pi_argv(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self._pi = PiRpcClient(pi_proc)
        self._reader = PiEventReader(self._pi)

    def _pi_argv(self) -> list[str]:
        ws_root = self._workspace.container_root if self._workspace else "/workspace"
        return [
            "pi",
            "--mode",
            "rpc",
            "--provider",
            self.config.provider,
            "--model",
            self.config.model,
            "--session-dir",
            f"{ws_root}/.pi/sessions",
            "--extension",
            f"{ws_root}/.pi/extensions/catanatron-arena.ts",
        ]

    def stop(self) -> None:
        # Best-effort cleanup: each step swallows its own errors so a failure
        # in one teardown doesn't strand the others.
        for closer in (
            ("pi", lambda: self._pi.close() if self._pi else None),
            ("reader", lambda: self._reader.join() if self._reader else None),
            ("container", lambda: self._container.stop() if self._container else None),
            (
                "workspace",
                lambda: destroy_seat_workspace(self._workspace) if self._workspace else None,
            ),
        ):
            try:
                closer[1]()
            except Exception:
                pass
        self._pi = None
        self._reader = None
        self._container = None
        self._workspace = None

    def __enter__(self) -> "DockerPiAgent":
        raise RuntimeError(
            "Use start(game_id, color, workspace_root) explicitly; the match runner manages lifecycle."
        )

    def __exit__(self, *exc_info) -> None:
        self.stop()

    def choose_action(self, observation: dict, attempt: int = 1) -> SelectedAction:
        if self._workspace is None or self._pi is None or self._reader is None:
            raise RuntimeError(f"{self.name} not started")

        decision_index = int(observation["decision_index"])
        output_path = self._workspace.write_decision_files(observation, attempt=attempt)

        prompt_id = f"decision-{decision_index:06d}-attempt-{attempt:03d}"
        prompt = self._build_prompt(observation, attempt)
        self._pi.send_prompt(prompt, request_id=prompt_id)

        outcome = await_decision_output(
            output_path,
            pull_event=self._reader.pull,
            timeout=self.config.move_timeout_seconds,
        )

        if outcome.status == "ok" and outcome.output is not None:
            action_id = outcome.output.get("action_id")
            if not isinstance(action_id, int):
                raise InvalidActionSelection(
                    f"choose_action output had non-integer action_id: {action_id!r}"
                )
            return SelectedAction(
                action_id=action_id,
                rationale=str(outcome.output.get("rationale") or ""),
            )

        # Non-ok outcome: surface as InvalidActionSelection so the match loop
        # treats it like an invalid choice (retry up to N, then fail the game
        # with a readable reason in the replay).
        try:
            self._pi.send_abort()
        except Exception:
            pass
        raise InvalidActionSelection(
            f"{self.name} {outcome.status} after {outcome.elapsed_seconds:.1f}s: "
            f"{outcome.error or outcome.status}"
        )

    def _build_prompt(self, observation: dict, attempt: int) -> str:
        decision_index = observation.get("decision_index", "?")
        n_legal = len(observation.get("legal_actions", []))
        color = self._color or observation.get("seat_color", "?")
        if attempt == 1:
            return (
                f"Decision {decision_index}. You are {color}. "
                f"Read current_observation.json and legal_actions.json in this workspace, "
                f"then call choose_action with one of the {n_legal} legal action_ids."
            )
        return (
            f"Decision {decision_index} retry {attempt}. Your previous choose_action "
            f"selected an invalid action_id. Re-read legal_actions.json and call "
            f"choose_action again with a valid action_id."
        )


def build_pi_agent(spec: str) -> DockerPiAgent:
    """Build a DockerPiAgent from a CLI spec of the form `pi:<provider>/<model>`."""
    if not spec.startswith("pi:"):
        raise ValueError(f"not a pi agent spec: {spec!r}")
    rest = spec[len("pi:") :]
    if "/" not in rest:
        raise ValueError(f"pi agent spec must be pi:<provider>/<model>, got {spec!r}")
    provider, model = rest.split("/", 1)
    if not provider or not model:
        raise ValueError(f"pi agent spec must be pi:<provider>/<model>, got {spec!r}")
    return DockerPiAgent(DockerPiAgentConfig(provider=provider, model=model))
