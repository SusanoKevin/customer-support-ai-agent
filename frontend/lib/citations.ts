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

/** Voice reads replies aloud, so chunk ids must go (the drawer and chat still show them). */
export function stripCitations(text: string): string {
  return text.replace(/\s*\[[a-z0-9_-]+:\d+:\d+\]/g, "").trim();
}
