import json

import pytest

from catanatron_arena.runtime import (
    DEFAULT_PI_EXTENSION_PATH,
    SeatWorkspace,
    create_seat_workspace,
    destroy_seat_workspace,
)
from catanatron_arena.runtime.workspace import DEFAULT_AGENTS_MD


def test_create_seat_workspace_lays_out_expected_structure(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")

    assert isinstance(ws, SeatWorkspace)
    assert ws.color == "RED"
    assert ws.container_root == "/workspace"
    assert (ws.root / "observations").is_dir()
    assert (ws.root / "outputs").is_dir()
    assert (ws.root / ".pi" / "sessions").is_dir()
    assert (ws.root / ".pi" / "extensions").is_dir()
    assert (ws.root / "AGENTS.md").read_text(encoding="utf-8") == DEFAULT_AGENTS_MD
    # Per the plan: do not pre-create memory.md; the agent may create it.
    assert not (ws.root / "memory.md").exists()


def test_create_seat_workspace_writes_extensions_package_json(tmp_path):
    import json

    ws = create_seat_workspace(tmp_path / "RED", color="RED")
    package = json.loads(
        (ws.root / ".pi" / "extensions" / "package.json").read_text(encoding="utf-8")
    )

    assert package["name"] == "catanatron-arena-extensions"
    assert "typebox" in package["dependencies"]
    assert "@earendil-works/pi-coding-agent" in package["dependencies"]


def test_create_seat_workspace_accepts_custom_agents_md(tmp_path):
    ws = create_seat_workspace(
        tmp_path / "BLUE",
        color="BLUE",
        agents_md="custom instructions",
    )
    assert (ws.root / "AGENTS.md").read_text(encoding="utf-8") == "custom instructions"


def test_create_seat_workspace_copies_pi_extension(tmp_path):
    extension = tmp_path / "src" / "catanatron-arena.ts"
    extension.parent.mkdir()
    extension.write_text("export const tool = {};", encoding="utf-8")

    ws = create_seat_workspace(
        tmp_path / "ORANGE",
        color="ORANGE",
        pi_extension_path=extension,
    )

    copied = ws.root / ".pi" / "extensions" / "catanatron-arena.ts"
    assert copied.read_text(encoding="utf-8") == "export const tool = {};"


def test_create_seat_workspace_rejects_existing_root(tmp_path):
    target = tmp_path / "WHITE"
    target.mkdir()

    with pytest.raises(FileExistsError):
        create_seat_workspace(target, color="WHITE")


def test_write_decision_files_writes_all_four_files(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")
    observation = {
        "decision_index": 7,
        "seat_color": "RED",
        "legal_actions": [
            {"id": 12, "type": "BUILD_ROAD", "value": [3, 7], "label": "..."},
            {"id": 99, "type": "END_TURN", "value": None, "label": "End turn"},
        ],
        "features": {"P0_PUBLIC_VPS": 2},
    }

    host_output_path = ws.write_decision_files(observation, attempt=1)

    assert host_output_path == ws.root / "outputs" / "turn_000007_attempt_001.json"

    current = json.loads((ws.root / "current_observation.json").read_text(encoding="utf-8"))
    legal = json.loads((ws.root / "legal_actions.json").read_text(encoding="utf-8"))
    decision = json.loads((ws.root / "decision_meta.json").read_text(encoding="utf-8"))
    historical = json.loads(
        (ws.root / "observations" / "turn_000007.json").read_text(encoding="utf-8")
    )

    assert current == observation
    assert historical == observation
    assert legal == observation["legal_actions"]
    assert decision == {
        "decision_index": 7,
        "attempt": 1,
        "seat_color": "RED",
        "output_path": "/workspace/outputs/turn_000007_attempt_001.json",
    }


def test_write_decision_files_overwrites_current_files_across_turns(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")
    ws.write_decision_files({"decision_index": 0, "legal_actions": [{"id": 1}]}, attempt=1)
    ws.write_decision_files({"decision_index": 1, "legal_actions": [{"id": 2}]}, attempt=1)

    current = json.loads((ws.root / "current_observation.json").read_text(encoding="utf-8"))
    assert current["decision_index"] == 1
    # Per-turn history is preserved for both decisions.
    assert (ws.root / "observations" / "turn_000000.json").is_file()
    assert (ws.root / "observations" / "turn_000001.json").is_file()


def test_write_decision_files_honors_custom_container_root(tmp_path):
    ws = create_seat_workspace(
        tmp_path / "RED",
        color="RED",
        container_root="/mnt/agent",
    )
    ws.write_decision_files({"decision_index": 0, "legal_actions": []}, attempt=1)

    decision = json.loads((ws.root / "decision_meta.json").read_text(encoding="utf-8"))
    assert decision["output_path"] == "/mnt/agent/outputs/turn_000000_attempt_001.json"


def test_destroy_seat_workspace_removes_root(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")

    destroy_seat_workspace(ws)

    assert not ws.root.exists()


def test_destroy_seat_workspace_archives_when_requested(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")
    ws.write_decision_files({"decision_index": 0, "legal_actions": []}, attempt=1)
    archive = tmp_path / "archived" / "game-abc" / "RED"

    destroy_seat_workspace(ws, archive_to=archive)

    assert not ws.root.exists()
    assert (archive / "current_observation.json").is_file()


def test_destroy_seat_workspace_is_idempotent(tmp_path):
    ws = SeatWorkspace(color="RED", root=tmp_path / "missing")
    destroy_seat_workspace(ws)  # no raise


def test_default_pi_extension_is_shipped_with_runtime():
    assert DEFAULT_PI_EXTENSION_PATH.is_file()
    assert DEFAULT_PI_EXTENSION_PATH.name == "catanatron-arena.ts"

    source = DEFAULT_PI_EXTENSION_PATH.read_text(encoding="utf-8")
    # Tool wiring: name, schema fields, and termination signal.
    assert 'name: "choose_action"' in source
    assert "action_id:" in source
    assert "rationale:" in source
    assert "terminate: true" in source
    # File bridge: reads the per-decision metadata to learn where to write.
    assert "decision_meta.json" in source
    assert "writeFile(outputPath" in source


def test_default_pi_extension_installs_into_workspace(tmp_path):
    ws = create_seat_workspace(
        tmp_path / "RED",
        color="RED",
        pi_extension_path=DEFAULT_PI_EXTENSION_PATH,
    )

    installed = ws.root / ".pi" / "extensions" / "catanatron-arena.ts"
    assert installed.is_file()
    assert installed.read_text(encoding="utf-8") == DEFAULT_PI_EXTENSION_PATH.read_text(
        encoding="utf-8"
    )
