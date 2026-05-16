from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click

import catanatron_arena
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
    "--rotate-seats",
    is_flag=True,
    help="Rotate agent specs through color seats across games.",
)
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
    rotate_seats: bool,
    observations: bool,
):
    """Run local arena matches."""
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = [item.strip() for item in agents.split(",") if item.strip()]
    results = []
    started_at = _utc_now()

    for game_index in range(games):
        game_seed = seed + game_index
        game_specs = _rotate_specs(specs, game_index) if rotate_seats else specs
        runtimes = [
            build_local_agent(spec, seed=game_seed + agent_index)
            for agent_index, spec in enumerate(game_specs)
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
                "failed": result.failed,
                "failure_reason": result.failure_reason,
                "agents": game_specs,
                "replay_path": str(result.replay_path),
            }
        )
        click.echo(
            f"{game_index + 1}/{games} game={result.game_id} winner={result.winner} "
            f"turns={result.turns} decisions={result.decisions} failed={result.failed} "
            f"agents={','.join(game_specs)}"
        )

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps({"results": results}, indent=2, sort_keys=True), encoding="utf-8")
    manifest_path = output_dir / "manifest.json"
    manifest = _build_manifest(
        agent_specs=specs,
        games=games,
        output_dir=output_dir,
        map_type=map_type,
        seed=seed,
        vps_to_win=vps_to_win,
        max_turns=max_turns,
        max_decisions=max_decisions,
        rotate_seats=rotate_seats,
        write_observations=observations,
        started_at=started_at,
        finished_at=_utc_now(),
        results=results,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    click.echo(f"Wrote {summary_path}")
    click.echo(f"Wrote {manifest_path}")


@main.command()
@click.argument("run_dir", type=click.Path(exists=True, path_type=Path))
def rank(run_dir: Path):
    """Summarize replay results in a run directory."""
    replays = sorted((run_dir / "games").glob("*/replay.json"))
    if not replays:
        raise click.ClickException(f"No replay files found under {run_dir / 'games'}")

    wins: dict[str, int] = {}
    total_vp: dict[str, int] = {}
    agent_games: dict[str, int] = {}
    agent_wins: dict[str, int] = {}
    agent_total_vp: dict[str, int] = {}
    games = 0
    for replay_path in replays:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        games += 1
        winner = replay["final"]["winner"]
        agent_by_color = replay["config"].get("agent_by_color", {})
        if winner is not None:
            wins[winner] = wins.get(winner, 0) + 1
            winner_agent = agent_by_color.get(winner)
            if winner_agent is not None:
                agent_wins[winner_agent] = agent_wins.get(winner_agent, 0) + 1
        for color, points in replay["final"]["victory_points"].items():
            total_vp[color] = total_vp.get(color, 0) + points
            agent = agent_by_color.get(color)
            if agent is not None:
                agent_games[agent] = agent_games.get(agent, 0) + 1
                agent_total_vp[agent] = agent_total_vp.get(agent, 0) + points

    click.echo(f"games: {games}")
    click.echo("by color:")
    for color in sorted(total_vp):
        win_rate = wins.get(color, 0) / games
        avg_vp = total_vp[color] / games
        click.echo(f"{color}: wins={wins.get(color, 0)} win_rate={win_rate:.3f} avg_vp={avg_vp:.2f}")
    if agent_games:
        click.echo("by agent:")
        for agent in sorted(agent_games):
            win_rate = agent_wins.get(agent, 0) / agent_games[agent]
            avg_vp = agent_total_vp[agent] / agent_games[agent]
            click.echo(
                f"{agent}: seats={agent_games[agent]} wins={agent_wins.get(agent, 0)} "
                f"win_rate={win_rate:.3f} avg_vp={avg_vp:.2f}"
            )


def _rotate_specs(specs: list[str], offset: int) -> list[str]:
    if not specs:
        return specs
    offset = offset % len(specs)
    return specs[offset:] + specs[:offset]


def _build_manifest(
    agent_specs: list[str],
    games: int,
    output_dir: Path,
    map_type: str,
    seed: int,
    vps_to_win: int,
    max_turns: int,
    max_decisions: int,
    rotate_seats: bool,
    write_observations: bool,
    started_at: str,
    finished_at: str,
    results: list[dict],
) -> dict:
    failed = sum(1 for result in results if result.get("failed"))
    unfinished = sum(
        1
        for result in results
        if result.get("winner") is None and not result.get("failed")
    )
    return {
        "schema_version": 1,
        "arena_version": catanatron_arena.__version__,
        "git_commit": _git_commit(),
        "started_at": started_at,
        "finished_at": finished_at,
        "output_dir": str(output_dir),
        "config": {
            "agent_specs": agent_specs,
            "games": games,
            "map_type": map_type,
            "seed": seed,
            "vps_to_win": vps_to_win,
            "max_turns": max_turns,
            "max_decisions": max_decisions,
            "rotate_seats": rotate_seats,
            "write_observations": write_observations,
        },
        "results": {
            "games_completed": len(results),
            "failed": failed,
            "unfinished": unfinished,
        },
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()
