import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Card } from "./kit.jsx";
import { SECTION_GAP } from "./density.js";
import { FONT_SIZE, FONT_WEIGHT } from "./theme.js";

/* 관리자 화면(Dashboard·진단·유지보수·작업 큐·개발자 리포트)이 함께 쓰는 껍데기·격자.
 * 예전엔 전부 Dashboard.jsx 안에 있어서, 그 화면 하나가 사실상 '관리자 전용 디자인 시스템'
 * 노릇을 했다(DS-17) — 5개 모듈이 화면 파일 하나를 import하는 구조였다. 여기로 옮겨 진짜
 * 공용 위치에 둔다. 순수 표시 헬퍼(serviceLabel·날짜/숫자 포맷 등)는 ops/opsHelpers.js로
 * 옮겼다 — 그쪽은 JSX 없는 순수 함수 모음이라는 기존 성격에 맞춘 것이다. */

/* 개수가 고정(5개)인 머리 지표 줄의 격자.
 *
 * 지표를 낱장 카드 격자(옛 `STAT_GRID`)로 까는 방식은 폐기했다 — 열 수가 개수를 나누지
 * 못하면 마지막 줄이 비고, 무엇보다 카드 N장은 무엇이 핵심 지표인지 말해 주지 않는다.
 * 지표는 이제 판 하나를 나눠 쓰는 판독 줄(kit.jsx::MetricStrip)이다.
 *
 * 이 격자는 지표가 아니라 **경보 타일**처럼 개수가 고정된 줄에만 남는다. 좁은 화면에서는
 * 2열로 접히고, 그때는 5개가 세 줄이 되는 게 맞다(가로 스크롤보다 낫다). */
export const HEADLINE_GRID = {
  xs: "1fr",
  sm: "repeat(2, minmax(0,1fr))",
  lg: "repeat(5, minmax(0,1fr))",
};

// 서비스/연동 카드 격자 — 타일이 작아 머리 지표 줄(HEADLINE_GRID)보다 촘촘하게 깐다.
export const SERVICE_GRID = {
  xs: "1fr", sm: "repeat(2, minmax(0,1fr))", md: "repeat(3, minmax(0,1fr))", xxl: "repeat(4, minmax(0,1fr))",
};

/* 대시보드·진단이 공유하는 섹션 껍데기(제목 + 오른쪽 보조 링크).
 * 예전엔 .dash-section/.dash-h2/.dash-h2-row 세 클래스를 두 화면이 각자 손으로 붙였고,
 * 한쪽에만 h2-row를 빠뜨려 같은 성격의 섹션이 화면마다 다른 간격으로 보였다. */
export function DashSection({ title, action, children }) {
  return (
    /* 섹션 사이 간격은 기준선 `.section`(24px)이다. 예전 값 `{ xs: 4, xxl: 5 }`(32px/40px)는
       한 화면에 섹션이 대여섯 개인 대시보드에서 화면 하나 분량의 빈 줄을 더 만들었다. */
    <Box component="section" sx={{ mb: SECTION_GAP }}>
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 2, mb: 1.5 }}>
        <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle }}>{title}</Typography>
        {action}
      </Box>
      {children}
    </Box>
  );
}

/* 서비스/연동 상태 타일(이름 + 배지). 대시보드와 진단이 같은 사실을 같은 모양으로 보여야 한다 —
 * 예전엔 두 화면이 각자 .dash-svc 마크업을 손으로 복사해 뒀고, 한쪽만 hover 표시를 붙여
 * '누를 수 있는 카드'인지 아닌지가 화면마다 달라 보였다.
 * 이름 옆에 중첩 <button>을 두지 않는다 — role="button" 안의 포커스 가능한 자손은 WAI-ARIA 금지이고,
 * 실제로도 '이름을 누르면 다른 일이 일어난다'는 잘못된 기대를 만든다. 카드 하나만 클릭 대상이다. */
export function StatusTile({ name, onClick, ariaLabel, children }) {
  return (
    <Card onClick={onClick}
      sx={{
        p: 2, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1,
        cursor: onClick ? "pointer" : "default",
        "&:hover": onClick ? { borderColor: "primary.main" } : undefined,
      }}
      role={onClick ? "button" : undefined} tabIndex={onClick ? 0 : undefined}
      aria-label={onClick ? ariaLabel : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } } : undefined}>
      <Typography
        variant="body2" title={name}
        sx={{ fontWeight: FONT_WEIGHT.bold, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
      >
        {name}
      </Typography>
      {children}
    </Card>
  );
}

// 섹션 안의 부연(‘성공률 분모’ 설명 등). 예전 .pending-note를 대신한다 — 클래스 하나로
// 문단·도움말·주석이 뒤섞여 있어서 한 곳을 고치면 엉뚱한 화면의 여백이 같이 움직였다.
// id를 받는다 — 이 문단이 곧 입력의 설명(aria-describedby 대상)이 되는 자리가 있다(Ops의 점검 공지).
export function Note({ children, sx, id }) {
  return (
    <Typography id={id} variant="body2" color="text.secondary" sx={{ mt: 1.5, lineHeight: 1.6, ...sx }}>
      {children}
    </Typography>
  );
}
