import type { Color, GameState, Resource } from "../model/types";
import { COLOR_FILL, RESOURCE_FILL } from "../model/colors";

const RESOURCES: readonly Resource[] = [
  "WOOD",
  "BRICK",
  "SHEEP",
  "WHEAT",
  "ORE",
] as const;

const DEV_CARDS = [
  "KNIGHT",
  "VICTORY_POINT",
  "MONOPOLY",
  "ROAD_BUILDING",
  "YEAR_OF_PLENTY",
] as const;

const SETTLEMENTS_PER_PLAYER = 5;
const CITIES_PER_PLAYER = 4;

export function PlayerPanels({
  state,
  agentByColor,
}: {
  state: GameState;
  agentByColor?: Partial<Record<Color, string>>;
}) {
  const ps = state.player_state;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {state.colors.map((color, idx) => {
        const prefix = `P${idx}_`;
        const num = (k: string) => (ps[prefix + k] as number) ?? 0;
        const bool = (k: string) => ps[prefix + k] === true;
        const isCurrent = state.current_color === color;
        const vp = num("ACTUAL_VICTORY_POINTS");
        const vpCards = num("VICTORY_POINT_IN_HAND");
        const resourceCounts = RESOURCES.map(
          (r) => [r, num(`${r}_IN_HAND`)] as const,
        );
        const totalResources = resourceCounts.reduce((s, [, v]) => s + v, 0);
        const totalDev = DEV_CARDS.reduce(
          (s, d) => s + num(`${d}_IN_HAND`),
          0,
        );
        const settlementsBuilt =
          SETTLEMENTS_PER_PLAYER - num("SETTLEMENTS_AVAILABLE");
        const citiesBuilt = CITIES_PER_PLAYER - num("CITIES_AVAILABLE");
        return (
          <div
            key={color}
            style={{
              padding: 8,
              borderRadius: 6,
              background: isCurrent ? "#eef3fb" : "#ffffff",
              boxShadow: "0 1px 0 #e2e6ec",
              border: `2px solid ${isCurrent ? COLOR_FILL[color] : "transparent"}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: 3,
                  background: COLOR_FILL[color],
                  display: "inline-block",
                  border: "1px solid #000",
                }}
              />
              <strong>{color}</strong>
              <span style={{ opacity: 0.6, fontSize: 12 }}>
                {agentByColor?.[color] ?? ""}
              </span>
              {bool("HAS_ROAD") && (
                <Badge title="Longest road (+2 VP)" color="#9b6a3a">
                  🛣 LR
                </Badge>
              )}
              {bool("HAS_ARMY") && (
                <Badge title="Largest army (+2 VP)" color="#8a3838">
                  ⚔ LA
                </Badge>
              )}
              <span style={{ marginLeft: "auto", fontSize: 13 }}>
                VP {vp}
                {vpCards > 0 && (
                  <span style={{ opacity: 0.7, marginLeft: 4 }}>
                    (incl. {vpCards} VP card{vpCards > 1 ? "s" : ""})
                  </span>
                )}
              </span>
            </div>
            <div style={{ fontSize: 12, marginTop: 4, opacity: 0.85 }}>
              hand {totalResources} · dev {totalDev} · roads{" "}
              {num("LONGEST_ROAD_LENGTH")} · knights {num("PLAYED_KNIGHT")} ·{" "}
              settlements {settlementsBuilt} · cities {citiesBuilt}
            </div>
            <div
              style={{
                display: "flex",
                gap: 4,
                marginTop: 4,
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
              }}
            >
              {resourceCounts.map(([r, v]) => (
                <span key={r} title={r} style={resourcePill(r)}>
                  {v}
                </span>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Badge({
  children,
  color,
  title,
}: {
  children: React.ReactNode;
  color: string;
  title: string;
}) {
  return (
    <span
      title={title}
      style={{
        background: color,
        color: "#fff",
        fontSize: 10,
        fontWeight: 700,
        padding: "1px 5px",
        borderRadius: 3,
        letterSpacing: 0.3,
      }}
    >
      {children}
    </span>
  );
}

function resourcePill(resource: Resource): React.CSSProperties {
  return {
    background: RESOURCE_FILL[resource],
    color: "#111",
    padding: "1px 6px",
    borderRadius: 3,
    minWidth: 18,
    textAlign: "center",
    fontWeight: 600,
  };
}
