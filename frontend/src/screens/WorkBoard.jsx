import React from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListFooter } from "../ui/InfiniteScroll.jsx";
import { useNavigate, Link as RouterLink } from "react-router-dom";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
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
  statusKind,
  useToast,
} from "../ui/kit.jsx";
import { FilterActions, FilterRow, FilterSurface, ToolbarRow } from "../ui/FilterBar.jsx";
import { DragBoard, DragItem, SortableList } from "../ui/DragDrop.jsx";
import { DepartmentFilter, EntityCombobox, FilterSelect, SearchBox } from "../ui/filters.jsx";
import { SprintLifecycle, sprintStateLabel } from "./SprintLifecycle.jsx";
import { useListMemory } from "../lib/listReturn.js";
import { priorityKind, priorityKo } from "../lib/priority.js";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { MODERATOR_ROLES, hasRole } from "../lib/roles.js";
import { useAuth } from "../app/auth.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { sprintFields } from "./sprint-fields.js";
import { TicketEditModal } from "./MyTickets.jsx";
import { useAssigneeOptions, useTicketMeta, useTicketProjects } from "./ticket-options.js";
import { SIGNALS, SIGNAL_ORDER, useTicketSignals } from "../lib/ticketSignals.js";
import { TicketSignals } from "../ui/TicketSignals.jsx";
import { TicketFace, TicketPeople } from "../ui/TicketFace.jsx";
import { StatusKpiStrip } from "../ui/StatusKpi.jsx";
import { LANE_SURFACE } from "../ui/density.js";
import { useQueryState } from "../lib/useQueryState.js";
import { pickOpenSprint } from "./sprint-charts.js";

/* 작업 보드 — 칸반과 백로그 (S6 · 지시 5 · REAUDIT §8).
 *
 * ## 두 화면이 아니라 두 탭인 이유
 *
 * 같은 티켓을 다른 질문으로 본다. 칸반은 "지금 무엇이 어디까지 왔는가", 백로그는 "다음에
 * 무엇을 하는가" 다. 화면을 나누면 카드를 옮긴 뒤 다른 주소로 이동해 순서를 정하게 되고,
 * 그 사이에 사람은 자기가 방금 무엇을 옮겼는지 잊는다.
 *
 * ## 백로그는 상태가 아니라 자리다 (D-349)
 *
 * 「백로그」라는 진행 상태는 없다. 어느 회차에도 안 담긴 티켓이 백로그다 —
 * `sprint_id IS NULL` 한 줄이 그 정의이고, 편입은 상태를 손으로 바꾸는 것이 아니라
 * 「스프린트에 담기」라는 **명시적 동작**이다.
 *
 * ## 신호는 카드를 옮기지 않는다
 *
 * 차단·지연·이슈는 진행 상태와 **직교하는 축**이다. 차단된 진행 중 티켓은 진행 중 열에
 * 그대로 서고 카드가 표식을 단다. 신호를 열로 만들면 「지금 무엇이 진행 중인가」에
 * 답이 둘이 되고, 차단이 풀린 뒤 어느 열로 돌려놓아야 하는지 아무도 모른다.
 *
 * ## 낙관적 갱신을 하지 않는다
 *
 * 카드를 먼저 옮겨 두면 화면은 빨라 보이지만, 서버가 409(다른 사람이 먼저 옮김)로 거절할 때
 * 되돌려야 한다. 그 되돌림이 반쯤 되면 사용자는 자기 화면이 진실인지 알 수 없게 된다 —
 * 그리고 이 화면의 이동은 **상태 변경**이라 되돌림이 조용히 실패하면 남의 일이 사라진다.
 * 그래서 서버가 답한 뒤 목록을 다시 읽는다.
 *
 * ## 버전을 함께 보낸다
 *
 * 카드마다 `version` 을 싣고 이동할 때 그대로 돌려보낸다. 두 사람이 같은 판을 열어 두고
 * 같은 카드를 옮기면 나중 사람이 앞사람의 이동을 덮어쓰는데, **둘 다 성공한 것처럼 보인다.**
 *
 * ## 범위(scope)와 쪽(page) — REAUDIT §8
 *
 * 회차 미선택 기본은 **실행 중인 업무만**(`execution`, 완료·취소 제외)이다 — 전체
 * 1,148건을 기본 칸반에 그리던 fallback 을 없앴다(A1). 진입 시 오늘에 걸린 활성 회차가
 * 있으면 자동으로 고른다. 열·백로그는 서버가 **커서**로 쪽을 낸다 — 「앞의 200건만
 * 보여 줍니다」로 끝내지 않는다. 이 화면은 첫 쪽을 그리고, 열 머리의 「더 보기」와 백로그
 * 아래의 「더 보기」가 다음 쪽을 **같은 조건으로** 요청한다(`app/work/service.py`
 * `_board_scope_stmt`/`_backlog_scope_stmt`). */

const TAB_BOARD = "board";
const TAB_BACKLOG = "backlog";

/* 🔴 **조건은 전부 주소에 있다.**
 *
 * 예전에는 이 셋만 주소에 있었고 담당자·검색·우선순위·난이도·스위치 넷은 `useState` 였다.
 * 탭을 옮길 때는 살아 있었지만(같은 컴포넌트의 리렌더라서) 새로고침·뒤로가기·링크 공유에서
 * 전부 풀렸다 — `useQueryState` 의 첫 문단이 바로 그 증상을 없애려고 그 훅을 만들었다고
 * 적고 있는데, 이 화면만 절반을 안 옮겨 두었다. */
const BOARD_SPEC = {
  tab: TAB_BOARD,
  project: "",
  sprint: "",
  dept: "",
  assignee: "",
  mine: false,
  q: "",
  priority: "",
  difficulty: "",
  // 차단·지연·이슈 중 하나. 예전 「차단과 이슈만」 스위치 하나는 지연만 보는 길을 안 줬다.
  signal: "",
  hold: false,
  all: false,
};

