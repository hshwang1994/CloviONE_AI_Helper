import React from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import { foldedFilterOptions, normalizeQuery } from "../lib/search.js";
import { CONTROL, DEBOUNCE_MS, FONT_SIZE, FONT_WEIGHT, ICON, controlHeight, remPx } from "./theme.js";
import { stepUp, textRem } from "./columnPlan.js";

/* 목록 화면들이 함께 쓰는 필터 입력 부품.
 *
 * 예전에는 이 셋이 화면마다 손으로 복사돼 있었다(DataScreen 의 검색창, 문서 목록의
 * FilterSelect, 티켓 목록의 select). 같은 뜻의 부품이 세 벌이면 한쪽만 고쳐지는 날이 오고,
 * 그때 증상은 "이 화면 필터만 다르게 동작한다" 라서 원인이 안 보인다. */

/** 검색·자유 입력 확정까지의 지연. 값의 정본은 토큰이다(theme.js::DEBOUNCE_MS). */
export const FILTER_DEBOUNCE_MS = DEBOUNCE_MS.filter;

/* ── 폭은 **의미**가 정한다 (W5 · C2 «폭 배분» · R-76 · R-80) ────────────────
 *
 * 예전 규칙은 격자 트랙 하나였다: `repeat(auto-fit, minmax(11rem, 16rem))`. 그 한 줄이
 * 세 가지를 동시에 만들었다.
 *   ① **값 길이와 무관한 균등 폭.** 「상태: 전체」(4글자)와 「P. SK 하이닉스 [용인 클러스터
 *      대비]」(24글자)가 같은 255px 를 받는다. 긴 프로젝트명은 잘리고, 앞부분이 같은
 *      프로젝트끼리는 잘린 뒤 구분이 불가능해진다.
 *   ② **고아 줄.** 트랙 수가 정해져 있으니 마지막 항목 하나가 자기 줄을 통째로 쓴다.
 *   ③ **검사 불능.** `width: fit-content` 가 격자 상자를 가장 넓은 줄 폭으로 줄이므로
 *      `isolated_control_row` 가 재는 «윗줄 여유» 가 구조적으로 항상 0 이 된다 —
 *      그래서 664 페이지에서 fail 이 0 이었다. «위반이 없다» 가 아니라 «잴 수 없다» 였다.
 *
 * 그래서 격자를 버리고 **줄바꿈되는 흐름**으로 간다. 각 컨트롤은 자기 종류가 요구하는
 * 폭을 들고 다니고, 컨테이너는 폭 전체를 차지한다(그래야 남는 폭이 실제로 남는 폭이고,
 * 프로브가 그것을 잴 수 있다).
 */
export const CONTROL_KIND = {
  /* 자유 검색 — 이 줄에서 유일하게 늘어나는 것. 한없이 늘리지는 않는다(긴 입력은 읽기 어렵다). */
  search: { flex: "1 1 20rem", maxWidth: "32rem", minWidth: "12rem" },
  /* Entity(프로젝트·담당자·부서·사용자) — 값이 길고 주요 탐색 조건이다. 넉넉히 준다.
     **자란다**(단 자기 상한까지만): 줄에 남는 폭이 있으면 값이 긴 축이 그것을 가져가는
     것이 옳고, 동시에 마지막 줄에 컨트롤 하나만 덩그러니 남는 고아 줄이 줄어든다
     (지시 76 이 이름으로 지목한 상태). 균등 폭이 아니다 — 각자 **자기** basis 에서
     자기 상한까지만 자란다. */
  entity: { flex: "1 1 18rem", minWidth: "12rem", maxWidth: "24rem" },
  /* 닫힌 열거형(상태·우선순위·난이도·역할) — 값이 짧고 개수가 고정이다. 내용만큼만. */
  enum: { flex: "0 0 auto", minWidth: "8rem", maxWidth: "13rem" },
  /* 날짜 — 브라우저 기본 위젯이 요구하는 폭이 있다. */
  date: { flex: "0 0 auto", minWidth: "9.5rem", maxWidth: "12rem" },
  /* 자유 입력(후보 목록이 없는 값). */
  text: { flex: "0 1 14rem", minWidth: "10rem", maxWidth: "18rem" },
  /* 숫자 — 값이 짧고 자릿수가 정해져 있다. 「동시 실행 수」의 값은 «1» 한 글자인데 균등
     격자가 775px 를 줬다(실측 `/settings?tab=ai`) — 폭이 값에 대해 거짓말을 하면 사용자는
     그 칸에 무엇을 넣어야 하는지 잘못 짐작한다. */
  number: { flex: "0 0 auto", minWidth: "7rem", maxWidth: "10rem" },
  /* 켜짐/꺼짐 칩·체크박스. */
  toggle: { flex: "0 0 auto" },
};

/* ── 필터 바 줄 칸의 폭 — **늘어나지 않는다** (UI 3차 · 조합 계약 C-2) ────────────────────
 *
 * 위 `CONTROL_KIND` 는 칸이 줄에 남는 폭을 나눠 가지는 흐름 치수다(Entity 18rem → 24rem 까지 자란다). 필터 바
 * 한 줄에서는 그 늘어남이 칸마다 다른 폭을 만들었다 — 같은 화면에서 프로젝트 384 · 대분류 224 · 상태 132 가 한 줄에
 * 섰고, 줄이 바뀔 때마다 폭이 달라져 칸이 무엇을 기준으로 서는지 읽히지 않았다. 필터 바의 칸은 종류가 폭을
 * 정하고 줄의 남는 폭은 비워 둔다(오른쪽 끝 묶음이 그 자리를 쓴다). 긴 값은 칸 안에서 말줄임되고 전체 값은
 * `title` 이 든다.
 *
 * 검색은 이 표 밖이다 — 줄의 검색 슬롯(20rem)이 정한다(`FilterBar.jsx::searchSlotSx`). 호출부가 `sx` 로 폭을
 * 말하면 그 값이 이긴다(작업 보드 · 스프린트 회의의 두 줄 필터 — D-484).
 *
 * 🔴 **Entity 칸은 크기가 둘이다 — 기본(`entity`)과 `wide`(`entityWide`).** 종류마다 폭을 하나만 두면 값이 긴 축이 잘린다.
 * 1920 팀 티켓의 프로젝트 칸은 208px 이라 이름 뒤의 값 자리가 100px 이 안 됐고, 앞부분이 같은 프로젝트끼리는 잘린 뒤 서로
 * 구분되지 않았다. 사람처럼 값이 짧은 축은 기본 13rem 이다. 프로젝트 · 부서와 팀의 경로 · 회차 · 문서 공간 · 연결된 스케줄은
 * `wide` 다(`EntityCombobox size="wide"`).
 *
 * wide 칸은 **필터 면의 폭**을 보고 세 계단으로 선다. 뷰포트가 아니라 면이 기준이다(`FILTER_SURFACE_CONTAINER`). 면이 96rem
 * 이상이면 20rem, 76rem 이상이면 16rem, 그보다 좁으면 기본과 같은 13rem 이다. 그래서 1366(면 1,070px)에서는 줄바꿈이 예전과
 * 같고 1600(1,288px)은 16rem, 1920(1,608px)은 20rem 이다. 계단은 늘어남이 아니다 — 면의 폭이 같으면 어느 줄에 서든 칸의 폭이
 * 같고, 칸은 줄의 남는 폭을 먹지 않는다(C-2 그대로).
 *
 * 계단은 폭을 직접 말하지 않고 사용자 정의 속성(`--filter-wide`) 하나만 바꾼다. 컨테이너 질의 규칙은 평범한 규칙보다 뒤에
 * 실리므로 계단이 `flex` · `width` 를 직접 말하면 호출부 `sx` 의 폭까지 덮는다. 값 하나만 바꾸면 폭을 말하는 호출부가 여전히
 * 이긴다. */
