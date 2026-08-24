import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FormModal,
  PageHeader,
  Skeleton,
  useToast,
} from "../ui/kit.jsx";
import { DragBoard, DragItem, SortableList } from "../ui/DragDrop.jsx";
import { priorityKind, priorityKo } from "../lib/priority.js";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { MODERATOR_ROLES, hasRole } from "../lib/roles.js";
import { useAuth } from "../app/auth.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { useTicketProjects } from "./ticket-options.js";
import { EntityCombobox } from "../ui/filters.jsx";

/* 작업 보드 — 칸반과 백로그 (S6).
 *
 * ## 두 화면이 아니라 두 탭인 이유
 *
 * 같은 티켓을 다른 질문으로 본다. 칸반은 "지금 무엇이 어디까지 왔는가", 백로그는 "다음에
 * 무엇을 하는가" 다. 화면을 나누면 카드를 옮긴 뒤 다른 주소로 이동해 순서를 정하게 되고,
 * 그 사이에 사람은 자기가 방금 무엇을 옮겼는지 잊는다.
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
 * 같은 카드를 옮기면 나중 사람이 앞사람의 이동을 덮어쓰는데, **둘 다 성공한 것처럼 보인다.** */

const TAB_BOARD = "board";
const TAB_BACKLOG = "backlog";

function cardKey(card) {
  return card.key || "이름 없음";
}

function TicketCard({ card, onOpen }) {
  return (
    <Card
      sx={{
        p: 1.25,
        display: "flex",
        flexDirection: "column",
        gap: 0.5,
        cursor: "pointer",
      }}
      onClick={() => onOpen(card)}
    >
      <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
          {cardKey(card)}
        </Typography>
        {card.priority ? (
          <Badge value={priorityKo(card.priority)} kind={priorityKind(card.priority)} />
        ) : null}
      </Stack>
      <Typography variant="body2" sx={{ ...KO_WORD_BREAK }}>
        {card.title || "제목 없음"}
      </Typography>
      {card.due ? (
        <Typography variant="caption" color="text.secondary">
          마감 {card.due}
        </Typography>
      ) : null}
    </Card>
  );
}

/* 새 스프린트 폼. 기간은 ISO 날짜라 서버 스키마(`SprintCreate`)와 같은 모양이다.
 * 프로젝트를 비우면 팀 전체 회차다 — 그 갈래가 있어야 한 프로젝트에 묶이지 않는
 * 주간 회차를 만들 수 있다. */
const SPRINT_FIELDS = [
  { name: "name", label: "이름", required: true, maxLength: 120 },
  { name: "starts_on", label: "시작일", type: "date", required: true },
  { name: "ends_on", label: "종료일", type: "date", required: true },
  { name: "goal", label: "목표", type: "textarea", maxLength: 2000 },
];

