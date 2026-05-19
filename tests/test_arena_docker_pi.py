"""Unit tests for DockerPiAgent that mock Docker and Pi at module boundaries.

No Docker daemon or Pi binary required.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from catanatron_arena.agents import build_pi_agent
from catanatron_arena.agents.docker_pi import (
    DEFAULT_IMAGE,
    DockerPiAgent,
    DockerPiAgentConfig,
)
from catanatron_arena.protocol.actions import InvalidActionSelection


@dataclass
class FakeDockerRuntime:
    spec: object
    started: bool = False
    stopped: bool = False
    exec_calls: list = field(default_factory=list)

    def __init__(self, spec, **_kwargs):
        self.spec = spec
        self.started = False
        self.stopped = False
        self.exec_calls = []

    def start(self):
        self.started = True

    def exec(self, cmd, **popen_kwargs):
        self.exec_calls.append((tuple(cmd), popen_kwargs))
        return _FakePiProcess()

    def stop(self):
        self.stopped = True


class _FakePiProcess:
    """Minimal Popen-like object good enough for PiRpcClient(process)."""

    def __init__(self):
        self.stdin = _Stdin()
        # PiRpcClient iterates stdout; an empty StringIO closes immediately,
        # which would push PIPE_CLOSED onto the reader queue. We want a stream
        # that never yields, so block forever. Tests will short-circuit via
        # FakePiRpcClient / FakePiEventReader below.
        self.stdout = _BlockingStream()

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


class _Stdin:
    def __init__(self):
        self.written: list[str] = []
        self.closed = False

    def write(self, s):
        self.written.append(s)
        return len(s)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class _BlockingStream:
    def __iter__(self):
        # Yield nothing and stay open. PiEventReader's _run will sit in
        # `for line in stdout` until the test overrides reader.pull.
        return iter([])


@dataclass
class FakePiEventReader:
    """Stub PiEventReader exposing only `pull` and `join` used by the agent."""

    events_for_pull: list = field(default_factory=list)
    joined: bool = False

    def __init__(self, pi, events_path=None):
        self.pi = pi
        self.events_path = events_path
        self.events_for_pull = []
        self.joined = False

    def pull(self, timeout):
        if not self.events_for_pull:
            return None
        return self.events_for_pull.pop(0)

    def join(self, timeout=5.0):
        self.joined = True


@dataclass
class FakePiRpcClient:
    pi_process: object
    sent: list = field(default_factory=list)
    closed: bool = False
    aborted: bool = False

    def __init__(self, pi_process):
        self.pi_process = pi_process
        self.sent = []
        self.closed = False
        self.aborted = False

    def send_prompt(self, message, request_id=None):
        self.sent.append({"type": "prompt", "message": message, "id": request_id})

    def send_abort(self):
        self.aborted = True

    def close(self, timeout=5.0):
        self.closed = True
        return 0


@pytest.fixture
def patched_runtime(monkeypatch):
    """Swap DockerRuntime / PiRpcClient / PiEventReader inside docker_pi."""
    import catanatron_arena.agents.docker_pi as mod

    monkeypatch.setattr(mod, "DockerRuntime", FakeDockerRuntime)
    monkeypatch.setattr(mod, "PiRpcClient", FakePiRpcClient)
    monkeypatch.setattr(mod, "PiEventReader", FakePiEventReader)
    return mod


# --- Spec parsing ---


def test_build_pi_agent_parses_provider_and_model():
    agent = build_pi_agent("pi:anthropic/claude-opus-4-5")
    assert agent.config.provider == "anthropic"
    assert agent.config.model == "claude-opus-4-5"
    assert agent.name == "pi:anthropic/claude-opus-4-5"


def test_build_pi_agent_rejects_non_pi_spec():
    with pytest.raises(ValueError, match="not a pi agent spec"):
        build_pi_agent("random")


def test_build_pi_agent_requires_provider_and_model():
    with pytest.raises(ValueError, match="pi:<provider>/<model>"):
        build_pi_agent("pi:claude-opus-4-5")
    with pytest.raises(ValueError, match="pi:<provider>/<model>"):
        build_pi_agent("pi:anthropic/")


def test_cli_build_agent_prefers_named_config_over_inline():
    from catanatron_arena.cli import _build_agent
    from catanatron_arena.agents.docker_pi import DockerPiAgentConfig

    named = DockerPiAgentConfig(
        provider="anthropic", model="claude-opus-4-5", image="custom:1",
        name="pi:opus-fast",
    )
    agent = _build_agent("pi:opus-fast", seed=0, pi_configs={"opus-fast": named})

    assert agent.config.image == "custom:1"
    assert agent.name == "pi:opus-fast"


def test_cli_build_agent_falls_back_to_inline_when_name_unknown():
    from catanatron_arena.cli import _build_agent

    agent = _build_agent("pi:anthropic/claude-opus-4-5", seed=0, pi_configs={})
    assert agent.config.provider == "anthropic"
    assert agent.config.model == "claude-opus-4-5"


def test_cli_build_agent_dispatches_local_specs_unchanged():
    from catanatron_arena.cli import _build_agent

    agent = _build_agent("first_action", seed=0, pi_configs={})
    assert agent.name == "first_action"


# --- Lifecycle ---


def test_choose_action_before_start_raises():
    agent = DockerPiAgent(DockerPiAgentConfig(provider="anthropic", model="x"))
    with pytest.raises(RuntimeError, match="not started"):
        agent.choose_action({"decision_index": 0, "legal_actions": []})


def test_start_builds_workspace_container_and_pi(tmp_path, patched_runtime):
    agent = DockerPiAgent(DockerPiAgentConfig(provider="anthropic", model="claude"))

    agent.start(game_id="g123", color="RED", workspace_root=tmp_path)

    # Workspace was created on disk.
    assert (tmp_path / "workspaces" / "RED" / "AGENTS.md").is_file()
    assert (tmp_path / "workspaces" / "RED" / ".pi" / "extensions" / "catanatron-arena.ts").is_file()

    # Container spec carries name, image, mount, env passthrough.
    container = agent._container  # noqa: SLF001
    assert container is not None and container.started
    assert container.spec.name == "catanatron-arena-g123-RED"
    assert container.spec.image == DEFAULT_IMAGE
    assert container.spec.bind_mounts[0].host == tmp_path / "workspaces" / "RED"
    env_names = [e.name for e in container.spec.env]
    assert "ANTHROPIC_API_KEY" in env_names

    # Pi was exec'd with the expected argv.
    (argv, kw), = container.exec_calls
    assert argv[:3] == ("pi", "--mode", "rpc")
    assert "--provider" in argv and "anthropic" in argv
    assert "--model" in argv and "claude" in argv
    assert any("/.pi/extensions/catanatron-arena.ts" in a for a in argv)
    assert kw["text"] is True
    assert kw["stderr"].name.endswith("runtime/RED/pi.stderr.log")
    reader = agent._reader  # noqa: SLF001
    assert reader.events_path == tmp_path / "runtime" / "RED" / "events.jsonl"

    agent.stop()


def test_start_twice_raises(tmp_path, patched_runtime):
    agent = DockerPiAgent(DockerPiAgentConfig(provider="anthropic", model="claude"))
    agent.start(game_id="g123", color="RED", workspace_root=tmp_path)
    with pytest.raises(RuntimeError, match="already started"):
        agent.start(game_id="g456", color="RED", workspace_root=tmp_path)
    agent.stop()


def test_stop_cleans_up_workspace_container_and_pi(tmp_path, patched_runtime):
    agent = DockerPiAgent(DockerPiAgentConfig(provider="anthropic", model="claude"))
    agent.start(game_id="g123", color="RED", workspace_root=tmp_path)

    container = agent._container  # noqa: SLF001
    pi = agent._pi  # noqa: SLF001
    reader = agent._reader  # noqa: SLF001
    workspace_root = tmp_path / "workspaces" / "RED"
    assert workspace_root.exists()

    agent.stop()

    assert container.stopped
    assert pi.closed
    assert reader.joined
    assert not workspace_root.exists()  # destroyed
    assert agent._container is None and agent._pi is None  # noqa: SLF001


def test_stop_is_idempotent(tmp_path, patched_runtime):
    agent = DockerPiAgent(DockerPiAgentConfig(provider="anthropic", model="claude"))
    agent.start(game_id="g123", color="RED", workspace_root=tmp_path)
    agent.stop()
    agent.stop()  # no raise


# --- choose_action behavior ---


def test_choose_action_writes_decision_files_and_sends_prompt(tmp_path, patched_runtime):
    agent = DockerPiAgent(DockerPiAgentConfig(provider="anthropic", model="claude"))
    agent.start(game_id="g1", color="RED", workspace_root=tmp_path)

    # Pre-stage the output file so await_decision_output returns "ok" on first check.
    obs = {
        "decision_index": 5,
        "seat_color": "RED",
        "legal_actions": [{"id": 7}, {"id": 9}],
    }
    output_path = (
        tmp_path / "workspaces" / "RED" / "outputs" / "turn_000005_attempt_001.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"action_id": 7, "rationale": "build settlement"}),
        encoding="utf-8",
    )
    reader = agent._reader  # noqa: SLF001
    reader.events_for_pull.append({"type": "agent_end"})

    selected = agent.choose_action(obs, attempt=1)

    assert selected.action_id == 7
    assert selected.rationale == "build settlement"

    # Decision files were written.
    ws_root = tmp_path / "workspaces" / "RED"
    assert (ws_root / "decision_meta.json").is_file()
    assert (ws_root / "legal_actions.json").is_file()
    assert (ws_root / "current_observation.json").is_file()
    artifacts = (
        tmp_path
        / "runtime"
        / "RED"
        / "decisions"
        / "turn_000005_attempt_001"
    )
    assert (artifacts / "prompt.txt").is_file()
    assert (artifacts / "current_observation.json").is_file()
    assert (artifacts / "legal_actions.json").is_file()
    assert (artifacts / "choice.json").is_file()
    assert '"type": "agent_end"' in (artifacts / "agent_events.jsonl").read_text(
        encoding="utf-8"
    )
    assert selected.runtime_refs["prompt"] == (
        "runtime/RED/decisions/turn_000005_attempt_001/prompt.txt"
    )
    assert selected.runtime_refs["output"] == (
        "runtime/RED/decisions/turn_000005_attempt_001/choice.json"
    )

    # Prompt was sent with the right request id.
    pi = agent._pi  # noqa: SLF001
    assert pi.sent[0]["id"] == "decision-000005-attempt-001"
    assert "Decision 5" in pi.sent[0]["message"]

    agent.stop()


def test_choose_action_retry_prompt_differs_from_first(tmp_path, patched_runtime):
    agent = DockerPiAgent(DockerPiAgentConfig(provider="anthropic", model="claude"))
    agent.start(game_id="g1", color="RED", workspace_root=tmp_path)

    obs = {"decision_index": 0, "legal_actions": [{"id": 1}]}
    output = tmp_path / "workspaces" / "RED" / "outputs" / "turn_000000_attempt_002.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"action_id": 1, "rationale": ""}), encoding="utf-8")

    agent.choose_action(obs, attempt=2)

    pi = agent._pi  # noqa: SLF001
    assert pi.sent[0]["id"] == "decision-000000-attempt-002"
    assert "retry" in pi.sent[0]["message"].lower()

    agent.stop()


def test_choose_action_timeout_raises_invalid_action_selection(tmp_path, patched_runtime):
    agent = DockerPiAgent(
        DockerPiAgentConfig(
            provider="anthropic", model="claude", move_timeout_seconds=0.05
        )
    )
    agent.start(game_id="g1", color="RED", workspace_root=tmp_path)

    obs = {"decision_index": 0, "legal_actions": []}

    with pytest.raises(InvalidActionSelection, match="timeout"):
        agent.choose_action(obs, attempt=1)

    # Agent sent an abort to free Pi up for the next attempt.
    pi = agent._pi  # noqa: SLF001
    assert pi.aborted

    agent.stop()


def test_choose_action_non_int_action_id_raises_invalid(tmp_path, patched_runtime):
    agent = DockerPiAgent(DockerPiAgentConfig(provider="anthropic", model="claude"))
    agent.start(game_id="g1", color="RED", workspace_root=tmp_path)

    obs = {"decision_index": 0, "legal_actions": []}
    output = tmp_path / "workspaces" / "RED" / "outputs" / "turn_000000_attempt_001.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"action_id": "twelve"}), encoding="utf-8")

    with pytest.raises(InvalidActionSelection, match="non-integer") as exc_info:
        agent.choose_action(obs, attempt=1)
    assert exc_info.value.runtime_refs["error"] == (
        "runtime/RED/decisions/turn_000000_attempt_001/error.json"
    )

    agent.stop()


# --- Match runner integration (lifecycle hook) ---


def test_run_match_calls_start_and_stop_on_lifecycle_agents(tmp_path, monkeypatch):
    """Patched DockerPiAgent: confirm run_match invokes start/stop."""
    from catanatron_arena.agents.local import build_local_agent
    from catanatron_arena.runner.match import MatchConfig, run_match
    from catanatron_arena.protocol.actions import SelectedAction

    started: dict = {}
    stopped: list = []

    class FakeLifecycleAgent:
        name = "fake-pi"
        max_invalid_retries = 0

        def start(self, *, game_id, color, workspace_root):
            started[color] = (game_id, workspace_root)

        def stop(self):
            stopped.append(True)

        def choose_action(self, observation, attempt=1):
            # Always pick the first legal action so the game progresses.
            return SelectedAction(
                action_id=observation["legal_actions"][0]["id"],
                rationale="fake",
            )

    agents = [FakeLifecycleAgent()] + [build_local_agent("first_action") for _ in range(3)]

    result = run_match(
        agents,
        tmp_path,
        MatchConfig(seed=7, map_type="MINI", vps_to_win=3, max_decisions=50),
    )

    assert result.replay_path.exists()
    # start() called for the lifecycle-aware agent (RED seat) with a game-scoped workspace_root.
    assert "RED" in started
    game_id, workspace_root = started["RED"]
    assert workspace_root == (tmp_path / "games" / game_id).resolve()
    # stop() called once.
    assert stopped == [True]
