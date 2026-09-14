/* qa-contract-change: 스프린트 회의의 담당자 타일 격자 PEOPLE_GRID 가 없어져 그 열 수를 세던 단정이 사라졌다. 그 자리는 이제 담당자별 남은 WD 막대이고, 「나란히 놓고 비교된다」는 성질은 격자 열 수가 아니라 하나의 축을 공유하는가로 지켜진다 — 아래에서 그 성질을 직접 단정한다(지시 4).
 * qa-contract-change: 논의 갈래 타일 트랙(DISCUSS_TILE_TRACK)이 사라졌다 — 갈래는 이제 격자 타일이 아니라 칩 한 줄이라(D-484) 「마지막 줄이 꽉 차는가」라는 결함 자체가 없다. 대신 회의 짝 판의 오른쪽 트랙에 바닥(rem)이 생긴 계약을 단정한다 — 그것이 게이지가 손톱만 해지던 결함을 막는 값이다.
 */
import { describe, it, expect } from "vitest";

import {
  BASELINE_TRACKS,
  CARD_PADDING,
  GRID_GAP,
  LIST_RAIL_GRID,
  SECTION_GAP,
  TILE_GRID_GAP,
  TILE_PADDING,
  MEETING_PAIR_TRACKS,
  PAIR_CHART_MIN_HEIGHT,
  fixedTileTrack,
  FORM_FIELD_GRID,
  pairTracks,
} from "./density.js";
import { FONT_SIZE } from "./theme.js";
import { DETAIL_GRID } from "../screens/Ticket.jsx";
import { NEW_TICKET_GRID } from "../screens/MyTickets.jsx";
import { workloadItems } from "../screens/sprint-charts.js";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/* 소스를 글자로 읽는다 — 격자 값은 sx 객체라 jsdom 이 계산하지 않는다. */
function readSrc(rel) {
  const here = path.dirname(fileURLToPath(import.meta.url));
  return fs.readFileSync(path.resolve(here, "..", rel), "utf8");
}


/* 밀도·격자 계약 — 목업이 아니라 **레이아웃이 지켜야 하는 성질**을 본다.
 *
 * ## 이 파일이 무엇을 대체했는가
 *
 * `density.test.jsx` 는 폐기한 목업(지시 64)(목업)을 파싱해
 * "카드 여백이 20px 인가", "격자 트랙 문자열이 목업과 글자까지 같은가"를 봤다. 목업은
 * 지시 64 로 폐기했고, 그런 값 대조는 **새 디자인을 옛 치수에 묶는** 종류의 검사였다.
 *
 * 살려 둔 것은 값이 아니라 성질이다. 그 시험들이 실제로 막고 있던 결함은 두 가지였다:
 *
 *   1. **왼쪽 쏠림** (지시 6) — 상세·폼 격자의 트랙에 `fr` 이 하나도 없으면 콘텐츠가 왼쪽에
 *      몰리고 오른쪽이 비어 버린다. 값이 몇이든 이 성질은 지켜져야 한다.
 *   2. **마지막 줄 빈 칸** — 개수가 고정된 카드 줄(홈 지표 6장)에서 열 수가 개수를 나누지
 *      못하면 오른쪽이 빈 채 줄만 하나 늘어난다.
 *
 * 여기에 밀도 자체가 무너지지 않는지(치수가 양수이고 서로 순서가 맞는지)를 더한다.
 * 정확한 픽셀은 D-141 방향과 함께 움직이는 값이라 고정하지 않는다.
 */

const rem = (v) => Number.parseFloat(String(v));

/* 트랙 목록에 `fr` 이 하나도 없으면 그 격자는 컨테이너를 채우지 못한다. */
function fills(track) {
  return /\dfr\b/.test(track);
}

/* sx 의 `gridTemplateColumns` 는 문자열이거나 브레이크포인트 객체다. 둘 다 받아
 * (브레이크포인트, 트랙) 목록으로 편다. */
function trackEntries(sx) {
  const v = sx.gridTemplateColumns;
  return typeof v === "string" ? [["(기본)", v]] : Object.entries(v);
}

