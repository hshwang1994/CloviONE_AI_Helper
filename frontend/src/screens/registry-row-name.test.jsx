import { describe, it, expect } from "vitest";

import { REGISTRY } from "./registry.js";
import { declaredRowName } from "../ui/rowName.js";

/* SEM-01 — "상세 보기" 버튼(및 선택 체크박스)의 접근 이름이 행마다 똑같던 문제.
 *
 * 원 감사는 `/jobs`(100개)·`/users`(18개)만 표본으로 들었지만, 원인(kit.jsx의
 * rowOpenLabel 이 첫 열에 rowName/openLabel 표식이 없고 그 열이 custom render() 를 쓰면
 * "상세 보기"로 뭉뚱그린다)은 화면 하나의 버그가 아니라 **표식이 아예 없던** 상태였다 —
 * registry/*.js 전체에 rowName 이 한 곳도 없었다. onRow 는 DataScreen.jsx 가 모든 등록
 * 화면에 무조건 붙이므로(1개 예외 없음), 첫 열이 render() 인 등록 화면은 전부 같은 결함을
 * 안고 있었다. 이 표는 그렇게 찾은 11개 화면 전부를 한 번에 고정한다(각 화면을 렌더링하지
 * 않고 REGISTRY 의 실제 config 를 직접 검증 — registry-identifiers.test.jsx 와 동일한 방식).
 */

