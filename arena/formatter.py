"""
Formats Catanatron game state into LLM-readable text.

Two responsibilities:
1. Redact hidden information (opponent hands, dev card contents)
2. Present game state in a clear, structured format an LLM can reason about
"""

from collections import defaultdict
from typing import List, Optional, Tuple

from catanatron.game import Game
from catanatron.models.enums import (
    RESOURCES,
    DEVELOPMENT_CARDS,
    Action,
    ActionType,
)
from catanatron.models.player import Color
from catanatron.state import State
from catanatron.state_functions import (
    get_longest_road_color,
    get_longest_road_length,
    get_largest_army,
    get_visible_victory_points,
    player_key,
    player_num_resource_cards,
)


RESOURCE_NAMES = {
    "WOOD": "Wood",
    "BRICK": "Brick",
    "SHEEP": "Sheep",
    "WHEAT": "Wheat",
    "ORE": "Ore",
}

DEV_CARD_NAMES = {
    "KNIGHT": "Knight",
    "YEAR_OF_PLENTY": "Year of Plenty",
    "MONOPOLY": "Monopoly",
    "ROAD_BUILDING": "Road Building",
    "VICTORY_POINT": "Victory Point",
}


def format_action(action: Action, index: int) -> str:
    """Format a single action into a human-readable string."""
    at = action.action_type
    v = action.value

    if at == ActionType.ROLL:
        return f"[{index}] Roll dice"
    elif at == ActionType.END_TURN:
        return f"[{index}] End turn"
    elif at == ActionType.BUILD_ROAD:
        return f"[{index}] Build road at edge {v}"
    elif at == ActionType.BUILD_SETTLEMENT:
        return f"[{index}] Build settlement at node {v}"
    elif at == ActionType.BUILD_CITY:
        return f"[{index}] Upgrade to city at node {v}"
    elif at == ActionType.BUY_DEVELOPMENT_CARD:
        return f"[{index}] Buy development card"
    elif at == ActionType.PLAY_KNIGHT_CARD:
        return f"[{index}] Play Knight card"
    elif at == ActionType.PLAY_YEAR_OF_PLENTY:
        resources = ", ".join(RESOURCE_NAMES.get(r, r) for r in v)
        return f"[{index}] Play Year of Plenty → take {resources}"
    elif at == ActionType.PLAY_MONOPOLY:
        return f"[{index}] Play Monopoly → take all {RESOURCE_NAMES.get(v, v)}"
    elif at == ActionType.PLAY_ROAD_BUILDING:
        return f"[{index}] Play Road Building (2 free roads)"
    elif at == ActionType.MARITIME_TRADE:
        giving = [RESOURCE_NAMES.get(r, r) for r in v[:-1] if r is not None]
        getting = RESOURCE_NAMES.get(v[-1], v[-1])
        return f"[{index}] Maritime trade: give {', '.join(giving)} → get {getting}"
    elif at == ActionType.OFFER_TRADE:
        offering = v[:5]
        asking = v[5:]
        give_parts = []
        ask_parts = []
        for i, res in enumerate(RESOURCES):
            if offering[i] > 0:
                give_parts.append(f"{offering[i]} {RESOURCE_NAMES[res]}")
            if asking[i] > 0:
                ask_parts.append(f"{asking[i]} {RESOURCE_NAMES[res]}")
        return f"[{index}] Offer trade: give {', '.join(give_parts)} for {', '.join(ask_parts)}"
    elif at == ActionType.ACCEPT_TRADE:
        return f"[{index}] Accept trade"
    elif at == ActionType.REJECT_TRADE:
        return f"[{index}] Reject trade"
    elif at == ActionType.CONFIRM_TRADE:
        partner = v[10]
        return f"[{index}] Confirm trade with {partner.value}"
    elif at == ActionType.CANCEL_TRADE:
        return f"[{index}] Cancel trade"
    elif at == ActionType.MOVE_ROBBER:
        coord, victim = v
        victim_str = f", steal from {victim.value}" if victim else ""
        return f"[{index}] Move robber to {coord}{victim_str}"
    elif at == ActionType.DISCARD:
        return f"[{index}] Discard cards"
    else:
        return f"[{index}] {at.value} {v}"


