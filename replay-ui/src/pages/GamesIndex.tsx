import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { defaultSource } from "../sources/ReplaySource";
import type { GameSummary } from "../model/types";

export function GamesIndex() {
  const { run } = useParams();
  const [games, setGames] = useState<GameSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!run) return;
    defaultSource
      .listGames(run)
      .then(setGames)
      .catch((e) => setError(String(e)));
  }, [run]);

  if (error) return <div style={{ padding: 24 }}>Error: {error}</div>;
  if (!games) return <div style={{ padding: 24 }}>Loading…</div>;
  return (
    <div style={{ padding: 24 }}>
      <p>
        <Link to="/">← runs</Link>
      </p>
      <h2>{run}</h2>
      <table cellPadding={6} style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", opacity: 0.7 }}>
            <th>game</th>
            <th>winner</th>
            <th>turns</th>
            <th>decisions</th>
            <th>agents</th>
          </tr>
        </thead>
        <tbody>
          {games.map((g) => (
            <tr key={g.game_id} style={{ borderTop: "1px solid #e2e6ec" }}>
              <td>
                <Link to={`/r/${run}/g/${g.game_id}`}>{g.game_id.slice(0, 8)}</Link>
                {g.failed && <span style={{ color: "#e07a5f" }}> failed</span>}
              </td>
              <td>{g.winner ?? "—"}</td>
              <td>{g.turns ?? "—"}</td>
              <td>{g.num_decisions ?? "—"}</td>
              <td style={{ fontSize: 12 }}>
                {g.agent_by_color
                  ? Object.entries(g.agent_by_color)
                      .map(([c, a]) => `${c}:${a}`)
                      .join(" ")
                  : (g.agents ?? []).join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