describe("SEM-01 — 등록 화면 목록의 행별 접근 이름", () => {
  it("승인(approvals): 유형 + 요청자로 행마다 구별된다", () => {
    const cols = REGISTRY.approvals.columns;
    const a = declaredRowName(cols, { request_type: "schedule.enable", requester_name: "김요청" });
    const b = declaredRowName(cols, { request_type: "schedule.enable", requester_name: "박요청" });
    expect(a).toContain("김요청");
    expect(b).toContain("박요청");
    expect(a).not.toBe(b);
  });

  it("승인 위임(approval-delegations): 위임한 사람 → 대리 승인자로 구별된다", () => {
    const cols = REGISTRY["approval-delegations"].columns;
    const a = declaredRowName(cols, { delegator_name: "위임자A", delegate_name: "대리자A" });
    const b = declaredRowName(cols, { delegator_name: "위임자B", delegate_name: "대리자B" });
    expect(a).toBe("위임자A → 대리자A");
    expect(b).toBe("위임자B → 대리자B");
  });

  it("감사 로그(audit): 작업 + 행위자로 행마다 구별된다(같은 작업이 반복돼도)", () => {
    const cols = REGISTRY.audit.columns;
    const a = declaredRowName(cols, { action: "user.update", actor_name: "감사자A", created_at: "2026-08-01T00:00:00Z" });
    const b = declaredRowName(cols, { action: "user.update", actor_name: "감사자B", created_at: "2026-08-01T00:00:00Z" });
    expect(a).toContain("감사자A");
    expect(b).toContain("감사자B");
    expect(a).not.toBe(b);
  });

  /* WF1 R1 재검증(2026-08-13) 중 정정 — title은 실제로는 app/audit/anomalies.py의 _finding이
   * 만드는 **kind별 고정 문자열**이라("실패가 몰려 있습니다" 등, 행위자·건수와 무관하게 항상
   * 같다) 이 시험이 원래 쓰던 가짜 값(title 자체가 이미 행마다 다름)은 실제로는 벌어지지
   * 않는 모양이었다 — 그래서 title만으로는 같은 kind의 두 행이 같은 이름이 되는 문제를 이
   * 시험이 가려 왔다. 실제 서버 모양(같은 kind는 title도 같다)으로 고치고, 행위자로 보강한
   * 결과를 확인한다. */
  it("감사 이상 징후(audit-anomalies): 같은 유형이라도 행위자로 구별된다", () => {
    const cols = REGISTRY["audit-anomalies"].columns;
    const a = declaredRowName(cols, { title: "실패가 몰려 있습니다", actor_name: "홍길동" });
    const b = declaredRowName(cols, { title: "실패가 몰려 있습니다", actor_name: "이몽룡" });
    expect(a).toBe("실패가 몰려 있습니다 / 홍길동");
    expect(b).toBe("실패가 몰려 있습니다 / 이몽룡");
    expect(a).not.toBe(b);
  });

  it("감사 이상 징후: 목록의 '요약' 열도(rowName뿐 아니라) 행위자로 구별된 값을 보여준다", () => {
    const titleCol = REGISTRY["audit-anomalies"].columns.find((c) => c.key === "title");
    expect(titleCol.render({ title: "실패가 몰려 있습니다", actor_name: "홍길동" })).toBe("실패가 몰려 있습니다 / 홍길동");
    // 행위자 이름이 없으면(퇴사·시스템 동작 등) id, 그마저 없으면 "시스템"으로 — 빈 값이 새지 않는다.
    expect(titleCol.render({ title: "실패가 몰려 있습니다", actor_id: "u-9" })).toBe("실패가 몰려 있습니다 / u-9");
    expect(titleCol.render({ title: "실패가 몰려 있습니다" })).toBe("실패가 몰려 있습니다 / 시스템");
  });

  it("임퍼소네이션(impersonation): 관리자 → 대상으로 구별된다", () => {
    const cols = REGISTRY.impersonation.columns;
    const a = declaredRowName(cols, { actor_name: "관리자A", target_name: "대상A" });
    const b = declaredRowName(cols, { actor_name: "관리자B", target_name: "대상B" });
    expect(a).toBe("관리자A → 대상A");
    expect(b).toBe("관리자B → 대상B");
  });

  it("백업(backup): 파일명으로 구별된다(전체 경로가 아니라 목록 열과 같은 파일명만)", () => {
    const cols = REGISTRY.backup.columns;
    const a = declaredRowName(cols, { path: "var/exports/web-20260101-000000.sqlite3" });
    const b = declaredRowName(cols, { path: "var/exports/web-20260102-000000.sqlite3" });
    expect(a).toBe("web-20260101-000000.sqlite3");
    expect(b).toBe("web-20260102-000000.sqlite3");
  });

  it("복구 리허설(restore-drills): 원본 백업 이름으로 구별된다", () => {
    const cols = REGISTRY["restore-drills"].columns;
    const a = declaredRowName(cols, { source_label: "web-20260101.sqlite3", started_at: "2026-08-01T00:00:00Z" });
    const b = declaredRowName(cols, { source_label: "web-20260102.sqlite3", started_at: "2026-08-01T00:00:00Z" });
    expect(a).toContain("web-20260101.sqlite3");
    expect(b).toContain("web-20260102.sqlite3");
    expect(a).not.toBe(b);
  });

  it("AI 사용 상한(ai-quotas): 대상 + 기간으로 구별된다", () => {
    const cols = REGISTRY["ai-quotas"].columns;
    const a = declaredRowName(cols, { scope_type: "user", user_name: "사용자A", period: "day" });
    const b = declaredRowName(cols, { scope_type: "user", user_name: "사용자B", period: "day" });
    expect(a).toBe("사용자A / 하루");
    expect(b).toBe("사용자B / 하루");
  });

  it("문서 자동 생성(documents): 미리보기 제목, 없으면 기간+상태로 구별된다", () => {
    const cols = REGISTRY.documents.columns;
    const a = declaredRowName(cols, { preview: { title: "8월 보고서" } });
    const b = declaredRowName(cols, { status: "pending", period: "2026-08" });
    expect(a).toBe("8월 보고서");
    expect(b).toBe("기간 2026-08 문서 (대기)");
  });

  it("조직도(org-tree): 조직/부서 구분 + 이름으로 구별된다", () => {
    const cols = REGISTRY["org-tree"].columns;
    const a = declaredRowName(cols, { kind: "organization", name: "조직A" });
    const b = declaredRowName(cols, { kind: "department", name: "부서A" });
    expect(a).toBe("조직 조직A");
    expect(b).toBe("부서 부서A");
  });

  it("작업 큐(jobs): 같은 유형끼리도(유형 필터로 좁혀 봐도) 생성 시각으로 구별된다", () => {
    const cols = REGISTRY.jobs.columns;
    const a = declaredRowName(cols, { job_type: "chat_message", created_at: "2026-08-01T00:00:00Z" });
    const b = declaredRowName(cols, { job_type: "chat_message", created_at: "2026-08-02T00:00:00Z" });
    expect(a).toContain("채팅 메시지");
    expect(b).toContain("채팅 메시지");
    expect(a).not.toBe(b);
    // 요청자 이름/이메일은 이 화면이 일부러 감추는 값이라(app/jobs/router.py _job_view) 안 들어간다.
    expect(a).not.toContain("@");
  });
});
