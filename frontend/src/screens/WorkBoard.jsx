import React from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
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
  MetricStrip,
  PageHeader,
  Skeleton,
  useToast,
} from "../ui/kit.jsx";
import { FilterActions, FilterRow, FilterSurface, ToolbarRow } from "../ui/FilterBar.jsx";
import { DragBoard, DragItem, SortableList } from "../ui/DragDrop.jsx";
import { EntityCombobox, FilterSelect, SearchBox } from "../ui/filters.jsx";
import { priorityKind, priorityKo } from "../lib/priority.js";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { MODERATOR_ROLES, hasRole } from "../lib/roles.js";
import { useAuth } from "../app/auth.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { SPRINT_FIELDS } from "./sprint-fields.js";
import { TicketEditModal } from "./MyTickets.jsx";
import { useAssigneeOptions, useTicketMeta, useTicketProjects } from "./ticket-options.js";
import { useTicketSignals } from "../lib/ticketSignals.js";
import { TicketSignals } from "../ui/TicketSignals.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";

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

/** 담당자 얼굴 줄. 셋까지 그리고 나머지는 숫자로 접는다.
 *
 * 카드 한 장의 폭이 정해져 있어서, 여섯 명이 걸린 티켓의 얼굴을 다 그리면 제목이 갈 자리가
 * 없다. 접는 기준을 숫자로 두는 대신 이름을 지우는 선택도 있었지만, 카드에서 사람은
 * **누가 하는가**라 가장 마지막까지 남아야 하는 정보다. */
function AssigneeRow({ card }) {
  const people = Array.isArray(card.assignees) ? card.assignees : [];
  if (!people.length) {
    // 「담당자가 없다」와 「이름을 못 읽었다」는 다른 사실이다. 뒤엣것을 「없음」으로
    // 적으면 미할당 필터가 그 티켓을 안 집는 이유를 아무도 못 찾는다.
    const unresolved = card.assignee_tokens > 0;
    return (
      <Typography variant="caption" color="text.secondary">
        {unresolved ? "담당자를 읽지 못했습니다." : "담당자 없음"}
      </Typography>
    );
  }
  const shown = people.slice(0, 3);
  const rest = people.length - shown.length;
  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.375, minWidth: 0 }}>
      {shown.map((p) => (
        <UserAvatar key={p.user_id || p.display_name} person={p} size="sm" label={p.display_name} />
      ))}
      {rest > 0 ? (
        <Typography variant="caption" color="text.secondary">
          {`외 ${rest}명`}
        </Typography>
      ) : null}
    </Box>
  );
}

/** 판의 카드 한 장.
 *
 * 다섯 줄이 최대다: 이름·우선순위·신호 / 제목 / 프로젝트 / 마감·예상 / 담당자.
 * 여섯째 줄을 더하고 싶어질 때마다 그 정보가 **카드에서 결정에 쓰이는가**를 먼저 묻는다 —
 * 아니면 상세로 간다. */
function TicketCard({ card, onOpen, signals, showProject }) {
  return (
    <Card
      sx={{ p: 1.25, display: "flex", flexDirection: "column", gap: 0.5, cursor: "pointer" }}
      onClick={() => onOpen(card)}
    >
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
          {cardKey(card)}
        </Typography>
        {card.priority ? (
          <Badge value={priorityKo(card.priority)} kind={priorityKind(card.priority)} />
        ) : null}
        {/* 신호는 카드를 옮기지 않는다 — 표식으로만 선다. 좁은 카드라 `mark` 다. */}
        <TicketSignals signals={signals} variant="mark" sx={{ marginInlineStart: "auto" }} />
      </Stack>
      <Typography variant="body2" sx={{ ...KO_WORD_BREAK }}>
        {card.title || "제목 없음"}
      </Typography>
      {/* 프로젝트를 이미 하나로 좁혔으면 카드마다 같은 이름을 적지 않는다. */}
      {showProject && card.project ? (
        <Typography variant="caption" color="text.secondary" sx={{ ...KO_WORD_BREAK }}>
          {card.project}
        </Typography>
      ) : null}
      {card.due || card.est_wd != null ? (
        <Typography variant="caption" color="text.secondary">
          {[card.due ? `마감 ${card.due}` : null, card.est_wd != null ? `예상 ${card.est_wd}WD` : null]
            .filter(Boolean)
            .join("  ")}
        </Typography>
      ) : null}
      <AssigneeRow card={card} />
    </Card>
  );
}

