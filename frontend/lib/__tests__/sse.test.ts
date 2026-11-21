import { describe, expect, it } from "vitest";
import { SseParser } from "../sse";

describe("SseParser", () => {
  it("parses CRLF frames split across chunks", () => {
    const parser = new SseParser();
    const first = parser.push('event: token\r\ndata: {"text":"Hel');
    const second = parser.push('lo"}\r\n\r\nevent: done\r\ndata: {"session_id":"s-1"}\r\n\r\n');
    expect(first).toEqual([]);
    expect(second).toEqual([
      { event: "token", data: { text: "Hello" } },
      { event: "done", data: { session_id: "s-1" } },
    ]);
  });

  it("ignores unknown event names and keep-alive comments", () => {
    const parser = new SseParser();
    const events = parser.push(': ping\n\nevent: surprise\ndata: {}\n\nevent: token\ndata: {"text":"ok"}\n\n');
    expect(events).toEqual([{ event: "token", data: { text: "ok" } }]);
  });

  it("drops frames whose data is not valid JSON", () => {
    const parser = new SseParser();
    expect(parser.push("event: token\ndata: not-json\n\n")).toEqual([]);
  });
});