/** 신호 어휘는 `lib/ticketSignals.js` 한 곳이다 — 이름도 색도.
 *
 * 🔴 예전에는 이 파일이 이름 표를 **다시 적었고**, 그래서 아래 KPI 타일이 지연을 빨강,
 * 이슈를 주황으로 칠했다. 목록의 신호 표시는 같은 티켓을 각각 주황·보라로 칠하고 있었다 —
 * 한 화면 안에서 같은 신호가 두 색이었다. 어휘가 두 벌이면 한쪽만 고쳐진다. */
const SIGNAL_TILE_KEYS = SIGNAL_ORDER;

/** 판이 어디까지 자랄 수 있는가. 칸 **안에서만** 굴러가고 페이지는 안 밀린다(지시 5).
 *
 * 화면 높이에서 머리말·탐색 줄·요약 줄이 쓰는 만큼을 뺀 값이다. 픽셀이 아니라 `vh` 인
 * 이유는 4K 에서도 같은 비율로 자라야 하기 때문이다 — 고정 픽셀을 적으면 큰 화면에서
 * 판이 화면 절반만 쓰고 아래가 비어 있다. */
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
 * 그것을 포기하고 표를 얻는 거래는 안 한다. 대신 열 이름을 머리줄에 적어 표처럼 읽힌다.
 *
 * 열 폭은 **머리와 줄이 같은 트랙**이다. 어느 트랙도 `auto` 가 아니다 — 마지막을 `auto` 로
 * 두면 머리의 빈 칸은 0 이고 줄의 단추 네 개는 14rem 을 먹어, 우선순위·난이도·예상·마감·
 * 담당자가 한 칸씩 밀린다. 늘어나는 트랙은 제목 하나뿐이다(아래 `BACKLOG_COLUMNS`). */

/* 백로그 줄의 열을 **한 자리**에서 적는다.
 *
 * 머리줄의 이름, 격자 트랙, 그리고 「줄어들 바닥」이 같은 목록에서 나와야 한쪽만 고쳐지는
 * 일이 없다. 예전에는 이름이 `BacklogHead` 안의 배열이고 폭은 문자열 하나라, 열을 하나
 * 더하면 두 곳을 같이 고쳐야 했다.
 *
 * 🔴 제목이 **남는 폭을 먹는다**(`1fr`). 예전 `minmax(14rem, 26rem)` 은 26rem 에서 멈췄고,
 * 그보다 넓은 화면에서는 줄의 오른쪽이 통째로 빈 채 남았다 — 실측(2026-09-01 · light):
 * 1920 에서 494px, 2560 에서 955px, 3840 에서 1608px 이 죽은 자리였다. 단추가 줄 가운데서
 * 끝나고 그 뒤로 흰 판만 이어지는 그림이다. 표(`DataTable`)의 `title` 열이 이미 같은
 * 규칙이라, 이렇게 해야 두 화면이 같은 모양으로 선다. */
const BACKLOG_COLUMNS = [
  { label: "티켓", rem: 14, grows: true },
  { label: "우선순위", rem: 6.5 },
  { label: "난이도", rem: 5.5 },
  { label: "예상", rem: 5 },
  { label: "마감", rem: 7.5 },
  { label: "담당자", rem: 9 },
  { label: "작업", rem: 10 },
];

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

/* 백로그가 줄어들 수 있는 **바닥 폭** — 모든 열이 자기 폭을 지킬 때의 줄 폭.
 *
 * 표의 `tableMinWidth`(`ui/columnTypes.js`)와 같은 뜻이고 같은 이유로 필요하다. 이 판은
 * `overflow: hidden` 이라, 칸이 이 폭보다 좁으면 트랙이 그대로 밖으로 나가 「작업」 열이
 * 소리 없이 잘렸다. 바닥 아래로는 줄이지 않고 **가로로 민다.** */
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

function BacklogHead() {
  const cells = BACKLOG_COLUMNS.map((c) => c.label);
  return (
    <Box
      sx={{
        ...BACKLOG_GRID,
        px: 1.25,
        py: 0.5,
        display: { xs: "none", md: "grid" },
        /* 목록 스크롤바와 같은 자리를 비워 머리·줄 열이 같은 선에 선다. */
        scrollbarGutter: "stable",
      }}
    >
      {cells.map((c, i) => (
        <Typography
          key={c || `spacer-${i}`}
          variant="caption"
          color="text.secondary"
          /* 머리는 가운데다(지시 8). 제목만 왼쪽이다 — 글이기 때문이다. */
          sx={{ textAlign: i === 0 ? "start" : "center" }}
        >
          {c}
        </Typography>
      ))}
    </Box>
  );
}

function BacklogRow({ card, onOpen, signals, onAddToSprint, canAdd, onQuickEdit, onMoveToTop, onMoveToBottom }) {
  return (
    <Card sx={{ ...BACKLOG_GRID, p: 1.25, cursor: "pointer" }} onClick={() => onOpen(card)}>
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
        ) : null}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
        {card.difficulty || "-"}
      </Typography>
      {/* 숫자도 가운데다(지시 8). 자릿수 정렬은 `tabular-nums` 가 지킨다. */}
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
      <Box
        sx={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 0.5 }}
        onClick={(e) => e.stopPropagation()}
      >
        {canAdd ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onAddToSprint(card)}
          >
            스프린트에 담기
          </Button>
        ) : null}
        <OverflowMenu
          size="sm"
          ariaLabel={`${cardKey(card)} 백로그 작업`}
          items={[
            { label: "빠른 수정", onClick: () => onQuickEdit(card) },
            { label: "맨 위로", onClick: () => onMoveToTop(card) },
            { label: "맨 아래로", onClick: () => onMoveToBottom(card) },
          ]}
        />
      </Box>
    </Card>
  );
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

