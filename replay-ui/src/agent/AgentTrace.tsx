import { useState } from "react";
import type { AgentEvent, AgentPayload, DecisionDetail } from "../model/types";

interface Props {
  decision: DecisionDetail | null;
  loading: boolean;
}

export function AgentTrace({ decision, loading }: Props) {
  if (loading)
    return <div style={{ padding: 12, opacity: 0.6 }}>Loading decision…</div>;
  if (!decision) return null;

  const agent = decision.agent ?? null;
  const isLLM = !!agent && (agent.agent_events || agent.prompt);

  return (
    <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 12 }}>
      <Header decision={decision} />
      {isLLM ? (
        <LLMTrace agent={agent!} />
      ) : (
        <div style={{ opacity: 0.6, fontSize: 13 }}>
          {decision.rationale ?? "Non-LLM agent (no trace)."}
        </div>
      )}
      <Collapsible title="Legal actions" defaultOpen={false}>
        <pre style={preStyle}>
          {JSON.stringify(decision.legal_actions ?? [], null, 2)}
        </pre>
      </Collapsible>
      <Collapsible title="Observation" defaultOpen={false}>
        <pre style={preStyle}>
          {JSON.stringify(decision.observation ?? {}, null, 2)}
        </pre>
      </Collapsible>
      {agent?.prompt != null && (
        <Collapsible title="Prompt" defaultOpen={false}>
          <pre style={preStyle}>{String(agent.prompt)}</pre>
        </Collapsible>
      )}
    </div>
  );
}

function Header({ decision }: { decision: DecisionDetail }) {
  return (
    <div style={{ fontSize: 13, lineHeight: 1.5 }}>
      <div>
        <strong>#{decision.decision_index}</strong> · {decision.seat_color} ·{" "}
        <code>{decision.current_prompt}</code>
      </div>
      <div style={{ opacity: 0.8 }}>
        chose <code>{decision.selected_action_label ?? "—"}</code>{" "}
        (id {decision.selected_action_id ?? "—"}) · {decision.latency_ms.toFixed(1)} ms ·{" "}
        status <code>{decision.status}</code>
      </div>
      {decision.error && (
        <div style={{ color: "#e07a5f" }}>error: {decision.error}</div>
      )}
    </div>
  );
}

function LLMTrace({ agent }: { agent: AgentPayload }) {
  const events = (agent.agent_events ?? []) as AgentEvent[];
  const choice = agent.choice ?? null;
  const thinking = collectThinking(events);
  const toolCalls = collectToolCalls(events);
  const finalText = collectFinalText(events);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {choice && (
        <Section title="Choice">
          <div>
            <code>action_id={choice.action_id}</code>
          </div>
          {choice.rationale && (
            <div style={{ marginTop: 4 }}>{choice.rationale}</div>
          )}
        </Section>
      )}
      {thinking.length > 0 && (
        <Section title={`Thinking (${thinking.length})`}>
          {thinking.map((t, i) => (
            <pre key={i} style={preStyle}>
              {t}
            </pre>
          ))}
        </Section>
      )}
      {finalText && (
        <Section title="Model output">
          <pre style={preStyle}>{finalText}</pre>
        </Section>
      )}
      {toolCalls.length > 0 && (
        <Section title={`Tool calls (${toolCalls.length})`}>
          {toolCalls.map((c, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <div>
                <strong>{c.name}</strong>
              </div>
              <pre style={preStyle}>{JSON.stringify(c.input, null, 2)}</pre>
              {c.result !== undefined && (
                <pre style={{ ...preStyle, background: "#e8ecf2" }}>
                  {typeof c.result === "string"
                    ? c.result
                    : JSON.stringify(c.result, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </Section>
      )}
      <Collapsible title={`Raw events (${events.length})`} defaultOpen={false}>
        <pre style={preStyle}>{JSON.stringify(events, null, 2)}</pre>
      </Collapsible>
    </div>
  );
}

function collectThinking(events: AgentEvent[]): string[] {
  const out: string[] = [];
  for (const e of events) {
    const content = e.message?.content;
    if (!Array.isArray(content)) continue;
    for (const c of content) {
      if (
        c &&
        typeof c === "object" &&
        (c as { type?: string }).type === "thinking"
      ) {
        const txt = (c as { thinking?: string }).thinking;
        if (txt) out.push(txt);
      }
    }
  }
  return dedupePrefixes(out);
}

function collectFinalText(events: AgentEvent[]): string | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const content = events[i].message?.content;
    if (!Array.isArray(content)) continue;
    if (events[i].message?.role !== "assistant") continue;
    const parts = content
      .filter((c) => c && typeof c === "object" && (c as { type?: string }).type === "text")
      .map((c) => (c as { text: string }).text);
    if (parts.length) return parts.join("\n");
  }
  return null;
}

interface ToolCall {
  id?: string;
  name: string;
  input: unknown;
  result?: unknown;
}

function collectToolCalls(events: AgentEvent[]): ToolCall[] {
  const calls = new Map<string, ToolCall>();
  for (const e of events) {
    const content = e.message?.content;
    if (!Array.isArray(content)) continue;
    for (const c of content) {
      if (!c || typeof c !== "object") continue;
      const obj = c as Record<string, unknown>;
      if (obj.type === "tool_use") {
        const id = (obj.id as string) ?? String(calls.size);
        if (!calls.has(id)) {
          calls.set(id, {
            id,
            name: (obj.name as string) ?? "tool",
            input: obj.input,
          });
        }
      } else if (obj.type === "tool_result") {
        const id = (obj.tool_use_id as string) ?? "";
        const existing = calls.get(id);
        if (existing) existing.result = obj.content;
      }
    }
  }
  return Array.from(calls.values());
}

function dedupePrefixes(items: string[]): string[] {
  // Streaming thinking events often emit growing prefixes of the same string.
  const out: string[] = [];
  for (const item of items) {
    if (out.length && item.startsWith(out[out.length - 1])) {
      out[out.length - 1] = item;
    } else {
      out.push(item);
    }
  }
  return out;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 11, opacity: 0.6, textTransform: "uppercase", marginBottom: 4 }}>
        {title}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Collapsible({
  title,
  children,
  defaultOpen,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  return (
    <div style={{ borderTop: "1px solid #e2e6ec", paddingTop: 6 }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: "none",
          color: "inherit",
          border: 0,
          padding: 0,
          cursor: "pointer",
          fontSize: 12,
          opacity: 0.7,
        }}
      >
        {open ? "▾" : "▸"} {title}
      </button>
      {open && <div style={{ marginTop: 6 }}>{children}</div>}
    </div>
  );
}

const preStyle: React.CSSProperties = {
  background: "#f1f3f7",
  color: "#1c2430",
  padding: 8,
  borderRadius: 4,
  fontSize: 12,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  maxHeight: 320,
  overflow: "auto",
  margin: 0,
};
