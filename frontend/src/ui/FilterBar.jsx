import React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Button } from "./kit.jsx";
import { FILTER_SURFACE_CONTAINER, FilterRowContext } from "./filters.jsx";
import { BREAKPOINTS, CONTROL, FONT_SIZE, FONT_WEIGHT, RADIUS, remPx } from "./theme.js";
import { hasFinalConsonant } from "../lib/format.js";

/* 탐색 줄 — 목록 화면의 «어떻게 볼지»(도구)와 «무엇을 볼지»(필터)를 담는 자리.
 *
 * ## W5 가 바꾼 것 하나: **이 자리는 판이 아니다**
 *
 * 예전에는 소비처 전부가 `<Card className="c-toolbar-card" sx={{ p: 2, mb: 2.5 }}>` 로
 * 컨트롤을 감쌌다(`TicketFilterBar`·`DataScreen`·`Board`·`TeamDocs`·`Users` 다섯 곳,
 * 손으로 복사된 같은 줄). 그 판은 지시 80 이 문장으로 금지한 바로 그것이다 —
 * «Control 은 화면 좌측 일부만 쓰는데 Container 는 Page 전체 폭을 차지하여 오른쪽 대부분이
 * 비어 있는 구조». 실측으로도 그랬다: `/policies` 의 필터 판은 1610×108px 인데 컨트롤은
 * 왼쪽 790px 만 쓴다(잉크 폭 비 0.43).
 *
 * 필터는 «자기 생명주기를 가진 경계 객체»가 아니다 — 저장·취소도, 독립 error/empty 도,
 * 독립 스크롤도 없다. PLAN «구획별 판정 체크리스트» 를 그대로 태우면 ⑥ **컨테이너 없음**
 * 이다. 그래서 이 부품은 캔버스 위에 놓이고, 목록과의 경계는 판이 아니라 **결과 줄과
 * 아래 실선**이 만든다.
 *
 * ## 그리고 그 판이 검사도 막고 있었다
 *
 * 옛 격자는 `width: "fit-content"` 였다. 그 한 줄이 격자 상자를 «가장 넓은 줄» 폭으로
 * 줄이므로, `isolated_control_row` 가 재는 «윗줄 여유(prevFree)» 가 구조적으로 **항상 0**
 * 이 된다. 664 페이지에서 이 검사의 fail 이 0 이었던 이유가 그것이다 — 위반이 없어서가
 * 아니라 **잴 수 없어서**다. R-76 이 이름으로 지목한 두 화면(`/board` 정렬 select,
 * `/sprint` 담당자)이 둘 다 «검사됨» 상태로 기각되고 있었다.
 *
 * 이제 줄은 폭 전체를 차지하고 컨트롤이 자기 종류만큼만 차지한다(`filters.jsx::CONTROL_KIND`).
 * 남는 폭은 실제로 남는 폭이고, 프로브가 그것을 잰다.
 */

/* ── 필터 축의 그룹 순서 (C2 «그룹 순서 고정») ──────────────────────────────
 *
 * 순서는 취향이 아니라 **좁히는 순서**다: 먼저 범위를 정하고(scope), 그 안에서 사람이나
 * 대상을 고르고(entity), 그 다음 분류·상태·기간으로 조인다. 예전에는 이 순서가
 * registry 28곳과 화면 파일 여섯 곳에 흩어져 있어서, 같은 축이 화면마다 다른 자리에 섰다.
 */
export const FILTER_GROUP_ORDER = ["scope", "entity", "category", "status", "period", "other"];

const GROUP_BY_KEY = [
  [/dept|department|org|scope/i, "scope"],
  [/user|assignee|actor|owner|requester|target|project|schedule|workflow|template|document|generation|member|successor/i, "entity"],
  [/category|type|kind|tag|field|mode|level|difficulty/i, "category"],
  [/status|state|result|enabled|active|unread|ok|approval/i, "status"],
  [/since|until|from|to|date|period|window|due/i, "period"],
];

