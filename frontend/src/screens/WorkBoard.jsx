import React from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListFooter } from "../ui/InfiniteScroll.jsx";
import { useSearchParams, Link as RouterLink } from "react-router-dom";
import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  FormModal,
  OverflowMenu,
  PageHeader,
  Skeleton,
  useToast,
  FlatBadgeSurface,
  Segmented,
} from "../ui/kit.jsx";
import { FilterToggle } from "../ui/FilterBar.jsx";
import { ContextBar } from "../ui/ContextBar.jsx";
import { GridHeaderCell } from "../ui/GridHeaderCell.jsx";
import { DragBoard, DragItem, DragItemActions, SortableList } from "../ui/DragDrop.jsx";
import { EntityCombobox, TeamSelect } from "../ui/filters.jsx";
import { SprintLifecycle, sprintStateLabel, useCanPlanSprint } from "./SprintLifecycle.jsx";
import { useListMemory } from "../lib/listReturn.js";
import { priorityKind, priorityKo } from "../lib/priority.js";
import { CONTROL, KO_WORD_BREAK, remPx } from "../ui/theme.js";
import { invalidateTicketViews } from "./ticket-views.js";
import { sprintFields, teamLabelOf } from "./sprint-fields.js";
import { TicketEditModal } from "./MyTickets.jsx";
import { TicketPeek, useTicketPeek } from "./TicketPeek.jsx";
import { eligibleProjects, useAssigneeOptions, useTicketMeta, useTicketProjects } from "./ticket-options.js";
import {
  TicketFilterBar, applyColumnFilter, asList, clearTicketFilters, columnFilterValue, hasTicketFilter,
  nextTicketSort, ticketAssigneeOptions, ticketFilterSpec, ticketQueryParams, ticketSortOf,
} from "./TicketFilterBar.jsx";
import { useTicketSignals } from "../lib/ticketSignals.js";
import { TicketSignals } from "../ui/TicketSignals.jsx";
import { TicketFace, TicketPeople } from "../ui/TicketFace.jsx";
import { LANE_SURFACE } from "../ui/density.js";
import { useQueryState } from "../lib/useQueryState.js";
import { useGuardedMutation } from "../lib/useGuardedMutation.js";
import { celebrateIfCompletedCategory } from "../ui/celebrate.js";
import { pickOpenSprint } from "./sprint-charts.js";

/* 작업 보드 — 칸반과 백로그 (S6 · 지시 5 · REAUDIT §8 · D-482 · D-483 · D-484 · D-497).
 *
 * ## 이 화면은 **회차를 구성하고 실제 업무를 관리하는 곳**이다
 *
 * 문맥은 셋이고 순서가 있다: **팀 → 회차 → 프로젝트**. 회차는 팀의 것이라(D-482) 팀을
 * 먼저 고르고, 그 팀의 회차 목록에서 하나를 고르고, 프로젝트는 그 회차 안의 티켓을 좁히는
 * **필터**일 뿐이다 — 프로젝트를 바꿔도 팀과 회차와 회차 목록은 그대로다. 팀을 바꾸면
 * 회차와 프로젝트는 비워지고 그 팀의 열린 회차가 다시 자동으로 선다.
 *
 * 회차에 담고 빼는 일(편성)은 이 화면에서만 한다. 스프린트 회의는 구성된 회차를 리뷰하고
 * 결정하는 곳이다(D-484) — 두 화면이 같은 편성을 서로 다른 규칙으로 하지 않는다.
 *
 * ## 위는 두 줄이다 — 문맥 · 보기 줄과 데이터 필터 줄 (D-497)
 *
 * 팀 · 회차는 「어느 판을 보는가」이고, 칸반|백로그 · 「내 티켓만」 · 「보류 펴기」 · 「완료와 취소 보기」는 「그 판을
 * 어떻게 그리는가」다. 둘 다 목록을 좁히는 조건이 아니라서 문맥 줄(`ui/ContextBar.jsx`)에 선다. 검색 · 프로젝트 · 담당자 ·
 * 우선순위 · 난이도 · 신호는 티켓 목록 셋과 **같은 필터 바**(`TicketFilterBar`) 한 줄이다 — 조건 칩 · 결과 수 · 「필터
 * 지우기」 · 여러 값 고르기가 다른 목록과 같다. 「필터 지우기」는 필터 바의 조건만 걷고 문맥 줄은 건드리지 않는다.
 *
 * 예전에는 이 넷과 여섯이 두 줄에 섞여 있었다(D-484 ②). 「내 티켓만」이 조건처럼 첫 줄 끝에 서서 「필터 초기화」가 그것을
 * 지웠고, 1920 에서도 필터가 두 줄이었다. 보기 옵션 묶음은 「내 티켓만」이 맨 앞이다 — 보류 · 완료와 취소는 칸반에만
 * 뜻이 있어 백로그 탭에서 빠지는데, 앞에 선 「내 티켓만」은 탭을 바꿔도 제자리다.
 *
 * ## 티켓 하나를 확인해도 화면을 잃지 않는다 (D-483)
 *
 * 카드를 누르면 상세로 가지 않고 **미리보기**(`TicketPeek`)가 이 화면 위에 열린다. 팀·회차·
 * 필터·탭·열의 스크롤이 전부 제자리다. 상세로 가는 것은 「티켓 상세 보기」 한 곳이고, 그
 * 상세의 「목록」과 뒤로가기는 미리보기 없는 이 화면으로 돌아온다.
 *
 * ## 두 화면이 아니라 두 탭인 이유
 *
 * 같은 티켓을 다른 질문으로 본다. 칸반은 "지금 무엇이 어디까지 왔는가", 백로그는 "다음에
 * 무엇을 하는가" 다. 화면을 나누면 카드를 옮긴 뒤 다른 주소로 이동해 순서를 정하게 되고,
 * 그 사이에 사람은 자기가 방금 무엇을 옮겼는지 잊는다.
 *
 * ## 백로그는 상태가 아니라 자리다 (D-349)
 *
 * 「백로그」라는 진행 상태는 없다. 이 팀 프로젝트의 티켓 중 어느 회차에도 안 담긴 것이
 * 백로그다 — `sprint_id IS NULL` 한 줄이 그 정의이고, 편입은 상태를 손으로 바꾸는 것이
 * 아니라 「회차에 담기」라는 **명시적 동작**이다. 백로그에 보이는 티켓은 전부 이 팀 회차에
 * 담을 수 있고, 담을 수 없는 티켓(다른 팀·조직 공통)은 백로그에 없다 — 서버가 같은 정의로
 * 거른다(`app/work/service.py::_team_projects_clause`).
 *
 * ## 신호는 카드를 옮기지 않는다
 *
 * 차단·지연·이슈는 진행 상태와 **직교하는 축**이다. 차단된 진행 중 티켓은 진행 중 열에
 * 그대로 서고 카드가 표식을 단다.
 *
 * ## 낙관적 갱신을 하지 않는다
 *
 * 카드를 먼저 옮겨 두면 화면은 빨라 보이지만, 서버가 409(다른 사람이 먼저 옮김)로 거절할 때
 * 되돌려야 한다. 그 되돌림이 반쯤 되면 사용자는 자기 화면이 진실인지 알 수 없게 된다.
 * 그래서 서버가 답한 뒤 목록을 다시 읽는다. 카드마다 `version` 을 싣고 이동할 때 그대로
 * 돌려보낸다.
 *
 * ## 범위(scope)와 쪽(page) — REAUDIT §8
 *
 * 회차 미선택 기본은 **실행 중인 업무만**(`execution`)이다. 진입 시 그 팀의 열린 회차가
 * 있으면 자동으로 고른다. 열·백로그는 서버가 **커서**로 쪽을 낸다. */

const TAB_BOARD = "board";
const TAB_BACKLOG = "backlog";

/** 데이터 조건 — 필터 바(`TicketFilterBar`)의 칸이다. 판 · 열 · 백로그와 「맨 위로/맨 아래로」의 위치 계산이 같은 축으로
 *  받는다. 프로젝트 · 담당자 · 우선순위 · 난이도는 여러 값이다(티켓 목록과 같다). */
export const BOARD_FIELDS = ["q", "project_id", "assignee_user_id", "priority", "difficulty", "signal"];

/** 백로그의 기본 순서 — 끌어 옮긴 순서(`backlog_rank`)다. 머리에서 다른 정렬을 고르면 서버 정렬로 보고, 이 값으로
 *  돌아와야 다시 끌 수 있다. */
export const BACKLOG_SORT_DEFAULT = { sort: "rank", order: "asc" };

/* 백로그 정렬의 서버 허용표(`GET /api/work/backlog?sort=`)와 같은 목록이다. 주소에 다른 값이 오면 기본 순서로 읽는다 —
   서버가 422 로 거절할 값을 싣지 않는다. */
const BACKLOG_SORT_KEYS = ["rank", "tid", "priority", "difficulty", "est_wd", "due_date"];

