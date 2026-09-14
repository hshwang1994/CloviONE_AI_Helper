import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";

/* 작성 중인 값이 세션에 남는다 (D-483).
 *
 *  1) 적은 값은 곧바로 저장소에 적히고, 새 훅(다른 트리)이 같은 키로 다시 읽는다.
 *  2) 키가 바뀌면 그 키의 초안을 읽는다 — 다른 회차의 글이 이 회차 칸에 오지 않는다.
 *  3) 빈 초안은 저장하지 않고, `clear` 는 지운다.
 *  4) 키가 없으면(회차 미선택) 저장하지 않는다. */

import { readSessionDraft, useSessionDraft } from "./useSessionDraft.js";

const EMPTY = { kind: "decision", body: "" };

beforeEach(() => {
  window.sessionStorage.clear();
});

describe("useSessionDraft", () => {
  it("적은 값이 저장소에 남고, 새 훅이 같은 키로 되읽는다", () => {
    const first = renderHook(() => useSessionDraft("cv.meetingDraft.v1:sp-1", EMPTY));
    act(() => first.result.current[1]((prev) => ({ ...prev, body: "아직 적는 중" })));
    expect(readSessionDraft("cv.meetingDraft.v1:sp-1")).toEqual({ kind: "decision", body: "아직 적는 중" });
    first.unmount();
    const second = renderHook(() => useSessionDraft("cv.meetingDraft.v1:sp-1", EMPTY));
    expect(second.result.current[0]).toEqual({ kind: "decision", body: "아직 적는 중" });
  });

  it("🔴 키가 바뀌면 그 키의 초안을 읽는다 — 다른 회차의 글이 섞이지 않는다", () => {
    window.sessionStorage.setItem("cv.meetingDraft.v1:sp-2", JSON.stringify({ kind: "action", body: "다른 회차" }));
    const hook = renderHook(({ key }) => useSessionDraft(key, EMPTY), { initialProps: { key: "cv.meetingDraft.v1:sp-1" } });
    act(() => hook.result.current[1]({ kind: "decision", body: "첫 회차" }));
    hook.rerender({ key: "cv.meetingDraft.v1:sp-2" });
    expect(hook.result.current[0]).toEqual({ kind: "action", body: "다른 회차" });
    hook.rerender({ key: "cv.meetingDraft.v1:sp-1" });
    expect(hook.result.current[0]).toEqual({ kind: "decision", body: "첫 회차" });
  });

  it("빈 초안은 저장하지 않고, clear 는 지운다", () => {
    const hook = renderHook(() => useSessionDraft("cv.meetingDraft.v1:sp-1", EMPTY));
    act(() => hook.result.current[1]({ ...EMPTY }));
    expect(readSessionDraft("cv.meetingDraft.v1:sp-1")).toBeUndefined();
    act(() => hook.result.current[1]({ kind: "decision", body: "글" }));
    expect(readSessionDraft("cv.meetingDraft.v1:sp-1")).toBeTruthy();
    act(() => hook.result.current[2]());
    expect(readSessionDraft("cv.meetingDraft.v1:sp-1")).toBeUndefined();
    expect(hook.result.current[0]).toEqual(EMPTY);
  });

  it("키가 없으면 저장하지 않는다 — 회차를 안 골랐을 때", () => {
    const hook = renderHook(() => useSessionDraft(null, EMPTY));
    act(() => hook.result.current[1]({ kind: "decision", body: "글" }));
    expect(hook.result.current[0].body).toBe("글");
    expect(window.sessionStorage.length).toBe(0);
  });
});
