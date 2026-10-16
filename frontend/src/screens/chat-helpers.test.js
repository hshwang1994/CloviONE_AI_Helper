/* qa-contract-change: 옛 실행기 시절의 카드 번호 · 본문 목록 걷기 · 응답 시간(timing) 헬퍼를 걷었다 — 서버가 그 구조를 더는 싣지 않아 화면에서 닿을 수 없는 코드였다(D-535). 그 자리의 시험은 도우미 답의 구조(걸린 시간 · 확인한 내용 · 찾아본 검색어)와 시작 예시가 할 수 있는 일만 약속하는지를 잰다. 우선순위 어휘 시험은 정의가 있는 lib/priority.js 에서 그대로 가져와 지킨다.
 * qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
 */
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
  parseInline,
  plainSegments,
  safeSourceRoute,
  stripBlock,
  toolCountLabel,
  INLINE_LINK_RE, findLink, safeAnswerRoute, safeListRoute,
  BOLD_RE,
  GUIDE_ROUTES,
} from "./chat-helpers.js";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

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
  it("「내가 작성한 문서」와 「내가 담당하는 미완료 티켓」을 예시로 든다(묻는 사람을 서버가 정하는 도구, A8)", () => {
    expect(QUICK_PROMPTS).toContain("내가 작성한 문서가 몇 개야?");
    expect(QUICK_PROMPTS).toContain("내가 담당하는 미완료 티켓을 알려 줘");
    // 클로비 패널은 앞의 넷을 쓴다(`app/AssistantPanel.jsx`) — 첫 예시는 그대로다.
    expect(QUICK_PROMPTS[0]).toBe("오늘 내가 할 일을 정리해 줘");
  });
});

describe("마크다운 머리글 (A8)", () => {
  it("「# 」 · 「## 」 · 「### 」 는 머리글이다(끝의 # 닫기는 뗀다)", () => {
    expect(classifyLine("# 요약")).toEqual({ kind: "head", text: "요약", note: "" });
    expect(classifyLine("## 이번 주 진행")).toEqual({ kind: "head", text: "이번 주 진행", note: "" });
    expect(classifyLine("### 셋째 ###")).toEqual({ kind: "head", text: "셋째", note: "" });
    expect(classifyLine("## C#")).toEqual({ kind: "head", text: "C#", note: "" });
  });
  it("띄어 쓰지 않은 「#태그」와 「##### 다섯」은 머리글이 아니고 「#### 넷」은 머리글이다", () => {
    // qa-contract-change: 형식 줄이 소제목(###)을 허용하면서 「####」까지 머리글로 그린다(AI 채팅 개선 회차).
    expect(classifyLine("#태그")).toEqual({ kind: "text", text: "#태그" });
    expect(classifyLine("#### 넷")).toEqual({ kind: "head", text: "넷", note: "" });
    expect(classifyLine("##### 다섯")).toEqual({ kind: "text", text: "##### 다섯" });
  });
  it("parseBlocks 가 머리글과 문단을 나눈다", () => {
    expect(parseBlocks("# 요약\n본문입니다.")).toEqual([
      { kind: "head", text: "요약", note: "" },
      { kind: "para", lines: ["본문입니다."] },
    ]);
  });
  it("「[제목](경로)」로 시작하는 줄은 대괄호 머리글이 아니다", () => {
    expect(classifyLine("[연차 규정](/knowledge/d-1) 홍길동, 2026-10-01")).toEqual({
      kind: "text", text: "[연차 규정](/knowledge/d-1) 홍길동, 2026-10-01",
    });
    expect(classifyLine("[요약] 이번 주")).toMatchObject({ kind: "head", text: "요약", note: "이번 주" });
  });
});

