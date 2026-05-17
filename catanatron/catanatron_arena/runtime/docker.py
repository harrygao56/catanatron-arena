"""Lifecycle for one Docker container per seat per game."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from catanatron_arena.runtime.workspace import SeatWorkspace


@dataclass(frozen=True)
class BindMount:
    host: Path
    container: str
    readonly: bool = False


@dataclass(frozen=True)
class EnvVar:
    """A container env var. `value=None` passes through from the host env
    (Docker's `--env NAME` form); use `value=""` for an explicit empty string.
    """

    name: str
    value: str | None = None


@dataclass(frozen=True)
class ContainerSpec:
    image: str
    name: str
    workdir: str = "/workspace"
    bind_mounts: tuple[BindMount, ...] = ()
    env: tuple[EnvVar, ...] = ()
    cpus: float | None = None
    memory_mb: int | None = None
    network: str | None = None


def workspace_mount(workspace: SeatWorkspace, readonly: bool = False) -> BindMount:
    return BindMount(host=workspace.root, container=workspace.container_root, readonly=readonly)


def build_run_argv(spec: ContainerSpec, docker_bin: str = "docker") -> list[str]:
    argv: list[str] = [
        docker_bin,
        "run",
        "--rm",
        "--detach",
        "--name",
        spec.name,
        "--workdir",
        spec.workdir,
    ]
    for mount in spec.bind_mounts:
        parts = ["type=bind", f"src={mount.host}", f"dst={mount.container}"]
        if mount.readonly:
            parts.append("readonly")
        argv.extend(["--mount", ",".join(parts)])
    for var in spec.env:
        argv.extend(["--env", var.name if var.value is None else f"{var.name}={var.value}"])
    if spec.cpus is not None:
        argv.extend(["--cpus", str(spec.cpus)])
    if spec.memory_mb is not None:
        argv.extend(["--memory", f"{spec.memory_mb}m"])
    if spec.network is not None:
        argv.extend(["--network", spec.network])
    argv.extend([spec.image, "sleep", "infinity"])
    return argv


def build_exec_argv(
    container_name: str,
    cmd: Sequence[str],
    workdir: str | None = None,
    interactive: bool = True,
    docker_bin: str = "docker",
) -> list[str]:
    argv: list[str] = [docker_bin, "exec"]
    if interactive:
        argv.append("-i")
    if workdir is not None:
        argv.extend(["--workdir", workdir])
    argv.append(container_name)
    argv.extend(cmd)
    return argv


class DockerRuntime:
    """One container per seat per game. `start()` runs detached, `exec()` opens
    a Pi (or other) subprocess inside it, `stop()` removes the container.
    """

    def __init__(self, spec: ContainerSpec, *, docker_bin: str = "docker"):
        self.spec = spec
        self.docker_bin = docker_bin
        self._started = False

    def start(self) -> None:
        if self._started:
            raise RuntimeError(f"container {self.spec.name!r} already started")
        subprocess.run(build_run_argv(self.spec, self.docker_bin), check=True)
        self._started = True

    def exec(self, cmd: Sequence[str], **popen_kwargs) -> subprocess.Popen:
        if not self._started:
            raise RuntimeError(f"container {self.spec.name!r} not started")
        argv = build_exec_argv(
            self.spec.name,
            cmd,
            workdir=self.spec.workdir,
            docker_bin=self.docker_bin,
        )
        return subprocess.Popen(argv, **popen_kwargs)

    def stop(self) -> None:
        if not self._started:
            return
        subprocess.run(
            [self.docker_bin, "rm", "-f", self.spec.name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._started = False

    def __enter__(self) -> "DockerRuntime":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()
