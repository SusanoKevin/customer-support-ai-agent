import { describe, expect, it, vi } from "vitest";
import { ASK_TOOL, answerToolCall } from "../tools";

describe("voice tool calls", () => {
  it("sends the customer's request to the chat agent and returns its reply without citations", async () => {
    const ask = vi.fn().mockResolvedValue("Pro plans can get up to $50 back [refunds:1:0].");
    const response = await answerToolCall({ id: "c1", name: ASK_TOOL, args: { message: "What is the Pro limit?" } }, ask);
    expect(ask).toHaveBeenCalledWith("What is the Pro limit?");
    expect(response).toEqual({ reply: "Pro plans can get up to $50 back." });
  });

  it("refuses unknown tools without calling the agent", async () => {
    const ask = vi.fn();
    const response = await answerToolCall({ id: "c1", name: "issue_refund", args: { amount: 500 } }, ask);
    expect(ask).not.toHaveBeenCalled();
    expect(response).toEqual({ error: "Unknown tool issue_refund" });
  });

  it("asks the customer to repeat when the message is missing or empty", async () => {
    const ask = vi.fn();
    const response = await answerToolCall({ id: "c1", name: ASK_TOOL, args: { message: "  " } }, ask);
    expect(ask).not.toHaveBeenCalled();
    expect(response).toHaveProperty("reply");
  });

  it("caps the message at the chat endpoint's 2000 character limit", async () => {
    const ask = vi.fn().mockResolvedValue("ok");
    await answerToolCall({ id: "c1", name: ASK_TOOL, args: { message: "x".repeat(2500) } }, ask);
    expect(ask.mock.calls[0][0]).toHaveLength(2000);
  });
});
