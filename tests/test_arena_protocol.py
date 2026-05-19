import json

from catanatron.game import Game
from catanatron.models.map import build_map
from catanatron.models.player import Color, Player

from catanatron_arena.agents.local import build_local_agent
from catanatron_arena.cli import _build_manifest, _rotate_specs
from catanatron_arena.protocol.actions import (
    InvalidActionSelection,
    legal_action_json,
    validate_selected_action,
)
from catanatron_arena.protocol.observation import build_observation
from catanatron_arena.runner.match import MatchConfig, run_match


def make_game(seed=1):
    players = [
        Player(Color.RED),
        Player(Color.BLUE),
        Player(Color.ORANGE),
        Player(Color.WHITE),
    ]
    return Game(players, seed=seed, catan_map=build_map("MINI"))


def test_legal_action_json_roundtrips():
    game = make_game()
    legal = legal_action_json(game, "MINI")

    assert legal
    recovered = validate_selected_action(game, legal[0]["id"], "MINI")

    assert recovered in game.playable_actions
    assert legal[0]["type"] == recovered.action_type.value


def test_invalid_action_id_is_rejected():
    game = make_game()

    try:
        validate_selected_action(game, -1, "MINI")
    except InvalidActionSelection as exc:
        assert "illegal action" in str(exc) or "outside action space" in str(exc)
    else:
        raise AssertionError("invalid action id should have been rejected")


def test_observation_is_json_safe_and_does_not_expose_raw_state():
    game = make_game()
    observation = build_observation(game, "MINI", decision_index=0)

    encoded = json.dumps(observation)

    assert observation["seat_color"] == game.state.current_color().value
    assert observation["legal_actions"]
    assert "player_state" not in encoded
    assert "development_listdeck" not in encoded


def test_local_match_writes_replay(tmp_path):
    agents = [build_local_agent("first_action") for _ in range(4)]

    result = run_match(
        agents,
        tmp_path,
        MatchConfig(seed=7, map_type="MINI", vps_to_win=3, max_decisions=250),
    )

    assert result.replay_path.exists()
    replay = json.loads(result.replay_path.read_text(encoding="utf-8"))
    assert replay["decisions"]
    assert replay["schema_version"] == 2
    assert replay["initial_state_ref"] == "states/state_000000.json"
    assert replay["final"]["num_decisions"] == result.decisions
    assert replay["config"]["agent_by_color"]

    game_dir = result.replay_path.parent
    first_decision = replay["decisions"][0]
    assert (game_dir / first_decision["state_before_ref"]).exists()
    assert (game_dir / first_decision["state_after_ref"]).exists()
    assert first_decision["decision_ref"] == "decisions/decision_000000.json"

    decision_detail = json.loads(
        (game_dir / first_decision["decision_ref"]).read_text(encoding="utf-8")
    )
    assert decision_detail["observation"]["decision_index"] == 0
    assert decision_detail["legal_actions"]
    assert (
        decision_detail["selected"]["action_id"] == first_decision["selected_action_id"]
    )

    viewer = json.loads((game_dir / "viewer.json").read_text(encoding="utf-8"))
    assert viewer["game_id"] == result.game_id
    assert viewer["initial_state_ref"] == "states/state_000000.json"
    assert viewer["timeline"][0]["decision_ref"] == first_decision["decision_ref"]


def test_compact_match_skips_observation_files(tmp_path):
    agents = [build_local_agent("random", seed=index) for index in range(4)]

    result = run_match(
        agents,
        tmp_path,
        MatchConfig(
            seed=7,
            map_type="MINI",
            vps_to_win=3,
            max_decisions=25,
            write_observations=False,
        ),
    )

    replay = json.loads(result.replay_path.read_text(encoding="utf-8"))
    assert replay["decisions"]
    assert replay["decisions"][0]["observation_ref"] is None
    assert not list(result.replay_path.parent.glob("observations/*.json"))


def test_match_records_configured_turn_limit(tmp_path):
    agents = [build_local_agent("first_action") for _ in range(4)]

    result = run_match(
        agents,
        tmp_path,
        MatchConfig(
            seed=7,
            map_type="MINI",
            max_turns=5,
            max_decisions=100,
            write_observations=False,
        ),
    )

    replay = json.loads(result.replay_path.read_text(encoding="utf-8"))
    assert result.turns == 5
    assert replay["config"]["max_turns"] == 5


