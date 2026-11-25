import { describe, expect, it } from "vitest";
import { citedSources, splitCitations, stripCitations } from "../citations";
import type { ToolCall } from "../conversation";

const retrieval: ToolCall = {
  name: "retrieve_policy",
  input: { query: "refund policy" },
  ok: true,
  output: {
    chunks: [
      { chunk_id: "refunds:0:0", doc: "refunds", heading: "Refund eligibility window", text: "..." },
      { chunk_id: "refunds:1:0", doc: "refunds", heading: "Refund limits by tier", text: "..." },
    ],
  },
};

describe("citedSources", () => {
  it("lists cited sections once, in order of first mention, with their headings", () => {
    const text = "Up to $50 [refunds:1:0]. Within 30 days [refunds:0:0]. Again [refunds:1:0].";
    expect(citedSources(text, [retrieval])).toEqual([
      { id: "refunds:1:0", title: "Refund limits by tier", doc: "refunds" },
      { id: "refunds:0:0", title: "Refund eligibility window", doc: "refunds" },
    ]);
  });

  it("falls back to the policy name when the retrieval is not on the message", () => {
    expect(citedSources("Text [troubleshooting:2:0].", [])).toEqual([
      { id: "troubleshooting:2:0", title: "Troubleshooting policy", doc: "troubleshooting" },
    ]);
  });

  it("returns nothing for text without citations", () => {
    expect(citedSources("No sources here.", [retrieval])).toEqual([]);
  });
});

describe("splitCitations", () => {
  it("separates chunk citations from text", () => {
    expect(splitCitations("Up to $50 [refunds:1:0]. Done.")).toEqual([
      { kind: "text", value: "Up to $50 " },
      { kind: "cite", value: "refunds:1:0" },
      { kind: "text", value: ". Done." },
    ]);
  });

  it("leaves ordinary brackets alone", () => {
    expect(splitCitations("See [this] and [a:b]")).toEqual([{ kind: "text", value: "See [this] and [a:b]" }]);
  });

  it("returns no segments for empty text", () => {
    expect(splitCitations("")).toEqual([]);
  });
});

describe("stripCitations", () => {
  it("removes chunk ids and the space before them, so voice never reads them aloud", () => {
    expect(stripCitations("Up to $50 [refunds:1:0]. Within 30 days [refunds:2:0] [refunds:3:1].")).toBe("Up to $50. Within 30 days.");
  });
});
