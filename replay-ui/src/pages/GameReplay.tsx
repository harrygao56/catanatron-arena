import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { defaultSource } from "../sources/ReplaySource";
import type {
  Color,
  DecisionDetail,
  GameState,
  Viewer,
} from "../model/types";
import { HexBoard } from "../board/HexBoard";
import { PlayerPanels } from "../board/PlayerPanels";
import { ActionTimeline } from "../timeline/ActionTimeline";
import { AgentTrace } from "../agent/AgentTrace";

function findLastRoll(
  viewer: Viewer | null,
  index: number,
): { dice: [number, number]; total: number; fresh: boolean } | null {
  if (!viewer) return null;
  for (let i = index; i >= 0; i--) {
    const item = viewer.timeline[i];
    if (item?.mapped_action?.type !== "ROLL") continue;
    // ROLL's mapped_action.value is null (you don't choose dice). The actual
    // rolled values live on action_record.action.value or action_record.result.
    const recorded = item.action_record?.action?.value;
    const result = (item.action_record as { result?: unknown } | null)?.result;
    const v = (Array.isArray(recorded) ? recorded : result) as
      | [number, number]
      | undefined;
    if (Array.isArray(v) && v.length === 2) {
      return { dice: v, total: v[0] + v[1], fresh: i === index };
    }
  }
  return null;
}

export function GameReplay() {
  const { run, gameId } = useParams();
  const [viewer, setViewer] = useState<Viewer | null>(null);
  const [index, setIndex] = useState(0);
  const [state, setState] = useState<GameState | null>(null);
  const [decision, setDecision] = useState<DecisionDetail | null>(null);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [stateCache] = useState<Map<string, GameState>>(() => new Map());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!run || !gameId) return;
    defaultSource
      .loadViewer(run, gameId)
      .then(setViewer)
      .catch((e) => setError(String(e)));
  }, [run, gameId]);

  const currentItem = viewer?.timeline[index] ?? null;
  const stateRef =
    currentItem?.state_after_ref ??
    currentItem?.state_before_ref ??
    viewer?.initial_state_ref ??
    null;

  useEffect(() => {
    if (!run || !gameId || !stateRef) return;
    const cached = stateCache.get(stateRef);
    if (cached) {
      setState(cached);
      return;
    }
    let cancelled = false;
    defaultSource.loadState(run, gameId, stateRef).then((s) => {
      if (cancelled) return;
      stateCache.set(stateRef, s);
      setState(s);
    });
    return () => {
      cancelled = true;
    };
  }, [run, gameId, stateRef, stateCache]);

  useEffect(() => {
    if (!run || !gameId || !currentItem) {
      setDecision(null);
      return;
    }
    setDecisionLoading(true);
    let cancelled = false;
    defaultSource
      .loadDecision(run, gameId, currentItem.decision_ref)
      .then((d) => {
        if (!cancelled) setDecision(d);
      })
      .catch(() => {
        if (!cancelled) setDecision(null);
      })
      .finally(() => {
        if (!cancelled) setDecisionLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [run, gameId, currentItem]);

  const agentByColor =
    ((viewer?.config as { agent_by_color?: Record<string, string> } | undefined)
      ?.agent_by_color as Partial<Record<Color, string>> | undefined) ?? {};

  const highlight = currentItem?.mapped_action
    ? {
        type: currentItem.mapped_action.type,
        value: currentItem.mapped_action.value,
      }
    : null;

  const lastRoll = useMemo(() => findLastRoll(viewer, index), [viewer, index]);

  if (error) return <div style={{ padding: 24 }}>Error: {error}</div>;
  if (!viewer) return <div style={{ padding: 24 }}>Loading…</div>;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 340px 420px",
        gridTemplateRows: "auto 1fr",
        height: "100vh",
        gap: 8,
        padding: 8,
        boxSizing: "border-box",
      }}
    >
      <div style={{ gridColumn: "1 / -1", display: "flex", gap: 12, alignItems: "baseline" }}>
        <Link to={`/r/${run}`}>← {run}</Link>
        <h2 style={{ margin: 0, fontSize: 16 }}>{gameId}</h2>
        <span style={{ opacity: 0.7, fontSize: 12 }}>
          seed {viewer.seed} · {viewer.timeline.length} decisions ·{" "}
          winner {viewer.final?.winner ?? "—"}
        </span>
      </div>

      <div style={{ minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ flex: 1, minHeight: 0 }}>
          {state ? (
            <HexBoard
              state={state}
              highlightAction={highlight}
              highlightNumber={lastRoll?.fresh ? lastRoll.total : null}
            />
          ) : (
            <div style={{ opacity: 0.6, padding: 24 }}>Loading state…</div>
          )}
        </div>
        {currentItem && (
          <div
            style={{
              fontSize: 13,
              padding: 8,
              background: "#ffffff",
              border: "1px solid #e2e6ec",
              borderRadius: 6,
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <div style={{ flex: 1 }}>
              <strong>{currentItem.seat_color}</strong>{" "}
              <code>{currentItem.current_prompt}</code> →{" "}
              <strong>{currentItem.selected_action_label}</strong>
            </div>
            {lastRoll && (
              <div
                style={{
                  background: "#f1f3f7",
                  border: "1px solid #e2e6ec",
                  padding: "4px 10px",
                  borderRadius: 4,
                  fontFamily: "ui-monospace, monospace",
                }}
                title={
                  lastRoll.fresh
                    ? "Roll on this decision"
                    : "Most recent roll up to this point"
                }
              >
                🎲 {lastRoll.dice[0]} + {lastRoll.dice[1]} ={" "}
                <strong>{lastRoll.total}</strong>
                {!lastRoll.fresh && (
                  <span style={{ opacity: 0.5 }}> (prev)</span>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div
        style={{
          background: "#ffffff",
          border: "1px solid #e2e6ec",
          borderRadius: 6,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
        {state && <PlayerPanels state={state} agentByColor={agentByColor} />}
        <div style={{ flex: 1, minHeight: 0 }}>
          <ActionTimeline
            timeline={viewer.timeline}
            index={index}
            onChange={setIndex}
          />
        </div>
      </div>

      <div
        style={{
          background: "#ffffff",
          border: "1px solid #e2e6ec",
          borderRadius: 6,
          overflowY: "auto",
          minHeight: 0,
        }}
      >
        <AgentTrace decision={decision} loading={decisionLoading} />
      </div>
    </div>
  );
}
