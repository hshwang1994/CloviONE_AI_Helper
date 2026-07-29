import { describe, it, expect, vi, afterEach } from "vitest";
import {
  safeNotion,
  priorityKo,
  priorityKind,
  msgAgeMs,
  classifyLine,
  parseBlocks,
  pageNumberOrNull,
  bodyListStart,
  ticketPageStart,
  stripDuplicatedTicketLines,
  newClientMessageId,
} from "./Chat.jsx";

describe("safeNotion", () => {
  it("allows https www.notion.so", () => {
    expect(safeNotion("https://www.notion.so/some-page")).toBe(true);
  });
  it("allows bare https notion.so", () => {
    expect(safeNotion("https://notion.so/x")).toBe(true);
  });
  it("allows *.notion.site subdomains", () => {
    expect(safeNotion("https://myteam.notion.site/doc")).toBe(true);
  });
  it("rejects http:// (insecure scheme)", () => {
    expect(safeNotion("http://www.notion.so/x")).toBe(false);
  });
  it("rejects notion.so.evil.com (suffix spoof)", () => {
    expect(safeNotion("https://notion.so.evil.com/x")).toBe(false);
  });
  it("rejects evilnotion.so (prefix spoof)", () => {
    expect(safeNotion("https://evilnotion.so/x")).toBe(false);
  });
  it("rejects arbitrary external hosts", () => {
    expect(safeNotion("https://evil.com")).toBe(false);
  });
  it("rejects malformed / non-URL input", () => {
    expect(safeNotion("notion.so/x")).toBe(false);
    expect(safeNotion(null)).toBe(false);
  });
});

describe("priorityKo", () => {
  it("maps known English grades to Korean", () => {
    expect(priorityKo("urgent")).toBe("긴급");
    expect(priorityKo("HIGH")).toBe("높음");
    expect(priorityKo("medium")).toBe("보통");
  });
  it("maps numeric grades", () => {
    expect(priorityKo(1)).toBe("높음");
    expect(priorityKo("2")).toBe("보통");
    expect(priorityKo(3)).toBe("낮음");
  });
  it("humanizes unknown snake_case fallback", () => {
    expect(priorityKo("p1_urgent")).toBe("P1 Urgent");
  });
  it("passes through a plain unknown token unchanged", () => {
    expect(priorityKo("weird")).toBe("weird");
  });
});

describe("priorityKind", () => {
  it("returns the mapped kind for known grades", () => {
    expect(priorityKind("urgent")).toBe("danger");
    expect(priorityKind("high")).toBe("warn");
    expect(priorityKind("normal")).toBe("info");
  });
  it("maps numeric grades", () => {
    expect(priorityKind(2)).toBe("info");
  });
  it("returns undefined for unknown grades (Badge falls back to neutral)", () => {
    expect(priorityKind("p1_urgent")).toBeUndefined();
  });
});

describe("msgAgeMs", () => {
  afterEach(() => vi.restoreAllMocks());
  it("returns 0 for missing/invalid created_at", () => {
    expect(msgAgeMs(null)).toBe(0);
    expect(msgAgeMs({})).toBe(0);
    expect(msgAgeMs({ created_at: "not-a-date" })).toBe(0);
  });
  it("measures age from created_at when no sinceMs", () => {
    const t = Date.parse("2026-01-01T00:00:00Z");
    vi.spyOn(Date, "now").mockReturnValue(t + 100000);
    expect(msgAgeMs({ created_at: "2026-01-01T00:00:00Z" })).toBe(100000);
  });
  it("treats a tz-less timestamp as UTC (appends Z)", () => {
    const t = Date.parse("2026-01-01T00:00:00Z");
    vi.spyOn(Date, "now").mockReturnValue(t + 5000);
    expect(msgAgeMs({ created_at: "2026-01-01T00:00:00" })).toBe(5000);
  });
  it("uses max(created_at, sinceMs) as the baseline", () => {
    const t = Date.parse("2026-01-01T00:00:00Z");
    vi.spyOn(Date, "now").mockReturnValue(t + 100000);
    // sinceMs is later than created_at -> baseline is sinceMs
    expect(msgAgeMs({ created_at: "2026-01-01T00:00:00Z" }, t + 10000)).toBe(90000);
  });
});

describe("classifyLine", () => {
  it("classifies blanks", () => {
    expect(classifyLine("")).toEqual({ kind: "blank" });
    expect(classifyLine("   ")).toEqual({ kind: "blank" });
  });
  it("classifies a key: value line as kv", () => {
    expect(classifyLine("담당: 김")).toMatchObject({ kind: "kv", key: "담당", text: "김" });
  });
  it("classifies ordered list items", () => {
    expect(classifyLine("1. 첫째")).toEqual({ kind: "item", marker: "1.", text: "첫째" });
  });
  it("classifies unordered list items", () => {
    expect(classifyLine("- 항목")).toEqual({ kind: "item", marker: "", text: "항목" });
  });
  it("classifies bracket headings with a note", () => {
    expect(classifyLine("[제목] 부가")).toMatchObject({ kind: "head", text: "제목", note: "부가" });
  });
  it("classifies ■ bullet headings", () => {
    expect(classifyLine("■ 머리글")).toMatchObject({ kind: "head", text: "머리글", note: "" });
  });
  it("does not treat a time (09:00) as kv", () => {
    expect(classifyLine("09:00 미팅")).toMatchObject({ kind: "text" });
  });
  it("falls back to plain text", () => {
    expect(classifyLine("그냥 문장입니다")).toEqual({ kind: "text", text: "그냥 문장입니다" });
  });
});

