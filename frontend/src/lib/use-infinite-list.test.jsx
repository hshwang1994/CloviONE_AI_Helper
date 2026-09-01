import React from "react";
import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/* 목록을 묶음으로 받는 훅의 계약.
 *
 * 여기서 재는 것은 「다음을 부를 수 있는가」가 아니라 **무엇을 부르는가**다 — 봉투가 셋이고
 * 각각 다음 지점을 다르게 계산하는데, 그 계산이 틀리면 행이 조용히 건너뛰어지거나 마지막
 * 묶음에서 한 번 더 부른다. 둘 다 오류를 안 낸다. */

import {
  CHUNK, cursorEnvelope, offsetEnvelope, pageEnvelope, useInfiniteList, useResetScrollOnKeyChange,
} from "./useInfiniteList.js";

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrap({ children }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const row = (n) => ({ id: `r${n}`, name: `행 ${n}` });

describe("useInfiniteList — 쪽 봉투", () => {
  it("첫 묶음은 page=1 이고, 기본 건수는 CHUNK 다", async () => {
    const fetch = vi.fn(async () => ({ items: [row(1)], total: 3 }));
    const { result } = renderHook(
      () => useInfiniteList({ key: ["k"], fetch }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(fetch).toHaveBeenCalledWith({ page: 1, page_size: CHUNK });
    expect(result.current.total).toBe(3);
    expect(result.current.hasNext).toBe(true);
  });

  it("다음 묶음을 받으면 이어 붙는다 — 갈아 끼우지 않는다", async () => {
    const fetch = vi.fn(async ({ page }) => ({ items: [row(page)], total: 3 }));
    const { result } = renderHook(
      () => useInfiniteList({ key: ["k"], fetch, size: 1 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    act(() => { result.current.fetchNext(); });
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    expect(fetch).toHaveBeenLastCalledWith({ page: 2, page_size: 1 });
    expect(result.current.rows.map((r) => r.id)).toEqual(["r1", "r2"]);
    expect(result.current.loaded).toBe(2);
  });

  it("total 만큼 받으면 더 안 부른다 — 마지막 묶음에서 한 번 더 부르지 않는다", async () => {
    const fetch = vi.fn(async () => ({ items: [row(1), row(2)], total: 2 }));
    const { result } = renderHook(
      () => useInfiniteList({ key: ["k"], fetch, size: 2 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    expect(result.current.hasNext).toBe(false);
  });

  it("total 이 없는 응답은 마지막 묶음이 가득 찼는지로 판정한다 — DS-22 폴백", async () => {
    const full = vi.fn(async () => ({ items: [row(1), row(2)] }));
    const { result: a } = renderHook(
      () => useInfiniteList({ key: ["full"], fetch: full, size: 2 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(a.current.rows).toHaveLength(2));
    expect(a.current.hasNext).toBe(true);

    const short = vi.fn(async () => ({ items: [row(1)] }));
    const { result: b } = renderHook(
      () => useInfiniteList({ key: ["short"], fetch: short, size: 2 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(b.current.rows).toHaveLength(1));
    expect(b.current.hasNext).toBe(false);
  });
});
describe("useInfiniteList — offset 봉투", () => {
  it("다음 offset 은 받은 건수다 — 요청 크기를 더하면 서버가 적게 줄 때 행이 건너뛰어진다", async () => {
    /* 첫 묶음에서 3을 달라는데 서버가 2만 준다(권한 절이 한 행을 떨궜다).
       `lastParam + size` 로 세면 다음 offset 이 3이 되어 3번째 행이 영영 안 보인다. */
    const seen = [];
    const fetch = vi.fn(async ({ offset }) => {
      seen.push(offset);
      return offset === 0
        ? { items: [row(1), row(2)], total: 4, limit: 3, offset }
        : { items: [row(3), row(4)], total: 4, limit: 3, offset };
    });
    const { result } = renderHook(
      () => useInfiniteList({ key: ["k"], fetch, envelope: offsetEnvelope, size: 3 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    act(() => { result.current.fetchNext(); });
    await waitFor(() => expect(result.current.rows).toHaveLength(4));
    expect(seen).toEqual([0, 2]);
  });
});

describe("useInfiniteList — 커서 봉투", () => {
  it("서버가 준 커서를 그대로 다음 요청에 싣고, 없으면 멈춘다", async () => {
    const fetch = vi.fn(async ({ cursor }) => (cursor
      ? { items: [row(2)], next_cursor: null }
      : { items: [row(1)], next_cursor: "c1" }));
    const { result } = renderHook(
      () => useInfiniteList({ key: ["k"], fetch, envelope: cursorEnvelope, size: 1 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.hasNext).toBe(true));
    act(() => { result.current.fetchNext(); });
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    expect(fetch).toHaveBeenLastCalledWith({ cursor: "c1", limit: 1 });
    expect(result.current.hasNext).toBe(false);
  });
});

describe("useInfiniteList — 조건이 바뀌면 받아 둔 묶음을 버린다", () => {
  it("옛 조건의 행이 새 조건 목록 위에 남지 않는다", async () => {
    /* 이 시험이 keepPreviousData 를 안 쓰기로 한 판단의 회귀 방지선이다. 그것을 켜면 옛
       조건 묶음이 남은 채 hasNext 가 옛 데이터에서 나오고, 센티넬이 그 자리에서 다음을
       불러 옛 행 아래에 새 행이 붙는다. */
    const fetch = vi.fn(async ({ page }) => ({ items: [{ id: `p${page}` }], total: 9 }));
    const { result, rerender } = renderHook(
      ({ status }) => useInfiniteList({ key: ["k", status], fetch, size: 1 }),
      { wrapper: wrapper(), initialProps: { status: "열림" } },
    );
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    act(() => { result.current.fetchNext(); });
    await waitFor(() => expect(result.current.rows).toHaveLength(2));

    rerender({ status: "닫힘" });
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(result.current.loaded).toBe(1);
  });
});
describe("useInfiniteList — 중복 제거", () => {
  it("rowId 를 주면 경계에서 겹쳐 온 행을 한 번만 그린다", async () => {
    /* offset 페이징은 그 사이 목록이 바뀌면 경계에서 같은 행을 두 번 준다. 쪽 화면에서는
       「2쪽을 다시 봤다」로 끝났지만, 이어 붙이는 화면에서는 한 화면 안에 같은 행 둘이다. */
    const fetch = vi.fn(async ({ page }) => (page === 1
      ? { items: [row(1), row(2)], total: 4 }
      : { items: [row(2), row(3)], total: 4 }));
    const { result } = renderHook(
      () => useInfiniteList({ key: ["k"], fetch, size: 2, rowId: (r) => r.id }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    act(() => { result.current.fetchNext(); });
    await waitFor(() => expect(result.current.rows).toHaveLength(3));
    expect(result.current.rows.map((r) => r.id)).toEqual(["r1", "r2", "r3"]);
  });

  it("rowId 가 없으면 안 거른다 — 식별자가 없는 목록에 없는 규칙을 지어내지 않는다", async () => {
    const fetch = vi.fn(async () => ({ items: [row(1), row(1)], total: 4 }));
    const { result } = renderHook(
      () => useInfiniteList({ key: ["k"], fetch, size: 2 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
  });
});

describe("useInfiniteList — 옛 주소의 page=N 이어받기", () => {
  it("resume 을 주면 그만큼 미리 받는다", async () => {
    const fetch = vi.fn(async ({ page }) => ({ items: [row(page)], total: 9 }));
    const { result } = renderHook(
      () => useInfiniteList({ key: ["k"], fetch, size: 1, resume: 3 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.chunks).toBe(3));
    expect(result.current.rows).toHaveLength(3);
  });

  it("아무리 큰 값을 줘도 다섯 묶음에서 멈춘다 — 북마크 하나가 스무 번 왕복하지 않는다", async () => {
    const fetch = vi.fn(async ({ page }) => ({ items: [row(page)], total: 99 }));
    const { result } = renderHook(
      () => useInfiniteList({ key: ["k"], fetch, size: 1, resume: 40 }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.chunks).toBe(5));
    await new Promise((r) => { setTimeout(r, 40); });
    expect(result.current.chunks).toBe(5);
  });
});

describe("pageEnvelope 는 lastPageParam 을 쓴다", () => {
  it("묶음 수가 아니라 마지막 쪽 번호 다음이다 — 옛 뷰의 page=3 에서 이어받을 수 있어야 한다", () => {
    const all = [{ items: [1], total: 99 }];
    expect(pageEnvelope.next(all[0], all, 3, 1, "items")).toBe(4);
  });
});
describe("useResetScrollOnKeyChange", () => {
  it("첫 마운트에는 안 되돌린다 — 그 순간은 listReturn 이 스크롤을 복원하는 자리다", () => {
    const spy = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    renderHook(({ token }) => useResetScrollOnKeyChange(token), { initialProps: { token: "a" } });
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it("조건이 바뀌면 목록 머리로 되돌린다 — 4,000px 아래에서 3건이 남으면 빈 화면으로 보인다", () => {
    const spy = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    const { rerender } = renderHook(
      ({ token }) => useResetScrollOnKeyChange(token),
      { initialProps: { token: "a" } },
    );
    rerender({ token: "b" });
    expect(spy).toHaveBeenCalledTimes(1);
    rerender({ token: "b" });
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });
});
describe("useInfiniteList — 옛 자료를 그리는 동안에는 이어 받지 않는다", () => {
  it("조건이 막 바뀐 순간 hasNext 는 거짓이고 fetchNext 는 아무 일도 안 한다", async () => {
    /* 🔴 이 시험이 지키는 것: `keepPreviousData` 는 목록이 깜빡이지 않게 하려고 켜 둔 것이고
       (그게 없으면 조건 상자까지 함께 사라진다), 그 옛 자료는 **다음 지점**까지 들고 있다.
       그대로 두면 센티넬이 그 자리에서 「다음」을 불러 옛 조건 다섯 묶음 아래에 새 조건
       두 묶음이 붙는다 — 한 화면에 두 조건의 결과가 섞인다. */
    let release;
    const gate = () => new Promise((r) => { release = r; });
    let hold = false;
    const fetch = vi.fn(async ({ page }) => {
      if (hold) { await gate(); }
      return { items: [{ id: `p${page}` }], total: 9 };
    });
    const { result, rerender } = renderHook(
      ({ status }) => useInfiniteList({ key: ["k", status], fetch, size: 1 }),
      { wrapper: wrapper(), initialProps: { status: "열림" } },
    );
    await waitFor(() => expect(result.current.hasNext).toBe(true));

    hold = true;
    rerender({ status: "닫힘" });
    /* 옛 자료가 아직 화면에 있다 — 그런데 더 받을 수는 없다. */
    await waitFor(() => expect(result.current.rows).toHaveLength(1));
    expect(result.current.hasNext).toBe(false);
    const before = fetch.mock.calls.length;
    act(() => { result.current.fetchNext(); });
    expect(fetch.mock.calls.length).toBe(before);

    hold = false;
    await act(async () => { release(); });
    await waitFor(() => expect(result.current.hasNext).toBe(true));
  });
});