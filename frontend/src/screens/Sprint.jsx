import React from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  FormModal,
  PageHeader,
  Section,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { FilterRow, FilterSurface } from "../ui/FilterBar.jsx";
import { EntityCombobox, FilterSelect } from "../ui/filters.jsx";
import { BarSeries } from "../ui/charts/BarSeries.jsx";
import { LineSeries } from "../ui/charts/LineSeries.jsx";
import { Gauge } from "../ui/charts/Gauge.jsx";
import { ProgressBar } from "../ui/charts/ProgressBar.jsx";
import {
  burndownSeries, datedLabel, healthBand, healthCuts, normalizeMeeting, pickOpenSprint,
  scopeTrendSeries, workloadItems,
} from "./sprint-charts.js";
import {
  SprintLifecycle, SprintStateBadge, sprintPhaseNote, sprintStateLabel, useCanPlanSprint,
} from "./SprintLifecycle.jsx";
import { sprintFields } from "./sprint-fields.js";
import { useQueryState } from "../lib/useQueryState.js";
import { useTicketProjects } from "./ticket-options.js";
import { SIGNALS, useTicketSignals } from "../lib/ticketSignals.js";
import { TicketFace, TicketPeople } from "../ui/TicketFace.jsx";
import { StatusKpiStrip } from "../ui/StatusKpi.jsx";
import { DiscussBucketRow } from "../ui/DiscussBucket.jsx";
import { DateField } from "../ui/DateField.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { priorityKind, priorityKo } from "../lib/priority.js";
import { MEETING_PAIR_TRACKS, PAIR_CHART_MIN_HEIGHT, PANEL_SURFACE, LANE_SURFACE, TILE_PADDING } from "../ui/density.js";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { UserAvatar } from "../ui/UserAvatar.jsx";

/* 스프린트 회의 (지시 4).
 *
 * ## 무엇이 달라졌나
 *
 * 예전 이 화면은 **회차를 몰랐다.** 「이번 주 월요일부터 다음 주 월요일까지 마감인 티켓」을
 * 모아 놓고 그것을 스프린트라고 불렀고, 화면 스스로 「날짜 범위 기준입니다」라고 사과하는
 * 문구를 달고 있었다. 그래서 회의에서 「이번 회차에 뭐 넣기로 했지」를 물으면 답이 없었다.
 *
 * 지금은 회차가 실체다(`sprints` 표). 이 화면은 **그 회차에 담긴 티켓**만 본다 —
 * `sprint_id` 한 칸이 그 정의다.
 *
 * ## 여섯 질문의 순서로 놓는다
 *
 * 지시가 적은 여섯 질문이 이 화면의 세로 순서다. 회의에서 실제로 말하는 순서이기도 하다.
 *
 *   1 정상 진행인가        → 요약 줄 · 번다운 · 건강
 *   2 어떤 티켓이 문제인가  → 오늘 논의할 항목
 *   3 Workload 가 고른가    → 담당자별 남은 WD
 *   4 Scope 가 얼마나 바뀌었나 → 범위 변경
 *   5 무엇을 더 넣을까      → 이번 회차 후보
 *   6 무엇을 정했나        → 회의 결정과 다음 할 일
 *
 * ## 그림은 셋이다
 *
 * 번다운 · 건강 · 담당자별 남은 WD. 넷째를 더하고 싶어질 때마다, 그 그림을 보고 **회의에서
 * 무엇을 결정할 수 있는가**를 먼저 묻는다. 답이 없으면 그것은 장식이고, 장식은 진짜 신호를
 * 묻는다. 상태 분포는 요약 줄이 이미 숫자로 말하므로 그리지 않는다.
 *
 * ## 회의록은 저장된다
 *
 * 이 화면의 유일한 쓰기다. 예전에는 조회 전용이라 회의에서 정한 것이 화면을 닫으면
 * 사라졌고, 다음 주에 같은 이야기가 다시 나왔다.
 */

const KIND_DECISION = "decision";
const KIND_ACTION = "action";

/** 「오늘 논의할 항목」의 갈래. 순서는 회의에서 말하는 순서다 — 급한 것부터.
 *
 * 🔴 이 줄이 **판독 줄이기도 하다.** 예전에는 위 KPI 줄이 지연·차단·이슈를 숫자로 한 번
 * 말하고 이 줄이 같은 숫자를 다시 말했다. 같은 값을 두 번 그리면 둘 중 어느 것이 눌리는지
 * 사용자가 배워야 하고, 그 답이 「아래것만」이라 위 숫자는 죽은 픽셀이었다. 지금 위 줄은
 * **진행**만 말하고(전체·완료·진행 중·남은 WD) 문제는 전부 여기 모여 눌린다.
 *
 * 뒤의 둘은 **회의 준비**다. 예상 WD 나 마감이 비어 있으면 번다운도 담당자별 남은 WD 도
 * 못 그리는데, 예전에는 그림이 안 나온 **뒤에야** 그 사실을 알 수 있었다.
 */