/* 🔴 **조건은 전부 주소에 있다.** 팀·회차·탭·데이터 조건·백로그 정렬·보기 옵션 셋·미리보기. 새로고침·뒤로가기·링크
 * 공유에서 어느 것도 풀리지 않는다. 조건의 모양은 티켓 목록과 같다(`ticketFilterSpec` — 여러 값 축은 배열이다). */
const BOARD_SPEC = ticketFilterSpec(BOARD_FIELDS, {
  tab: TAB_BOARD,
  team: "",
  sprint: "",
  // 보기 옵션 — 조건이 아니다. 칩이 없고 「필터 지우기」가 건드리지 않는다(팀 티켓의 「완료, 취소 포함」과 같은 취급).
  mine: false,
  hold: false,
  all: false,
  // 열린 미리보기의 티켓(page_id). 목록의 기억(`useListMemory`)에서는 뺀다.
  peek: "",
  // 백로그 머리 「예상」 필터의 범위. 판 · 열도 같은 범위로 좁힌다.
  est_wd_min: "",
  est_wd_max: "",
  ...BACKLOG_SORT_DEFAULT,
});

/** 「필터 지우기」가 비우는 키 — 데이터 조건뿐이다. 팀·회차·탭·보기 옵션·미리보기는 문맥이라 여기 없다. */
export const BOARD_FILTER_KEYS = [...BOARD_FIELDS, "est_wd_min", "est_wd_max"];

/* 「내 티켓만」이 켜져 있으면 담당자 조건은 쓰지 않는다 — 서버도 `mine` 이 담당자 조건을 덮는다. 칸은 꺼진 채 이 문장을
   들고, 담당자 칩은 서지 않는다. */
const MINE_OFF = { assignee_user_id: "「내 티켓만」이 켜져 있는 동안에는 담당자 조건을 쓰지 않습니다." };

/* 옛 주소 키 — 조건이 여러 값이 되며 이름이 서버와 같아졌다(`project` → `project_id`, `assignee` → `assignee_user_id`).
   밖에서 들어오는 링크(스프린트 회의)는 팀 · 회차 · 탭만 싣지만, 목록의 기억과 즐겨찾기에는 옛 키가 남아 있다. */
const LEGACY_BOARD_KEYS = [["project", "project_id"], ["assignee", "assignee_user_id"]];

/** 옛 키를 새 키로 고쳐 쓴 질의 문자열. 고칠 것이 없으면 `null` 이다. 새 키가 이미 있으면 새 키가 이기고 옛 키는
 *  지운다. 다른 키의 자리와 값은 그대로다. */
export function rewriteLegacyBoardSearch(search) {
  const params = new URLSearchParams(search || "");
  let changed = false;
  for (const [oldKey, newKey] of LEGACY_BOARD_KEYS) {
    if (!params.has(oldKey)) continue;
    const values = params.getAll(oldKey).filter((v) => v !== "");
    params.delete(oldKey);
    if (!params.getAll(newKey).length) {
      for (const v of values) params.append(newKey, v);
    }
    changed = true;
  }
  return changed ? params.toString() : null;
}

/** 주소의 백로그 정렬 — 허용표 밖의 값이면 기본 순서다. */
export function backlogSortOf(state) {
  const sort = state && state.sort;
  if (!BACKLOG_SORT_KEYS.includes(sort)) return { ...BACKLOG_SORT_DEFAULT };
  return { sort, order: state.order === "desc" ? "desc" : "asc" };
}

/** 판 · 열 · 백로그가 싣는 조건. 여러 값은 키를 되풀이한다(`ticketQueryParams` 와 같은 모양). 팀 문맥은
 *  `department_id` 로 싣는다. 「내 티켓만」이 켜져 있으면 담당자 조건은 싣지 않는다. 정렬은 백로그만 받는다 —
 *  `sortDefault` 를 주면 그것과 다른 정렬만 싣고, 안 주면 정렬을 아예 싣지 않는다. `extra` 의 빈 값은 싣지 않는다. */
export function boardQueryParams(state, extra, sortDefault) {
  const view = {
    ...state,
    assignee_user_id: state.mine ? [] : state.assignee_user_id,
    sort: sortDefault ? state.sort : "",
  };
  const params = ticketQueryParams(view, BOARD_FIELDS, null, sortDefault || BACKLOG_SORT_DEFAULT);
  if (state.team) params.set("department_id", state.team);
  if (state.mine) params.set("mine", "true");
  for (const [key, value] of Object.entries(extra || {})) {
    if (value !== "" && value != null && value !== false) params.set(key, String(value));
  }
  return params;
}

/** 이미 만든 질의 문자열에 쪽 · 범위 값을 더한다. 빈 값은 싣지 않는다. */
function withParams(search, extra) {
  const params = new URLSearchParams(search);
  for (const [key, value] of Object.entries(extra || {})) {
    if (value !== "" && value != null && value !== false) params.set(key, String(value));
  }
  return params.toString();
}

/** 이동 본문의 `position_*` 목록 칸 — 값이 없으면 `null` 이다(서버는 한 값과 목록을 둘 다 받는다). */
function listOrNull(values) {
  const list = asList(values);
  return list.length ? list : null;
}