export function WorkBoard() {
  const navigate = useNavigate();
  // `useAuth()` 는 react-query 결과 객체다 — `data` 안에 사용자가 있다.
  const auth = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  useListMemory("/work-board");
  const [state, setState] = useQueryState(BOARD_SPEC);
  const tab = state.tab === TAB_BACKLOG ? TAB_BACKLOG : TAB_BOARD;
  const projectId = state.project;
  const sprintId = state.sprint;
  const deptId = state.dept;
  const assigneeId = state.assignee;
  const mine = state.mine;
  const signal = state.signal;
  const showHold = state.hold;
  /* §8.1 — 완료·취소까지 보는 토글.
   *
   * 🔴 예전에는 **회차를 골랐을 때 이 토글이 사라졌다.** 「회차 안에서는 그 회차의 전체
   * 이력이 이미 다 보인다」가 이유였는데, 그것이 바로 사용자가 「끝난 일이 보드에서 안
   * 빠진다」고 말한 상태다 — 3주짜리 회차의 완료 열이 계속 자라고 그 옆에서 남은 일을
   * 찾아야 했다. 이제 회차 안에서도 접을 수 있고, **회차 안의 기본값은 접힘**이다.
   * 회의에서 보는 것은 남은 일이다. */
  const showAll = state.all;
  const query = state.q;
  const priority = state.priority;
  const difficulty = state.difficulty;
  const [sprintFormOpen, setSprintFormOpen] = React.useState(false);
  const [editing, setEditing] = React.useState(null);
  // 열 하나가 첫 쪽 위에 받아 온 다음 쪽들. `{ [statusKey]: { cards, nextCursor, loading } }`
  const [colExtra, setColExtra] = React.useState({});

  const signalsOf = useTicketSignals();

  // `enabled` 를 안 주면 이 질의는 아예 안 돈다(ticket-options.js) — 프로젝트 선택기가
  // 늘 비어 보이고, 그 화면은 오류를 내지 않는다.
  const projects = useTicketProjects(true);
  const meta = useTicketMeta(true);
  // 후보는 **그 프로젝트에 닿을 수 있는 사람**으로 서버가 좁혀 준다. 프로젝트를 안 골랐으면
  // 전체 명부다 — 판이 여러 프로젝트를 함께 보여 주는 자리이기 때문이다.
  const assignees = useAssigneeOptions(true, projectId);
  const sprints = useQuery({
    queryKey: ["work-sprints", projectId],
    queryFn: () => api("/api/work/sprints?" + qs({ project_id: projectId })),
  });
  const sprintRows = (sprints.data && sprints.data.sprints) || [];

  // §8.3 — 진입 시 오늘에 걸린 활성 회차가 있으면 자동으로 고른다. 한 번만 한다 — 사용자가
  // 그 뒤 직접 회차를 비우면(「전체」로 되돌리면) 자동 선택이 다시 덮어쓰지 않는다.
  // 🔴 주소에 이미 회차가 실려 들어온 진입(딥링크)도 「이미 골랐다」다 — 여기서 ref 를
  // 안 세우면, 나중에 사용자가 비운 선택이 회차 목록의 신원이 바뀌는 순간 되살아난다.
  const autoSelectedRef = React.useRef(!!state.sprint);
  // 판 질의는 회차 선택이 **정리된 뒤에** 연다. 예전에는 진입 즉시 회차 없는 질의(전
  // 회차 최대 비용)를 한 번 쏘고, 자동 선택이 끝나면 같은 판을 두 번째로 읽었다.
  const [sprintSettled, setSprintSettled] = React.useState(!!state.sprint);
  React.useEffect(() => {
    if (!sprints.isSuccess && !sprints.isError) return;
    if (!autoSelectedRef.current && !sprintId && sprints.isSuccess) {
      autoSelectedRef.current = true;
      const picked = pickOpenSprint(sprintRows);
      if (picked) {
        // 주소가 바뀐 다음 렌더에서 이 이펙트가 다시 돌아 settled 를 켠다 — 그래야
        // 판 질의가 처음부터 회차를 실은 채 정확히 한 번 나간다.
        setState({ sprint: picked.id }, { replace: true });
        return;
      }
    }
    setSprintSettled(true);
  }, [sprints.isSuccess, sprints.isError, sprintId, sprintRows, setState]);

  // §8.1 — scope. 「완료와 취소 보기」를 켜면 all, 아니면 execution 이다. 회차를 골랐든
  // 안 골랐든 같은 규칙이다 — 규칙이 문맥마다 다르면 사용자가 그 차이를 배워야 한다.
  const scope = showAll ? "all" : "execution";

  /* 판과 백로그가 **같은 축으로 좁힌다**. 예전에는 검색·우선순위·난이도가 백로그 탭에만
     있었고 서버의 `/board` 는 그 이름을 받지도 않았다 — 백로그에서 검색어를 넣고 칸반으로
     옮기면 조건이 조용히 사라졌다. 지금은 한 벌이고, 서버도 한 절을 공유한다. */
  const shared = {
    project_id: projectId,
    department_id: deptId,
    assignee_user_id: mine ? "" : assigneeId,
    mine,
    q: query,
    priority,
    difficulty,
    signal,
  };
  const sharedKey = [projectId, deptId, assigneeId, mine, query, priority, difficulty, signal];
  const boardKey = [...sharedKey, sprintId, scope];
  const board = useQuery({
    queryKey: ["work-board", ...boardKey],
    queryFn: () =>
      api(
        "/api/work/board?" +
          qs({
            ...shared,
            sprint_id: sprintId,
            scope,
            column_page_size: COLUMN_PAGE_SIZE,
          })
      ),
    enabled: tab === TAB_BOARD && sprintSettled,
  });

  // 필터가 바뀌면 다음 쪽으로 받아 둔 것도 함께 비운다 — 안 그러면 옛 조건의 카드가
  // 새 조건의 열 아래에 그대로 남는다. (직렬화는 원시값 배열의 join 이면 충분하다 —
  // JSON.stringify 를 의존성 자리에서 매 렌더 부를 이유가 없다.)
  const boardKeyStr = boardKey.join("\u001f");
  React.useEffect(() => { setColExtra({}); }, [boardKeyStr]);

  const backlogKey = sharedKey;
  const backlog = useInfiniteQuery({
    queryKey: ["work-backlog", ...backlogKey],
    queryFn: ({ pageParam }) =>
      api(
        "/api/work/backlog?" +
          qs({
            ...shared,
            cursor: pageParam || "",
            limit: BACKLOG_PAGE_SIZE,
          })
      ),
    initialPageParam: null,
    getNextPageParam: (lastPage) => lastPage.next_cursor || undefined,
    enabled: tab === TAB_BACKLOG,
  });

  const createSprint = useMutation({
    mutationFn: (body) => api("/api/work/sprints", { method: "POST", body }),
    onSuccess: (sprint) => {
      qc.invalidateQueries({ queryKey: ["work-sprints"] });
      setSprintFormOpen(false);
      // 만든 회차를 바로 고른다. 안 고르면 「만들었는데 아무 일도 안 일어난」 것으로
      // 보인다. 프로젝트 필터도 그 회차의 것으로 함께 옮긴다 — 폼에서 다른 프로젝트를
      // 골랐을 때 지금 판이 그 회차를 안 보여 주는 어긋남을 없앤다.
      setState({ project: sprint.project_id || "", sprint: sprint.id });
      toast("스프린트를 만들었습니다.", "success");
    },
    onError: (e) =>
      toast((e && e.message) || "스프린트를 만들지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const move = useMutation({
    mutationFn: ({ id, body }) =>
      api(`/api/work/board/${encodeURIComponent(id)}/move`, { method: "POST", body }),
    onSuccess: () => {
      // 「더 보기」로 받아 둔 확장분을 접는다 — 첫 쪽만 재조회되므로, 남겨 두면 옮긴
      // 카드가 옛 열의 확장분과 새 열의 첫 쪽에 **동시에** 서고 dnd 등록 id 가 겹친다.
      setColExtra({});
      qc.invalidateQueries({ queryKey: ["work-board"] });
      qc.invalidateQueries({ queryKey: ["work-backlog"] });
      // 상태가 바뀌면 티켓 목록·홈·스프린트가 함께 낡는다. 어떤 키가 티켓을 그리는지는
      // `ticket-views.js` 한 곳이 안다.
      invalidateTicketViews(qc, { refetchType: "all" });
    },
    onError: (e) =>
      toast((e && e.message) || "옮기지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const openTicket = React.useCallback(
    (card) => {
      if (card.page_id) navigate(`/tickets/${encodeURIComponent(card.page_id)}`);
    },
    [navigate]
  );

  /* 판의 카드를 편집 모달이 아는 모양으로 편다.
   *
   * 모달의 `id` 는 상세 주소의 키(`page_id`)이고, `category` 는 **사람이 적는 분류**다 —
   * 판이 주는 상태 갈래(`status_category`)와 이름이 겹쳤던 자리라 여기서 섞지 않는다. */
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
    }),
    []
  );

  /* 열 하나의 다음 쪽 — **첫 쪽과 같은 조건**으로(§8.5 · `app/work/router.py` 의 계약).
     🔴 예전에는 이 함수가 검색·부서·우선순위·난이도·신호를 빼먹고(게다가 선언된 적 없는
     변수를 참조해 누르는 즉시 ReferenceError 였다), 조건이 어긋나면 이 쪽에서 다른 카드가
     새거나 겹쳤다. `shared` 를 그대로 실어 첫 쪽 질의와 한 벌을 유지한다. */
  const loadMoreColumn = React.useCallback(
    async (statusKey, cursor) => {
      setColExtra((prev) => ({
        ...prev, [statusKey]: { ...(prev[statusKey] || EMPTY_EXTRA), loading: true },
      }));
      try {
        const body = await api(
          `/api/work/board/columns/${encodeURIComponent(statusKey)}?` +
            qs({ ...shared, sprint_id: sprintId, scope, cursor, limit: COLUMN_PAGE_SIZE })
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
    // `shared` 객체는 렌더마다 새로 만들어지지만 내용은 이 원시값들이 정한다 — 값이 같으면
    // 옛 클로저의 `shared` 도 같은 내용이라 재생성할 이유가 없다. 목록은 `shared` 의
    // 전 축 + sprint_id + scope 다 — 축을 더하는 날 여기도 함께 는다.
    [projectId, deptId, assigneeId, mine, query, priority, difficulty, signal, sprintId, scope, toast]
  );

  /* 열은 서버가 정한 **자리**로 고른다(`placement`). 화면이 상태 이름을 적어 열을 고르면
     어휘가 바뀐 날 이 화면만 옛 목록으로 남고, 그 어긋남은 아무 오류도 안 낸다.
     첫 쪽(board.data) 위에 `colExtra` 로 받아 둔 다음 쪽들을 얹는다. */
  const columns = React.useMemo(() => {
    const data = board.data;
    if (!data) return [];
    const wanted = [PLACE_COLUMN];
    if (showHold) wanted.push(PLACE_COLLAPSED);
    if (showAll) wanted.push(PLACE_HIDDEN);
    /* 첫 쪽과 확장분을 id 로 겹침 없이 합친다 — 이동·재조회 뒤 첫 쪽이 바뀌면 확장분과
       같은 카드가 겹칠 수 있고, 겹친 카드는 dnd 등록 id 충돌로 드래그 출발지를 흐린다. */
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
          // 「N건 중 M건」— 잘랐다는 사실이 아니라 지금까지 받은 양을 말한다(§8.5).
          hint: c.total > items.length ? `${c.total}건 중 ${items.length}건을 받았습니다.` : null,
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
              to={"/new-ticket?" + qs({
                project: projectId,
                sprint: tab === TAB_BOARD ? sprintId : "",
                status: c.key,
              })}
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
      // 어휘 밖 상태. **버리지 않는다** — 안 보이는 티켓은 아무도 못 고친다.
      cols.push({
        id: UNCLASSIFIED,
        title: "분류되지 않음",
        count: data.unclassified_total,
        items,
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
  }, [board.data, showHold, showAll, colExtra, projectId, sprintId, tab, loadMoreColumn]);

  // 매 렌더 새 배열을 만들면 아래 cardById → labelOf → DnD 안내문까지 memo 가 연쇄로
  // 무효가 된다 — 응답이 그대로면 행 배열도 그대로여야 한다(`|| []` 도 매번 새 배열이다).
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
        // 판에서 끌었다 — 순서는 `board_rank` 에 적힌다. 이 한 칸을 안 보내면 판에서
        // 옮긴 것이 백로그 순서를 함께 흐트러뜨린다.
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
     `position_*` 로 다시 실어, 서버가 카드를 안 끌어오고도 목표 순위를 잰다. */
  function movePosition(card, position) {
    move.mutate({
      id: card.id,
      body: {
        reorder: true, base_version: card.version,
        to_position: position,
        position_project_id: projectId || null,
        position_q: query || null,
        position_assignee_user_id: mine ? null : (assigneeId || null),
        position_mine: mine,
        position_priority: priority || null,
        position_difficulty: difficulty || null,
        position_department_id: deptId || null,
        position_signal: signal || null,
      },
    });
  }

  function addToSprint(card) {
    if (!sprintId) {
      toast("먼저 담을 스프린트를 고르세요.", "warn");
      return;
    }
    move.mutate({
      id: card.id,
      body: { sprint_id: sprintId, set_sprint: true, base_version: card.version },
    });
  }

  const canPlanSprint = hasRole(MODERATOR_ROLES, auth.data && auth.data.role);
  const active = tab === TAB_BOARD ? board : backlog;
  const summary = (board.data && board.data.summary) || null;
  const projectRows = (projects.data && projects.data.projects) || [];
  const assigneeRows = (assignees.data && assignees.data.assignees) || [];
  const metaBody = meta.data || {};
  // 부서 후보는 **서버가 동봉한다**(`departments: {selected, options}`). 화면이 스스로
  // 조직도를 훑어 만들면 서버가 좁힌 범위와 갈라진다.
  const departments =
    (board.data && board.data.departments) || (backlogPages[0] && backlogPages[0].departments) || null;
  const sprint = sprintRows.find((s) => s.id === sprintId) || null;

  /* 판독 줄 — **자르기 전에 센** 값이다(`app/work/service.py::board`). 열의 카드를 더해
     세면 잘린 열에서 조용히 틀린다. */
  /* 상태 판독을 누르면 **그 열로 데려간다**. 열 이름이 아니라 열쇠로 찾는다 —
     이름은 어휘가 바뀌면 달라지지만 열쇠는 서버가 준 값 그대로다. */
  const scrollToColumn = React.useCallback((key) => {
    const el = document.querySelector(`[data-col-key="${CSS.escape(String(key))}"]`);
    if (el && el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, []);

  const statusTiles = summary
    ? (board.data.columns || []).map((c) => {
        const n = (summary.by_status || {})[c.key] ?? 0;
        return {
          key: c.key,
          label: c.label,
          value: String(n),
          kind: statusKind(c.key) !== "neutral" ? statusKind(c.key) : statusKind(c.label),
          pct: summary.total ? Math.round((n / summary.total) * 100) : 0,
          onClick: n ? () => scrollToColumn(c.key) : undefined,
        };
      })
    : [];
  /* 이름도 색도 공용 표에서 온다 — 이 타일과 목록의 신호 표시가 **같은 티켓을 같은 색**으로
     칠한다. 셋이 서로 다른 색인 이유는 어휘 표에 적혀 있다(빨강=지금 막힘, 주황=시간이 지남,
     보라=알고 있어야 함). */
  const signalTiles = summary
    ? SIGNAL_TILE_KEYS.map((k) => ({
      key: k,
      label: SIGNALS[k].label,
      value: String(summary.signals[k]),
      kind: SIGNALS[k].tone,
    }))
    : [];

  /* 「티켓 추가」가 데려가는 곳. 회차 맥락은 **판 탭에서만** 싣는다 — 백로그 탭에서 만든
     티켓이 회차로 들어가면 그 탭의 뜻(아직 안 담은 일)과 어긋난다. */
  const newTicketQuery = qs({
    project: projectId,
    sprint: tab === TAB_BOARD ? sprintId : "",
  });
  const newTicketPath = "/new-ticket" + (newTicketQuery ? `?${newTicketQuery}` : "");

  const boardEmpty = columns.every((c) => c.items.length === 0);

  /* 판 위의 한 줄 — **지금 어디쯤인가와 다음에 할 일**.
   *
   * 흐름은 넷이다: 회차를 안 골랐다 · 아직 안 열었다 · 진행 중이다 · 끝났다.
   * 각 자리에서 사람이 할 일이 다르고, 그것을 화면이 말하지 않으면 「이 화면을 어떻게
   * 쓰는지 모르겠다」가 된다. */
  const boardNotice = (() => {
    if (!sprintId) {
      const scopeLine = showAll
        ? "완료와 취소를 포함한 전체 티켓을 보여 줍니다."
        : "실행 중인 업무만 보여 줍니다.";
      // 자동 선택이 비켜 간 이유를 말한다 — 회차가 있는데 열린 것이 없으면, 사람이
      // 지난 회차를 고르거나 새 회차를 여는 것이 다음 행동이다.
      const noneOpen =
        sprintRows.length > 0 && !sprintRows.some((s) => s && (s.active || s.state === "active"));
      if (noneOpen) {
        return {
          title: "진행 중인 회차가 없습니다.",
          body: canPlanSprint
            ? `${scopeLine} 위에서 지난 회차를 고르거나 「스프린트 추가」로 새 회차를 만들 수 있습니다.`
            : `${scopeLine} 위 스프린트 칸에서 지난 회차를 골라 볼 수 있습니다.`,
        };
      }
      return {
        title: "회차를 고르지 않았습니다.",
        body: `${scopeLine} 회차를 고르면 그 회차의 일만 봅니다.`,
      };
    }
    const label = sprint ? sprint.name : "이 회차";
    if (sprint && sprint.state === "planned") {
      return {
        title: `${label} (${sprintStateLabel(sprint)})`,
        body: "아직 열지 않은 회차입니다. 백로그에서 할 일을 담고 「회차 열기」를 누르면 오늘부터 진행을 셉니다.",
      };
    }
    if (sprint && sprint.state === "closed") {
      return {
        title: `${label} (${sprintStateLabel(sprint)})`,
        body: "끝난 회차입니다. 안 끝났던 일은 닫을 때 옮긴 곳에 있습니다.",
      };
    }
    return {
      title: `${label} (${sprintStateLabel(sprint) || "진행 중"})`,
      body: showAll
        ? "완료와 취소까지 함께 보여 줍니다. 회의에서는 남은 일만 보는 편이 빠릅니다."
        : "남은 일만 보여 줍니다. 끝난 일은 「완료와 취소 보기」로 펼칩니다.",
    };
  })();

  return (
    <>
      <PageHeader
        area="팀 업무"
        title="작업 보드"
        crumbRoot={null}
        description="팀이 지금 무슨 일을 어디까지 했는지 보고, 다음에 할 일의 순서를 정합니다."
        actions={
          <Stack direction="row" spacing={1} alignItems="center">
            {/* 🔴 **만드는 자리가 기본값을 정한다** (지시 5).
                여기서 만든 티켓은 지금 보고 있는 프로젝트와 회차로 간다 — 회차를 안
                골랐으면 백로그다. 맥락을 안 실어 보내면 만든 사람이 곧바로 「스프린트에
                담기」를 한 번 더 눌러야 하고, 그 한 번을 빠뜨린 티켓은 회의에서 아무도
                못 본다. 회차 id 는 서버가 다시 본다. */}
            <Button variant="secondary" onClick={() => navigate(newTicketPath)}>
              티켓 추가
            </Button>
            {/* 회차의 한 바퀴 — 열고 닫는 자리. 회의 화면과 **같은 부품**을 쓴다. */}
            <SprintLifecycle sprint={sprint} sprints={sprintRows} size="md" />
            {/* 서버가 `PROJECT_WRITE` 로 막는다(`app/work/router.py`). 여기서 감추는
                것은 권한 보장이 아니라 **누를 수 없는 버튼을 안 보여 주는 것**이다 —
                눌러서 403 을 보는 것은 안내가 아니다. */}
            {canPlanSprint ? (
              <Button
                variant={sprintRows.length === 0 ? "primary" : "secondary"}
                onClick={() => setSprintFormOpen(true)}
              >
                스프린트 추가
              </Button>
            ) : null}
          </Stack>
        }
        help="카드를 끌어 상태와 순서를 바꿉니다. 키보드로는 스페이스로 집고 화살표로 옮긴 뒤 스페이스로 놓습니다."
      />

      {/* §8.2 — 판 위에 **지금 어디쯤인가와 다음에 할 일**을 한 줄로 말한다.
          예전에는 회차를 안 골랐을 때만 한 줄이 있었고, 회차를 골랐을 때는 그 회차가
          아직 안 열렸는지 이미 끝났는지 화면이 아무 말도 안 했다 — 사용자가 「어떻게
          쓰는지 모르겠다」고 한 자리가 여기다. */}
      {tab === TAB_BOARD ? (
        <Callout tone="info" sx={{ mb: 1.5 }} title={boardNotice.title}>
          {boardNotice.body}
        </Callout>
      ) : null}

      {/* 탐색 줄의 구조가 프로젝트·티켓과 **같다**(지시 8): 위 줄이 「무엇을 찾는가」,
          아래 줄이 「무엇으로 좁히는가」. 프로젝트와 스프린트가 맨 앞인 이유는 이 화면의
          질문이 언제나 「어느 프로젝트의 이번 회차」로 시작하기 때문이다. */}
      <FilterSurface>
        {/* 🔴 검색은 **두 탭 모두**에 있다. 예전에는 백로그 탭에만 있었고 서버의
            `/board` 는 `q` 를 받지도 않아서, 백로그에서 검색어를 넣고 칸반으로 옮기면
            검색이 조용히 사라졌다. */}
        <ToolbarRow>
          <SearchBox
            value={query}
            onSearch={(v) => setState({ q: v || "" })}
            placeholder="티켓 제목, 이름 검색"
            ariaLabel="티켓 검색"
          />
        </ToolbarRow>
        <FilterRow>
          {/* 프로젝트는 **기수가 무한히 자라는 대상**이라 평범한 드롭다운으로 못 고른다
              (`plain_dropdown_for_entity`). 같은 이유로 담당자도 조합 상자다. */}
          <EntityCombobox
            label="프로젝트"
            value={projectId}
            onChange={(next) => setState({ project: next || "" })}
            loading={projects.isLoading}
            options={projectRows.map((p) => ({ value: p.id, label: p.name }))}
            allLabel="전체"
            sx={{ minWidth: "14rem" }}
          />
          <EntityCombobox
            label="스프린트"
            value={sprintId}
            onChange={(next) => setState({ sprint: next || "" })}
            loading={sprints.isLoading}
            options={sprintRows.map((s) => ({
              value: s.id,
              label: s.active ? `${s.name} (진행 중)` : s.name,
            }))}
            allLabel="전체"
            sx={{ minWidth: "12rem" }}
          />
          {/* 팀(부서) 축. 티켓에는 부서 칸이 없고 티켓의 팀은 프로젝트가 정한다 —
              서버가 그 한 단계를 대신 걷는다(`app/work/router.py::_dept`).
              후보가 둘 미만이면 이 부품이 스스로 안 그린다. */}
          <DepartmentFilter
            departments={departments}
            value={deptId}
            onChange={(next) => setState({ dept: next || "" })}
            sx={{ minWidth: "12rem" }}
          />
          <EntityCombobox
            label="담당자"
            value={assigneeId}
            onChange={(next) => setState({ assignee: next || "" })}
            loading={assignees.isLoading}
            options={assigneeRows.map((a) => ({ value: a.user_id, label: a.display_name }))}
            allLabel="전체"
            disabled={mine}
            sx={{ minWidth: "12rem" }}
          />
          {/* 우선순위·난이도도 두 탭 공통이다 — 같은 티켓을 다른 질문으로 볼 뿐이라
              좁히는 말이 탭마다 다를 이유가 없다. */}
          <FilterSelect
            label="우선순위"
            value={priority}
            onChange={(v) => setState({ priority: v || "" })}
            options={metaBody.priorities || []}
            allLabel="전체"
          />
          <FilterSelect
            label="난이도"
            value={difficulty}
            onChange={(v) => setState({ difficulty: v || "" })}
            options={metaBody.difficulties || []}
            allLabel="전체"
          />
          {/* 신호는 셋 중 하나다. 예전에는 「차단과 이슈만」 스위치 하나였고, 서버에서도
              그 깃발 하나가 차단 **또는** 이슈를 뜻해서 **지연만 보는 길이 없었다.** */}
          <FilterSelect
            label="신호"
            value={signal}
            onChange={(v) => setState({ signal: v || "" })}
            options={SIGNAL_ORDER.map((k) => ({ value: k, label: SIGNALS[k].label }))}
            allLabel="전체"
          />
          <FormControlLabel
            sx={{ m: 0 }}
            control={
              <Switch
                size="small"
                checked={mine}
                onChange={(e) => setState({ mine: e.target.checked })}
              />
            }
            label={<Typography variant="body2">내 티켓만</Typography>}
          />
          <FilterActions>
            {tab === TAB_BOARD ? (
              /* 보류는 기본 판에서 비켜 있다(D-349). 없애는 것이 아니라 **접는 것**이라,
                 펴는 스위치가 늘 여기 있다 — 안 그러면 보류한 일이 어느 화면에도 없어서
                 영영 잊힌다. */
              <Button variant="ghost" size="sm" onClick={() => setState({ hold: !showHold })}>
                {showHold ? "보류 접기" : "보류 펴기"}
              </Button>
            ) : null}
            {/* 🔴 회차를 골랐을 때도 접을 수 있다. 예전에는 이 단추가 사라져서 3주짜리
                회차의 완료 열이 계속 자랐다 — 「끝난 일이 보드에서 안 빠진다」가 그것이다. */}
            <Button variant="ghost" size="sm" onClick={() => setState({ all: !showAll })}>
              {showAll ? "완료와 취소 감추기" : "완료와 취소 보기"}
            </Button>
          </FilterActions>
        </FilterRow>
      </FilterSurface>

      <Tabs value={tab} onChange={(_e, v) => setState({ tab: v })} aria-label="보기 선택" sx={{ mb: 2 }}>
        <Tab value={TAB_BOARD} label="칸반" />
        <Tab value={TAB_BACKLOG} label="백로그" />
      </Tabs>

      {active.isLoading ? <Skeleton kind="section" /> : null}
      {active.isError ? <ErrorState error={active.error} onRetry={active.refetch} /> : null}

      {/* 🔴 판독 줄에 **판을 두르지 않는다.** 타일이 이미 `background.plate` 라서
          바깥 판이 있으면 판 안에 판이 겹친다(사용자: 「카드 안에 또 카드」). */}
      {tab === TAB_BOARD && summary ? (
        <Stack spacing={1.5} sx={{ mb: 2 }}>
          <StatusKpiStrip
            ariaLabel="상태별 티켓 수"
            revealKey="work-board:status-kpi"
            items={[{ label: "전체", value: String(summary.total), primary: true }, ...statusTiles]}
          />
          {/* 신호 타일은 **필터 토글**이다. 숫자를 보고 「그래서 어떤 티켓인데」를
              물을 수 있어야 그 숫자가 뜻이 있다. 같은 칸을 다시 누르면 풀린다.
              셋이 다 0 이면 줄 자체를 안 그린다 — 「신호가 없다」는 상태 줄이 이미
              말하고, 0 짜리 토글 셋은 누를 것이 없는 단추다(신호는 탐색 줄에도 있다). */}
          {signalTiles.some((t) => t.value !== "0") ? (
            <StatusKpiStrip
              ariaLabel="신호별 티켓 수"
              revealKey="work-board:signal-kpi"
              items={signalTiles}
              value={signal}
              onSelect={(key) => setState({ signal: signal === key ? "" : key })}
            />
          ) : null}
        </Stack>
      ) : null}

      {tab === TAB_BOARD && board.data ? (
        boardEmpty ? (
          <EmptyState
            title="보여 줄 티켓이 없습니다."
            help={!sprintId && !showAll ? "완료와 취소를 포함해 보면 있을 수 있습니다." : undefined}
            action={
              !sprintId && !showAll
                ? <Button variant="secondary" onClick={() => setState({ all: true })}>완료와 취소 보기</Button>
                : undefined
            }
          />
        ) : (
          /* 🔴 **바깥 판을 없앴다.** 예전에는 여기 함몰면이 한 겹 더 있었고, 그 안에 칸이
             또 한 겹, 그 위에 카드가 한 겹이라 흰 상자가 세 번 겹쳐 보였다. 칸이 이미
             자기 바탕을 갖고 있으므로 이 겹은 아무 말도 안 하고 여백만 먹었다. */
          <Box>
          <DragBoard
            columns={columns}
            labelOf={labelOf}
            onMove={handleBoardMove}
            columnMaxHeight={COLUMN_BODY_MAX}
            // §15.1 재검수 — 서버가 이미 열마다 커서로 잘라 준 것(§8.5) 위에 렌더링만
            // 가상화한다. 카드 하나(TicketFace)는 배지·신호·담당자 이름까지 있어 백로그 행보다
            // 조금 크다 — 실측 없이 어림한 값이고 실제 높이는 measureElement가 다시 잰다.
            virtualize={{ estimateSize: 156 }}
          >
            {(card) => (
              <DragItem key={card.id} id={card.id} label={labelOf(card.id)}>
                <TicketFace
                  card={card}
                  onClick={openTicket}
                  signals={signalsOf(card)}
                  showProject={!projectId}
                />
              </DragItem>
            )}
          </DragBoard>
          </Box>
        )
      ) : null}

      {tab === TAB_BACKLOG && backlogPages.length ? (
        backlogRows.length === 0 ? (
          <EmptyState title="백로그가 비어 있습니다." />
        ) : (
          <Box sx={{ ...LANE_SURFACE, overflow: "hidden" }}>
            {/* 칸이 바닥보다 좁으면 줄을 짜부라뜨리는 대신 **가로로 민다** — 열을
                눌러 담으면 「작업」이 잘려 단추에 닿을 수 없다. 머리줄과 목록이 같은
                상자 안에 있어야 함께 밀린다: 따로 두면 이름만 제자리에 남아 값이 다른
                열 이름 아래에 선다. */}
            <Box sx={{ overflowX: "auto" }}>
              <Box sx={{ minWidth: { xs: 0, md: BACKLOG_MIN_WIDTH } }}>
                <BacklogHead />
                <SortableList
                  items={backlogRows}
                  labelOf={labelOf}
                  onReorder={handleBacklogReorder}
                  // §15.1 재검수 — 서버 커서 페이징(§8.5, useInfiniteQuery) 위에 렌더링만
                  // 가상화한다. 181행을 한 번에 그리던 자리다. 판 열과 같은 높이(60vh)를
                  // 써서 두 탭이 같은 느낌으로 스크롤한다.
                  virtualize={{
                    estimateSize: 56, height: "60vh", ariaLabel: "백로그 목록",
                    sx: { scrollbarGutter: "stable" },
                  }}
                >
                  {(card) => (
                    <DragItem key={card.id} id={card.id} label={labelOf(card.id)}>
                      <BacklogRow
                        card={card}
                        onOpen={openTicket}
                        signals={signalsOf(card)}
                        onAddToSprint={addToSprint}
                        canAdd={canPlanSprint}
                        onQuickEdit={(c) => setEditing(asTicket(c))}
                        onMoveToTop={(c) => movePosition(c, "top")}
                        onMoveToBottom={(c) => movePosition(c, "bottom")}
                      />
                    </DragItem>
                  )}
                </SortableList>
              </Box>
            </Box>
            {/* 「N건 중 M건」과 「더 보기」— 서버가 실제로 다음 쪽을 내주는 계약(§8.5).
                키보드·스크린리더 사용자는 무한 스크롤에 닿을 수 없어 단추를 함께 둔다.
                이 문구가 이 저장소 목록 전부의 정본이 됐다 — 이제 공용 부품을 쓴다.
                🔴 `root="auto"` 다: 백로그는 **자기 스크롤 창**(60vh 짜리 가상 목록) 안에 있고,
                뷰포트를 기준으로 재면 열자마자 끝까지 받는다. */}
            <ListFooter
              total={backlogTotal} loaded={backlogRows.length}
              hasNext={backlog.hasNextPage} isFetchingNext={backlog.isFetchingNextPage}
              onMore={() => backlog.fetchNextPage()}
              root="auto"
              moreLabel="백로그 더 보기"
            />
          </Box>
        )
      ) : null}

      <FormModal
        open={sprintFormOpen}
        title="새 스프린트"
        submitLabel="만들기"
        // 프로젝트 칸이 폼에 보인다(sprint-fields.js 의 이유). 기본값은 현재 필터이고,
        // 다른 프로젝트를 골라 만들면 onSuccess 가 필터를 그 회차로 옮긴다 — 「만들었는데
        // 판에 안 보인다」가 생기지 않는다.
        fields={sprintFields(projectRows.map((p) => ({ value: p.id, label: p.name })))}
        initial={{ project_id: projectId || "" }}
        onSubmit={(values) =>
          createSprint.mutateAsync({
            name: values.name,
            starts_on: values.starts_on,
            ends_on: values.ends_on,
            project_id: values.project_id || null,
            goal: values.goal || null,
          })
        }
        onClose={() => setSprintFormOpen(false)}
      />

      {/* 빠른 수정은 **목록이 이미 쓰는 부품**이다. 새로 만들면 같은 값을 고치는 자리가
          화면마다 다른 폼이 되고, 어느 한쪽만 새 칸을 얻는 날이 온다. */}
      <TicketEditModal
        ticket={editing}
        open={!!editing}
        onClose={() => setEditing(null)}
      />
    </>
  );
}
