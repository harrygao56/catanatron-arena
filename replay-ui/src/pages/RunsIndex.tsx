import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { defaultSource } from "../sources/ReplaySource";
import type { RunSummary } from "../model/types";

export function RunsIndex() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    defaultSource
      .listRuns()
      .then(setRuns)
      .catch((e) => setError(String(e)));
  }, []);

  if (error)
    return (
      <div style={{ padding: 24 }}>
        <h2>Could not load runs</h2>
        <p>{error}</p>
        <p style={{ opacity: 0.7 }}>
          Did you run <code>python3 scripts/build_replay_index.py</code>?
        </p>
      </div>
    );
  if (!runs) return <div style={{ padding: 24 }}>Loading…</div>;
  return (
    <div style={{ padding: 24 }}>
      <h1>Catanatron Arena Replays</h1>
      <ul>
        {runs.map((r) => (
          <li key={r.run}>
            <Link to={`/r/${r.run}`}>{r.run}</Link>{" "}
            <span style={{ opacity: 0.7 }}>({r.num_games} games)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
