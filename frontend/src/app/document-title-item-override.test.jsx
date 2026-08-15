import React from "react";
import { describe, it, expect, beforeEach } from "vitest";
import { act, render } from "@testing-library/react";

/* 탭 제목이 나브 라벨("티켓")이 아니라 실제 항목 제목을 말하는가 (VIS-133).
 *
 * 여러 티켓 탭을 열어 두면 전부 "티켓 | ClovirAssist"였다 — 나브 라벨은 화면
 * *종류*만 알지 그 화면이 지금 보여주는 *항목*은 모른다. Ticket.jsx 등이 자기 데이터를
 * 읽은 뒤 setItemTitle(pathname, 실제제목)을 불러 이 갭을 메운다(setBrand()와 같은
 * 모듈 전역 + 구독자 패턴, document-title-brand-async.test.jsx가 그 원조 사례를 고정한다).
 */

import { useDocumentTitle, setItemTitle, labelForPath, BRAND } from "./documentTitle.js";

function Probe({ path }) {
  useDocumentTitle(path);
  return null;
}

// "/tickets/abc" 는 나브 항목이 아니지만 EXTRA_LABELS의 "/tickets" 접두어에 걸려 기본
// 라벨이 "티켓"이다 — 항목 제목이 아직 없을 때는 이 라벨로 돌아가야 한다(전부 "없음"으로
// 떨어지는 게 아니라 "화면 종류"까지는 항상 안다).
const TICKET_LABEL = labelForPath("/tickets/abc");

describe("항목별 탭 제목 override (VIS-133)", () => {
  beforeEach(() => {
    // 이전 시험의 override가 이번 시험의 경로와 우연히 겹치지 않을, 존재할 수 없는 경로로
    // 밀어내 초기화한다(setBrand("") 와 같은 목적의 정리).
    setItemTitle("/__reset__", "");
  });

  it("등록된 pathname과 일치하면 나브 라벨 대신 항목 제목을 쓴다", () => {
    render(<Probe path="/tickets/abc" />);
    expect(document.title).toBe(`${TICKET_LABEL} | ${BRAND}`);

    act(() => { setItemTitle("/tickets/abc", "서버 재부팅 후 로그인 안 됨"); });
    expect(document.title).toBe(`서버 재부팅 후 로그인 안 됨 | ${BRAND}`);
  });

  it("다른 경로로 이미 옮겨간 뒤 도착한 지연 응답은 지금 화면의 제목을 덮지 않는다", () => {
    const { rerender } = render(<Probe path="/tickets/abc" />);
    act(() => { setItemTitle("/tickets/abc", "첫 번째 티켓"); });
    expect(document.title).toBe(`첫 번째 티켓 | ${BRAND}`);

    // 사용자가 다른 티켓으로 옮겨간다 — 그 화면은 아직 자기 제목을 못 읽은 참이다.
    rerender(<Probe path="/tickets/xyz" />);
    expect(document.title, "새 경로는 아직 항목 제목이 없으니 라벨로 돌아가야 한다")
      .toBe(`${TICKET_LABEL} | ${BRAND}`);

    // 첫 번째 티켓의 지연 응답이 이제야 도착했다고 하자 — 이미 다른 화면이니 무시돼야 한다.
    act(() => { setItemTitle("/tickets/abc", "첫 번째 티켓(늦게 도착)"); });
    expect(document.title, "떠난 화면의 지연 응답이 지금 화면의 탭 제목을 덮었다")
      .toBe(`${TICKET_LABEL} | ${BRAND}`);

    // 두 번째 티켓 자신의 응답이 도착하면 정상 반영된다.
    act(() => { setItemTitle("/tickets/xyz", "두 번째 티켓"); });
    expect(document.title).toBe(`두 번째 티켓 | ${BRAND}`);
  });
});
