import { describe, it, expect } from "vitest";

import {
  CARD_PADDING,
  GRID_GAP,
  SECTION_GAP,
  TILE_GRID_GAP,
  TILE_PADDING,
} from "./density.js";
import { FONT_SIZE } from "./theme.js";
import { DETAIL_GRID } from "../screens/Ticket.jsx";
import { DOC_DETAIL_GRID } from "../screens/TeamDoc.jsx";
import { NEW_TICKET_GRID } from "../screens/MyTickets.jsx";
import { PEOPLE_GRID } from "../screens/Sprint.jsx";

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

/* `repeat(N, ...)` 과 명시 트랙 나열을 모두 센다. */
function columnCount(track) {
  const repeat = /repeat\(\s*(\d+)/.exec(track);
  if (repeat) return Number(repeat[1]);
  return track.trim().split(/\s+(?![^(]*\))/).length;
}

describe("왼쪽 쏠림 방지 — 상세·폼 격자는 본문 폭을 채운다 (지시 6)", () => {
  const grids = [
    ["티켓 상세", DETAIL_GRID],
    ["문서 상세", DOC_DETAIL_GRID],
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

describe("개수가 고정된 카드 줄은 마지막 줄에 빈 칸을 남기지 않는다", () => {
  /* 홈 지표 줄(6장)을 여기서 검사하던 자리다. 그 줄은 이제 격자가 아니라 판독 줄
     (kit.jsx::MetricStrip)이라 마지막 줄 빈 칸이라는 결함 자체가 없다 — 검사는 실제
     렌더링을 보는 `screens/home.test.jsx`
     ("지표가 카드 여섯 장이 아니라 판 두 개에 담긴다")로 옮겼다. 트랙 문자열 대신 DOM 을
     보므로 더 강한 검사다. */

  it("담당자 현황은 넓은 화면에서 촘촘하게 편다(작은 타일이므로)", () => {
    /* 이름 + 숫자 셋짜리 작은 타일이다. `card.pad` 급 3열로 펴면 한 사람이 화면 1/3 을
       차지해 비교가 안 된다 — 스프린트 회의는 담당자끼리 **나란히 놓고 비교**하는 자리다.
       정확한 열 수는 방향과 함께 움직이므로 하한만 못박는다.
       (열 수 자체의 재설계는 지시 9 / P7-3 에서 다룬다.) */
    const widest = Math.max(...trackEntries(PEOPLE_GRID).map(([, t]) => columnCount(t)));
    expect(widest).toBeGreaterThanOrEqual(4);
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
