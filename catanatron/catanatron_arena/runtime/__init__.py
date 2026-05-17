"""Runtime helpers for sandboxed model-agent containers."""

from pathlib import Path

from catanatron_arena.runtime.workspace import (
    SeatWorkspace,
    create_seat_workspace,
    destroy_seat_workspace,
)

DEFAULT_PI_EXTENSION_PATH = Path(__file__).parent / "pi_extension" / "catanatron-arena.ts"

__all__ = [
    "DEFAULT_PI_EXTENSION_PATH",
    "SeatWorkspace",
    "create_seat_workspace",
    "destroy_seat_workspace",
]
