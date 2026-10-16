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
  EmptyState,
  ErrorState,
  FormModal,
  PageHeader,
  Section,
  Skeleton,
  useConfirm,
  useToast,
  CountChip,
  SectionTitle,
  FieldLabel,
} from "../ui/kit.jsx";
import { ContextBar } from "../ui/ContextBar.jsx";
import { EntityCombobox, FilterSelect, TeamSelect } from "../ui/filters.jsx";
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
import { sprintFields, teamLabelOf } from "./sprint-fields.js";
import { useQueryState } from "../lib/useQueryState.js";
import { useListMemory } from "../lib/listReturn.js";
import { useSessionDraft } from "../lib/useSessionDraft.js";
import { useGuardedMutation } from "../lib/useGuardedMutation.js";
import { eligibleProjects, useAssigneeOptions, useTicketProjects } from "./ticket-options.js";
import { useAuth } from "../app/auth.jsx";
import { SIGNALS, useTicketSignals } from "../lib/ticketSignals.js";
import { TicketFace } from "../ui/TicketFace.jsx";
import { StatusKpiStrip } from "../ui/StatusKpi.jsx";
import { DiscussBucketRow } from "../ui/DiscussBucket.jsx";
import { DateField } from "../ui/DateField.jsx";
import { TicketPeek, useTicketPeek } from "./TicketPeek.jsx";
import { MEETING_PAIR_TRACKS, PAIR_CHART_MIN_HEIGHT, PANEL_SURFACE, LANE_SURFACE, TILE_PADDING } from "../ui/density.js";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { UserAvatar } from "../ui/UserAvatar.jsx";

/* 스프린트 회의 (지시 4 · D-482 · D-483 · D-484).
 *
 * ## 이 화면은 **이미 구성된 팀 회차 전체를 리뷰하고 결정하는 곳**이다
 *
 * 회차는 팀의 것이다(D-482). 문맥은 **팀 → 회차**이고, 프로젝트는 「오늘 논의할 항목」만
 * 좁히는 필터다 — 요약·건강·번다운·업무량·범위 변경은 언제나 회차 전체다. 필터가 지표까지
 * 바꾸면 같은 회의에서 두 사람이 다른 번다운을 본다.
 *
 * 회차를 **구성**하는 일(담기·빼기·후보)은 여기 없다(D-484). 작업 보드가 그 일을 하고, 이
 * 화면은 「작업 보드에서 회차 관리」로 그리 보낸다 — 두 화면이 같은 편성을 서로 다른 규칙으로
 * 하지 않는다.
 *
 * ## 다섯 절의 순서
 *
 *   1 회차 개요          어느 팀의 어느 회차인가 · 기간 · 단계 · 목표 · 이전/다음 · 열고 닫기
 *   2 현재 진행 상황      요약 세 칸 · 번다운 · 건강
 *   3 오늘 논의할 항목    유형별 목록(프로젝트 필터는 여기만)
 *   4 업무량과 범위 변경  담당자별 남은 WD · 드나든 기록
 *   5 회의 결정과 다음 할 일  회의록(작성 중인 글은 회차별로 남는다)
 *
 * ## 티켓 하나를 확인해도 회의를 잃지 않는다 (D-483)
 *
 * 논의 줄·회의록의 티켓 단추는 상세로 가지 않고 **미리보기**를 연다. 팀·회차·필터·논의
 * 갈래·작성 중인 회의록이 전부 제자리다. 작성 중인 글은 세션 저장소(`useSessionDraft`)에
 * 회차별로 남아, 상세를 다녀오거나 회차를 오가도 사라지지 않는다.
 *
 * ## 그림은 셋이다
 *
 * 번다운 · 건강 · 담당자별 남은 WD. 넷째를 더하고 싶어질 때마다, 그 그림을 보고 **회의에서
 * 무엇을 결정할 수 있는가**를 먼저 묻는다. 상태 분포는 요약 줄이 이미 숫자로 말한다. */

const KIND_DECISION = "decision";
const KIND_ACTION = "action";

/** 「오늘 논의할 항목」의 갈래. 순서는 회의에서 말하는 순서다 — 급한 것부터. 앞의 셋은
 * **신호**라 이름도 색도 `lib/ticketSignals.js` 의 공용 표에서 온다. 뒤의 다섯은 회의 준비
 * 항목이라 공용 표에 없다. */
const DISCUSS_TABS = [
  { key: "overdue", label: SIGNALS.overdue.label, empty: "지연된 티켓이 없습니다.", tone: SIGNALS.overdue.tone },
  { key: "blocked", label: SIGNALS.blocked.label, empty: "차단된 티켓이 없습니다.", tone: SIGNALS.blocked.tone },
  { key: "issue", label: SIGNALS.issue.label, empty: "이슈로 표시한 티켓이 없습니다.", tone: SIGNALS.issue.tone },
  { key: "unassigned", label: "미할당", empty: "미할당 티켓이 없습니다." },
  { key: "due_soon", label: "마감 임박", empty: "곧 마감인 티켓이 없습니다.", tone: "warn" },
  { key: "no_estimate", label: "예상 WD 없음", empty: "예상 WD가 비어 있는 티켓이 없습니다." },
  { key: "no_due", label: "마감 없음", empty: "마감이 비어 있는 티켓이 없습니다." },
  { key: "scope_changes", label: "범위 변경", empty: "회차가 시작한 뒤 드나든 티켓이 없습니다." },
];