def _get_node_production(state: State, node_id: int) -> List[Tuple[str, int]]:
    """Get (resource, number) pairs for tiles touching a node."""
    production = []
    for coord, tile in state.board.map.tiles.items():
        if not hasattr(tile, "number") or tile.number is None:
            continue
        if node_id in tile.nodes.values():
            production.append((tile.resource, tile.number))
    return production


def _format_resource_hand(state: State, color: Color) -> str:
    """Format a player's resource hand."""
    key = player_key(state, color)
    parts = []
    for res in RESOURCES:
        count = state.player_state[f"{key}_{res}_IN_HAND"]
        if count > 0:
            parts.append(f"{RESOURCE_NAMES[res]}×{count}")
    return ", ".join(parts) if parts else "empty"


def _format_dev_cards(state: State, color: Color) -> str:
    """Format a player's dev cards in hand."""
    key = player_key(state, color)
    parts = []
    for dev in DEVELOPMENT_CARDS:
        count = state.player_state[f"{key}_{dev}_IN_HAND"]
        if count > 0:
            parts.append(f"{DEV_CARD_NAMES[dev]}×{count}")
    return ", ".join(parts) if parts else "none"


def _format_played_dev_cards(state: State, color: Color) -> str:
    """Format a player's played dev cards."""
    key = player_key(state, color)
    parts = []
    for dev in DEVELOPMENT_CARDS:
        count = state.player_state[f"{key}_PLAYED_{dev}"]
        if count > 0:
            parts.append(f"{DEV_CARD_NAMES[dev]}×{count}")
    return ", ".join(parts) if parts else "none"


def _format_port_access(state: State, color: Color) -> str:
    """List ports the player has access to via settlements/cities."""
    port_nodes = state.board.map.port_nodes
    player_nodes = set()
    for node_id, building in state.board.buildings.items():
        if building[0] == color:
            player_nodes.add(node_id)

    ports = set()
    for resource, nodes in port_nodes.items():
        if player_nodes & nodes:
            if resource is None:
                ports.add("3:1 (any)")
            else:
                ports.add(f"2:1 ({RESOURCE_NAMES[resource]})")

    return ", ".join(sorted(ports)) if ports else "none"


def _number_probability(number: int) -> str:
    """Dots notation for dice probability."""
    probs = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
    dots = probs.get(number, 0)
    return "•" * dots


