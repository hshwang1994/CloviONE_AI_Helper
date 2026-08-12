import { describe, it, expect } from "vitest";

import { detailTitle } from "./detailFields.js";
import { REGISTRY } from "../registry.js";

/* SEM-01(행 버튼)이 고친 것과 같은 근본 원인의 또 다른 소비처.
 *
 * kit.jsx의 rowOpenLabel()은 declaredRowName()을 먼저 보지만, DataScreen.jsx가 상세 모달/수정
 * 드로어 제목에 쓰는 detailTitle()은 그 기준을 몰랐다 — columns[0]만 봤다. 그래서 첫 열이
 * render()를 쓰는 화면(감사 이상 징후의 중요도 배지, 작업 큐의 생성 시각)은 "상세 보기" 버튼은
 * SEM-01로 이미 행마다 구별됐는데 같은 행을 열었을 때 드로어 제목만 여전히 원시 값(raw
 * enum "high"/"medium"/"low", 또는 같은 날 여러 건이면 서로 구별 안 되는 시각)이었다.
 */
describe("detailTitle — 선언된 rowName을 columns[0] 폴백보다 먼저 쓴다", () => {
  it("감사 이상 징후: 제목이 배지 원시값('high')이 아니라 서버 요약(title)이다", () => {
    const cols = REGISTRY["audit-anomalies"].columns;
    const row = { severity: "high", title: "실패 급증: 홍길동" };
    expect(detailTitle(row, cols)).toBe("실패 급증: 홍길동");
    expect(detailTitle(row, cols)).not.toBe("high");
  });

  it("작업 큐: 같은 날 생성된 서로 다른 유형의 작업이 제목으로 구별된다", () => {
    const cols = REGISTRY.jobs.columns;
    const a = detailTitle({ job_type: "chat_message", created_at: "2026-08-01T00:00:00Z" }, cols);
    const b = detailTitle({ job_type: "schedule_run", created_at: "2026-08-01T00:00:00Z" }, cols);
    expect(a).toContain("채팅 메시지");
    expect(a).not.toBe(b);
  });

  it("조직도: 부서 행 제목이 '부서 <이름>'이다(들여쓰기 트리 JSX가 아니라)", () => {
    const cols = REGISTRY["org-tree"].columns;
    expect(detailTitle({ kind: "department", name: "개발팀" }, cols)).toBe("부서 개발팀");
  });

  it("rowName 표식이 없는 화면(알림)은 이전과 동일하게 columns[0] 원시값으로 폴백한다", () => {
    const cols = REGISTRY.notifications.columns;
    expect(detailTitle({ title: "승인 요청이 도착했습니다" }, cols)).toBe("승인 요청이 도착했습니다");
  });

  it("열 정의가 없으면 id로 폴백한다(회귀 없음)", () => {
    expect(detailTitle({ id: 42 }, undefined)).toBe("42");
    expect(detailTitle({ id: 42 }, [])).toBe("42");
  });
});
