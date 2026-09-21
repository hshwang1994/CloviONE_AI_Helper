import React from "react";
import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { stableKey, useGuardedMutation } from "./useGuardedMutation.js";

/* 같은 요청은 끝나기 전에 한 번만 나간다 (P4 — 더블클릭 · Enter 연타).
 *
 * 여기서 재는 것은 **같은 틱**의 두 번이다. 사람의 두 번째 클릭은 TanStack 의 알림(다음
 * 매크로태스크)보다 늦게 올 때가 많아서 `isPending` 으로 꺼지는 단추만으로도 대개 막히지만,
 * 키보드 처리기와 숨은 제출 단추는 그 알림을 기다리지 않는다. 그 창을 결정적으로 재현하는
 * 방법이 같은 틱에 두 번 부르는 것이다. */

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return function Wrap({ children }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe("useGuardedMutation", () => {
  it("같은 변수를 같은 틱에 두 번 보내면 요청은 한 번이고, mutateAsync 는 같은 약속을 돌려준다", async () => {
    const gate = deferred();
    const mutationFn = vi.fn(() => gate.promise);
    const { result } = renderHook(() => useGuardedMutation({ mutationFn }), { wrapper: wrapper() });

    let first;
    let second;
    act(() => {
      first = result.current.mutateAsync({ title: "같은 티켓", project_id: "p1" });
      second = result.current.mutateAsync({ project_id: "p1", title: "같은 티켓" });
    });
    expect(second).toBe(first);
    await act(async () => { gate.resolve({ ok: true }); await first; });
    expect(mutationFn).toHaveBeenCalledTimes(1);
    await expect(second).resolves.toEqual({ ok: true });
  });

  it("mutate 를 같은 틱에 두 번 불러도 요청은 한 번이다 — 호출별 onSuccess 도 한 번이다", async () => {
    const gate = deferred();
    const mutationFn = vi.fn(() => gate.promise);
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useGuardedMutation({ mutationFn }), { wrapper: wrapper() });

    act(() => {
      result.current.mutate("안녕하세요", { onSuccess });
      result.current.mutate("안녕하세요", { onSuccess });
    });
    await act(async () => { gate.resolve("sent"); });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mutationFn).toHaveBeenCalledTimes(1);
    expect(mutationFn.mock.calls[0][0]).toBe("안녕하세요");
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it("변수가 다르면 둘 다 나간다 — 빠르게 친 서로 다른 채팅 두 줄을 잃지 않는다", async () => {
    const mutationFn = vi.fn(async (text) => text);
    const { result } = renderHook(() => useGuardedMutation({ mutationFn }), { wrapper: wrapper() });

    await act(async () => {
      await Promise.all([result.current.mutateAsync("첫째 줄"), result.current.mutateAsync("둘째 줄")]);
    });
    expect(mutationFn.mock.calls.map((c) => c[0])).toEqual(["첫째 줄", "둘째 줄"]);
  });

  it("끝난 뒤에는 같은 값을 다시 보낼 수 있다", async () => {
    const mutationFn = vi.fn(async () => "ok");
    const { result } = renderHook(() => useGuardedMutation({ mutationFn }), { wrapper: wrapper() });

    await act(async () => { await result.current.mutateAsync({ id: "t1" }); });
    await act(async () => { await result.current.mutateAsync({ id: "t1" }); });
    expect(mutationFn).toHaveBeenCalledTimes(2);
  });

  it("실패해도 키를 푼다 — 같은 값으로 다시 시도할 수 있다", async () => {
    const mutationFn = vi.fn()
      .mockRejectedValueOnce(Object.assign(new Error("서버에 연결할 수 없습니다."), { kind: "network" }))
      .mockResolvedValueOnce("ok");
    const { result } = renderHook(() => useGuardedMutation({ mutationFn }), { wrapper: wrapper() });

    await act(async () => {
      await expect(result.current.mutateAsync("다시")).rejects.toThrow("서버에 연결할 수 없습니다.");
    });
    await act(async () => { await expect(result.current.mutateAsync("다시")).resolves.toBe("ok"); });
    expect(mutationFn).toHaveBeenCalledTimes(2);
  });

  it("mutate 가 실패해도 처리되지 않은 거부가 새지 않고, 다음 호출은 나간다", async () => {
    const mutationFn = vi.fn()
      .mockRejectedValueOnce(new Error("저장하지 못했습니다."))
      .mockResolvedValueOnce("ok");
    const onError = vi.fn();
    const { result } = renderHook(() => useGuardedMutation({ mutationFn, onError }), { wrapper: wrapper() });

    act(() => { result.current.mutate("값"); });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(onError).toHaveBeenCalledTimes(1);
    act(() => { result.current.mutate("값"); });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mutationFn).toHaveBeenCalledTimes(2);
  });

  it("key 를 주면 그 기준으로 가른다 — 값이 달라도 같은 키면 한 번이다", async () => {
    const gate = deferred();
    const mutationFn = vi.fn(() => gate.promise);
    const { result } = renderHook(
      () => useGuardedMutation({ mutationFn, key: () => "image" }),
      { wrapper: wrapper() },
    );

    act(() => {
      result.current.mutate(new File(["a"], "paste.png", { type: "image/png" }));
      result.current.mutate(new File(["b"], "paste.png", { type: "image/png" }));
    });
    await act(async () => { gate.resolve("ok"); });
    expect(mutationFn).toHaveBeenCalledTimes(1);
  });

  it("값으로 비교할 수 없는 변수는 그 객체 자신이 키다 — 서로 다른 FormData 는 둘 다 나간다", async () => {
    const gate = deferred();
    const mutationFn = vi.fn(() => gate.promise);
    const { result } = renderHook(() => useGuardedMutation({ mutationFn }), { wrapper: wrapper() });
    const same = new FormData();

    act(() => {
      result.current.mutate(same);
      result.current.mutate(same);
      result.current.mutate(new FormData());
    });
    await act(async () => { gate.resolve("ok"); });
    expect(mutationFn).toHaveBeenCalledTimes(2);
  });

  it("useMutation 의 나머지 값은 그대로 준다", async () => {
    const mutationFn = vi.fn(async (v) => v);
    const { result } = renderHook(() => useGuardedMutation({ mutationFn }), { wrapper: wrapper() });

    expect(result.current.isPending).toBe(false);
    expect(typeof result.current.reset).toBe("function");
    await act(async () => { await result.current.mutateAsync("값"); });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.variables).toBe("값");
    expect(result.current.data).toBe("값");
    act(() => { result.current.reset(); });
    await waitFor(() => expect(result.current.isIdle).toBe(true));
  });
});

describe("stableKey", () => {
  it("객체의 키 순서와 undefined 값은 키를 바꾸지 않는다 — JSON 본문과 같은 규칙이다", () => {
    expect(stableKey({ a: 1, b: "x" })).toBe(stableKey({ b: "x", a: 1 }));
    expect(stableKey({ a: 1, c: undefined })).toBe(stableKey({ a: 1 }));
    expect(stableKey({ a: [1, { z: 2, y: 3 }] })).toBe(stableKey({ a: [1, { y: 3, z: 2 }] }));
  });

  it("값이 다르면 키가 다르다 — 형이 달라도 다르다", () => {
    expect(stableKey("1")).not.toBe(stableKey(1));
    expect(stableKey(true)).not.toBe(stableKey("true"));
    expect(stableKey(null)).not.toBe(stableKey(undefined));
    expect(stableKey({ a: 1 })).not.toBe(stableKey({ a: 2 }));
    expect(stableKey([1, 2])).not.toBe(stableKey([2, 1]));
  });

  it("순환 참조가 있어도 멈추지 않는다", () => {
    const loop = { name: "고리" };
    loop.self = loop;
    expect(() => stableKey(loop)).not.toThrow();
    expect(stableKey(loop)).toBe(stableKey(loop));
  });
});
