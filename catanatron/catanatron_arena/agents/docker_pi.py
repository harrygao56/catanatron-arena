"""Docker + Pi agent: one container per seat per game.

Wires together the runtime pieces (`SeatWorkspace`, `DockerRuntime`,
`PiRpcClient`, `PiEventReader`, `await_decision_output`) into an
`AgentRuntime`-compatible agent. The match runner calls `start()` before
the game and `stop()` after; per-decision behavior happens in
`choose_action(observation, attempt)`.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from catanatron_arena.protocol.actions import InvalidActionSelection, SelectedAction
from catanatron_arena.runtime import (
    AttemptArtifacts,
    DEFAULT_PI_EXTENSION_PATH,
    ContainerSpec,
    DockerRuntime,
    EnvVar,
    PiEventReader,
    PiRpcClient,
    RuntimeArtifacts,
    SeatWorkspace,
    await_decision_output,
    copy_if_exists,
    create_seat_workspace,
    destroy_seat_workspace,
    write_json,
    workspace_mount,
)


DEFAULT_ENV_PASSTHROUGH = (
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
)
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
        self._artifacts: RuntimeArtifacts | None = None
        self._stderr_log: TextIO | None = None

    def start(self, *, game_id: str, color: str, workspace_root: Path) -> None:
        if self._workspace is not None:
            raise RuntimeError(f"{self.name} already started")
        self._color = color
        self._artifacts = RuntimeArtifacts(workspace_root, color)
        self._artifacts.prepare()
        self._workspace = create_seat_workspace(
            workspace_root / "workspaces" / color,
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
        self._stderr_log = self._artifacts.stderr_path.open("w", encoding="utf-8")
        pi_proc = self._container.exec(
            self._pi_argv(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_log,
            text=True,
            encoding="utf-8",
        )
        self._pi = PiRpcClient(pi_proc)
        self._reader = PiEventReader(self._pi, self._artifacts.session_events_path)

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
            ("stderr_log", lambda: self._stderr_log.close() if self._stderr_log else None),
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
        self._artifacts = None
        self._stderr_log = None

    def __enter__(self) -> "DockerPiAgent":
        raise RuntimeError(
            "Use start(game_id, color, workspace_root) explicitly; the match runner manages lifecycle."
        )

    def __exit__(self, *exc_info) -> None:
        self.stop()

    def choose_action(self, observation: dict, attempt: int = 1) -> SelectedAction:
        if (
            self._workspace is None
            or self._pi is None
            or self._reader is None
            or self._artifacts is None
        ):
            raise RuntimeError(f"{self.name} not started")

        decision_index = int(observation["decision_index"])
        output_path = self._workspace.write_decision_files(observation, attempt=attempt)

        prompt_id = f"decision-{decision_index:06d}-attempt-{attempt:03d}"
        prompt = self._build_prompt(observation, attempt)
        attempt_artifacts = self._artifacts.attempt(decision_index, attempt)
        _write_attempt_inputs(
            attempt_artifacts,
            prompt=prompt,
            observation=observation,
            workspace_root=self._workspace.root,
        )
        self._pi.send_prompt(prompt, request_id=prompt_id)

        outcome = await_decision_output(
            output_path,
            pull_event=_recording_pull(self._reader.pull, attempt_artifacts.events_path),
            timeout=self.config.move_timeout_seconds,
        )
        write_json(
            attempt_artifacts.outcome_path,
            {
                "status": outcome.status,
                "elapsed_seconds": outcome.elapsed_seconds,
                "error": outcome.error,
            },
        )

        if outcome.status == "ok" and outcome.output is not None:
            copy_if_exists(output_path, attempt_artifacts.output_copy_path)
            _drain_terminal_events(self._reader.pull, attempt_artifacts.events_path)
            action_id = outcome.output.get("action_id")
            if not isinstance(action_id, int):
                write_json(
                    attempt_artifacts.error_path,
                    {
                        "error": f"choose_action output had non-integer action_id: {action_id!r}",
                        "output": outcome.output,
                    },
                )
                raise InvalidActionSelection(
                    f"choose_action output had non-integer action_id: {action_id!r}",
                    runtime_refs=attempt_artifacts.refs(self._artifacts.game_dir),
                )
            return SelectedAction(
                action_id=action_id,
                rationale=str(outcome.output.get("rationale") or ""),
                runtime_refs=attempt_artifacts.refs(self._artifacts.game_dir),
            )

        # Non-ok outcome: surface as InvalidActionSelection so the match loop
        # treats it like an invalid choice (retry up to N, then fail the game
        # with a readable reason in the replay).
        try:
            self._pi.send_abort()
        except Exception:
            pass
        write_json(
            attempt_artifacts.error_path,
            {
                "status": outcome.status,
                "error": outcome.error or outcome.status,
                "events": list(outcome.events),
            },
        )
        raise InvalidActionSelection(
            f"{self.name} {outcome.status} after {outcome.elapsed_seconds:.1f}s: "
            f"{outcome.error or outcome.status}",
            runtime_refs=attempt_artifacts.refs(self._artifacts.game_dir),
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


def _write_attempt_inputs(
    artifacts: AttemptArtifacts,
    *,
    prompt: str,
    observation: dict,
    workspace_root: Path,
) -> None:
    artifacts.prompt_path.write_text(prompt, encoding="utf-8")
    write_json(artifacts.observation_path, observation)
    copy_if_exists(workspace_root / "legal_actions.json", artifacts.legal_actions_path)
    copy_if_exists(workspace_root / "decision_meta.json", artifacts.decision_meta_path)


def _recording_pull(pull, events_path: Path):
    def wrapped(timeout: float):
        item = pull(timeout)
        if isinstance(item, dict):
            from catanatron_arena.runtime import append_jsonl

            append_jsonl(events_path, item)
        return item

    return wrapped


def _drain_terminal_events(pull, events_path: Path, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        item = pull(0.05)
        if not isinstance(item, dict):
            continue
        from catanatron_arena.runtime import append_jsonl

        append_jsonl(events_path, item)
        if item.get("type") == "agent_end":
            return
