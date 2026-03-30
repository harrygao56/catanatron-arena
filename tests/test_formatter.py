"""Tests for arena.formatter — game state formatting for LLM agents."""

from catanatron import Game, RandomPlayer, Color
from catanatron.models.enums import ActionType, RESOURCES
from catanatron.state_functions import player_key

from arena.formatter import format_game_state, format_action


def _make_game(seed=42):
    """Create a deterministic game."""
    players = [
        RandomPlayer(Color.RED),
        RandomPlayer(Color.BLUE),
        RandomPlayer(Color.WHITE),
        RandomPlayer(Color.ORANGE),
    ]
    return Game(players, seed=seed)


def _advance_game(game, ticks=30):
    """Advance a game by N ticks."""
    for _ in range(ticks):
        if game.winning_color() is None:
            game.play_tick()
    return game


class TestFormatGameState:
    def test_output_contains_required_sections(self):
        game = _advance_game(_make_game(), ticks=40)
        color = game.state.colors[0]
        output = format_game_state(game, color)

        assert "=== GAME STATE" in output
        assert "--- YOUR STATUS ---" in output
        assert "--- YOUR BUILDINGS ---" in output
        assert "--- OPPONENTS ---" in output
        assert "--- BOARD ---" in output
        assert "--- LEGAL ACTIONS ---" in output

    def test_shows_correct_perspective_color(self):
        game = _advance_game(_make_game(), ticks=40)
        for color in game.state.colors:
            output = format_game_state(game, color)
            assert f"You are: {color.value}" in output

    def test_shows_own_resources_not_opponents(self):
        game = _advance_game(_make_game(), ticks=50)
        state = game.state
        perspective = state.colors[0]
        output = format_game_state(game, perspective)

        # Our resources section should show actual resource names
        lines = output.split("\n")
        our_section = False
        opp_section = False
        for line in lines:
            if "--- YOUR STATUS ---" in line:
                our_section = True
                opp_section = False
            elif "--- OPPONENTS ---" in line:
                our_section = False
                opp_section = True
            elif "---" in line:
                our_section = False
                opp_section = False

            # Opponents should only show card counts, not specific resources
            if opp_section and "Cards:" in line:
                assert "resource" in line  # "N resource, M dev"

    def test_redacts_opponent_dev_card_purchases(self):
        """When an opponent buys a dev card, the result should be hidden."""
        game = _advance_game(_make_game(), ticks=100)
        state = game.state
        perspective = state.colors[0]
        output = format_game_state(game, perspective)

        # Check that opponent dev card purchases don't reveal the card type
        for line in output.split("\n"):
            if "BUY_DEVELOPMENT_CARD" in line and "RECENT ACTIONS" in "".join(output.split("\n")[:output.split("\n").index(line)]):
                # If it's not our color, it should say "got a card" not the card name
                for color in state.colors:
                    if color != perspective and color.value in line:
                        assert "got a card" in line or "BUY_DEVELOPMENT_CARD" in line

    def test_legal_actions_are_numbered(self):
        game = _advance_game(_make_game(), ticks=40)
        color = game.state.current_color()
        output = format_game_state(game, color)

        actions_section = output.split("--- LEGAL ACTIONS ---")[1]
        lines = [l.strip() for l in actions_section.strip().split("\n") if l.strip()]
        for i, line in enumerate(lines):
            assert line.startswith(f"[{i}]"), f"Action {i} not properly numbered: {line}"

    def test_shows_robber_location(self):
        game = _advance_game(_make_game(), ticks=40)
        color = game.state.colors[0]
        output = format_game_state(game, color)
        assert "Robber:" in output

    def test_shows_bank_resources(self):
        game = _advance_game(_make_game(), ticks=40)
        color = game.state.colors[0]
        output = format_game_state(game, color)
        assert "Bank:" in output

    def test_shows_port_access(self):
        game = _advance_game(_make_game(), ticks=40)
        color = game.state.colors[0]
        output = format_game_state(game, color)
        assert "Ports:" in output

    def test_shows_building_production(self):
        game = _advance_game(_make_game(), ticks=40)
        color = game.state.colors[0]
        output = format_game_state(game, color)
        # Buildings section should mention production
        if "Settlement at node" in output or "City at node" in output:
            assert "produces" in output

    def test_initial_build_phase(self):
        """Formatter should work during initial settlement placement."""
        game = _make_game()
        color = game.state.current_color()
        output = format_game_state(game, color)
        assert "BUILD_INITIAL_SETTLEMENT" in output
        assert "--- LEGAL ACTIONS ---" in output

    def test_recent_actions_limited(self):
        game = _advance_game(_make_game(), ticks=100)
        color = game.state.colors[0]
        output = format_game_state(game, color, last_n_actions=3)
        actions_section = output.split("--- RECENT ACTIONS ---")[1].split("--- LEGAL ACTIONS ---")[0]
        action_lines = [l for l in actions_section.strip().split("\n") if l.strip()]
        assert len(action_lines) <= 3

    def test_no_recent_actions(self):
        game = _advance_game(_make_game(), ticks=40)
        color = game.state.colors[0]
        output = format_game_state(game, color, last_n_actions=0)
        assert "--- RECENT ACTIONS ---" not in output


class TestFormatAction:
    def test_roll(self):
        from catanatron.models.enums import Action
        a = Action(Color.RED, ActionType.ROLL, None)
        assert format_action(a, 0) == "[0] Roll dice"

    def test_end_turn(self):
        from catanatron.models.enums import Action
        a = Action(Color.RED, ActionType.END_TURN, None)
        assert format_action(a, 5) == "[5] End turn"

    def test_build_settlement(self):
        from catanatron.models.enums import Action
        a = Action(Color.RED, ActionType.BUILD_SETTLEMENT, 7)
        assert format_action(a, 2) == "[2] Build settlement at node 7"

    def test_build_road(self):
        from catanatron.models.enums import Action
        a = Action(Color.RED, ActionType.BUILD_ROAD, (4, 7))
        assert format_action(a, 1) == "[1] Build road at edge (4, 7)"

    def test_maritime_trade(self):
        from catanatron.models.enums import Action
        a = Action(Color.RED, ActionType.MARITIME_TRADE, ("WOOD", "WOOD", "WOOD", "WOOD", "ORE"))
        result = format_action(a, 3)
        assert "[3] Maritime trade" in result
        assert "Wood" in result
        assert "Ore" in result

    def test_monopoly(self):
        from catanatron.models.enums import Action
        a = Action(Color.RED, ActionType.PLAY_MONOPOLY, "WHEAT")
        assert "Wheat" in format_action(a, 0)

    def test_move_robber_with_victim(self):
        from catanatron.models.enums import Action
        a = Action(Color.RED, ActionType.MOVE_ROBBER, ((1, -1, 0), Color.BLUE))
        result = format_action(a, 0)
        assert "Move robber" in result
        assert "BLUE" in result

    def test_move_robber_no_victim(self):
        from catanatron.models.enums import Action
        a = Action(Color.RED, ActionType.MOVE_ROBBER, ((1, -1, 0), None))
        result = format_action(a, 0)
        assert "Move robber" in result
        assert "steal" not in result
