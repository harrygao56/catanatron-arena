"""Runtime helpers for sandboxed model-agent containers."""

from pathlib import Path

from catanatron_arena.runtime.decisions import (
    PIPE_CLOSED,
    DecisionOutcome,
    DecisionStatus,
    PiEventReader,
    await_decision_output,
)
from catanatron_arena.runtime.docker import (
    BindMount,
    ContainerSpec,
    DockerRuntime,
    EnvVar,
    build_exec_argv,
    build_run_argv,
    workspace_mount,
)
from catanatron_arena.runtime.pi_rpc import PiRpcClient
from catanatron_arena.runtime.workspace import (
    SeatWorkspace,
    create_seat_workspace,
    destroy_seat_workspace,
)

DEFAULT_PI_EXTENSION_PATH = Path(__file__).parent / "pi_extension" / "catanatron-arena.ts"

__all__ = [
    "DEFAULT_PI_EXTENSION_PATH",
    "PIPE_CLOSED",
    "BindMount",
    "ContainerSpec",
    "DecisionOutcome",
    "DecisionStatus",
    "DockerRuntime",
    "EnvVar",
    "PiEventReader",
    "PiRpcClient",
    "SeatWorkspace",
    "await_decision_output",
    "build_exec_argv",
    "build_run_argv",
    "create_seat_workspace",
    "destroy_seat_workspace",
    "workspace_mount",
]
