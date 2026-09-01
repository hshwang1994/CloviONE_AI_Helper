import React from "react";
import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";

/* 목록을 **쪽 대신 묶음으로** 받는 공용 훅.
 *
 * ## 왜 화면마다 `useInfiniteQuery` 를 안 쓰는가
 *
 * 이 저장소의 목록 봉투는 셋이다 — `{items,total,page,page_size}`(라우터 14개),
 * `{items,total,limit,offset}`(문서 목록), `{items,next_cursor}`(작업 보드). 화면마다 손으로
 * 쓰면 `getNextPageParam` 이 열일곱 벌이 되고, 그중 하나는 반드시 «마지막 묶음에서 한 번 더
 * 부른다» 가 된다. 그 결함은 오류를 안 내고, 서버 로그에만 남는다.
 *
 * 봉투 사이에 실제로 다른 것은 **순수 함수 셋뿐**이다: 첫 `pageParam` · 그것을 질의로 바꾸는
 * 법 · 다음 것을 구하는 법. 그래서 어댑터를 값 객체로 두고 훅은 하나만 둔다.
 *
 * ## 옛 자료를 남기되, 그 위에서 **다음을 안 부른다**
 *
 * `placeholderData: keepPreviousData` 는 쪽 화면의 옳은 관용이다 — 조건을 바꾸는 동안 목록이
 * 스켈레톤으로 사라지지 않는다. 그것이 없으면 목록만 깜빡이는 게 아니라 **조건 상자까지
 * 사라진다**(화면들이 「로딩이면 스켈레톤」 분기 안에 필터 줄을 함께 두고 있다) — 고르는
 * 도중에 고르던 상자가 없어진다.
 *
 * 🔴 그런데 무한 질의에서는 그 옛 자료가 **다음 지점**까지 들고 있다. 그대로 두면 조건을 바꾼
 * 직후 `hasNextPage` 가 옛 데이터에서 나오고, 자동 로딩 센티넬이 그 자리에서 「다음」을 불러
 * 옛 조건 다섯 묶음 아래에 새 조건 두 묶음이 붙는다.
 *
 * 그래서 **보여 주는 것과 이어 받는 것을 가른다**: 옛 자료는 그대로 그리되(`rows`),
 * 그것이 옛 자료인 동안(`isPlaceholderData`)에는 `hasNext` 를 거짓으로 두고 `fetchNext` 를
 * 무시한다. 새 자료가 도착하면 그 순간부터 다시 이어 받는다.
 *
 * 🔴 **`refetchOnWindowFocus` 를 켜지 않는다.** react-query 는 무한 질의를 다시 받을 때
 * **받아 둔 묶음 전부**를 순서대로 다시 부른다. 다섯 묶음이면 창을 한 번 돌아올 때마다 요청이
 * 다섯 번이다.
 *
 * ## `gcTime` 이 10분인 이유
 *
 * 목록 → 상세 → 수정 → 뒤로 가 이 제품의 기본 동선이고(`lib/listReturn.js`), 돌아왔을 때
 * 스크롤을 복원하려면 **받아 뒀던 묶음이 캐시에 그대로 있어야** 한다. `page` 가 질의 키에서
 * 빠졌으므로 캐시가 곧 그 기억이다. 캐시가 사라진 뒤 돌아오면 첫 묶음만 남고 스크롤이 잘리는데,
 * 그것은 쪽 화면의 «1페이지로 돌아감» 과 같은 결과라 후퇴가 아니다.
 */

/** 한 번에 받는 기본 건수. 서버 상한은 100(`app/core/pagination.py::MAX_PAGE_SIZE`)이다.
 *
 * 왜 50인가: 20 은 184건짜리 목록에 왕복이 열 번이라 너무 작고, 100 은 **첫 묶음**으로 너무
 * 크다 — 「진입 즉시 전량을 안 그린다」의 값어치가 첫 페인트 비용에 있는데 100행은 지금과 같다.
 * 50행 × 44px ≈ 2,200px 라 아래 `InfiniteScroll` 의 선행 여백(600px)과 합치면 사용자가 바닥에
 * 닿기 전에 다음 묶음이 도착한다. */
