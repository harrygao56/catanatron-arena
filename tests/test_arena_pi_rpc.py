import io
import json
import subprocess

import pytest

from catanatron_arena.runtime import PiRpcClient


class FakeStdin:
    def __init__(self):
        self.written: list[str] = []
        self.closed = False

    def write(self, s: str) -> int:
        self.written.append(s)
        return len(s)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    """Just enough of subprocess.Popen for PiRpcClient to drive."""

    def __init__(self, stdout_lines: list[str], *, returncode: int = 0):
        self.stdin = FakeStdin()
        self.stdout = io.StringIO("".join(stdout_lines))
        self.returncode = returncode
        self.wait_calls: list[float | None] = []
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls.append(timeout)
        return self.returncode

    def kill(self) -> None:
        self.killed = True


def test_construct_rejects_non_piped_process():
    proc = FakeProcess([])
    proc.stdin = None  # type: ignore[assignment]
    with pytest.raises(ValueError, match="stdin=PIPE"):
        PiRpcClient(proc)  # type: ignore[arg-type]


def test_send_writes_jsonl_line_and_flushes():
    proc = FakeProcess([])
    client = PiRpcClient(proc)

    client.send({"type": "prompt", "message": "hi"})

    assert len(proc.stdin.written) == 1
    raw = proc.stdin.written[0]
    assert raw.endswith("\n")
    assert json.loads(raw) == {"type": "prompt", "message": "hi"}


def test_send_prompt_includes_request_id_when_given():
    proc = FakeProcess([])
    client = PiRpcClient(proc)

    client.send_prompt("decide", request_id="decision-007-attempt-001")

    payload = json.loads(proc.stdin.written[0])
    assert payload == {
        "type": "prompt",
        "message": "decide",
        "id": "decision-007-attempt-001",
    }


def test_send_prompt_omits_request_id_when_absent():
    proc = FakeProcess([])
    client = PiRpcClient(proc)

    client.send_prompt("decide")

    payload = json.loads(proc.stdin.written[0])
    assert "id" not in payload


def test_send_abort_writes_abort_command():
    proc = FakeProcess([])
    client = PiRpcClient(proc)

    client.send_abort()

    assert json.loads(proc.stdin.written[0]) == {"type": "abort"}


def test_iter_events_parses_jsonl_and_skips_blank_lines():
    lines = [
        '{"type": "agent_start"}\n',
        "\n",
        '{"type": "message_update", "delta": "hi"}\n',
        '{"type": "agent_end"}\n',
    ]
    proc = FakeProcess(lines)
    client = PiRpcClient(proc)

    events = list(client.iter_events())

    assert events == [
        {"type": "agent_start"},
        {"type": "message_update", "delta": "hi"},
        {"type": "agent_end"},
    ]


def test_iter_events_handles_crlf_line_endings():
    proc = FakeProcess(['{"type":"agent_start"}\r\n', '{"type":"agent_end"}\r\n'])
    client = PiRpcClient(proc)

    events = list(client.iter_events())

    assert [e["type"] for e in events] == ["agent_start", "agent_end"]


def test_iter_events_raises_on_malformed_line():
    proc = FakeProcess(['{"type":"ok"}\n', "not json\n"])
    client = PiRpcClient(proc)
    gen = client.iter_events()

    assert next(gen) == {"type": "ok"}
    with pytest.raises(json.JSONDecodeError):
        next(gen)


def test_close_closes_stdin_and_waits():
    proc = FakeProcess([])
    client = PiRpcClient(proc)

    rc = client.close(timeout=2.0)

    assert proc.stdin.closed
    assert proc.wait_calls == [2.0]
    assert rc == 0


def test_close_kills_process_when_wait_times_out():
    class TimingOutProcess(FakeProcess):
        def __init__(self):
            super().__init__([])
            self._calls = 0

        def wait(self, timeout: float | None = None) -> int:
            self._calls += 1
            if self._calls == 1:
                raise subprocess.TimeoutExpired(cmd="pi", timeout=timeout or 0.0)
            return -9

    proc = TimingOutProcess()
    client = PiRpcClient(proc)

    rc = client.close(timeout=0.1)

    assert proc.killed
    assert rc == -9


def test_context_manager_closes_on_exit():
    proc = FakeProcess([])
    with PiRpcClient(proc) as client:
        client.send_prompt("hi")

    assert proc.stdin.closed
    assert proc.wait_calls  # close() called
