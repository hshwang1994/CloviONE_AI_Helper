import React from "react";
import Button from "@mui/material/Button";
import BrandLogo from "../ui/BrandLogo.jsx";
import { NAV_BREAKPOINT_PX } from "./navConfig.js";

/* 상단바 왼쪽의 브랜드 자리 — 기준선의 `.brand > .brand-lockup`.
 *
 * AppShell 에서 떼어낸 이유가 둘이다. AppShell 이 700줄을 넘었고, 이 자리의 겉모습을
 * 시험이 직접 보려면(topbar-baseline.test.jsx) 셸 전체를 띄우지 않고 이것만 그릴 수 있어야 한다.
 *
 * ── 반전 자산을 쓰지 않는다 (D-141) ──────────────────────────────────────────
 * 예전에는 `BrandLogo inverse`(흰 글자)를 썼다. 딥 인디고 상단바를 전제한 선택이다.
 * chrome 이 캔버스 계열이 된 지금 그 자산은 밝은 바탕 위 흰 글자라 대비 1.21 로 떨어진다.
 * 정방향 자산이 맞다 — 워드마크의 "Assist"는 브랜드 인디고이고, 그 색은 밝은 판 위에서
 * 이미 AA 를 넘는다(theme-contract.test.js 가 프리셋 전체로 검증한다).
 */

/* 락업이냐 마크만이냐의 경계.
 *
 * 기준선은 899px 이하에서 락업을 마크 폭(42px)으로 잘라 쓴다. 예전 코드는 그 경계를
 * MUI 의 `sm`(600px)으로 잡아 두었는데, 그러면 600~860px 구간에서 좁은 상단바에 2줄 락업이
 * 통째로 들어가 검색 막대를 밀어낸다. 그 구간은 사이드바가 서랍으로 접히는 구간이기도 하다
 * (AppShell 의 `isNarrow` = NAV_BREAKPOINT_PX 이하) — 락업이 앉을 264px 열 자체가 없다.
 * 그래서 경계를 그 값 하나로 맞춘다: 열이 있으면 락업, 없으면 마크.
 *
 * 락업 자체의 폭은 여기서 정하지 않는다. BrandLogo 가 rem 으로 짜여 있어 4K 에서 루트
 * 폰트사이즈 레버(styles/root.css)를 타고 같이 커진다 — 브레이크포인트별 px 표(예전
 * LOCKUP_WIDTH)는 그 레버와 이중으로 크기를 정하고 있었다. */
const WIDE = `@media (min-width:${NAV_BREAKPOINT_PX + 1}px)`;

export default function TopBrand({ onClick, label = "홈으로", width }) {
  return (
    <Button
      onClick={onClick}
      aria-label={label}
      color="inherit"
      sx={{
        /* 로고 칸은 사이드바 열과 같은 폭이다 — 상단바는 한 줄로 보이지만 실제로는 두 구역이고,
           그 경계가 아래 사이드바 경계와 어긋나면 두 층이 서로 다른 격자를 쓰는 것처럼 보인다.
           좁은 화면(사이드바가 서랍으로 접힘)에서는 그 열이 없으므로 폭을 풀어 준다. */
        width: width || "auto",
        flexShrink: 0,
        // 사이드바 열과 폭을 맞춘 것 자체가 기준선에 없는 이 저장소만의 결정이라
        // (사용자 지적: 상단바 로고 칸 = 사이드바 폭), 그 넓은 칸 안에서 로고를
        // 왼쪽에 붙이면(flex-start) 오른쪽에 큰 빈 공간이 남아 "가운데가 아니라
        // 왼쪽에 붙어 있다"는 지적이 그대로 재현된다. 사이드바 자체의 로고 헤더
        // (AppShell.jsx 의 Toolbar)는 이미 가운데 정렬돼 있으니 여기도 맞춘다.
        justifyContent: "center",
        textTransform: "none",
        // 기준선 `.brand { padding: 5px 7px }`. 흰 판이 없으니 로고가 스스로 여백을 가진다.
        px: "7px",
        py: "5px",
        minWidth: 0,
      }}
    >
      <BrandLogo sx={{ display: "none", [WIDE]: { display: "inline-flex" } }} />
      {/* 자르는 대신 같은 마크를 그린다 — 인라인 SVG라 자를 이유가 없다. */}
      <BrandLogo markOnly width={34} sx={{ [WIDE]: { display: "none" } }} />
    </Button>
  );
}
