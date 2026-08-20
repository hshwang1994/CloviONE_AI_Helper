import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

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
      sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1.5, width: "100%", ...sx }}
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
      sx={{ display: "flex", alignItems: "center", gap: 1, marginInlineStart: "auto", ...sx }}
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