def format_game_state(
    game: Game,
    perspective_color: Color,
    last_n_actions: int = 10,
) -> str:
    """
    Format the full game state from a player's perspective.

    Hidden information is redacted:
    - Opponent resource cards → count only
    - Opponent dev cards → count only
    - Dev card deck order → hidden

    Args:
        game: Current game state
        perspective_color: The color of the player receiving this state
        last_n_actions: Number of recent actions to include

    Returns:
        Formatted string suitable for LLM consumption
    """
    state = game.state
    p_key = player_key(state, perspective_color)
    sections = []

    # === Header ===
    sections.append(
        f"=== GAME STATE (Turn {state.num_turns}) ==="
    )
    sections.append(f"You are: {perspective_color.value}")
    sections.append(f"Phase: {state.current_prompt.value}")

    # === Your Status ===
    vp = get_visible_victory_points(state, perspective_color)
    actual_vp = state.player_state[f"{p_key}_ACTUAL_VICTORY_POINTS"]
    sections.append("")
    sections.append("--- YOUR STATUS ---")
    sections.append(f"Victory Points: {vp} public" + (
        f" ({actual_vp} actual)" if actual_vp != vp else ""
    ))
    sections.append(f"Resources: {_format_resource_hand(state, perspective_color)}")
    sections.append(f"Dev cards: {_format_dev_cards(state, perspective_color)}")
    sections.append(f"Played dev cards: {_format_played_dev_cards(state, perspective_color)}")
    sections.append(f"Roads left: {state.player_state[f'{p_key}_ROADS_AVAILABLE']}")
    sections.append(f"Settlements left: {state.player_state[f'{p_key}_SETTLEMENTS_AVAILABLE']}")
    sections.append(f"Cities left: {state.player_state[f'{p_key}_CITIES_AVAILABLE']}")
    sections.append(f"Longest road length: {state.player_state[f'{p_key}_LONGEST_ROAD_LENGTH']}")
    sections.append(f"Knights played: {state.player_state[f'{p_key}_PLAYED_KNIGHT']}")
    sections.append(f"Ports: {_format_port_access(state, perspective_color)}")

    # === Your Buildings ===
    sections.append("")
    sections.append("--- YOUR BUILDINGS ---")
    buildings = state.buildings_by_color.get(perspective_color, {})
    for btype in ["SETTLEMENT", "CITY"]:
        nodes = buildings.get(btype, [])
        if nodes:
            for node in nodes:
                prod = _get_node_production(state, node)
                prod_str = ", ".join(
                    f"{RESOURCE_NAMES[r]} on {n} {_number_probability(n)}"
                    for r, n in prod
                )
                sections.append(f"  {btype.title()} at node {node}: produces [{prod_str}]")
    roads = buildings.get("ROAD", [])
    if roads:
        sections.append(f"  Roads: {roads}")

    # === Opponents ===
    sections.append("")
    sections.append("--- OPPONENTS ---")
    for color in state.colors:
        if color == perspective_color:
            continue
        opp_key = player_key(state, color)
        opp_vp = get_visible_victory_points(state, color)
        opp_cards = player_num_resource_cards(state, color)
        opp_dev_count = sum(
            state.player_state[f"{opp_key}_{dev}_IN_HAND"]
            for dev in DEVELOPMENT_CARDS
        )
        opp_buildings = state.buildings_by_color.get(color, {})
        settlements = opp_buildings.get("SETTLEMENT", [])
        cities = opp_buildings.get("CITY", [])
        road_len = state.player_state[f"{opp_key}_LONGEST_ROAD_LENGTH"]
        knights = state.player_state[f"{opp_key}_PLAYED_KNIGHT"]

        sections.append(f"  {color.value}:")
        sections.append(f"    VP: {opp_vp} | Cards: {opp_cards} resource, {opp_dev_count} dev")
        sections.append(f"    Played dev cards: {_format_played_dev_cards(state, color)}")
        if settlements:
            sections.append(f"    Settlements: nodes {settlements}")
        if cities:
            sections.append(f"    Cities: nodes {cities}")
        sections.append(f"    Longest road: {road_len} | Knights played: {knights}")

    # === Board State ===
    sections.append("")
    sections.append("--- BOARD ---")

    # Robber
    sections.append(f"Robber: tile {state.board.robber_coordinate}")

    # Longest road / largest army holders
    lr_color = get_longest_road_color(state)
    la = get_largest_army(state)
    if lr_color:
        sections.append(f"Longest Road: {lr_color.value}")
    if la and la[0] is not None:
        sections.append(f"Largest Army: {la[0].value} ({la[1]} knights)")

    # Bank
    bank = state.resource_freqdeck
    bank_str = ", ".join(
        f"{RESOURCE_NAMES[RESOURCES[i]]}×{bank[i]}" for i in range(5)
    )
    sections.append(f"Bank: {bank_str}")
    sections.append(f"Dev cards remaining: {len(state.development_listdeck)}")

    # === Recent Actions ===
    if last_n_actions > 0 and state.action_records:
        sections.append("")
        sections.append("--- RECENT ACTIONS ---")
        recent = state.action_records[-last_n_actions:]
        for record in recent:
            a = record.action
            result_str = ""
            if a.action_type == ActionType.ROLL and record.result:
                result_str = f" → rolled {record.result[0]}+{record.result[1]}={sum(record.result)}"
            elif a.action_type == ActionType.BUY_DEVELOPMENT_CARD and record.result:
                # Don't reveal what card was bought (unless it's the perspective player)
                if a.color == perspective_color:
                    result_str = f" → got {DEV_CARD_NAMES.get(record.result, record.result)}"
                else:
                    result_str = " → got a card"
            sections.append(f"  {a.color.value}: {a.action_type.value}" + (
                f" {a.value}" if a.value is not None and a.action_type != ActionType.ROLL else ""
            ) + result_str)

    # === Legal Actions ===
    sections.append("")
    sections.append("--- LEGAL ACTIONS ---")
    for i, action in enumerate(game.playable_actions):
        sections.append(format_action(action, i))

    return "\n".join(sections)