export const CHUNK = 50;

/** 훑는 화면(감사 로그·작업 큐·문서 목록)의 묶음. 행이 싸고 넓은 기간을 지나가야 한다. */
export const CHUNK_WIDE = 100;

const EMPTY_PAGES = [];

function loadedCount(pages, itemsKey) {
  let n = 0;
  for (const p of pages) n += ((p && p[itemsKey]) || []).length;
  return n;
}

/** `{items,total,page,page_size}` — `app/core/pagination.py::PageEnvelope` 를 쓰는 라우터 전부. */
export const pageEnvelope = {
  first: 1,
  toParams: (pageParam, size) => ({ page: pageParam, page_size: size }),
  next: (last, all, lastParam, size, itemsKey) => {
    const loaded = loadedCount(all, itemsKey);
    /* `total` 이 있으면 그것이 진실이다. 없는 응답도 있다(내 활동 로그) — 그때는 마지막
       묶음이 가득 찼는지로 추정한다. `Pager` 의 `hasNext` 폴백과 같은 판정이다(DS-22). */
    if (last && last.total != null) return loaded < last.total ? lastParam + 1 : undefined;
    return ((last && last[itemsKey]) || []).length >= size ? lastParam + 1 : undefined;
  },
};

/** `{items,total,limit,offset}` — `GET /api/knowledge/documents`. */
export const offsetEnvelope = {
  first: 0,
  toParams: (pageParam, size) => ({ limit: size, offset: pageParam }),
  next: (last, all, lastParam, size, itemsKey) => {
    /* 🔴 다음 offset 은 `lastParam + size` 가 **아니라** 지금까지 받은 건수다.
       서버가 요청보다 적게 줄 수 있고(권한 절이 행을 떨구는 경우), 그때 offset 이 어긋나면
       **행이 통째로 건너뛰어진다** — 오류는 안 난다. */
    const loaded = loadedCount(all, itemsKey);
    if (last && last.total != null) return loaded < last.total ? loaded : undefined;
    return ((last && last[itemsKey]) || []).length >= size ? loaded : undefined;
  },
};

/** `{items,next_cursor}` — `GET /api/work/board|backlog` 의 keyset 커서(§8.5). */
export const cursorEnvelope = {
  first: null,
  toParams: (pageParam, size) => ({ cursor: pageParam || "", limit: size }),
  next: (last) => (last && last.next_cursor) || undefined,
};

/**
 * @param key      조건 전부가 들어가는 배열. 이것이 바뀌면 처음부터 다시 받는다
 * @param fetch    `(params) => Promise<봉투>`. URL 조립은 화면이 소유한다
 * @param envelope `pageEnvelope` | `offsetEnvelope` | `cursorEnvelope`
 * @param size     한 묶음 건수
 * @param itemsKey 봉투 안 배열의 이름(기본 `items`)
 * @param rowId    `(row) => id`. 주면 중복을 제거한다 — offset 페이징은 목록이 움직이면
 *                 경계에서 같은 행을 두 번 준다. 쪽 화면에서는 «2쪽을 다시 봤다» 로 끝났지만
 *                 이어 붙이는 화면에서는 **한 화면 안에 같은 행 둘**이 된다
 * @param resume   진입 시 미리 받아 둘 묶음 수(옛 `?page=3` 링크 호환). 5로 자른다
 */
