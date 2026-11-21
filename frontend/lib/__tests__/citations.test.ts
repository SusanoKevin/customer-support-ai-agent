import { describe, expect, it } from "vitest";
import { splitCitations } from "../citations";

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