/** 이동 본문의 범위 칸 — 주소의 글자를 수로 싣는다. 읽을 수 없으면 `null` 이다. */
function numberOrNull(value) {
  if (value === "" || value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** 판이 어디까지 자랄 수 있는가. 칸 **안에서만** 굴러가고 페이지는 안 밀린다(지시 5). */
const COLUMN_BODY_MAX = "min(60vh, 44rem)";

/** 판이 그리는 자리. 서버 어휘(`app/work/workflow.py`)와 같은 말이다. */
const PLACE_COLUMN = "column";
const PLACE_COLLAPSED = "collapsed";
const PLACE_HIDDEN = "hidden";

const UNCLASSIFIED = "__unclassified__";

/* 열 하나가 받아 온 다음 쪽 카드. 초기값(board() 첫 쪽) 위에 얹인다 — board() 가 다시
 * 불리면(필터가 바뀌면) 이 상태도 함께 비워야 한다(§8.5, 아래 useEffect). */
const EMPTY_EXTRA = { cards: [], nextCursor: null, loading: false };

function cardKey(card) {
  return card.key || "이름 없음";
}

/** 백로그 한 줄. 표처럼 보이지만 표가 아니다 — 끌어서 순서를 바꿀 수 있어야 하기 때문이다.
 *
 * 공용 `DataTable` 은 행을 끌 수 없다. 순서가 이 목록의 **본질**이라(다음에 무엇을 하는가)
 * 그것을 포기하고 표를 얻는 거래는 안 한다(D-473 — 흡수하지 않고 열 어휘와 치수만 맞춘다).
 *
 * 머리 줄은 표 머리와 **같은 칸**이다(`ui/GridHeaderCell.jsx`, D-497). 열 선언은 티켓 표(`MyTickets.jsx::ticketColumns`)의
 * 어휘를 그대로 쓴다 — 같은 열이 같은 이름으로 정렬되고 같은 조건 창으로 걸린다. 머리 필터와 필터 바의 칸은 같은 주소
 * 상태다(`columnFilterValue` · `applyColumnFilter`). 머리 정렬(가로)은 열 어휘가 정한다 — 제목 열(티켓)만 왼쪽이다. */
const BACKLOG_COLUMNS = [
  { key: "tid", label: "티켓", type: "title", rem: 14, grows: true, sortable: true },
  { key: "priority", label: "우선순위", type: "status", rem: 6.5, sortable: true, filter: { kind: "enum", field: "priority" } },
  { key: "difficulty", label: "난이도", type: "enum", rem: 5.5, sortable: true, filter: { kind: "enum", field: "difficulty" } },
  { key: "est_wd", label: "예상", type: "number", rem: 5, sortable: true, filter: { kind: "number", field: "est_wd" } },
  { key: "due", label: "마감", type: "date", rem: 7.5, sortable: true },
  { key: "assignee", label: "담당자", type: "name", rem: 9, filter: { kind: "entity", field: "assignee_user_id" } },
  { key: "_actions", label: "작업", type: "actions", rem: 10 },
];

/* 정렬 칩의 낱말 — 「정렬: 마감 ↑」. 열 이름은 머리와 같은 낱말이다. 마감 열의 주소 값은 `due_date` 다
   (`TicketFilterBar.jsx::nextTicketSort` 와 같은 짝). */
export function backlogSortLabel({ sort, order }) {
  const column = BACKLOG_COLUMNS.find((c) => c.sortable && (c.key === "due" ? "due_date" : c.key) === sort);
  return `정렬: ${column ? column.label : "기본 순서"} ${order === "desc" ? "↓" : "↑"}`;
}

/** 칸 사이(`columnGap: 1` = `spacing(1)`)와 줄 좌우 여백(`px: 1.25`). 둘 다 rem 이라
 *  루트 폰트사이즈가 커지는 4K 에서 트랙과 같은 비율로 함께 자란다. */
const BACKLOG_GAP_REM = 0.5;
const BACKLOG_PAD_REM = 1.25;

export const BACKLOG_TRACKS = {
  xs: "1fr",
  md: BACKLOG_COLUMNS
    .map((c) => (c.grows ? `minmax(${c.rem}rem, 1fr)` : `${c.rem}rem`))
    .join(" "),
};

/* 백로그가 줄어들 수 있는 **바닥 폭** — 모든 열이 자기 폭을 지킬 때의 줄 폭. 바닥 아래로는
 * 줄이지 않고 **가로로 민다.** */
export const BACKLOG_MIN_WIDTH = `${
  BACKLOG_COLUMNS.reduce((sum, c) => sum + c.rem, 0)
  + BACKLOG_GAP_REM * (BACKLOG_COLUMNS.length - 1)
  + BACKLOG_PAD_REM
}rem`;

const BACKLOG_GRID = {
  display: "grid",
  gridTemplateColumns: BACKLOG_TRACKS,
  columnGap: 1,
  rowGap: 0.5,
  alignItems: "center",
};

/* 머리 줄 — `role="table"` 안의 `role="row"` 하나에 격자 머리 칸(`role="columnheader"`)이 선다. 몸통은 표가 아니라 끄는
   목록(`SortableList` · 「백로그 목록」)이라 표의 행이 아니다. 머리 줄은 표 머리와 **같은 높이**다(`CONTROL.tableHead`). */
function BacklogHead({ columns, sort, onSort, filters, onFilter, filterOptions, entityOptions }) {
  return (
    <Box role="table" aria-label="백로그 열" data-backlog-head="" sx={{ display: { xs: "none", md: "block" } }}>
      <Box
        role="row"
        sx={{
          ...BACKLOG_GRID,
          px: 1.25,
          py: 0.5,
          minHeight: remPx(CONTROL.tableHead),
          /* 몸통(가상 목록)은 굴러가는 상자라 스크롤바 자리(`scrollbar-gutter: stable`)를 늘 비워 둔다. 머리 줄도 같은 자리를
             비워야 두 격자의 트랙이 같은 x 에 선다. `scrollbar-gutter` 는 스크롤 상자에만 먹으므로 `overflow: hidden` 으로
             머리 줄을 스크롤 상자로 만든다 — 없으면 막대 스크롤바를 쓰는 Windows 에서 머리 칸이 제 열보다 15px 오른쪽에
             섰다(실측). 머리 칸의 필터 창은 포털이라 잘리지 않는다. */
          overflow: "hidden",
          scrollbarGutter: "stable",
        }}
      >
        {columns.map((c) => {
          const field = (c.filter && c.filter.field) || c.key;
          return (
            <GridHeaderCell
              key={c.key}
              column={c}
              sort={sort}
              onSort={onSort}
              filterValue={c.filter ? columnFilterValue(filters, field) : undefined}
              onFilter={onFilter}
              filterOptions={filterOptions && filterOptions[field]}
              entityOptions={entityOptions && entityOptions[field]}
            />
          );
        })}
      </Box>
    </Box>
  );
}

/* 빈 칸은 표와 같이 「-」 다(담당자는 「담당자 없음」 — `TicketPeople`). */
function EmptyCell() {
  return (
    <Typography variant="caption" color="text.secondary">
      -
    </Typography>
  );
}

/* `busy` 는 이동이 반영되는 동안(요청 · 재조회)이고, `adding` 은 **이 줄의** 「회차에 담기」가 가는 중이라는 뜻이다.
   그동안 단추는 꺼지고 담는 줄의 단추는 진행 중을 말한다 — 끌기가 같은 동안 꺼지는 것과 같은 규칙이다. */
function BacklogRow({ card, onOpen, signals, onAddToSprint, canAdd, busy = false, adding = false, onQuickEdit, onMoveToTop, onMoveToBottom, sorted }) {
  return (
    /* 백로그는 표 모양의 목록이다 — 우선순위 「긴급」도 면 없이 점 + 낱말로 선다(RULES §2). */
    <FlatBadgeSurface>
    {/* clovi-allow-geometry: 백로그는 표 모양의 목록이라 한 줄이 표 행 높이(`CONTROL.tableRow`)를 따른다. */}
    <Card
      padding="compact"
      sx={{
        ...BACKLOG_GRID,
        minHeight: remPx(CONTROL.tableRow),
        cursor: "pointer",
        transition: (t) => t.transitions.create("background-color", { duration: 90 }),
        "&:hover": { bgcolor: "background.inset" },
      }}
      onClick={() => onOpen(card)}
    >
      <Box sx={{ minWidth: 0 }}>
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
          <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
            {cardKey(card)}
          </Typography>
          <TicketSignals signals={signals} variant="mark" />
        </Stack>
        <Typography variant="body2" sx={{ ...KO_WORD_BREAK }}>
          {card.title || "제목 없음"}
        </Typography>
      </Box>
      <Box sx={{ textAlign: "center" }}>
        {card.priority ? (
          <Badge value={priorityKo(card.priority)} kind={priorityKind(card.priority)} />
        ) : <EmptyCell />}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
        {card.difficulty || "-"}
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ textAlign: "center", fontVariantNumeric: "tabular-nums" }}
      >
        {card.est_wd != null ? `${card.est_wd}WD` : "-"}
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ textAlign: "center", fontVariantNumeric: "tabular-nums" }}
      >
        {card.due || "-"}
      </Typography>
      <Box sx={{ display: "flex", justifyContent: "center", minWidth: 0 }}>
        <TicketPeople card={card} />
      </Box>
      {/* 작업 칸 — 끌기와 미리보기를 방해하지 않는 감싸개 안에 선다(`DragItemActions`). 정렬해서 보는 동안에는 순서를
          바꾸는 두 항목(맨 위로 · 맨 아래로)이 없다 — 화면의 순서가 끌어 옮긴 순서가 아니다. */}
      <DragItemActions sx={{ justifyContent: "center", gap: 0.5 }}>
        {canAdd ? (
          <Button
            variant="secondary"
            size="sm"
            disabled={busy}
            loading={adding}
            onClick={() => onAddToSprint(card)}
          >
            회차에 담기
          </Button>
        ) : null}
        <OverflowMenu
          size="sm"
          ariaLabel={`${cardKey(card)} 백로그 작업`}
          items={[
            { label: "빠른 수정", onClick: () => onQuickEdit(card) },
            sorted ? null : { label: "맨 위로", onClick: () => onMoveToTop(card) },
            sorted ? null : { label: "맨 아래로", onClick: () => onMoveToBottom(card) },
          ]}
        />
      </DragItemActions>
    </Card>
    </FlatBadgeSurface>
  );
}

/* 이동 응답의 새 version 을 받아 둔 목록에 심는다 — 위치는 안 옮긴다(재조회가 곧
 * 정본을 준다). 이 패치가 없으면 재조회가 오기 전의 짧은 창에서 같은 카드를 다시
 * 끌 때 옛 version 이 실려 혼자서도 409(「다른 사람이 먼저…」)를 봤다. */
function withCardVersion(list, fresh) {
  let changed = false;
  const next = (list || []).map((card) => {
    if (card.id !== fresh.id || card.version === fresh.version) return card;
    changed = true;
    return { ...card, version: fresh.version };
  });
  return changed ? next : list;
}

function patchBoardVersion(old, fresh) {
  if (!old) return old;
  let changed = false;
  const columns = (old.columns || []).map((col) => {
    const cards = withCardVersion(col.cards, fresh);
    if (cards === col.cards) return col;
    changed = true;
    return { ...col, cards };
  });
  const unclassified = withCardVersion(old.unclassified, fresh);
  if (unclassified !== old.unclassified) changed = true;
  return changed ? { ...old, columns, unclassified } : old;
}

function patchBacklogVersion(old, fresh) {
  if (!old || !old.pages) return old;
  let changed = false;
  const pages = old.pages.map((page) => {
    const items = withCardVersion(page.items, fresh);
    if (items === page.items) return page;
    changed = true;
    return { ...page, items };
  });
  return changed ? { ...old, pages } : old;
}

/** 값이 있는 조건만 질의 문자열에 넣는다. 빈 값을 실어 보내면 캐시 키가 갈라진다. */
function qs(pairs) {
  return new URLSearchParams(
    Object.entries(pairs).filter(([, v]) => v !== "" && v != null && v !== false)
      .map(([k, v]) => [k, String(v)])
  ).toString();
}

const COLUMN_PAGE_SIZE = 50;
const BACKLOG_PAGE_SIZE = 50;

/** 회차가 열려 있는가(planned·active) — 닫힌 회차는 기록이라 편성 단추가 서지 않는다. */
function isOpenSprint(sprint) {
  return !!sprint && sprint.state !== "closed";
}

/* 옛 주소 키로 들어오면 **판을 그리기 전에** 새 키로 고쳐 쓴다(replace). 옛 키를 읽은 채 판을 그리면 조건 없는 판 질의가
   먼저 나가고, 고친 뒤 같은 판을 한 번 더 읽는다 — 진입 한 번에 판 질의는 하나여야 한다. 고쳐 쓰는 동안은 아무것도 그리지
   않는다.
   🔴 고쳐 쓰기는 레이아웃 효과가 아니라 **보통 효과**에서 한다. 라우터는 자기 주소 구독을 레이아웃 효과에서 거는데 자식의
   레이아웃 효과가 먼저 돈다 — 앱을 처음 여는 순간(라우터와 이 화면이 같은 커밋에 선다) 그 자리에서 이동하면 라우터가
   못 듣고, 화면은 옛 주소에 머문 채 영영 비어 있다(시험이 실제로 그 상태를 잡았다). */
