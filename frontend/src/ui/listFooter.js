import React from "react";
import { ScrollRootContext } from "./scrollRoot.js";

/* 목록 끝의 **논리** — 자동 로딩 센티넬 · 무성장 가드 · 자동 상한 · 받은 건수 문장 (UI 3차 · 조합 계약 C-3).
 *
 * 예전에는 이 논리가 `ListFooter` 부품 안에만 있었다. 그 부품은 자기 상자 안에 센티넬 · 문장 · 「더 보기」를
 * 함께 그렸고, 목록 화면은 그 상자를 표 **밖** 가운데에 따로 세웠다(발이 판 밖에 선 원인). 발을 목록 판 안
 * 마지막 줄로 옮기려면 논리째 옮겨야 해서, 논리와 모양을 가른다:
 *
 *   `ListFooter`(InfiniteScroll.jsx)  판 밖 목록(작업 보드 백로그 · 활동 기록 · 서랍 안 하위 목록)의 옛 모양
 *   `DataTable list`(kit.jsx)         목록 판 안 발 — 문장과 「더 보기」는 발에, 센티넬은 표 끝 **흐름**에 선다
 *
 * 🔴 센티넬을 sticky 발 안에 두지 않는다. 판 안 발은 `position: sticky; bottom: 0` 이라 긴 목록에서 늘 뷰포트
 * 아래 끝에 붙어 있고, 그 안의 센티넬은 늘 「보인다」(rootMargin 600px) — 자동 로딩이 목록 끝까지 멈추지 않는다.
 *
 * 이 파일은 `kit.jsx` 를 import 하지 않는다. `InfiniteScroll.jsx` 가 `kit.jsx` 의 `Button` 을 쓰고 `kit.jsx` 가 이
 * 논리를 쓰므로, 논리가 부품 파일에 남으면 두 파일이 서로를 부른다.
 */

/* 이 요소를 실제로 굴리는 조상. 없으면 `null`(=뷰포트).
 *
 * 모달·드로어 안의 목록은 스크롤 창이 윈도가 아니다. 그 노드를 호출부가 ref 로 꿰어 넘기게
 * 하면 자리마다 배선이 하나씩 늘고, 그중 하나는 반드시 빠진다 — 그러면 센티넬이 뷰포트를
 * 기준으로 「보인다」고 판정해 **열자마자 끝까지 받는다**(모달 본문은 뷰포트 안에 통째로 있다).
 * 그래서 센티넬 자신이 자기 위를 걸어 올라가 찾는다. */
function scrollParent(el) {
  if (typeof window === "undefined") return null;
  let node = el && el.parentElement;
  while (node && node !== document.body && node !== document.documentElement) {
    const s = window.getComputedStyle(node);
    if (/(auto|scroll|overlay)/.test(s.overflowY)) return node;
    node = node.parentElement;
  }
  return null;
}

/** 센티넬이 보이면 `onHit` 을 부른다.
 *
 * @param root `null` 이면 뷰포트, `"auto"` 면 **실제로 굴리는 조상**을 스스로 찾는다.
 *             노드를 직접 줘도 된다.
 */
export function useInfiniteSentinel(ref, { onHit, enabled, root = null, rootMargin }) {
  const hit = React.useRef(onHit);
  hit.current = onHit;
  React.useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return undefined;
    const scrollRoot = root === "auto" ? scrollParent(el) : root;
    /* jsdom 에는 이 생성자가 없다. 없으면 **조용히 「더 보기」 단추만 남는다** — 그 단추가
       있어야 하는 이유(키보드·스크린리더)와 같은 이유로 이 폴백이 그대로 성립한다. */
    if (typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver(
      (entries) => { if (entries.some((e) => e.isIntersecting)) hit.current(); },
      {
        root: scrollRoot,
        /* 모드마다 다르다. 윈도는 한 화면쯤 앞서 받아 이어 붙는 것이 안 보이게 하고,
           안쪽 상자(32rem = 512px)는 600 을 쓰면 마운트 즉시 걸린다. */
        rootMargin: rootMargin || (scrollRoot ? "200px 0px" : "600px 0px"),
        /* 센티넬은 1px 짜리다 — 이보다 높은 임계값은 영원히 안 걸린다. */
        threshold: 0,
      },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref, enabled, root, rootMargin]);
}