describe("parseBlocks", () => {
  it("treats a single 'k: v' line as a paragraph, not a kv table", () => {
    const blocks = parseBlocks("내 티켓: 총 25건");
    expect(blocks).toEqual([{ kind: "para", lines: ["내 티켓: 총 25건"] }]);
  });
  it("treats 2+ 'k: v' lines as a kv block", () => {
    const blocks = parseBlocks("상태: 진행\n담당: 김");
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("kv");
    expect(blocks[0].rows).toHaveLength(2);
    expect(blocks[0].rows[0]).toMatchObject({ key: "상태", text: "진행" });
  });
  it("builds an ordered list and attaches indented sub-lines", () => {
    const blocks = parseBlocks("1. 첫째\n  세부 설명\n2. 둘째");
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("list");
    expect(blocks[0].items).toHaveLength(2);
    expect(blocks[0].items[0]).toMatchObject({ marker: "1.", text: "첫째", subs: ["세부 설명"] });
    expect(blocks[0].items[1]).toMatchObject({ marker: "2.", text: "둘째", subs: [] });
  });
  it("builds an unordered list", () => {
    const blocks = parseBlocks("- 하나\n- 둘");
    expect(blocks[0].kind).toBe("list");
    expect(blocks[0].items.map((i) => i.text)).toEqual(["하나", "둘"]);
  });
  it("emits a bracket heading block", () => {
    const blocks = parseBlocks("[요약]");
    expect(blocks).toEqual([{ kind: "head", text: "요약", note: "" }]);
  });
  it("emits a ■ heading block", () => {
    const blocks = parseBlocks("■ 개요");
    expect(blocks).toEqual([{ kind: "head", text: "개요", note: "" }]);
  });
});

describe("pageNumberOrNull", () => {
  it("accepts positive integers", () => {
    expect(pageNumberOrNull(1)).toBe(1);
    expect(pageNumberOrNull(7)).toBe(7);
  });
  it("rejects zero, negatives, non-integers, and non-numbers", () => {
    expect(pageNumberOrNull(0)).toBeNull();
    expect(pageNumberOrNull(-1)).toBeNull();
    expect(pageNumberOrNull(2.5)).toBeNull();
    expect(pageNumberOrNull("3")).toBeNull();
    expect(pageNumberOrNull(Infinity)).toBeNull();
  });
});

describe("bodyListStart", () => {
  it("returns the first numbered list marker in the body", () => {
    expect(bodyListStart("요약\n3. 티켓A\n4. 티켓B")).toBe(3);
  });
  it("returns null when there is no numbered list", () => {
    expect(bodyListStart("그냥 문단입니다")).toBeNull();
  });
});

describe("ticketPageStart", () => {
  it("returns null for non-object structured", () => {
    expect(ticketPageStart(null, "")).toBeNull();
    expect(ticketPageStart(undefined, "")).toBeNull();
  });
  it("uses start_index when the body has no list", () => {
    expect(ticketPageStart({ start_index: 3 }, "설명만 있음")).toBe(3);
  });
  it("returns the start when card number matches body list start", () => {
    expect(ticketPageStart({ start_index: 3 }, "3. 티켓A\n4. 티켓B")).toBe(3);
  });
  it("returns null when card number disagrees with body list start", () => {
    expect(ticketPageStart({ start_index: 3 }, "1. 티켓A")).toBeNull();
  });
  it("falls back to carried context.last_result_start", () => {
    expect(ticketPageStart({ context: { last_result_start: 5 } }, "설명만")).toBe(5);
  });
  it("returns null when neither claimed nor carried is valid", () => {
    expect(ticketPageStart({ start_index: 0 }, "설명만")).toBeNull();
  });
});

describe("stripDuplicatedTicketLines", () => {
  it("removes numbered item lines and their indented sub-lines, keeping prose", () => {
    const src = "요약입니다\n1. 티켓A\n  담당: 김\n2. 티켓B\n\n끝";
    expect(stripDuplicatedTicketLines(src)).toBe("요약입니다\n\n끝");
  });
  it("keeps content untouched when there are no item lines", () => {
    expect(stripDuplicatedTicketLines("안내 문장\n두 번째 줄")).toBe("안내 문장\n두 번째 줄");
  });
});

describe("newClientMessageId", () => {
  const RE = /^[A-Za-z0-9_-]{8,64}$/;
  it("uses crypto.randomUUID when available and it matches the id shape", () => {
    const orig = Object.getOwnPropertyDescriptor(window, "crypto");
    try {
      Object.defineProperty(window, "crypto", {
        configurable: true,
        value: { randomUUID: () => "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" },
      });
      const id = newClientMessageId();
      expect(id).toBe("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
      expect(id).toMatch(RE);
    } finally {
      if (orig) Object.defineProperty(window, "crypto", orig);
      else delete window.crypto;
    }
  });
  it("falls back to a random id that matches the id shape", () => {
    const orig = Object.getOwnPropertyDescriptor(window, "crypto");
    try {
      Object.defineProperty(window, "crypto", { configurable: true, value: undefined });
      const id = newClientMessageId();
      expect(id).toMatch(RE);
      expect(id.startsWith("m-")).toBe(true);
    } finally {
      if (orig) Object.defineProperty(window, "crypto", orig);
      else delete window.crypto;
    }
  });
});
