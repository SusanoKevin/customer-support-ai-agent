import { describe, expect, it } from "vitest";
import { applyEvent, initialConversation, sessionTotals, startTurn } from "../conversation";
import type { AgentEvent } from "../events";

function run(events: AgentEvent[], message = "Refund please") {
  return events.reduce(applyEvent, startTurn(initialConversation(), message));
}

const trace = (step: string, cost: number, tokensIn = 10, tokensOut = 5): AgentEvent => ({
  event: "trace",
  data: { step, latency_ms: 12.5, model: "gemini-3.8-flash", tokens_in: tokensIn, tokens_out: tokensOut, cost_usd: cost },
});

describe("conversation reducer", () => {
  it("adds the user message and an empty assistant message on send", () => {
    const state = startTurn(initialConversation(), "Hi");
    expect(state.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(state.busy).toBe(true);
  });

  it("does not mutate the previous state", () => {
    const before = startTurn(initialConversation(), "Hi");
    const after = applyEvent(before, { event: "token", data: { text: "Hello" } });
    expect(before.messages[1].text).toBe("");
    expect(after.messages[1].text).toBe("Hello");
  });

  it("tracks steps from started to completed or failed", () => {
    const state = run([
      { event: "status", data: { step: "classify_intent", state: "started", label: "Understanding..." } },
      { event: "status", data: { step: "classify_intent", state: "completed", label: "Understanding..." } },
      { event: "status", data: { step: "respond", state: "started", label: "Writing..." } },
      { event: "status", data: { step: "respond", state: "failed", label: "Writing..." } },
    ]);
    expect(state.messages[1].steps.map((s) => [s.step, s.state])).toEqual([
      ["classify_intent", "completed"],
      ["respond", "failed"],
    ]);
  });

  it("attaches tools, escalation and errors to the current assistant message", () => {
    const state = run([
      { event: "tool", data: { name: "verify_account", input: {}, output: { tier: "pro" }, ok: true } },
      { event: "escalation", data: { reason: "over_tier_limit", ticket_id: "T-1", priority: "normal" } },
      { event: "error", data: { code: "rate_limited", message: "Busy", retryable: true } },
    ]);
    const reply = state.messages[1];
    expect(reply.tools.map((t) => t.name)).toEqual(["verify_account"]);
    expect(reply.escalation?.ticket_id).toBe("T-1");
    expect(reply.error?.retryable).toBe(true);
  });

  it("groups trace rows by turn and totals them per session", () => {
    const first = run([trace("classify_intent", 0.0002), trace("respond", 0.003, 900, 120), { event: "done", data: { session_id: "s-1" } }]);
    const second = [trace("classify_intent", 0.0001)].reduce(applyEvent, startTurn(first, "Thanks"));
    expect(second.turns.map((t) => t.rows.length)).toEqual([2, 1]);
    expect(first.busy).toBe(false);
    const totals = sessionTotals(second);
    expect(totals.costUsd).toBeCloseTo(0.0033);
    expect(totals.tokensIn).toBe(920);
  });
});