/** 백로그 한 줄. 표처럼 보이지만 표가 아니다 — 끌어서 순서를 바꿀 수 있어야 하기 때문이다.
 *
 * 공용 `DataTable` 은 행을 끌 수 없다. 순서가 이 목록의 **본질**이라(다음에 무엇을 하는가)
 * 그것을 포기하고 표를 얻는 거래는 안 한다. 대신 열 이름을 머리줄에 적어 표처럼 읽힌다. */
const BACKLOG_GRID = {
  display: "grid",
  gridTemplateColumns: {
    xs: "1fr",
    md: "minmax(0, 1fr) 6rem 6rem 5rem 7rem minmax(6rem, 9rem) minmax(0, auto)",
  },
  gap: 1,
  alignItems: "center",
};

function BacklogHead() {
  const cells = ["티켓", "우선순위", "난이도", "예상", "마감", "담당자", ""];
  return (
    <Box
      sx={{
        ...BACKLOG_GRID,
        px: 1.25,
        py: 0.5,
        display: { xs: "none", md: "grid" },
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
        <AssigneeRow card={card} />
      </Box>
      <Box sx={{ display: "flex", justifyContent: "center", gap: 0.5, flexWrap: "wrap" }}>
        {/* 「빠른 수정」이 여기 있는 이유: 백로그를 다듬는 일은 **여러 건을 연달아**
            고치는 일이다(우선순위 셋, 예상 WD 다섯). 건마다 상세로 갔다 돌아오면 그
            사이에 방금 어디까지 봤는지를 잊는다. */}
        <Button
          variant="ghost"
          size="sm"
          onClick={(e) => {
            // 줄 전체가 상세로 가는 자리라, 단추가 그 이동을 막아야 한다.
            e.stopPropagation();
            onQuickEdit(card);
          }}
        >
          빠른 수정
        </Button>
        {/* 화면에 없는 카드 기준 이동(§8.5) — 181행 중 맨 끝으로 보낼 때 그 자리의
            이웃은 아직 안 받아 왔을 수 있다. 끌기 대신 이 둘로 그 자리에 닿는다. */}
        <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onMoveToTop(card); }}>
          맨 위로
        </Button>
        <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onMoveToBottom(card); }}>
          맨 아래로
        </Button>
        {canAdd ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onAddToSprint(card);
            }}
          >
            스프린트에 담기
          </Button>
        ) : null}
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
  const [tab, setTab] = React.useState(TAB_BOARD);
  const [projectId, setProjectId] = React.useState("");
  const [sprintId, setSprintId] = React.useState("");
  const [assigneeId, setAssigneeId] = React.useState("");
  const [mine, setMine] = React.useState(false);
  const [troubleOnly, setTroubleOnly] = React.useState(false);
  const [showHold, setShowHold] = React.useState(false);
  // §8.1 — 회차 미선택일 때 완료·취소까지 보는 토글. 회차 안에서는 뜻이 없다(그 회차의
  // 전체 이력이 이미 다 보인다) — 그래서 sprintId 가 있을 때는 안 보여 준다.
  const [showAll, setShowAll] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [priority, setPriority] = React.useState("");
  const [difficulty, setDifficulty] = React.useState("");
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
  const autoSelectedRef = React.useRef(false);
  React.useEffect(() => {
    if (autoSelectedRef.current || !sprints.data || sprintId) return;
    autoSelectedRef.current = true;
    const active = sprintRows.find((s) => s.active);
    if (active) setSprintId(active.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sprints.data]);

  // §8.1 — scope. 회차를 골랐으면 그 회차 전체(완료·취소 포함)를 본다 — "실행분만"이라는
  // 개념 자체가 회차 문맥에는 없다. 안 골랐으면 execution(기본)/all(토글) 이다.
  const scope = sprintId ? undefined : (showAll ? "all" : "execution");

  // 판과 백로그가 **같은 조건 이름**을 쓴다. 탭을 옮겨도 방금 건 조건이 그대로 산다.
  const boardKey = [projectId, sprintId, assigneeId, mine, troubleOnly, scope];
  const board = useQuery({
    queryKey: ["work-board", ...boardKey],
    queryFn: () =>
      api(
        "/api/work/board?" +
          qs({
            project_id: projectId,
            sprint_id: sprintId,
            assignee_user_id: mine ? "" : assigneeId,
            mine,
            blocked_only: troubleOnly,
            scope,
            column_page_size: COLUMN_PAGE_SIZE,
          })
      ),
    enabled: tab === TAB_BOARD,
  });

  // 필터가 바뀌면 다음 쪽으로 받아 둔 것도 함께 비운다 — 안 그러면 옛 조건의 카드가
  // 새 조건의 열 아래에 그대로 남는다.
  React.useEffect(() => { setColExtra({}); }, [JSON.stringify(boardKey)]);

  const backlogKey = [projectId, query, assigneeId, mine, priority, difficulty];
  const backlog = useInfiniteQuery({
    queryKey: ["work-backlog", ...backlogKey],
    queryFn: ({ pageParam }) =>
      api(
        "/api/work/backlog?" +
          qs({
            project_id: projectId,
            q: query,
            assignee_user_id: mine ? "" : assigneeId,
            mine,
            priority,
            difficulty,
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
      // 만든 회차를 바로 고른다. 안 고르면 「만들었는데 아무 일도 안 일어난」 것으로 보인다.
      setSprintId(sprint.id);
      toast("스프린트를 만들었습니다.", "success");
    },
    onError: (e) =>
      toast((e && e.message) || "스프린트를 만들지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const move = useMutation({
    mutationFn: ({ id, body }) =>
      api(`/api/work/board/${encodeURIComponent(id)}/move`, { method: "POST", body }),
    onSuccess: () => {
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

  /* 열은 서버가 정한 **자리**로 고른다(`placement`). 화면이 상태 이름을 적어 열을 고르면
     어휘가 바뀐 날 이 화면만 옛 목록으로 남고, 그 어긋남은 아무 오류도 안 낸다.
     첫 쪽(board.data) 위에 `colExtra` 로 받아 둔 다음 쪽들을 얹는다. */
  const columns = React.useMemo(() => {
    const data = board.data;
    if (!data) return [];
    const wanted = [PLACE_COLUMN];
    if (showHold) wanted.push(PLACE_COLLAPSED);
    if (showAll) wanted.push(PLACE_HIDDEN);
    const cols = (data.columns || [])
      .filter((c) => wanted.indexOf(c.placement || PLACE_COLUMN) >= 0)
      .map((c) => {
        const extra = colExtra[c.key] || EMPTY_EXTRA;
        const items = [...(c.cards || []), ...extra.cards];
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
        };
      });
    if ((data.unclassified || []).length || data.unclassified_next_cursor) {
      const extra = colExtra[UNCLASSIFIED] || EMPTY_EXTRA;
      const items = [...(data.unclassified || []), ...extra.cards];
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [board.data, showHold, showAll, colExtra]);

  /* 열 하나의 다음 쪽 — **같은 조건**으로(§8.5). 필터가 바뀌면 boardKey 도 바뀌어
     colExtra 가 비워지므로, 여기서는 "지금 이 boardKey" 를 그대로 싣는다. */
  async function loadMoreColumn(statusKey, cursor) {
    setColExtra((prev) => ({
      ...prev, [statusKey]: { ...(prev[statusKey] || EMPTY_EXTRA), loading: true },
    }));
    try {
      const body = await api(
        `/api/work/board/columns/${encodeURIComponent(statusKey)}?` +
          qs({
            project_id: projectId, sprint_id: sprintId,
            assignee_user_id: mine ? "" : assigneeId, mine, blocked_only: troubleOnly,
            scope, cursor, limit: COLUMN_PAGE_SIZE,
          })
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
  }

  const backlogPages = (backlog.data && backlog.data.pages) || [];
  const backlogRows = backlogPages.flatMap((p) => p.items || []);
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

  /* 판독 줄 — **자르기 전에 센** 값이다(`app/work/service.py::board`). 열의 카드를 더해
     세면 잘린 열에서 조용히 틀린다. */
  const statusTiles = summary
    ? (board.data.columns || []).map((c) => ({
        label: c.label,
        value: String((summary.by_status || {})[c.key] ?? 0),
      }))
    : [];
  const signalTiles = summary
    ? [
        { label: "차단됨", value: String(summary.signals.blocked), kind: "danger" },
        { label: "지연", value: String(summary.signals.overdue), kind: "danger" },
        { label: "이슈 있음", value: String(summary.signals.issue), kind: "warn" },
      ]
    : [];

  /* 「티켓 추가」가 데려가는 곳. 회차 맥락은 **판 탭에서만** 싣는다 — 백로그 탭에서 만든
     티켓이 회차로 들어가면 그 탭의 뜻(아직 안 담은 일)과 어긋난다. */
  const newTicketQuery = qs({
    project: projectId,
    sprint: tab === TAB_BOARD ? sprintId : "",
  });
  const newTicketPath = "/new-ticket" + (newTicketQuery ? `?${newTicketQuery}` : "");

  const boardEmpty = columns.every((c) => c.items.length === 0);

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

      {/* §8.2 — 회차 미선택일 때 판 위에 맥락을 말한다. 회차가 0건이면 「스프린트
          만들기」를 강조 단추로 둔다(위 actions). */}
      {tab === TAB_BOARD && !sprintId ? (
        <Callout tone="info" variant="inline" sx={{ mb: 1.5 }}>
          {showAll
            ? "완료와 취소를 포함한 전체 티켓을 보여 줍니다."
            : "회차를 고르지 않아 실행 중인 업무만 보여 줍니다."}
        </Callout>
      ) : null}

      {/* 탐색 줄의 구조가 프로젝트·티켓과 **같다**(지시 8): 위 줄이 「무엇을 찾는가」,
          아래 줄이 「무엇으로 좁히는가」. 프로젝트와 스프린트가 맨 앞인 이유는 이 화면의
          질문이 언제나 「어느 프로젝트의 이번 회차」로 시작하기 때문이다. */}
      <FilterSurface>
        {tab === TAB_BACKLOG ? (
          <ToolbarRow>
            <SearchBox
              value={query}
              onSearch={setQuery}
              placeholder="티켓 제목, 이름 검색"
              ariaLabel="백로그 검색"
            />
          </ToolbarRow>
        ) : null}
        <FilterRow>
          {/* 프로젝트는 **기수가 무한히 자라는 대상**이라 평범한 드롭다운으로 못 고른다
              (`plain_dropdown_for_entity`). 같은 이유로 담당자도 조합 상자다. */}
          <EntityCombobox
            label="프로젝트"
            value={projectId}
            onChange={(next) => setProjectId(next || "")}
            loading={projects.isLoading}
            options={projectRows.map((p) => ({ value: p.id, label: p.name }))}
            allLabel="전체"
            sx={{ minWidth: "14rem" }}
          />
          <EntityCombobox
            label="스프린트"
            value={sprintId}
            onChange={(next) => setSprintId(next || "")}
            loading={sprints.isLoading}
            options={sprintRows.map((s) => ({
              value: s.id,
              label: s.active ? `${s.name} (진행 중)` : s.name,
            }))}
            allLabel="전체"
            sx={{ minWidth: "12rem" }}
          />
          <EntityCombobox
            label="담당자"
            value={assigneeId}
            onChange={(next) => setAssigneeId(next || "")}
            loading={assignees.isLoading}
            options={assigneeRows.map((a) => ({ value: a.user_id, label: a.display_name }))}
            allLabel="전체"
            disabled={mine}
            sx={{ minWidth: "12rem" }}
          />
          {tab === TAB_BACKLOG ? (
            <>
              <FilterSelect
                label="우선순위"
                value={priority}
                onChange={setPriority}
                options={metaBody.priorities || []}
                allLabel="전체"
              />
              <FilterSelect
                label="난이도"
                value={difficulty}
                onChange={setDifficulty}
                options={metaBody.difficulties || []}
                allLabel="전체"
              />
            </>
          ) : null}
          <FormControlLabel
            sx={{ m: 0 }}
            control={
              <Switch size="small" checked={mine} onChange={(e) => setMine(e.target.checked)} />
            }
            label={<Typography variant="body2">내 티켓만</Typography>}
          />
          {tab === TAB_BOARD ? (
            <FormControlLabel
              sx={{ m: 0 }}
              control={
                <Switch
                  size="small"
                  checked={troubleOnly}
                  onChange={(e) => setTroubleOnly(e.target.checked)}
                />
              }
              label={<Typography variant="body2">차단과 이슈만</Typography>}
            />
          ) : null}
          {tab === TAB_BOARD ? (
            <FilterActions>
              {/* 보류는 기본 판에서 비켜 있다(D-349). 없애는 것이 아니라 **접는 것**이라,
                  펴는 스위치가 늘 여기 있다 — 안 그러면 보류한 일이 어느 화면에도 없어서
                  영영 잊힌다. */}
              <Button variant="ghost" size="sm" onClick={() => setShowHold((v) => !v)}>
                {showHold ? "보류 접기" : "보류 펴기"}
              </Button>
              {/* 완료·취소는 열이 아니라 이 토글로 본다(§8.1) — 회차를 이미 골랐으면
                  그 회차 전체가 항상 다 보이므로 이 토글 자체가 뜻이 없다. */}
              {!sprintId ? (
                <Button variant="ghost" size="sm" onClick={() => setShowAll((v) => !v)}>
                  {showAll ? "완료와 취소 감추기" : "완료와 취소 보기"}
                </Button>
              ) : null}
            </FilterActions>
          ) : null}
        </FilterRow>
      </FilterSurface>

      <Tabs value={tab} onChange={(_e, v) => setTab(v)} aria-label="보기 선택" sx={{ mb: 2 }}>
        <Tab value={TAB_BOARD} label="칸반" />
        <Tab value={TAB_BACKLOG} label="백로그" />
      </Tabs>

      {active.isLoading ? <Skeleton kind="section" /> : null}
      {active.isError ? <ErrorState error={active.error} onRetry={active.refetch} /> : null}

      {tab === TAB_BOARD && summary ? (
        <Stack spacing={1} sx={{ mb: 2 }}>
          <MetricStrip
            ariaLabel="상태별 티켓 수"
            items={[{ label: "전체", value: String(summary.total), primary: true }, ...statusTiles]}
          />
          {/* 신호 줄은 켜진 것이 하나라도 있을 때만 선다. 「차단 0 · 지연 0 · 이슈 0」은
              매일 같은 자리를 쓰면서 아무 것도 말하지 않는다. */}
          {signalTiles.some((t) => t.value !== "0") ? (
            <MetricStrip ariaLabel="신호별 티켓 수" items={signalTiles} />
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
                ? <Button variant="secondary" onClick={() => setShowAll(true)}>완료와 취소 보기</Button>
                : undefined
            }
          />
        ) : (
          <DragBoard
            columns={columns}
            labelOf={labelOf}
            onMove={handleBoardMove}
            columnMaxHeight={COLUMN_BODY_MAX}
            // §15.1 재검수 — 서버가 이미 열마다 커서로 잘라 준 것(§8.5) 위에 렌더링만
            // 가상화한다. 카드 하나(TicketCard)는 배지·신호·담당자까지 있어 백로그 행보다
            // 조금 크다 — 실측 없이 어림한 값이고 실제 높이는 measureElement가 다시 잰다.
            virtualize={{ estimateSize: 128 }}
          >
            {(card) => (
              <DragItem key={card.id} id={card.id} label={labelOf(card.id)}>
                <TicketCard
                  card={card}
                  onOpen={openTicket}
                  signals={signalsOf(card)}
                  showProject={!projectId}
                />
              </DragItem>
            )}
          </DragBoard>
        )
      ) : null}

      {tab === TAB_BACKLOG && backlogPages.length ? (
        backlogRows.length === 0 ? (
          <EmptyState title="백로그가 비어 있습니다." />
        ) : (
          <Box>
            <BacklogHead />
            <SortableList
              items={backlogRows}
              labelOf={labelOf}
              onReorder={handleBacklogReorder}
              // §15.1 재검수 — 서버 커서 페이징(§8.5, useInfiniteQuery) 위에 렌더링만
              // 가상화한다. 181행을 한 번에 그리던 자리다. 판 열과 같은 높이(60vh)를
              // 써서 두 탭이 같은 느낌으로 스크롤한다.
              virtualize={{ estimateSize: 72, height: "60vh", ariaLabel: "백로그 목록" }}
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
            {/* 「N건 중 M건」과 「더 보기」— 서버가 실제로 다음 쪽을 내주는 계약(§8.5).
                키보드·스크린리더 사용자는 무한 스크롤에 닿을 수 없어 단추를 함께 둔다. */}
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 1, mt: 2 }}>
              <Typography variant="caption" color="text.secondary">
                {backlogTotal}건 중 {backlogRows.length}건을 받았습니다.
              </Typography>
              {backlog.hasNextPage ? (
                <Button
                  variant="ghost" size="sm" loading={backlog.isFetchingNextPage}
                  onClick={() => backlog.fetchNextPage()}
                >
                  백로그 더 보기
                </Button>
              ) : null}
            </Box>
          </Box>
        )
      ) : null}

      <FormModal
        open={sprintFormOpen}
        title="새 스프린트"
        submitLabel="만들기"
        fields={SPRINT_FIELDS}
        onSubmit={(values) =>
          createSprint.mutateAsync({
            name: values.name,
            starts_on: values.starts_on,
            ends_on: values.ends_on,
            // 위에서 고른 프로젝트에 만든다. 「전체」면 팀 전체 회차다 — 폼에 칸을
            // 하나 더 두면 위 선택기와 다른 값을 고를 수 있고, 그러면 만든 회차가
            // 지금 보고 있는 판에 안 나타난다.
            project_id: projectId || null,
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