export function WorkBoard() {
  const navigate = useNavigate();
  // `useAuth()` 는 react-query 결과 객체다 — `data` 안에 사용자가 있다.
  const auth = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = React.useState(TAB_BOARD);
  const [projectId, setProjectId] = React.useState("");
  const [sprintId, setSprintId] = React.useState("");
  const [sprintFormOpen, setSprintFormOpen] = React.useState(false);

  // `enabled` 를 안 주면 이 질의는 아예 안 돈다(ticket-options.js) — 프로젝트 선택기가
  // 늘 비어 보이고, 그 화면은 오류를 내지 않는다.
  const projects = useTicketProjects(true);
  const sprints = useQuery({
    queryKey: ["work-sprints", projectId],
    queryFn: () =>
      api(
        "/api/work/sprints" +
          (projectId ? `?project_id=${encodeURIComponent(projectId)}` : "")
      ),
  });
  const board = useQuery({
    queryKey: ["work-board", projectId, sprintId],
    queryFn: () =>
      api(
        "/api/work/board?" +
          new URLSearchParams(
            Object.entries({ project_id: projectId, sprint_id: sprintId }).filter(
              ([, v]) => v
            )
          )
      ),
    enabled: tab === TAB_BOARD,
  });
  const backlog = useQuery({
    queryKey: ["work-backlog", projectId],
    queryFn: () =>
      api("/api/work/backlog" + (projectId ? `?project_id=${encodeURIComponent(projectId)}` : "")),
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

  const columns = React.useMemo(() => {
    const data = board.data;
    if (!data) return [];
    const cols = (data.columns || []).map((c) => ({
      id: c.key,
      title: c.label,
      count: c.total,
      items: c.cards || [],
      // 잘렸다는 사실을 말한다. 안 말하면 사용자는 이 열이 전부라고 믿는다.
      hint:
        c.total > (c.cards || []).length
          ? `앞의 ${c.cards.length}건만 보여 줍니다.`
          : null,
    }));
    if ((data.unclassified || []).length) {
      // 어휘 밖 상태. **버리지 않는다** — 안 보이는 티켓은 아무도 못 고친다.
      cols.push({
        id: "__unclassified__",
        title: "분류되지 않음",
        count: data.unclassified_total,
        items: data.unclassified,
        hint: "상태 값이 목록에 없습니다.",
      });
    }
    return cols;
  }, [board.data]);

  const cardById = React.useMemo(() => {
    const out = {};
    for (const c of columns) for (const it of c.items) out[it.id] = it;
    for (const it of (backlog.data && backlog.data.items) || []) out[it.id] = it;
    return out;
  }, [columns, backlog.data]);

  const labelOf = React.useCallback(
    (id) => {
      const card = cardById[id];
      return card ? `${cardKey(card)} ${card.title || ""}`.trim() : "";
    },
    [cardById]
  );

  function handleBoardMove({ id, fromColumn, toColumn, beforeId, afterId }) {
    const card = cardById[id];
    if (!card || toColumn === "__unclassified__") return;
    move.mutate({
      id,
      body: {
        to_status: fromColumn === toColumn ? null : toColumn,
        before_id: beforeId,
        after_id: afterId,
        reorder: true,
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

  const canPlanSprint = hasRole(MODERATOR_ROLES, auth.data && auth.data.role);
  const active = tab === TAB_BOARD ? board : backlog;
  const sprintFilter = (
    <TextField
      select
      size="small"
      label="스프린트"
      /* 프로젝트 선택기와 같은 이유로 라벨을 칸 위에 고정한다. */
      InputLabelProps={{ shrink: true }}
      value={sprintId}
      onChange={(e) => setSprintId(e.target.value)}
      sx={{ minWidth: "12rem" }}
    >
      <MenuItem value="">전체</MenuItem>
      {((sprints.data && sprints.data.sprints) || []).map((s) => (
        <MenuItem key={s.id} value={s.id}>
          {s.name}
        </MenuItem>
      ))}
    </TextField>
  );
  /* 🔴 이 자리가 이 화면을 통째로 죽이고 있었다.
   *
   * `/api/tickets/projects` 는 **객체**를 준다(`{ projects: [...] }`). 이 화면만 그것을
   * 배열로 읽어 `.map` 을 불렀고, 질의가 도착하는 순간 `TypeError` 로 ErrorBoundary 가
   * 화면을 대신 그렸다 — 즉 `/work-board` 는 아무에게도 안 열렸다. 같은 훅을 쓰는 나머지
   * 넷은 전부 `.projects` 를 읽는다(`BoardPost` · `MyTickets` 둘 · `TicketFilterBar`).
   * 한 곳만 다르게 읽는 것은 시험이 아니라 **실제 화면**을 열어야 보인다 — S16 의 캡처가
   * `console_errors` 로 잡았다.
   *
   * 그리고 프로젝트는 **기수가 무한히 자라는 대상**이라 평범한 드롭다운으로 고를 수 없다
   * (`plain_dropdown_for_entity`). 크래시가 가려 두었던 두 번째 결함이다 — 공용 선택기로
   * 바꾼다. 「값이 비면 라벨이 칸 안으로 내려앉는다」를 막는 성질은 그 부품이 이미 갖고 있다. */
  const projectRows = (projects.data && projects.data.projects) || [];
  const projectFilter = (
    <EntityCombobox
      label="프로젝트"
      value={projectId}
      onChange={(next) => setProjectId(next || "")}
      loading={projects.isLoading}
      options={projectRows.map((p) => ({ value: p.id, label: p.name }))}
      allLabel="전체"
      sx={{ minWidth: "14rem" }}
    />
  );

  return (
    <>
      <PageHeader
        area="팀 업무"
        title="작업 보드"
        crumbRoot={null}
        actions={
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            {projectFilter}
            {tab === TAB_BOARD ? sprintFilter : null}
            {/* 서버가 `PROJECT_WRITE` 로 막는다(`app/work/router.py`). 여기서 감추는
                것은 권한 보장이 아니라 **누를 수 없는 버튼을 안 보여 주는 것**이다 —
                눌러서 403 을 보는 것은 안내가 아니다. */}
            {canPlanSprint ? (
              <Button onClick={() => setSprintFormOpen(true)}>스프린트 추가</Button>
            ) : null}
          </Stack>
        }
        help="카드를 끌어 상태와 순서를 바꿉니다. 키보드로는 스페이스로 집고 화살표로 옮긴 뒤 스페이스로 놓습니다."
      />
      <Tabs
        value={tab}
        onChange={(_e, v) => setTab(v)}
        aria-label="보기 선택"
        sx={{ mb: 2 }}
      >
        <Tab value={TAB_BOARD} label="칸반" />
        <Tab value={TAB_BACKLOG} label="백로그" />
      </Tabs>

      {active.isLoading ? <Skeleton kind="section" /> : null}
      {active.isError ? <ErrorState error={active.error} onRetry={active.refetch} /> : null}

      {tab === TAB_BOARD && board.data ? (
        columns.length === 0 ? (
          <EmptyState title="보여 줄 티켓이 없습니다." />
        ) : (
          <DragBoard columns={columns} labelOf={labelOf} onMove={handleBoardMove}>
            {(card) => (
              <DragItem key={card.id} id={card.id} label={labelOf(card.id)}>
                <TicketCard card={card} onOpen={openTicket} />
              </DragItem>
            )}
          </DragBoard>
        )
      ) : null}

      {tab === TAB_BACKLOG && backlog.data ? (
        (backlog.data.items || []).length === 0 ? (
          <EmptyState title="백로그가 비어 있습니다." />
        ) : (
          <Box sx={{ maxWidth: "48rem" }}>
            <SortableList
              items={backlog.data.items}
              labelOf={labelOf}
              onReorder={handleBacklogReorder}
            >
              {(card) => (
                <DragItem key={card.id} id={card.id} label={labelOf(card.id)}>
                  <TicketCard card={card} onOpen={openTicket} />
                </DragItem>
              )}
            </SortableList>
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
    </>
  );
}