describe("safeSourceRoute · stripBlock (A8)", () => {
  it("여섯 갈래의 앱 안 경로만 받는다 — 회의록은 `/sprint` 자체나 질의가 붙은 것만", () => {
    expect(safeSourceRoute("/sprint?team=t&sprint=s")).toBe("/sprint?team=t&sprint=s");
    expect(safeSourceRoute("/sprint")).toBe("/sprint");
    expect(safeSourceRoute("/knowledge/d-1?block=b2")).toBe("/knowledge/d-1?block=b2");
    expect(safeSourceRoute("/my-approvals?id=a1")).toBe("/my-approvals?id=a1");
    for (const bad of ["//evil.example/x", "javascript:alert(1)", "/sprints-x", "/sprint-x", "/sprint/x",
      "https://evil.example/knowledge/d", "/admin/users", "/my-approvalsX", "", null, undefined, 3]) {
      expect(safeSourceRoute(bad)).toBeNull();
    }
  });
  it("block 질의만 뗀다", () => {
    expect(stripBlock("/knowledge/d-1?block=b2")).toBe("/knowledge/d-1");
    expect(stripBlock("/knowledge/d-1?x=1&block=b2")).toBe("/knowledge/d-1?x=1");
    expect(stripBlock("/knowledge/d-1?block=b2&x=1")).toBe("/knowledge/d-1?x=1");
    expect(stripBlock("/sprint?team=t&sprint=s")).toBe("/sprint?team=t&sprint=s");
    expect(stripBlock("/knowledge/d-1")).toBe("/knowledge/d-1");
    expect(stripBlock("/tickets/blocker?blocked=1")).toBe("/tickets/blocker?blocked=1");
    expect(stripBlock(null)).toBe("");
  });
});

