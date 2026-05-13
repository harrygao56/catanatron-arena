from __future__ import annotations

import json
from pathlib import Path

import click

from catanatron_arena.agents.local import build_local_agent
from catanatron_arena.runner.match import MatchConfig, run_match


@click.group()
def main():
    """Run and rank Catanatron Arena benchmarks."""


@main.command()
@click.option("--agents", default="random,random,random,random", show_default=True)
@click.option("--games", default=1, show_default=True, type=int)
@click.option("--out", "output_dir", default="runs/smoke", show_default=True, type=click.Path(path_type=Path))
@click.option("--map-type", default="BASE", show_default=True, type=click.Choice(["BASE", "MINI", "TOURNAMENT"]))
@click.option("--seed", default=1, show_default=True, type=int)
@click.option("--vps-to-win", default=10, show_default=True, type=int)
@click.option("--max-turns", default=1000, show_default=True, type=int)
@click.option("--max-decisions", default=20000, show_default=True, type=int)
@click.option(
    "--observations/--compact",
    default=True,
    show_default=True,
    help="Write full per-decision observation JSON files, or compact replay metadata only.",
)
def run(
    agents: str,
    games: int,
    output_dir: Path,
    map_type: str,
    seed: int,
    vps_to_win: int,
    max_turns: int,
    max_decisions: int,
    observations: bool,
):
    """Run local arena matches."""
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = [item.strip() for item in agents.split(",") if item.strip()]
    results = []

    for game_index in range(games):
        game_seed = seed + game_index
        runtimes = [
            build_local_agent(spec, seed=game_seed + agent_index)
            for agent_index, spec in enumerate(specs)
        ]
        result = run_match(
            runtimes,
            output_dir,
            MatchConfig(
                seed=game_seed,
                map_type=map_type,
                vps_to_win=vps_to_win,
                max_turns=max_turns,
                max_decisions=max_decisions,
                write_observations=observations,
            ),
        )
        results.append(
            {
                "game_id": result.game_id,
                "winner": result.winner,
                "turns": result.turns,
                "decisions": result.decisions,
                "replay_path": str(result.replay_path),
            }
        )
        click.echo(
            f"{game_index + 1}/{games} game={result.game_id} winner={result.winner} "
            f"turns={result.turns} decisions={result.decisions} failed={result.failed}"
        )

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps({"results": results}, indent=2, sort_keys=True), encoding="utf-8")
    click.echo(f"Wrote {summary_path}")


@main.command()
@click.argument("run_dir", type=click.Path(exists=True, path_type=Path))
def rank(run_dir: Path):
    """Summarize replay results in a run directory."""
    replays = sorted((run_dir / "games").glob("*/replay.json"))
    if not replays:
        raise click.ClickException(f"No replay files found under {run_dir / 'games'}")

    wins: dict[str, int] = {}
    total_vp: dict[str, int] = {}
    games = 0
    for replay_path in replays:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        games += 1
        winner = replay["final"]["winner"]
        if winner is not None:
            wins[winner] = wins.get(winner, 0) + 1
        for color, points in replay["final"]["victory_points"].items():
            total_vp[color] = total_vp.get(color, 0) + points

    click.echo(f"games: {games}")
    for color in sorted(total_vp):
        win_rate = wins.get(color, 0) / games
        avg_vp = total_vp[color] / games
        click.echo(f"{color}: wins={wins.get(color, 0)} win_rate={win_rate:.3f} avg_vp={avg_vp:.2f}")
