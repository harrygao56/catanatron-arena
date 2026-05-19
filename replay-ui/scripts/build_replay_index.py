#!/usr/bin/env python3
"""Build index.json files for the replay UI.

Usage:
    python3 scripts/build_replay_index.py [RUNS_DIR] [OUTPUT_DIR]

Defaults RUNS_DIR=../runs (relative to repo), OUTPUT_DIR=public/data.
Writes:
    OUTPUT_DIR/index.json              -> list of runs
    OUTPUT_DIR/<run>/index.json        -> list of games

The runs themselves are expected to be reachable from OUTPUT_DIR (typically
OUTPUT_DIR is a symlink into RUNS_DIR, so per-run index files land directly
inside each run directory and are served by the dev server).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def summarize_game(game_dir: Path) -> dict | None:
    viewer = load_json(game_dir / "viewer.json")
    if viewer is None:
        return None
    final = viewer.get("final") or {}
    config = viewer.get("config") or {}
    return {
        "game_id": viewer.get("game_id", game_dir.name),
        "winner": final.get("winner"),
        "turns": final.get("turns"),
        "num_decisions": final.get("num_decisions"),
        "failed": bool(final.get("failed")),
        "victory_points": final.get("victory_points"),
        "agent_by_color": config.get("agent_by_color"),
        "agents": config.get("agents"),
        "seed": viewer.get("seed"),
    }


def summarize_run(run_dir: Path) -> dict | None:
    games_dir = run_dir / "games"
    if not games_dir.is_dir():
        return None
    games = []
    for game_dir in sorted(games_dir.iterdir()):
        if not game_dir.is_dir():
            continue
        summary = summarize_game(game_dir)
        if summary is not None:
            games.append(summary)
    if not games:
        return None
    (run_dir / "index.json").write_text(
        json.dumps({"games": games}, indent=2, sort_keys=True), encoding="utf-8"
    )
    return {
        "run": run_dir.name,
        "num_games": len(games),
    }


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else script_dir.parent.parent / "runs"
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else script_dir.parent / "public" / "data"
    runs_dir = runs_dir.resolve()
    output_dir = output_dir.resolve()

    if not runs_dir.is_dir():
        print(f"runs dir not found: {runs_dir}", file=sys.stderr)
        return 1

    runs: list[dict] = []
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        summary = summarize_run(run_dir)
        if summary is not None:
            runs.append(summary)

    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = output_dir / "index.json"
    index_path.write_text(
        json.dumps({"runs": runs}, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Indexed {len(runs)} run(s) into {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