export function WorkBoard() {
  const [params, setParams] = useSearchParams();
  const legacy = rewriteLegacyBoardSearch(params.toString());
  React.useEffect(() => {
    if (legacy != null) setParams(new URLSearchParams(legacy), { replace: true });
  }, [legacy, setParams]);
  if (legacy != null) return null;
  return <WorkBoardScreen />;
}

function WorkBoardScreen() {
  const qc = useQueryClient();
  const toast = useToast();
  // 미리보기(`peek`)는 목록의 조건이 아니라 그 위에 잠깐 연 것이다 — 기억에서 뺀다.
  useListMemory("/work-board", { omit: ["peek"] });
  const [state, setState] = useQueryState(BOARD_SPEC);
  const peek = useTicketPeek(state, setState);
  const tab = state.tab === TAB_BACKLOG ? TAB_BACKLOG : TAB_BOARD;
  const teamId = state.team;
  const sprintId = state.sprint;
  const projectIds = React.useMemo(() => asList(state.project_id), [state.project_id]);
  // 프로젝트를 **하나만** 골랐을 때만 그 프로젝트가 문맥이다(새 티켓의 기본값 · 담당자 후보 · 카드의 프로젝트 줄).
  const singleProject = projectIds.length === 1 ? projectIds[0] : "";
  const mine = state.mine;
  const showHold = state.hold;
  /* §8.1 — 완료·취소까지 보는 토글. 회차 안에서도 접을 수 있고, **회차 안의 기본값은
     접힘**이다. 회의에서 보는 것은 남은 일이다. */
  const showAllChosen = state.all;
  const backlogSort = backlogSortOf(state);
  const backlogSorted = backlogSort.sort !== BACKLOG_SORT_DEFAULT.sort
    || backlogSort.order !== BACKLOG_SORT_DEFAULT.order;
  const [sprintFormOpen, setSprintFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState(null);
  // 열 하나가 첫 쪽 위에 받아 온 다음 쪽들. `{ [statusKey]: { cards, nextCursor, loading } }`
  const [colExtra, setColExtra] = React.useState({});

  const signalsOf = useTicketSignals();

  const projects = useTicketProjects(true);
  const meta = useTicketMeta(true);
  // 후보는 **그 프로젝트에 닿을 수 있는 사람**으로 서버가 좁혀 준다(프로젝트를 하나만 골랐을 때).
  const assignees = useAssigneeOptions(true, singleProject);

  /* 회차 목록은 **팀별**이다(D-482). 응답에 팀 선택기의 후보와 기본 선택(`team`)이 함께
     온다 — 화면이 스스로 조직도를 훑어 만들면 서버가 좁힌 범위와 갈라진다. 팀을 안 골랐으면
     서버가 기본 팀(본인 부서, 아니면 유일한 후보)의 회차를 준다. */
  const sprints = useQuery({
    queryKey: ["work-sprints", teamId],
    queryFn: () => api("/api/work/sprints?" + qs({ department_id: teamId })),
  });
  const sprintRows = React.useMemo(
    () => (sprints.data && sprints.data.sprints) || [],
    [sprints.data],
  );
  /* 닫힌 회차의 판은 **기록**이다(D-484) — 「남은 일만」 보는 실행 시야는 끝난 회차에서 뜻이
     없어(전부 끝난 회차는 빈 판이 된다) 완료·취소까지 늘 편다. 그때 토글은 감춘다. */
  const sprintClosed = sprintRows.some((s) => s && s.id === sprintId && s.state === "closed");
  const showAll = showAllChosen || sprintClosed;
  const team = (sprints.data && sprints.data.team) || null;
  const teamOptions = React.useMemo(() => (team && team.options) || [], [team]);
  const teamRow = React.useMemo(
    () => teamOptions.find((o) => o.id === teamId) || null,
    [teamOptions, teamId],
  );
  const teamLabel = teamLabelOf(teamRow);
  // 편성 단추의 화면 쪽 그림자 — 역할(`PROJECT_WRITE`) ∧ 이 팀의 관리 범위. 서버가 둘 다
  // 다시 본다(403). 감추는 것은 보안이 아니라 **누를 수 없는 단추를 안 보여 주는 것**이다.
  const roleCanPlan = useCanPlanSprint();
  const canPlan = roleCanPlan && !!teamRow && teamRow.manageable === true;

  /* 팀 자동 선택 — 주소에 팀이 없으면 서버가 고른 기본 팀을 주소에 적는다(replace).
     같은 응답이 이미 그 팀의 회차라 캐시에 미리 심어 두 번째 요청을 없앤다. */
  React.useEffect(() => {
    if (teamId || !sprints.isSuccess) return;
    const picked = team && team.selected;
    if (!picked) return;
    qc.setQueryData(["work-sprints", picked], sprints.data);
    setState({ team: picked }, { replace: true });
  }, [teamId, sprints.isSuccess, sprints.data, team, qc, setState]);
  // 팀이 정해졌는가(주소에 있거나, 기본 팀이 없어 고를 수 없는 상태가 확인됐는가).
  const teamSettled = !!teamId || (sprints.isSuccess && !(team && team.selected));

  // §8.3 — 진입 시 그 팀의 열린 회차가 있으면 자동으로 고른다. 한 번만 한다 — 사용자가
  // 그 뒤 직접 회차를 비우면 자동 선택이 다시 덮어쓰지 않는다. 팀이 바뀌면 다시 무장한다.
  const autoSelectedFor = React.useRef(state.sprint ? teamId : null);
  const [sprintSettled, setSprintSettled] = React.useState(!!state.sprint);
  /* 팀이 비면(같은 메뉴를 다시 눌러 주소의 질의가 비었다) 「진입 때 한 번」을 다시 무장한다 — 팀이 다시 서면 그 팀의
     열린 회차가 다시 선다. 셸이 같은 메뉴 재클릭을 새 진입으로 다시 마운트하지만(`app/navEntry.jsx`, D-498) 이 화면은
     그것에 기대지 않는다: 주소가 비는 길은 뒤로가기 · 목록의 기억 · 손으로 고친 주소에도 있다. 무장이 풀린 채 팀만
     다시 서면 회차 없는 판이 선다 — 한 번 누른 끝 상태와 다르다. */
  React.useEffect(() => {
    if (teamId) return;
    autoSelectedFor.current = null;
    setSprintSettled(false);
  }, [teamId]);
  React.useEffect(() => {
    if (!teamSettled) return;
    if (!sprints.isSuccess && !sprints.isError) return;
    if (!sprintId && autoSelectedFor.current !== teamId && sprints.isSuccess) {
      autoSelectedFor.current = teamId;
      const picked = pickOpenSprint(sprintRows);
      if (picked) {
        setState({ sprint: picked.id }, { replace: true });
        return;
      }
    }
    setSprintSettled(true);
  }, [teamSettled, sprints.isSuccess, sprints.isError, sprintId, teamId, sprintRows, setState]);

  /** 팀을 바꾼다 — 회차·프로젝트는 그 팀의 것이 아니므로 비우고, 자동 선택을 다시 무장한다. */
  const changeTeam = React.useCallback((next) => {
    autoSelectedFor.current = null;
    setSprintSettled(false);
    setState({ team: next || "", sprint: "", project_id: [] });
  }, [setState]);

  // §8.1 — scope. 「완료와 취소 보기」를 켜면 all, 아니면 execution 이다.
  const scope = showAll ? "all" : "execution";

  /* 판과 백로그가 **같은 축으로 좁힌다**. 팀 문맥(`department_id`)이 그 첫 축이다. 질의 문자열 하나가 조건 전부라
     그것을 그대로 캐시 키로 쓴다 — 같은 문자열이면 같은 요청이다. */
  const conditionQs = boardQueryParams(state).toString();
  const boardQs = withParams(conditionQs, { sprint_id: sprintId, scope, column_page_size: COLUMN_PAGE_SIZE });
  const board = useQuery({
    queryKey: ["work-board", boardQs],
    queryFn: () => api("/api/work/board?" + boardQs),
    enabled: tab === TAB_BOARD && !!teamId && sprintSettled,
  });

  // 필터가 바뀌면 다음 쪽으로 받아 둔 것도 함께 비운다.
  React.useEffect(() => { setColExtra({}); }, [boardQs]);

  /* 백로그는 정렬을 더 싣는다 — 기본 순서(끌어 옮긴 순서)면 싣지 않는다. 커서는 불투명하다(정렬 중에도 화면은 받은 값을
     그대로 돌려보낸다). */
  const backlogQs = boardQueryParams({ ...state, ...backlogSort }, null, BACKLOG_SORT_DEFAULT).toString();
  const backlog = useInfiniteQuery({
    queryKey: ["work-backlog", backlogQs],
    queryFn: ({ pageParam }) =>
      api("/api/work/backlog?" + withParams(backlogQs, { cursor: pageParam || "", limit: BACKLOG_PAGE_SIZE })),
    initialPageParam: null,
    getNextPageParam: (lastPage) => lastPage.next_cursor || undefined,
    enabled: tab === TAB_BACKLOG && !!teamId,
  });

  const createSprint = useMutation({
    mutationFn: (body) => api("/api/work/sprints", { method: "POST", body }),
    onSuccess: (sprint) => {
      qc.invalidateQueries({ queryKey: ["work-sprints"] });
      setSprintFormOpen(false);
      // 만든 회차를 바로 고른다. 팀은 그대로다 — 이 팀의 회차를 만들었다. 프로젝트 필터도
      // 건드리지 않는다(프로젝트는 회차의 소유자가 아니다).
      setState({ sprint: sprint.id });
      toast("회차를 추가했습니다.", "success");
    },
    onError: (e) =>
      toast((e && e.message) || "회차를 추가하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  /* 같은 이동은 끝나기 전에 한 번만 나간다(`useGuardedMutation`). 이동은 카드의 `base_version` 을 싣는데, 같은 요청이
     두 번 나가면 둘째가 첫째가 올린 판을 모르고 409(「다른 사람이 먼저 이 티켓을 옮겼습니다」)로 끝났다 — 백로그 줄의
     「회차에 담기」를 두 번 누른 사람이 자기 클릭 때문에 그 문장을 봤다. */
  const move = useGuardedMutation({
    mutationFn: ({ id, body }) =>
      api(`/api/work/board/${encodeURIComponent(id)}/move`, { method: "POST", body }),
    onSuccess: (data, variables) => {
      setColExtra({});
      const fresh = data && data.ticket;
      if (fresh) {
        qc.setQueriesData({ queryKey: ["work-board"] }, (old) => patchBoardVersion(old, fresh));
        qc.setQueriesData({ queryKey: ["work-backlog"] }, (old) => patchBacklogVersion(old, fresh));
      }
      // 어떤 키가 티켓을 그리는지는 `ticket-views.js` 한 곳이 안다(미리보기 포함).
      invalidateTicketViews(qc);
      if (variables && variables.body && variables.body.to_status) {
        celebrateIfCompletedCategory(fresh);
      }
      if (variables && variables.toastText) toast(variables.toastText, "success");
    },
    onError: (e) => {
      if (e && e.status === 409) {
        qc.invalidateQueries({ queryKey: ["work-board"] });
        qc.invalidateQueries({ queryKey: ["work-backlog"] });
      }
      toast((e && e.message) || "옮기지 못했습니다. 다시 시도해 주세요.", "error");
    },
  });

  /* 판의 카드를 편집 모달이 아는 모양으로 편다. */
  const asTicket = React.useCallback(
    (card) => ({
      id: card.page_id,
      title: card.title,
      project_uid: card.project_uid,
      status: card.status,
      priority: card.priority,
      difficulty: card.difficulty,
      est_wd: card.est_wd,
      act_wd: card.act_wd,
      due: card.due,
      start: card.start,
      category: card.category,
      assignee_user_ids: card.assignee_user_ids || [],
      sprint_id: card.sprint_id,
    }),
    []
  );

  /* 열 하나의 다음 쪽 — **첫 쪽과 같은 조건**으로(§8.5). 조건은 판 질의와 같은 문자열(`conditionQs`)에서 온다 — 축을
     더하는 날 판과 열이 따로 늘지 않는다. */
  const loadMoreColumn = React.useCallback(
    async (statusKey, cursor) => {
      setColExtra((prev) => ({
        ...prev, [statusKey]: { ...(prev[statusKey] || EMPTY_EXTRA), loading: true },
      }));
      try {
        const body = await api(
          `/api/work/board/columns/${encodeURIComponent(statusKey)}?` +
            withParams(conditionQs, { sprint_id: sprintId, scope, cursor, limit: COLUMN_PAGE_SIZE })
        );
        setColExtra((prev) => {
          const before = prev[statusKey] || EMPTY_EXTRA;
          return {
            ...prev,
            [statusKey]: {
              cards: [...before.cards, ...(body.cards || [])],
              nextCursor: body.next_cursor || null,
              loading: false,
            },
          };
        });
      } catch (e) {
        setColExtra((prev) => ({
          ...prev, [statusKey]: { ...(prev[statusKey] || EMPTY_EXTRA), loading: false },
        }));
        toast((e && e.message) || "더 받아오지 못했습니다. 다시 시도해 주세요.", "error");
      }
    },
    [conditionQs, sprintId, scope, toast]
  );

  const sprint = sprintRows.find((s) => s.id === sprintId) || null;
  const sprintOpen = isOpenSprint(sprint);
  // 「티켓 추가」·「이 칸에 추가」가 실어 나르는 문맥 — 팀은 언제나, 회차는 편성할 수 있고
  // 열려 있을 때만(판 탭에서). 백로그 탭에서 만든 티켓이 회차로 들어가면 그 탭의 뜻과 어긋난다.
  const newTicketContext = {
    team: teamId,
    project: singleProject,
    sprint: tab === TAB_BOARD && canPlan && sprintOpen ? sprintId : "",
  };

  /* 열은 서버가 정한 **자리**로 고른다(`placement`). 첫 쪽(board.data) 위에 `colExtra` 로
     받아 둔 다음 쪽들을 얹는다. */
  const columns = React.useMemo(() => {
    const data = board.data;
    if (!data) return [];
    const wanted = [PLACE_COLUMN];
    if (showHold) wanted.push(PLACE_COLLAPSED);
    if (showAll) wanted.push(PLACE_HIDDEN);
    const merge = (first, extra) => {
      const seen = new Set((first || []).map((x) => x.id));
      return [...(first || []), ...extra.cards.filter((x) => !seen.has(x.id))];
    };
    const cols = (data.columns || [])
      .filter((c) => wanted.indexOf(c.placement || PLACE_COLUMN) >= 0)
      .map((c) => {
        const extra = colExtra[c.key] || EMPTY_EXTRA;
        const items = merge(c.cards, extra);
        const nextCursor = extra.cards.length ? extra.nextCursor : c.next_cursor;
        return {
          id: c.key,
          title: c.label,
          count: c.total,
          items,
          hint: c.total > items.length ? `전체 ${c.total}건 중 ${items.length}건 표시` : null,
          action: nextCursor ? (
            <Button
              variant="ghost" size="sm" loading={extra.loading}
              onClick={() => loadMoreColumn(c.key, nextCursor)}
            >
              더 보기
            </Button>
          ) : null,
          footer: (
            <Button
              variant="ghost" size="sm"
              component={RouterLink}
              to={"/new-ticket?" + qs({ ...newTicketContext, status: c.key })}
              onClick={(e) => e.stopPropagation()}
            >
              이 칸에 추가
            </Button>
          ),
        };
      });
    if ((data.unclassified || []).length || data.unclassified_next_cursor) {
      const extra = colExtra[UNCLASSIFIED] || EMPTY_EXTRA;
      const items = merge(data.unclassified, extra);
      const nextCursor = extra.cards.length ? extra.nextCursor : data.unclassified_next_cursor;
      cols.push({
        id: UNCLASSIFIED,
        title: "분류되지 않음",
        count: data.unclassified_total,
        items,
        droppable: false,
        hint: "상태 값이 목록에 없습니다.",
        action: nextCursor ? (
          <Button
            variant="ghost" size="sm" loading={extra.loading}
            onClick={() => loadMoreColumn(UNCLASSIFIED, nextCursor)}
          >
            더 보기
          </Button>
        ) : null,
      });
    }
    return cols;
    // `newTicketContext` 는 렌더마다 새 객체지만 내용은 아래 원시값이 정한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [board.data, showHold, showAll, colExtra, teamId, singleProject, sprintId, tab, canPlan, sprintOpen, loadMoreColumn]);

  const backlogPages = React.useMemo(
    () => (backlog.data && backlog.data.pages) || [],
    [backlog.data]
  );
  const backlogRows = React.useMemo(
    () => backlogPages.flatMap((p) => p.items || []),
    [backlogPages]
  );
  const backlogTotal = backlogPages.length ? backlogPages[0].total : 0;

  const cardById = React.useMemo(() => {
    const out = {};
    for (const c of columns) for (const it of c.items) out[it.id] = it;
    for (const it of backlogRows) out[it.id] = it;
    return out;
  }, [columns, backlogRows]);

  const labelOf = React.useCallback(
    (id) => {
      const card = cardById[id];
      return card ? `${cardKey(card)} ${card.title || ""}`.trim() : "";
    },
    [cardById]
  );

  const dragOverlay = React.useCallback(
    (id) => {
      const card = cardById[id];
      return card ? (
        <TicketFace card={card} signals={signalsOf(card)} showProject={!singleProject} />
      ) : null;
    },
    [cardById, signalsOf, singleProject]
  );

  function handleBoardMove({ id, fromColumn, toColumn, beforeId, afterId }) {
    const card = cardById[id];
    if (!card || toColumn === UNCLASSIFIED) return;
    move.mutate({
      id,
      body: {
        to_status: fromColumn === toColumn ? null : toColumn,
        before_id: beforeId,
        after_id: afterId,
        reorder: true,
        on_board: true,
        base_version: card.version,
      },
    });
  }

  function handleBacklogReorder({ id, beforeId, afterId }) {
    const card = cardById[id];
    if (!card) return;
    move.mutate({
      id,
      body: { before_id: beforeId, after_id: afterId, reorder: true, base_version: card.version },
    });
  }

  /* 화면에 없는 카드 기준 이동(§8.5) — "지금 화면이 보는 백로그"와 같은 조건을
     `position_*` 로 다시 실어, 서버가 카드를 안 끌어오고도 목표 순위를 잰다. 여러 값 축은 목록으로 싣는다. */
  function movePosition(card, position) {
    move.mutate({
      id: card.id,
      body: {
        reorder: true, base_version: card.version,
        to_position: position,
        position_project_id: listOrNull(state.project_id),
        position_q: state.q || null,
        position_assignee_user_id: mine ? null : listOrNull(state.assignee_user_id),
        position_mine: mine,
        position_priority: listOrNull(state.priority),
        position_difficulty: listOrNull(state.difficulty),
        position_est_wd_min: numberOrNull(state.est_wd_min),
        position_est_wd_max: numberOrNull(state.est_wd_max),
        position_department_id: teamId || null,
        position_signal: state.signal || null,
      },
    });
  }

  function addToSprint(card) {
    if (!sprintId) {
      toast("먼저 담을 회차를 고르세요.", "warn");
      return;
    }
    move.mutate({
      id: card.id,
      body: { sprint_id: sprintId, set_sprint: true, base_version: card.version },
      toastText: "회차에 담았습니다.",
    });
  }

  /** 현재 회차에서 뺀다 — 백로그로 돌아간다. 「스프린트에서 뺀다」와 「안 건드린다」는 다른
   *  요청이라 의도(`set_sprint`)를 따로 싣는 서버 계약 그대로다. */
  function removeFromSprint(card) {
    move.mutate({
      id: card.id,
      body: { sprint_id: null, set_sprint: true, base_version: card.version },
      toastText: "현재 회차에서 빼 백로그로 돌렸습니다.",
    });
  }

  const active = tab === TAB_BOARD ? board : backlog;
  const moveBusy =
    move.isPending || (tab === TAB_BOARD ? board.isFetching : backlog.isFetching);
  /* 지금 회차에 담는 중인 카드 — 그 줄의 「회차에 담기」가 진행 중을 말한다. */
  const addingId =
    move.isPending && move.variables && move.variables.body && move.variables.body.set_sprint
      && move.variables.body.sprint_id ? move.variables.id : null;
  const projectRows = React.useMemo(
    () => eligibleProjects((projects.data && projects.data.projects) || [], teamId),
    [projects.data, teamId],
  );
  const assigneeRows = React.useMemo(
    () => (assignees.data && assignees.data.assignees) || [],
    [assignees.data],
  );
  const metaBody = React.useMemo(() => meta.data || {}, [meta.data]);

  /* 필터 바 · 백로그 머리 필터가 **같은 후보**를 쓴다 — 프로젝트는 이 팀의 것, 담당자는 (하나 고른) 프로젝트에 닿는 사람. */
  const projectItems = React.useMemo(
    () => projectRows.map((p) => ({ value: p.id, label: p.name || "(제목 없음)" })),
    [projectRows],
  );
  const assigneeItems = React.useMemo(() => ticketAssigneeOptions(assigneeRows), [assigneeRows]);
  const filterCandidates = React.useMemo(() => ({
    project_id: { items: projectItems, loading: projects.isLoading },
    assignee_user_id: { items: assigneeItems, loading: assignees.isLoading },
  }), [projectItems, assigneeItems, projects.isLoading, assignees.isLoading]);
  const headFilterOptions = React.useMemo(() => ({
    priority: (metaBody.priorities || []).map((p) => ({ value: p, label: priorityKo(p) })),
    difficulty: metaBody.difficulties || [],
  }), [metaBody]);
  const headEntityOptions = React.useMemo(() => ({ assignee_user_id: assigneeItems }), [assigneeItems]);
  // 「내 티켓만」이 켜져 있으면 담당자 조건을 쓰지 않는다 — 머리의 담당자 필터도 서지 않는다.
  const backlogColumns = React.useMemo(
    () => (mine ? BACKLOG_COLUMNS.map((c) => (c.key === "assignee" ? { ...c, filter: undefined } : c)) : BACKLOG_COLUMNS),
    [mine],
  );

  const boardEmpty = columns.every((c) => c.items.length === 0);
  // 빈 목록이 「조건 때문」인지 가르는 값 — 쓰지 않는 담당자 조건(내 티켓만)은 세지 않는다.
  const filtersActive = hasTicketFilter(
    state,
    mine ? BOARD_FILTER_KEYS.filter((k) => k !== "assignee_user_id") : BOARD_FILTER_KEYS,
  );
  /* 「필터 지우기」 — 데이터 조건만 걷는다. 팀 · 회차 · 탭 · 보기 옵션(내 티켓만 · 보류 · 완료와 취소)은 그대로다. 백로그
     탭에서는 조건 줄에 선 정렬 칩도 함께 걷는다(지우기는 조건 줄에 보이는 것을 전부 걷는다). */
  const clearFilters = React.useCallback(() => {
    setState({
      ...clearTicketFilters(BOARD_FIELDS),
      ...(tab === TAB_BACKLOG ? BACKLOG_SORT_DEFAULT : null),
    });
  }, [setState, tab]);
  const resetSort = React.useCallback(() => setState({ ...BACKLOG_SORT_DEFAULT }), [setState]);
  const sortChips = tab === TAB_BACKLOG && backlogSorted
    ? [{ key: "sort", label: backlogSortLabel(backlogSort), onDelete: resetSort }]
    : null;
  // 조건 줄의 결과 수 — 칸반은 판의 요약(자르기 전), 백로그는 목록의 전체 수다. 받기 전이면 「세는 중…」이다.
  const resultTotal = tab === TAB_BOARD
    ? (board.data && board.data.summary ? board.data.summary.total : null)
    : (backlogPages.length ? backlogTotal : null);

  const teamOptionsForForm = React.useMemo(
    () => teamOptions.filter((o) => o.manageable).map((o) => ({ value: o.id, label: teamLabelOf(o) })),
    [teamOptions],
  );
  // 열린 회차에 담긴 티켓의 프로젝트 후보를 같은 팀으로 좁히는 빠른 수정 문맥(D-482).
  const projectScope = React.useMemo(
    () => (teamId ? { teamId, note: "열린 회차에 담긴 티켓은 같은 팀의 프로젝트로만 옮길 수 있습니다." } : null),
    [teamId],
  );

  /* 판 위의 한 줄 — **지금 어디쯤인가와 다음에 할 일**. 흐름은 넷이다: 회차를 안 골랐다 ·
     아직 안 열었다 · 진행 중이다 · 끝났다. 팀 미정 회차는 다섯째다. */
  const boardNotice = (() => {
    if (!sprintId) {
      const scopeLine = showAll
        ? "완료와 취소를 포함한 이 팀의 전체 티켓을 보여 줍니다."
        : "이 팀의 실행 중인 업무만 보여 줍니다.";
      const noneOpen =
        sprintRows.length > 0 && !sprintRows.some((s) => s && (s.active || s.state === "active"));
      if (noneOpen) {
        return {
          title: "진행 중인 회차가 없습니다.",
          body: canPlan
            ? `${scopeLine} 위에서 지난 회차를 고르거나 「회차 추가」로 새 회차를 만들 수 있습니다.`
            : `${scopeLine} 위 회차 칸에서 지난 회차를 골라 볼 수 있습니다.`,
        };
      }
      return {
        title: "회차를 고르지 않았습니다.",
        body: `${scopeLine} 회차를 고르면 그 회차의 일만 봅니다.`,
      };
    }
    const label = sprint ? sprint.name : "이 회차";
    if (sprint && !sprint.department_id) {
      return {
        title: `${label} (팀 미정)`,
        body: canPlan
          ? "팀이 정해지지 않은 회차입니다. 「회차 수정」에서 팀을 정하면 티켓을 담고 회차를 열 수 있습니다."
          : "팀이 정해지지 않은 회차입니다. 팀 지정은 조직 관리자가 할 수 있습니다.",
      };
    }
    if (sprint && sprint.state === "planned") {
      return {
        title: `${label} (${sprintStateLabel(sprint)})`,
        body: "아직 열지 않은 회차입니다. 백로그에서 할 일을 담고 「회차 열기」를 누르면 오늘부터 진행을 셉니다.",
      };
    }
    if (sprint && sprint.state === "closed") {
      return {
        title: `${label} (${sprintStateLabel(sprint)})`,
        body: "끝난 회차라 기록으로만 남습니다. 완료와 취소까지 모두 보이고, 카드를 옮기거나 담고 뺄 수 없습니다.",
      };
    }
    return {
      title: `${label} (${sprintStateLabel(sprint) || "진행 중"})`,
      body: showAll
        ? "완료와 취소까지 함께 보여 줍니다. 회의에서는 남은 일만 보는 편이 빠릅니다."
        : "남은 일만 보여 줍니다. 끝난 일은 「완료와 취소 보기」로 펼칩니다.",
    };
  })();

  /** 카드 안 작업 메뉴 — 편성할 수 있는 열린 회차의 판에서만. 끌기·미리보기를 방해하지 않는다. */
  const cardActions = React.useCallback(
    (card) => {
      if (!canPlan || !sprintOpen || !sprintId || card.sprint_id !== sprintId) return null;
      return (
        <DragItemActions>
          <OverflowMenu
            size="sm"
            ariaLabel={`${cardKey(card)} 카드 작업`}
            items={[
              { label: "빠른 수정", onClick: () => setEditing(asTicket(card)) },
              { label: "현재 회차에서 빼기", onClick: () => removeFromSprint(card) },
            ]}
          />
        </DragItemActions>
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canPlan, sprintOpen, sprintId, asTicket]
  );

  const peekActions = React.useMemo(() => {
    if (!canPlan || !sprintOpen || !sprintId || !peek.pageId) return [];
    const card = Object.values(cardById).find((c) => c.page_id === peek.pageId);
    if (!card) return [];
    if (card.sprint_id === sprintId) {
      return [{ key: "remove", label: "현재 회차에서 빼기", onClick: () => { removeFromSprint(card); peek.close(); } }];
    }
    if (!card.sprint_id && sprint && sprint.department_id) {
      return [{ key: "add", label: "회차에 담기", onClick: () => { addToSprint(card); peek.close(); } }];
    }
    return [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canPlan, sprintOpen, sprintId, peek.pageId, cardById, sprint]);

  const noTeamAtAll = sprints.isSuccess && teamOptions.length === 0;
  const needTeamPick = sprints.isSuccess && !teamId && !(team && team.selected) && teamOptions.length > 0;

  /* 조건 때문에 빈 목록 · 「내 티켓만」 때문에 빈 목록은 두 판 모두 같은 말을 한다. 둘 다 아니면 판마다 자기 말을 한다. */
  const emptyByFilter = (title, help) => (
    <EmptyState
      title={title}
      help={help}
      action={<Button variant="secondary" onClick={clearFilters}>필터 지우기</Button>}
    />
  );
  const emptyByMine = (
    <EmptyState
      title="내 티켓이 없습니다."
      help="「내 티켓만」을 끄면 이 팀의 티켓을 모두 볼 수 있습니다."
      action={<Button variant="secondary" onClick={() => setState({ mine: false })}>내 티켓만 끄기</Button>}
    />
  );

  return (
    <>
      <PageHeader
        area="팀 업무"
        title="작업 보드"
        crumbRoot={null}
        description="팀의 회차를 구성하고, 지금 무슨 일이 어디까지 왔는지 보며 다음에 할 일의 순서를 정합니다."
        actions={
          /* 머리 동작의 순서 — 보조 동작이 먼저, 채움은 오른쪽 끝이다. 채움은 둘 중 하나만 선다: 회차가 하나도 없으면
             「회차 추가」, 예정 회차를 골랐으면 회차 한 바퀴의 「회차 열기」다. 그래서 회차 한 바퀴가 맨 끝이고 「회차 추가」는
             그 바로 앞이다(회차가 없으면 한 바퀴는 서지 않는다). */
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            {/* 🔴 **만드는 자리가 기본값을 정한다** (지시 5). 팀 문맥은 언제나 싣고, 회차는
                편성할 수 있는 열린 회차일 때만 싣는다. 회차 id 는 서버가 다시 본다. */}
            {teamId ? (
              <Button
                variant="secondary"
                component={RouterLink}
                to={"/new-ticket?" + qs(newTicketContext)}
              >
                티켓 추가
              </Button>
            ) : null}
            {/* 회의 화면으로 가는 길 — 머리 동작이라 34 보조 단추다(글자 단추는 목록 안 부수 동작의 자리다). */}
            {sprintId ? (
              <Button
                variant="secondary"
                component={RouterLink}
                to={"/sprint?" + qs({ team: teamId, sprint: sprintId })}
              >
                스프린트 회의
              </Button>
            ) : null}
            {canPlan ? (
              <Button
                variant={sprintRows.length === 0 ? "primary" : "secondary"}
                onClick={() => setSprintFormOpen(true)}
              >
                회차 추가
              </Button>
            ) : null}
            {/* 회차의 한 바퀴 — 열고 닫는 자리. 회의 화면과 **같은 부품**을 쓴다. */}
            <SprintLifecycle
              sprint={sprint}
              sprints={sprintRows}
              size="md"
              canPlan={canPlan}
              teams={teamOptionsForForm}
              onDeleted={() => setState({ sprint: "" })}
            />
          </Stack>
        }
        help="카드를 누르면 미리보기가 열리고, 끌어서 상태와 순서를 바꿉니다. 키보드로는 스페이스로 집고 화살표로 옮긴 뒤 스페이스로 놓습니다."
      />

      {/* 문맥 · 보기 줄 — 어느 판을 보는가(팀 · 회차)와 어떻게 그리는가(칸반|백로그 · 보기 옵션). 데이터 조건이 아니라서
          아래 필터 바와 다른 줄이고, 「필터 지우기」가 이 줄을 건드리지 않는다(D-497). 팀 · 회차는 값이 경로 · 긴 이름이라
          wide 칸이다. */}
      <ContextBar
        context={(
          <>
            <TeamSelect team={team} value={teamId} onChange={changeTeam} loading={sprints.isLoading} />
            <EntityCombobox
              size="wide"
              /* 백로그 탭에서 이 축은 목록을 거르지 않는다(백로그는 회차 없는 일이다) —
                 「회차에 담기」의 대상 선택기다. 이름이 그 역할을 말하게 한다. */
              label={tab === TAB_BACKLOG ? "담을 회차" : "회차"}
              value={sprintId}
              onChange={(next) => setState({ sprint: next || "" })}
              loading={sprints.isLoading}
              disabled={!teamId}
              options={sprintRows.map((s) => ({
                value: s.id,
                label: `${s.name} (${s.active ? "진행 중" : sprintStateLabel(s)})`,
                secondary: `${s.starts_on} ~ ${s.ends_on}`,
              }))}
              allLabel="전체"
            />
          </>
        )}
        /* 보기 전환은 세그먼티드(34)다 — 같은 두 옵션 · 같은 접근 이름(표 5). */
        view={teamId ? (
          <Segmented
            ariaLabel="보기 선택" value={tab} onChange={(v) => setState({ tab: v })}
            options={[{ value: TAB_BOARD, label: "칸반" }, { value: TAB_BACKLOG, label: "백로그" }]}
          />
        ) : null}
        /* 보기 옵션은 켬/끔 34 중립 단추다 — 켜져 있을 때만 눌린 면이다(핸드오프 RULES §3 · 계획 P-14). 「내 티켓만」이 맨
           앞이다: 뒤의 둘은 칸반에만 뜻이 있어 백로그 탭에서 빠지고, 닫힌 회차에서는 완료와 취소가 늘 보여 그 토글이 없다. */
        options={teamId ? (
          <>
            <FilterToggle pressed={mine} onClick={() => setState({ mine: !mine })}>내 티켓만</FilterToggle>
            {tab === TAB_BOARD ? (
              <FilterToggle pressed={showHold} onClick={() => setState({ hold: !showHold })}>
                {showHold ? "보류 접기" : "보류 펴기"}
              </FilterToggle>
            ) : null}
            {tab === TAB_BOARD && !sprintClosed ? (
              <FilterToggle pressed={showAll} onClick={() => setState({ all: !showAll })}>
                {showAll ? "완료와 취소 감추기" : "완료와 취소 보기"}
              </FilterToggle>
            ) : null}
          </>
        ) : null}
      />

      {/* 데이터 필터 — 티켓 목록 셋과 같은 필터 바 한 줄이다. 후보는 이 팀으로 좁히고(프로젝트) 고른 프로젝트로 좁힌다
          (담당자). 조건이 있으면 같은 면 안 둘째 줄이 조건 칩 · 결과 수 · 「필터 지우기」다. */}
      {teamId ? (
        <TicketFilterBar
          fields={BOARD_FIELDS}
          value={state}
          onChange={setState}
          total={resultTotal}
          options={filterCandidates}
          disabled={mine ? MINE_OFF : null}
          tailChips={sortChips}
          onClear={clearFilters}
        />
      ) : null}

      {sprints.isError ? <ErrorState layout="region" error={sprints.error} onRetry={sprints.refetch} /> : null}

      {noTeamAtAll ? (
        <EmptyState
          layout="page"
          title="회차를 볼 수 있는 팀이 없습니다."
          help="소속 팀이 정해지면 그 팀의 회차와 백로그가 여기 보입니다. 소속은 관리자가 지정할 수 있습니다."
        />
      ) : null}
      {needTeamPick ? (
        <EmptyState
          layout="page"
          title="팀을 골라 주세요."
          help="회차는 팀이 운영합니다. 위 팀 칸에서 팀을 고르면 그 팀의 회차와 백로그가 보입니다."
        />
      ) : null}

      {teamId ? (
        <>
          {/* 칸반 판 위의 한 줄 — 지금 어디쯤인가와 다음에 할 일. 문맥 줄에 넣기에는 문장이 길어 필터 바 아래 한 줄이다. */}
          {tab === TAB_BOARD ? (
            <Callout variant="inline" tone="info" title={boardNotice.title}>
              {boardNotice.body}
            </Callout>
          ) : null}
          {/* 정렬해서 보는 백로그 — 화면의 순서가 끌어 옮긴 순서가 아니라서 끌기와 순서 이동을 쓰지 않는다. 기본 순서로
              돌아가는 길을 같은 자리에 둔다(조건 줄의 정렬 칩도 같은 일을 한다). */}
          {tab === TAB_BACKLOG && backlogSorted && backlogRows.length ? (
            <Callout
              tone="info"
              compact
             
              action={<Button size="sm" onClick={resetSort}>기본 순서로 보기</Button>}
            >
              정렬해서 보는 동안에는 끌어서 순서를 바꿀 수 없습니다.
            </Callout>
          ) : null}

          {moveBusy && !active.isLoading ? (
            <LinearProgress aria-label="이동 반영 중" sx={{ mb: 1.5 }} />
          ) : null}

          {active.isLoading ? <Skeleton kind="section" /> : null}
          {active.isError ? <ErrorState layout="region" error={active.error} onRetry={active.refetch} /> : null}

          {tab === TAB_BOARD && board.data ? (
            boardEmpty ? (
              filtersActive
                ? emptyByFilter("조건에 맞는 티켓이 없습니다.", "필터를 지우면 이 회차의 티켓을 전부 볼 수 있습니다.")
                : mine ? emptyByMine : (
                  <EmptyState
                    title={
                      sprint && sprint.state === "planned"
                        ? "아직 담긴 티켓이 없습니다."
                        : sprintId
                          ? "남은 일이 없습니다."
                          : "보여 줄 티켓이 없습니다."
                    }
                    help={
                      sprint && sprint.state === "planned"
                        ? "백로그 탭에서 이 회차에 담을 일을 고릅니다."
                        : !showAll ? "완료와 취소를 포함해 보면 있을 수 있습니다." : undefined
                    }
                    action={
                      sprint && sprint.state === "planned"
                        ? <Button variant="secondary" onClick={() => setState({ tab: TAB_BACKLOG })}>백로그 보기</Button>
                        : !showAll
                          ? <Button variant="secondary" onClick={() => setState({ all: true })}>완료와 취소 보기</Button>
                          : undefined
                    }
                  />
                )
            ) : (
              <Box>
                <DragBoard
                  columns={columns}
                  labelOf={labelOf}
                  overlay={dragOverlay}
                  onMove={handleBoardMove}
                  // 닫힌 회차의 판은 기록이다 — 끌 수 없다(서버도 422 로 막는다).
                  disabled={moveBusy || (!!sprint && sprint.state === "closed")}
                  columnMaxHeight={COLUMN_BODY_MAX}
                  virtualize={{
                    estimateSize: 160, overscan: 4, rowGap: 8,
                    // 열마다 스크롤 자리를 기억한다 — 회차와 열이 열쇠다(D-483).
                    scrollKeyPrefix: `board:${sprintId || "execution"}`,
                  }}
                >
                  {(card) => (
                    <DragItem key={card.id} id={card.id} label={labelOf(card.id)}>
                      <TicketFace
                        card={card}
                        onClick={peek.open}
                        signals={signalsOf(card)}
                        showProject={!singleProject}
                        actions={cardActions(card)}
                      />
                    </DragItem>
                  )}
                </DragBoard>
              </Box>
            )
          ) : null}

          {tab === TAB_BACKLOG && backlogPages.length ? (
            backlogRows.length === 0 ? (
              filtersActive
                ? emptyByFilter("조건에 맞는 백로그 티켓이 없습니다.", "필터를 지우면 이 팀의 백로그를 전부 볼 수 있습니다.")
                : mine ? emptyByMine : (
                  <EmptyState
                    title="백로그가 비어 있습니다."
                    help="이 팀 프로젝트의 티켓 중 어느 회차에도 담기지 않은 일이 여기 보입니다."
                    action={<Button variant="secondary" component={RouterLink} to={"/new-ticket?" + qs({ team: teamId, project: singleProject })}>티켓 추가</Button>}
                  />
                )
            ) : (
              <Box sx={{ ...LANE_SURFACE, overflow: "hidden" }}>
                <Box sx={{ overflowX: "auto" }}>
                  <Box sx={{ minWidth: { xs: 0, md: BACKLOG_MIN_WIDTH } }}>
                    <BacklogHead
                      columns={backlogColumns}
                      sort={ticketSortOf(backlogSort)}
                      onSort={(key) => setState(nextTicketSort(backlogSort, key))}
                      filters={state}
                      onFilter={(field, next) => setState(applyColumnFilter(field, next))}
                      filterOptions={headFilterOptions}
                      entityOptions={headEntityOptions}
                    />
                    <SortableList
                      items={backlogRows}
                      labelOf={labelOf}
                      overlay={dragOverlay}
                      onReorder={handleBacklogReorder}
                      // 정렬해서 보는 동안에는 끌 수 없다 — 놓은 자리가 끌어 옮긴 순서의 어디인지 알 수 없다.
                      disabled={moveBusy || backlogSorted}
                      virtualize={{
                        estimateSize: 56, rowGap: 6, height: "60vh", ariaLabel: "백로그 목록",
                        sx: { scrollbarGutter: "stable" },
                        // 정렬마다 다른 목록이다 — 스크롤 자리도 따로 기억한다.
                        scrollKey: `backlog:${teamId}:${backlogSort.sort}:${backlogSort.order}`,
                        onEndReached: () => {
                          if (backlog.hasNextPage && !backlog.isFetchingNextPage) backlog.fetchNextPage();
                        },
                      }}
                    >
                      {(card) => (
                        <DragItem key={card.id} id={card.id} label={labelOf(card.id)}>
                          <BacklogRow
                            card={card}
                            onOpen={peek.open}
                            signals={signalsOf(card)}
                            onAddToSprint={addToSprint}
                            /* 담기는 편성이다 — 편성할 수 있는 사람이 열린(팀이 정해진) 회차를
                               골랐을 때만. 백로그의 티켓은 전부 이 팀의 것이라 프로젝트를
                               다시 견주지 않는다. 서버 검증은 그대로 정본이다. */
                            canAdd={canPlan && sprintOpen && !!(sprint && sprint.department_id)}
                            busy={moveBusy}
                            adding={addingId === card.id}
                            onQuickEdit={(c) => setEditing(asTicket(c))}
                            onMoveToTop={(c) => movePosition(c, "top")}
                            onMoveToBottom={(c) => movePosition(c, "bottom")}
                            sorted={backlogSorted}
                          />
                        </DragItem>
                      )}
                    </SortableList>
                  </Box>
                </Box>
                <ListFooter
                  total={backlogTotal} loaded={backlogRows.length}
                  hasNext={backlog.hasNextPage} isFetchingNext={backlog.isFetchingNextPage}
                  onMore={() => backlog.fetchNextPage()}
                  autoMaxRows={0}
                  moreLabel="백로그 더 보기"
                />
              </Box>
            )
          ) : null}
        </>
      ) : null}

      <FormModal
        open={sprintFormOpen}
        title="새 회차"
        submitLabel="추가"
        // 프로젝트 칸이 없다(sprint-fields.js 의 이유). 어느 팀의 회차인지는 이름 칸 아래
        // 한 줄이 말하고, 팀 자체는 이 화면이 이미 골라 둔 값이다.
        fields={sprintFields({ teamLabel })}
        initial={{}}
        onSubmit={(values) =>
          createSprint.mutateAsync({
            name: values.name,
            starts_on: values.starts_on,
            ends_on: values.ends_on,
            department_id: teamId,
            goal: values.goal || null,
          })
        }
        onClose={() => setSprintFormOpen(false)}
      />

      {/* 빠른 수정은 **목록이 이미 쓰는 부품**이다. */}
      <TicketEditModal
        ticket={editing}
        open={!!editing}
        projectScope={editing && editing.sprint_id ? projectScope : null}
        onClose={() => setEditing(null)}
      />

      {/* 티켓 미리보기 — 이 화면을 떠나지 않고 티켓 하나를 확인한다(D-483). */}
      <TicketPeek
        pageId={peek.pageId}
        onClose={peek.close}
        onDetail={peek.detail}
        from="/work-board"
        sprints={sprintRows}
        actions={peekActions}
        projectScope={projectScope}
      />
    </>
  );
}
