import subprocess
from pathlib import Path

import pytest

from catanatron_arena.runtime import (
    BindMount,
    ContainerSpec,
    DockerRuntime,
    EnvVar,
    build_exec_argv,
    build_run_argv,
    create_seat_workspace,
    workspace_mount,
)


def test_build_run_argv_minimal_spec():
    argv = build_run_argv(ContainerSpec(image="my/image:tag", name="c1"))

    assert argv == [
        "docker",
        "run",
        "--rm",
        "--detach",
        "--name",
        "c1",
        "--workdir",
        "/workspace",
        "my/image:tag",
        "sleep",
        "infinity",
    ]


def test_build_run_argv_includes_bind_mounts():
    spec = ContainerSpec(
        image="img",
        name="c1",
        bind_mounts=(
            BindMount(host=Path("/tmp/ws"), container="/workspace"),
            BindMount(host=Path("/tmp/cfg"), container="/etc/cfg", readonly=True),
        ),
    )

    argv = build_run_argv(spec)

    assert "--mount" in argv
    assert "type=bind,src=/tmp/ws,dst=/workspace" in argv
    assert "type=bind,src=/tmp/cfg,dst=/etc/cfg,readonly" in argv


def test_build_run_argv_env_passthrough_vs_explicit():
    spec = ContainerSpec(
        image="img",
        name="c1",
        env=(
            EnvVar(name="ANTHROPIC_API_KEY"),
            EnvVar(name="MODEL", value="claude-opus"),
        ),
    )

    argv = build_run_argv(spec)

    assert argv[argv.index("--env") :].count("--env") == 2
    assert "ANTHROPIC_API_KEY" in argv
    assert "MODEL=claude-opus" in argv


def test_build_run_argv_includes_resource_limits():
    spec = ContainerSpec(image="img", name="c1", cpus=2.0, memory_mb=2048, network="none")

    argv = build_run_argv(spec)

    assert "--cpus" in argv and "2.0" in argv
    assert "--memory" in argv and "2048m" in argv
    assert "--network" in argv and "none" in argv


def test_build_run_argv_honors_custom_docker_bin():
    argv = build_run_argv(ContainerSpec(image="img", name="c1"), docker_bin="/usr/local/bin/docker")
    assert argv[0] == "/usr/local/bin/docker"


def test_build_run_argv_image_and_sleep_are_last():
    spec = ContainerSpec(
        image="img",
        name="c1",
        env=(EnvVar(name="X", value="y"),),
        bind_mounts=(BindMount(host=Path("/tmp"), container="/workspace"),),
        cpus=1.0,
    )
    argv = build_run_argv(spec)

    assert argv[-3:] == ["img", "sleep", "infinity"]


def test_build_exec_argv_defaults():
    argv = build_exec_argv("c1", ["pi", "--mode", "rpc"])
    assert argv == ["docker", "exec", "-i", "c1", "pi", "--mode", "rpc"]


def test_build_exec_argv_with_workdir():
    argv = build_exec_argv("c1", ["pi"], workdir="/workspace")
    assert argv == ["docker", "exec", "-i", "--workdir", "/workspace", "c1", "pi"]


def test_build_exec_argv_non_interactive():
    argv = build_exec_argv("c1", ["ls"], interactive=False)
    assert argv == ["docker", "exec", "c1", "ls"]


def test_workspace_mount_derives_from_seat_workspace(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED", container_root="/mnt/agent")
    mount = workspace_mount(ws)

    assert mount == BindMount(host=ws.root, container="/mnt/agent", readonly=False)


# --- Lifecycle (subprocess mocked) ---


@pytest.fixture
def fake_subprocess(monkeypatch):
    """Replace subprocess.run/Popen with fakes that record their argv."""
    calls = {"run": [], "popen": []}

    class FakePopen:
        def __init__(self, argv, **kw):
            self.argv = argv
            self.kw = kw
            calls["popen"].append((argv, kw))

    def fake_run(argv, **kw):
        calls["run"].append((argv, kw))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    return calls


def test_runtime_start_runs_docker_run(fake_subprocess):
    rt = DockerRuntime(ContainerSpec(image="img", name="c1"))
    rt.start()

    assert len(fake_subprocess["run"]) == 1
    argv, kw = fake_subprocess["run"][0]
    assert argv[:2] == ["docker", "run"]
    assert "--name" in argv and "c1" in argv
    assert kw.get("check") is True


def test_runtime_start_twice_raises(fake_subprocess):
    rt = DockerRuntime(ContainerSpec(image="img", name="c1"))
    rt.start()

    with pytest.raises(RuntimeError, match="already started"):
        rt.start()


def test_runtime_exec_before_start_raises(fake_subprocess):
    rt = DockerRuntime(ContainerSpec(image="img", name="c1"))

    with pytest.raises(RuntimeError, match="not started"):
        rt.exec(["pi"])


def test_runtime_exec_uses_exec_argv_with_workdir(fake_subprocess):
    rt = DockerRuntime(ContainerSpec(image="img", name="c1", workdir="/workspace"))
    rt.start()
    rt.exec(["pi", "--mode", "rpc"], stdin=subprocess.PIPE)

    argv, kw = fake_subprocess["popen"][0]
    assert argv == ["docker", "exec", "-i", "--workdir", "/workspace", "c1", "pi", "--mode", "rpc"]
    assert kw["stdin"] is subprocess.PIPE


def test_runtime_stop_removes_container(fake_subprocess):
    rt = DockerRuntime(ContainerSpec(image="img", name="c1"))
    rt.start()
    rt.stop()

    assert fake_subprocess["run"][-1][0] == ["docker", "rm", "-f", "c1"]


def test_runtime_stop_without_start_is_noop(fake_subprocess):
    rt = DockerRuntime(ContainerSpec(image="img", name="c1"))
    rt.stop()

    assert fake_subprocess["run"] == []


def test_runtime_context_manager_stops_on_exit(fake_subprocess):
    with DockerRuntime(ContainerSpec(image="img", name="c1")) as rt:
        rt.exec(["pi"])

    assert fake_subprocess["run"][-1][0] == ["docker", "rm", "-f", "c1"]
