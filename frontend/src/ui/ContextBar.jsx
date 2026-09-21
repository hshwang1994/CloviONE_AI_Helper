import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { FILTER_SURFACE_CONTAINER, FilterRowContext } from "./filters.jsx";

/* 문맥 · 보기 줄 — 「어느 판을 보는가」와 「그 판을 어떻게 그리는가」 (D-497).
 *
 * ## 필터 바와 다른 줄인 이유
 *
 * 작업 보드의 팀 · 회차는 목록을 좁히는 조건이 아니라 **판 자체**다. 팀을 바꾸면 회차 목록이 바뀌고, 회차를 바꾸면 다른
 * 판이 선다. 「내 티켓만」 · 「보류 펴기」 · 「완료와 취소 보기」도 조건이 아니라 **보는 방식**이다. 예전에는 이 넷이 검색 ·
 * 우선순위 같은 데이터 조건과 두 줄에 섞여 있었다. 사용자는 「필터 초기화」가 팀을 지울지, 「내 티켓만」이 조건 칩으로
 * 설지 줄만 보고는 알 수 없었다.
 *
 * 그래서 두 줄로 가른다. 이 줄은 문맥과 보기만 담고, 데이터 조건은 아래 필터 바(`FilterBar` · `TicketFilterBar`)가
 * 담는다. 이 줄에는 검색 칸도 조건 줄(칩 · 결과 수 · 필터 지우기)도 없다. 필터 바의 「필터 지우기」는 이 줄을 건드리지
 * 않는다.
 *
 *   context   문맥 칸(팀 · 회차). 필터 바와 같은 34 줄 칸이다 — 이 줄이 `FilterRowContext` 를 깐다. 값이 긴 축은
 *             `size="wide"` 라 필터 면과 같은 계단(13 · 16 · 20rem)으로 선다. 이 줄이 그 계단의 크기 컨테이너다.
 *   view      보기 전환(칸반 | 백로그 같은 세그먼티드).
 *   options   보기 옵션 묶음. `role="group"` 「보기 옵션」이고 보기 전환 **바로 뒤, 왼쪽부터** 선다. 묶음째 줄바꿈한다.
 *             화면이 탭마다 옵션을 더하고 빼도 앞에 선 것은 제자리다 — 탭에 상관없는 옵션을 맨 앞에 둔다.
 *
 * 줄은 부모 폭을 다 쓰는 블록이다. 크기 컨테이너(`FILTER_SURFACE_CONTAINER`)는 내용으로 폭을 정하지 않으므로 이 줄을
 * 내용 폭으로 줄어드는 자리(`inline-flex` · `fit-content` · 가로 flex 의 `0 0 auto` 칸)에 두면 폭이 0 이 된다. 그런
 * 자리에 두지 않는다. */
export function ContextBar({ context, view, options, optionsLabel = "보기 옵션", sx, ...rest }) {
  return (
    <Box
      data-context-bar=""
      sx={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        columnGap: 1.5,
        rowGap: 1.5,
        mb: 2,
        ...FILTER_SURFACE_CONTAINER,
        ...sx,
      }}
      {...rest}
    >
      <FilterRowContext.Provider value>
        {context}
        {view ? (
          <Box data-context-view="" sx={{ display: "flex", alignItems: "center", flex: "0 0 auto" }}>
            {view}
          </Box>
        ) : null}
        {options ? (
          <Box
            role="group"
            aria-label={optionsLabel}
            data-context-options=""
            /* 묶음은 한 덩어리로 줄바꿈한다(`FilterBar.jsx::ToolbarEnd` 와 같은 규칙) — 단추 하나만 다음 줄로 떨어지면
               같은 묶음이 두 줄로 읽힌다. 전화기 폭은 단추 셋이 한 줄에 안 들어가므로 묶음 안에서 접는다. */
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
              flexWrap: { xs: "wrap", sm: "nowrap" },
              flex: "0 0 auto",
              maxWidth: "100%",
            }}
          >
            {/* 묶음 이름은 눈에 보이는 글자로도 선다 — 켬/끔 단추가 데이터 조건이 아니라 보기 방식이라는 것을 줄만 보고 알
                수 있어야 한다. 낭독기는 묶음 이름(`aria-label`)으로 한 번만 읽는다. */}
            <Typography
              component="span"
              variant="caption"
              color="text.secondary"
              aria-hidden="true"
              sx={{ whiteSpace: "nowrap" }}
            >
              {optionsLabel}
            </Typography>
            {options}
          </Box>
        ) : null}
      </FilterRowContext.Provider>
    </Box>
  );
}
