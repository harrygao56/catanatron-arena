import type {
  Cube,
  EdgeEntry,
  GameState,
  NodeDirection,
  NodeEntry,
} from "../model/types";

export const HEX_SIZE = 48;

const SQRT3 = Math.sqrt(3);

// Pointy-top hex geometry. Catanatron uses cube coords (x, y, z) and axial
// (q = cube_x, r = cube_z) — see catanatron/models/coordinate_system.py.
export function tileCenter(cube: Cube, size = HEX_SIZE): [number, number] {
  const q = cube[0];
  const r = cube[2];
  const x = SQRT3 * size * (q + r / 2);
  const y = 1.5 * size * r;
  return [x, y];
}

const NODE_OFFSETS_UNIT: Record<NodeDirection, [number, number]> = {
  NORTH: [0, -1],
  NORTHEAST: [SQRT3 / 2, -0.5],
  SOUTHEAST: [SQRT3 / 2, 0.5],
  SOUTH: [0, 1],
  SOUTHWEST: [-SQRT3 / 2, 0.5],
  NORTHWEST: [-SQRT3 / 2, -0.5],
};

export function nodePosition(node: NodeEntry, size = HEX_SIZE): [number, number] {
  return cornerPosition(node.tile_coordinate, node.direction, size);
}

export function cornerPosition(
  cube: Cube,
  direction: NodeDirection,
  size = HEX_SIZE,
): [number, number] {
  const [cx, cy] = tileCenter(cube, size);
  const [ox, oy] = NODE_OFFSETS_UNIT[direction];
  return [cx + ox * size, cy + oy * size];
}

export function hexCorners(
  [q, r]: Cube,
  size = HEX_SIZE,
): Array<[number, number]> {
  const [cx, cy] = tileCenter([q, r, -q - r], size);
  return (Object.keys(NODE_OFFSETS_UNIT) as NodeDirection[]).map((dir) => {
    const [ox, oy] = NODE_OFFSETS_UNIT[dir];
    return [cx + ox * size, cy + oy * size];
  });
}

export function buildNodeIndex(state: GameState): Map<number, NodeEntry> {
  const map = new Map<number, NodeEntry>();
  for (const node of Object.values(state.nodes)) {
    map.set(node.id, node);
  }
  return map;
}

export function edgeEndpoints(
  edge: EdgeEntry,
  nodeIndex: Map<number, NodeEntry>,
  size = HEX_SIZE,
): [[number, number], [number, number]] | null {
  const a = nodeIndex.get(edge.id[0]);
  const b = nodeIndex.get(edge.id[1]);
  if (!a || !b) return null;
  return [nodePosition(a, size), nodePosition(b, size)];
}

export function bounds(state: GameState, size = HEX_SIZE) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const tile of state.tiles) {
    const corners = hexCorners(tile.coordinate, size);
    for (const [x, y] of corners) {
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
  }
  const pad = size * 0.6;
  return {
    x: minX - pad,
    y: minY - pad,
    width: maxX - minX + pad * 2,
    height: maxY - minY + pad * 2,
  };
}