describe("parseInline (A8)", () => {
  const routeLinks = new Set(["/knowledge/d-1?block=b2", "/tickets/t-1"]);
  const keyLinks = new Map([["ABCDEF-12", "/tickets/t-1"]]);

  it("정규식은 전역이 아니다(lastIndex 상태가 남지 않는다)", () => {
    expect(INLINE_LINK_RE.global).toBe(false);
    expect(BOLD_RE.global).toBe(false);
  });

  it("굵게는 bold 조각이고 그 안을 다시 나눈다", () => {
    expect(parseInline("앞 **굵게** 뒤")).toEqual([
      { t: "text", text: "앞 " },
      { t: "bold", children: [{ t: "text", text: "굵게" }] },
      { t: "text", text: " 뒤" },
    ]);
    expect(parseInline("**a** 와 **b**")).toEqual([
      { t: "bold", children: [{ t: "text", text: "a" }] },
      { t: "text", text: " 와 " },
      { t: "bold", children: [{ t: "text", text: "b" }] },
    ]);
  });

  it("비었거나 공백으로 감싼 굵게, 닫히지 않은 굵게는 글자 그대로다", () => {
    expect(parseInline("** 아님 **")).toEqual([{ t: "text", text: "** 아님 **" }]);
    expect(parseInline("****")).toEqual([{ t: "text", text: "****" }]);
    expect(parseInline("**열기만")).toEqual([{ t: "text", text: "**열기만" }]);
  });

  it("출처와 같은 경로의 링크는 link 조각이고 가는 곳은 출처의 경로다", () => {
    expect(parseInline("[연차 규정](/knowledge/d-1?block=b9)", { routeLinks })).toEqual([
      { t: "link", route: "/knowledge/d-1?block=b2", label: "연차 규정" },
    ]);
    expect(parseInline("[연차 규정](/knowledge/d-1)", { routeLinks })).toEqual([
      { t: "link", route: "/knowledge/d-1?block=b2", label: "연차 규정" },
    ]);
  });

  it("출처에 없는 링크 · 바깥 링크는 원래 글자 그대로다", () => {
    expect(parseInline("[가짜](/knowledge/zz)", { routeLinks })).toEqual([{ t: "text", text: "[가짜](/knowledge/zz)" }]);
    expect(parseInline("[바깥](https://evil.example/a)", { routeLinks })).toEqual([
      { t: "text", text: "[바깥](" },
      { t: "url", url: "https://evil.example/a" },
      { t: "text", text: ")" },
    ]);
    expect(parseInline("[연차 규정](/knowledge/d-1)")).toEqual([{ t: "text", text: "[연차 규정](/knowledge/d-1)" }]);
  });

  it("화면 길잡이 경로는 출처에 없어도 정확히 그 경로면 링크다 — 하위 경로 · 질의는 아니다", () => {
    expect(parseInline("[사내 문서](/knowledge) 화면에서 보세요.")).toEqual([
      { t: "link", route: "/knowledge", label: "사내 문서" },
      { t: "text", text: " 화면에서 보세요." },
    ]);
    expect(parseInline("[내 티켓](/my-tickets)")).toEqual([{ t: "link", route: "/my-tickets", label: "내 티켓" }]);
    expect(parseInline("[문서](/knowledge?q=x)")).toEqual([{ t: "text", text: "[문서](/knowledge?q=x)" }]);
    expect(parseInline("[가짜](/knowledgebase)")).toEqual([{ t: "text", text: "[가짜](/knowledgebase)" }]);
  });

  it("화면 길잡이 목록은 서버가 모델에게 알려 주는 경로와 같다(app/ai/assistant/turn.py ROUTE_GUIDE)", () => {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const source = fs.readFileSync(path.resolve(here, "../../../app/ai/assistant/turn.py"), "utf-8");
    const block = source.slice(source.indexOf("ROUTE_GUIDE = ("), source.indexOf(")", source.indexOf("ROUTE_GUIDE = (")));
    const paths = new Set(block.match(/\/[a-z][a-z-]*/g));
    expect([...paths].sort()).toEqual([...GUIDE_ROUTES].sort());
  });

  it("굵게 안의 링크와 티켓 키도 조각이 된다", () => {
    expect(parseInline("**[결재 화면](/tickets/t-1) ABCDEF-12**", { routeLinks, keyLinks })).toEqual([
      {
        t: "bold",
        children: [
          { t: "link", route: "/tickets/t-1", label: "결재 화면" },
          { t: "text", text: " " },
          { t: "key", key: "ABCDEF-12", route: "/tickets/t-1" },
        ],
      },
    ]);
  });

  it("링크 글 안의 굵게 표시는 걷는다(앵커 안에 다른 조각을 넣지 않는다)", () => {
    expect(parseInline("[**연차 규정**](/knowledge/d-1)", { routeLinks })).toEqual([
      { t: "link", route: "/knowledge/d-1?block=b2", label: "연차 규정" },
    ]);
  });

  it("티켓 키는 출처에 있는 키만, 앞뒤가 다른 키 글자에 붙어 있지 않을 때만 key 조각이다", () => {
    expect(parseInline("ABCDEF-12 는 진행 중이고 ZZZZZZ-99 는 모릅니다.", { keyLinks })).toEqual([
      { t: "key", key: "ABCDEF-12", route: "/tickets/t-1" },
      { t: "text", text: " 는 진행 중이고 ZZZZZZ-99 는 모릅니다." },
    ]);
    expect(parseInline("ABCDEF-123 과 XABCDEF-12", { keyLinks })).toEqual([{ t: "text", text: "ABCDEF-123 과 XABCDEF-12" }]);
    expect(parseInline("(ABCDEF-12)에서", { keyLinks })).toEqual([
      { t: "text", text: "(" },
      { t: "key", key: "ABCDEF-12", route: "/tickets/t-1" },
      { t: "text", text: ")에서" },
    ]);
  });

  it("맨 주소는 url 조각이고 끝의 문장 부호는 뒤 글로 돌아간다", () => {
    expect(parseInline("주소 https://a.example/c.")).toEqual([
      { t: "text", text: "주소 " },
      { t: "url", url: "https://a.example/c" },
      { t: "text", text: "." },
    ]);
    expect(plainSegments("")).toEqual([]);
  });

  it("routeLinks 의 안전하지 않은 경로는 무시한다", () => {
    const unsafe = new Set(["//evil.example/x", "javascript:alert(1)"]);
    expect(parseInline("[x](//evil.example/x)", { routeLinks: unsafe })).toEqual([{ t: "text", text: "[x](//evil.example/x)" }]);
  });
});

