import { useEffect, useRef, useState } from "react";
import type { TimelineItem } from "../model/types";
import { COLOR_FILL } from "../model/colors";

interface Props {
  timeline: TimelineItem[];
  index: number;
  onChange: (next: number) => void;
}

export function ActionTimeline({ timeline, index, onChange }: Props) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const timer = useRef<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!playing) return;
    timer.current = window.setInterval(() => {
      onChange(Math.min(index + 1, timeline.length - 1));
    }, 1000 / speed);
    return () => {
      if (timer.current != null) window.clearInterval(timer.current);
    };
  }, [playing, speed, index, timeline.length, onChange]);

  useEffect(() => {
    if (index >= timeline.length - 1) setPlaying(false);
  }, [index, timeline.length]);

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-i="${index}"]`);
    if (el && "scrollIntoView" in el) {
      (el as HTMLElement).scrollIntoView({ block: "nearest" });
    }
  }, [index]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", padding: 8 }}>
        <button onClick={() => onChange(0)}>⏮</button>
        <button onClick={() => onChange(Math.max(0, index - 1))}>◀</button>
        <button onClick={() => setPlaying((p) => !p)}>
          {playing ? "⏸" : "▶"}
        </button>
        <button
          onClick={() => onChange(Math.min(timeline.length - 1, index + 1))}
        >
          ▶
        </button>
        <button onClick={() => onChange(timeline.length - 1)}>⏭</button>
        <select
          value={speed}
          onChange={(e) => setSpeed(Number(e.target.value))}
          style={{ marginLeft: 8 }}
        >
          <option value={1}>1×</option>
          <option value={2}>2×</option>
          <option value={4}>4×</option>
          <option value={8}>8×</option>
          <option value={16}>16×</option>
        </select>
        <span style={{ marginLeft: "auto", fontSize: 12, opacity: 0.7 }}>
          {index + 1} / {timeline.length}
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={timeline.length - 1}
        value={index}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ margin: "0 8px" }}
      />
      <div
        ref={listRef}
        style={{
          flex: 1,
          overflowY: "auto",
          fontSize: 12,
          fontFamily: "ui-monospace, monospace",
          marginTop: 8,
        }}
      >
        {timeline.map((t, i) => (
          <div
            key={i}
            data-i={i}
            onClick={() => onChange(i)}
            style={{
              padding: "4px 8px",
              cursor: "pointer",
              background: i === index ? "#eef3fb" : "transparent",
              borderLeft: `3px solid ${COLOR_FILL[t.seat_color]}`,
              opacity: t.status === "ok" ? 1 : 0.7,
            }}
          >
            <span style={{ opacity: 0.5, marginRight: 8 }}>#{t.decision_index}</span>
            <span>{t.seat_color}</span>
            <span style={{ marginLeft: 6, opacity: 0.8 }}>
              {t.selected_action_label ?? t.mapped_action?.type ?? t.current_prompt}
            </span>
            {t.status !== "ok" && (
              <span style={{ color: "#e07a5f", marginLeft: 6 }}>
                [{t.status}]
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