/** 필터 정의 하나가 어느 그룹인가. 선언이 `group` 을 주면 그것이 이긴다. */
export function filterGroupOf(f) {
  if (!f) return "other";
  if (f.group && FILTER_GROUP_ORDER.includes(f.group)) return f.group;
  if (f.kind === "entity") return "entity";
  const key = String(f.key || "");
  for (const [re, group] of GROUP_BY_KEY) if (re.test(key)) return group;
  return "other";
}

/* ── Entity 칸의 크기 — 값이 긴 축은 `wide` 다 (`filters.jsx::ROW_KIND.entityWide`) ─────────────
 *
 * 프로젝트 · 부서 · 팀 · 문서 공간 · 회차 · 일정은 값이 길다(경로이거나 긴 이름이다). 사람 · 이름 축은 짧다. registry 선언이
 * `size` 를 주면 그것이 이기고, 안 주면 키 이름이 정한다 — 그룹 순서(`filterGroupOf`)와 같은 방식이다. */
const WIDE_ENTITY_KEY = /project|dept|department|team|space|sprint|schedule/i;

/** 필터 정의 하나의 Entity 칸 크기(`"wide"` · `"default"`). `EntityCombobox size` 로 넘긴다. */
export function entitySizeOf(f) {
  if (!f) return "default";
  if (f.size === "wide" || f.size === "default") return f.size;
  return WIDE_ENTITY_KEY.test(String(f.key || "")) ? "wide" : "default";
}

/** 탐색 줄 전체를 감싸는 자리. **판이 아니다** — 캔버스 위에 놓이고 아래로 목록과 갈린다. */
export function FilterSurface({ children, divider = true, sx, ...rest }) {
  return (
    <Box
      data-filter-surface=""
      sx={{
        display: "grid",
        gap: 1.5,
        mb: 2,
        /* 이 면이 줄 칸 크기의 기준이다 — wide Entity 칸이 면의 폭을 보고 계단을 고른다(`filters.jsx::ROW_KIND.entityWide`).
           크기 격리(`inline-size`)는 면의 폭을 내용과 떼어 놓는다. 면은 언제나 부모 폭을 다 쓰는 블록이라 그 격리가 면의 폭을
           바꾸지 않는다(목록 화면 · 탭 판 · 서랍 · 대화상자 모두 그렇다). 내용 폭으로 줄어드는 자리(`fit-content`, 가로 flex 의
           `0 0 auto` 칸)에 면을 두면 폭이 0 이 되므로 그런 자리에는 두지 않는다. */
        ...FILTER_SURFACE_CONTAINER,
        ...(divider ? { pb: 2, borderBottom: 1, borderColor: "divider" } : null),
        ...sx,
      }}
      {...rest}
    >
      {/* 이 안의 필터 칸은 줄 모양(34 · 칸 안 이름)이다 — `filters.jsx::FilterRowContext`. */}
      <FilterRowContext.Provider value>{children}</FilterRowContext.Provider>
    </Box>
  );
}

/* ── 검색 슬롯 — desktop 에서 **320 고정**, 남는 폭을 먹지 않는다 (핸드오프 D-5 · README §3) ──
 *
 * 폭은 `SearchBox` 가 아니라 **필터 바의 줄**이 정한다. 같은 검색창이 좁은 판 · 모달 · 채팅 목록
 * (296)에 서면 그 부모 폭을 그대로 써야 하고(`layout="fill"`), 320 을 부품에 박으면 그 자리마다
 * 넘친다. 그래서 줄 부품 둘(`ToolbarRow` · `FilterRow`)이 자기 **직계** 검색 칸에만 슬롯을 준다.
 * `sm` 미만에서는 한 줄을 다 쓴다. `max-width: 100%` 는 줄이 320 보다 좁아지는 드문 경우의 안전선이다. */
