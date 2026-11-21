// Voice has one tool (backend/app/voice.py, log D29). Its answer comes from a normal chat turn on the same session.
import { stripCitations } from "../citations";
import type { ToolCall } from "./protocol";

export const ASK_TOOL = "ask_support_agent";
const MAX_MESSAGE = 2000; // ChatRequest.message max_length in backend/app/main.py
const NOTHING_HEARD = "I didn't catch the request. Ask the customer to say it again.";

/** Runs one chat turn and resolves with its reply text. Must not throw. */
export type AskAgent = (message: string) => Promise<string>;

export async function answerToolCall(call: ToolCall, ask: AskAgent): Promise<Record<string, unknown>> {
  if (call.name !== ASK_TOOL) return { error: `Unknown tool ${call.name}` };
  const message = typeof call.args.message === "string" ? call.args.message.trim().slice(0, MAX_MESSAGE) : "";
  if (!message) return { reply: NOTHING_HEARD };
  return { reply: stripCitations(await ask(message)) };
}
