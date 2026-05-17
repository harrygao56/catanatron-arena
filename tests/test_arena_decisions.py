import io
import json

import pytest

from catanatron_arena.runtime import (
    PIPE_CLOSED,
    DecisionOutcome,
    PiEventReader,
    PiRpcClient,
    await_decision_output,
)


# --- Orchestration logic (pure; no real threads or sleeps) ---


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def make_puller(script):
    """Build a pull_event callable that walks through `script` items.

    Each item is one of:
      - ("event", dict): yields the dict on the next call
      - ("idle", n): yields None for n calls (poll timeouts)
      - ("close",): yields PIPE_CLOSED
      - ("file", path, payload): writes `payload` JSON to `path` before next call

    The puller also advances the clock by the requested wait each call.
    """
    queue = list(script)

    def pull(wait):
        if not queue:
            return None
        item = queue[0]
        if item[0] == "event":
            queue.pop(0)
            clock.t += wait
            return item[1]
        if item[0] == "idle":
            n = item[1] - 1
            if n <= 0:
                queue.pop(0)
            else:
                queue[0] = ("idle", n)
            clock.t += wait
            return None
        if item[0] == "close":
            queue.pop(0)
            clock.t += wait
            return PIPE_CLOSED
        if item[0] == "file":
            _, path, payload = queue.pop(0)
            path.write_text(json.dumps(payload), encoding="utf-8")
            clock.t += wait
            # Return None for this tick; the loop's top-of-iteration file
            # check will find the file before the next pull_event call.
            return None
        raise AssertionError(f"bad script item: {item}")

    clock = FakeClock()
    pull.clock = clock  # type: ignore[attr-defined]
    return pull


def test_returns_ok_when_output_already_exists(tmp_path):
    out = tmp_path / "out.json"
    out.write_text(json.dumps({"action_id": 5, "rationale": "hi"}), encoding="utf-8")
    pull = make_puller([])

    outcome = await_decision_output(
        out, pull_event=pull, timeout=1.0, clock=pull.clock
    )

    assert outcome.status == "ok"
    assert outcome.output == {"action_id": 5, "rationale": "hi"}
    assert outcome.events == ()


def test_returns_ok_when_output_appears_after_events(tmp_path):
    out = tmp_path / "out.json"
    pull = make_puller(
        [
            ("event", {"type": "agent_start"}),
            ("event", {"type": "tool_execution_start", "toolName": "choose_action"}),
            ("file", out, {"action_id": 12, "rationale": "build"}),
        ]
    )

    outcome = await_decision_output(
        out, pull_event=pull, timeout=1.0, poll_interval=0.01, clock=pull.clock
    )

    assert outcome.status == "ok"
    assert outcome.output == {"action_id": 12, "rationale": "build"}
    assert [e["type"] for e in outcome.events] == ["agent_start", "tool_execution_start"]


def test_returns_timeout_when_nothing_happens(tmp_path):
    out = tmp_path / "out.json"
    pull = make_puller([("idle", 1000)])

    outcome = await_decision_output(
        out, pull_event=pull, timeout=0.5, poll_interval=0.05, clock=pull.clock
    )

    assert outcome.status == "timeout"
    assert outcome.output is None
    assert "0.5" in (outcome.error or "")


def test_returns_agent_ended_without_output_when_agent_end_arrives_first(tmp_path):
    out = tmp_path / "out.json"
    pull = make_puller(
        [
            ("event", {"type": "agent_start"}),
            ("event", {"type": "agent_end"}),
        ]
    )

    outcome = await_decision_output(
        out, pull_event=pull, timeout=1.0, poll_interval=0.01, clock=pull.clock
    )

    assert outcome.status == "agent_ended_without_output"
    assert outcome.output is None


def test_agent_end_then_output_is_treated_as_ok(tmp_path):
    """If the output file flushes just before agent_end, the top-of-loop file
    check should catch it after agent_end is consumed."""
    out = tmp_path / "out.json"
    pull = make_puller(
        [
            ("file", out, {"action_id": 7, "rationale": "ok"}),
            ("event", {"type": "agent_end"}),
        ]
    )

    outcome = await_decision_output(
        out, pull_event=pull, timeout=1.0, poll_interval=0.01, clock=pull.clock
    )

    assert outcome.status == "ok"
    assert outcome.output == {"action_id": 7, "rationale": "ok"}