class InvalidAgent:
    name = "invalid"
    max_invalid_retries = 0

    def choose_action(self, observation, attempt=1):
        from catanatron_arena.protocol.actions import SelectedAction

        return SelectedAction(action_id=-1, rationale="bad id")


class InvalidAgentWithRuntimeRefs:
    name = "invalid-with-refs"
    max_invalid_retries = 0

    def choose_action(self, observation, attempt=1):
        from catanatron_arena.protocol.actions import SelectedAction

        return SelectedAction(
            action_id=-1,
            rationale="bad id",
            runtime_refs={
                "prompt": "runtime/RED/decisions/turn_000000_attempt_001/prompt.txt"
            },
        )


def test_invalid_local_agent_fails_match(tmp_path):
    agents = [InvalidAgent()] + [build_local_agent("first_action") for _ in range(3)]

    result = run_match(
        agents,
        tmp_path,
        MatchConfig(seed=7, map_type="MINI", vps_to_win=3, max_decisions=250),
    )

    assert result.failed
    replay = json.loads(result.replay_path.read_text(encoding="utf-8"))
    assert replay["final"]["failed"]
    assert any(
        decision["status"] == "invalid_action_failed"
        for decision in replay["decisions"]
    )


def test_failed_decision_records_runtime_refs(tmp_path):
    agents = [InvalidAgentWithRuntimeRefs()] + [
        build_local_agent("first_action") for _ in range(3)
    ]

    result = run_match(
        agents,
        tmp_path,
        MatchConfig(seed=7, map_type="MINI", vps_to_win=3, max_decisions=250),
    )

    replay = json.loads(result.replay_path.read_text(encoding="utf-8"))
    decision = next(
        decision
        for decision in replay["decisions"]
        if decision["status"] == "invalid_action_failed"
    )
    assert decision["runtime_refs"]["1"]["prompt"] == (
        "runtime/RED/decisions/turn_000000_attempt_001/prompt.txt"
    )
    detail = json.loads(
        (result.replay_path.parent / decision["decision_ref"]).read_text(
            encoding="utf-8"
        )
    )
    assert detail["agent"]["1"]["refs"]["prompt"] == (
        "runtime/RED/decisions/turn_000000_attempt_001/prompt.txt"
    )


def test_catanatron_baseline_uses_action_protocol(tmp_path):
    agents = [build_local_agent("weighted_random") for _ in range(4)]

    result = run_match(
        agents,
        tmp_path,
        MatchConfig(
            seed=7,
            map_type="MINI",
            vps_to_win=3,
            max_turns=200,
            max_decisions=1000,
            write_observations=False,
        ),
    )

    replay = json.loads(result.replay_path.read_text(encoding="utf-8"))
    assert replay["decisions"]
    assert replay["decisions"][0]["mapped_action"]["type"]


def test_parameterized_catanatron_baselines_build():
    assert build_local_agent("mcts:2").name == "mcts:2:0"
    assert build_local_agent("mcts:2:1").name == "mcts:2:1"
    assert build_local_agent("greedy:2").name == "greedy:2"
    assert build_local_agent("ab:1").name == "ab:1:1"
    assert build_local_agent("sab:1:0").name == "sab:1:0"


def test_rotate_specs():
    specs = ["a", "b", "c", "d"]
    assert _rotate_specs(specs, 0) == ["a", "b", "c", "d"]
    assert _rotate_specs(specs, 1) == ["b", "c", "d", "a"]
    assert _rotate_specs(specs, 4) == ["a", "b", "c", "d"]


def test_build_manifest_counts_results(tmp_path):
    manifest = _build_manifest(
        agent_specs=["ab:1", "random"],
        games=3,
        output_dir=tmp_path,
        map_type="BASE",
        seed=10,
        vps_to_win=10,
        max_turns=100,
        max_decisions=500,
        rotate_seats=True,
        write_observations=False,
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        results=[
            {"winner": "RED", "failed": False},
            {"winner": None, "failed": False},
            {"winner": None, "failed": True},
        ],
    )

    assert manifest["config"]["rotate_seats"]
    assert manifest["results"]["games_completed"] == 3
    assert manifest["results"]["unfinished"] == 1
    assert manifest["results"]["failed"] == 1
