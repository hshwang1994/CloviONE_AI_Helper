/* qa-contract-change: 옛 실행기 시절의 카드 번호 · 본문 목록 걷기 · 응답 시간(timing) 헬퍼를 걷었다 — 서버가 그 구조를 더는 싣지 않아 화면에서 닿을 수 없는 코드였다(D-535). 그 자리의 시험은 도우미 답의 구조(걸린 시간 · 확인한 내용 · 찾아본 검색어)와 시작 예시가 할 수 있는 일만 약속하는지를 잰다. 우선순위 어휘 시험은 정의가 있는 lib/priority.js 에서 그대로 가져와 지킨다. */
import { describe, it, expect, vi, afterEach } from "vitest";
import * as helpers from "./chat-helpers.js";
import { priorityKo, priorityKind } from "../lib/priority.js";
import {
  msgAgeMs,
  elapsedLabel,
  checkedTools,
  searchedWords,
  QUICK_PROMPTS,
  classifyLine,
  parseBlocks,
  newClientMessageId,
} from "./chat-helpers.js";

/* 예전에는 이 자리에 `safeNotion` 의 허용 호스트 시험 여덟 개가 있었다: notion.so 계열은
   진짜 앵커로 열고 나머지(스킴 위조·접미 위조·접두 위조·임의 호스트)는 거절한다.

   그 게이트가 없어졌다. 문서와 티켓의 정본이 이 서버로 넘어왔으므로 notion.so 주소가 여는
   것은 우리가 더 이상 쓰지 않는 낡은 사본이고, 그 한 호스트만 「믿을 수 있다」고 대우할
   이유가 없다. 지금은 **어떤 외부 주소도 앵커가 아니다** - 열 수 있는 곳이 줄어드는
   방향이라 위 여덟 갈래가 지키던 성질보다 강하다. 게이트를 되살리면 이 시험이 빨개진다. */
describe("외부 주소 허용 목록이 없다", () => {
  it("허용 호스트 게이트와 그 목록이 모듈에서 사라졌다", () => {
    expect(helpers.safeNotion).toBeUndefined();
    expect(helpers.NOTION_HOSTS).toBeUndefined();
  });
  it("옛 카드 정규화 함수가 모듈에 없다 - 화면이 바깥 링크 갈래를 다시 기다리지 않는다", () => {
    expect(helpers.structuredCards).toBeUndefined();
    expect(helpers.ticketPageStart).toBeUndefined();
    expect(helpers.responseTimeLabel).toBeUndefined();
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
    expect(priorityKind("낮음")).toBe("teal");
  });
  it("등급 넷은 서로 다른 색이다", () => {
    const kinds = ["긴급", "높음", "보통", "낮음"].map(priorityKind);
    expect(new Set(kinds).size).toBe(4);
    expect(kinds).not.toContain("neutral");
  });
  it("maps numeric grades", () => {
    expect(priorityKind(2)).toBe("info");
    expect(priorityKind(3)).toBe("teal");
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

describe("elapsedLabel (D-535)", () => {
  it("서버가 잰 한 차례의 시간을 초로 보인다", () => {
    expect(elapsedLabel({ elapsed_ms: 3200 })).toBe("3.2초");
    expect(elapsedLabel({ elapsed_ms: 0 })).toBe("0.0초");
  });
  it("값이 없거나 숫자가 아니거나 음수면 아무것도 보이지 않는다", () => {
    expect(elapsedLabel({})).toBeNull();
    expect(elapsedLabel(null)).toBeNull();
    expect(elapsedLabel({ elapsed_ms: "812" })).toBeNull();
    expect(elapsedLabel({ elapsed_ms: -5 })).toBeNull();
  });
  it("옛 실행기의 timing 칸은 읽지 않는다", () => {
    expect(elapsedLabel({ timing: { total_ms: 3200 } })).toBeNull();
  });
});

describe("checkedTools · searchedWords (D-535)", () => {
  const st = { tools: [
    { name: "search_documents", label: "사내 문서 검색", ok: true, count: 0, query: "연차" },
    { name: "my_work", label: "내 업무", ok: true, count: 2 },
    { name: "search_workspace", label: "통합 검색", ok: true, count: 0, query: "연차" },
    { name: "broken" },
  ] };
  it("화면 이름이 있는 도구만 「확인한 내용」에 남긴다", () => {
    expect(checkedTools(st).map((t) => t.label)).toEqual(["사내 문서 검색", "내 업무", "통합 검색"]);
    expect(checkedTools(null)).toEqual([]);
  });
  it("찾아본 검색어는 중복 없이 순서대로다", () => {
    expect(searchedWords(st)).toEqual(["연차"]);
    expect(searchedWords({})).toEqual([]);
  });
});

describe("QUICK_PROMPTS", () => {
  it("시작 예시는 도우미가 실제로 할 수 있는 일만 약속한다(읽기만 한다)", () => {
    expect(QUICK_PROMPTS).toHaveLength(6);
    for (const prompt of QUICK_PROMPTS) {
      expect(prompt).not.toMatch(/만들어|생성|등록|삭제|바꿔/);
    }
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
  it("does not treat a time with a prefix (오전 9:30) as kv either (step 10 #3)", () => {
    // 예전엔 키가 순수 숫자일 때만 막아서("09:00") 시 앞에 다른 말이 붙으면
    // ("오전 9:30에 회의") 정의목록(dl) 2줄로 잘못 렌더됐다.
    expect(classifyLine("오전 9:30에 회의")).toMatchObject({ kind: "text" });
    expect(classifyLine("오후 11:05 마감")).toMatchObject({ kind: "text" });
  });
  it("still treats a genuine numeric-looking key as kv (no over-correction)", () => {
    // 키 끝이 숫자여도 그 앞이 공백/괄호/줄 시작이 아니면(=글자에 바로 붙은 숫자) 시각이
    // 아니다 - "질문2"의 "2"를 시(hour)로 오인해 진짜 키-값 줄까지 막으면 안 된다.
    expect(classifyLine("질문2: 15번 참고")).toMatchObject({ kind: "kv", key: "질문2", text: "15번 참고" });
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

  // AI-34: 펜스 안 줄은 classifyLine을 절대 안 거친다 — 불릿/kv/빈 줄처럼 생겼어도
  // 코드 블록 텍스트로 그대로 보존돼야 한다.
  it("keeps fenced content verbatim as a code block instead of misclassifying list/kv lines inside it", () => {
    const blocks = parseBlocks("```python\ndef f(x):\n- 다른 목록\n상태: 값\n\n안녕\n```");
    expect(blocks).toEqual([
      { kind: "code", lang: "python", text: "def f(x):\n- 다른 목록\n상태: 값\n\n안녕" },
    ]);
  });

  it("classifies content before and after a fenced block normally", () => {
    const blocks = parseBlocks("- 목록1\n```\ncode line\n```\n상태: 진행\n담당: 김");
    expect(blocks).toHaveLength(3);
    expect(blocks[0]).toMatchObject({ kind: "list" });
    expect(blocks[1]).toEqual({ kind: "code", lang: "", text: "code line" });
    expect(blocks[2]).toMatchObject({ kind: "kv" });
  });

  it("still yields a code block for an unterminated fence at end of input", () => {
    const blocks = parseBlocks("```\n- 안 닫힌 펜스\n마지막 줄");
    expect(blocks).toEqual([{ kind: "code", lang: "", text: "- 안 닫힌 펜스\n마지막 줄" }]);
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
