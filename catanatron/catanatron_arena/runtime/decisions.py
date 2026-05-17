"""Wait for an agent's per-decision output file, or for Pi to give up first.

Used between sending a Pi prompt and reading the agent's `{action_id,
rationale}` reply from disk. The orchestration is split from the threading
so the logic can be tested without real threads.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Literal

from catanatron_arena.runtime.pi_rpc import PiRpcClient


class _PipeClosedSentinel:
    def __repr__(self) -> str:
        return "PIPE_CLOSED"


PIPE_CLOSED = _PipeClosedSentinel()


PullEvent = Callable[[float], "dict | None | _PipeClosedSentinel"]


DecisionStatus = Literal[
    "ok",
    "timeout",
    "agent_ended_without_output",
    "pipe_closed",
]


@dataclass(frozen=True)
class DecisionOutcome:
    status: DecisionStatus
    output: dict | None
    events: tuple[dict, ...]
    elapsed_seconds: float
    error: str | None = None


def _try_read_output(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        # Missing file or partial write (Node fs.writeFile isn't atomic).
        return None


def await_decision_output(
    output_path: Path,
    *,
    pull_event: PullEvent,
    timeout: float,
    poll_interval: float = 0.05,
    clock: Callable[[], float] = time.monotonic,
) -> DecisionOutcome:
    """Block until the agent writes `output_path`, until Pi emits `agent_end`,
    until the pipe closes, or until `timeout` seconds elapse.

    `pull_event(wait)` returns one of:
      - a parsed event dict,
      - `None` if no event arrived within `wait` seconds (poll tick),
      - `PIPE_CLOSED` if the event source is exhausted.
    """
    start = clock()
    deadline = start + timeout
    events: list[dict] = []
    saw_agent_end = False

    while True:
        output = _try_read_output(output_path)
        if output is not None:
            return DecisionOutcome("ok", output, tuple(events), clock() - start)

        if saw_agent_end:
            return DecisionOutcome(
                "agent_ended_without_output",
                None,
                tuple(events),
                clock() - start,
                error="agent_end was emitted without writing the decision output file",
            )

        remaining = deadline - clock()
        if remaining <= 0:
            return DecisionOutcome(
                "timeout",
                None,
                tuple(events),
                clock() - start,
                error=f"no output after {timeout}s",
            )

        item = pull_event(min(poll_interval, remaining))

        if isinstance(item, _PipeClosedSentinel):
            # Last-shot file check: extension may have flushed just as Pi closed.
            output = _try_read_output(output_path)
            if output is not None:
                return DecisionOutcome("ok", output, tuple(events), clock() - start)
            return DecisionOutcome(
                "pipe_closed",
                None,
                tuple(events),
                clock() - start,
                error="Pi pipe closed before the decision output appeared",
            )

        if item is None:
            continue

        # item is dict by elimination.
        events.append(item)
        if item.get("type") == "agent_end":
            saw_agent_end = True


class PiEventReader:
    """Background thread that drains a Pi RPC client's events into a queue.

    One reader per Pi session: `pi.iter_events()` can have only one consumer.
    """

    def __init__(self, pi: PiRpcClient):
        self._pi = pi
        self._queue: Queue[dict | _PipeClosedSentinel] = Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name="pi-rpc-reader")
        self._thread.start()

    def _run(self) -> None:
        try:
            for ev in self._pi.iter_events():
                self._queue.put(ev)
        except Exception:
            pass
        finally:
            self._queue.put(PIPE_CLOSED)

    def pull(self, timeout: float) -> dict | None | _PipeClosedSentinel:
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def join(self, timeout: float = 5.0) -> None:
        self._thread.join(timeout=timeout)

    def __enter__(self) -> "PiEventReader":
        return self

    def __exit__(self, *exc_info) -> None:
        self.join()
