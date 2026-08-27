import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Callout,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  FormModal,
  MetricStrip,
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
import { burndownSeries, workloadItems } from "./sprint-charts.js";
import { SPRINT_FIELDS } from "./sprint-fields.js";
import { useQueryState } from "../lib/useQueryState.js";
import { useTicketProjects } from "./ticket-options.js";
import { useTicketSignals } from "../lib/ticketSignals.js";
import { TicketSignals } from "../ui/TicketSignals.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { DateField } from "../ui/DateField.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { priorityKind, priorityKo } from "../lib/priority.js";
import { KO_WORD_BREAK } from "../ui/theme.js";

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

/** 「오늘 논의할 항목」의 다섯 갈래. 순서는 회의에서 말하는 순서다 — 급한 것부터. */
const DISCUSS_TABS = [
  { key: "overdue", label: "지연", empty: "지연된 티켓이 없습니다." },
  { key: "blocked", label: "차단", empty: "차단된 티켓이 없습니다." },
  { key: "unassigned", label: "미할당", empty: "담당자가 비어 있는 티켓이 없습니다." },
  { key: "due_soon", label: "마감 임박", empty: "곧 마감인 티켓이 없습니다." },
  { key: "scope_changes", label: "범위 변경", empty: "회차가 시작한 뒤 드나든 티켓이 없습니다." },
];

const SPRINT_SPEC = { project: "", sprint: "" };

/** 담당자 얼굴 줄. 판의 카드와 **같은 부품**을 쓴다 (지시 6). */
function People({ row }) {
  const people = Array.isArray(row.assignees) ? row.assignees : [];
  if (!people.length) {
    return (
      <Typography variant="caption" color="text.secondary">
        {row.assignee_tokens > 0 ? "읽지 못함" : "없음"}
      </Typography>
    );
  }
  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.375, minWidth: 0 }}>
      {people.slice(0, 3).map((p) => (
        <UserAvatar key={p.user_id || p.display_name} person={p} size="sm" label={p.display_name} />
      ))}
      {people.length > 3 ? (
        <Typography variant="caption" color="text.secondary">
          {`외 ${people.length - 3}명`}
        </Typography>
      ) : null}
    </Box>
  );
}

/** 논의 목록 한 줄. 누르면 그 티켓으로 간다 — 「관련 티켓으로 바로 이동」이 요구다. */
function DiscussRow({ row, onOpen, signals }) {
  return (
    <Card
      sx={{
        p: 1, display: "grid", gap: 1, alignItems: "center", cursor: "pointer",
        gridTemplateColumns: { xs: "1fr", md: "6rem minmax(0, 1fr) 7rem 8rem" },
      }}
      onClick={() => onOpen(row)}
    >
      <Typography variant="caption" color="text.secondary">
        {row.key || row.ticket_id || "이름 없음"}
      </Typography>
      <Box sx={{ minWidth: 0, display: "flex", alignItems: "center", gap: 0.75 }}>
        <Typography variant="body2" sx={{ ...KO_WORD_BREAK }}>
          {row.title || "제목 없음"}
        </Typography>
        <TicketSignals signals={signals} variant="mark" />
      </Box>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ textAlign: "center", fontVariantNumeric: "tabular-nums" }}
      >
        {row.due || (row.direction === "added" ? "들어옴" : row.direction === "removed" ? "빠짐" : "-")}
      </Typography>
      <Box sx={{ display: "flex", justifyContent: "center" }}>
        {row.assignees || row.assignee_tokens != null ? <People row={row} /> : null}
      </Box>
    </Card>
  );
}

/** 회의록 한 줄. 결정과 할 일이 **같은 목록**에 시간순으로 선다. */
function DecisionRow({ row, onToggle, onDelete, onOpenTicket }) {
  return (
    <Card sx={{ p: 1.25, display: "flex", alignItems: "flex-start", gap: 1 }}>
      <Checkbox
        size="small"
        checked={!!row.done}
        onChange={(e) => onToggle(row, e.target.checked)}
        inputProps={{ "aria-label": `${row.body} 완료 여부` }}
        sx={{ p: 0.5 }}
      />
      <Box sx={{ minWidth: 0, flex: 1 }}>
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0, mb: 0.25 }}>
          <Badge
            value={row.kind === KIND_ACTION ? "할 일" : "결정"}
            kind={row.kind === KIND_ACTION ? "info" : "neutral"}
          />
          {row.ticket_page_id ? (
            <Button variant="ghost" size="sm" onClick={() => onOpenTicket(row)}>
              {row.ticket_key || "티켓 열기"}
            </Button>
          ) : null}
        </Stack>
        <Typography
          variant="body2"
          sx={{
            ...KO_WORD_BREAK,
            /* 끝난 줄은 흐리게 둔다. 지우지 않는 이유는 회의록이기 때문이다 — 「했다」도
               기록이고, 지우면 다음 회의에서 그 일이 있었다는 사실 자체가 사라진다. */
            color: row.done ? "text.secondary" : "text.primary",
            textDecoration: row.done ? "line-through" : "none",
          }}
        >
          {row.body}
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.25 }}>
          {row.assignee ? <UserAvatar person={row.assignee} size="sm" label={row.assignee.display_name} /> : null}
          <Typography variant="caption" color="text.secondary">
            {[
              row.assignee ? row.assignee.display_name : null,
              row.due_date ? `마감 ${row.due_date}` : null,
            ].filter(Boolean).join("  ") || "담당자와 마감은 아직 정하지 않았습니다."}
          </Typography>
        </Stack>
      </Box>
      <Button variant="ghost" size="sm" onClick={() => onDelete(row)}>
        삭제
      </Button>
    </Card>
  );
}

