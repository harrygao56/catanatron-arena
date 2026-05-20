export type Color = "RED" | "BLUE" | "ORANGE" | "WHITE";
export type Cube = [number, number, number];
export type EdgeId = [number, number];

export type Resource = "BRICK" | "WOOD" | "SHEEP" | "WHEAT" | "ORE";

export type EdgeDirection =
  | "NORTHEAST"
  | "EAST"
  | "SOUTHEAST"
  | "SOUTHWEST"
  | "WEST"
  | "NORTHWEST";

export type NodeDirection =
  | "NORTH"
  | "NORTHEAST"
  | "SOUTHEAST"
  | "SOUTH"
  | "SOUTHWEST"
  | "NORTHWEST";

export type TilePayload =
  | { id: number; type: "DESERT" }
  | { id: number; type: "WATER" }
  | { id: number; type: "RESOURCE_TILE"; resource: Resource; number: number }
  | {
      id: number;
      type: "PORT";
      direction: EdgeDirection;
      resource: Resource | null;
    };

export interface TileEntry {
  coordinate: Cube;
  tile: TilePayload;
}

export interface NodeEntry {
  id: number;
  tile_coordinate: Cube;
  direction: NodeDirection;
  building: "SETTLEMENT" | "CITY" | null;
  color: Color | null;
}

export interface EdgeEntry {
  id: EdgeId;
  tile_coordinate: Cube;
  direction: EdgeDirection;
  color: Color | null;
}

export interface GameState {
  tiles: TileEntry[];
  nodes: Record<string, NodeEntry>;
  edges: EdgeEntry[];
  robber_coordinate: Cube;
  current_color: Color | null;
  current_prompt: string;
  colors: Color[];
  player_state: Record<string, number | boolean>;
  longest_roads_by_player: Record<Color, number>;
  winning_color: Color | null;
  is_initial_build_phase: boolean;
  state_index: number;
}

export interface ActionPayload {
  color: Color;
  type: string;
  value: unknown;
}

export interface TimelineItem {
  decision_index: number;
  decision_ref: string;
  state_before_ref: string;
  state_after_ref: string | null;
  seat_color: Color;
  current_prompt: string;
  selected_action_id: number | null;
  selected_action_label: string | null;
  mapped_action: ActionPayload | null;
  action_record: { action: ActionPayload; result: unknown } | null;
  latency_ms: number;
  status: string;
  error: string | null;
  attempts?: unknown;
}

export interface Viewer {
  schema_version: number;
  replay_schema_version: number;
  game_id: string;
  seed: number;
  config: Record<string, unknown>;
  seating_order: Color[];
  initial_state_ref: string;
  final: {
    winner: Color | null;
    turns: number;
    num_decisions: number;
    victory_points: Record<Color, number>;
    failed?: boolean;
    failure_reason?: string;
  } | null;
  timeline: TimelineItem[];
}

export interface DecisionDetail extends TimelineItem {
  observation?: Record<string, unknown>;
  legal_actions?: Array<{
    id: number;
    type: string;
    value: unknown;
    label: string;
  }>;
  selected?: {
    action_id: number;
    label: string | null;
    rationale: string | null;
  };
  rationale?: string | null;
  agent?: AgentPayload | Record<string, AgentPayload> | null;
}

export interface AgentPayload {
  prompt?: string | null;
  choice?: { action_id: number; rationale?: string | null } | null;
  outcome?: { status: string; elapsed_seconds?: number; error?: string | null } | null;
  events?: AgentEvent[] | null;
  agent_events?: AgentEvent[] | null;
}

export interface AgentEvent {
  type: string;
  message?: {
    role?: string;
    content?: Array<
      | { type: "text"; text: string }
      | { type: "thinking"; thinking: string }
      | { type: "tool_use"; id?: string; name?: string; input?: unknown }
      | { type: "tool_result"; tool_use_id?: string; content?: unknown }
      | Record<string, unknown>
    >;
    model?: string;
    timestamp?: number;
    usage?: Record<string, unknown>;
  };
  [key: string]: unknown;
}

export interface RunSummary {
  run: string;
  num_games: number;
}

export interface GameSummary {
  game_id: string;
  winner: Color | null;
  turns: number;
  num_decisions: number;
  failed?: boolean;
  agents?: string[];
  agent_by_color?: Partial<Record<Color, string>>;
  victory_points?: Partial<Record<Color, number>>;
}
