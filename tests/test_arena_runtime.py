import json

import pytest

from catanatron_arena.runtime import (
    SeatWorkspace,
    create_seat_workspace,
    destroy_seat_workspace,
)
from catanatron_arena.runtime.workspace import DEFAULT_AGENTS_MD


def test_create_seat_workspace_lays_out_expected_structure(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")

    assert isinstance(ws, SeatWorkspace)
    assert ws.color == "RED"
    assert ws.observations_dir.is_dir()
    assert ws.outputs_dir.is_dir()
    assert ws.pi_sessions_dir.is_dir()
    assert ws.pi_extensions_dir.is_dir()
    assert ws.agents_md_path.is_file()
    assert ws.agents_md_path.read_text(encoding="utf-8") == DEFAULT_AGENTS_MD
    # Per the plan: do not pre-create memory.md; the agent may create it.
    assert not (ws.root / "memory.md").exists()


def test_create_seat_workspace_accepts_custom_agents_md(tmp_path):
    ws = create_seat_workspace(
        tmp_path / "BLUE",
        color="BLUE",
        agents_md="custom instructions",
    )
    assert ws.agents_md_path.read_text(encoding="utf-8") == "custom instructions"


def test_create_seat_workspace_copies_pi_extension(tmp_path):
    extension = tmp_path / "src" / "catanatron-arena.ts"
    extension.parent.mkdir()
    extension.write_text("export const tool = {};", encoding="utf-8")

    ws = create_seat_workspace(
        tmp_path / "ORANGE",
        color="ORANGE",
        pi_extension_path=extension,
    )

    copied = ws.pi_extensions_dir / "catanatron-arena.ts"
    assert copied.is_file()
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

    output_path = ws.write_decision_files(observation, attempt=1)

    assert output_path == ws.output_path(7, 1)
    assert output_path == ws.outputs_dir / "turn_000007_attempt_001.json"

    current = json.loads(ws.current_observation_path.read_text(encoding="utf-8"))
    legal = json.loads(ws.legal_actions_path.read_text(encoding="utf-8"))
    decision = json.loads(ws.current_decision_path.read_text(encoding="utf-8"))
    historical = json.loads(ws.observation_path(7).read_text(encoding="utf-8"))

    assert current == observation
    assert historical == observation
    assert legal == observation["legal_actions"]
    assert decision == {
        "decision_index": 7,
        "attempt": 1,
        "seat_color": "RED",
        "output_path": str(output_path),
    }


def test_write_decision_files_overwrites_current_files_across_turns(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")
    obs_a = {"decision_index": 0, "legal_actions": [{"id": 1}]}
    obs_b = {"decision_index": 1, "legal_actions": [{"id": 2}]}

    ws.write_decision_files(obs_a, attempt=1)
    ws.write_decision_files(obs_b, attempt=1)

    current = json.loads(ws.current_observation_path.read_text(encoding="utf-8"))
    assert current["decision_index"] == 1
    # Per-turn history is preserved for both decisions.
    assert ws.observation_path(0).is_file()
    assert ws.observation_path(1).is_file()


def test_read_attempt_output_parses_agent_file(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")
    ws.write_decision_files({"decision_index": 3, "legal_actions": []}, attempt=2)
    ws.output_path(3, 2).write_text(
        json.dumps({"action_id": 42, "rationale": "go"}),
        encoding="utf-8",
    )

    assert ws.read_attempt_output(3, 2) == {"action_id": 42, "rationale": "go"}


def test_destroy_seat_workspace_removes_root(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")
    assert ws.root.exists()

    destroy_seat_workspace(ws)

    assert not ws.root.exists()


def test_destroy_seat_workspace_archives_when_requested(tmp_path):
    ws = create_seat_workspace(tmp_path / "RED", color="RED")
    ws.write_decision_files({"decision_index": 0, "legal_actions": []}, attempt=1)
    archive = tmp_path / "archived" / "game-abc" / "RED"

    destroy_seat_workspace(ws, archive_to=archive)

    assert not ws.root.exists()
    assert archive.is_dir()
    assert (archive / "current_observation.json").is_file()


def test_destroy_seat_workspace_is_idempotent(tmp_path):
    ws = SeatWorkspace(color="RED", root=tmp_path / "missing")
    # Should not raise.
    destroy_seat_workspace(ws)
