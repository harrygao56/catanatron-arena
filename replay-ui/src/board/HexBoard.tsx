import type {
  EdgeDirection,
  EdgeEntry,
  GameState,
  NodeDirection,
  NodeEntry,
  TileEntry,
} from "../model/types";
import {
  COLOR_FILL,
  COLOR_STROKE,
  DESERT_FILL,
  GENERIC_PORT_FILL,
  RESOURCE_FILL,
  WATER_FILL,
} from "../model/colors";
import {
  HEX_SIZE,
  bounds,
  buildNodeIndex,
  cornerPosition,
  edgeEndpoints,
  hexCorners,
  nodePosition,
  tileCenter,
} from "./hex";

// Each tile edge connects two corners. EAST edge of a pointy-top hex runs
// between its NORTHEAST and SOUTHEAST vertices, etc.
const EDGE_TO_CORNERS: Record<EdgeDirection, [NodeDirection, NodeDirection]> = {
  EAST: ["NORTHEAST", "SOUTHEAST"],
  WEST: ["NORTHWEST", "SOUTHWEST"],
  NORTHEAST: ["NORTH", "NORTHEAST"],
  SOUTHEAST: ["SOUTHEAST", "SOUTH"],
  SOUTHWEST: ["SOUTH", "SOUTHWEST"],
  NORTHWEST: ["NORTHWEST", "NORTH"],
};

const PORT_DOCK_COLOR = "#bfc4ca";

function tileFill(tile: TileEntry["tile"]): string {
  switch (tile.type) {
    case "RESOURCE_TILE":
      return RESOURCE_FILL[tile.resource];
    case "DESERT":
      return DESERT_FILL;
    case "PORT":
    case "WATER":
      return WATER_FILL;
  }
}

function numberPipColor(n: number): string {
  return n === 6 || n === 8 ? "#a31515" : "#1c1c1c";
}

export interface HexBoardProps {
  state: GameState;
  highlightAction?: { type: string; value: unknown } | null;
  highlightNumber?: number | null;
}

export function HexBoard({
  state,
  highlightAction,
  highlightNumber,
}: HexBoardProps) {
  const size = HEX_SIZE;
  const nodeIndex = buildNodeIndex(state);
  const box = bounds(state, size);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <Legend />
      <svg
        viewBox={`${box.x} ${box.y} ${box.width} ${box.height}`}
        style={{
          width: "100%",
          height: "100%",
          background: "#eef3f8",
          borderRadius: 8,
        }}
      >
        <g>
          {state.tiles.map((tile, i) => (
            <Tile
              key={i}
              tile={tile}
              size={size}
              highlight={
                tile.tile.type === "RESOURCE_TILE" &&
                highlightNumber != null &&
                tile.tile.number === highlightNumber
              }
            />
          ))}
        </g>
        <g>
          {state.tiles.map((t, i) =>
            t.tile.type === "PORT" ? <Port key={i} tile={t} size={size} /> : null,
          )}
        </g>
        <g>
          {state.edges.map((edge, i) => (
            <RoadEdge
              key={i}
              edge={edge}
              nodeIndex={nodeIndex}
              size={size}
              highlight={isEdgeHighlighted(edge, highlightAction)}
            />
          ))}
        </g>
        <g>
          {Object.values(state.nodes).map((node) => (
            <BuildingNode
              key={node.id}
              node={node}
              size={size}
              highlight={isNodeHighlighted(node, highlightAction)}
            />
          ))}
        </g>
        <Robber coord={state.robber_coordinate} size={size} />
      </svg>
    </div>
  );
}

function Legend() {
  const items: Array<[string, string]> = [
    ["Wood", RESOURCE_FILL.WOOD],
    ["Brick", RESOURCE_FILL.BRICK],
    ["Sheep", RESOURCE_FILL.SHEEP],
    ["Wheat", RESOURCE_FILL.WHEAT],
    ["Ore", RESOURCE_FILL.ORE],
    ["Desert", DESERT_FILL],
    ["3:1 port", GENERIC_PORT_FILL],
  ];
  return (
    <div
      style={{
        position: "absolute",
        top: 8,
        left: 8,
        background: "rgba(255, 255, 255, 0.92)",
        border: "1px solid #e2e6ec",
        color: "#1c2430",
        borderRadius: 6,
        padding: "6px 8px",
        fontSize: 11,
        display: "grid",
        gridTemplateColumns: "auto auto",
        columnGap: 8,
        rowGap: 3,
        zIndex: 1,
        pointerEvents: "none",
      }}
    >
      {items.map(([label, color]) => (
        <span key={label} style={{ display: "contents" }}>
          <span
            style={{
              width: 12,
              height: 12,
              background: color,
              border: "1px solid #2c3641",
              borderRadius: 2,
              alignSelf: "center",
              justifySelf: "start",
            }}
          />
          <span style={{ opacity: 0.9 }}>{label}</span>
        </span>
      ))}
    </div>
  );
}

function Tile({
  tile,
  size,
  highlight,
}: {
  tile: TileEntry;
  size: number;
  highlight: boolean;
}) {
  const corners = hexCorners(tile.coordinate, size);
  const path = corners.map(([x, y]) => `${x},${y}`).join(" ");
  const [cx, cy] = tileCenter(tile.coordinate, size);
  const payload = tile.tile;
  return (
    <g>
      <polygon
        points={path}
        fill={tileFill(payload)}
        stroke="#2c3641"
        strokeWidth={1}
      />
      {payload.type === "RESOURCE_TILE" && (
        <>
          <circle
            cx={cx}
            cy={cy}
            r={size * 0.32}
            fill={highlight ? "#ffe66d" : "#f3e8c8"}
            stroke={highlight ? "#a37a00" : "#2c3641"}
            strokeWidth={highlight ? 2 : 1}
          />
          <text
            x={cx}
            y={cy + 5}
            textAnchor="middle"
            fontSize={size * 0.42}
            fontWeight={700}
            fill={numberPipColor(payload.number)}
          >
            {payload.number}
          </text>
        </>
      )}
    </g>
  );
}