function searchSlotSx() {
  /* 🔴 MUI 는 sx 안의 미디어 규칙을 **평범한 규칙보다 앞에** 싣는다(실측: 생성된 CSS 순서). 같은
     특이도면 뒤의 것이 이기므로, 좁은 화면 규칙은 선택자를 한 단 더 세게(`&&`) 적는다. */
  return {
    "& > [data-filter-kind=search]": { flex: "0 0 20rem", width: "20rem", maxWidth: "100%", minWidth: 0 },
    [`@media (max-width:${BREAKPOINTS.sm - 0.05}px)`]: {
      "&& > [data-filter-kind=search]": { flex: "1 1 100%", width: "100%" },
    },
  };
}

/* 도구 줄 — 필터 줄 **위**에 놓는 한 줄이다 (지시 5).
 *
 * 왜 갈라 놓나: 목록 화면의 컨트롤은 두 종류다. "무엇을 볼지"(검색·필터)와 "어떻게
 * 볼지"(정렬·카드/표). 예전 문서 목록은 여덟 개를 한 격자에 같은 폭으로 깔고 보기 전환만
 * 그 아래 오른쪽에 따로 뒀다 — 결과가 세 줄이었고, 정렬이 필터 하나처럼 읽혔다.
 *
 * 이 줄은 **검색이 지배**하고(늘어난다), 오른쪽 끝에 "어떻게 볼지"가 붙는다. 내용 필터는
 * 아래 `FilterRow` 로 내려간다. 두 줄이면 충분하고, 각 줄이 한 가지 질문만 답한다.
 */
export function ToolbarRow({ children, sx }) {
  return (
    <Box data-search-slot="" sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", ...searchSlotSx(), ...sx }}>
      {children}
    </Box>
  );
}

/** 도구 줄의 오른쪽 묶음("어떻게 볼지"). 남는 폭을 밀어내 항상 끝에 붙는다. */
export function ToolbarEnd({ children, sx }) {
  return (
    <Box
      /* 이 묶음은 **의도적으로** 오른쪽 끝에 선다 — 밀려난 것이 아니다.
         예외 표식은 쓰지 않는다: 표식은 억제 대장에 행을
         요구하고, 공유 부품에 박은 표식은 그 대장을 «영구 예외» 목록으로 만든다. 대신
         `isolated_control_row` 가 **기하로** 가른다 — 고아는 왼쪽에 남고 이것은 오른쪽 끝에
         선다(지시 76 의 문장 그대로). */
      /* **한 덩어리로 줄바꿈한다** (핸드오프 §0-4). 폭이 모자라면 버튼 하나를 줄이거나 떨어뜨리지
         않고 묶음째 다음 줄로 내려간다 — `nowrap` 은 묶음 안, `flex: 0 0 auto` 는 묶음 자신이
         줄어들지 않게 한다. 버튼의 라벨이 잘리는 것보다 줄이 하나 느는 편이 낫다. */
      sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "nowrap", flex: "0 0 auto", marginInlineStart: "auto", ...sx }}
    >
      {children}
    </Box>
  );
}

/* 내용 필터 줄 — «무엇을 볼지».
 *
 * 격자가 아니라 **흐름**이다. 폭은 각 컨트롤이 자기 종류에서 가져온다
 * (`filters.jsx::CONTROL_KIND`). 그래서 「상태」는 내용만큼만 차지하고 「프로젝트」는
 * 넉넉히 가져가며, 값이 길다고 잘리지 않는다.
 *
 * `alignItems: center` — 이 줄의 컨트롤은 전부 MUI 노치 라벨(테두리에 얹힌 라벨)이라
 * 상자 높이가 같고, 텍스트 버튼처럼 높이가 다른 것은 중심으로 맞춘다.
 */