/** 회의록을 적는 줄. 화면 아래가 아니라 목록 **위**에 둔다 — 회의 중에 쓰는 칸이다. */
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
    <Box component="form" onSubmit={submit} sx={{ display: "flex", flexWrap: "wrap", gap: 1, mb: 1.5 }}>
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
        sx={{ flex: "1 1 20rem" }}
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
    </Box>
  );
}

export function Sprint() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const signalsOf = useTicketSignals();
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

  /* 회차를 안 골랐으면 **열려 있는 회차**를 고른다. 회의를 여는 사람이 매번 목록에서
     같은 것을 다시 고르게 하지 않는다. 열린 회차가 없으면 가장 최근 회차다. */
  React.useEffect(() => {
    if (state.sprint || !sprintRows.length) return;
    const active = sprintRows.find((s) => s.state === "active");
    setState({ sprint: (active || sprintRows[0]).id }, { replace: true });
  }, [state.sprint, sprintRows, setState]);

  const meeting = useQuery({
    queryKey: ["sprint-meeting", state.sprint],
    queryFn: () => api(`/api/work/sprints/${encodeURIComponent(state.sprint)}/meeting`),
    enabled: !!state.sprint,
  });
  const body = meeting.data;

  function refreshMeeting() {
    qc.invalidateQueries({ queryKey: ["sprint-meeting"] });
  }

  const createSprint = useMutation({
    mutationFn: (body) => api("/api/work/sprints", { method: "POST", body }),
    onSuccess: (sprint) => {
      qc.invalidateQueries({ queryKey: ["work-sprints"] });
      setSprintFormOpen(false);
      // 만든 회차를 바로 연다 — 안 열면 「만들었는데 아무 일도 안 일어난」 것으로 보인다.
      setState({ sprint: sprint.id });
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

  const burndown = body ? burndownSeries(body.burndown) : null;
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
    [addToSprint]
  );

  const tab = DISCUSS_TABS.find((t) => t.key === discussTab) || DISCUSS_TABS[0];
  const bucket = body ? body.discuss[tab.key] : null;

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
            options={((projects.data && projects.data.projects) || []).map((p) => ({
              value: p.id,
              label: p.name,
            }))}
            allLabel="전체"
            sx={{ minWidth: "14rem" }}
          />
          <EntityCombobox
            label="스프린트"
            value={state.sprint}
            onChange={(next) => setState({ sprint: next || "" })}
            loading={sprints.isLoading}
            options={sprintRows.map((s) => ({
              value: s.id,
              label: s.name,
              secondary: `${s.starts_on} ~ ${s.ends_on}`,
            }))}
            allLabel="고르세요"
            sx={{ minWidth: "16rem" }}
          />
        </FilterRow>
      </FilterSurface>

      {meeting.isLoading ? <Skeleton kind="section" /> : null}
      {meeting.isError ? <ErrorState error={meeting.error} onRetry={meeting.refetch} /> : null}
      {!state.sprint && !sprints.isLoading && sprintRows.length === 0 ? (
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

      {body ? (
        <>
          <Callout
            tone="info"
            title={body.sprint.name}
            detail={body.sprint.goal || undefined}
            detailLabel="회차 목표"
          >
            {`${body.sprint.starts_on}부터 ${body.sprint.ends_on}까지의 회차를 봅니다. 오늘은 ${body.today}입니다.`}
          </Callout>

          {/* 1 — 정상 진행인가 */}
          <MetricStrip
            ariaLabel="이번 회차 요약"
            sx={{ mb: 2 }}
            items={[
              { label: "전체", value: String(summary.total), primary: true },
              { label: "완료", value: String(summary.done) },
              { label: "진행 중", value: String(summary.in_progress) },
              { label: "지연", value: String(summary.overdue), kind: summary.overdue ? "danger" : undefined },
              { label: "차단", value: String(summary.blocked), kind: summary.blocked ? "danger" : undefined },
              { label: "이슈", value: String(summary.issue), kind: summary.issue ? "warn" : undefined },
              { label: "남은 WD", value: String(summary.remaining_wd) },
            ]}
          />

          <Box
            sx={{
              display: "grid", gap: 2, mb: 2,
              gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 2fr) minmax(0, 1fr)" },
            }}
          >
            <Section title="번다운" rule>
              {burndown ? (
                <LineSeries
                  series={burndown.series}
                  labels={burndown.labels}
                  unit="인일"
                  summary={burndown.summary}
                  question="이 회차가 계획대로 줄고 있는지 봅니다."
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  마감일과 예상 WD 가 적힌 티켓이 있어야 번다운을 그릴 수 있습니다.
                </Typography>
              )}
            </Section>
            <Section title="회차 건강" rule>
              <Stack spacing={1.5} alignItems="center">
                <Gauge
                  value={body.health ? body.health.score : null}
                  label="지연과 차단을 반영한 점수입니다."
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
            </Section>
          </Box>

          {/* 2 — 어떤 티켓이 문제인가 */}
          <Section title="오늘 논의할 항목" rule>
            <Tabs
              value={tab.key}
              onChange={(_e, v) => setDiscussTab(v)}
              aria-label="논의 항목 선택"
              variant="scrollable"
              scrollButtons="auto"
              sx={{ mb: 1.5 }}
            >
              {DISCUSS_TABS.map((t) => (
                <Tab
                  key={t.key}
                  value={t.key}
                  label={`${t.label} ${body.discuss[t.key].total}`}
                />
              ))}
            </Tabs>
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
                  />
                ))}
                {bucket.truncated ? (
                  <Typography variant="caption" color="text.secondary">
                    {`${bucket.total}건 가운데 앞의 ${bucket.items.length}건만 보여 줍니다.`}
                  </Typography>
                ) : null}
              </Stack>
            )}
          </Section>

          {/* 3 · 4 — 업무량과 범위 변경 */}
          <Box
            sx={{
              display: "grid", gap: 2, mb: 2,
              gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 2fr) minmax(0, 1fr)" },
            }}
          >
            <Section title="담당자별 남은 WD" rule>
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
            </Section>
            <Section title="범위 변경" rule>
              {/* 「기록이 없다」와 「안 바뀌었다」는 다른 사실이다. 0 으로 적으면 화면이
                  안정된 회차라고 말하는데, 실은 아무것도 모르는 것이다. */}
              {body.scope.tracked ? (
                <Stack spacing={1}>
                  <Typography variant="body2">
                    {`회차가 시작한 뒤 ${body.scope.added}건이 들어오고 ${body.scope.removed}건이 빠졌습니다.`}
                  </Typography>
                  {/* REAUDIT §15.2 — 여섯 번째 ECharts 그림. 들어온 건수와 빠진 건수를 나란히
                      비교한다. 새 API(일자별 시계열)를 만들지 않고 이미 있는 두 집계값을
                      막대로 낸다 — 이미 마이그레이션한 BarSeries 를 그대로 재사용한다. */}
                  {body.scope.added > 0 || body.scope.removed > 0 ? (
                    <BarSeries
                      question="이번 회차 동안 범위가 얼마나 드나들었는지 봅니다."
                      unit="건"
                      items={[
                        { label: "들어옴", value: body.scope.added },
                        { label: "빠짐", value: body.scope.removed, color: body.scope.removed > 0 ? "warn" : undefined },
                      ]}
                    />
                  ) : null}
                  <Typography variant="caption" color="text.secondary">
                    어떤 티켓이 드나들었는지는 위 논의 항목 탭에서 볼 수 있습니다.
                  </Typography>
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  이 회차에는 드나든 기록이 없어서 범위가 얼마나 바뀌었는지 알 수 없습니다.
                </Typography>
              )}
            </Section>
          </Box>

          {/* 5 — 무엇을 더 넣을까 */}
          <Section
            title="이번 회차 후보"
            help="어느 회차에도 담기지 않은 티켓입니다. 「추가」를 누르면 이번 회차로 들어옵니다."
            rule
          >
            <DataTable
              columns={candidateColumns}
              rows={body.candidates}
              rowKey={(r) => r.id}
              onRow={openTicket}
              empty="담을 수 있는 백로그 티켓이 없습니다."
            />
          </Section>

          {/* 6 — 무엇을 정했나 */}
          <Section
            title="회의 결정과 다음 할 일"
            help="여기 적은 것은 화면을 닫아도 남습니다."
            rule
          >
            <DecisionComposer
              busy={addDecision.isPending}
              onAdd={(payload, reset) =>
                addDecision.mutate(payload, { onSuccess: reset })
              }
            />
            {body.decisions.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                아직 적은 것이 없습니다.
              </Typography>
            ) : (
              <Stack spacing={1}>
                {body.decisions.map((row) => (
                  <DecisionRow
                    key={row.id}
                    row={row}
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
          </Section>
        </>
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
            project_id: state.project || null,
            goal: values.goal || null,
          })
        }
        onClose={() => setSprintFormOpen(false)}
      />
    </>
  );
}