/* 앞의 셋은 **신호**다. 이름도 색도 `lib/ticketSignals.js` 의 공용 표에서 온다 — 예전에는
   여기 손으로 적혀 있어서 같은 신호가 목록에서는 「이슈 있음·보라」, 이 카드에서는
   「이슈·주황」이었고, 지연과 차단은 둘 다 빨강이라 서로 구분되지도 않았다.
   뒤의 다섯은 신호가 아니라 **회의 준비 항목**이라 공용 표에 없다. */
const DISCUSS_TABS = [
  { key: "overdue", label: SIGNALS.overdue.label, empty: "지연된 티켓이 없습니다.", tone: SIGNALS.overdue.tone },
  { key: "blocked", label: SIGNALS.blocked.label, empty: "차단된 티켓이 없습니다.", tone: SIGNALS.blocked.tone },
  { key: "issue", label: SIGNALS.issue.label, empty: "이슈로 표시한 티켓이 없습니다.", tone: SIGNALS.issue.tone },
  { key: "unassigned", label: "미할당", empty: "담당자가 비어 있는 티켓이 없습니다." },
  { key: "due_soon", label: "마감 임박", empty: "곧 마감인 티켓이 없습니다.", tone: "warn" },
  { key: "no_estimate", label: "예상 WD 없음", empty: "예상 WD 가 비어 있는 티켓이 없습니다." },
  { key: "no_due", label: "마감 없음", empty: "마감이 비어 있는 티켓이 없습니다." },
  { key: "scope_changes", label: "범위 변경", empty: "회차가 시작한 뒤 드나든 티켓이 없습니다." },
];

/* 논의 목록·후보 표·회의록 레인의 세로 상한. 20행짜리 목록 둘이 화면 두 장을 먹던
 * 자리다(1920 에서 페이지 8828px 실측) — 목록은 자기 상자 안에서 구른다.
 * 값은 작업 보드 열 상한과 같은 감각(60vh)이고, 초광폭에서 무한히 크지 않게 rem 으로 막는다. */
const MEETING_LIST_MAX = "min(60vh, 44rem)";

const SPRINT_SPEC = { project: "", sprint: "" };

/** 담당자 얼굴 줄. 판의 카드와 **같은 부품**을 쓴다 (지시 6). */
function People({ row }) {
  return <TicketPeople card={row} />;
}

/** 논의 목록 한 줄. 누르면 그 티켓으로 간다 — 「관련 티켓으로 바로 이동」이 요구다. */
function DiscussRow({ row, onOpen, signals, showProject }) {
  return (
    <Card sx={{ p: 1.25, cursor: "pointer" }} onClick={() => onOpen(row)}>
      <TicketFace
        card={row}
        signals={signals}
        showProject={showProject}
        compact
      />
    </Card>
  );
}

/** 회의록 한 줄. 레인 안에서는 종류 뱃지를 숨기고, 할 일만 체크한다. */
function DecisionRow({ row, onToggle, onDelete, onOpenTicket, inLane = false }) {
  const isAction = row.kind === KIND_ACTION;
  return (
    <Card sx={{ p: 1.25, display: "flex", alignItems: "flex-start", gap: 1 }}>
      {isAction ? (
        <Checkbox
          size="small"
          checked={!!row.done}
          onChange={(e) => onToggle(row, e.target.checked)}
          inputProps={{ "aria-label": `${row.body} 완료 여부` }}
          sx={{ p: 0.5 }}
        />
      ) : (
        <Box sx={{ width: 28, flexShrink: 0 }} aria-hidden />
      )}
      <Box sx={{ minWidth: 0, flex: 1 }}>
        {!inLane ? (
          <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0, mb: 0.25 }}>
            <Badge
              value={isAction ? "할 일" : "결정"}
              kind={isAction ? "info" : "neutral"}
            />
            {row.ticket_page_id ? (
              <Button variant="ghost" size="sm" onClick={() => onOpenTicket(row)}>
                {row.ticket_key || "티켓 열기"}
              </Button>
            ) : null}
          </Stack>
        ) : row.ticket_page_id ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onOpenTicket(row)}
            sx={{ mb: 0.25, minHeight: 0, px: 0 }}
          >
            {row.ticket_key || "티켓 열기"}
          </Button>
        ) : null}
        <Typography
          variant="body2"
          sx={{
            ...KO_WORD_BREAK,
            color: row.done ? "text.secondary" : "text.primary",
            textDecoration: row.done ? "line-through" : "none",
          }}
        >
          {row.body}
        </Typography>
        {isAction ? (
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.25 }}>
            {row.assignee ? <UserAvatar person={row.assignee} size="sm" label={row.assignee.display_name} /> : null}
            <Typography variant="caption" color="text.secondary">
              {[
                row.assignee ? row.assignee.display_name : null,
                row.due_date ? `마감 ${row.due_date}` : null,
              ].filter(Boolean).join("  ") || "담당자와 마감은 아직 정하지 않았습니다."}
            </Typography>
          </Stack>
        ) : row.due_date ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block" }}>
            {`마감 ${row.due_date}`}
          </Typography>
        ) : null}
      </Box>
      <Button variant="ghost" size="sm" onClick={() => onDelete(row)}>
        삭제
      </Button>
    </Card>
  );
}

