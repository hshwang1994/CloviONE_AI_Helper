import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  MAX_QUERY_CHARS,
  foldText,
  foldedFilterOptions,
  includesFolded,
  isSearchable,
  normalizeQuery,
  searchResultsPath,
} from "./search.js";

/* 검색 접기 규칙 — 화면이 서버와 **같은 값**을 내는가 (D-495).
 *
 * 공백 · 대소문자 · 전각 표기가 검색 결과를 바꾸지 않으려면 질의와 대상을 같은 규칙으로 접어야 하고, 그 규칙은
 * 서버(Python `fold`, SQL `search_fold()`)와 화면(`foldText`)이 한 벌이어야 한다. 한쪽만 다르면 목록 검색과
 * 고르개 검색이 같은 글자로 서로 다른 결과를 낸다.
 *
 * 그래서 기댓값을 여기 손으로 적지 않고 공용 말뭉치 `tests/fixtures/search_fold_corpus.json` 에서 읽는다.
 * 서버 시험(`tests/unit/test_search_fold.py`)도 같은 파일을 읽으므로, 말뭉치가 바뀌면 세 구현이 함께 다시 잰다.
 * 사본을 옮겨 적으면 서버가 바뀐 날 이 시험도 같이 통과해 버린다(`role-sets-match-backend.test.js` 와 같은 이유).
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CORPUS = JSON.parse(
  fs.readFileSync(path.resolve(HERE, "../../../tests/fixtures/search_fold_corpus.json"), "utf-8"),
);

describe("공용 말뭉치 — 화면의 접기가 서버와 같은 값을 낸다", () => {
  it("말뭉치가 비어 있지 않다 — 빈 말뭉치면 아래 시험은 아무것도 증명하지 않는다", () => {
    expect(CORPUS.fold.length).toBeGreaterThanOrEqual(50);
    expect(CORPUS.display.length).toBeGreaterThanOrEqual(5);
  });

  for (const c of CORPUS.fold) {
    it(`foldText: ${c.name}`, () => {
      expect(foldText(c.input)).toBe(c.fold);
    });
  }

  for (const c of CORPUS.display) {
    it(`normalizeQuery: ${c.name}`, () => {
      expect(normalizeQuery(c.input)).toBe(c.display);
    });
  }

  it("두 번 접어도 값이 같다 — 질의와 대상 어느 쪽을 먼저 접어도 결과가 안 바뀐다", () => {
    for (const c of CORPUS.fold) expect(foldText(c.fold), c.name).toBe(c.fold);
    for (const c of CORPUS.display) expect(normalizeQuery(c.display), c.name).toBe(c.display);
  });
});

describe("normalizeQuery — 화면과 주소에 서는 값", () => {
  it("사람이 친 대소문자는 그대로 둔다 — 주소에는 친 글자가 선다", () => {
    expect(normalizeQuery("  ClovirONE  ")).toBe("ClovirONE");
  });

  it("상한은 코드포인트로 센다 — 그림 문자 하나를 두 글자로 세지 않는다", () => {
    const out = normalizeQuery("\u{1F44D}".repeat(MAX_QUERY_CHARS + 5));
    expect(Array.from(out)).toHaveLength(MAX_QUERY_CHARS);
    expect(out).toBe("\u{1F44D}".repeat(MAX_QUERY_CHARS));
  });

  it("값이 없으면 빈 글자다", () => {
    expect(normalizeQuery(undefined)).toBe("");
    expect(normalizeQuery(null)).toBe("");
  });

  it("결과 화면 주소도 같은 값을 싣는다", () => {
    expect(searchResultsPath("  현황   제외 ")).toBe("/search?q=" + encodeURIComponent("현황 제외"));
  });
});

describe("includesFolded — 질의와 대상을 같은 규칙으로 접어 본다", () => {
  const CASES = [
    // [대상, 질의, 기대, 이유]
    ["현황 제외 보고", "현황제외", true, "대상 쪽 공백도 접는다"],
    ["현황제외 보고", "현황 제외", true, "질의 쪽 공백도 접는다"],
    ["현황  제외", "  현황 제외 ", true, "앞뒤 · 연속 공백"],
    ["현황\u{3000}제외", "현황 제외", true, "전각 공백"],
    ["현황\u{00A0}제외", "현황제외", true, "줄바꿈 없는 공백"],
    ["현황\u{200B}제외", "현황제외", true, "제로폭 공백"],
    ["ClovirONE 2.0", "clovirone", true, "소문자 질의"],
    ["ClovirONE 2.0", "CLOVIRONE", true, "대문자 질의"],
    ["ClovirONE 2.0", "ＣｌｏｖｉｒＯＮＥ", true, "전각 질의"],
    ["ＣＬＯＶＩＲＯＮＥ", "clovir one", true, "전각 대상"],
    ["현황 제외", "현황 포함", false, "다른 낱말은 안 걸린다"],
    ["élan", "elan", false, "억양은 지우지 않는다 — 다른 글자다"],
    ["회의록", "회의룩", false, "오타를 허용하지 않는다"],
    ["100% 달성", "%", true, "%는 글자 그대로다"],
    ["달성", "%", false, "%는 아무 글자와도 맞는 기호가 아니다"],
    ["a_b", "_", true, "_는 글자 그대로다"],
    ["ab", "_", false, "_는 아무 한 글자와 맞는 기호가 아니다"],
  ];
  for (const [hay, q, want, why] of CASES) {
    it(`${why}: ${JSON.stringify(q)} → ${JSON.stringify(hay)} = ${want}`, () => {
      expect(includesFolded(hay, q)).toBe(want);
    });
  }

  it("접은 질의가 비면 조건이 없는 것이다 — 무엇이든 통과한다", () => {
    for (const q of ["", "   ", "\u{200B}", "\u{3000}\u{3000}", null, undefined]) {
      expect(includesFolded("아무 글자", q), JSON.stringify(q)).toBe(true);
      expect(includesFolded([], q), JSON.stringify(q)).toBe(true);
    }
  });

  it("배열이면 칸마다 따로 보고 하나라도 맞으면 참이다", () => {
    expect(includesFolded(["김하나", "개발팀"], "개발")).toBe(true);
    expect(includesFolded(["김하나", "개발팀"], "김 하나")).toBe(true);
    expect(includesFolded(["김하나", "개발팀"], "운영")).toBe(false);
  });

  it("칸을 이어 붙여 보지 않는다 — 이은 자리에서 없던 낱말이 생기지 않는다", () => {
    expect(includesFolded(["김하나", "개발팀"], "나개발")).toBe(false);
    expect(includesFolded(["김하나", "개발팀"], "하나 개발")).toBe(false);
  });

  it("값이 없는 칸 · 숫자 칸도 죽지 않는다", () => {
    expect(includesFolded([null, undefined, 12345], "234")).toBe(true);
    expect(includesFolded(null, "가")).toBe(false);
    expect(includesFolded([], "가")).toBe(false);
  });
});

describe("foldedFilterOptions — MUI Autocomplete 의 후보 거르기", () => {
  const OPTIONS = [
    { value: "p3", label: "현황 제외 보고", code: "RPT-3" },
    { value: "p1", label: "ClovirONE 2.0", code: "CLV-1" },
    { value: "p2", label: "현황제외 정리", code: "RPT-2" },
  ];
  const state = (inputValue) => ({ inputValue, getOptionLabel: (o) => o.label });

  it("입력이 없으면 전부를 순서 그대로 새 배열로 돌려준다", () => {
    const filter = foldedFilterOptions();
    for (const input of ["", "   ", "\u{200B}"]) {
      const out = filter(OPTIONS, state(input));
      expect(out.map((o) => o.value)).toEqual(["p3", "p1", "p2"]);
      expect(out, "받은 배열을 그대로 돌려주면 부르는 쪽의 push 가 후보 목록을 고친다").not.toBe(OPTIONS);
    }
  });

  it("공백을 붙이든 띄우든 같은 후보가 같은 순서로 남는다", () => {
    const filter = foldedFilterOptions();
    for (const input of ["현황 제외", "현황제외", " 현황  제외 ", "현황\u{3000}제외"]) {
      expect(filter(OPTIONS, state(input)).map((o) => o.value), input).toEqual(["p3", "p2"]);
    }
  });

  it("대소문자 · 전각 표기가 달라도 같은 후보가 남는다", () => {
    const filter = foldedFilterOptions();
    for (const input of ["clovirone", "CLOVIRONE", "ClovirONE", "ｃｌｏｖｉｒｏｎｅ"]) {
      expect(filter(OPTIONS, state(input)).map((o) => o.value), input).toEqual(["p1"]);
    }
  });

  it("stringify 가 배열을 주면 칸마다 본다 — 이름이든 코드든 걸린다", () => {
    const filter = foldedFilterOptions({ stringify: (o) => [o.label, o.code] });
    expect(filter(OPTIONS, state("rpt")).map((o) => o.value)).toEqual(["p3", "p2"]);
    expect(filter(OPTIONS, state("clv-1")).map((o) => o.value)).toEqual(["p1"]);
    expect(filter(OPTIONS, state("보고rpt")), "이름과 코드를 이어 붙인 자리는 안 걸린다").toEqual([]);
  });

  it("getOptionLabel 없이 불려도 죽지 않는다", () => {
    const filter = foldedFilterOptions();
    expect(filter(["가나", "다라"], { inputValue: "다" })).toEqual(["다라"]);
    expect(filter(undefined, { inputValue: "다" })).toEqual([]);
  });
});

describe("isSearchable — 서버로 보낼 만한 검색어인가", () => {
  it("접으면 빈 검색어는 보내지 않는다", () => {
    for (const q of ["", "   ", "\u{200B}", "\u{3000}", null, undefined]) {
      expect(isSearchable(q), JSON.stringify(q)).toBe(false);
    }
  });

  it("한 글자부터 보낸다 — 서버의 짧은 검색어 경로를 화면이 막지 않는다", () => {
    expect(isSearchable("가")).toBe(true);
    expect(isSearchable("  a  ")).toBe(true);
  });
});