def test_pipe_closed_status_when_pipe_exhausts_first(tmp_path):
    out = tmp_path / "out.json"
    pull = make_puller([("close",)])

    outcome = await_decision_output(
        out, pull_event=pull, timeout=1.0, poll_interval=0.01, clock=pull.clock
    )

    assert outcome.status == "pipe_closed"
    assert outcome.output is None


def test_pipe_closes_after_output_written_is_ok(tmp_path):
    """File written before pipe close; the after-PIPE_CLOSED retry should pick it up."""
    out = tmp_path / "out.json"

    # Pre-stage the file so it's there at PIPE_CLOSED time.
    out.write_text(json.dumps({"action_id": 1, "rationale": "x"}), encoding="utf-8")
    pull = make_puller([("close",)])

    outcome = await_decision_output(
        out, pull_event=pull, timeout=1.0, poll_interval=0.01, clock=pull.clock
    )

    assert outcome.status == "ok"
    assert outcome.output == {"action_id": 1, "rationale": "x"}


def test_partial_json_is_treated_as_not_ready(tmp_path):
    out = tmp_path / "out.json"
    out.write_text('{"action_id": 5, "rationa', encoding="utf-8")  # half-written
    pull = make_puller([("idle", 1000)])

    outcome = await_decision_output(
        out, pull_event=pull, timeout=0.2, poll_interval=0.05, clock=pull.clock
    )

    assert outcome.status == "timeout"


def test_partial_json_then_complete_yields_ok(tmp_path):
    out = tmp_path / "out.json"
    out.write_text('{"action_id": 5, "rationa', encoding="utf-8")

    seen = {"n": 0}

    def pull(wait):
        seen["n"] += 1
        clock.t += wait
        if seen["n"] == 2:
            out.write_text(
                json.dumps({"action_id": 5, "rationale": "complete"}),
                encoding="utf-8",
            )
        return None

    clock = FakeClock()
    outcome = await_decision_output(
        out, pull_event=pull, timeout=1.0, poll_interval=0.01, clock=clock
    )

    assert outcome.status == "ok"
    assert outcome.output == {"action_id": 5, "rationale": "complete"}


# --- PiEventReader (uses real threads, but with a tiny in-memory Pi) ---


class _FakeProcStdin:
    def write(self, s): return len(s)
    def flush(self): pass
    def close(self): pass


class _FakeProcess:
    def __init__(self, lines):
        self.stdin = _FakeProcStdin()
        self.stdout = io.StringIO("".join(lines))
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def test_event_reader_yields_events_in_order():
    proc = _FakeProcess([
        '{"type":"agent_start"}\n',
        '{"type":"message_update","delta":"x"}\n',
        '{"type":"agent_end"}\n',
    ])
    pi = PiRpcClient(proc)

    with PiEventReader(pi) as reader:
        got = []
        while True:
            item = reader.pull(timeout=1.0)
            if item is PIPE_CLOSED:
                break
            assert item is not None
            got.append(item)

    assert [e["type"] for e in got] == ["agent_start", "message_update", "agent_end"]


def test_event_reader_pull_returns_none_on_quick_timeout():
    """No events available yet → pull returns None within `timeout`."""
    proc = _FakeProcess([])  # empty; reader closes immediately
    # Hold the pipe open so reader doesn't immediately yield PIPE_CLOSED.

    class StallingProc(_FakeProcess):
        def __init__(self):
            super().__init__([])
            # An iterator that blocks until told otherwise.
            import threading as _t
            self._event = _t.Event()

            class _Stall(io.StringIO):
                def __iter__(inner_self):
                    self._event.wait()
                    return iter([])

            self.stdout = _Stall("")

        def release(self):
            self._event.set()

    proc = StallingProc()
    pi = PiRpcClient(proc)
    reader = PiEventReader(pi)

    try:
        item = reader.pull(timeout=0.05)
        assert item is None
    finally:
        proc.release()
        reader.join(timeout=1.0)


def test_event_reader_terminates_with_pipe_closed_sentinel():
    proc = _FakeProcess(['{"type":"agent_end"}\n'])
    pi = PiRpcClient(proc)

    with PiEventReader(pi) as reader:
        first = reader.pull(timeout=1.0)
        second = reader.pull(timeout=1.0)

    assert first == {"type": "agent_end"}
    assert second is PIPE_CLOSED
