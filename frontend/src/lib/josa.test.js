/* 조사(을/를, 은/는)를 받침으로 고른다 — 화면 문구의 주어가 데이터일 때.
 *
 * 왜 시험이 필요한가: 2026-09-06 배포 환경(clovirassist.gooddi.lab)에서 관리자 폼의 필수
 * 칸 오류가 「제목을(를) 입력하세요.」로 나오는 것을 실측했다. 두 조사를 나란히 적은 것은
 * 한국어 문장이 아니라 미결정 상태를 화면에 내보낸 것이다. 규칙은 코드가 아는 것이므로
 * 코드가 고른다.
 *
 * 반례를 함께 잰다 — 받침 있는 낱말과 없는 낱말이 **다른** 조사를 받아야 하고, 한글이
 * 아닌 낱말과 빈 문자열에서도 깨지지 않아야 한다. 한쪽만 재면 「항상 을」도 통과한다.
 */
import { describe, it, expect } from "vitest";
import { hasFinalConsonant, objectParticle, topicParticle } from "./format.js";

describe("objectParticle — 목적격 조사", () => {
  it("받침이 있으면 '을'이다", () => {
    expect(objectParticle("제목")).toBe("을");
    expect(objectParticle("이름")).toBe("을");
    expect(objectParticle("직책")).toBe("을");
    expect(objectParticle("실행 시각")).toBe("을");
  });

  it("받침이 없으면 '를'이다 — 반례", () => {
    expect(objectParticle("대상자")).toBe("를");
    expect(objectParticle("주기")).toBe("를");
    expect(objectParticle("메모")).toBe("를");
  });

  it("한글이 아니면 '를'로 읽는다", () => {
    expect(objectParticle("Cron")).toBe("를");
    expect(objectParticle("2026-09-06")).toBe("를");
    expect(objectParticle("")).toBe("를");
    expect(objectParticle(null)).toBe("를");
    expect(objectParticle(undefined)).toBe("를");
  });

  it("낱말마다 다른 답을 낸다 — '항상 같은 조사'를 배제한다", () => {
    const answers = new Set(["제목", "대상자", "이름", "주기"].map(objectParticle));
    expect(answers.size).toBe(2);
  });
});

describe("hasFinalConsonant — 두 조사가 함께 보는 하나의 판정", () => {
  it("받침 유무를 낱말별로 가른다", () => {
    expect(hasFinalConsonant("제목")).toBe(true);
    expect(hasFinalConsonant("대상자")).toBe(false);
    expect(hasFinalConsonant("")).toBe(false);
  });

  it("한글이 아닌 끝은 받침 없는 쪽으로 읽는다 — 백엔드(app/core/text.py)와 같은 답", () => {
    expect(hasFinalConsonant("job")).toBe(false);
    expect(hasFinalConsonant("Cron")).toBe(false);
    expect(hasFinalConsonant("2026")).toBe(false);
  });
});

describe("topicParticle — 주제 조사", () => {
  it("받침이 있으면 '은', 없으면 '는'이다", () => {
    expect(topicParticle("상태")).toBe("는");
    expect(topicParticle("제목")).toBe("은");
    expect(topicParticle("Cron")).toBe("는");
    expect(topicParticle("")).toBe("는");
  });

  it("목적격과 짝이 어긋나지 않는다 — 같은 낱말이면 받침 판정도 같다", () => {
    for (const w of ["제목", "상태", "이름", "주기", "Cron"]) {
      const hasBatchim = objectParticle(w) === "을";
      expect(topicParticle(w)).toBe(hasBatchim ? "은" : "는");
    }
  });
});