/** 목록 끝 줄의 상태.
 *
 * @param total        서버가 센 전체 건수. 모르는 목록(활동 로그)은 `null`
 * @param loaded       지금까지 받은 건수
 * @param autoMaxRows  이만큼 받으면 **자동 로딩을 끄고 단추만 남긴다**. `0` 이면 자동 없음
 * @param root         센티넬의 스크롤 창(모달 안 목록만)
 * @param enabled      `false` 면 아무것도 말하지 않고 센티넬도 안 건다(발이 필요 없는 표)
 *
 * 돌려주는 것:
 *   sentinelRef  센티넬 요소에 거는 **콜백 ref**. 센티넬이 나중에 붙어도(불러오는 중 → 행) 관찰이 다시 걸린다
 *   sentence     「N건 중 M건을 받았습니다.」 — 셀 것도 더 받을 것도 없으면 `null`(한 줄짜리 목록 아래에 자리만 먹는다)
 *   hasNext      「더 보기」와 센티넬을 그릴 것인가
 *   more         「더 보기」가 부르는 함수(무성장 가드가 이 호출을 센다)
 */
export function useListFooter({
  total = null, loaded = 0, hasNext = false, isFetchingNext = false, onMore,
  unit = "건", root, autoMaxRows, enabled = true,
} = {}) {
  /* 스크롤 창을 안 말하면 자리가 정한다 — 작업 공간 판 몸(`Workspace.jsx::WorkspacePane`) 안이면 실제로 굴리는 조상을 찾고
     (`"auto"`), 그 밖이면 창이다. 판 안 목록이 창을 기준으로 「보인다」고 판정하면 판을 열자마자 끝까지 받는다(D-531). */
  const ctxRoot = React.useContext(ScrollRootContext);
  const scrollRoot = root !== undefined ? root : ctxRoot;
  const [node, setNode] = React.useState(null);
  /* ref **객체**가 노드와 함께 바뀌어야 `useInfiniteSentinel` 의 효과가 다시 돈다 — 평범한 `useRef` 는 센티넬이
     늦게 붙어도 효과를 다시 부르지 않아 자동 로딩이 조용히 안 걸린다. */
  const nodeRef = React.useMemo(() => ({ current: node }), [node]);
  /* 무성장 가드 — 다음 묶음을 받았는데 `loaded` 가 안 늘면(전부 걸러졌거나 컨테이너가
     `display:none` 이라 센티넬이 계속 보이면) 자동 로딩이 폭주한다. 한 번 겪으면 끈다. */
  const [stalled, setStalled] = React.useState(false);
  const askedAt = React.useRef(null);
  React.useEffect(() => {
    if (isFetchingNext) return;
    if (askedAt.current == null) return;
    if (loaded <= askedAt.current) setStalled(true);
    askedAt.current = null;
  }, [isFetchingNext, loaded]);
  React.useEffect(() => { setStalled(false); }, [total]);

  const more = React.useCallback(() => {
    askedAt.current = loaded;
    if (onMore) onMore();
  }, [onMore, loaded]);

  const next = !!(enabled && hasNext);
  const capped = autoMaxRows != null && (autoMaxRows === 0 || loaded >= autoMaxRows);
  const auto = next && !isFetchingNext && !stalled && !capped;
  useInfiniteSentinel(nodeRef, { onHit: more, enabled: auto, root: scrollRoot });

  /* 다 받았고 셀 것도 없으면 아무 말도 안 한다 — 한 줄짜리 목록 아래에 「1건 중 1건」은
     자리만 먹는다(`Pager` 가 한 쪽짜리 목록에서 사라지던 것과 같은 규칙). */
  const silent = !enabled
    || (!next && (total == null || total <= loaded) && loaded <= 0)
    || (!next && total != null && total <= loaded && loaded < 2);
  let sentence = null;
  if (!silent) {
    const n = (v) => Number(v).toLocaleString("ko-KR");
    sentence = total == null
      ? `${n(loaded)}${unit}을 받았습니다.`
      : `${n(total)}${unit} 중 ${n(loaded)}${unit}을 받았습니다.`;
    if (capped && next) sentence += " 조건을 좁히면 더 빨리 찾습니다.";
  }
  return { sentinelRef: setNode, sentence, hasNext: next, isFetchingNext: !!isFetchingNext, more, capped };
}