export function FilterRow({ children, sx, ...rest }) {
  return (
    <Box
      data-filter-row=""
      data-search-slot=""
      /* 🔴 세로 정렬은 **위**다(가운데가 아니다). 이 줄의 컨트롤은 전부 같은 높이(36px)인데,
         그중 하나가 `helperText` 를 달면 그 상자만 20px 더 커진다. 가운데 정렬이면 그
         차이의 절반만큼 **입력칸 자체가 서로 어긋난다** — 회의 화면의 「프로젝트」와
         「스프린트」가 11.4px 어긋나 있었고(QA `control_baseline_mismatch`), 사용자에게는
         두 상자가 층이 진 것으로 보였다. 위로 맞추면 입력칸의 윗변이 한 줄로 서고 설명은
         그 아래에 매달린다. */
      sx={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 1.5, width: "100%", ...searchSlotSx(), ...sx }}
      {...rest}
    >
      {children}
    </Box>
  );
}

/* 필터 줄 끝의 동작 묶음 — «필터 지우기»·«저장된 뷰».
 *
 * **격자 칸이 아니다.** 예전에는 `필터 지우기` 가 필터와 같은 트랙에 들어가 테두리 있는
 * 255px 상자가 됐고, 그것이 **지우려는 필터(255px)와 같은 폭**이었다(`/policies` 실측).
 * 지시 76·80 이 그 상태를 이름으로 지적한다. 되돌리는 일은 조건이 아니라 **동작**이므로
 * 흐름의 끝에 텍스트로 붙는다.
 */
export function FilterActions({ children, sx }) {
  return (
    <Box
      data-filter-actions=""
      /* 줄이 위로 맞춰졌으므로(FilterRow) 이 묶음은 **자기 안에서** 입력칸 높이만큼의
         띠를 만들고 그 가운데에 선다 — 그래야 설명이 달린 줄에서도 단추가 입력칸과
         같은 눈높이에 있다. 띠 높이는 필터 칸과 같은 rem 34 다 — 예전의 px 36 은 칸보다 2px 높았고
         루트 글자 18 · 20px(2560 · 3840)에서는 rem 칸보다 낮아져 단추가 칸 가운데에서 비켜 섰다. */
      sx={{
        display: "flex", alignItems: "center", gap: 1, marginInlineStart: "auto",
        alignSelf: "flex-start", minHeight: remPx(CONTROL.button), ...sx,
      }}
    >
      {children}
    </Box>
  );
}

/* 결과 줄 — «이 조건에 대한 결과가 몇 건인가».
 *
 * C2 가 요구하는 것은 숫자가 아니라 **관계**다: 건수를 필터 상자의 남는 자리에 아무 데나
 * 두면 그것은 그냥 숫자이고, 필터와 목록 **사이**에 두면 «위 조건 → 아래 결과» 라는 문장이
 * 된다. 예전에는 이 숫자가 제품 안 11곳에 제각각 있었고(같은 문자열의 사본 4벌), 페이지가
 * 하나뿐이면 Pager 와 함께 통째로 사라졌다 — «총 2건» 을 못 보는 화면이 생기는 이유였다.
 *
 * `aria-live="polite"` — 필터를 바꾸면 화면 어딘가의 숫자가 바뀐다는 사실을 눈으로만
 * 알 수 있으면 안 된다.
 */
/* `text` — 화면이 이미 쓰던 결과 문장(「총 N건 가운데 M건을 보여 줍니다.」 · 「총 N건, 짧은 검색어라
   부분 일치로 찾았습니다」)을 그대로 세운다(계획 P-21 — 문구를 통일하지 않는다). 문장을 준 화면은
   0건이어도 그 문장을 말한다 — 원래 그랬다. */
/* 조건과 결과를 **한 문장**으로 말한다 (계획 2.2).
 *
 * 예전 문구 「조건 2개, 결과 3건」은 쉼표로 이은 두 조각이라 "조건 2개" 가 무엇을 뜻하는지 읽는
 * 사람이 짐작해야 했다. 지금은 완전한 문장이다: 「조건 2개에 맞는 결과가 3건입니다.」 조건이 없으면
 * 「전체 12건입니다.」다. 셀 대상이 결과가 아니라 부서처럼 이름이 있으면 `noun` 으로 주고
 * 조사는 받침으로 고른다(「부서가」 · 「티켓이」). 단위는 `unit` 이다. */
