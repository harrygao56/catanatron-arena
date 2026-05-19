"""Load named DockerPiAgent configs from a TOML file.

Expected file shape::

    [agents.<name>]
    provider = "anthropic"            # required
    model = "claude-opus-4-5"         # required
    image = "my-arena-agent:latest"   # optional
    move_timeout_seconds = 60         # optional
    max_invalid_retries = 3           # optional
    cpus = 4.0                        # optional (omit for no limit; explicit number to override)
    memory_mb = 4096                  # optional (same)
    network = "none"                  # optional
    env_passthrough = ["ANTHROPIC_API_KEY"]  # optional

Omitted keys take the defaults from `DockerPiAgentConfig`. Reference a
named entry on the CLI with `pi:<name>` (e.g. `pi:claude-opus`).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from catanatron_arena.agents.docker_pi import DockerPiAgentConfig


_REQUIRED_KEYS = {"provider", "model"}
_OPTIONAL_KEYS = {
    "image",
    "move_timeout_seconds",
    "max_invalid_retries",
    "cpus",
    "memory_mb",
    "network",
    "env_passthrough",
}
_ALLOWED_KEYS = _REQUIRED_KEYS | _OPTIONAL_KEYS


def load_pi_agents_config(path: Path) -> dict[str, DockerPiAgentConfig]:
    """Return a `{name: DockerPiAgentConfig}` map parsed from `path`.

    Raises `ValueError` on missing required keys, unknown keys, or wrong types.
    Raises `FileNotFoundError` if `path` doesn't exist.
    """
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    agents = raw.get("agents", {})
    if not isinstance(agents, dict):
        raise ValueError(f"{path}: [agents] must be a table of named entries")
    return {name: _build_config(path, name, body) for name, body in agents.items()}


def _build_config(path: Path, name: str, body: object) -> DockerPiAgentConfig:
    if not isinstance(body, dict):
        raise ValueError(f"{path}: [agents.{name}] must be a table")

    missing = _REQUIRED_KEYS - body.keys()
    if missing:
        raise ValueError(
            f"{path}: agents.{name} missing required key(s): {sorted(missing)}"
        )
    unknown = body.keys() - _ALLOWED_KEYS
    if unknown:
        raise ValueError(
            f"{path}: agents.{name} has unknown key(s): {sorted(unknown)}; "
            f"allowed: {sorted(_ALLOWED_KEYS)}"
        )

    # Only forward keys that were actually present, so DockerPiAgentConfig's
    # field defaults remain the single source of truth for omitted options.
    kwargs: dict[str, Any] = {
        "provider": _str(path, name, "provider", body["provider"]),
        "model": _str(path, name, "model", body["model"]),
        "name": f"pi:{name}",
    }
    if "image" in body:
        kwargs["image"] = _str(path, name, "image", body["image"])
    if "move_timeout_seconds" in body:
        kwargs["move_timeout_seconds"] = _float(
            path, name, "move_timeout_seconds", body["move_timeout_seconds"]
        )
    if "max_invalid_retries" in body:
        kwargs["max_invalid_retries"] = _int(
            path, name, "max_invalid_retries", body["max_invalid_retries"]
        )
    if "cpus" in body:
        kwargs["cpus"] = _optional_float(path, name, "cpus", body["cpus"])
    if "memory_mb" in body:
        kwargs["memory_mb"] = _optional_int(path, name, "memory_mb", body["memory_mb"])
    if "network" in body:
        kwargs["network"] = _optional_str(path, name, "network", body["network"])
    if "env_passthrough" in body:
        kwargs["env_passthrough"] = _str_tuple(
            path, name, "env_passthrough", body["env_passthrough"]
        )
    return DockerPiAgentConfig(**kwargs)


def _str(path: Path, name: str, key: str, value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path}: agents.{name}.{key} must be a string, got {type(value).__name__}")
    return value


def _optional_str(path: Path, name: str, key: str, value: object) -> str | None:
    return None if value is None else _str(path, name, key, value)


def _int(path: Path, name: str, key: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path}: agents.{name}.{key} must be an integer, got {type(value).__name__}")
    return value


def _optional_int(path: Path, name: str, key: str, value: object) -> int | None:
    return None if value is None else _int(path, name, key, value)


def _float(path: Path, name: str, key: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}: agents.{name}.{key} must be a number, got {type(value).__name__}")
    return float(value)


def _optional_float(path: Path, name: str, key: str, value: object) -> float | None:
    return None if value is None else _float(path, name, key, value)


def _str_tuple(path: Path, name: str, key: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{path}: agents.{name}.{key} must be a list of strings")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(
                f"{path}: agents.{name}.{key}[{index}] must be a string, got {type(item).__name__}"
            )
        items.append(item)
    return tuple(items)