export const ROW_KIND = {
  search: CONTROL_KIND.search,
  entity: { flex: "0 0 13rem", width: "13rem", minWidth: 0, maxWidth: "100%" },
  entityWide: {
    "--filter-wide": "13rem",
    flex: "0 0 var(--filter-wide)", width: "var(--filter-wide)", minWidth: 0, maxWidth: "100%",
    "@container filter-surface (min-width: 76rem)": { "--filter-wide": "16rem" },
    "@container filter-surface (min-width: 96rem)": { "--filter-wide": "20rem" },
  },
  /* 닫힌 집합의 칸 폭은 **선택지**가 정한다(`selectWidthRem`, D-530) — 지금 값이 아니라 가장 긴 선택지로 재서 값을 바꿔도 칸이
     흔들리지 않는다. 범위는 8 ~ 16rem 이다(예전 상한 13rem 에서 「문제 종류」 값이 여섯 글자에서 잘렸다). */
  enum: { flex: "0 0 auto", minWidth: "8rem", maxWidth: "16rem" },
  /* 「기간」 칸 하나(`PeriodFilter`) — 날짜 칸 둘을 대신한다. 값은 「최근 7일」 · 「9월 2일 ~ 10월 1일」 길이다. */
  period: { flex: "0 0 13rem", width: "13rem", minWidth: 0, maxWidth: "100%" },
  /* 자유 입력은 **값 자리 6rem + 이름**이다 — 이름이 긴 칸(감사 「작업(정확히, 예: user.update)」)을 11rem 에 가두면 이름이
     칸을 다 먹어 친 글자가 안 보인다. 짧은 이름은 11rem 바닥에 선다. */
  text: { flex: "0 0 auto", minWidth: "11rem", maxWidth: "min(24rem, 100%)", "& .MuiInputBase-input": { width: "6rem", minWidth: 0 } },
  date: { flex: "0 0 11rem", width: "11rem", minWidth: 0, maxWidth: "100%" },
  datetime: { flex: "0 0 18rem", width: "18rem", minWidth: 0, maxWidth: "100%" },
  number: CONTROL_KIND.number,
  toggle: CONTROL_KIND.toggle,
};

/** 필터 면을 **크기 컨테이너**로 여는 선언. `FilterBar.jsx::FilterSurface` 가 깔고, 위 `ROW_KIND.entityWide` 의 계단이
 * 이 이름으로 면의 폭을 묻는다. 이름을 붙이는 이유는 면 안에 다른 크기 컨테이너가 생겨도 계단이 그쪽을 보지 않게 하려는
 * 것이다(`density.js::CONTENT_PAIR_CONTAINER` 와 같은 관례). */
export const FILTER_SURFACE_CONTAINER = { containerType: "inline-size", containerName: "filter-surface" };

/** 폼 칸으로 설 때의 치수 — **줄 치수를 통째로 무효로 만든다.**
 *
 * 🔴 위 `CONTROL_KIND` 는 **가로로 흐르는 조건 줄**의 치수다. `flex: 1 1 18rem` 의
 * 18rem 은 그 줄에서 «폭»이지만, 같은 컨트롤을 세로 `Stack`(flex-direction: column)
 * 안에 놓으면 그 값이 **높이**가 된다 — 한 칸이 324px 로 부풀어 새 문서 모달의 폼이
 * 「프로젝트」와 「폴더」 사이에 손바닥만 한 빈칸을 만들었다. 실제로 그랬다.
 *
 * 그래서 폼 자리는 치수를 물려받지 않는다고 **선언**한다. 부모의 방향을 CSS 로 물어볼
 * 수는 없으므로, 아는 쪽(호출부)이 말한다. */
export const FORM_FIELD_SX = { flex: "0 0 auto", width: "100%", minWidth: 0, maxWidth: "none" };

/* ── 필터 바 안의 칸은 **34 한 줄**이고 이름이 칸 **안**에 있다 (핸드오프 README §3 · D1) ──────
 *
 * 폼의 입력은 36 이고 라벨이 위에 선다(`FieldLabel`). 필터 바의 칸은 폼이 아니다 — 「프로젝트
 * 전체」처럼 이름(muted)과 값(600)이 34px 한 칸에 나란히 선다. 예전에는 필터 칸이 폼 입력과 같은
 * 36 에 MUI 노치 라벨(테두리에 얹힌 라벨)이었다: 한 줄의 높이가 버튼(34)과 갈렸고, 라벨이 칸
 * 위로 튀어나와 필터 줄이 폼처럼 읽혔다.
 *
 * **어디가 필터 바인가는 자리가 말한다.** `FilterBar.jsx::FilterSurface` 가 이 문맥을 깔고, 그
 * 안의 `SearchBox` · `FilterSelect` · `EntityCombobox` · `DebouncedTextField` 가 스스로 줄 모양이
 * 된다. 판 · 모달 · 서랍처럼 필터 바 밖에서 필터를 세우는 자리는 `layout="row"` 로 말한다.
 * `layout="form"` · `"fill"` 은 언제나 폼 치수(36 · 라벨 위)다. */
export const FilterRowContext = React.createContext(false);

/** 이 칸이 필터 바의 줄 모양(34 · 칸 안 이름)인가. 같은 줄에 서는 다른 고르개(`TagPicker`)도 이
 * 판정과 아래 `PrefixLabel` 을 같이 쓴다 — 줄 모양을 부품마다 따로 판정하면 한 줄에서 갈린다. */
export function useRowCell(layout) {
  const inRow = React.useContext(FilterRowContext);
  if (layout === "row") return true;
  if (layout === "form" || layout === "fill") return false;
  return layout == null && inRow;
}

/* 줄 칸의 높이 — 버튼(34)과 같은 값. Autocomplete 는 테마가 `inputRoot` 에 36 을 박으므로 거기도
   함께 말한다(크기를 정하는 속성이 둘이면 둘 다 말해야 한다 — `MuiIconButton.sizeSmall` 과 같은 교훈).

   🔴 **칸 해부는 종류와 무관하게 하나다** (UI 3차 · 조합 계약 C-2). 셀렉트 · 자유 입력은 MUI 가 칸 왼쪽에 14 를
   두고 접두 이름 뒤에 6 이 서는데, 자동완성은 `inputRoot` 여백 6 에 입력 여백 8 이 붙어 **접두가 칸 안 6 에서
   시작하고 값이 14 떨어져** 섰다(프로젝트 · 작성자 · 태그 칸 실측). 한 줄에 두 해부가 섞이면 이름과 값의
   세로 열이 칸마다 어긋난다. 자동완성 칸의 여백을 셀렉트와 같게 옮긴다. 다중 선택은 칸 안에 칩을 그리지 않고
   고른 이름을 한 줄로 요약한다(`RowValue`) — 그래서 이 칸은 칩 때문에 높이가 풀리는 일이 없다. 칩은 조건 줄의
   것이다. 「전체」처럼 상태를 말하는 빈 값은 자리표시자여도 값 글자(잉크 · 600)로 선다. */
/* 칸 높이는 컨트롤 높이 변수(`controlHeight`, 기본 34)다 - 선택 발처럼 밀집 줄(30)에 서는 칸은 그릇이
   `densityVars("dense")` 로 함께 낮춘다(D-526). 칸마다 높이 숫자를 따로 적지 않는다. */
const ROW_CELL_SX = {
  "& .MuiInputBase-root, && .MuiAutocomplete-inputRoot": {
    height: controlHeight, minHeight: controlHeight,
  },
  "&& .MuiAutocomplete-inputRoot": { paddingLeft: remPx(14), paddingTop: 0, paddingBottom: 0, flexWrap: "nowrap" },
  "&& .MuiAutocomplete-inputRoot .MuiAutocomplete-input": { paddingLeft: 0, minWidth: remPx(30) },
  "& .MuiInputBase-input, & .MuiSelect-select": { paddingTop: 0, paddingBottom: 0, fontWeight: FONT_WEIGHT.semibold },
  "& .MuiSelect-select": { display: "flex", alignItems: "center", minHeight: 0 },
  "& .MuiInputBase-input:not([data-row-hint])::placeholder": { opacity: 1, color: "text.primary" },
  "& .MuiInputBase-input:not([data-row-hint])::-webkit-input-placeholder": { opacity: 1, color: "text.primary" },
  /* 「검색 또는 입력」 같은 **안내**는 값이 아니다 — 흐리지 않되 muted · 보통 굵기로 선다. */
  "& .MuiInputBase-input[data-row-hint]::placeholder": { opacity: 1, color: "text.secondary", fontWeight: FONT_WEIGHT.regular },
  "& .MuiInputBase-input[data-row-hint]::-webkit-input-placeholder": { opacity: 1, color: "text.secondary", fontWeight: FONT_WEIGHT.regular },
};