export function useInfiniteList({
  key, fetch, envelope = pageEnvelope, size = CHUNK,
  itemsKey = "items", rowId, enabled = true, resume = 1, ...rq
}) {
  const q = useInfiniteQuery({
    queryKey: [...key, "inf", size],
    queryFn: ({ pageParam }) => fetch(envelope.toParams(pageParam, size)),
    initialPageParam: envelope.first,
    /* v5 의 4번째 인자가 아니라 **3번째**(`lastPageParam`)를 쓴다 — `allPages.length + 1` 로
       세면 옛 뷰의 `page=3` 에서 이어받는 경로가 어긋난다. */
    getNextPageParam: (last, all, lastParam) => envelope.next(last, all, lastParam, size, itemsKey),
    enabled,
    retry: false,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    gcTime: 10 * 60 * 1000,
    ...rq,
  });
  /* 지금 그리는 것이 **옛 조건의 자료**인가. 그렇다면 보여 주기는 하되 이어 받지는 않는다. */
  const stale = q.isPlaceholderData;

  const pages = q.data ? q.data.pages : EMPTY_PAGES;
  const rows = React.useMemo(() => {
    const out = [];
    const seen = rowId ? new Set() : null;
    for (const p of pages) {
      for (const r of ((p && p[itemsKey]) || [])) {
        if (seen) {
          const id = rowId(r);
          if (id != null) {
            if (seen.has(id)) continue;
            seen.add(id);
          }
        }
        out.push(r);
      }
    }
    return out;
  }, [pages, itemsKey, rowId]);

  const total = pages.length && pages[0] && pages[0].total != null ? pages[0].total : null;

  const { hasNextPage, isFetchingNextPage, fetchNextPage } = q;
  const canNext = !!hasNextPage && !stale;
  const fetchNext = React.useCallback(() => {
    if (canNext && !isFetchingNextPage) fetchNextPage();
  }, [canNext, isFetchingNextPage, fetchNextPage]);

  /* 옛 주소·저장된 뷰의 `page=N` 을 대략 그 자리로 되살린다. 무한정 미리 받지 않는다 —
     북마크 하나가 스무 번 왕복하는 진입을 만들면 안 된다(그래서 5로 자른다).
     조건이 바뀌면(`keyToken`) 이 되살리기도 처음부터 다시 판단한다. */
  const wantChunks = Math.min(Math.max(1, Number(resume) || 1), 5);
  React.useEffect(() => {
    if (wantChunks <= 1) return;
    if (pages.length === 0 || q.isFetching || !canNext) return;
    if (pages.length >= wantChunks) return;
    fetchNextPage();
  }, [wantChunks, pages.length, q.isFetching, canNext, fetchNextPage]);

  return {
    rows,
    total,
    loaded: rows.length,
    chunks: pages.length,
    /* 첫 묶음 원본. 목록 밖의 값을 함께 싣는 응답이 있다 — 문서 목록의 `authors`,
       프로젝트 목록의 `departments`. 그 값들은 조건이 같으면 묶음마다 같으므로 첫 것을 쓴다. */
    first: pages.length ? pages[0] : null,
    hasNext: canNext,
    fetchNext,
    /* 지금 보이는 것이 옛 조건의 자료인가. 화면이 「받는 중」을 말하고 싶을 때 쓴다. */
    isStale: stale,
    isFetchingNext: isFetchingNextPage,
    /* 첫 묶음만이다 — `isFetching` 을 쓰면 다음 묶음을 받는 동안 목록 전체가 스켈레톤이 된다. */
    isLoading: q.isPending && enabled,
    isError: q.isError,
    error: q.error,
    /* 「지금 서버와 말하는 중인가」 — 첫 묶음이든 다음 묶음이든. 낙관적 갱신을 되돌리지
       않으려고 「받는 중에는 손대지 않는다」를 판단하는 자리가 이것을 본다. */
    isFetching: q.isFetching,
    refetch: q.refetch,
    query: q,
  };
}

/** 조건이 바뀌면 목록 머리로 되돌린다.
 *
 * 왜 필요한가: 4,000px 아래에서 필터를 걸었는데 결과가 3건이면 화면에는 **아무것도 없다** —
 * 사용자는 그것을 「조건에 맞는 것이 없다」로 읽는다. 쪽 화면에서는 없던 문제다(쪽을 넘기면
 * 어차피 위로 갔다).
 *
 * 🔴 **첫 마운트에는 안 돈다.** 그 순간은 `lib/listReturn.js` 가 스크롤을 되돌리는 자리라
 * 여기서 끼어들면 둘이 싸운다 — 상세에서 돌아온 사람이 매번 맨 위로 튕긴다. */
export function useResetScrollOnKeyChange(token) {
  const prev = React.useRef(null);
  React.useEffect(() => {
    if (prev.current === null) { prev.current = token; return; }
    if (prev.current === token) return;
    prev.current = token;
    if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
      window.scrollTo({ top: 0, behavior: "auto" });
    }
  }, [token]);
}