/* 공통 배치 부품 둘 — 머리 줄(`HeadRow`)과 흐름(`FlowStack`) (D-528).
 *
 * ## 머리 줄 — 「앞 · 글 · 동작」을 **첫 줄 가운데선** 하나에 세운다
 *
 * 메시지 상자 · 구획 머리 · 판 머리 · 스위치 줄 · 체크리스트 행은 모두 같은 모양이다: 앞(아이콘 · 상태 표지), 글(한 줄일 수도 여러
 * 줄일 수도 있다), 오른쪽 끝의 동작. 예전에는 부품마다 다른 정렬로 구현했다 — 메시지 상자는 위 정렬이라 한 줄 글(24px) 옆
 * 30px 단추가 3 ~ 5px 내려갔고, 구획 머리는 제목과 도움말을 한 상자에 쌓아 동작이 그 상자 가운데에 섰고, 페이지 머리는
 * 아래 정렬이었다. 같은 「한 줄 + 오른쪽 동작」이 화면마다 다르게 보인 원인이다.
 *
 * 이 부품은 줄의 높이 `H`(동작이 있으면 동작 높이 30 · 34, 없으면 글 한 줄 높이)를 정하고, 아이콘과 글을 `(H − 자기 높이) / 2`
 * 만큼 내려 **첫 줄**이 동작과 같은 가운데선에 서게 한다. 글이 여러 줄이 되어도 아이콘과 동작은 첫 줄 띠에 남는다(흔들리지
 * 않는다). 두 모드:
 *   first-line  메시지 상자 · 구획 머리 · 판 머리 · 스위치 줄(기본)
 *   center      두 줄짜리 목록 행 · 초기 설정 체크리스트처럼 행 전체의 가운데가 맞는 자리
 *
 * ## 흐름 — 간격은 상자가 아니라 담는 쪽이 준다
 *
 * RULES §0: 요소 사이 세로 간격은 16px 하나, 카드 안은 14px. 예전에는 화면마다 메시지 상자 · 페이지 머리 · 필터 면에 위아래
 * 여백을 손으로 적었다(메시지 상자에만 74곳). `FlowStack` 이 자식 사이 간격을 주고 자식의 위아래 바깥 여백을 지운다. 화면
 * 그릇(`.c-screen`)도 같은 규칙이다(`styles/screens.css`).
 */
import React from "react";
import Box from "@mui/material/Box";

import { CONTROL, remPx } from "./theme.js";

/* 흐름 간격(rem). page 16 · card 14 · tight 8 — RULES §0. */
export const FLOW_GAP = { page: "1rem", card: "0.875rem", tight: "0.5rem" };

/** 픽셀 높이 둘의 차이의 반을 rem 으로 — 첫 줄을 가운데선에 내리는 여백. 음수면 0. */
export function centerPad(boxPx, itemPx) {
  return remPx(Math.max(0, (boxPx - itemPx) / 2));
}

/**
 * 머리 줄. `lead` 앞(아이콘 · 표지) · `children` 글 · `action` 오른쪽 끝 동작.
 *
 * first-line 모드의 기하는 픽셀 셋으로 정한다 — `lineHeightPx`(글 첫 줄의 줄 높이), `leadPx`(앞의 높이), `actionPx`(동작 높이,
 * 기본 `CONTROL.control` 34). 줄 높이 H = 동작이 있으면 max(동작, 첫 줄), 없으면 첫 줄이다.
 */
export function HeadRow({
  lead, children, action, mode = "first-line", lineHeightPx = 24, leadPx = 16, actionPx = CONTROL.control,
  gap = 1.25, actionGap = 1, className, component = "div", sx, ...rest
}) {
  const H = action ? Math.max(actionPx, lineHeightPx) : lineHeightPx;
  const firstLine = mode !== "center";
  const columns = [lead ? "auto" : null, "minmax(0,1fr)", action ? "auto" : null].filter(Boolean).join(" ");
  return (
    <Box
      component={component}
      className={className ? `k-head-row ${className}` : "k-head-row"}
      data-head-row={mode}
      sx={(t) => ({
        display: "grid",
        gridTemplateColumns: columns,
        columnGap: gap,
        alignItems: firstLine ? "start" : "center",
        minWidth: 0,
        "--head-h": remPx(H),
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
      {...rest}
    >
      {lead ? (
        <Box
          className="k-head-lead"
          sx={{ display: "flex", alignItems: "center", flexShrink: 0, ...(firstLine ? { pt: centerPad(H, leadPx) } : null) }}
        >
          {lead}
        </Box>
      ) : null}
      <Box className="k-head-text" sx={{ minWidth: 0, ...(firstLine ? { pt: centerPad(H, lineHeightPx) } : null) }}>
        {children}
      </Box>
      {action ? (
        <Box
          className="k-head-action"
          sx={{
            display: "flex", alignItems: "center", justifyContent: "flex-end", gap: actionGap, flexShrink: 0,
            ...(firstLine ? { pt: centerPad(H, actionPx), minHeight: remPx(actionPx) } : null),
          }}
        >
          {action}
        </Box>
      ) : null}
    </Box>
  );
}

/**
 * 흐름 그릇. 자식 사이 세로 간격을 주고 자식의 위아래 바깥 여백을 지운다(자식의 sx 보다 이기도록 선택자를 두 번 겹친다).
 * 가로 여백(전폭 띠의 음수 여백 등)은 건드리지 않는다.
 */
export function FlowStack({ gap = "page", component = "div", className, children, sx, ...rest }) {
  const rowGap = FLOW_GAP[gap] || gap;
  return (
    <Box
      component={component}
      className={className ? `k-flow ${className}` : "k-flow"}
      data-flow={gap}
      sx={(t) => ({
        display: "flex",
        flexDirection: "column",
        rowGap,
        minWidth: 0,
        "&& > *": { marginBlockStart: 0, marginBlockEnd: 0 },
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
      {...rest}
    >
      {children}
    </Box>
  );
}
