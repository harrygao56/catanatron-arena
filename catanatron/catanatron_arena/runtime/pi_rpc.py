"""JSONL RPC client for a Pi `--mode rpc` subprocess.

Pi RPC speaks newline-delimited JSON over stdin (commands) and stdout (events
+ command responses). See docs/extensions or the upstream RPC mode reference
for the full event schema. This wrapper is intentionally thin: send commands,
iterate events. Timeout handling and output-file polling live one layer up.
"""

from __future__ import annotations

import json
import subprocess
from typing import Iterator


class PiRpcClient:
    """Wraps a Pi `--mode rpc` subprocess (or `docker exec`'d equivalent).

    The process must be started with `text=True`, `stdin=PIPE`, `stdout=PIPE`,
    and `encoding="utf-8"` so we can write and iterate UTF-8 JSONL.
    """

    def __init__(self, process: subprocess.Popen):
        if process.stdin is None or process.stdout is None:
            raise ValueError("Pi process must be started with stdin=PIPE and stdout=PIPE")
        self.process = process
        self._stdin = process.stdin
        self._stdout = process.stdout

    def send(self, command: dict) -> None:
        line = json.dumps(command, separators=(",", ":")) + "\n"
        self._stdin.write(line)
        self._stdin.flush()

    def send_prompt(self, message: str, request_id: str | None = None) -> None:
        cmd: dict = {"type": "prompt", "message": message}
        if request_id is not None:
            cmd["id"] = request_id
        self.send(cmd)

    def send_abort(self) -> None:
        self.send({"type": "abort"})

    def iter_events(self) -> Iterator[dict]:
        """Blocking generator over JSON events from Pi's stdout.

        Yields parsed dicts. Skips blank lines. Stops when the pipe closes.
        Lines that fail to parse raise `json.JSONDecodeError`; callers decide
        whether to treat a malformed line as fatal.
        """
        for line in self._stdout:
            line = line.rstrip("\r\n")
            if not line:
                continue
            yield json.loads(line)

    def close(self, timeout: float = 5.0) -> int:
        try:
            self._stdin.close()
        except Exception:
            pass
        try:
            return self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            return self.process.wait()

    def __enter__(self) -> "PiRpcClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
