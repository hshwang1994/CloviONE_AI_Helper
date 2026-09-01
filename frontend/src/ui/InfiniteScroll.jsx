import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Button } from "./kit.jsx";

/* 목록의 끝 — **센티넬 · 받은 건수 · 「더 보기」 셋을 한 부품이** 낸다.
 *
 * 셋을 따로 두면 「자동은 되는데 단추가 없는 화면」이 반드시 생긴다. 그리고 단추는 장식이
 * 아니다 — **키보드·스크린리더 사용자는 무한 스크롤에 닿을 수 없다.** 이 계약은 이 저장소가
 * REAUDIT §8.5 에서 이미 정한 것이고, 작업 보드 백로그가 쓰던 문구를 여기로 올린 것이다.
 *
 * 자동 로딩의 신호는 **두 가지**다. 이 부품의 센티넬은 그중 하나일 뿐이다:
 *
 *   가상화한 목록  → 가상화기가 이미 「마지막 행이 창에 들어왔다」를 안다. 스크롤 창이 윈도인지
 *                    안쪽 상자인지의 차이를 가상화기가 흡수하므로 `root` 문제가 안 생긴다.
 *   그 밖의 목록    → 여기 센티넬. `root` 는 거의 언제나 `null`(뷰포트)이고, 모달 안 하위
 *                    목록만 자기 스크롤 창을 넘긴다.
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

/** 목록 끝 줄.
 *
 * @param total          서버가 센 전체 건수. 모르는 목록(활동 로그)은 `null`
 * @param loaded         지금까지 받은 건수
 * @param autoMaxRows    이만큼 받으면 **자동 로딩을 끄고 단추만 남긴다**. 가상화가 안 되는
 *                       목록(`GroupedTickets`·좁은 화면 카드 뷰)이 이것을 쓴다. `0` 이면 자동 없음
 * @param root           센티넬의 스크롤 창(모달 안 목록만)
 */
export function ListFooter({
  total, loaded, hasNext, isFetchingNext, onMore,
  unit = "건", moreLabel = "더 보기", root = null, autoMaxRows, sx,
}) {
  const ref = React.useRef(null);
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

  const capped = autoMaxRows != null && (autoMaxRows === 0 || loaded >= autoMaxRows);
  const auto = hasNext && !isFetchingNext && !stalled && !capped;
  useInfiniteSentinel(ref, { onHit: more, enabled: auto, root });

  /* 다 받았고 셀 것도 없으면 아무것도 안 그린다 — 한 줄짜리 목록 아래에 「1건 중 1건」은
     자리만 먹는다(`Pager` 가 한 쪽짜리 목록에서 사라지던 것과 같은 규칙). */
  if (!hasNext && (total == null || total <= loaded) && loaded <= 0) return null;
  if (!hasNext && total != null && total <= loaded && loaded < 2) return null;

  return (
    <Box
      data-list-footer=""
      sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 1, mt: 2, ...sx }}
    >
      {/* 🔴 `width: 1` 이 아니라 `"1px"` 이다. MUI 의 sx 는 `width`/`height` 의 1 이하 숫자를
          **백분율**로 옮긴다 — `width: 1` 은 1px 이 아니라 `100%` 다. 그러면 이 보이지 않는
          칸이 바닥 줄의 flex 폭을 통째로 먹어 건수 문구와 「더 보기」가 오른쪽으로 밀리고
          단추 글자가 두 줄로 접힌다(실브라우저에서 915px 을 차지하는 것을 쟀다).
          `flex: "0 0 auto"` 는 그 반대쪽 사고를 막는다 — flex 가 이 칸을 늘리지 못하게 한다. */}
      {hasNext ? (
        <Box ref={ref} aria-hidden="true"
             sx={{ width: "1px", height: "1px", flex: "0 0 auto" }} />
      ) : null}
      {/* 묶음이 붙을 때마다 이 숫자가 다시 낭독된다. **포커스는 안 옮긴다** — 굴리던 자리를
          화면이 빼앗으면 안 된다. */}
      <Typography variant="caption" color="text.secondary" aria-live="polite">
        {total == null
          ? `${loaded.toLocaleString("ko-KR")}${unit}을 받았습니다.`
          : `${total.toLocaleString("ko-KR")}${unit} 중 ${loaded.toLocaleString("ko-KR")}${unit}을 받았습니다.`}
        {capped && hasNext ? " 조건을 좁히면 더 빨리 찾습니다." : ""}
      </Typography>
      {hasNext ? (
        <Button variant="ghost" size="sm" loading={isFetchingNext} onClick={more}>{moreLabel}</Button>
      ) : null}
    </Box>
  );
}