/** 회의록을 적는 줄. 위 입력은 아래 결정·할 일 레인으로 나뉘어 쌓인다. */
function DecisionComposer({ onAdd, busy }) {
  const [kind, setKind] = React.useState(KIND_DECISION);
  const [body, setBody] = React.useState("");
  const [due, setDue] = React.useState("");

  function submit(e) {
    e.preventDefault();
    const text = body.trim();
    if (!text) return;
    onAdd({ kind, body: text, due_date: due || null }, () => {
      setBody("");
      setDue("");
    });
  }

  return (
    <Box component="form" onSubmit={submit} sx={{ display: "grid", gap: 1.5 }}>
      <Typography variant="body2" color="text.secondary">
        위에서 적은 내용은 아래 칸에 나뉘어 쌓입니다. 결정은 사실 기록이고, 할 일은 끝나면 체크합니다.
      </Typography>
      <Stack direction="row" flexWrap="wrap" gap={1} alignItems="flex-end">
        <FilterSelect
          label="종류"
          value={kind}
          onChange={setKind}
          options={[
            { value: KIND_DECISION, label: "결정" },
            { value: KIND_ACTION, label: "할 일" },
          ]}
        />
        <TextField
          size="small"
          label="내용"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="회의에서 정한 것을 한 문장으로 적습니다."
          InputLabelProps={{ shrink: true }}
          sx={{ flex: "1 1 18rem", minWidth: "14rem" }}
        />
        <DateField
          size="small"
          label="마감"
          value={due}
          onChange={setDue}
          sx={{ minWidth: "10rem" }}
        />
        <Button type="submit" disabled={busy || !body.trim()}>
          적기
        </Button>
      </Stack>
    </Box>
  );
}

