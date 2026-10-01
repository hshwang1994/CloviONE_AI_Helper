import React from "react";
import { describe, it, expect, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { useInstantSave } from "./useInstantSave.js";

/* 즉시 저장 설정의 저장 (D-525) — 누른 순간 반영하고, 같은 대상의 요청은 한 줄로 보내며, 서버 값으로 확정하는 것은
 * 줄의 마지막 요청뿐이다. 화면 쪽 시험(profile · mail-status · ai-settings)이 「저장 중에도 스위치가 켜져 있다」를 잰다.
 * 여기서는 훅의 규칙 셋을 직접 잰다: 줄 선 요청의 순서, 앞 응답이 뒤 토글을 되돌리지 않음, 실패의 되돌림 범위. */

function setup(initial = { muted: [] }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  qc.setQueryData(["prefs"], initial);
  function wrapper({ children }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { qc, wrapper };
}

function gate() {
  const calls = [];
  const fn = vi.fn((vars) => new Promise((resolve, reject) => calls.push({ vars, resolve, reject })));
  return { fn, calls };
}

const apply = (old, vars) => ({ ...old, muted: vars.muted });

describe("useInstantSave", () => {
  it("누른 순간 캐시에 반영하고, 둘째 요청은 첫 응답 뒤에 나가며, 응답으로 확정하는 것은 마지막 하나다", async () => {
    const { qc, wrapper } = setup();
    const { fn, calls } = gate();
    const onSaved = vi.fn();
    const { result } = renderHook(
      () => useInstantSave({ queryKey: ["prefs"], mutationFn: fn, apply, fromResponse: (data) => data, onSaved }),
      { wrapper },
    );
    act(() => result.current.mutate({ muted: ["a"] }));
    await waitFor(() => expect(qc.getQueryData(["prefs"])).toEqual({ muted: ["a"] }));
    act(() => result.current.mutate({ muted: ["a", "b"] }));
    await waitFor(() => expect(qc.getQueryData(["prefs"])).toEqual({ muted: ["a", "b"] }));
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(1));
    // 둘째는 줄에서 기다린다 — 첫 응답 전에는 나가지 않는다.
    expect(fn).toHaveBeenCalledTimes(1);

    await act(async () => { calls[0].resolve({ muted: ["a"], from: "first" }); });
    // 첫 응답은 캐시에 쓰지 않는다 — 쓰면 줄 선 둘째 토글(b)이 잠깐 되돌아간다.
    expect(qc.getQueryData(["prefs"])).toEqual({ muted: ["a", "b"] });
    expect(onSaved).not.toHaveBeenCalled();
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
    expect(calls[1].vars).toEqual({ muted: ["a", "b"] });

    await act(async () => { calls[1].resolve({ muted: ["a", "b"], from: "last" }); });
    await waitFor(() => expect(qc.getQueryData(["prefs"])).toEqual({ muted: ["a", "b"], from: "last" }));
    expect(onSaved).toHaveBeenCalledTimes(1);
  });

  it("응답으로 확정하지 않는 저장은 줄이 빌 때 그 쿼리를 한 번만 다시 읽는다", async () => {
    const { qc, wrapper } = setup();
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const { fn, calls } = gate();
    const { result } = renderHook(() => useInstantSave({ queryKey: ["prefs"], mutationFn: fn, apply }), { wrapper });
    act(() => result.current.mutate({ muted: ["a"] }));
    act(() => result.current.mutate({ muted: ["a", "b"] }));
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(1));
    await act(async () => { calls[0].resolve({}); });
    expect(invalidate).not.toHaveBeenCalled();
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
    await act(async () => { calls[1].resolve({}); });
    await waitFor(() => expect(invalidate).toHaveBeenCalledTimes(1));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["prefs"] });
  });

  it("마지막 요청이 실패하면 이전 값으로 되돌리고, 뒤에 줄 선 요청이 있으면 되돌리지 않는다", async () => {
    const { qc, wrapper } = setup();
    const onError = vi.fn();
    const { fn, calls } = gate();
    const { result } = renderHook(
      () => useInstantSave({ queryKey: ["prefs"], mutationFn: fn, apply, fromResponse: (d) => d, onError }),
      { wrapper },
    );
    // 홀로 실패 — 마지막이므로 누르기 전 값으로 돌아간다.
    act(() => result.current.mutate({ muted: ["a"] }));
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(1));
    await act(async () => { calls[0].reject(new Error("저장하지 못했습니다.")); });
    await waitFor(() => expect(qc.getQueryData(["prefs"])).toEqual({ muted: [] }));
    expect(onError).toHaveBeenCalledTimes(1);

    // 줄 선 요청이 있는 동안의 실패 — 뒤 요청이 최신 의도를 통째로 나르므로 화면을 되돌리지 않는다.
    act(() => result.current.mutate({ muted: ["x"] }));
    act(() => result.current.mutate({ muted: ["x", "y"] }));
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
    await act(async () => { calls[1].reject(new Error("저장하지 못했습니다.")); });
    expect(onError).toHaveBeenCalledTimes(2);
    expect(qc.getQueryData(["prefs"])).toEqual({ muted: ["x", "y"] });
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(3));
    await act(async () => { calls[2].resolve({ muted: ["x", "y"] }); });
    await waitFor(() => expect(qc.getQueryData(["prefs"])).toEqual({ muted: ["x", "y"] }));
  });
});
