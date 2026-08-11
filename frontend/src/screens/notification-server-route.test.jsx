import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";

/* RG-02 — 알림 목록 화면(/notifications)의 "관련 항목 보기"/"관련 목록 열기"가 서버가 이미
 * 계산해 주는 related_route(app/notifications/destinations.py)를 무시하고 로컬 표
 * (registry/shared.js의 OBJ_ROUTE/OBJ_ID_PARAM)로만 목적지를 다시 계산했다. 팀 문서 댓글
 * (document)이 정확히 이 순서를 안 지켜서 겪은 문제: 서버는 `/team-docs/{id}`를 주는데
 * 화면은 그걸 버리고 관리 콘솔의 "문서 생성" 화면(`#/documents?id=<id>`)으로 보내
 * `GET /api/admin/documents/<team_docs_id>` 404로 갔다. `NotificationBell.jsx`(팝오버)는
 * 이미 서버 값을 최우선으로 쓰고 있었다 — 이 화면만 안 그랬다.
 */
describe("알림 목록의 '관련 항목 보기' — 서버가 계산한 related_route를 최우선으로 쓴다 (RG-02)", () => {
  const action = () => REGISTRY.notifications.actions.find((a) => a.label === "관련 항목 보기");

  it("팀 문서 댓글(document) — 서버 related_route가 /documents(관리 콘솔)가 아니라 /team-docs로 보낸다", () => {
    const row = { related_object_type: "document", related_object_id: "np-1", related_route: "/team-docs/np-1" };
    expect(action().when(row, { role: "user" })).toBe(true);
    expect(action().navigate(row)).toBe("#/team-docs/np-1");
  });

  it("일반 사용자(role=user)도 서버가 계산해 준 자기 대상(티켓·채팅·게시글)은 클릭할 수 있다", () => {
    const row = { related_object_type: "ticket", related_object_id: "t-1", related_route: "/tickets/t-1" };
    expect(action().when(row, { role: "user" })).toBe(true);
    expect(action().navigate(row)).toBe("#/tickets/t-1");
  });

  it("related_route가 없으면(서버가 아직 모르는 유형) 로컬 표로 폴백한다 — 기존 동작 유지", () => {
    const row = { related_object_type: "runner", related_object_id: "r-1" };
    expect(action().when(row, { role: "operator" })).toBe(true);
    expect(action().navigate(row)).toBe("#/runners?id=r-1");
  });

  it("로컬 표 폴백 대상은 여전히 일반 사용자에게 숨는다(관리자 콘솔 경로라서)", () => {
    const row = { related_object_type: "runner", related_object_id: "r-1" };
    expect(action().when(row, { role: "user" })).toBe(false);
  });

  it("프로토콜 상대 URL(//evil.example)은 related_route로 받아도 무시하고 로컬 표로 폴백한다", () => {
    const row = { related_object_type: "runner", related_object_id: "r-1", related_route: "//evil.example" };
    expect(action().navigate(row)).toBe("#/runners?id=r-1");
  });

  it("'관련 목록 열기'는 related_route가 있는 행에서는 안 뜬다(항목 보기와 상호 배타)", () => {
    const listAction = REGISTRY.notifications.actions.find((a) => a.label === "관련 목록 열기");
    const row = { related_object_type: "document", related_object_id: "np-1", related_route: "/team-docs/np-1" };
    expect(listAction.when(row, { role: "admin" })).toBe(false);
  });
});
