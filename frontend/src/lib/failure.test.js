import { describe, expect, it } from "vitest";

import { errorText, failureText, latestMutation } from "./failure.js";

/* 실패 문장을 고르는 규칙 — 자리마다 메시지 박스가 이 규칙 하나로 서고 걷힌다(lib/failure.js). */

const ok = (at) => ({ submittedAt: at, isError: false, error: null });
const bad = (at, message) => ({ submittedAt: at, isError: true, error: message === undefined ? null : { message } });
const idle = () => ({ submittedAt: 0, isError: false, error: null });

describe("failureText — 가장 나중에 보낸 요청 하나만 말한다", () => {
  it("실패한 요청이 하나면 서버 문장을, 문장이 없으면 그 동작의 기본 문장을 준다", () => {
    expect(failureText([bad(10, "권한이 없습니다."), "복원하지 못했습니다."])).toBe("권한이 없습니다.");
    expect(failureText([bad(10), "복원하지 못했습니다."])).toBe("복원하지 못했습니다.");
  });

  it("다음 시도가 성공하면 앞의 실패는 서지 않는다(새 요청 성공 시 해제)", () => {
    expect(failureText([bad(10, "실패"), "복원"], [ok(20), "삭제"])).toBeNull();
  });

  it("다음 시도가 아직 결과가 없어도 앞의 실패는 걷힌다(다음 시도 시 해제)", () => {
    const pending = { submittedAt: 30, isError: false, error: null };
    expect(failureText([bad(10, "실패"), "복원"], [pending, "삭제"])).toBeNull();
  });

  it("앞의 성공 뒤에 실패하면 그 실패를 말한다 — 기본 문장도 그 동작의 것이다", () => {
    expect(failureText([ok(10), "복원하지 못했습니다."], [bad(20), "삭제하지 못했습니다."])).toBe("삭제하지 못했습니다.");
  });

  it("보낸 적 없는 요청 · reset 한 요청은 후보가 아니다(모달을 다시 열면 잔존 0)", () => {
    expect(failureText([idle(), "복원"], null, undefined)).toBeNull();
    expect(failureText()).toBeNull();
  });
});

describe("errorText — 손으로 부른 요청", () => {
  it("서버 문장이 먼저이고 없으면 기본 문장이다", () => {
    expect(errorText({ message: "용량이 모자랍니다." }, "올리지 못했습니다.")).toBe("용량이 모자랍니다.");
    expect(errorText(null, "올리지 못했습니다.")).toBe("올리지 못했습니다.");
    expect(errorText(undefined, undefined)).toBeNull();
  });
});

describe("latestMutation — 한 자리의 요청 중 가장 나중 것", () => {
  it("보낸 시각이 가장 늦은 요청을 준다 · 하나도 안 보냈으면 null", () => {
    const a = ok(10); const b = bad(20, "x"); const c = idle();
    expect(latestMutation(a, b, c)).toBe(b);
    expect(latestMutation(c, null)).toBeNull();
  });
});
