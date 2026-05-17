// Catanatron Arena Pi extension.
//
// Registers a single tool, `choose_action`, that the model agent calls once
// per decision to submit a chosen action back to the arena host.
//
// Per-decision protocol (host side writes these files into the workspace
// before each Pi prompt):
//   current_observation.json  player-view observation
//   legal_actions.json        list of {id, type, value, label}
//   current_decision.json     {decision_index, attempt, seat_color, output_path}
//
// The tool reads `current_decision.json` to learn the container-absolute
// `output_path` it should write to, then writes `{action_id, rationale}` to
// that path and signals `terminate: true` so the agent loop ends after this
// single tool call. The host then reads the output file, validates the
// `action_id` against the engine's legal actions, and applies the move.
//
// The workspace root inside the container is `/workspace` by default. Set
// the env var `CATANATRON_ARENA_WORKSPACE_ROOT` to override (e.g. when the
// host bind-mounts elsewhere).

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { readFile, writeFile } from "node:fs/promises";

const WORKSPACE_ROOT =
  process.env.CATANATRON_ARENA_WORKSPACE_ROOT ?? "/workspace";
const CURRENT_DECISION_FILE = `${WORKSPACE_ROOT}/current_decision.json`;

interface CurrentDecision {
  decision_index?: number;
  attempt?: number;
  seat_color?: string;
  output_path?: string;
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "choose_action",
    label: "Choose action",
    description:
      "Submit exactly one legal Catan action for the current decision. " +
      "`action_id` must be an integer that appears as `id` in " +
      "`legal_actions.json`. The arena validates the choice against the " +
      "engine's legal actions and applies it. On invalid action_id the " +
      "arena will re-prompt this session with a brief reason.",
    promptSnippet:
      "choose_action: submit one legal Catan action per decision (see AGENTS.md)",
    promptGuidelines: [
      "Call choose_action exactly once per decision after reading current_observation.json and legal_actions.json.",
      "choose_action's action_id must equal an id present in legal_actions.json.",
    ],
    parameters: Type.Object({
      action_id: Type.Integer({
        description:
          "An integer that matches an `id` in legal_actions.json for this decision.",
      }),
      rationale: Type.Optional(
        Type.String({
          description:
            "Short explanation of why this action was chosen. Stored in the replay for debugging.",
        }),
      ),
    }),

    async execute(_toolCallId, params) {
      let raw: string;
      try {
        raw = await readFile(CURRENT_DECISION_FILE, "utf8");
      } catch (err) {
        throw new Error(
          `choose_action: failed to read ${CURRENT_DECISION_FILE}: ${
            (err as Error).message
          }`,
        );
      }

      let decision: CurrentDecision;
      try {
        decision = JSON.parse(raw) as CurrentDecision;
      } catch (err) {
        throw new Error(
          `choose_action: ${CURRENT_DECISION_FILE} is not valid JSON: ${
            (err as Error).message
          }`,
        );
      }

      const outputPath = decision.output_path;
      if (typeof outputPath !== "string" || outputPath.length === 0) {
        throw new Error(
          `choose_action: ${CURRENT_DECISION_FILE} is missing 'output_path'`,
        );
      }

      const payload = JSON.stringify(
        {
          action_id: params.action_id,
          rationale: params.rationale ?? "",
        },
        null,
        2,
      );
      await writeFile(outputPath, payload, "utf8");

      return {
        content: [
          {
            type: "text",
            text:
              `Submitted choose_action(action_id=${params.action_id}). ` +
              `The arena will validate and apply this move; this decision is complete.`,
          },
        ],
        details: {
          output_path: outputPath,
          decision_index: decision.decision_index,
          attempt: decision.attempt,
          seat_color: decision.seat_color,
        },
        terminate: true,
      };
    },
  });
}