export function filterSummaryText({ count, total, unit = "건", noun = "결과" }) {
  if (total == null) return "세는 중…";
  const amount = total.toLocaleString("ko-KR") + unit;
  if (!count) return `전체 ${amount}입니다.`;
  const particle = hasFinalConsonant(noun) ? "이" : "가";
  return `조건 ${count}개에 맞는 ${noun}${particle} ${amount}입니다.`;
}

export function ResultLine({ total, unit = "건", noun = "결과", conditions, action, text, sx }) {
  const has = Array.isArray(conditions) ? conditions.filter(Boolean) : [];
  /* 조건도 없고 결과도 0 이면 그리지 않는다 — 그 자리에는 이미 빈 상태가 «왜 비었는지» 를
     말하고 있고, 그 위에 「전체 0건」을 한 줄 더 얹으면 같은 사실이 두 번 나온다.
     반대로 **조건이 걸린 채 0건**이면 이 줄이 그 화면에서 가장 중요한 문장이다 —
     «데이터가 없다» 와 «조건 때문에 없다» 를 가르는 것이 그것이기 때문이다(C2). */
  if (!text && !has.length && (total === 0 || total == null)) return null;
  return (
    <Box
      data-result-line=""
      sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap", mb: 1.5, ...sx }}
    >
      <Typography variant="body2" color="text.secondary" aria-live="polite">
        {text || filterSummaryText({ count: has.length, total, unit, noun })}
      </Typography>
      {action}
    </Box>
  );
}

/* 조건 칩의 얼굴 — **알약이고 옅은 브랜드 면이다** (확정 규약 · 갤러리 대조 D-4).
 *
 * MUI `Chip` 기본은 중립 회색 필이다. 그 얼굴로는 이 줄의 칩이 바로 위 태그(`Tag`)와
 * 구분되지 않았고, 「지울 수 있는 조건」이라는 뜻이 모양에서 사라졌다 — 실제로 갤러리에
 * 나란히 세우고서야 보였다. 셋을 바꾼다: 모서리를 알약(`RADIUS.full`)으로, 면을 강조색에서
 * 유도한 옅은 면(`primary.light`)으로, 높이를 `CONTROL.chip` 26 으로.
 *
 * 면과 글자를 **강조색 파생**으로 두는 것이 중요하다. `primary.light` 는 강조색을 판면에
 * 10% 섞은 값이고 `primary.dark` 는 그 강조색의 진한 잉크다 — 사용자가 강조색을 바꾸면
 * 둘이 함께 따라간다. 고정 hex 를 쓰면 보라 이외의 강조색에서 칩만 보라로 남는다.
 *
 * 높이는 옆의 「필터 초기화」(30)와 **일부러 다르다.** 칩은 지금 걸린 조건을 말하는 표지이고 그 옆은
 * 누르는 단추다 — 한 높이로 세우면 셋이 한 종류로 읽힌다. 줄이 `align-items: center` 라 두 높이가 한 축에 선다. */