/* 논의 목록·회의록 레인의 세로 상한. 목록은 자기 상자 안에서 구른다. */
const MEETING_LIST_MAX = "min(60vh, 44rem)";

/* 🔴 **조건은 전부 주소에 있다.** 팀·회차·(논의용) 프로젝트·논의 갈래·미리보기. */
const SPRINT_SPEC = { team: "", sprint: "", project: "", discuss: "", peek: "" };

/** 작성 중인 회의록의 빈 값 — 초안의 기준이다(전부 비면 저장소에서 지운다). */
const EMPTY_DRAFT = { kind: KIND_DECISION, body: "", due: "", assignee: "", ticketId: "" };

/** 값이 있는 조건만 질의 문자열에 넣는다. */
function qs(pairs) {
  return new URLSearchParams(
    Object.entries(pairs).filter(([, v]) => v !== "" && v != null && v !== false)
      .map(([k, v]) => [k, String(v)])
  ).toString();
}

/** 논의 목록 한 줄. 누르면 그 티켓의 **미리보기**가 열린다 — 회의를 떠나지 않는다. */
function DiscussRow({ row, onOpen, signals, showProject }) {
  return (
    <Card
      padding="compact"
      sx={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 1 }}
      onClick={() => onOpen(row)}
    >
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <TicketFace
          card={row}
          signals={signals}
          showProject={showProject}
          compact
        />
      </Box>
    </Card>
  );
}

/** 회의록 한 줄. 레인 안에서는 종류 뱃지를 숨기고, 할 일만 체크한다. */
function DecisionRow({ row, onToggle, onDelete, onEdit, onOpenTicket, inLane = false }) {
  const isAction = row.kind === KIND_ACTION;
  return (
    <Card padding="compact" sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
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
          /* 인라인 동작은 작은 단추 30 그대로다(계획 표 5) — 높이와 좌우 여백을 0 으로 덮으면 누를 자리가
             글자 줄상자만큼 줄고 같은 줄의 다른 30 단추와 높이가 갈린다. */
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onOpenTicket(row)}
            sx={{ mb: 0.25 }}
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
      {onEdit ? (
        <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); onEdit(row); }}>
          수정
        </Button>
      ) : null}
      {onDelete ? (
        <Button variant="ghost" size="sm" onClick={() => onDelete(row)}>
          삭제
        </Button>
      ) : null}
    </Card>
  );
}

/** 회의록을 적는 줄. 위 입력은 아래 결정·할 일 레인으로 나뉘어 쌓인다.
 *
 * 입력은 **초안**(`draft`)이다 — 부르는 화면이 회차별 세션 저장소에 들고 있어서 티켓을
 * 확인하러 나갔다 와도, 회차를 오가도 그대로다(D-483). 칸 구성은 종류를 따른다: 할 일에만
 * 담당자·마감이 붙는다. 셋 다 비울 수 있다 — 회의 중에 다 안 정해지는 것이 정상이다. */
function DecisionComposer({ draft, onDraftChange, onAdd, busy, assigneeOptions, ticketOptions }) {
  const d = draft || EMPTY_DRAFT;
  const isAction = d.kind === KIND_ACTION;
  const set = (patch) => onDraftChange((prev) => ({ ...(prev || EMPTY_DRAFT), ...patch }));

  function submit(e) {
    e.preventDefault();
    const text = (d.body || "").trim();
    if (!text) return;
    const payload = { kind: d.kind, body: text, ticket_id: d.ticketId || null };
    if (isAction) {
      payload.assignee_user_id = d.assignee || null;
      payload.due_date = d.due || null;
    }
    onAdd(payload);
  }

  return (
    <Box component="form" onSubmit={submit} sx={{ display: "grid", gap: 1.5 }}>
      <Typography variant="body2" color="text.secondary">
        위에서 적은 내용은 아래 칸에 나뉘어 쌓입니다. 결정은 사실 기록이고, 할 일은 끝나면 체크합니다. 적다 만 글은 이 회차에 남습니다.
      </Typography>
      <Stack direction="row" flexWrap="wrap" gap={1} alignItems="flex-end">
        <FilterSelect
          label="종류"
          value={d.kind}
          onChange={(v) => set({ kind: v })}
          options={[
            { value: KIND_DECISION, label: "결정" },
            { value: KIND_ACTION, label: "할 일" },
          ]}
        />
        {/* 이 줄의 고르개들이 이름을 칸 위에 세우므로(`filters.jsx::LABEL_ABOVE_SX`) 내용 칸도 같은 자리에 이름을 둔다. */}
        <Box sx={{ flex: "1 1 18rem", minWidth: "14rem" }}>
          <FieldLabel htmlFor="sprint-decision-body">내용</FieldLabel>
          <TextField id="sprint-decision-body"
            size="small"
            fullWidth
            value={d.body || ""}
            onChange={(e) => set({ body: e.target.value })}
            placeholder="회의에서 정한 것을 한 문장으로 적습니다."
          />
        </Box>
        <EntityCombobox
          label="관련 티켓"
          value={d.ticketId || ""}
          onChange={(next) => set({ ticketId: next || "" })}
          options={ticketOptions || []}
          allLabel="연결 안 함"
          sx={{ minWidth: "12rem" }}
        />
        {isAction ? (
          <>
            <EntityCombobox
              label="담당자"
              value={d.assignee || ""}
              onChange={(next) => set({ assignee: next || "" })}
              options={assigneeOptions || []}
              allLabel="아직 미정"
              sx={{ minWidth: "11rem" }}
            />
            <DateField
              size="small"
              label="마감"
              value={d.due || ""}
              onChange={(v) => set({ due: v })}
              sx={{ minWidth: "10rem" }}
            />
          </>
        ) : null}
        {/* 단추 낱말은 동사표의 「추가」이고, 무엇에 더하는지까지 말한다 — 이 화면에는 티켓을 담는 단추가 없어야 하므로(D-484)
            맨 「추가」는 티켓을 담는 일로 읽힐 수 있다(「적기」는 동사표 밖이었다, r23 #52). */}
        <Button type="submit" disabled={busy || !(d.body || "").trim()}>
          회의록에 추가
        </Button>
      </Stack>
    </Box>
  );
}

