# Catanatron Arena Implementation Plan

## Goal

Build an open-source benchmark framework for model agents competing in simulated
Catan games through Catanatron. The benchmark will run controlled matches between
models such as GPT and Claude, record replayable games, and publish aggregate
results.

The benchmark does not accept third-party submitted agents and does not
distribute agent VM images. Each agent seat runs in an isolated runtime with
filesystem memory that lasts for one game.

## Core Decisions

- Use Catanatron as the authoritative game engine.
- Use decision-only observations: call an agent only when that agent must choose
  an action.
- Give each agent a fresh per-game workspace that persists across that game and
  is destroyed or archived after the game.
- Use Docker for per-agent isolation.
- Use Pi as the model-agent harness inside each Docker container.
- Allow bash access inside the agent container for the initial tool-using league.
- Allow network access from agent containers for model API calls.
- Inject provider API credentials through environment variables, not files.
- Do not mount the host repo or Docker socket into agent containers.
- Require agents to choose actions through a constrained `choose_action` tool.
- Reuse Catanatron Gym action IDs for action selection.
- Base player-view redaction on Catanatron's existing feature extraction rather
  than exposing raw `Game` or `State` objects.

## Architecture

```text
arena runner
  |
  |-- Catanatron engine process
  |
  |-- Docker container: RED agent workspace + Pi harness
  |-- Docker container: BLUE agent workspace + Pi harness
  |-- Docker container: ORANGE agent workspace + Pi harness
  |-- Docker container: WHITE agent workspace + Pi harness
```

The engine owns the complete game state. Agent containers receive only
player-view observations and legal action lists. Agents never receive the raw
Catanatron `Game` object.

## Observation Model

An observation is the player-view JSON sent to the current player when that
player must decide an action.

Decision-only flow:

1. The game reaches a player decision.
2. The arena builds an observation for the current player.
3. The arena writes the observation into that player's game workspace.
4. The arena prompts the player's Pi session.
5. The agent calls `choose_action`.
6. The arena validates the selected action ID and applies the Catanatron action.

Observations should include:

- game ID, decision index, current phase, and current player color
- player color for the receiving agent
- public board state
- public player state such as public VP, road/army status, and visible counts
- private hand state for the receiving agent only
- public recent action history or replay references
- currently legal actions

Observations must not include:

- opponent resource card identities
- opponent development card identities
- deck order
- raw `player_state`
- raw `Game` or `State` objects

Initial implementation should use `catanatron.features.create_sample(game,
color)` as the redaction source of truth, then format that redacted sample into
JSON for model agents.

## Action Model

Use Catanatron's existing Gym action mapping:

- `get_action_array(player_colors, map_type)`
- `to_action_space(action, player_colors, map_type)`
- `from_action_space(action_id, color, player_colors, map_type)`

Each legal action exposed to the agent should include:

```json
{
  "id": 173,
  "type": "BUILD_ROAD",
  "value": [3, 7],
  "label": "Build road on edge 3-7"
}
```

The arena must validate that the selected ID maps to an action in
`game.playable_actions` before executing it.

## Pi Tool

Create a Pi extension exposing a single benchmark action tool:

```json
{
  "name": "choose_action",
  "description": "Choose exactly one legal Catan action for the current decision.",
  "parameters": {
    "type": "object",
    "properties": {
      "action_id": {"type": "integer"},
      "rationale": {"type": "string"}
    },
    "required": ["action_id"]
  }
}
```

The rationale is stored for debugging and replay inspection, but the engine only
uses `action_id`.

## Agent Workspace

Each seat gets a workspace like:

```text
/workspace/
  AGENTS.md
  memory.md
  observations/
    turn_000001.json
  outputs/
    turn_000001.json
  .pi/
    sessions/
```

The workspace persists across turns within one game. Official rankings should
not allow cross-game memory unless a separate league explicitly enables it.

## Docker Runtime

The Docker runtime should start one long-lived container per agent seat per
game.

Required constraints:

- per-game writable workspace mount only
- no Docker socket mount
- no host repo mount
- CPU limit
- memory limit
- disk/workspace limit where practical
- hard per-move timeout
- cleanup after each game

Network access is allowed for v1 so Pi can call model providers directly.
Provider API keys should be passed as environment variables.

## Replay And Results

Record enough data to make every benchmark auditable:

- engine version and git commit
- arena version and git commit
- agent configs and model IDs
- seed, map type, number placement, and seating
- per-decision observation file reference
- legal actions shown to the agent
- selected action ID
- selected Catanatron action
- model rationale from `choose_action`
- invalid action and timeout events
- final VP and winner
- turn count and latency metrics

Ranking should report:

- win rate
- average victory points
- placement distribution
- invalid action rate
- timeout rate
- average turns per game
- average decision latency
- confidence intervals or uncertainty estimates

## Phased Build

### Phase 1: Local Arena Core

- Add a separate arena package.
- Implement action JSON using Gym action IDs.
- Implement redacted decision-only observations using `create_sample`.
- Implement a local fake runtime with `random` and `first_action` agents.
- Implement replay recording.
- Add a smoke CLI:

```bash
catanatron-arena run --agents random,random,random,random --games 10 --out runs/smoke
catanatron-arena rank runs/smoke
```

### Phase 2: Docker Runtime

- Build per-game workspace creation.
- Start one long-lived Docker container per seat.
- Send decision-only prompts to each agent container.
- Enforce timeouts and cleanup.

### Phase 3: Pi Harness

- Build the Pi `choose_action` extension.
- Build the reusable Docker agent image.
- Add model/provider configuration.
- Store Pi session logs and selected actions.

### Phase 4: Model Benchmarking

- Add GPT and Claude agent configs.
- Add fixed seed suites and seat rotation.
- Add resumable runs.
- Add official scoring output.

### Phase 5: Replay Viewer

- Adapt existing Catanatron replay/UI pieces to load arena replay artifacts.
- Show board state, action history, selected action, and model rationale.

## First Implementation Scope

The first implementation should be API-free and Docker-free:

- `catanatron_arena.protocol.actions`
- `catanatron_arena.protocol.observation`
- `catanatron_arena.replay.recorder`
- `catanatron_arena.runner.match`
- `catanatron_arena.agents.local`
- `catanatron-arena run`
- `catanatron-arena rank`

This proves the protocol and replay format before adding Pi, Docker, or model
API cost.
