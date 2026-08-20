import React from "react";
import Button from "@mui/material/Button";
import BrandLogo from "../ui/BrandLogo.jsx";
import { NAV_BREAKPOINT_PX } from "./navConfig.js";

/* 상단바 왼쪽의 브랜드 자리 — 기준선의 `.brand > .brand-lockup`.
 *
 * AppShell 에서 떼어낸 이유가 둘이다. AppShell 이 700줄을 넘었고, 이 자리의 겉모습을
 * 시험이 직접 보려면(topbar-baseline.test.jsx) 셸 전체를 띄우지 않고 이것만 그릴 수 있어야 한다.
 *
 * ── 반전 자산 대신 **상속되는 잉크**를 쓴다 (D-141 -> D-179) ────────────────
 * 이 자리는 두 번 뒤집혔다. 원래는 `BrandLogo inverse`(흰 글자)로 딥 인디고 상단바를
 * 전제했고, D-141 이 chrome 을 밝게 만들자 그 자산이 밝은 바탕 위 흰 글자가 되어 1.21 로
 * 떨어졌다. D-179 가 chrome 을 다시 인디고로 되돌리자 이번에는 정방향 자산의 "Assist"가
 * 2.32 로 떨어졌다.
 *
 * 그래서 **자산을 고르는 방식 자체를 그만뒀다.** `BrandLogo` 는 `--clovir-wordmark` 를 읽고,
 * Shell 컨테이너가 그 변수를 `chrome.wordmark` 로 덮는다. 다음에 chrome 밝기가 또 바뀌어도
 * 호출부는 손댈 것이 없다 — 면을 소유한 컨테이너가 잉크도 함께 말한다.
 * `brand-logo.test.jsx` 가 Shell 모든 stop 에서 AA 를, `theme-contract.test.js` 가
 * Accent 프리셋 전체에서 Brand 불변을 단언한다.
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
        /* 기준선 `.brand { padding: 5px 7px }`. 흰 판이 없으니 로고가 스스로 여백을 가진다.
           단위는 rem 이다 — 락업 자체가 rem 으로 자라는데(BrandLogo 의 BRAND_UNIT) 여백만
           px 로 고정하면 4K 에서 로고가 자기 칸에 꽉 차 보인다. D-182 와 같은 규율이다. */
        px: "0.4375rem",
        py: "0.3125rem",
        minWidth: 0,
      }}
    >
      {/* 락업은 **한 줄**이다 (R-13 "로고 영역을 현재보다 조금 줄인다").
          부제 글자 크기는 줄일 수 없다 — QA 의 tiny_text 가 폭 2200 이상에서 12px 하한을
          걸고, 그 폭에서 그 글자는 이미 12.24px 다(BrandLogo 의 BRAND_UNIT 주석). 즉 락업을
          줄이는 유일한 레버는 **줄 수**다. 두 줄에서 한 줄로 내리면 락업이 216×37 →
          약 197×27(면적 -33%)이 되고, 로고가 헤더의 시각적 중심을 과도하게 차지하지 않는다.

          ── W5 정정: 태그라인이 **아무 데도 없었다** ────────────────────────────
          W2(D-183 ⑦)는 부제를 빼면서 "태그라인은 사라지지 않는다 — 좁은 화면 사이드바
          서랍 머리와 로그인 화면이 계속 보여 준다"고 적었다. 그 근거 두 개 중 하나는
          **실재하지 않았다**: 사이드바 머리(`AppShell` 의 Toolbar)는 Drawer paper 가
          `top:0` 에서 시작하는데 그 위를 `zIndex: drawer + 1` 인 fixed AppBar 가 같은
          높이로 덮는다 — 서랍을 연 390 에서도 덮인다(`w4-nav-e2e/anatomy-*-390x844.png`
          에 그 머리가 없다). 남은 하나(로그인)는 실재하지만 두 SVG 락업의 부제가 1920·3840
          양쪽에서 **캡 높이 5px(≈7px 글자)** 이라 읽을 수 있는 크기가 아니다.
          결과적으로 제품의 태그라인은 **어느 폭·어느 테마에서도 화면에 없었다.**

          그래서 되돌리되 **줄 수는 늘리지 않는다** — 부제는 워드마크 **옆**에 인라인으로
          놓는다. 다만 이 버튼 안이 아니라 **상단바 흐름**에 놓는다(`AppShell` 의 Toolbar):
          이 칸은 사이드바 열과 같은 폭(`DRAWER_WIDTH`)에 묶여 있어서, 안에 넣으면 내용이
          칸을 넘겨 락업이 왼쪽에서 잘린다(실측: 「ClovirAssist」가 「irAssist」로 잘렸다).
          R-13 이 필요로 한 레버(높이)는 그대로 지켜진다. */}
      <BrandLogo subtitle={false} sx={{ display: "none", [WIDE]: { display: "inline-flex" } }} />
      {/* 자르는 대신 같은 마크를 그린다 — 인라인 SVG라 자를 이유가 없다. */}
      <BrandLogo markOnly width={34} sx={{ [WIDE]: { display: "none" } }} />
    </Button>
  );
}
