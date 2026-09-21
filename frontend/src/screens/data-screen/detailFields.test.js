/* qa-contract-change: 조직도(org-tree) 설정이 registry 를 떠나 조직 콘솔(screens/org/)로 재구성되면서 그 설정의 rowName 을 검사하던 케이스가 대상을 잃었다 — 남은 화면들(jobs·admin-notifications)이 같은 규칙을 계속 진다. */
import { describe, it, expect } from "vitest";

import { EMPTY_DETAIL_LABEL, detailTitle, isEmptyDetailValue, partitionDetailFields } from "./detailFields.js";
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
  it("감사 이상 징후: 제목이 배지 원시값('high')이 아니라 서버 요약(title)+행위자다", () => {
    const cols = REGISTRY["audit-anomalies"].columns;
    // title은 kind별 고정 문자열이다(app/audit/anomalies.py) — actor_name까지 있어야 실제
    // 서버 응답 모양과 같다(registry-row-name.test.jsx 참고).
    const row = { severity: "high", title: "실패가 몰려 있습니다", actor_name: "홍길동" };
    expect(detailTitle(row, cols)).toBe("실패가 몰려 있습니다 / 홍길동");
    expect(detailTitle(row, cols)).not.toBe("high");
  });

  it("작업 큐: 같은 날 생성된 서로 다른 유형의 작업이 제목으로 구별된다", () => {
    const cols = REGISTRY.jobs.columns;
    const a = detailTitle({ job_type: "chat_message", created_at: "2026-08-01T00:00:00Z" }, cols);
    const b = detailTitle({ job_type: "schedule_run", created_at: "2026-08-01T00:00:00Z" }, cols);
    expect(a).toContain("채팅 메시지");
    expect(a).not.toBe(b);
  });

  it("rowName 표식이 없는 화면(알림)은 이전과 동일하게 columns[0] 원시값으로 폴백한다", () => {
    const cols = REGISTRY["admin-notifications"].columns;
    expect(detailTitle({ title: "승인 요청이 도착했습니다" }, cols)).toBe("승인 요청이 도착했습니다");
  });

  it("열 정의가 없으면 id로 폴백한다(회귀 없음)", () => {
    expect(detailTitle({ id: 42 }, undefined)).toBe("42");
    expect(detailTitle({ id: 42 }, [])).toBe("42");
  });
});

/* 상세의 빈 값은 한 줄이다 (D-501) — 무엇이 「없음」인가를 한 함수가 정한다. */
describe("partitionDetailFields — 빈 줄을 가른다", () => {
  it("원시 값이 비었거나 그린 값이 `-` 이면 빈 줄이고, 순서는 그대로다", () => {
    const fields = [
      { key: "id", label: "작업 ID" },
      { key: "key", label: "중복 방지 키" },
      { key: "err", label: "오류", render: (r) => r.err || "-" },
      { key: "who", label: "요청자" },
    ];
    const { filled, empty } = partitionDetailFields(fields, { id: "j1", key: "", err: null, who: "u-1" });
    expect(filled.map((x) => [x.field.label, x.value])).toEqual([["작업 ID", "j1"], ["요청자", "u-1"]]);
    expect(empty.map((f) => f.label)).toEqual(["중복 방지 키", "오류"]);
  });

  it("그린 값이 요소라 글자로 못 가르는 필드는 스스로 `isEmpty` 를 말한다 — 그것이 이긴다", () => {
    const element = { type: "span", props: {} };
    const fields = [
      { key: "started_at", label: "시작", isEmpty: (r) => r.started_at == null, render: () => element },
      { key: "status", label: "상태", isEmpty: () => false, render: () => "-" },
    ];
    const { filled, empty } = partitionDetailFields(fields, { started_at: null, status: null });
    expect(empty.map((f) => f.label)).toEqual(["시작"]);
    // `isEmpty` 가 「있다」고 말하면 그린 값이 `-` 여도 줄로 선다.
    expect(filled.map((x) => x.field.label)).toEqual(["상태"]);
  });

  it("빈 줄의 이름표는 「값 없음」 하나다", () => {
    expect(EMPTY_DETAIL_LABEL).toBe("값 없음");
    expect(isEmptyDetailValue({}, {}, false)).toBe(true);
    expect(isEmptyDetailValue({}, {}, 0)).toBe(false);
  });
});