describe("왼쪽 쏠림 방지 — 상세·폼 격자는 본문 폭을 채운다 (지시 6)", () => {
  /* 「문서 상세」 줄을 걷었다 — 그것이 읽던 `DOC_DETAIL_GRID` 는 제품 소비처가 0 이었고
     실제 문서 상세는 `ui/DetailLayout.jsx` 로 두 열을 그린다. 즉 여기 「티켓 상세」로 적힌
     `DETAIL_GRID` 가 **문서 상세의 격자이기도 하다**(둘이 같은 부품을 쓴다). 없는 것을
     재는 줄을 남기면 「문서 상세도 확인했다」로 읽힌다. */
  const grids = [
    ["티켓 상세(문서 상세도 같은 격자다)", DETAIL_GRID],
    ["새 티켓", NEW_TICKET_GRID],
  ];

  it.each(grids)("%s 의 모든 트랙 조합에 fr 이 있다", (name, sx) => {
    const stuck = trackEntries(sx).filter(([, track]) => !fills(track));
    expect(
      stuck.map(([bp, track]) => `${bp}: ${track}`),
      `${name}: 상한이 전부 고정값인 트랙은 오른쪽을 비운다`,
    ).toEqual([]);
  });

  it.each(grids)("%s 에 고정 px 트랙만으로 된 조합이 없다", (name, sx) => {
    /* `240px 1fr` 은 괜찮다(보조 열이 고정, 본문이 늘어남). `240px 320px` 은 안 된다. */
    const allFixed = trackEntries(sx).filter(([, t]) => /px/.test(t) && !/fr/.test(t));
    expect(allFixed.map(([bp]) => bp), `${name}: 고정 px 만으로 짠 트랙`).toEqual([]);
  });
});

describe("회의 짝 판은 폭을 채운다", () => {
  it("좁은 화면·넓은 화면 트랙에 모두 fr 이 있다", () => {
    expect(fills(MEETING_PAIR_TRACKS.xs)).toBe(true);
    expect(fills(MEETING_PAIR_TRACKS.lg)).toBe(true);
  });
});