const ROW_SEARCH_SX = {
  "& .MuiInputBase-root": { height: controlHeight, minHeight: controlHeight },
  "& .MuiInputBase-input": { paddingTop: 0, paddingBottom: 0 },
};

/* 칸 안의 이름. 값보다 가볍고(muted · 400) 줄어들지 않는다 — 좁아지면 값이 말줄임된다. */
export function PrefixLabel({ id, children }) {
  return (
    <Box
      component="span"
      id={id}
      data-prefix-label=""
      sx={{ color: "text.secondary", fontWeight: FONT_WEIGHT.regular, whiteSpace: "nowrap", flexShrink: 0, marginInlineEnd: 0.75 }}
    >
      {children}
    </Box>
  );
}

/* 칸 안의 값 — 한 줄, 넘치면 말줄임, 전체 값은 `title` 로. 다중 선택의 고른 이름 요약도 이 자리다. */
export function RowValue({ children, title }) {
  return (
    <Box
      component="span"
      title={title}
      data-row-value=""
      sx={{ minWidth: 0, flex: "0 1 auto", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: FONT_WEIGHT.semibold, color: "text.primary" }}
    >
      {children}
    </Box>
  );
}

/* 다중 선택 줄 칸의 요약 — 「가, 나」 한 줄. 넘치면 말줄임이고 전체 이름은 `title` 이 든다. */
export function RowSummary({ names }) {
  const list = (Array.isArray(names) ? names : []).filter((n) => n != null && n !== "").map(String);
  if (!list.length) return null;
  const text = list.join(", ");
  return <RowValue title={text}>{text}</RowValue>;
}

/* 줄 칸의 빈 값 낱말. 칸 안에 이름(접두)이 이미 서 있으므로, 호출부가 준 「역할: 전체」 · 「분류 전체」 ·
   「전체 상태」처럼 **이름이 따로 선 낱말**이면 그 이름을 떼고 나머지만 값 자리에 세운다 — 「역할 역할: 전체」 ·
   「상태 전체 상태」로 같은 낱말이 두 번 읽히지 않는다.

   🔴 이름이 **낱말의 일부**면 떼지 않는다. 예전 규칙은 앞글자만 맞으면 뗐다 — 「팀을 고르세요」가 「을 고르세요」가
   되어 칸이 「팀 · 을 고르세요」로 읽혔다(작업 보드 · 스프린트 회의 실측). 메뉴의 빈 항목 글자는 호출부 낱말 그대로다. */
export function rowAllText(label, allLabel) {
  if (!allLabel) return "전체";
  if (typeof label !== "string" || !label || typeof allLabel !== "string") return allLabel;
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const lead = allLabel.match(new RegExp(`^${escaped}(?:[\\s:：]+)(.+)$`));
  if (lead) return lead[1];
  const tail = allLabel.match(new RegExp(`^(.+?)\\s+${escaped}$`));
  if (tail) return tail[1];
  return allLabel;
}

/** 종류별 기본 폭에 호출부 `sx` 를 얹는다. 호출부가 이기되, 안 주면 의미가 정한다.
 *
 * `layout="form"` · `"fill"` 이면 줄 치수 대신 폼 치수를 깐다(위 `FORM_FIELD_SX` 참고). `fill` 은
 * 좁은 판 · 모달 · 채팅 목록처럼 **부모 폭을 그대로 쓰는** 검색창의 이름이다(핸드오프: 320 은
 * 필터 바 검색 슬롯의 규칙이고, 그보다 좁은 부모에서는 100%). */
/* 폼 · 판 자리의 이름은 **칸 위**에 선다 — 핸드오프 RULES §7(「라벨 위 0.8125rem/600」) · 계획 §0-11(필터 · 폼의
   노치 라벨 금지). 줄 칸이 아닌 자리에서 `label` 을 받으면 MUI 라벨을 테두리 노치에서 떼어 칸 위 흐름에 세운다 —
   글자 · 간격은 `kit.jsx::FieldLabel` 과 같다. 노치 틈(`legend`)은 폭만 0 으로 접는다: 높이를 남겨야 테두리 윗선이
   제자리(칸 윗변)에 그려진다. 날짜 칸(MUI X)도 같은 라벨 · 같은 윤곽 구조라 같은 규칙을 쓴다. */
export const LABEL_ABOVE_SX = {
  "& .MuiInputLabel-root": {
    position: "static", transform: "none", maxWidth: "none", whiteSpace: "normal", overflow: "visible",
    marginBottom: remPx(4), fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.medium, lineHeight: 1.25,
    color: "text.primary",
  },
  "& .MuiInputLabel-root.Mui-focused, & .MuiInputLabel-root.Mui-error, & .MuiInputLabel-root.Mui-disabled": {
    color: "text.primary",
  },
  "& .MuiFormLabel-asterisk": { color: "error.main" },
  "& .MuiOutlinedInput-notchedOutline legend, & .MuiPickersOutlinedInput-notchedOutline legend": { maxWidth: "0.01px" },
};

/** 칸 sx 에 위 라벨 규칙을 얹는다(sx 가 함수여도 모양을 지킨다). */
export function withLabelAbove(sx) {
  if (typeof sx === "function") return (theme) => ({ ...LABEL_ABOVE_SX, ...sx(theme) });
  return { ...LABEL_ABOVE_SX, ...sx };
}

/* `size` — 줄 칸의 크기. `"wide"` 는 그 종류에 wide 치수(`ROW_KIND.entityWide`)가 있을 때만 뜻이 있고, 줄 밖(흐름 치수 ·
   폼 치수)에서는 쓰지 않는다. */
export function kindSx(kind, sx, layout, row = false, size) {
  const rowSpec = (size === "wide" && ROW_KIND[`${kind}Wide`]) || ROW_KIND[kind];
  const base = layout === "form" || layout === "fill"
    ? FORM_FIELD_SX
    : (row ? (rowSpec || CONTROL_KIND[kind] || null) : (CONTROL_KIND[kind] || null));
  /* 검색창은 친 글자라 값 굵기(600)를 받지 않는다 — 이름표가 없는 칸이다. */
  const extra = row === "search" ? ROW_SEARCH_SX : row ? ROW_CELL_SX : null;
  if (!base && !extra) return sx;
  if (typeof sx === "function") return (theme) => ({ ...base, ...extra, ...sx(theme) });
  return { ...base, ...extra, ...sx };
}

/* 빈 값(전체·없음)을 고를 수 있는 select 에 반드시 함께 넘긴다.
 * MUI Select 는 값이 '' 이면 '아직 아무것도 안 골랐다'로 보고 라벨을 축소하지 않은 채
 * 입력 자리에 그대로 둔다 — 그러면 고른 값(전체·없음)이 화면에서 사라지고 상자가 빈 것처럼
 * 보인다. displayEmpty 로 빈 값의 항목 라벨을 그리게 하고, 라벨은 항상 노치로 올린다. */
export const EMPTYABLE_SELECT = { SelectProps: { displayEmpty: true }, InputLabelProps: { shrink: true } };

/* ── 후보에 없는 값 ──────────────────────────────────────────────────────────
 *
 * 🔴 고르개는 값이 후보에 없으면 **값 자체를 라벨로** 썼다. 그 값이 UUID 이면 화면에
 * `62134ac8-831e-4071-bb07-d7c3144d85eb` 가 그대로 뜬다 — 실제로 운영의 새 문서 모달과
 * 문서 필터 줄이 그랬다(후보 질의가 422 라 목록이 비어 있었고, 아무 오류도 안 떴다).
 *
 * 그렇다고 「모르는 값」을 전부 가리지는 않는다. 상태 이름·태그처럼 **값이 곧 이름**인
 * 축이 있고, 그 자리에서 값을 감추면 고른 것이 사라진다. 그래서 가리는 것은 **식별자
 * 모양**뿐이다: 사람에게 아무 뜻이 없다는 것이 모양만으로 확실한 값.
 *
 * 값이 아직 오는 중인지(`loading`)까지 구분한다 — 「없는 항목」과 「아직 못 받았다」는
 * 다른 사실이고, 둘을 같은 문구로 말하면 새로 고치면 될 것을 지워야 하는 것으로 읽는다. */
