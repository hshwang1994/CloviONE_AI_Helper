import React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, RADIUS, remPx } from "./theme.js";

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

/** 탐색 줄 전체를 감싸는 자리. **판이 아니다** — 캔버스 위에 놓이고 아래로 목록과 갈린다. */
export function FilterSurface({ children, divider = true, sx, ...rest }) {
  return (
    <Box
      data-filter-surface=""
      sx={{
        display: "grid",
        gap: 1.5,
        mb: 2,
        ...(divider ? { pb: 2, borderBottom: 1, borderColor: "divider" } : null),
        ...sx,
      }}
      {...rest}
    >
      {children}
    </Box>
  );
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
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", ...sx }}>
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
      sx={{ display: "flex", alignItems: "center", gap: 1, marginInlineStart: "auto", ...sx }}
    >
      {children}
    </Box>
  );
}

/** 도구 줄 안의 검색창 폭 — 늘어나되 한없이 늘지는 않는다(긴 입력은 읽기 어렵다). */
export const TOOLBAR_SEARCH_SX = { flex: "1 1 20rem", maxWidth: "32rem" };

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
      /* 🔴 세로 정렬은 **위**다(가운데가 아니다). 이 줄의 컨트롤은 전부 같은 높이(36px)인데,
         그중 하나가 `helperText` 를 달면 그 상자만 20px 더 커진다. 가운데 정렬이면 그
         차이의 절반만큼 **입력칸 자체가 서로 어긋난다** — 회의 화면의 「프로젝트」와
         「스프린트」가 11.4px 어긋나 있었고(QA `control_baseline_mismatch`), 사용자에게는
         두 상자가 층이 진 것으로 보였다. 위로 맞추면 입력칸의 윗변이 한 줄로 서고 설명은
         그 아래에 매달린다. */
      sx={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 1.5, width: "100%", ...sx }}
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
         같은 눈높이에 있다. */
      sx={{
        display: "flex", alignItems: "center", gap: 1, marginInlineStart: "auto",
        alignSelf: "flex-start", minHeight: `${CONTROL.input}px`, ...sx,
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
export function ResultLine({ total, unit = "건", conditions, action, sx }) {
  const has = Array.isArray(conditions) ? conditions.filter(Boolean) : [];
  /* 조건도 없고 결과도 0 이면 그리지 않는다 — 그 자리에는 이미 빈 상태가 «왜 비었는지» 를
     말하고 있고, 그 위에 「전체 0건」을 한 줄 더 얹으면 같은 사실이 두 번 나온다.
     반대로 **조건이 걸린 채 0건**이면 이 줄이 그 화면에서 가장 중요한 문장이다 —
     «데이터가 없다» 와 «조건 때문에 없다» 를 가르는 것이 그것이기 때문이다(C2). */
  if (!has.length && (total === 0 || total == null)) return null;
  return (
    <Box
      data-result-line=""
      sx={{ display: "flex", alignItems: "baseline", gap: 1.5, flexWrap: "wrap", mb: 1.5, ...sx }}
    >
      <Typography variant="body2" color="text.secondary" aria-live="polite">
        {total == null
          ? "세는 중…"
          : has.length
            ? `조건 ${has.length}개, 결과 ${total.toLocaleString("ko-KR")}${unit}`
            : `전체 ${total.toLocaleString("ko-KR")}${unit}`}
      </Typography>
      {action}
    </Box>
  );
}

/* 지금 걸린 조건을 Chip 으로 보여 주고 하나씩 뗄 수 있게 한다.
 * 숨은 기본 조건은 여기에 안 넣는다 — 넣은 것만 사용자가 본 조건이다. */
/* 🔴 조건 줄의 **모든 조작기가 한 높이로 선다** (S22 · `control_baseline_mismatch`).
 *
 * 이 줄에는 세 종류가 섞인다: 조건 칩(`Chip size="small"`) · 「필터 초기화」 · 화면이
 * 넘기는 `extraAction`(「전체 보기」 같은 글자 단추). 칩은 토큰 높이로 서는데 글자 단추는
 * 자기 줄 높이라, 4K 레버가 루트 폰트사이즈를 올리면 둘이 갈렸다 — `/my-tickets` 3840 에서
 * 다섯 컨트롤이 5.5px 어긋났다. 좁은 화면에서는 우연히 같아서 아무도 못 봤다.
 *
 * 줄이 자기 높이를 주는 것만으로는 모자란다 — 프로브가 재는 것은 **버튼 요소 자신**이라
 * 감싼 상자의 높이는 그 판정에 안 들어간다(실측으로 확인했다). 그래서 이 값을 내보내
 * `extraAction` 을 만드는 화면이 **그 버튼에 직접** 얹게 한다. */
export const CHIP_ROW_CONTROL = {
  display: "inline-flex", alignItems: "center", minHeight: remPx(CONTROL.buttonSm),
};

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
 * 높이는 옆의 「필터 초기화」(30, `CHIP_ROW_CONTROL`)와 **일부러 다르다.** 칩은 지금 걸린
 * 조건을 말하는 표지이고 그 옆은 누르는 단추다 — 한 높이로 세우면 셋이 한 종류로 읽힌다.
 * 줄이 `align-items: center` 라 두 높이가 한 축에 선다. */
const CONDITION_CHIP_SX = {
  height: remPx(CONTROL.chip),
  /* `px` 를 붙인다 — MUI 의 `borderRadius` 시스템 prop 은 **맨 숫자에 `shape.borderRadius`
     를 곱한다.** `RADIUS.full`(999)을 그대로 주면 `7992px` 가 나간다. 브라우저가 알아서
     높이의 절반으로 잘라 주니 화면은 맞지만, 선언된 값이 계약과 달라진다. */
  borderRadius: `${RADIUS.full}px`,
  bgcolor: "primary.light",
  color: "primary.dark",
  border: 1,
  borderColor: "divider",
  fontSize: FONT_SIZE.caption,
  fontWeight: FONT_WEIGHT.semibold,
  "& .MuiChip-deleteIcon": {
    color: "inherit",
    opacity: 0.7,
    "&:hover": { color: "inherit", opacity: 1 },
  },
};

export function FilterChips({ items, onClearAll, clearLabel = "필터 초기화", extraAction }) {
  const chips = Array.isArray(items) ? items.filter((c) => c && c.label) : [];
  if (!chips.length && !extraAction) return null;
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 1.5 }}>
      {chips.map((chip) => (
        <Chip
          key={chip.key}
          size="small"
          label={chip.label}
          onDelete={chip.onDelete}
          sx={CONDITION_CHIP_SX}
        />
      ))}
      {onClearAll ? (
        <Typography
          component="button"
          type="button"
          variant="body2"
          onClick={onClearAll}
          sx={{
            border: 0, background: "none", cursor: "pointer", color: "primary.main", font: "inherit",
            ...CHIP_ROW_CONTROL,
            "&:focus-visible": (t) => ({ outline: `2px solid ${t.palette.focusRing}`, outlineOffset: 2 }),
          }}
        >
          {clearLabel}
        </Typography>
      ) : null}
      {extraAction ? <Box sx={CHIP_ROW_CONTROL}>{extraAction}</Box> : null}
    </Box>
  );
}