describe("toolCountLabel (A8, D-567)", () => {
  it("전체가 더 많으면 「전체 N건 중 M건」, 같으면 「전체 N건」이다", () => {
    expect(toolCountLabel({ total: 25, count: 8 })).toBe("전체 25건 중 8건");
    expect(toolCountLabel({ total: 8, count: 8 })).toBe("전체 8건");
  });
  it("전체 수를 모르거나 0건이면 붙이지 않는다", () => {
    expect(toolCountLabel({ total: null, count: 3 })).toBeNull();
    expect(toolCountLabel({ count: 3 })).toBeNull();
    expect(toolCountLabel({ total: 0, count: 0 })).toBeNull();
    expect(toolCountLabel(null)).toBeNull();
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

describe("답의 마크다운 — 괄호 든 링크 · 코드 · 목록 · 인용 · 표 (AI 채팅 개선 회차)", () => {
  const routeLinks = new Set(["/knowledge/732b9211-84de-415f-b7d9-c906b2c95f8b"]);

  it("제목에 대괄호가 든 링크가 링크 하나다 — 사용자 캡처의 글자 그대로 남던 줄", () => {
    const line = "[[포스코DX] 부가서비스·NAS 빌링 화면 가이드](/knowledge/732b9211-84de-415f-b7d9-c906b2c95f8b) 황형섭, 2026-09-04";
    expect(parseInline(line, { routeLinks })).toEqual([
      { t: "link", route: "/knowledge/732b9211-84de-415f-b7d9-c906b2c95f8b", label: "[포스코DX] 부가서비스·NAS 빌링 화면 가이드" },
      { t: "text", text: " 황형섭, 2026-09-04" },
    ]);
    expect(findLink("앞 [가 [나] 다](/knowledge/x) 뒤")).toEqual({ index: 2, end: 25, label: "가 [나] 다", route: "/knowledge/x" });
    expect(findLink("[짝이 [안 맞음](/knowledge/x)")).toEqual({ index: 4, end: 24, label: "안 맞음", route: "/knowledge/x" });
    expect(findLink("[경로에 공백](/knowledge/a b)")).toBeNull();
  });

  it("줄 맨 앞의 괄호 든 링크는 머리글이 아니다", () => {
    const line = "[[포스코DX] 부가서비스 가이드](/knowledge/732b9211-84de-415f-b7d9-c906b2c95f8b) 황형섭";
    expect(classifyLine(line)).toEqual({ kind: "text", text: line });
    expect(classifyLine("[이번 주 요약] 세 건")).toEqual({ kind: "head", text: "이번 주 요약", note: "세 건" });
  });

  it("인라인 코드는 해석하지 않는 조각이다", () => {
    expect(parseInline("명령은 `sudo clovirassist ai --with-ai` 입니다.")).toEqual([
      { t: "text", text: "명령은 " }, { t: "code", text: "sudo clovirassist ai --with-ai" }, { t: "text", text: " 입니다." },
    ]);
    expect(parseInline("`**굵게 아님**`")).toEqual([{ t: "code", text: "**굵게 아님**" }]);
  });

  it("글머리 「*」 「•」도 목록이고, 들여쓴 목록 줄은 윗 항목의 딸린 목록이다", () => {
    expect(parseBlocks("* 하나\n• 둘\n  - 둘의 하나\n  1. 둘의 둘\n- 셋")).toEqual([{ kind: "list", items: [
      { marker: "", text: "하나", subs: [] },
      { marker: "", text: "둘", subs: [], children: [{ marker: "", text: "둘의 하나" }, { marker: "1.", text: "둘의 둘" }] },
      { marker: "", text: "셋", subs: [] },
    ] }]);
    expect(classifyLine("**굵게로 시작하는 문장**")).toEqual({ kind: "text", text: "**굵게로 시작하는 문장**" });
  });

  it("인용 · 구분선 · 표를 블록으로 나눈다 — 머리 구분선이 없는 「| |」 줄은 글 그대로다", () => {
    expect(parseBlocks("> 첫 줄\n> 둘째 줄\n\n---\n| 키 | 상태 |\n|---|:---:|\n| A-1 | 진행 |")).toEqual([
      { kind: "quote", lines: ["첫 줄", "둘째 줄"] },
      { kind: "rule" },
      { kind: "table", head: ["키", "상태"], rows: [["A-1", "진행"]] },
    ]);
    expect(parseBlocks("| 표 아님 |\n| 그냥 |")).toEqual([{ kind: "para", lines: ["| 표 아님 |", "| 그냥 |"] }]);
  });

  it("답 안 링크와 「전체 목록 열기」의 경로 판정", () => {
    expect(safeAnswerRoute("/knowledge")).toBe("/knowledge");
    expect(safeAnswerRoute("/knowledge/d1")).toBe("/knowledge/d1");
    expect(safeAnswerRoute("/knowledgebase")).toBeNull();
    expect(safeListRoute("/knowledge?author=u1&sort=recent")).toBe("/knowledge?author=u1&sort=recent");
    expect(safeListRoute("/my-tickets")).toBe("/my-tickets");
    expect(safeListRoute("//evil.example")).toBeNull();
    expect(safeListRoute("/admin/users")).toBeNull();
    expect(safeListRoute("https://evil.example/knowledge")).toBeNull();
  });
});