function Port({ tile, size }: { tile: TileEntry; size: number }) {
  if (tile.tile.type !== "PORT") return null;
  const { coordinate } = tile;
  const { direction, resource } = tile.tile;

  const [cx, cy] = tileCenter(coordinate, size);
  const [c1, c2] = EDGE_TO_CORNERS[direction].map((d) =>
    cornerPosition(coordinate, d, size),
  );

  const fill = resource ? RESOURCE_FILL[resource] : GENERIC_PORT_FILL;
  const ratio = resource ? "2:1" : "3:1";

  return (
    <g>
      <line
        x1={cx}
        y1={cy}
        x2={c1[0]}
        y2={c1[1]}
        stroke={PORT_DOCK_COLOR}
        strokeWidth={size * 0.09}
        strokeLinecap="round"
      />
      <line
        x1={cx}
        y1={cy}
        x2={c2[0]}
        y2={c2[1]}
        stroke={PORT_DOCK_COLOR}
        strokeWidth={size * 0.09}
        strokeLinecap="round"
      />
      <circle
        cx={cx}
        cy={cy}
        r={size * 0.3}
        fill={fill}
        stroke="#1f2933"
        strokeWidth={1.5}
      />
      <text
        x={cx}
        y={cy + size * 0.11}
        textAnchor="middle"
        fontSize={size * 0.28}
        fontWeight={700}
        fill="#1f2933"
      >
        {ratio}
      </text>
    </g>
  );
}

function BuildingNode({
  node,
  size,
  highlight,
}: {
  node: NodeEntry;
  size: number;
  highlight: boolean;
}) {
  const [x, y] = nodePosition(node, size);
  if (!node.building) {
    return highlight ? (
      <circle cx={x} cy={y} r={size * 0.15} fill="#ffe66d" opacity={0.7} />
    ) : null;
  }
  const fill = node.color ? COLOR_FILL[node.color] : "#888";
  const stroke = node.color ? COLOR_STROKE[node.color] : "#222";
  if (node.building === "SETTLEMENT") {
    const r = size * 0.22;
    return (
      <polygon
        points={`${x},${y - r} ${x + r},${y - r * 0.2} ${x + r},${y + r * 0.7} ${x - r},${y + r * 0.7} ${x - r},${y - r * 0.2}`}
        fill={fill}
        stroke={stroke}
        strokeWidth={2}
      />
    );
  }
  const r = size * 0.28;
  return (
    <rect
      x={x - r}
      y={y - r}
      width={r * 2}
      height={r * 1.7}
      rx={3}
      fill={fill}
      stroke={stroke}
      strokeWidth={2}
    />
  );
}

function RoadEdge({
  edge,
  nodeIndex,
  size,
  highlight,
}: {
  edge: EdgeEntry;
  nodeIndex: Map<number, NodeEntry>;
  size: number;
  highlight: boolean;
}) {
  const ends = edgeEndpoints(edge, nodeIndex, size);
  if (!ends) return null;
  const [[x1, y1], [x2, y2]] = ends;
  if (!edge.color && !highlight) return null;
  const stroke = edge.color ? COLOR_FILL[edge.color] : "#ffe66d";
  return (
    <line
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke={stroke}
      strokeWidth={size * 0.18}
      strokeLinecap="round"
      opacity={highlight && !edge.color ? 0.6 : 1}
    />
  );
}

function Robber({ coord, size }: { coord: GameState["robber_coordinate"]; size: number }) {
  const [cx, cy] = tileCenter(coord, size);
  // Offset above the tile's number token so the dice number stays readable.
  const ox = cx + size * 0.3;
  const oy = cy - size * 0.4;
  return (
    <g>
      <circle
        cx={ox}
        cy={oy + size * 0.05}
        r={size * 0.18}
        fill="#1c1c1c"
        stroke="#f3e8c8"
        strokeWidth={1.5}
      />
      <circle
        cx={ox}
        cy={oy - size * 0.15}
        r={size * 0.1}
        fill="#1c1c1c"
        stroke="#f3e8c8"
        strokeWidth={1.5}
      />
    </g>
  );
}

function isNodeHighlighted(
  node: NodeEntry,
  action: HexBoardProps["highlightAction"],
): boolean {
  if (!action) return false;
  if (
    action.type === "BUILD_SETTLEMENT" ||
    action.type === "BUILD_INITIAL_SETTLEMENT" ||
    action.type === "BUILD_CITY"
  ) {
    return action.value === node.id;
  }
  return false;
}

function isEdgeHighlighted(
  edge: EdgeEntry,
  action: HexBoardProps["highlightAction"],
): boolean {
  if (!action) return false;
  if (action.type === "BUILD_ROAD" || action.type === "BUILD_INITIAL_ROAD") {
    const v = action.value as [number, number] | undefined;
    if (!Array.isArray(v) || v.length !== 2) return false;
    const [a, b] = edge.id;
    return (a === v[0] && b === v[1]) || (a === v[1] && b === v[0]);
  }
  return false;
}
