import React from "react";
import Button from "@mui/material/Button";
import BrandLogo from "../ui/BrandLogo.jsx";

/* 상단바 왼쪽의 브랜드 자리 — 기준선의 `.brand > .brand-lockup`.
 *
 * AppShell 에서 떼어낸 이유가 둘이다. AppShell 이 700줄을 넘었고, 이 자리의 겉모습을
 * 시험이 직접 보려면(topbar-baseline.test.jsx) 셸 전체를 띄우지 않고 이것만 그릴 수 있어야 한다.
 *
 * ── 흰 판을 걷어냈다 (사용자 지적: "아이콘 ClovirAssist 흰바탕이 너무 크다") ──────────
 * 여기에는 로고를 흰 사각형 위에 얹는 상자가 있었다. 이유는 대비였다 — 워드마크의 강조어
 * "Assist"가 브랜드 인디고(#536CD6)라 딥 인디고 상단바 위에서 묻혔기 때문이다. 그런데
 * 기준선은 이 자리를 `background: transparent` 로 두고(`.brand-lockup > img`), 대신 반전
 * 자산(clovirassist-logo-horizontal-dark.svg)을 끼운다. 대비 문제의 답은 흰 판이 아니라
 * 글자색이었다. `BrandLogo inverse` 가 그 자산의 색을 그대로 쓴다.
 */

/* 기준선의 로고 폭. `.brand-lockup.is-compact > img` 가 170px 이고, 아래 두 미디어쿼리가
 * 좁아질수록 줄인다(1100 이하 150, 899 이하는 마크만 42px 로 잘라 쓴다).
 * 4K 쪽(xxl/uhd)은 기준선에 없다 — 사이드바 열이 넓어지는 만큼 같이 키운 우리 값이다. */
const LOCKUP_WIDTH = { xs: 150, md: 170, xxl: 196, uhd: 224 };

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
      <BrandLogo
        inverse
        width={LOCKUP_WIDTH}
        sx={{ display: { xs: "none", sm: "block" } }}
      />
      {/* 기준선은 899px 이하에서 락업을 마크 폭(42px)으로 잘라 쓴다. 우리는 자르는 대신
          같은 마크를 그린다 — 인라인 SVG라 자를 이유가 없다. */}
      <BrandLogo inverse markOnly width={42} sx={{ display: { xs: "block", sm: "none" } }} />
    </Button>
  );
}
