# Catanatron Arena Agent Runtime Handoff

## Current State

The arena package lives under `catanatron/catanatron_arena/`.

Implemented and pushed locally:

- `protocol/actions.py`: legal action JSON, Gym action ID conversion, selected-ID validation.
- `protocol/observation.py`: redacted decision observation builder using `create_sample(game, color)`.
- `agents/local.py`: local `first_action`, `random`, and Catanatron-backed baselines.
- `runner/match.py`: match loop, invalid-action retries/failures, compact/full observation recording.
- `replay/recorder.py`: replay JSON, optional full observation files.
- `cli.py`: `catanatron-arena run` and `catanatron-arena rank`.

Recent features:

- `--compact` skips per-decision observation JSON files.
- `--observations` writes full per-decision observations.
- `--vps-to-win`, `--max-turns`, and `--max-decisions` configure run limits.
- `--rotate-seats` rotates agent specs through color seats across games.
- `manifest.json` is written at run root with config, git commit, timestamps, and aggregate failed/unfinished counts.
- `rank` reports by color and by agent using replay `config.agent_by_color`.

Focused test command:

```bash
.venv/bin/python -m pytest tests/test_arena_protocol.py -q
```

Last known focused test status:

```text
11 passed
```

## Useful Local Commands

Run a quick baseline-vs-random smoke:

```bash
catanatron-arena run \
  --agents ab:1,random,random,random \
  --games 4 \
  --out runs/rotate-smoke \
  --map-type BASE \
  --seed 700 \
  --vps-to-win 3 \
  --max-turns 500 \
  --max-decisions 2000 \
  --compact \
  --rotate-seats
```

Rank:

```bash
catanatron-arena rank runs/rotate-smoke
```

Known validation result:

- `ab:1` beat three random agents 40/40 on BASE 10 VP when manually rotated through seats.
- BASE is the meaningful default for 10 VP runs.
- MINI is useful only for fast protocol smoke tests; 10 VP MINI games can stall.

## Local Baseline Specs

Supported by `build_local_agent()`:

- `first_action`
- `random`
- `weighted_random`, `weighted`, `w`
- `victory_point`, `vp`
- `value`, `value_function`, `f`
- `mcts:N`
- `mcts:N:PRUNING`
- `greedy:N`
- `ab:DEPTH`
- `ab:DEPTH:PRUNING`
- `sab:DEPTH`
- `sab:DEPTH:PRUNING`

`ab:1` is currently the fastest useful real baseline.

## Model Agent Runtime Direction

Next major work is Docker + Pi model agents.

Agreed design:

- One Docker container per seat per game.
- Container lives for exactly one game.
- Same Pi conversation/session is used for every decision in that game.
- The per-game workspace persists across turns within that game.
- Do not pre-create `memory.md`. The agent may create files if it wants.
- Keep workspace blank/minimal except for arena-provided files such as `AGENTS.md`, observation files, and the Pi extension.
- Full observation is written to files; prompt sent to Pi should be compact.
- Agent must choose actions through `choose_action`.
- `choose_action` includes `action_id` and `rationale`.
- Invalid action retries happen in the same Pi session with a retry prompt explaining the invalid choice.
- Host `.env` can hold provider tokens, but do not mount `.env` into containers. Arena should load selected variables and pass them via Docker environment.

## Pi Invocation Design

Arena starts each seat container on the host:

```bash
docker run \
  --rm \
  --name catanatron-arena-<game_id>-RED \
  --workdir /workspace \
  --mount type=bind,src=<host_workspace_RED>,dst=/workspace \
  --env OPENAI_API_KEY \
  --env ANTHROPIC_API_KEY \
  catanatron-arena-agent:latest \
  sleep infinity
```

Then arena starts Pi inside that container and keeps the process alive for the game:

```bash
docker exec -i \
  --workdir /workspace \
  catanatron-arena-<game_id>-RED \
  pi --mode rpc \
    --provider <provider> \
    --model <model> \
    --session-dir /workspace/.pi/sessions \
    --extension /workspace/.pi/extensions/catanatron-arena.ts
```

The arena process writes Pi RPC commands as JSONL to stdin and reads JSONL responses/events from stdout.

Per decision, arena writes:

```text
/workspace/current_observation.json
/workspace/legal_actions.json
/workspace/current_decision.json
/workspace/observations/turn_000042.json
```

Then sends a Pi RPC prompt:

```json
{
  "id": "decision-000042-attempt-001",
  "type": "prompt",
  "message": "Decision 42. You are RED. Read /workspace/current_observation.json and /workspace/legal_actions.json. Call choose_action with one legal action_id and a rationale."
}
```

Pi accepts the prompt with a response event, then streams agent/tool events. The runner should wait for output, `agent_end`, or timeout.

## Tool File Bridge

Use a Pi TypeScript extension to register `choose_action`.

The extension should read `/workspace/current_decision.json` to find the decision/attempt/output path, then write:

```text
/workspace/outputs/turn_000042_attempt_001.json
```

Payload:

```json
{
  "action_id": 123,
  "rationale": "Build settlement to improve ore and wheat production."
}
```

The host sees this file through the bind-mounted workspace and validates `action_id` against Catanatron legal actions. The tool does not apply game state.

Retry file naming:

```text
outputs/turn_000042_attempt_001.json
outputs/turn_000042_attempt_002.json
outputs/turn_000042_attempt_003.json
```

On invalid action, prompt the same Pi session:

```text
Your previous choose_action selected action_id=999.
That action is invalid because: <reason>.
Use the same legal_actions.json and choose a valid action_id.
Attempts remaining: 2.
```

Do not advance game state until a valid action is selected.

## Observation And Prompt Bloat

The canonical observation currently contains:

- `game_id`
- `decision_index`
- `current_prompt`
- `seat_color`
- `seating_order`
- `turn_index`
- `features`
- `legal_actions`
- `recent_actions`

`features` comes from `catanatron.features.create_sample(game, seat_color)` and is intended to be redacted/player-view. Do not expose raw `Game`, raw `State`, raw `player_state`, deck order, or opponent hidden cards.

Bloat risks:

- `features`
- `legal_actions`

`recent_actions` is capped at 12 and is less concerning.

Recommended model prompt strategy:

- Write full observation files.
- Keep the inline prompt concise.
- Include legal action count and maybe action-type counts inline.
- Let the agent read `/workspace/legal_actions.json` and `/workspace/current_observation.json`.

## Next Implementation Steps

1. Add workspace creation helpers for Docker/Pi seats.
2. Add a project-local Pi extension template for `choose_action`.
3. Add a Docker runtime class that starts/stops one container per seat per game.
4. Add a Pi RPC client wrapper that sends prompts and reads events.
5. Add output-file polling and timeout handling.
6. Wire Docker/Pi runtime into `run_match`.
7. Add agent config file support for provider/model/image/env vars/timeouts.
8. Add replay refs for prompt/output/session logs and runtime failure statuses.