const OPAQUE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$|^[0-9a-f]{32}$/i;

/** 값이 사람에게 뜻이 없는 식별자(UUID 계열)인가. */
export function isOpaqueId(value) {
  return OPAQUE_ID.test(String(value == null ? "" : value).trim());
}

/** 후보에서 못 찾은 값의 라벨. 식별자면 사람이 읽을 문장으로 바꾼다. */
export function unmatchedLabel(value, loading) {
  const text = String(value == null ? "" : value);
  if (!isOpaqueId(text)) return text;
  return loading ? "불러오는 중" : "이름을 확인할 수 없는 항목";
}

/* ── 검색 팝오버의 항목 한 줄 — `PickerOption` (핸드오프 README §6 · RULES §3 · ACCEPTANCE G3) ──
 *
 * 사람 · 프로젝트 · 태그처럼 늘어나는 목록은 셀렉트가 아니라 검색 팝오버다: 위에 검색 입력,
 * 아래에 **32px 항목**(앞 그림 + 이름 + 보조 식별자 muted), 고른 항목에 체크. 새 부품이 아니라
 * `EntityCombobox` 가 그리는 목록의 계약이다(P-6). 예전에는 항목이 이름과 보조 식별자를 두 줄로
 * 쌓아 48~56px 로 섰고, 고른 것이 무엇인지는 배경색 하나로만 말했다.
 *
 * 한 줄이다 — 이름이 길면 이름이, 그다음 보조 식별자가 말줄임되고 전체는 `title` 이 든다.
 * `aria-selected` 는 MUI 가 `props` 로 준다(그대로 흘려보낸다). */
/* `sx` — 자동완성 목록 밖(모달 안에 늘 펼쳐 둔 사람 목록)에서 줄에 여백 · 가리킴 · 포커스 링을 더할 때만 쓴다.
   자동완성 안에서는 MUI 가 그 셋을 준다. */
