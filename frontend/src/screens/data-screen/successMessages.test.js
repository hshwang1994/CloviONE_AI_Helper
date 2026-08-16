import { describe, it, expect } from "vitest";
import { ACTION_SUCCESS_MESSAGES, GENERIC_SUCCESS_MESSAGE, successMessageFor } from "./successMessages.js";

/* 기본 성공 토스트 문구 사전 (PA-RC-0025).
 *
 * 예전엔 DataScreen.jsx/SubListDrawer.jsx가 각자 `라벨 + " 완료"`로 토스트를 만들어
 * "삭제 완료"처럼 마침표 없는 명사형이 났다. 이 사전은 그 대신 라벨마다 손으로 확인한
 * 문장형 성공 문구를 낸다 — 여기서는 그 조회 함수(successMessageFor) 자체가 정확히
 * 문서(docs/UX_WRITING.md §3-1)와 같은 규칙을 지키는지만 본다. 실제 화면 소비처(삭제 버튼을
 * 눌렀을 때 실제로 뜨는 토스트)는 datascreen-success-toast.test.jsx가 렌더 수준에서 본다.
 */
describe("successMessageFor (PA-RC-0025)", () => {
  it("실제 버그 리포트의 사례 — '삭제'는 더 이상 '삭제 완료'가 아니라 문장형이다", () => {
    expect(successMessageFor("삭제")).toBe("삭제했습니다.");
  });

  it("사전에 있는 모든 문구는 마침표로 끝난다(docs/UX_WRITING.md §2)", () => {
    for (const [label, msg] of Object.entries(ACTION_SUCCESS_MESSAGES)) {
      expect(msg.endsWith("."), `"${label}" → "${msg}"에 마침표가 없다`).toBe(true);
    }
  });

  it("사전에 있는 문구는 하나도 '라벨 완료' 패턴(명사+완료, 마침표 없음)이 아니다", () => {
    for (const msg of Object.values(ACTION_SUCCESS_MESSAGES)) {
      expect(/완료$/.test(msg)).toBe(false);
      expect(/성공$/.test(msg)).toBe(false);
    }
  });

  it("헤더 작업 라벨의 선행 '+ '를 지우고 조회한다(DataScreen.jsx의 옛 stripping과 동일 동작)", () => {
    // 지금 등록된 default-path 헤더 액션 중에는 '+ ' 접두 라벨이 없지만(전부 a.result가 있다),
    // 이 stripping 자체는 앞으로 그런 라벨이 생겨도 안전하도록 보존한 기존 동작이다.
    expect(successMessageFor("+ 삭제")).toBe(successMessageFor("삭제"));
  });

  it("사전에 없는 새 라벨은 옛 '라벨 완료' 패턴이 아니라 문장형 기본값으로 떨어진다", () => {
    expect(successMessageFor("아직-등록-안-된-액션")).toBe(GENERIC_SUCCESS_MESSAGE);
    expect(GENERIC_SUCCESS_MESSAGE.endsWith(".")).toBe(true);
    expect(GENERIC_SUCCESS_MESSAGE).not.toMatch(/완료$/);
  });

  it("빈 라벨/undefined도 안전하게 제네릭 문구로 떨어진다(throw하지 않는다)", () => {
    expect(successMessageFor("")).toBe(GENERIC_SUCCESS_MESSAGE);
    expect(successMessageFor(undefined)).toBe(GENERIC_SUCCESS_MESSAGE);
  });

  it("PA-RC-0025 acceptance criteria가 명시한 예시 매핑을 직접 확인한다", () => {
    expect(ACTION_SUCCESS_MESSAGES["삭제"]).toBe("삭제했습니다.");
    expect(ACTION_SUCCESS_MESSAGES["보관"]).toBe("보관했습니다.");
    expect(ACTION_SUCCESS_MESSAGES["활성화"]).toBe("활성화했습니다.");
  });

  it("복합 라벨('이 버전으로 롤백')도 문자열 절단이 아니라 온전한 사전 값을 낸다", () => {
    // 라벨을 자르거나 접두어만 남겨 억지로 동사를 만들지 않았는지 확인 — 전체 라벨이 그대로
    // 키이고, 값도 그 라벨 전체를 살린 문장이다(PA-RC-0025: 기계적 conjugation 금지).
    expect(successMessageFor("이 버전으로 롤백")).toBe("이 버전으로 롤백했습니다.");
  });
});