const CONDITION_CHIP_SX = {
  height: remPx(CONTROL.chip),
  /* `px` 를 붙인다 — MUI 의 `borderRadius` 시스템 prop 은 **맨 숫자에 `shape.borderRadius`
     를 곱한다.** `RADIUS.full`(999)을 그대로 주면 `7992px` 가 나간다. */
  borderRadius: `${RADIUS.full}px`,
  bgcolor: "primary.light",
  color: "primary.dark",
  border: 1,
  borderColor: "divider",
  fontSize: FONT_SIZE.caption,
  fontWeight: FONT_WEIGHT.semibold,
  maxWidth: "100%",
  "& .MuiChip-label": { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  "& .MuiChip-deleteIcon": {
    color: "inherit",
    opacity: 0.7,
    "&:hover": { color: "inherit", opacity: 1 },
  },
};

/* 조건 줄의 글자 단추(지우기 · 「전체 보기」) — 목록 안 부수 동작이라 ghost 30 이고 링크 잉크로 선다(RULES §3). */
const CONDITION_ACTION_SX = { color: "primary.dark" };

/* ── 조건 줄 — 필터 바의 **두 번째 줄** (핸드오프 README §3 · ACCEPTANCE D3 · UI 3차 조합 계약 C-1) ─────
 *
 * 조건 칩이 하나라도 있으면 필터 면 **안**, 컨트롤 줄 아래에 위 1px 실선을 긋고 한 줄로 선다:
 * 「조건 N개, 결과 M건」 → 조건 칩 → 지우기 → 덧붙는 글자 단추(「전체 보기」). 칩이 없으면 **그리지 않는다.**
 *
 * **N 은 칩 수다.** 예전에는 화면이 조건 수를 따로 세서 넘겼다 — 문서 · 게시판은 검색어를 조건으로 세면서
 * 칩은 안 그렸고(「조건 2개」 옆에 칩 하나), 태그 셋을 조건 하나로 셌다. 세는 것과 보이는 것이 한 목록이면
 * 둘이 갈라질 자리가 없다. 조건이 아닌데 칩이 필요한 것은 없다 — 모든 조건은 칩을 가진다.
 *
 * 결과 수의 자리는 여기와 목록 판 발 둘뿐이다. 목록 위 단독 「전체 N건」 줄은 걷었다 — 발의
 * 「N건 중 M건을 받았습니다.」가 같은 수를 말한다. */
export function FilterConditionLine({ total, unit = "건", noun = "결과", chips, onClearAll, clearLabel = "필터 초기화", extraAction }) {
  const list = Array.isArray(chips) ? chips.filter((c) => c && c.label) : [];
  if (!list.length) return null;
  return (
    <Box
      data-condition-line=""
      sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", columnGap: 1, rowGap: 1, pt: 1.5, borderTop: 1, borderColor: "rule" }}
    >
      <Typography
        data-condition-count=""
        variant="body2"
        color="text.secondary"
        aria-live="polite"
        sx={{ marginInlineEnd: 0.5, whiteSpace: "nowrap" }}
      >
        {filterSummaryText({ count: list.length, total, unit, noun })}
      </Typography>
      {list.map((chip) => (
        <Chip
          key={chip.key}
          data-condition-chip=""
          size="small"
          label={chip.label}
          onDelete={chip.onDelete}
          /* 긴 조건값은 한 칩 안에서 말줄임되고 전체 값은 `title` 이 든다(§0-3). */
          title={typeof chip.label === "string" ? chip.label : undefined}
          sx={CONDITION_CHIP_SX}
        />
      ))}
      {onClearAll ? (
        <Button data-filter-clear="" variant="ghost" size="sm" onClick={onClearAll} sx={CONDITION_ACTION_SX}>
          {clearLabel}
        </Button>
      ) : null}
      {extraAction ? (
        <Button variant="ghost" size="sm" onClick={extraAction.onClick} sx={CONDITION_ACTION_SX}>
          {extraAction.label}
        </Button>
      ) : null}
    </Box>
  );
}

/* ── 필터 바 — 목록 화면의 탐색 줄 **한 벌** (UI 3차 · 조합 계약 C-1) ─────────────────────────────
 *
 * 예전에는 이 파일이 낱개(`FilterSurface` · `ToolbarRow` · `FilterRow` · `ToolbarEnd` · `FilterActions` ·
 * `FilterChips` · `ResultLine` · `FilterConditionLine`)만 내보냈고 목록 화면 열여섯 곳이 제각각 조립했다.
 * 티켓 · 게시판은 칩 줄과 결과 줄을 면 **밖**에 두 줄로 세웠고, DataScreen · 사용자 · 프로젝트 · 조직은
 * 검색만 한 줄을 쓰고 필터를 다음 줄로 내렸고(1920 에서도 두 줄), 「필터 지우기」는 줄 끝 동작 묶음에서
 * 화면마다 다른 크기로 섰다. 부품은 전부 정본인데 조합이 화면마다 달랐다.
 *
 * 이 부품이 조합을 정한다: 한 줄 = 검색(20rem 슬롯) → 내용 필터 칸 → 빈 공간 → `end`(정렬 · 보기 · 켬/끔 ·
 * 저장된 뷰), 아래 1px 실선. 조건 칩이 하나라도 있으면 같은 면 안 둘째 줄이 조건 줄이다. 좁아지면 순서를
 * 지킨 채 줄바꿈하고 `end` 는 묶음째 내려간다. 화면은 칸과 칩만 넘긴다.
 *
 *   search      `SearchBox` 하나(없으면 생략)
 *   children    내용 필터 칸(순서는 `FILTER_GROUP_ORDER`)
 *   end         오른쪽 끝 묶음
 *   conditions  `{ chips, total, unit, noun, onClearAll, clearLabel, extraAction: { label, onClick } }`
 *   divider     아래 실선. 서랍 안 필터처럼 목록과 가를 선이 필요 없는 자리만 `false`
 *
 * 낱개 부품은 이 조합 안에서만 쓴다. 대장 예외(`docs/ui-renewal/COMPONENT_LEDGER.md` 「조합 예외」)만 낱개를
 * 직접 조립한다 — `scripts/check_composition.py` 가 그 표와 대조한다. */
export function FilterBar({ search, children, end, conditions, divider = true, flush = false, sx, ...rest }) {
  /* `flush` — 아래 간격을 걷는다. 그릇(흐름 · 판)이 간격을 주는 자리다(화면이 숫자 여백을 적지 않는다). */
  const merged = flush ? { mb: 0, ...sx } : sx;
  return (
    <FilterSurface divider={divider} sx={merged} data-filter-bar="" {...rest}>
      <FilterRow>
        {search || null}
        {children}
        {end ? <ToolbarEnd>{end}</ToolbarEnd> : null}
      </FilterRow>
      {conditions ? <FilterConditionLine {...conditions} /> : null}
    </FilterSurface>
  );
}

/* ── 필터 토글 — 「내 티켓만」 · 「상세 필터」 (핸드오프 README §3 · RULES §3) ───────────────
 *
 * 필터 바에서 켜고 끄는 것은 **스위치가 아니라 34px 중립 버튼**이고, 켜져 있을 때만 눌린 면
 * (함몰면 + strong 테두리)이다. 스위치는 「누르는 즉시 저장되는 설정」의 어휘라, 필터 줄에 서면
 * 조건이 아니라 설정처럼 읽힌다.
 *
 * 둘 중 하나를 말한다:
 *   `pressed`   목록을 좁히는 켜짐/꺼짐 — `aria-pressed`
 *   `expanded`  패널을 여닫는 것(상세 필터) — `aria-expanded`
 * 라벨은 화면이 주는 낱말 그대로다(문구를 바꾸지 않는다). */
export const FilterToggle = React.forwardRef(function FilterToggle(
  { pressed, expanded, onClick, disabled, children, sx, ...rest }, ref,
) {
  const panel = expanded !== undefined;
  const on = panel ? !!expanded : !!pressed;
  return (
    <Button
      ref={ref}
      variant="default"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={panel ? undefined : on}
      aria-expanded={panel ? on : undefined}
      data-filter-toggle={panel ? "panel" : "toggle"}
      sx={(t) => ({
        ...(on ? { bgcolor: "background.inset", borderColor: t.palette.dividerStrong, "&:hover": { bgcolor: "background.inset", borderColor: t.palette.text.secondary } } : null),
        ...(typeof sx === "function" ? sx(t) : sx),
      })}
      {...rest}
    >
      {children}
    </Button>
  );
});