export function Sprint() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [state, setState] = useQueryState(SPRINT_SPEC);
  const [discussTab, setDiscussTab] = React.useState(DISCUSS_TABS[0].key);
  // §8.3 — 스프린트를 만드는 자리 셋 중 하나가 이 화면의 빈 상태다.
  const [sprintFormOpen, setSprintFormOpen] = React.useState(false);

  const projects = useTicketProjects(true);
  const sprints = useQuery({
    queryKey: ["work-sprints", state.project],
    queryFn: () =>
      api(
        "/api/work/sprints" +
          (state.project ? `?project_id=${encodeURIComponent(state.project)}` : "")
      ),
  });
  const sprintRows = React.useMemo(
    () => (sprints.data && sprints.data.sprints) || [],
    [sprints.data]
  );
  const projectOptions = React.useMemo(
    () =>
      ((projects.data && projects.data.projects) || []).map((p) => ({
        value: p.id,
        label: p.name,
      })),
    [projects.data]
  );

  /* 회차를 안 골랐으면 **열려 있는 회차**를 고른다. 회의를 여는 사람이 매번 목록에서
     같은 것을 다시 고르게 하지 않는다. 열린 회차가 없으면 고르지 않고 아래 빈 상태가
     안내한다(pickOpenSprint 의 qa-contract-change).

     🔴 「한 번만」은 **프로젝트 단위**다. 예전에는 불리언 ref 라, 프로젝트를 바꾸면
     (선택기가 sprint 를 비운다) 재자동선택이 영영 안 돌아 머리+필터만 남고 본문이
     백지가 됐다 — 빈 상태 조건(회차 0건)도 안 맞아 아무 안내가 없었다. 같은
     프로젝트에서 사용자가 손으로 비운 선택은 여전히 다시 덮지 않는다. */
  const autoFor = React.useRef(null);
  React.useEffect(() => {
    if (state.sprint) { autoFor.current = state.project; return; }
    if (sprints.isLoading || autoFor.current === state.project) return;
    autoFor.current = state.project;
    const picked = pickOpenSprint(sprintRows);
    if (picked) setState({ sprint: picked.id }, { replace: true });
  }, [state.sprint, state.project, sprintRows, sprints.isLoading, setState]);

  const meeting = useQuery({
    queryKey: ["sprint-meeting", state.sprint],
    queryFn: () => api(`/api/work/sprints/${encodeURIComponent(state.sprint)}/meeting`),
    enabled: !!state.sprint,
    // 회차를 넘길 때 본문을 언마운트하지 않는다 — 예전에는 매 전환마다 전체가
    // Skeleton 으로 무너졌다 차트 넷을 다시 세웠다(reveal 애니메이션까지 재생).
    // 이전 회차의 판을 감광 상태로 붙잡아 두고 새 응답이 오면 갈아 끼운다.
    placeholderData: keepPreviousData,
    // 부분 응답에도 안 죽는 모양으로 한 곳에서 정규화한다(sprint-charts.js).
    select: normalizeMeeting,
  });
  // keepPreviousData 는 회차 선택을 **비운** 직후에도 옛 판을 들고 있다 — 선택이
  // 없으면 본문도 없어야 한다(잔상 차단).
  const body = state.sprint ? meeting.data : null;
  // 지연 표식은 서버의 「오늘」로 판정한다(§불변 9 — 신호의 정본은 서버). 브라우저
  // 시계로 재면 지연 버킷 안의 티켓에 지연 표식이 안 붙는 모순이 났다(시계가 다른
  // PC, 자정을 넘겨 켜 둔 탭).
  const signalsOf = useTicketSignals(body ? body.today : undefined);
  const canPlan = useCanPlanSprint();

  function refreshMeeting() {
    qc.invalidateQueries({ queryKey: ["sprint-meeting"] });
  }

  const createSprint = useMutation({
    mutationFn: (body) => api("/api/work/sprints", { method: "POST", body }),
    onSuccess: (sprint) => {
      qc.invalidateQueries({ queryKey: ["work-sprints"] });
      setSprintFormOpen(false);
      // 만든 회차를 바로 연다 — 안 열면 「만들었는데 아무 일도 안 일어난」 것으로 보인다.
      // 프로젝트 필터도 그 회차의 것으로 옮긴다(폼에서 다른 프로젝트를 골랐을 수 있다).
      setState({ project: sprint.project_id || "", sprint: sprint.id });
      toast("스프린트를 만들었습니다.", "success");
    },
    onError: (e) =>
      toast((e && e.message) || "스프린트를 만들지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const addDecision = useMutation({
    mutationFn: (payload) =>
      api(`/api/work/sprints/${encodeURIComponent(state.sprint)}/decisions`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      refreshMeeting();
      toast("회의 기록을 남겼습니다.", "success");
    },
    onError: (e) => toast((e && e.message) || "적지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  const editDecision = useMutation({
    mutationFn: ({ id, patch }) =>
      api(`/api/work/decisions/${encodeURIComponent(id)}`, { method: "PATCH", body: patch }),
    onSuccess: refreshMeeting,
    onError: (e) => toast((e && e.message) || "고치지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  const removeDecision = useMutation({
    mutationFn: (id) =>
      api(`/api/work/decisions/${encodeURIComponent(id)}`, { method: "DELETE" }),
    onSuccess: () => {
      refreshMeeting();
      toast("회의 기록을 삭제했습니다.", "success");
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  const addToSprint = useMutation({
    mutationFn: (card) =>
      api(`/api/work/board/${encodeURIComponent(card.id)}/move`, {
        method: "POST",
        body: { sprint_id: state.sprint, set_sprint: true, base_version: card.version },
      }),
    onSuccess: () => {
      refreshMeeting();
      qc.invalidateQueries({ queryKey: ["work-backlog"] });
      qc.invalidateQueries({ queryKey: ["work-board"] });
      invalidateTicketViews(qc, { refetchType: "all" });
      toast("이번 회차에 담았습니다.", "success");
    },
    onError: (e) => toast((e && e.message) || "담지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const openTicket = React.useCallback(
    (row) => {
      const id = row.page_id || row.ticket_page_id;
      if (id) navigate(`/tickets/${encodeURIComponent(id)}`);
    },
    [navigate]
  );

  /** 이 회차를 작업 보드에서 연다 — 회의에서 「그래서 지금 뭐가 어디까지 왔나」로 넘어가는 길. */
  const openBoard = React.useCallback(
    (extra) => {
      navigate("/work-board?" + new URLSearchParams({
        project: state.project || "",
        sprint: state.sprint || "",
        ...(extra || {}),
      }).toString());
    },
    [navigate, state.project, state.sprint]
  );

  const burndown = body ? burndownSeries(body.burndown) : null;
  const scopeTrend = body ? scopeTrendSeries(body.scope) : null;
  const workload = body ? workloadItems(body.workload) : null;
  const summary = body ? body.summary : null;

  /* 후보 표. 지시가 적은 열 그대로다 — 티켓 ID · 제목 · Project · 우선순위 · 예상 WD ·
     담당자 · 마감 · 추가. 머리는 가운데이고 제목만 왼쪽이다(지시 8). */
  const candidateColumns = React.useMemo(
    () => [
      { key: "key", label: "티켓", type: "identifier", render: (r) => r.key || "-" },
      { key: "title", label: "제목", type: "title" },
      { key: "project", label: "프로젝트", type: "name", render: (r) => r.project || "-" },
      {
        key: "priority", label: "우선순위", type: "enum",
        render: (r) =>
          r.priority ? <Badge value={priorityKo(r.priority)} kind={priorityKind(r.priority)} /> : "-",
      },
      {
        key: "est_wd", label: "예상 WD", type: "number",
        render: (r) => (r.est_wd != null ? r.est_wd : "-"),
      },
      { key: "assignees", label: "담당자", type: "name", render: (r) => <People row={r} /> },
      { key: "due", label: "마감", type: "date", render: (r) => r.due || "-" },
      {
        key: "add", label: "", type: "actions",
        render: (r) => (
          <Button
            variant="ghost"
            size="sm"
            // 연타 방지 — 두 번째 요청이 자기 version 과 409(「다른 사람이 먼저…」)를
            // 만든다. 같은 화면의 DecisionComposer 가 이미 지키는 규칙이다.
            disabled={addToSprint.isPending}
            onClick={(e) => {
              e.stopPropagation();
              addToSprint.mutate(r);
            }}
          >
            추가
          </Button>
        ),
      },
    ],
    // mutation 결과 객체는 렌더마다 새것이라 memo 를 헛돌게 한다 — 안정 참조(mutate)와
    // 실제로 렌더를 바꾸는 값(isPending)만 의존한다.
    [addToSprint.mutate, addToSprint.isPending]
  );

  const tab = DISCUSS_TABS.find((t) => t.key === discussTab) || DISCUSS_TABS[0];
  // 서버가 아직 새 갈래를 모르는 순간(배포 사이)에도 화면이 안 죽는다.
  const bucket = body ? (body.discuss[tab.key] || { items: [], total: 0, truncated: false }) : null;

  return (
    <>
      <PageHeader
        area="팀 업무"
        title="스프린트 회의"
        crumbRoot={null}
        description="이번 회차가 계획대로 가고 있는지 함께 보고, 다음에 할 일을 정합니다."
        actions={
          body ? (
            <Stack direction="row" spacing={1} alignItems="center">
              {/* 앞뒤 회차는 서버가 준다. 화면이 목록에서 스스로 찾으면 두 곳의 정렬이 갈린다. */}
              <Button
                variant="ghost"
                size="sm"
                disabled={!body.neighbours.prev}
                onClick={() => setState({ sprint: body.neighbours.prev.id })}
              >
                이전 회차
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={!body.neighbours.next}
                onClick={() => setState({ sprint: body.neighbours.next.id })}
              >
                다음 회차
              </Button>
            </Stack>
          ) : null
        }
      />

      <FilterSurface>
        <FilterRow>
          <EntityCombobox
            label="프로젝트"
            value={state.project}
            onChange={(next) => setState({ project: next || "", sprint: "" })}
            loading={projects.isLoading}
            options={projectOptions}
            allLabel="전체"
            sx={{ minWidth: "14rem" }}
          />
          <EntityCombobox
            label="스프린트"
            value={state.sprint}
            onChange={(next) => setState({ sprint: next || "" })}
            loading={sprints.isLoading}
            /* 상태를 이름 옆에 적는다. 예정·진행 중·종료가 안 보이면 목록에서 어느 회차가
               지금 것인지 고를 수가 없다 — 「진행 중」 배지가 한 번도 안 붙던 이유가
               여는 동작 자체가 없어서였다(`SprintLifecycle.jsx`). */
            options={sprintRows.map((s) => ({
              value: s.id,
              label: `${s.name} (${sprintStateLabel(s)})`,
              secondary: `${s.starts_on} ~ ${s.ends_on}`,
            }))}
            allLabel="고르세요"
            sx={{ minWidth: "16rem" }}
          />
        </FilterRow>
      </FilterSurface>

      {meeting.isLoading || (sprints.isLoading && !state.sprint) ? (
        /* 본문의 실제 구조(머리 절 + 차트 두 단 + 표)를 근사한다 — 절 하나짜리
           스켈레톤은 로딩이 끝나는 순간 화면이 통째로 다른 모양으로 바뀌어 튄다. */
        <Stack spacing={2}>
          <Skeleton kind="section" />
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: MEETING_PAIR_TRACKS }}>
            <Skeleton kind="chart" />
            <Skeleton kind="chart" />
          </Box>
          <Skeleton kind="section" />
        </Stack>
      ) : null}
      {meeting.isError ? <ErrorState error={meeting.error} onRetry={meeting.refetch} /> : null}
      {/* 회차 목록 자체가 실패하면 아래 빈 상태들이 「회차가 없다」는 다른 사실을 말하게
          된다 — 실패는 실패로 그린다. */}
      {sprints.isError && !state.sprint ? (
        <ErrorState error={sprints.error} onRetry={sprints.refetch} />
      ) : null}
      {!state.sprint && !sprints.isLoading && !sprints.isError && sprintRows.length === 0 ? (
        // §8.3 — 회의 빈 상태는 화면 전체가 비었다(layout="page")로 그린다. 없는 prop
        // `hint` 를 넘기던 자리라 안내 문장 자체가 안 나왔다(A2) — `help` 로 옮기고,
        // 「스프린트 만들기」·「백로그 보기」 둘을 다음 행동으로 준다.
        <EmptyState
          layout="page"
          title="아직 만든 스프린트가 없습니다."
          help="회차를 만들면 여기서 번다운과 건강, 담당자별 남은 일을 보고 회의를 진행할 수 있습니다."
          action={
            <>
              <Button variant="primary" onClick={() => setSprintFormOpen(true)}>스프린트 추가</Button>
              <Button variant="secondary" onClick={() => navigate("/work-board?tab=backlog")}>백로그 보기</Button>
            </>
          }
        />
      ) : null}
      {!state.sprint && !sprints.isLoading && !sprints.isError && sprintRows.length > 0 ? (
        /* 회차는 있는데 열린 것이 없어 자동 선택이 비켜 간 상태다. 예전에는 이 조합이
           머리+필터만 남는 백지였다 — 화면이 다음 행동을 말한다. */
        <EmptyState
          layout="page"
          title="회의할 회차를 고르세요."
          help="위 스프린트 칸에서 회차를 고르면 번다운과 남은 일을 보며 회의를 시작할 수 있습니다. 열려 있는 회차가 있으면 자동으로 고릅니다."
          action={
            <>
              <Button variant="primary" onClick={() => setState({ sprint: sprintRows[0].id })}>
                가장 최근 회차 열기
              </Button>
              <Button variant="secondary" onClick={() => setSprintFormOpen(true)}>스프린트 추가</Button>
            </>
          }
        />
      ) : null}

      {body ? (
        /* 회차 전환 중(keepPreviousData 의 잔상 표시)에는 감광으로 「바뀌는 중」을
           말한다 — 차트 넷을 언마운트하지 않으면서도 옛 값이 새 값 행세를 안 한다. */
        <Box
          aria-busy={meeting.isPlaceholderData || undefined}
          sx={{
            opacity: meeting.isPlaceholderData ? 0.55 : 1,
            transition: "opacity 120ms ease",
          }}
        >
          {/* 회차 머리 — **안내가 아니라 화면 문맥**이다.
              예전에는 이 자리가 `Callout` 이었고, 그 톤의 색(#1F5FBF)이 Brand(#4C58C8)와
              가까워서 「안내 영역인데 본문과 시각적으로 구분되지 않는다」는 말을 들었다.
              지금은 중립 함몰면 위에 회차 이름·기간·오늘·상태·목표와 **여는/닫는 단추**가
              한 줄로 선다 — 이 화면에서 회차에 대해 할 수 있는 일이 전부 여기 있다. */}
          <Box sx={{ ...LANE_SURFACE, p: PANEL_SURFACE.p, mb: 2 }}>
            <Stack
              direction="row" flexWrap="wrap" gap={1} alignItems="center"
              justifyContent="space-between"
            >
              <Box sx={{ minWidth: 0 }}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                  <Typography component="h2" variant="sectionTitle" sx={{ ...KO_WORD_BREAK }}>
                    {body.sprint.name}
                  </Typography>
                  <SprintStateBadge sprint={body.sprint} />
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, ...KO_WORD_BREAK }}>
                  {`${datedLabel(body.sprint.starts_on)} ~ ${datedLabel(body.sprint.ends_on)}, 오늘 ${body.today}`}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, ...KO_WORD_BREAK }}>
                  {sprintPhaseNote({ state: body.sprint.state, phase: body.phase, canPlan })}
                </Typography>
                {body.sprint.goal ? (
                  <Typography variant="body2" sx={{ mt: 0.75, ...KO_WORD_BREAK }}>
                    {`회차 목표: ${body.sprint.goal}`}
                  </Typography>
                ) : null}
              </Box>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ flexShrink: 0 }}>
                <SprintLifecycle
                  sprint={body.sprint}
                  sprints={sprintRows}
                  size="md"
                  onDeleted={() => setState({ sprint: "" })}
                />
                <Button
                  variant="secondary"
                  onClick={() => navigate("/work-board?" + new URLSearchParams({
                    project: state.project || "", sprint: body.sprint.id,
                  }).toString())}
                >
                  작업 보드에서 보기
                </Button>
              </Stack>
            </Stack>
          </Box>

          {/* 1 — 정상 진행인가. **판을 두르지 않는다** — 타일이 이미 판이다. */}
          <StatusKpiStrip
            ariaLabel="이번 회차 요약"
            revealKey="sprint-meeting:kpi"
            sx={{ mb: 2 }}
            items={[
              /* 셈 타일 셋은 전부 눌린다 — 「전체」만 눌리면 똑같이 생긴 타일이 어떤
                 것은 반응하고 어떤 것은 죽어 있어, 사용자가 규칙을 못 배운다. 측정
                 타일 둘(남은 WD·진행률)은 데려갈 목록이 없어 그대로 둔다. */
              { label: "전체", value: String(summary.total), primary: true, onClick: () => openBoard() },
              {
                label: "완료", value: String(summary.done), kind: "ok",
                pct: summary.total ? Math.round((summary.done / summary.total) * 100) : 0,
                onClick: () => openBoard({ all: "1" }),
              },
              { label: "진행 중", value: String(summary.in_progress), kind: "info", onClick: () => openBoard() },
              { label: "남은 WD", value: String(summary.remaining_wd) },
              {
                label: "진행률",
                value: body.health ? `${body.health.progress_pct}%` : "-",
                pct: body.health ? body.health.elapsed_pct : undefined,
              },
            ]}
          />

          <Box
            sx={{
              display: "grid", gap: 2, mb: 2,
              gridTemplateColumns: MEETING_PAIR_TRACKS,
              "& > *": { minHeight: PAIR_CHART_MIN_HEIGHT, display: "flex", flexDirection: "column" },
              "& > * > *:last-child": { flex: 1, minHeight: 0, justifyContent: "flex-start" },
            }}
          >
            <Section title="번다운" rule sx={{ mb: 0, flex: 1 }}>
              <Box sx={{ ...PANEL_SURFACE, flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
              {burndown ? (
                <LineSeries
                  series={burndown.series}
                  labels={burndown.labels}
                  unit="인일"
                  summary={burndown.summary}
                  question="이 회차가 계획대로 줄고 있는지 봅니다. 남은 일 선은 오늘까지만 그립니다."
                  revealKey={body.sprint.id}
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  예상 WD 가 적힌 티켓이 있어야 번다운을 그릴 수 있습니다. 위 「예상 WD 없음」에서 채울 수 있습니다.
                </Typography>
              )}
              </Box>
            </Section>
            <Section title="회차 건강" rule sx={{ mb: 0, flex: 1 }}>
              <Box sx={{ ...PANEL_SURFACE, flex: 1, display: "flex", flexDirection: "column", alignItems: "center", minHeight: 0 }}>
              <Stack spacing={1.5} alignItems="center" sx={{ width: "100%", pt: 0.5 }}>
                <Gauge
                  value={body.health ? body.health.score : null}
                  centerText={body.health && healthBand(body.health.score)
                    ? `${body.health.score} ${healthBand(body.health.score).label}`
                    : undefined}
                  label={body.health ? healthCuts(summary) : "지연과 차단을 반영한 점수입니다."}
                  emptyLabel="담긴 티켓이 없어 아직 재지 않았습니다."
                  revealKey={body.sprint.id}
                />
                {body.health ? (
                  <Box sx={{ width: "100%" }}>
                    <ProgressBar
                      percent={body.health.progress_pct}
                      label={`진도 ${body.health.progress_pct}%, 기간 경과 ${body.health.elapsed_pct}%`}
                      revealKey={body.sprint.id}
                    />
                  </Box>
                ) : null}
              </Stack>
              </Box>
            </Section>
          </Box>

          {/* 2 — 어떤 티켓이 문제인가. 이 줄이 **판독이자 드릴다운**이다: 숫자를 누르면
              바로 아래에 그 티켓이 선다. 위 요약 줄과 숫자가 겹치지 않는다. */}
          <Section
            title="오늘 논의할 항목"
            help="숫자를 누르면 그 티켓이 아래에 나옵니다. 뒤의 둘은 회의 전에 채워 두면 좋은 값입니다."
            rule
          >
            <DiscussBucketRow
              value={tab.key}
              onChange={setDiscussTab}
              idBase="discuss"
              items={DISCUSS_TABS.map((t) => ({
                key: t.key,
                label: t.label,
                count: (body.discuss[t.key] || {}).total || 0,
                tone: t.tone,
              }))}
            />
            <Box
              role="tabpanel"
              id="discuss-panel"
              aria-labelledby={`discuss-tab-${tab.key}`}
              sx={{
                ...LANE_SURFACE, p: PANEL_SURFACE.p, minHeight: "6rem",
                // 목록은 자기 상자 안에서 구른다 — 20행이 화면 한 장을 통째로 먹지 않게.
                maxHeight: MEETING_LIST_MAX, overflowY: "auto",
              }}
            >
            {bucket.items.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                {tab.empty}
              </Typography>
            ) : (
              <Stack spacing={1}>
                {bucket.items.map((row) => (
                  <DiscussRow
                    key={row.id || row.ticket_id}
                    row={row}
                    onOpen={openTicket}
                    signals={signalsOf(row)}
                    showProject={!state.project}
                  />
                ))}
                {bucket.truncated ? (
                  <Typography variant="caption" color="text.secondary">
                    {`${bucket.total}건 가운데 앞의 ${bucket.items.length}건만 보여 줍니다.`}
                  </Typography>
                ) : null}
              </Stack>
            )}
            </Box>
          </Section>

          {/* 3 · 4 — 업무량과 범위 변경 */}
          <Box
            sx={{
              display: "grid", gap: 2, mb: 2,
              gridTemplateColumns: MEETING_PAIR_TRACKS,
              "& > *": { minHeight: PAIR_CHART_MIN_HEIGHT, display: "flex", flexDirection: "column" },
              "& > * > *:last-child": { flex: 1, minHeight: 0, justifyContent: "flex-start" },
            }}
          >
            <Section title="담당자별 남은 WD" rule sx={{ mb: 0, flex: 1 }}>
              <Box sx={{ ...PANEL_SURFACE, flex: 1, minHeight: 0 }}>
              {workload ? (
                <BarSeries
                  items={workload.items}
                  max={workload.max}
                  unit="인일"
                  relativeNote={workload.summary}
                  question="한 사람에게 일이 몰려 있는지 봅니다."
                  revealKey={body.sprint.id}
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  담당자가 걸린 남은 티켓이 없습니다.
                </Typography>
              )}
              </Box>
            </Section>
            <Section title="범위 변경" rule sx={{ mb: 0, flex: 1 }}>
              <Box sx={{ ...PANEL_SURFACE, flex: 1, minHeight: 0 }}>
              {/* 「기록이 없다」와 「안 바뀌었다」는 다른 사실이다. 0 으로 적으면 화면이
                  안정된 회차라고 말하는데, 실은 아무것도 모르는 것이다. */}
              {body.scope.tracked ? (
                <Stack spacing={1}>
                  <Typography variant="body2">
                    {`회차가 시작한 뒤 ${body.scope.added}건이 들어오고 ${body.scope.removed}건이 빠졌습니다.`}
                  </Typography>
                  {/* 막대 두 개가 아니라 **추이**다. 회의가 묻는 것은 「얼마나」보다
                      「언제부터 불어났나」이고, 그 답은 이미 읽은 활동 기록의 날짜에 있다 —
                      새 API 를 만들지 않고 같은 기록을 날짜로 접었다. */}
                  {scopeTrend ? (
                    <LineSeries
                      series={scopeTrend.series}
                      labels={scopeTrend.labels}
                      unit="건"
                      question="회차 중에 범위가 언제 드나들었는지 봅니다."
                      revealKey={body.sprint.id}
                    />
                  ) : null}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDiscussTab("scope_changes")}
                  >
                    드나든 티켓 보기
                  </Button>
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  이 회차에는 드나든 기록이 없어서 범위가 얼마나 바뀌었는지 알 수 없습니다.
                </Typography>
              )}
              </Box>
            </Section>
          </Box>

          {/* 5 — 무엇을 더 넣을까 */}
          <Section
            title="이번 회차 후보"
            help="어느 회차에도 담기지 않은 티켓입니다. 「추가」를 누르면 이번 회차로 들어옵니다."
            rule
          >
            <Box sx={{ ...LANE_SURFACE, overflow: "hidden" }}>
              <Box sx={{ maxHeight: MEETING_LIST_MAX, overflowY: "auto" }}>
                <DataTable
                  columns={candidateColumns}
                  rows={body.candidates}
                  rowKey={(r) => r.id}
                  onRow={openTicket}
                  empty="담을 수 있는 백로그 티켓이 없습니다."
                />
              </Box>
            </Box>
            {/* 잘렸다는 사실을 말한다 — 논의 갈래는 truncated 를 말하는데 이 표만
                조용히 잘려, 백로그 181건인 프로젝트에서 「후보가 20개뿐」으로 읽혔다. */}
            {body.candidates_total > body.candidates.length ? (
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  {`백로그 ${body.candidates_total}건 가운데 앞의 ${body.candidates.length}건만 보여 줍니다.`}
                </Typography>
                <Button variant="ghost" size="sm" onClick={() => openBoard({ tab: "backlog" })}>
                  백로그 보기
                </Button>
              </Stack>
            ) : null}
          </Section>

          {/* 6 — 무엇을 정했나 */}
          <Section
            title="회의 결정과 다음 할 일"
            help="회의에서 정한 내용과 할 일을 적어 두면 다음에 다시 열어도 남습니다."
            rule
          >
            <Box sx={{ ...PANEL_SURFACE, mb: 2 }}>
              <DecisionComposer
                busy={addDecision.isPending}
                onAdd={(payload, reset) =>
                  addDecision.mutate(payload, { onSuccess: reset })
                }
              />
            </Box>
            <Box
              sx={{
                display: "grid",
                gap: 2,
                gridTemplateColumns: MEETING_PAIR_TRACKS,
              }}
            >
              {[
                {
                  kind: KIND_DECISION,
                  title: "결정",
                  help: "회의에서 확정한 사실을 적어 둡니다.",
                  empty: "아직 적은 결정이 없습니다.",
                },
                {
                  kind: KIND_ACTION,
                  title: "할 일",
                  help: "다음에 해야 할 일을 적고, 끝나면 체크합니다.",
                  empty: "아직 적은 할 일이 없습니다.",
                },
              ].map((lane) => {
                const rows = body.decisions.filter((r) => r.kind === lane.kind);
                return (
                  <Box
                    key={lane.kind}
                    sx={{
                      ...LANE_SURFACE,
                      p: TILE_PADDING,
                      minHeight: "10rem",
                      // 회의록이 쌓여도 레인은 자기 상자 안에서 구른다(세로 예산).
                      maxHeight: MEETING_LIST_MAX,
                      overflowY: "auto",
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
                      <Typography variant="subtitle2" component="h3">{lane.title}</Typography>
                      <Badge value={String(rows.length)} kind="neutral" />
                    </Stack>
                    <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: "block" }}>
                      {lane.help}
                    </Typography>
                    {rows.length === 0 ? (
                      <Typography variant="body2" color="text.secondary" sx={{ mt: "auto" }}>
                        {lane.empty}
                      </Typography>
                    ) : (
                      <Stack spacing={1}>
                        {rows.map((row) => (
                          <DecisionRow
                            key={row.id}
                            row={row}
                            inLane
                            onToggle={(r, done) => editDecision.mutate({ id: r.id, patch: { done } })}
                            onOpenTicket={openTicket}
                            onDelete={async (r) => {
                              const ok = await confirm(
                                "삭제한 회의 기록은 되살릴 수 없습니다. 이 기록을 삭제할까요?",
                                { danger: true, confirmLabel: "삭제" }
                              );
                              if (ok) removeDecision.mutate(r.id);
                            }}
                          />
                        ))}
                      </Stack>
                    )}
                  </Box>
                );
              })}
            </Box>
          </Section>
        </Box>
      ) : null}

      <FormModal
        open={sprintFormOpen}
        title="새 스프린트"
        submitLabel="만들기"
        // 프로젝트 칸이 폼에 보인다(sprint-fields.js 의 이유). 기본값은 현재 필터다.
        fields={sprintFields(projectOptions)}
        initial={{ project_id: state.project || "" }}
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
    </>
  );
}
