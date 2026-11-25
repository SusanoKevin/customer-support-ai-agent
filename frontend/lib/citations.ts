import type { ToolCall } from "./conversation";

// Answers cite policy chunks as [doc:section:window], the same format backend/app/agent/guardrails.py checks.
const CITATION = /\[([a-z0-9_-]+:\d+:\d+)\]/g;

export type Segment = { kind: "text"; value: string } | { kind: "cite"; value: string };

export function splitCitations(text: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const start = match.index ?? 0;
    if (start > last) segments.push({ kind: "text", value: text.slice(last, start) });
    segments.push({ kind: "cite", value: match[1] });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ kind: "text", value: text.slice(last) });
  return segments;
}

export interface Source { id: string; title: string; doc: string }

/** Cited policy sections in order of first mention, titled from the turn's retrieve_policy output. */
export function citedSources(text: string, tools: readonly ToolCall[]): Source[] {
  const headings = new Map<string, string>();
  for (const tool of tools) {
    const chunks = tool.name === "retrieve_policy" ? tool.output?.chunks : undefined;
    if (!Array.isArray(chunks)) continue;
    for (const c of chunks) {
      if (typeof c?.chunk_id === "string" && typeof c?.heading === "string") headings.set(c.chunk_id, c.heading);
    }
  }
  const ids = [...new Set(splitCitations(text).flatMap((s) => (s.kind === "cite" ? [s.value] : [])))];
  return ids.map((id) => {
    const doc = id.split(":")[0];
    return { id, doc, title: headings.get(id) ?? `${doc[0].toUpperCase()}${doc.slice(1)} policy` };
  });
}

/** Voice reads replies aloud, so chunk ids must go (the drawer and chat still show them). */
export function stripCitations(text: string): string {
  return text.replace(/\s*\[[a-z0-9_-]+:\d+:\d+\]/g, "").trim();
}