/** 짝 판의 격자 — 두 절이 같은 트랙·높이를 쓴다. */
const PAIR_GRID = {
  display: "grid", gap: 2, mb: 2,
  gridTemplateColumns: MEETING_PAIR_TRACKS,
  "& > *": { minHeight: PAIR_CHART_MIN_HEIGHT, display: "flex", flexDirection: "column" },
  "& > * > *:last-child": { flex: 1, minHeight: 0, justifyContent: "flex-start" },
};

/* 업무량과 범위 변경의 짝 — 높이를 맞추지 않는다. 담당자별 남은 WD 는 사람 수만큼의 막대라 짧을 때가 많은데, 옆 범위 변경 그림의
   높이에 맞춰 늘면 막대 한 줄 아래가 300px 비었다(r23 #104). 두 판은 위에서 맞추고 각자 내용 높이로 선다. */
const PAIR_GRID_NATURAL = {
  display: "grid", gap: 2, mb: 2, alignItems: "start",
  gridTemplateColumns: MEETING_PAIR_TRACKS,
  "& > *": { display: "flex", flexDirection: "column" },
};

export function Sprint() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  useListMemory("/sprint", { omit: ["peek"] });
  const [state, setState] = useQueryState(SPRINT_SPEC);
  const peek = useTicketPeek(state, setState);
  const teamId = state.team;
  const sprintId = state.sprint;
  // §8.3 — 회차를 만드는 자리 셋 중 하나가 이 화면의 빈 상태다.
  const [sprintFormOpen, setSprintFormOpen] = React.useState(false);
  const [editingDecision, setEditingDecision] = React.useState(null);
  const auth = useAuth();

  const projects = useTicketProjects(true);
  /* 회차 목록은 **팀별**이다(D-482). 응답에 팀 선택기의 후보와 기본 선택이 함께 온다. */
  const sprints = useQuery({
    queryKey: ["work-sprints", teamId],
    queryFn: () => api("/api/work/sprints?" + qs({ department_id: teamId })),
  });
  const sprintRows = React.useMemo(
    () => (sprints.data && sprints.data.sprints) || [],
    [sprints.data]
  );
  const team = (sprints.data && sprints.data.team) || null;
  const teamOptions = React.useMemo(() => (team && team.options) || [], [team]);
  const teamRow = React.useMemo(
    () => teamOptions.find((o) => o.id === teamId) || null,
    [teamOptions, teamId],
  );
  const teamLabel = teamLabelOf(teamRow);
  const roleCanPlan = useCanPlanSprint();
  const canPlan = roleCanPlan && !!teamRow && teamRow.manageable === true;

  /* 팀 자동 선택 — 작업 보드와 같은 규칙. */
  React.useEffect(() => {
    if (teamId || !sprints.isSuccess) return;
    const picked = team && team.selected;
    if (!picked) return;
    qc.setQueryData(["work-sprints", picked], sprints.data);
    setState({ team: picked }, { replace: true });
  }, [teamId, sprints.isSuccess, sprints.data, team, qc, setState]);
  const teamSettled = !!teamId || (sprints.isSuccess && !(team && team.selected));

  /* 회차를 안 골랐으면 **열려 있는 회차**를 고른다. 「한 번만」은 **팀 단위**다 — 팀을
     바꾸면 재자동선택이 돌고, 같은 팀에서 사용자가 손으로 비운 선택은 다시 덮지 않는다.
     팀이 비면(같은 메뉴를 다시 눌러 주소의 질의가 비었다) 다시 무장한다 — 팀이 다시 서면 그 팀의 열린 회차가 다시 선다.
     셸이 같은 메뉴 재클릭을 새 진입으로 다시 마운트하지만(`app/navEntry.jsx`, D-498) 이 화면은 그것에 기대지 않는다
     (작업 보드와 같은 규칙). */
  const autoFor = React.useRef(state.sprint ? teamId : null);
  React.useEffect(() => {
    if (!teamId) { autoFor.current = null; return; }
    if (!teamSettled) return;
    if (sprintId) { autoFor.current = teamId; return; }
    if (sprints.isLoading || autoFor.current === teamId) return;
    autoFor.current = teamId;
    const picked = pickOpenSprint(sprintRows);
    if (picked) setState({ sprint: picked.id }, { replace: true });
  }, [teamSettled, teamId, sprintId, sprintRows, sprints.isLoading, setState]);

  const changeTeam = React.useCallback((next) => {
    autoFor.current = null;
    setState({ team: next || "", sprint: "", project: "", discuss: "" });
  }, [setState]);

  const projectOptions = React.useMemo(
    () =>
      eligibleProjects((projects.data && projects.data.projects) || [], teamId).map((p) => ({
        value: p.id,
        label: p.name,
      })),
    [projects.data, teamId]
  );

  const meeting = useQuery({
    // 프로젝트 필터는 논의 목록만 좁히지만 응답 하나에 실려 오므로 키에 함께 든다.
    queryKey: ["sprint-meeting", sprintId, state.project],
    queryFn: () =>
      api(`/api/work/sprints/${encodeURIComponent(sprintId)}/meeting` + (state.project ? `?${qs({ project_id: state.project })}` : "")),
    enabled: !!sprintId,
    // 회차를 넘길 때 본문을 언마운트하지 않는다 — 이전 회차의 판을 감광 상태로 붙잡아
    // 두고 새 응답이 오면 갈아 끼운다.
    placeholderData: keepPreviousData,
    select: normalizeMeeting,
    // 회의는 여럿이 **같이** 보는 화면이다 — 홈과 같은 간격(30초)으로 다시 읽는다.
    staleTime: 30000,
    refetchInterval: 30000,
  });
  const body = sprintId ? meeting.data : null;
  // 지연 표식은 서버의 「오늘」로 판정한다(§불변 9).
  const signalsOf = useTicketSignals(body ? body.today : undefined);

  // 회의록의 담당자 후보 — 프로젝트를 골랐으면 그 프로젝트에 닿는 사람으로 좁힌다.
  const assignees = useAssigneeOptions(true, state.project);
  const assigneeOptions = React.useMemo(
    () =>
      ((assignees.data && assignees.data.assignees) || []).map((a) => ({
        value: a.user_id,
        label: a.display_name,
      })),
    [assignees.data]
  );
  // 회의록에 걸 티켓 후보 — **이 회차에 담긴 티켓**이다(`body.tickets`).
  const ticketOptions = React.useMemo(() => {
    if (!body) return [];
    return (body.tickets || [])
      .filter((row) => row && row.id)
      .map((row) => ({ value: row.id, label: `${row.key || ""} ${row.title || ""}`.trim() }));
  }, [body]);
  // 서버 _editable_or_403 과 같은 판정 — 못 누를 단추를 안 보여 준다.
  const canEditDecision = React.useCallback(
    (row) => {
      const myId = auth.data && auth.data.id;
      return roleCanPlan || (myId && (row.author_user_id === myId || row.assignee_user_id === myId));
    },
    [auth.data, roleCanPlan]
  );
  // 감사자는 회의를 읽기만 한다 — 서버(`_ensure_not_read_only`)와 같은 판정.
  const readOnly = !!(auth.data && auth.data.role === "auditor");

  /* 작성 중인 회의록 — 회차별 초안(D-483). 회차를 안 골랐으면 저장하지 않는다. */
  const [draft, setDraft, clearDraft] = useSessionDraft(
    sprintId ? `cv.meetingDraft.v1:${sprintId}` : null,
    EMPTY_DRAFT,
  );

  const createSprint = useMutation({
    mutationFn: (payload) => api("/api/work/sprints", { method: "POST", body: payload }),
    onSuccess: (sprint) => {
      qc.invalidateQueries({ queryKey: ["work-sprints"] });
      setSprintFormOpen(false);
      setState({ sprint: sprint.id });
      toast("회차를 추가했습니다.", "success");
    },
    onError: (e) =>
      toast((e && e.message) || "회차를 추가하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  /* 회의록만 캐시에서 수술한다 — 체크 한 번에 `/meeting` 전체를 다시 읽을 이유가 없다.
     캐시는 **원본 응답**을 들고(select 가 읽을 때 정규화한다) 원본 모양으로 고친다. */
  const meetingKey = React.useMemo(() => ["sprint-meeting", sprintId, state.project], [sprintId, state.project]);
  const patchDecisions = React.useCallback(
    (updater) => {
      qc.setQueryData(meetingKey, (old) =>
        old ? { ...old, decisions: updater(old.decisions || []) } : old
      );
    },
    [qc, meetingKey]
  );

  /* 회의록은 「내용」 칸의 Enter 로도 적힌다(`DecisionComposer` 의 폼 제출). 그 제출에는 진행 중 가드가 없고 「적기」가
     꺼지는 것은 다음 렌더의 일이라, 그 전에 온 둘째 제출이 같은 기록을 한 번 더 남겼다. 같은 기록은 끝나기 전에 한 번만
     보낸다(`useGuardedMutation`). */
  const addDecision = useGuardedMutation({
    mutationFn: (payload) =>
      api(`/api/work/sprints/${encodeURIComponent(sprintId)}/decisions`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: (row) => {
      patchDecisions((list) => [...list, row]);
      // 다른 프로젝트 필터의 캐시도 회의록은 같다 — 다음에 읽을 때 새로 온다.
      qc.invalidateQueries({ queryKey: ["sprint-meeting", sprintId], refetchType: "none" });
      clearDraft();
      toast("회의 기록을 남겼습니다.", "success");
    },
    onError: (e) => toast((e && e.message) || "적지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  const editDecision = useMutation({
    mutationFn: ({ id, patch }) =>
      api(`/api/work/decisions/${encodeURIComponent(id)}`, { method: "PATCH", body: patch }),
    onMutate: async ({ id, patch }) => {
      if (!("done" in patch)) return undefined;
      await qc.cancelQueries({ queryKey: meetingKey });
      const prev = qc.getQueryData(meetingKey);
      patchDecisions((list) =>
        list.map((d) => (d.id === id ? { ...d, done: patch.done } : d))
      );
      return { prev };
    },
    onError: (e, _vars, ctx) => {
      if (ctx && ctx.prev) qc.setQueryData(meetingKey, ctx.prev);
      toast((e && e.message) || "수정하지 못했습니다. 다시 시도해 주세요.", "error");
    },
    onSuccess: (row) => {
      patchDecisions((list) => list.map((d) => (d.id === row.id ? row : d)));
    },
  });
  const removeDecision = useMutation({
    mutationFn: (id) =>
      api(`/api/work/decisions/${encodeURIComponent(id)}`, { method: "DELETE" }),
    onSuccess: (_res, id) => {
      patchDecisions((list) => list.filter((d) => d.id !== id));
      toast("회의 기록을 삭제했습니다.", "success");
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  /** 이 회차를 작업 보드에서 연다 — 팀·회차 문맥을 그대로 싣는다. */
  const openBoard = React.useCallback(
    (extra) => {
      navigate("/work-board?" + qs({ team: teamId, sprint: sprintId, ...(extra || {}) }));
    },
    [navigate, teamId, sprintId]
  );

  const burndown = body ? burndownSeries(body.burndown) : null;
  const scopeTrend = body ? scopeTrendSeries(body.scope) : null;
  const workload = body ? workloadItems(body.workload) : null;
  const summary = body ? body.summary : null;
  const band = body && body.health ? healthBand(body.health.score) : null;

  const discussKey = state.discuss || DISCUSS_TABS[0].key;
  const tab = DISCUSS_TABS.find((t) => t.key === discussKey) || DISCUSS_TABS[0];
  const setDiscussTab = React.useCallback((key) => setState({ discuss: key === DISCUSS_TABS[0].key ? "" : key }), [setState]);
  // 서버가 아직 새 갈래를 모르는 순간(배포 사이)에도 화면이 안 죽는다.
  const bucket = body ? (body.discuss[tab.key] || { items: [], total: 0, truncated: false }) : null;
  const teamOptionsForForm = React.useMemo(
    () => teamOptions.filter((o) => o.manageable).map((o) => ({ value: o.id, label: teamLabelOf(o) })),
    [teamOptions],
  );
  const noTeamAtAll = sprints.isSuccess && teamOptions.length === 0;
  const needTeamPick = sprints.isSuccess && !teamId && !(team && team.selected) && teamOptions.length > 0;
  const sprintsReady = !!teamId && !sprints.isLoading && !sprints.isError;

  return (
    <>
      <PageHeader
        area="팀 업무"
        title="스프린트 회의"
        crumbRoot={null}
        description="팀의 회차가 계획대로 가고 있는지 함께 보고, 다음에 할 일을 정합니다."
        help={"회차를 구성하는 일은 작업 보드에서 합니다. "
          + "여기서는 남은 일과 막힌 일을 보고, 결정과 할 일을 적습니다. "
          + "다 되면 「회차 닫기」로 안 끝난 일을 다음 회차로 넘깁니다."}
      />

      {/* 문맥 줄 — 어느 팀의 어느 회차를 리뷰하는가. 작업 보드와 같은 부품이고 같은 칸이다(팀 · 회차 모두 값이 긴 축이라
          wide 칸, D-497). 조건 줄이 없다 — 이 둘은 목록을 좁히는 조건이 아니라 회의의 문맥이다. */}
      <ContextBar
        context={(
          <>
            <TeamSelect team={team} value={teamId} onChange={changeTeam} loading={sprints.isLoading} />
            {/* 주소의 회차가 이 팀 목록에 없으면(지워졌거나 잘못 적힌 주소) 칸에 원시 id 를 쓰지 않는다 — 「none-r23」 같은 값이
                회차 이름처럼 보였다(r23 #50). 그 회차를 못 찾았다는 사실은 아래 판(404)이 말한다. */}
            <EntityCombobox
              size="wide"
              label="회차"
              value={sprintsReady && sprintId && !sprintRows.some((s) => s.id === sprintId) ? "" : sprintId}
              onChange={(next) => setState({ sprint: next || "", discuss: "" })}
              loading={sprints.isLoading}
              disabled={!teamId}
              options={sprintRows.map((s) => ({
                value: s.id,
                label: `${s.name} (${sprintStateLabel(s)})`,
                secondary: `${s.starts_on} ~ ${s.ends_on}`,
              }))}
              allLabel="회차 선택"
            />
            {/* 회차를 고르기 전에는 「최근 회차 열기」가 회차 칸 바로 옆에 선다 — 고를 칸과 여는 단추가 한 묶음이다. 예전에는 화면
                가운데 안내판 안에 있어 회차 칸에서 200px 아래로 떨어져 있었다(r23 화면 대장 19). */}
            {sprintsReady && !sprintId && sprintRows.length > 0 ? (
              <Button variant="primary" onClick={() => setState({ sprint: sprintRows[0].id })}>최근 회차 열기</Button>
            ) : null}
          </>
        )}
      />

      {meeting.isLoading || (sprints.isLoading && !sprintId) ? (
        <Stack spacing={2}>
          <Skeleton kind="section" />
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: MEETING_PAIR_TRACKS }}>
            <Skeleton kind="chart" />
            <Skeleton kind="chart" />
          </Box>
          <Skeleton kind="section" />
        </Stack>
      ) : null}
      {meeting.isError ? <ErrorState layout="region" error={meeting.error} onRetry={meeting.refetch} /> : null}
      {sprints.isError ? <ErrorState layout="region" error={sprints.error} onRetry={sprints.refetch} /> : null}

      {noTeamAtAll ? (
        <EmptyState
          layout="page"
          title="회차를 볼 수 있는 팀이 없습니다."
          help="소속 팀이 정해지면 그 팀의 회차와 회의가 여기 보입니다. 소속은 관리자가 지정할 수 있습니다."
        />
      ) : null}
      {needTeamPick ? (
        <EmptyState
          layout="page"
          title="팀을 골라 주세요."
          help="회차는 팀이 운영합니다. 위 팀 칸에서 팀을 고르면 그 팀의 회차로 회의를 시작할 수 있습니다."
        />
      ) : null}
      {sprintsReady && !sprintId && sprintRows.length === 0 ? (
        <EmptyState
          layout="page"
          title="등록된 회차가 없습니다."
          help="회차를 추가하면 여기서 번다운과 건강, 담당자별 남은 일을 보고 회의를 진행할 수 있습니다."
          action={
            <>
              {canPlan ? (
                <Button variant="primary" onClick={() => setSprintFormOpen(true)}>회차 추가</Button>
              ) : null}
              <Button variant="secondary" onClick={() => openBoard({ tab: "backlog" })}>백로그 보기</Button>
            </>
          }
        />
      ) : null}
      {sprintsReady && !sprintId && sprintRows.length > 0 ? (
        /* 안내는 문맥 줄 바로 아래 판 안이다 — 여는 단추는 위 회차 칸 옆에 있다. */
        <Card data-sprint-pick-hint="">
          <EmptyState
            layout="region"
            title="회의 회차를 선택하세요."
            help="회차를 선택하면 회의 내용을 확인할 수 있습니다. 열려 있는 회차가 있으면 자동으로 고릅니다."
            action={canPlan ? <Button variant="secondary" onClick={() => setSprintFormOpen(true)}>회차 추가</Button> : null}
          />
        </Card>
      ) : null}

      {body ? (
        <Box
          aria-busy={meeting.isPlaceholderData || undefined}
          sx={{
            opacity: meeting.isPlaceholderData ? 0.55 : 1,
            transition: "opacity 120ms ease",
          }}
        >
          {/* 1 — 회차 개요. 어느 팀의 어느 회차인가가 첫 줄이다 — 팀 A 의 「9-2」와 팀 B 의
              「9-2」는 다른 회차라 이름만으로는 어느 회의인지 알 수 없다. */}
          <Section title="회차 개요" rule>
            <Box sx={{ ...LANE_SURFACE, p: PANEL_SURFACE.p }}>
              <Stack
                direction="row" flexWrap="wrap" gap={1} alignItems="center"
                justifyContent="space-between"
              >
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", ...KO_WORD_BREAK }}>
                    {body.team
                      ? (body.team.path || []).map((n) => n.name).join(" › ") || body.team.name
                      : "팀이 정해지지 않은 회차"}
                  </Typography>
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                    <Typography component="h3" variant="sectionTitle" sx={{ ...KO_WORD_BREAK }}>
                      {body.sprint.name}
                    </Typography>
                    <SprintStateBadge sprint={body.sprint} />
                  </Stack>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, ...KO_WORD_BREAK }}>
                    {`${datedLabel(body.sprint.starts_on)} ~ ${datedLabel(body.sprint.ends_on)}, 오늘 ${datedLabel(body.today)}`}
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
                {/* 단추 묶음은 줄 폭을 넘지 않는다(r23 390 가로 넘침) — `flexShrink: 0` 이면 둘째 줄로 내려가서도 내용 폭(단추 다섯, 약 420px)을
                    고집해 390 화면이 가로로 38px 넘쳤다. 넓은 화면에서는 한 줄에 다 들어가 줄지 않는다. */}
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ minWidth: 0, maxWidth: "100%" }}>
                  {/* 앞뒤 회차는 서버가 준다(같은 팀 안에서). 화면이 목록에서 스스로 찾으면 두 곳의 정렬이 갈린다. */}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!body.neighbours.prev}
                    onClick={() => setState({ sprint: body.neighbours.prev.id, discuss: "" })}
                  >
                    이전 회차
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={!body.neighbours.next}
                    onClick={() => setState({ sprint: body.neighbours.next.id, discuss: "" })}
                  >
                    다음 회차
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => openBoard()}>
                    작업 보드에서 보기
                  </Button>
                  <SprintLifecycle
                    sprint={body.sprint}
                    sprints={sprintRows}
                    size="sm"
                    canPlan={canPlan}
                    teams={teamOptionsForForm}
                    onDeleted={() => setState({ sprint: "" })}
                  />
                </Stack>
              </Stack>
            </Box>
          </Section>

          {/* 2 — 현재 진행 상황. 숫자 셋은 **읽는 것**이다 — 누르면 어디로 가는 단추가 아니다.
              그래서 어디로도 안 간다고 캡션이 말한다. */}
          <Section title="현재 진행 상황" rule>
            <StatusKpiStrip
              ariaLabel="이번 회차 요약"
              revealKey="sprint-meeting:kpi"
              sx={{ mb: 2 }}
              note="회차 전체의 숫자입니다. 아래 프로젝트 필터는 논의 목록만 좁힙니다."
              items={[
                { label: "전체", value: String(summary.total), primary: true },
                {
                  label: "완료", value: String(summary.done), kind: "ok",
                  pct: summary.total ? Math.round((summary.done / summary.total) * 100) : 0,
                },
                { label: "진행 중", value: String(summary.in_progress), kind: "info" },
              ]}
            />
            {/* 둘 다 그릴 것이 없는 회차(담긴 티켓이 없다)는 짝 판 높이를 맞추지 않는다 — 예전에는 230px 빈 흰 면 둘에 문장 하나씩만
                남았다(r23 #51). */}
            <Box sx={!burndown && !body.health ? PAIR_GRID_NATURAL : PAIR_GRID}>
              <Section flush title="번다운" rule sx={{ flex: 1 }} titleAs="h4">
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
                      예상 WD가 적힌 티켓이 있어야 번다운을 그릴 수 있습니다. 아래 「예상 WD 없음」에서 채울 수 있습니다.
                    </Typography>
                  )}
                </Box>
              </Section>
              <Section flush title="회차 건강" rule sx={{ flex: 1 }} titleAs="h4">
                <Box sx={{ ...PANEL_SURFACE, flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: 0 }}>
                  <Stack spacing={1.5} alignItems="center" sx={{ width: "100%" }}>
                    {/* 게이지가 이 판의 주인이다 — 크게, 한가운데. 점수와 밴드가 링 안에 서고
                        깎인 이유는 그 아래 한 줄이다. 점수가 없으면(담긴 티켓이 없다) 점선 원 대신 문장 하나다(r23 #51). */}
                    {body.health ? (
                    <Gauge
                      value={body.health ? body.health.score : null}
                      size="11rem"
                      thickness={8}
                      centerSize="readout"
                      centerText={body.health ? String(body.health.score) : undefined}
                      centerCaption={band ? band.label : undefined}
                      label={body.health ? (healthCuts(summary) || "지연과 차단이 없습니다.") : "지연과 차단을 반영한 점수입니다."}
                      emptyLabel="담긴 티켓이 없어 아직 재지 않았습니다."
                      revealKey={body.sprint.id}
                    />
                    ) : (
                      <Typography variant="body2" color="text.secondary" sx={{ alignSelf: "flex-start", ...KO_WORD_BREAK }}>
                        담긴 티켓이 없어 아직 재지 않았습니다.
                      </Typography>
                    )}
                    {body.health ? (
                      <Stack spacing={1} sx={{ width: "100%" }}>
                        {/* 막대가 값을 스스로 적는다 — 라벨은 이름만. 위 요약 줄과 **같은
                            낱말**(진도율·기간 경과율)이다. */}
                        <ProgressBar
                          percent={body.health.progress_pct}
                          label="진도율"
                          revealKey={body.sprint.id}
                        />
                        <ProgressBar
                          percent={body.health.elapsed_pct}
                          label="기간 경과율"
                          color="neutral"
                          revealKey={body.sprint.id}
                        />
                      </Stack>
                    ) : null}
                  </Stack>
                </Box>
              </Section>
            </Box>
          </Section>

          {/* 3 — 이번 회차 논의 항목(회차의 지금 상태로 센다 — 「오늘」이 아니다). 프로젝트 필터는 **여기만** 좁힌다. */}
          <Section
            title="이번 회차 논의 항목"
            help="항목을 누르면 그 티켓이 아래에 나옵니다. 줄을 누르면 미리 보기가 열립니다."
            rule
          >
            <Stack direction="row" flexWrap="wrap" gap={1} alignItems="center" sx={{ mb: 1.5 }}>
              <EntityCombobox
                label="프로젝트"
                value={state.project}
                onChange={(next) => setState({ project: next || "" })}
                loading={projects.isLoading}
                options={projectOptions}
                allLabel="전체"
                sx={{ minWidth: "14rem" }}
              />
              <Typography variant="caption" color="text.secondary" sx={{ ...KO_WORD_BREAK }}>
                이 필터는 논의 목록만 좁힙니다.
              </Typography>
            </Stack>
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
                maxHeight: MEETING_LIST_MAX, overflowY: "auto",
              }}
            >
              {bucket.items.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  {body.discuss_project_id ? "선택한 프로젝트에는 이 항목에 든 티켓이 없습니다." : tab.empty}
                </Typography>
              ) : (
                <Box
                  sx={{
                    display: "grid", gap: 1,
                    gridTemplateColumns: { xs: "1fr", xl: "repeat(2, minmax(0, 1fr))" },
                  }}
                >
                  {bucket.items.map((row) => (
                    <DiscussRow
                      key={row.id || row.ticket_id}
                      row={row}
                      onOpen={peek.open}
                      signals={signalsOf(row)}
                      showProject={!state.project}
                    />
                  ))}
                  {bucket.truncated ? (
                    <Typography variant="caption" color="text.secondary" sx={{ gridColumn: "1 / -1" }}>
                      {`전체 ${bucket.total}건 중 ${bucket.items.length}건 표시`}
                    </Typography>
                  ) : null}
                </Box>
              )}
            </Box>
            {/* 편성은 작업 보드의 일이다(D-484). 회의에서 「빼기」를 누르던 자리에 그 사실과
                가는 길을 둔다. */}
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
              {/* 편성할 수 없는 사람에게 「담거나 빼는 일」을 말하지 않는다 — 그 사람이 판에서
                  할 수 있는 일은 옮기고 순서를 바꾸는 것이다. 단추 이름도 그 일에 맞춘다. */}
              <Typography variant="caption" color="text.secondary">
                {canPlan
                  ? "티켓을 담거나 빼는 일은 작업 보드에서 합니다."
                  : "티켓을 옮기거나 순서를 바꾸는 일은 작업 보드에서 합니다."}
              </Typography>
              <Button variant="ghost" size="sm" onClick={() => openBoard()}>
                {canPlan ? "작업 보드에서 회차 관리" : "작업 보드로 가기"}
              </Button>
            </Stack>
          </Section>

          {/* 4 — 업무량과 범위 변경. 회차 전체다. */}
          <Section title="업무량과 범위 변경" rule>
            <Box sx={PAIR_GRID_NATURAL}>
              <Section flush title="담당자별 남은 WD" rule sx={{ flex: 1 }} titleAs="h4">
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
                      담당자가 지정된 남은 티켓이 없습니다.
                    </Typography>
                  )}
                </Box>
              </Section>
              <Section flush title="범위 변경" rule sx={{ flex: 1 }} titleAs="h4">
                <Box sx={{ ...PANEL_SURFACE, flex: 1, minHeight: 0 }}>
                  {body.scope.tracked ? (
                    <Stack spacing={1}>
                      <Typography variant="body2">
                        {`회차가 시작한 뒤 ${body.scope.added}건이 추가되고 ${body.scope.removed}건이 제외되었습니다.`}
                      </Typography>
                      {scopeTrend ? (
                        <LineSeries
                          series={scopeTrend.series}
                          labels={scopeTrend.labels}
                          unit="건"
                          question="회차 중에 티켓이 언제 추가되고 제외되었는지 봅니다."
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
          </Section>

          {/* 5 — 회의 결정과 다음 할 일 */}
          <Section
            title="회의 결정과 다음 할 일"
            help="회의에서 정한 내용과 할 일을 적어 두면 다음에 다시 열어도 남습니다."
            rule
          >
            {readOnly ? (
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                감사자는 회의록을 읽기만 할 수 있습니다.
              </Typography>
            ) : (
              <Box sx={{ ...PANEL_SURFACE, mb: 2 }}>
                <DecisionComposer
                  busy={addDecision.isPending}
                  draft={draft}
                  onDraftChange={setDraft}
                  assigneeOptions={assigneeOptions}
                  ticketOptions={ticketOptions}
                  onAdd={(payload) => addDecision.mutate(payload)}
                />
              </Box>
            )}
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
                  empty: "등록된 결정이 없습니다.",
                },
                {
                  kind: KIND_ACTION,
                  title: "할 일",
                  help: "다음에 해야 할 일을 적고, 끝나면 체크합니다.",
                  empty: "등록된 할 일이 없습니다.",
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
                      maxHeight: MEETING_LIST_MAX,
                      overflowY: "auto",
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    {/* 레인 머리는 판 제목 정본이다 — 이름 · 도움말 한 쌍과 오른쪽 건수 칩(계획 표 5 허용 치환). */}
                    <SectionTitle spacing="tight"
                      component="h4"
                      title={lane.title}
                      help={lane.help}
                      action={<CountChip value={rows.length} />}

                    />
                    {rows.length === 0 ? (
                      <Box sx={{ mt: "auto" }}>
                        <EmptyState layout="inline" title={lane.empty} />
                      </Box>
                    ) : (
                      <Stack spacing={1}>
                        {rows.map((row) => (
                          <DecisionRow
                            key={row.id}
                            row={row}
                            inLane
                            onToggle={readOnly ? () => {} : (r, done) => editDecision.mutate({ id: r.id, patch: { done } })}
                            onOpenTicket={(r) => peek.open(r.ticket_page_id)}
                            onEdit={!readOnly && canEditDecision(row) ? (r) => setEditingDecision(r) : undefined}
                            onDelete={
                              !readOnly && canEditDecision(row)
                                ? async (r) => {
                                    const ok = await confirm(
                                      "삭제한 회의 기록은 되돌릴 수 없습니다. 이 기록을 삭제할까요?",
                                      { danger: true, confirmLabel: "삭제" }
                                    );
                                    if (ok) removeDecision.mutate(r.id);
                                  }
                                : undefined
                            }
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
        open={!!editingDecision}
        title="회의 기록 수정"
        submitLabel="저장"
        fields={
          editingDecision && editingDecision.kind === KIND_ACTION
            ? [
                { name: "body", label: "내용", type: "textarea", required: true, maxLength: 2000 },
                {
                  name: "assignee_user_id", label: "담당자", type: "entity",
                  options: assigneeOptions, emptyLabel: "아직 미정",
                },
                { name: "due_date", label: "마감", type: "date" },
              ]
            : [{ name: "body", label: "내용", type: "textarea", required: true, maxLength: 2000 }]
        }
        initial={
          editingDecision
            ? {
                body: editingDecision.body || "",
                assignee_user_id: editingDecision.assignee_user_id || "",
                due_date: editingDecision.due_date || "",
              }
            : null
        }
        onSubmit={(values) => {
          const patch =
            editingDecision.kind === KIND_ACTION
              ? {
                  body: values.body,
                  assignee_user_id: values.assignee_user_id || null,
                  due_date: values.due_date || null,
                }
              : { body: values.body };
          return editDecision
            .mutateAsync({ id: editingDecision.id, patch })
            .then(() => setEditingDecision(null));
        }}
        onClose={() => setEditingDecision(null)}
      />
      <FormModal
        open={sprintFormOpen}
        title="새 회차"
        submitLabel="추가"
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

      {/* 티켓 미리보기 — 회의를 떠나지 않고 티켓 하나를 확인한다(D-483). 편성 단추는 없다. */}
      <TicketPeek
        pageId={peek.pageId}
        onClose={peek.close}
        onDetail={peek.detail}
        from="/sprint"
        sprints={sprintRows}
        quickEdit={!readOnly}
      />
    </>
  );
}
