// SSE event contract. Mirror of backend/app/events.py; change both together.

export type StepState = "started" | "completed" | "failed";
export type Priority = "low" | "normal" | "high";

export type AgentEvent =
  | { event: "status"; data: { step: string; state: StepState; label: string } }
  | { event: "token"; data: { text: string } }
  | { event: "tool"; data: { name: string; input: Record<string, unknown>; output: Record<string, unknown> | null; ok: boolean } }
  | { event: "escalation"; data: { reason: string; ticket_id: string | null; priority: Priority | null } }
  | { event: "trace"; data: { step: string; latency_ms: number; tokens_in: number; tokens_out: number; cost_usd: number } }
  | { event: "error"; data: { code: string; message: string; retryable: boolean } }
  | { event: "done"; data: { session_id: string } };
