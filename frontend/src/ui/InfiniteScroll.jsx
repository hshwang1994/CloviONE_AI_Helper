import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Button } from "./kit.jsx";
import { useInfiniteSentinel, useListFooter } from "./listFooter.js";

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
 *
 * **목록 판 안의 표는 이 부품을 쓰지 않는다**(UI 3차 · 조합 계약 C-3). 그 표의 발은 `DataTable list` 가 판 안
 * 마지막 줄에 그리고, 같은 논리(`listFooter.js::useListFooter`)를 쓴다. 이 부품이 남는 자리는 판이 없는 목록 —
 * 작업 보드 백로그(보호 화면) · 활동 기록 · 서랍 안 하위 목록이다.
 */

export { useInfiniteSentinel };

/** 목록 끝 줄.
 *
 * @param total          서버가 센 전체 건수. 모르는 목록(활동 로그)은 `null`
 * @param loaded         지금까지 받은 건수
 * @param autoMaxRows    이만큼 받으면 **자동 로딩을 끄고 단추만 남긴다**. 가상화가 안 되는
 *                       목록(좁은 화면 카드 뷰)이 이것을 쓴다. `0` 이면 자동 없음
 * @param root           센티넬의 스크롤 창(모달 안 목록만)
 */
export function ListFooter({
  total, loaded, hasNext, isFetchingNext, onMore,
  unit = "건", moreLabel = "더 보기", root = null, autoMaxRows, sx,
}) {
  const foot = useListFooter({ total, loaded, hasNext, isFetchingNext, onMore, unit, root, autoMaxRows });
  if (!foot.sentence) return null;

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
      {foot.hasNext ? (
        <Box ref={foot.sentinelRef} aria-hidden="true"
             sx={{ width: "1px", height: "1px", flex: "0 0 auto" }} />
      ) : null}
      {/* 묶음이 붙을 때마다 이 숫자가 다시 낭독된다. **포커스는 안 옮긴다** — 굴리던 자리를
          화면이 빼앗으면 안 된다. */}
      <Typography variant="caption" color="text.secondary" aria-live="polite">
        {foot.sentence}
      </Typography>
      {foot.hasNext ? (
        <Button variant="ghost" size="sm" loading={isFetchingNext} onClick={foot.more}>{moreLabel}</Button>
      ) : null}
    </Box>
  );
}