describe("개수가 고정된 카드 줄은 마지막 줄에 빈 칸을 남기지 않는다", () => {
  it("KPI 타일 트랙은 칸 수만큼만 fr 을 쓴다", () => {
    expect(fills(fixedTileTrack(7))).toBe(true);
    expect(fixedTileTrack(7)).toBe("repeat(7, minmax(0, 1fr))");
  });

  /* 🔴 회의 짝 판의 오른쪽(건강 게이지)이 1366 폭에서 300px 남짓으로 눌려 게이지가
     손톱만 했다 — `2fr 1fr` 은 바닥이 없다. 게이지는 원이라 폭이 곧 크기다. 오른쪽 트랙에
     rem 바닥이 있고, 높이도 큰 게이지와 진도 막대가 설 만큼이어야 한다(D-484). */
  it("회의 짝 판의 오른쪽 트랙은 rem 바닥을 갖고, 높이는 큰 게이지가 설 만큼이다", () => {
    const right = MEETING_PAIR_TRACKS.lg.split(") ")[1];
    expect(right).toMatch(/^minmax\(\d+rem,/);
    expect(Number.parseFloat(/minmax\((\d+)rem/.exec(right)[1])).toBeGreaterThanOrEqual(18);
    // 11rem 게이지 + 캡션 + 진도 막대 둘 — 12rem 으로는 잘렸다.
    expect(Number.parseFloat(PAIR_CHART_MIN_HEIGHT.lg)).toBeGreaterThanOrEqual(16);
  });

  /* 홈 지표 줄(6장)을 여기서 검사하던 자리다. 그 줄은 이제 격자가 아니라 판독 줄
     (kit.jsx::MetricStrip)이라 마지막 줄 빈 칸이라는 결함 자체가 없다 — 검사는 실제
     렌더링을 보는 `screens/home.test.jsx`
     ("지표가 카드 여섯 장이 아니라 판 두 개에 담긴다")로 옮겼다. 트랙 문자열 대신 DOM 을
     보므로 더 강한 검사다. */

  it("🔴 담당자 현황은 한 축을 공유한다 — 그래야 나란히 비교된다", () => {
    /* 여기 있던 것은 담당자 타일 **격자**의 열 수 하한이었다. 그 격자가 없어졌다.
       지키던 성질은 「한 사람이 화면 1/3 을 차지해 비교가 안 되는 것을 막는다」였고,
       스프린트 회의는 담당자끼리 **나란히 놓고 비교**하는 자리라는 것이 그 이유다.

       지금 그 자리는 막대다. 막대가 비교되려면 **분모가 하나**여야 한다 — 줄마다 자기
       최대값으로 그리면 남은 1WD 와 남은 9WD 가 같은 길이가 되고, 그때 그림은 거짓말을
       한다. 그래서 `max` 를 목록 전체의 최대값 하나로 낸다.

       그리고 예상 WD 를 안 적은 티켓은 합계에 못 들어가므로 그 건수를 줄 설명으로
       따로 말한다 — 「남은 3WD」와 「남은 3WD + 예상 없는 다섯 건」은 다른 이야기다. */
    const rows = [
      { user_id: "u-1", display_name: "가", remaining_wd: 9, open: 4, unestimated: 0 },
      { user_id: "u-2", display_name: "나", remaining_wd: 1, open: 1, unestimated: 2 },
    ];
    const out = workloadItems(rows);
    expect(out.max).toBe(9);
    expect(out.items.map((i) => i.value)).toEqual([9, 1]);
    expect(out.items[1].note).toContain("예상을 안 적은 것 2건");
    // 아무도 남은 일이 없으면 **빈 막대를 그리지 않는다** — 0 짜리 줄만 늘어선 그림은
    // 「고르다」가 아니라 「아무것도 없다」이고, 그 둘은 다른 사실이다.
    expect(workloadItems([])).toBeNull();
  });
});

describe("밀도 토큰이 무너지지 않는다", () => {
  it("모든 치수가 양수다", () => {
    for (const [name, v] of Object.entries({
      CARD_PADDING, GRID_GAP, SECTION_GAP, TILE_PADDING, TILE_GRID_GAP,
    })) {
      expect(rem(v), name).toBeGreaterThan(0);
    }
  });

  it("구획 간격이 카드 안 여백보다 크다 (구획이 카드보다 멀리 떨어져야 묶음이 읽힌다)", () => {
    expect(rem(SECTION_GAP)).toBeGreaterThan(rem(CARD_PADDING) / 2);
  });

  it("작은 타일은 카드보다 촘촘하다", () => {
    expect(rem(TILE_PADDING)).toBeLessThanOrEqual(rem(CARD_PADDING));
    expect(rem(TILE_GRID_GAP)).toBeLessThanOrEqual(rem(GRID_GAP));
  });

  it("판독값이 본문보다 확실히 크다 (지배하는 수치 하나 — D-141)", () => {
    /* 예전엔 density.js 의 `STAT_VALUE_FONT_SIZE`(목업 30px 파생)를 봤다. 그 치수의
       소비자였던 StatCard 가 MetricStrip 으로 대체되면서 판독값 크기의 정본은 테마의
       `FONT_SIZE.readout` 하나가 됐다 — 검사도 그 정본을 본다. */
    expect(rem(FONT_SIZE.readout)).toBeGreaterThanOrEqual(rem(FONT_SIZE.body) * 1.8);
    expect(rem(FONT_SIZE.readout)).toBeGreaterThan(rem(FONT_SIZE.title));
  });
});

describe("좌측 레일 목록 화면은 한 트랙을 쓴다", () => {
  it("listRail 트랙의 모든 조합에 fr 이 있고, 간격은 GRID_GAP 이다", () => {
    // 이 트랙이 없던 동안 문서 작업공간(18rem·gap16)과 조직 콘솔(20~26rem·gap20)이
    // 서로 다른 값을 각자 하드코딩했다 — 정본은 이제 이 한 벌이다.
    const stuck = trackEntries(LIST_RAIL_GRID).filter(([, track]) => !fills(track));
    expect(stuck).toEqual([]);
    expect(LIST_RAIL_GRID.gap).toBe(GRID_GAP);
    expect(LIST_RAIL_GRID.gridTemplateColumns.lg).toBe(BASELINE_TRACKS.listRail);
  });
});

describe("설정성 화면의 판 짝은 한 부품에서 나온다 (D-457)", () => {
  it("pairTracks 는 좁은 폭에서 한 줄, lg 부터 넘긴 가중치를 그대로 쓴다", () => {
    const g = pairTracks("minmax(0, 1.15fr) minmax(0, 0.85fr)");
    expect(g.gridTemplateColumns.xs).toBe("minmax(0, 1fr)");
    expect(g.gridTemplateColumns.lg).toBe("minmax(0, 1.15fr) minmax(0, 0.85fr)");
    expect(g.gap).toBe(GRID_GAP);
    expect(g.alignItems).toBe("stretch");
    const stuck = trackEntries(g).filter(([, track]) => !fills(track));
    expect(stuck).toEqual([]);
  });

  it("폼 필드 격자는 컨테이너 폭에 따라 1·2·3열로 서고 어느 단에서도 fr 로 채운다", () => {
    const keys = Object.keys(FORM_FIELD_GRID).filter((k) => k.startsWith("@container"));
    expect(keys.length).toBe(2);
    expect(FORM_FIELD_GRID.gridTemplateColumns).toBe("minmax(0, 1fr)");
    for (const k of keys) expect(fills(FORM_FIELD_GRID[k].gridTemplateColumns)).toBe(true);
    // 반례: 2열 질의가 3열 질의보다 좁은 폭에서 켜진다 — 순서가 뒤집히면 3열이 먼저 잡혀 2열이 죽는다.
    const widths = keys.map((k) => Number(k.match(/min-width: ([\d.]+)rem/)[1]));
    expect(widths[0]).toBeLessThan(widths[1]);
  });
});

/* 판을 세로로 쌓는 자리는 **가로 이음매와 같은 값**을 쓴다 (2026-09-07 지시).
 *
 * `pairTracks` 와 `DetailLayout` 이 가로 이음매를 `GRID_GAP`(24px)로 그리는데 세로 스택만
 * MUI `gap: 2.5`(20px)나 `spacing={2}`(16px)이면 한 화면에서 두 값이 나란히 보인다. 좁은
 * 화면에서 두 열이 한 열로 접히면 24 → 20 → 24 로 교대하기까지 한다.
 *
 * 소스를 훑어 재는 이유: jsdom 은 격자를 계산하지 않아 픽셀로 잴 길이 없고, 이 계약이
 * 지키려는 것은 「이 화면들이 정본 토큰을 쓴다」는 사실 자체다. 폼 칸 묶음은 20px 이
 * 따로 정본이라(`FORM_FIELD_GAP_REM`) 반례로 함께 잰다.
 */
describe("판을 쌓는 화면은 정본 간격을 쓴다", () => {
  const PANEL_STACK_SCREENS = [
    "screens/Profile.jsx", "screens/Ticket.jsx", "screens/Integrity.jsx",
    "screens/MyStats.jsx", "screens/Project.jsx", "screens/KnowledgeDoc.jsx",
  ];

  it.each(PANEL_STACK_SCREENS)("%s 는 GRID_GAP 을 가져다 쓴다", (rel) => {
    const src = readSrc(rel);
    expect(src).toMatch(/import \{[^}]*GRID_GAP[^}]*\} from "\.\.\/ui\/density\.js"/);
    expect(src).toContain("gap: GRID_GAP");
  });

  it("반례 — 폼 칸 묶음은 20px 그대로다. 모든 화면을 24px 로 민 것이 아니다", () => {
    // 게시글 추가 모달의 카테고리·제목 두 칸. 판이 아니라 입력 칸이라 폼 리듬을 지킨다.
    expect(readSrc("screens/Board.jsx")).toContain("gap: 2.5");
  });

  it("반례 — 이 검사가 실제로 소스를 읽는다", () => {
    expect(readSrc("screens/Profile.jsx").length).toBeGreaterThan(1000);
    expect(() => readSrc("screens/NoSuchScreen.jsx")).toThrow();
  });
});