export function PickerOption({ liProps, label, secondary, leading, suffix, selected, sx }) {
  const { key, ...rest } = liProps || {};
  const full = [label, secondary].filter((v) => typeof v === "string" && v).join(", ");
  return (
    <Box
      component="li"
      key={key}
      {...rest}
      data-picker-option=""
      title={full || undefined}
      sx={[
        {
          "&&": {
            display: "flex", alignItems: "center", gap: 1, minWidth: 0,
            minHeight: remPx(CONTROL.menuItem), paddingTop: 0, paddingBottom: 0,
          },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {leading}
      <Box component="span" sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0, flex: 1, overflow: "hidden" }}>
        <Typography component="span" variant="body2" noWrap sx={{ minWidth: 0, flexShrink: 1 }}>{label}</Typography>
        {suffix}
        {secondary ? (
          <Typography component="span" variant="caption" color="text.secondary" noWrap sx={{ minWidth: 0, flexShrink: 2 }}>
            {secondary}
          </Typography>
        ) : null}
      </Box>
      <CheckRoundedIcon
        aria-hidden="true"
        sx={{ flexShrink: 0, fontSize: remPx(ICON.inline), color: "primary.main", visibility: selected ? "visible" : "hidden" }}
      />
    </Box>
  );
}

/** 후보를 **내 계정이 맨 위**가 되게 세운다(핸드오프 README §6). 나머지 순서는 그대로다. */
export function mineFirst(options, myId) {
  if (myId == null || myId === "") return options;
  const at = options.findIndex((o) => o && String(o.value) === String(myId));
  if (at <= 0) return options;
  return [options[at], ...options.slice(0, at), ...options.slice(at + 1)];
}

/** 후보가 많아져도 화면 높이가 같이 늘어나지 않게 한다. 넘는 분은 안에서 스크롤한다. */
export const FILTER_LISTBOX_SX = { maxHeight: "16rem", overflow: "auto" };
const SELECT_MENU = { MenuProps: { PaperProps: { sx: FILTER_LISTBOX_SX } } };

/* 타이핑 중인 값은 **자기가 든다** (PF4).
 *
 * 예전에는 타이핑 중인 값이 1,000줄짜리 화면 컴포넌트에 살았다. 그래서 글자 하나를 칠
 * 때마다 화면 전체가 다시 실행됐다 — 표 100행, 필터 일곱 개, 상세 드로어까지.
 *
 * 입력과 디바운스를 부품 안으로 내리면 타이핑은 이 작은 부품만 다시 그린다. 부모는
 * **확정된** 값이 바뀔 때만 다시 그린다.
 *
 * `value` 는 바깥에서 값이 바뀌는 경우(저장된 뷰 부르기, 필터 지우기, 뒤로가기)를 위한
 * 것이다. 그때는 `onCommit` 을 부르지 않는다 — 부르면 복원한 페이지 번호를 1로 되돌려,
 * 사용자가 링크를 열었는데 다른 화면을 보게 된다.
 *
 * `normalize` 는 확정하는 값의 모양이다(검색창은 `normalizeQuery`). 주면 **다듬은 값끼리** 견주고 다듬은 값을
 * 확정한다. 「회의」를 확정한 뒤 끝에 공백 하나를 더 쳐도 조건이 바뀌지 않았으므로 다시 확정하지 않는다.
 * 입력 상자의 글자는 건드리지 않는다 — 방금 확정한 값이 `value` 로 돌아오는 것은 자기가 보낸 값의 메아리라서
 * 초안을 다시 쓰지 않는다. 그때 초안을 다시 쓰면 치는 도중에 끝 공백이 사라져 다음 낱말이 앞 낱말에 붙는다.
 * 주지 않으면(자유 입력 필터) 친 값을 그대로 견주고 그대로 확정한다.
 */
export function useDebouncedCommit(value, onCommit, delay = FILTER_DEBOUNCE_MS, normalize = keepAsTyped) {
  const [draft, setDraft] = React.useState(value);
  const committed = React.useRef(value);

  React.useEffect(() => {
    if (value === committed.current) return;
    committed.current = value;
    setDraft(value);
  }, [value]);

  React.useEffect(() => {
    const next = normalize(draft);
    if (next === normalize(committed.current)) return undefined;
    const t = setTimeout(() => { committed.current = next; onCommit(next); }, delay);
    return () => clearTimeout(t);
  }, [draft, onCommit, delay, normalize]);

  return [draft, setDraft];
}

/** `useDebouncedCommit` 의 기본 모양 — 친 값 그대로다. 모듈 최상위에 두어 참조가 렌더마다 안 바뀐다. */
function keepAsTyped(value) {
  return value;
}

/* 검색창. `type="search"` 라 스크린리더·검사 모두 searchbox 로 잡는다.
 *
 * **기본 `sx` 가 없다** (W5). 예전 기본값은 `{ gridColumn: { sm: "span 2" } }` 였는데,
 * JS 기본 인자는 `undefined` 를 «안 넘긴 것» 으로 보므로 `sx={undefined}` 로 «기본을 끄겠다»
 * 는 호출부에서 오히려 **되살아났다**. 실제로 `/board`·`/ideas` 가 그 함정을 밟아 검색창이
 * 2칸을 차지했고, 그 결과 정렬 select 하나가 두 번째 줄로 혼자 밀려났다 —
 * R-76 이 이름으로 지목한 «Sort Select 하나만 아래 왼쪽에 홀로» 가 바로 이것이다.
 * `OrgTree.jsx` 는 이 함정을 알고 `sx={{}}` 로 우회하고 있었다(주석까지 달아 두었다):
 * 한 호출부가 우회로 알고 있는 기본값은 기본값이 아니라 결함이다. 폭은 이제 종류가 정한다.
 */
export const SearchBox = React.memo(function SearchBox({
  value, placeholder, ariaLabel, onSearch, sx, layout, immediate = false,
}) {
  /* 확정하는 값은 화면 · 주소의 검색어 모양(`normalizeQuery`)이다 — 앞뒤 · 연속 공백만 다른 입력은 새 검색이 아니다.
     입력 상자에는 친 글자가 그대로 남는다(`useDebouncedCommit` 머리 주석). */
  const debounced = useDebouncedCommit(value, onSearch, FILTER_DEBOUNCE_MS, normalizeQuery);
  /* `immediate` — **제출형 검색**(통합 검색)은 부모가 글자마다 값을 들고 Enter · 「검색」 단추가
     확정한다. 디바운스로 확정하면 Enter 를 누른 순간 부모 값이 아직 옛 글자일 수 있다. */
  const [draft, setDraft] = immediate ? [value, onSearch] : debounced;
  const row = useRowCell(layout);
  return (
    <TextField
      type="search"
      size="small"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      placeholder={placeholder}
      inputProps={{ "aria-label": ariaLabel }}
      InputProps={{ startAdornment: <InputAdornment position="start"><SearchRoundedIcon fontSize="small" /></InputAdornment> }}
      data-filter-kind="search"
      sx={kindSx("search", sx, layout, row ? "search" : false)}
    />
  );
});

/* 자유 입력 필터(대분류처럼 후보 목록이 없는 값). 검색창과 같은 이유로 자기 상태를 든다.
 *
 * **디바운스가 여기 있는 이유** (W5 · F-W5D-115): 예전에는 이 자리가 맨 `TextField` 였고
 * `onChange` 가 곧바로 필터 상태와 질의 키를 갱신했다 — 서버 필터인 키는 **타자 한 글자마다**
 * API 를 한 번씩 불렀다. 검색창은 이미 이 부품 계열로 디바운스를 하고 있었는데 자유 입력
 * 필터만 규칙이 갈려 있었다.
 *
 * `freeTextReason` 은 «이 자유 텍스트는 일부러 그렇다» 는 **선언**이다. 후보 목록이 존재하지
 * 않는 값(외부 시스템 식별자, 여러 object_type 을 가로지르는 대상 ID)이 그렇다. 그 **문장이
 * 그대로** DOM 에 `data-free-text` 로 남아 프로브가 그 자리를 결함으로 세지 않는다.
 *
 * **억제 마커가 아니다.** `plain_dropdown_for_entity` 는 끌 수 없는 검사이고(QA_SUPPRESSIONS
 * 규칙 4) 그것이 옳다 — 여기서 말하는 것은 «이 검사를 끄겠다» 가 아니라 «이 칸은 애초에
 * 선택기가 될 수 없다(고를 후보가 세상에 없다)» 는 **종류 선언**이다. 값이 boolean 이 아니라
 * 문장인 이유도 같다: 읽는 사람이 DOM 에서 바로 그 이유를 본다. */
export const DebouncedTextField = React.memo(function DebouncedTextField({
  value, onCommit, label, placeholder, sx, kind = "text", inputProps, freeTextReason, layout, type,
}) {
  const [draft, setDraft] = useDebouncedCommit(value, onCommit);
  const row = useRowCell(layout);
  return (
    <TextField
      /* `type` — 시각 조건(`datetime-local`)도 같은 칸 모양으로 선다. 브라우저가 자리표시자를 무시하는
         종류라 칸 안 이름이 그 칸이 무엇인지 말한다. */
      type={type}
      size="small"
      label={row ? undefined : label}
      InputLabelProps={row ? undefined : { shrink: true }}
      InputProps={row && label ? { startAdornment: <PrefixLabel>{label}</PrefixLabel> } : undefined}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      /* 값이 없을 때 **아무 말도 안 하는 상자**를 만들지 않는다 (W5 재정정 — 독립 검수 실측:
         「대분류」가 모든 뷰포트에서 224px 빈 상자였다). 같은 줄의 select 들은 전부 「… 전체」
         라고 자기 상태를 말하는데 이 칸만 비어 있으면 사용자는 그것을 «덜 그려졌다» 로 읽는다.
         조건이 없는 자유 입력의 뜻은 정확히 «전체» 다 — 그 낱말을 그대로 쓴다. */
      placeholder={placeholder || "전체"}
      inputProps={{ maxLength: 200, ...(row && label ? { "aria-label": label } : null), ...inputProps }}
      data-filter-kind={kind}
      data-free-text={freeTextReason || undefined}
      sx={row ? kindSx(kind, sx, layout, row) : withLabelAbove(kindSx(kind, sx, layout, row))}
    />
  );
});

/* 선택 필터.
 *
 * **렌더 함수 밖(모듈 최상위)에 있어야 한다.** 화면 컴포넌트 본문 안에서 정의하면 부모가
 * 다시 그려질 때마다 React 가 다른 타입으로 보고 select 를 통째로 새로 마운트한다
 * (포커스와 열려 있던 드롭다운이 매번 날아간다).
 *
 * `options` 는 문자열 배열이거나 `{value,label}` 배열이다. 값과 보여줄 이름이 다른 필터
 * (담당자는 앱 user_id 로 나가고 화면에는 이름이 보인다)가 있어서 둘 다 받는다. */
export function FilterSelect({
  label, value, onChange, options, allLabel, disabled, sx, kind = "enum", multiple = false,
  layout, noAllOption = false, size,
}) {
  /* `noAllOption` — 「전체」가 답이 될 수 없는 축(정렬 · 연도 · 월). 빈 항목을 세우지 않는다 —
     세우면 고를 수 없던 값(정렬 없음)이 메뉴에 생긴다. `EntityCombobox` 와 같은 이름이다. */
  const list = normalizeOptions(options);
  const row = useRowCell(layout);
  /* 줄 칸의 폭 — 닫힌 집합(`enum`)이거나 호출부가 크기를 말한 칸만 선택지로 잰다(Entity 처럼 종류가 폭을 정하는 칸은 그대로다). */
  const cellRem = row && (kind === "enum" || size) ? selectWidthRem({ label, options: list, allLabel, noAllOption, size }) : null;
  const rowSx = withCellWidth(cellRem, sx);
  if (multiple) {
    const selected = Array.isArray(value) ? value.map(String) : (value ? [String(value)] : []);
    for (const item of selected) {
      if (item && !list.some((o) => o.value === item)) {
        list.unshift({ value: item, label: unmatchedLabel(item, false) });
      }
    }
    const labelOf = (v) => (list.find((o) => o.value === v) || { label: v }).label;
    const text = (picked) => (
      picked && picked.length
        ? picked.map(labelOf).join(", ")
        : (row ? rowAllText(label, allLabel) : (allLabel || `${label} 전체`))
    );
    return (
      <TextField
        select size="small" label={row ? undefined : label} value={selected} disabled={disabled}
        data-filter-kind={kind}
        sx={row ? kindSx(kind, rowSx, layout, row) : withLabelAbove(kindSx(kind, sx, layout, row))}
        onChange={(e) => onChange(Array.isArray(e.target.value) ? e.target.value : [])}
        InputLabelProps={row ? undefined : { shrink: true }}
        inputProps={row ? { "aria-label": label } : undefined}
        SelectProps={{
          multiple: true,
          displayEmpty: true,
          renderValue: row
            ? (picked) => (
              <>
                <PrefixLabel>{label}</PrefixLabel>
                <RowValue title={`${label} ${text(picked)}`}>{text(picked)}</RowValue>
              </>
            )
            : text,
          ...SELECT_MENU,
        }}
      >
        {list.map((o) => (
          <MenuItem key={o.value} value={o.value}>
            {o.label}
          </MenuItem>
        ))}
      </TextField>
    );
  }
  if (value && !list.some((o) => o.value === value)) {
    list.unshift({ value, label: unmatchedLabel(value, false) });
  }
  if (row) {
    /* 줄 칸 — 이름은 칸 안 접두(muted), 값은 600 한 줄. 「… 전체」 항목의 메뉴 글자는 그대로 두고
       칸에는 이미 이름이 있으니 값 자리에 「전체」만 선다(같은 낱말을 두 번 쓰지 않는다). */
    const shown = (v) => {
      if (v === "" || v == null) return rowAllText(label, allLabel);
      const hit = list.find((o) => String(o.value) === String(v));
      return hit ? hit.label : String(v);
    };
    return (
      <TextField
        select size="small" value={value == null ? "" : value} disabled={disabled}
        data-filter-kind={kind}
        sx={kindSx(kind, rowSx, layout, true)}
        onChange={(e) => onChange(e.target.value)}
        inputProps={{ "aria-label": label }}
        SelectProps={{
          displayEmpty: true,
          renderValue: (v) => (
            <>
              <PrefixLabel>{label}</PrefixLabel>
              <RowValue title={`${label} ${shown(v)}`}>{shown(v)}</RowValue>
            </>
          ),
          ...SELECT_MENU,
        }}
      >
        {noAllOption ? null : <MenuItem value="">{allLabel || `${label} 전체`}</MenuItem>}
        {list.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
      </TextField>
    );
  }
  return (
    <TextField
      select size="small" label={label} value={value} disabled={disabled}
      data-filter-kind={kind}
      sx={withLabelAbove(kindSx(kind, sx, layout))}
      onChange={(e) => onChange(e.target.value)}
      {...EMPTYABLE_SELECT}
      SelectProps={{ ...EMPTYABLE_SELECT.SelectProps, ...SELECT_MENU }}
    >
      {noAllOption ? null : <MenuItem value="">{allLabel || `${label} 전체`}</MenuItem>}
      {list.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
    </TextField>
  );
}

/* ── 닫힌 집합 칸의 폭 — 선택지로 정한다 (F4 · D-530) ─────────────────────────────────────────
 *
 * 예전 칸은 `flex: 0 0 auto` 라 **지금 고른 값**의 길이가 폭을 정했다 — 「전체」에서 「담당자를 포털 계정으로 연결하지 못한 티켓」
 * 으로 바꾸는 순간 칸이 늘어 옆 칸을 밀었고, 상한(13rem)에 닿은 긴 값은 여섯 글자에서 잘렸다. 폭은 선택지 전부를 보고 한 번 정한다:
 * 왼쪽 여백 14 + 칸 안 이름 + 간격 6 + 가장 긴 선택지(600) + 화살표 자리 32 + 2(테두리 · 반올림 여유)를 0.5rem 단위로 올리고
 * [8, 16]rem 으로 묶는다. 넘치는 값은 칸 안에서 말줄임이고 전체 값은 `title` 이 든다. 호출부가 크기를 말하면(`size`) 그 표가 이긴다:
 * S 8 · M 10 · L 13 · XL 16rem. */
export const FILTER_SELECT_SIZES = Object.freeze({ S: 8, M: 10, L: 13, XL: 16 });
export const SELECT_WIDTH_RANGE_REM = Object.freeze([8, 16]);
/* 칸 글자는 입력 글자(body1, 0.9375rem)다. 여백은 MUI 선택 상자의 실제 값(왼쪽 14 · 오른쪽 32)에 접두 간격 6 과 여유 2 를 더한 것이다. */
const CELL_FONT_REM = 0.9375;
const SELECT_CELL_CHROME_REM = (14 + 6 + 32 + 2) / 16;

/** 선택지로 정한 줄 칸 폭(rem 숫자). `size` 를 주면 그 크기다. */
export function selectWidthRem({ label, options, allLabel, noAllOption = false, size } = {}) {
  if (size && FILTER_SELECT_SIZES[size]) return FILTER_SELECT_SIZES[size];
  const list = normalizeOptions(options);
  const words = list.map((o) => (o && o.label != null ? String(o.label) : String((o && o.value) ?? "")));
  if (!noAllOption) words.push(rowAllText(label, allLabel));
  const longest = words.reduce((m, w) => Math.max(m, textRem(w, CELL_FONT_REM, 600)), 0);
  const need = SELECT_CELL_CHROME_REM + (label ? textRem(label, CELL_FONT_REM, 400) : 0) + longest;
  const [lo, hi] = SELECT_WIDTH_RANGE_REM;
  return Math.min(hi, Math.max(lo, stepUp(need)));
}

/* 칸 폭 선언을 호출부 `sx` 아래에 깐다 — 호출부가 폭을 말하면 그것이 이긴다. */
function withCellWidth(rem, sx) {
  if (rem == null) return sx;
  const width = { flex: `0 0 ${rem}rem`, width: `${rem}rem` };
  if (typeof sx === "function") return (theme) => ({ ...width, ...sx(theme) });
  return { ...width, ...sx };
}

/** `["가","나"]` 와 `[{value,label,secondary}]` 를 한 모양으로 편다. */
export function normalizeOptions(options) {
  return (Array.isArray(options) ? options : []).map(
    (o) => (typeof o === "string" ? { value: o, label: o } : o),
  ).filter(Boolean);
}

/* 후보의 이름. 입력 상자의 글자와 후보 거르기가 같은 값을 쓴다. */
const optionLabelOf = (o) => (o && o.label != null ? String(o.label) : "");

/* 후보 거르기 — 이름과 보조 글자(소속 · 코드 · 기간)를 칸마다 따로, 서버와 같은 접기로 본다(`lib/search.js`).
   보조 글자도 보는 이유는 목록 줄이 그 글자를 함께 보여 주기 때문이다. 보이는 글자로 찾을 수 있어야 하므로 프로젝트는
   코드로도, 사람은 소속으로도 찾는다. 공백 · 대소문자 · 전각 표기가 달라도 같은 후보가 남는다. */
const ENTITY_FILTER = foldedFilterOptions({ stringify: (o) => [optionLabelOf(o), o && o.secondary] });

/* ── Entity Selector — 검색형 Combobox (R-5 · C2 · 지시 0-2.17) ──────────────
 *
 * **`FilterSelect` 와 무엇이 다른가.** `FilterSelect` 는 값 집합이 **닫힌** 축 전용이다
 * (상태·우선순위·난이도·역할). `EntityCombobox` 는 값 집합이 **데이터가 쌓이는 만큼
 * 자란다**(프로젝트·담당자·사용자·부서·조직·일정·워크플로). 그 둘을 같은 부품으로 그리면
 * 프로젝트 200개가 스크롤 목록이 되고, 사용자는 이름을 알면서도 그것을 눈으로 찾아야 한다.
 *
 * 이 부품이 지키는 것 다섯 (전부 실측된 결함에서 나왔다):
 *   ① **검색 가능.** 입력하면 후보가 걸러진다. 지금 제품에는 이런 자리가 **0개**였다 —
 *      `plain_dropdown_for_entity` 가 664 페이지에서 pass 0 · fail 80 이었던 이유다.
 *   ② **고른 값을 끝까지 알 수 있다.** 잘리더라도 `title` 로 전체 값이 나온다(C2 «값 식별성»).
 *   ③ **후보끼리 구분된다.** 앞부분이 같은 긴 이름은 보조 식별자(부서·코드·기간)를 둘째 줄로
 *      함께 보인다 — 자르고 끝내면 「P. SK 하이닉스 [용인…」 두 개가 같은 값이 된다.
 *   ④ **주소에서 복원한 값이 사라지지 않는다.** 후보 목록에 없는 값이면 그 값 자체를 후보로
 *      끼워 넣는다(`FilterSelect` 와 같은 규율).
 *   ⑤ **키보드.** MUI Autocomplete 가 ARIA 1.2 combobox 시맨틱·화살표·Home/End·Escape 를
 *      내장한다. 새 의존성이 아니다 — 이미 `MyTickets.jsx` 의 담당자 선택이 쓰고 있다.
 *
 * `size="wide"` 는 값이 긴 축(프로젝트 · 부서와 팀의 경로 · 회차 · 문서 공간 · 연결된 스케줄)의 줄 칸이다. 폭은 필터 면이
 * 정한다(`ROW_KIND.entityWide`). 사람처럼 값이 짧은 축은 주지 않는다.
 */
export function EntityCombobox({
  label, value, onChange, options, loading, disabled, sx, kind = "entity", id,
  placeholder, allLabel, noOptionsText = "일치하는 항목이 없습니다", required, helperText,
  ariaLabelledBy, ariaDescribedBy, hideLabel, multiple = false, renderOption, noAllOption = false, layout, myId,
  open, disablePortal, size,
}) {
  const list = mineFirst(normalizeOptions(options), myId);
  /* 필터 바 줄 칸이면 이름이 칸 안 접두로 선다(위 `FilterRowContext`). 이름을 밖에서 그리는 폼
     자리(`hideLabel` · `ariaLabelledBy`)는 줄 칸이 아니다. */
  const row = useRowCell(layout) && !hideLabel && !ariaLabelledBy;
  /* 크기는 줄 칸에서만 뜻이 있다 — 폼 칸은 부모 폭을 그대로 쓴다. 칸 뿌리의 `data-filter-size` 는 실브라우저 잣대
     (`composition_checks.py` · `filter_e2e.py`)가 기본 칸과 wide 칸의 폭 계약을 가르는 표식이다. */
  const cellSize = row && size === "wide" ? "wide" : undefined;
  // 기본 렌더(라벨 + 보조줄)는 그대로 두고, 부르는 쪽이 다른 그림(아바타 등)이 필요하면
  // 이것 하나로 갈아 끼운다 — §15.3 의 UserPicker 가 이 자리를 쓴다.
  const renderRow = renderOption || ((props, o, state) => (
    <PickerOption
      liProps={{ ...props, key: props.key ?? o.value }}
      label={o.label}
      secondary={o.secondary}
      selected={!!(state && state.selected)}
    />
  ));
  if (multiple) {
    const selected = Array.isArray(value) ? value : (value ? [value] : []);
    /* 고른 칩의 낱말 — 옵션이 `tagLabel` 을 들면 칩은 그 짧은 이름만 말한다(사람 고르개: 칩은 「김하나」,
       목록 줄과 검색은 「김하나 (개발본부 팀장)」). 전체 이름은 칩의 `title` 로 남는다. 없으면 MUI 기본 칩이
       옵션 이름을 그대로 쓴다. */
    const shortTags = list.some((o) => o && o.tagLabel);
    const current = selected.map((v) => (
      list.find((o) => String(o.value) === String(v))
        || { value: v, label: unmatchedLabel(v, loading) }
    ));
    return (
      <Autocomplete
        id={id}
        multiple
        open={open}
        disablePortal={disablePortal}
        size="small"
        openOnFocus
        autoHighlight
        handleHomeEndKeys
        disabled={disabled}
        loading={!!loading}
        options={list}
        value={current}
        onChange={(e, next) => onChange((next || []).map((o) => o.value).filter((v) => v !== "" && v != null))}
        getOptionLabel={optionLabelOf}
        filterOptions={ENTITY_FILTER}
        isOptionEqualToValue={(a, b) => String(a.value) === String(b.value)}
        noOptionsText={noOptionsText}
        loadingText="불러오는 중…"
        data-filter-kind={kind}
        data-filter-size={cellSize}
        sx={kindSx(kind, sx, layout, row, cellSize)}
        ListboxProps={{ sx: FILTER_LISTBOX_SX }}
        renderOption={renderRow}
        renderTags={row
          /* 줄 칸은 칩을 그리지 않는다 — 고른 이름을 한 줄로 요약하고 전체는 `title` 이 든다. 하나씩 떼는 칩은
             필터 바의 조건 줄이 그린다(UI 3차 · 조합 계약 C-2). */
          ? (tagValue) => <RowSummary names={tagValue.map((o) => o.tagLabel || o.label)} />
          : (shortTags ? (tagValue, getTagProps) => tagValue.map((o, i) => {
            const { key, ...rest } = getTagProps({ index: i });
            return <Chip key={key ?? o.value} {...rest} size="small" label={o.tagLabel || o.label} title={o.label} />;
          }) : undefined)}
        renderInput={(params) => (
          <TextField
            {...params}
            label={hideLabel || row ? undefined : label}
            required={required}
            helperText={helperText}
            InputLabelProps={row ? params.InputLabelProps : { ...params.InputLabelProps, shrink: true }}
            InputProps={row
              ? { ...params.InputProps, startAdornment: <><PrefixLabel>{label}</PrefixLabel>{params.InputProps.startAdornment}</> }
              : params.InputProps}
            /* 이름을 바깥 `FieldLabel` 이 그리는 폼 칸이면 그 라벨을 가리키고(`ariaLabelledBy`), 칸 밖의 도움말 · 오류 줄은
               `ariaDescribedBy` 로 잇는다 — 아래 단일 고르개와 같은 계약이다. 가리킬 것이 없으면 키를 아예 안 싣는다:
               `undefined` 를 실으면 MUI 가 도움말에서 이은 설명을 덮어 지운다. */
            inputProps={{
              ...params.inputProps,
              ...(row ? { "aria-label": label } : null),
              ...(ariaLabelledBy ? { "aria-labelledby": ariaLabelledBy } : null),
              ...(ariaDescribedBy ? { "aria-describedby": ariaDescribedBy } : null),
            }}
            /* 고른 값이 있으면 자리표시자를 겹쳐 세우지 않는다 — 줄 칸(요약)도 폼 칸(칩)도 같다. 폼 칸에서는 「UI QA ⊗ 예: 김하나」처럼
               예시 글이 고른 사람 칩 옆에 값처럼 섰다(새 티켓 담당자, UI 3차 P4 눈 대조). */
            placeholder={current.length ? undefined : (placeholder || (row ? rowAllText(label, allLabel) : (allLabel || `${label} 전체`)))}
            sx={row ? undefined : LABEL_ABOVE_SX}
          />
        )}
      />
    );
  }
  const all = { value: "", label: allLabel || `${label} 전체` };
  /* `noAllOption` — 생성 폼처럼 「전체」가 답이 될 수 없는 자리. 필터 어휘(「… 전체」)가
     선택지로 서면 고르는 값의 뜻이 흐려진다 — 비우기는 여전히 된다(입력을 지우면 된다). */
  const withAll = noAllOption ? list : [all, ...list];
  /* 값이 없으면 입력을 **비워 둔다** — 「… 전체」 는 자리표시자로 보이고 목록에도 남는다.
     값을 입력 **글자**로 넣으면(MUI Select 의 `displayEmpty` 관용) 사용자가 타이핑할 때
     그 글자 뒤에 덧붙어 후보가 0개가 된다. 실브라우저에서 확인했다: 「프로젝트 전체」 상태에서
     ArrowDown 으로 열고 「D.」를 치면 입력이 「프로젝트 전체D.」가 되어 23개가 0개가 됐다.
     보이는 결과는 자리표시자 쪽이 오히려 정확하다 — «아직 안 골랐다» 가 잉크 무게로도 드러난다. */
  const current = value
    ? (list.find((o) => String(o.value) === String(value))
      || { value, label: unmatchedLabel(value, loading) })
    : null;
  return (
    <Autocomplete
      id={id}
      open={open}
      disablePortal={disablePortal}
      size="small"
      openOnFocus
      autoHighlight
      handleHomeEndKeys
      disableClearable
      /* 고른 값이 있는 상태에서 타이핑하면 **덧붙이지 말고 갈아 끼운다.** 없으면 입력이
         「프로젝트 전체하이닉스」가 되어 후보가 0개가 된다 — 검색형인데 검색이 안 되는 상태다.
         `clearOnBlur` 는 그 짝이다: 반쯤 친 글자를 두고 자리를 뜨면 화면의 글자와 실제 값이
         갈라진다(고른 값은 그대로인데 상자에는 다른 글자가 남는다). */
      selectOnFocus
      clearOnBlur
      disabled={disabled}
      loading={!!loading}
      options={withAll}
      value={current}
      onChange={(e, next) => onChange(next ? next.value : "")}
      getOptionLabel={optionLabelOf}
      filterOptions={ENTITY_FILTER}
      isOptionEqualToValue={(a, b) => String(a.value) === String(b.value)}
      noOptionsText={noOptionsText}
      loadingText="불러오는 중…"
      data-filter-kind={kind}
      data-filter-size={cellSize}
      sx={kindSx(kind, sx, layout, row, cellSize)}
      ListboxProps={{ sx: FILTER_LISTBOX_SX }}
      renderOption={renderRow}
      renderInput={(params) => {
        /* 라벨이 있을 때만 노치를 연다. `shrink: true` 를 라벨 없이 넘기면 TextField 가
           `notched=true` 를 강제하고, 윗테두리에 빈 구멍이 난다 — 폼의 `FieldLabel` 아래
           entity 칸이 그 함정이다. 필터처럼 노치 라벨이 있는 자리는 그대로 항상 축소한다. */
        const shownLabel = hideLabel ? undefined : label;
        return (
        <TextField
          {...params}
          /* `hideLabel` 은 **이름이 이미 화면에 있는 자리**를 위한 것이다 — 상세 화면의
             `MetaRow` 처럼 왼쪽 열이 「부서」를 이미 적고 있으면 노치 라벨이 같은 낱말을
             한 번 더 그린다. 이름을 지우는 게 아니라 **보이는 자리에서만 뺀다**: 접근
             이름은 아래 `aria-label` 로 그대로 남는다(이름 없는 combobox 는 스크린리더도
             시험도 부를 수 없다). */
          label={row ? undefined : shownLabel}
          required={required}
          helperText={helperText}
          InputLabelProps={{ ...params.InputLabelProps, shrink: Boolean(shownLabel) && !row }}
          InputProps={row
            ? { ...params.InputProps, startAdornment: <><PrefixLabel>{label}</PrefixLabel>{params.InputProps.startAdornment}</> }
            : params.InputProps}
          placeholder={current ? placeholder : (placeholder || (row ? rowAllText(label, allLabel) : all.label))}
          /* **한 줄에 잉크 무게는 하나다** (W5 재정정 — 독립 검수 실측 2.68:1 vs 옆 select 17.24:1).
             값이 없을 때 이 상자가 말하는 「… 전체」는 자리표시자가 아니라 **고른 값**이다 —
             옆의 `FilterSelect` 는 같은 뜻을 빈 `MenuItem` 의 **본문 글자**로 그린다. 브라우저
             기본 자리표시자 투명도(0.42)를 그대로 두면 같은 뜻이 한 줄 안에서 두 무게로 서고,
             사용자는 그 차이를 «이 칸만 비어 있다» 로 읽는다. 값을 **입력 글자로** 넣지 않는
             이유는 그대로다(타이핑이 그 글자 뒤에 덧붙는다) — 무게만 맞춘다. */
          sx={{
            ...(row ? null : LABEL_ABOVE_SX),
            "& .MuiInputBase-input::placeholder": { opacity: 1, color: "text.primary" },
            "& .MuiInputBase-input:focus::placeholder": { opacity: 1, color: "text.primary" },
            "& .MuiInputBase-input::-webkit-input-placeholder": { opacity: 1, color: "text.primary" },
            "& .MuiInputBase-input:focus::-webkit-input-placeholder": { opacity: 1, color: "text.primary" },
          }}
          /* 잘려도 전체 값을 알 수 있어야 한다 (C2 «선택된 값 식별성»). */
          /* 라벨을 부품 밖(`FieldLabel`)이 그리는 자리에서는 이름을 **가리켜서** 잇는다 —
             `label` 을 안 넘기면 MUI 는 이름 없는 combobox 를 만들고, 그러면 스크린리더도
             시험도 그 컨트롤을 부를 수 없다. */
          inputProps={{
            ...params.inputProps,
            "aria-labelledby": ariaLabelledBy || params.inputProps["aria-labelledby"],
            "aria-label": (hideLabel && !ariaLabelledBy) || row ? label : params.inputProps["aria-label"],
            ...(ariaDescribedBy ? { "aria-describedby": ariaDescribedBy } : null),
            title: current ? current.label : undefined,
          }}
        />
        );
      }}
    />
  );
}

/* 부서 필터 (0060 §32) — **목록을 어느 팀 것으로 좁힐 것인가**.
 *
 * 후보는 서버가 준다(`departments.options`). 프런트가 스스로 조직도를 훑어 만들면 서버
 * 검증(`app/org/context.py`)과 갈라지고, 갈라진 쪽이 넓으면 사용자는 고를 수는 있는데
 * 404 만 보는 상자를 얻는다.
 *
 * 보여 주는 것은 이름이 아니라 **경로**다. '개발팀' 하나만 있으면 어느 줄기인지 알 수 없고,
 * 조직 개편으로 같은 이름이 다른 자리에 생기면 구분이 아예 불가능해진다.
 *
 * 고를 것이 하나뿐이면 아무것도 안 그린다 — 선택지가 하나인 선택기는 정보가 아니라 소음이고,
 * 화면만 좁힌다(부서가 하나인 조직, 팀 하나에만 속한 사람이 그렇다).
 */
/** 회차의 **팀** 선택기 (D-482) — 작업 보드와 스프린트 회의가 같은 부품을 쓴다.
 *
 * 부서 필터(`DepartmentFilter`)와 다른 물건이다. 그쪽은 「내 범위 전체」가 있는 **좁히기**
 * 이고, 이쪽은 **문맥**이다 — 회차는 팀의 것이라 「전체 팀의 회차」라는 목록이 없다. 그래서
 * 「전체」 항목이 없고 값이 비면 화면이 고르라고 말한다. 후보는 서버가 동봉한 것
 * (`team.options` — 회차를 볼 수 있는 팀)만이고, 화면이 스스로 조직도를 훑어 만들지 않는다.
 *
 * 후보가 하나뿐이면 아무것도 안 그린다 — 선택지가 하나인 선택기는 정보가 아니라 소음이다.
 * 그때도 문맥은 주소(`team`)에 있다.
 *
 * 칸은 wide 가 기본이다 — 이름이 「플랫폼본부 › 플랫폼개발팀」 같은 경로라 값이 긴 축이다(`ROW_KIND.entityWide`). */
export function TeamSelect({ team, value, onChange, label = "팀", sx, loading, size = "wide" }) {
  const options = (team && team.options) || [];
  /* 줄 칸에는 이름(「팀」)이 칸 안 접두로 이미 선다 — 빈 글자는 회차 칸과 같은 「고르세요」다. 폼 자리는
     이름이 칸 위라 빈 글자가 스스로 무엇을 고르는지 말한다(「팀을 고르세요」). */
  const row = useRowCell();
  if (options.length < 2) return null;
  return (
    <EntityCombobox
      label={label}
      value={value || ""}
      onChange={(next) => onChange(next || "")}
      loading={loading}
      noAllOption
      allLabel={row ? "고르세요" : "팀을 고르세요"}
      sx={sx}
      size={size}
      options={options.map((o) => ({
        value: o.id,
        label: (o.path || []).map((n) => n.name).join(" › ") || o.name,
      }))}
    />
  );
}

export function DepartmentFilter({ departments, value, onChange, label = "부서", sx, size = "wide" }) {
  const options = (departments && departments.options) || [];
  if (options.length < 2) return null;
  /* 부서는 **Entity** 다 — 조직이 자라면 후보도 자란다. 그리고 이 축의 라벨은 경로라서
     제품에서 가장 긴 값 축에 속한다("브로드컴사업본부 › ClovirONE팀"). 닫힌 열거형용
     `FilterSelect` 로 그리면 그 경로가 255px 트랙 안에서 잘리고, 잘린 뒤에는 같은 본부의
     팀들이 서로 구분되지 않는다. 이름은 **보조 식별자**로 함께 낸다 — 조직 개편으로 같은
     이름이 다른 자리에 생기면 경로만이 둘을 가른다. 같은 이유로 칸은 wide 가 기본이다(`ROW_KIND.entityWide`). */
  return (
    <EntityCombobox
      label={label}
      value={value || ""}
      onChange={onChange}
      allLabel="내 범위 전체"
      sx={sx}
      size={size}
      options={options.map((o) => ({
        value: o.id,
        label: (o.path || []).map((n) => n.name).join(" › ") || o.name,
      }))}
    />
  );
}
