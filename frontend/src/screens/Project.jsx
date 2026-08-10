import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import {
  Badge, Button, Callout, Card, EmptyState, ErrorState, FormModal, PageHeader,
  Skeleton, useConfirm, useToast,
} from "../ui/kit.jsx";
import { KO_WORD_BREAK, PROSE_MAX_WIDTH } from "../ui/theme.js";
import { useAuth } from "../app/auth.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { HealthBlock, ProgressBlock } from "./ProjectMetrics.jsx";
import { ProjectTickets } from "./ProjectTickets.jsx";
import { ProjectWbs } from "./ProjectWbs.jsx";
import { ProjectWeekly } from "./ProjectWeekly.jsx";
import {
  MILESTONE_FORM_FIELDS, MILESTONE_STATUS_KO, PROJECT_FORM_FIELDS,
  PROJECT_STATUS_KO, PROJECT_WRITE_ROLES, deptLabel, periodText,
} from "./project-format.js";
import {
  useArchiveProject, useCreateMilestone, useDeleteMilestone, useDeptNames, useProject,
  useProjectHealth, useProjectMilestones, useProjectProgress, useProjectWbs, useProjectWeekly,
  useUpdateMilestone, useUpdateProject,
} from "./project-queries.js";

/* 프로젝트 상세 — 개요, WBS 트리, 마일스톤, 티켓, 주간 리포트.
 *
 * ## 탭도 주소에 둔다
 *
 * 목록의 필터와 같은 이유다. 탭이 `useState` 에만 있으면 "WBS 를 보라"고 주소를 건넬 수 없고,
 * 새로고침하면 개요로 돌아온다. `useQueryState` 로 주소에 둔다.
 *
 * ## 안 보는 탭의 자료는 안 받는다
 *
 * 탭마다 서버 경로가 따로다(WBS, 마일스톤, 주간 리포트, 티켓). 처음 열 때 전부 받으면 왕복이
 * 여섯 번이고, 그중 사용자가 실제로 보는 것은 하나다. 그래서 질의에 `enabled` 를 준다.
 */

const DETAIL_SPEC = { tab: "overview", week: "", page: 1 };
/* 탭이나 주를 바꾸면 티켓 목록 페이지는 처음으로 돌아간다. 3페이지에 머무르면 사용자는
 * 빈 목록을 보고 "티켓이 없다"고 읽는다(티켓 화면들과 같은 규약). */
const DETAIL_RESET = { reset: ["page"] };

const TABS = [
  ["overview", "개요"],
  ["wbs", "WBS"],
  ["milestones", "마일스톤"],
  ["tickets", "티켓"],
  ["weekly", "주간 리포트"],
];

const TAB_KEYS = TABS.map(([key]) => key);

function MetaRow({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "6rem minmax(0,1fr)" }, gap: 1, py: 1, borderBottom: 1, borderColor: "divider" }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Box sx={{ minWidth: 0, fontSize: "0.875rem", ...KO_WORD_BREAK }}>{children}</Box>
    </Box>
  );
}

/* 마일스톤 타임라인 + **추가·수정·삭제**.
 *
 * 예전에는 읽기만 했다. 그런데 백엔드에는 처음부터 CRUD 가 다 있었고(app/projects/router.py)
 * 화면에 버튼이 없어서 마일스톤을 노션에서만 만들 수 있었다 - 사용자가 없애라고 한 상태가
 * 정확히 그것이다("노션에서 설정 및 추가를 못 한다고 생각해라").
 *
 * 순서는 서버가 정한다(sort_order → 기한 → id). 화면이 다시 정렬하면 사람이 손으로 정한
 * 순서가 조용히 무시된다.
 *
 * 삭제는 확인을 받는다. 마일스톤에는 딸린 이력이 없어 하드 삭제고(app/projects/milestones.py),
 * 되돌릴 방법이 없다.
 */
function MilestoneTimeline({ projectId, query, canWrite }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [editing, setEditing] = React.useState(null);
  const create = useCreateMilestone(projectId);
  const update = useUpdateMilestone(projectId);
  const remove = useDeleteMilestone(projectId);

  const items = (query.data && query.data.items) || [];

  async function submit(body) {
    if (editing && editing.id) await update.mutateAsync({ id: editing.id, body });
    else await create.mutateAsync(body);
    setEditing(null);
    toast(editing && editing.id ? "마일스톤을 수정했습니다." : "마일스톤을 추가했습니다.", "success");
  }

  async function del(m) {
    const ok = await confirm(
      "'" + m.name + "' 마일스톤을 삭제할까요? 되돌릴 수 없습니다.",
      { danger: true, title: "마일스톤 삭제", confirmLabel: "삭제" },
    );
    if (!ok) return;
    try {
      await remove.mutateAsync(m.id);
      toast("마일스톤을 삭제했습니다.", "success");
    } catch (e) {
      toast((e && e.message) || "마일스톤을 삭제하지 못했습니다.", "error");
    }
  }

  const addButton = canWrite ? (
    <Button variant="primary" size="sm" onClick={() => setEditing({})}>+ 마일스톤 추가</Button>
  ) : null;

  /* 폼은 목록이 비어 있을 때도 열려야 한다 - 그래서 조기 반환보다 위에서 그린다.
     `editing` 이 `{}` 면 추가, id 가 있으면 수정이다. */
  const form = (
    <FormModal
      open={!!editing}
      title={editing && editing.id ? "마일스톤 수정" : "마일스톤 추가"}
      fields={MILESTONE_FORM_FIELDS}
      initial={editing && editing.id ? editing : { status: "planned", sort_order: 0 }}
      submitLabel={editing && editing.id ? "저장" : "추가"}
      onSubmit={submit}
      onClose={() => setEditing(null)}
    />
  );

  if (query.isPending) return <Card><Skeleton lines={5} /></Card>;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  if (!items.length) {
    return (
      <>
        <Card>
          <EmptyState
            art="tickets"
            title="마일스톤이 없습니다"
            help="마일스톤이 하나도 없으면 일정 준수 여부를 판정할 수 없어 Health 에서도 그 항목이 빠집니다."
            action={addButton}
          />
        </Card>
        {form}
      </>
    );
  }

  return (
    <>
      <Card>
        <Stack direction="row" gap={1} sx={{ flexWrap: "wrap", alignItems: "center", mb: 1.5 }}>
          <Typography component="h2" variant="h6" sx={{ fontSize: "1rem", flex: 1 }}>마일스톤</Typography>
          {addButton}
        </Stack>
        <Box component="ol" sx={{ m: 0, p: 0, display: "grid", gap: 0 }}>
          {items.map((m) => (
            <Box
              component="li" key={m.id}
              sx={{ listStyle: "none", display: "flex", gap: 1.5, alignItems: "baseline", flexWrap: "wrap", py: 1.25, borderBottom: 1, borderColor: "divider" }}
            >
              <Typography variant="body2" color="text.secondary" sx={{ minWidth: "6.5rem", whiteSpace: "nowrap" }}>
                {m.due_on || "기한 없음"}
              </Typography>
              <Typography sx={{ fontWeight: 700, fontSize: "0.9375rem", minWidth: 0, ...KO_WORD_BREAK }}>
                {m.name}
              </Typography>
              <Badge value={MILESTONE_STATUS_KO[m.status] || m.status} />
              {canWrite ? (
                <Stack direction="row" gap={0.5} sx={{ ml: "auto" }}>
                  <Button
                    size="sm"
                    aria-label={"마일스톤 수정: " + m.name}
                    onClick={() => setEditing(m)}
                  >
                    수정
                  </Button>
                  <Button
                    size="sm"
                    aria-label={"마일스톤 삭제: " + m.name}
                    onClick={() => del(m)}
                  >
                    삭제
                  </Button>
                </Stack>
              ) : null}
            </Box>
          ))}
        </Box>
      </Card>
      {form}
    </>
  );
}

function Overview({ project, deptNames, progressQuery, healthQuery, canWrite, onEdit, onArchive, archiving }) {
  const p = project || {};
  const dept = deptLabel(p, deptNames);
  const progress = progressQuery.data || {};
  const health = healthQuery.data || {};
  return (
    <Stack gap={2.5}>
      <Card>
        <Stack direction="row" gap={1} sx={{ flexWrap: "wrap", alignItems: "center", mb: 1 }}>
          <Typography component="h2" variant="h6" sx={{ fontSize: "1rem", flex: 1 }}>개요</Typography>
          {canWrite ? <Button size="sm" onClick={onEdit}>수정</Button> : null}
          {/* FN-04: 화면엔 "보관됨" 배지·"보관한 프로젝트 포함" 체크박스가 있는데 정작
              그 상태로 보내는 버튼이 없었다 — 보관은 되돌릴 API가 없어(project-queries.js
              주석 참조) 이미 보관된 프로젝트에는 버튼을 다시 안 그린다. */}
          {canWrite && !p.archived_at ? (
            <Button size="sm" variant="ghost" disabled={archiving} onClick={onArchive}>보관</Button>
          ) : null}
        </Stack>
        <Box>
          <MetaRow label="상태">
            <Stack direction="row" gap={1} sx={{ flexWrap: "wrap" }}>
              <Badge value={PROJECT_STATUS_KO[p.status] || p.status} />
              {p.notion_status ? <Badge value={p.notion_status} /> : null}
              {p.archived_at ? <Badge value="보관됨" /> : null}
            </Stack>
          </MetaRow>
          {p.code ? <MetaRow label="코드">{p.code}</MetaRow> : null}
          {dept ? <MetaRow label="부서">{dept}</MetaRow> : null}
          <MetaRow label="기간">{periodText(p.starts_on, p.ends_on)}</MetaRow>
          {p.biz_type ? <MetaRow label="사업 유형">{p.biz_type}</MetaRow> : null}
          {p.product ? <MetaRow label="제품">{p.product}</MetaRow> : null}
          <MetaRow label="노션 연결">
            {p.notion_page_id ? "노션 페이지와 연결되어 있습니다." : "포털에서만 관리하는 프로젝트입니다."}
          </MetaRow>
        </Box>
        {p.goal ? (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary">목표</Typography>
            <Typography sx={{ mt: 0.5, maxWidth: PROSE_MAX_WIDTH, whiteSpace: "pre-wrap", ...KO_WORD_BREAK }}>
              {p.goal}
            </Typography>
          </Box>
        ) : null}
      </Card>

      <Card>
        <Typography component="h2" variant="h6" sx={{ fontSize: "1rem", mb: 1.5 }}>진행률</Typography>
        {progressQuery.isPending ? <Skeleton lines={4} />
          : progressQuery.isError ? <ErrorState error={progressQuery.error} onRetry={() => progressQuery.refetch()} />
          : (
            /* 포털이 계산한 값 하나만 그린다. 응답에는 `notion_percent` 도 있지만 그리지
               않는다 - 정본은 포털이고 Notion 은 데이터 소스다(ProjectMetrics.jsx). */
            <ProgressBlock percent={progress.percent} basis={progress.basis} />
          )}
      </Card>

      <Card>
        <Typography component="h2" variant="h6" sx={{ fontSize: "1rem", mb: 1.5 }}>Health</Typography>
        {healthQuery.isPending ? <Skeleton lines={5} />
          : healthQuery.isError ? <ErrorState error={healthQuery.error} onRetry={() => healthQuery.refetch()} />
          : <HealthBlock score={health.score} reasons={health.reasons} unknown={health.unknown} />}
      </Card>
    </Stack>
  );
}

export function Project() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const auth = useAuth();
  const [state, setState] = useQueryState(DETAIL_SPEC, DETAIL_RESET);
  // 주소를 손으로 고친 사람에게 오류 화면을 주지 않는다 - 모르는 값이면 개요를 보여 준다
  // (`weekly.resolve_week` 가 서버에서 같은 판단을 기록한다).
  const tab = TAB_KEYS.includes(state.tab) ? state.tab : "overview";
  const [editing, setEditing] = React.useState(false);

  const projectQuery = useProject(id);
  const progressQuery = useProjectProgress(id, tab === "overview");
  const healthQuery = useProjectHealth(id, tab === "overview");
  const wbsQuery = useProjectWbs(id, tab === "wbs");
  const milestoneQuery = useProjectMilestones(id, tab === "milestones");
  const weeklyQuery = useProjectWeekly(id, state.week, tab === "weekly");
  const deptNames = useDeptNames();
  const update = useUpdateProject(id);
  const archive = useArchiveProject();

  const role = (auth.data && auth.data.role) || "";
  const canWrite = PROJECT_WRITE_ROLES.includes(role);

  const back = <Button onClick={() => nav("/projects")}>목록</Button>;

  if (projectQuery.isError) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="팀 공간" area="프로젝트" title="프로젝트" actions={back} />
        <ErrorState error={projectQuery.error} onRetry={() => projectQuery.refetch()} />
      </div>
    );
  }
  if (projectQuery.isPending) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="팀 공간" area="프로젝트" title="프로젝트" />
        <Card><Skeleton lines={8} /></Card>
      </div>
    );
  }

  const project = (projectQuery.data && projectQuery.data.project) || {};

  /* 저장할 때 **편집을 시작한 시점의 지문**을 함께 보낸다.
   *
   * 안 보내면 두 사람이 같은 폼을 열어 뒀을 때 나중 사람이 앞사람 변경을 조용히 덮어쓰고
   * 양쪽 다 성공 화면을 본다(app/projects/sync.py::ensure_not_changed). 서버가 이미 그
   * 계약을 갖고 있는데 화면이 안 쓰면 배관만 깔려 있고 양 끝이 끊긴 상태다. */
  async function submitEdit(body) {
    await update.mutateAsync({ ...body, base_notion_version: project.notion_version });
    setEditing(false);
    toast("프로젝트를 저장했습니다.", "success");
  }

  async function handleArchive() {
    if (!(await confirm(
      "\"" + (project.name || "이 프로젝트") + "\"를 보관할까요? 되돌리는 기능은 없습니다.",
      { danger: true, confirmLabel: "프로젝트 보관" }
    ))) return;
    await archive.mutateAsync(project.id);
    toast("프로젝트를 보관했습니다.", "success");
  }

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="프로젝트" title={project.name || "프로젝트"} actions={back} />

      {project.notion_sync_error ? (
        <Box sx={{ mb: 2 }}>
          <Callout tone="warn">{"노션에 반영하지 못했습니다. " + project.notion_sync_error}</Callout>
        </Box>
      ) : null}
      {project.notion_missing_at ? (
        <Box sx={{ mb: 2 }}>
          <Callout tone="warn">
            {"이번 동기화에서 노션 쪽 페이지가 보이지 않았습니다(" + project.notion_missing_at
              + "). 노션에서 온 값은 그 시점 이후로 멈춰 있을 수 있습니다."}
          </Callout>
        </Box>
      ) : null}

      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2.5 }}>
        <Tabs
          value={tab}
          onChange={(e, next) => setState({ tab: next })}
          variant="scrollable"
          allowScrollButtonsMobile
          aria-label="프로젝트 상세 탭"
        >
          {TABS.map(([key, label]) => <Tab key={key} value={key} label={label} />)}
        </Tabs>
      </Box>

      {tab === "overview" ? (
        <Overview
          project={project} deptNames={deptNames}
          progressQuery={progressQuery} healthQuery={healthQuery}
          canWrite={canWrite} onEdit={() => setEditing(true)}
          onArchive={handleArchive} archiving={archive.isPending}
        />
      ) : null}

      {tab === "wbs" ? (
        wbsQuery.isPending ? <Card><Skeleton lines={8} /></Card>
          : wbsQuery.isError ? <ErrorState error={wbsQuery.error} onRetry={() => wbsQuery.refetch()} />
          : <ProjectWbs data={wbsQuery.data} ticketsLinked={!!project.notion_page_id} />
      ) : null}

      {tab === "milestones" ? (
        <MilestoneTimeline projectId={id} query={milestoneQuery} canWrite={canWrite} />
      ) : null}

      {tab === "tickets" ? (
        <ProjectTickets
          project={project} page={state.page}
          onPage={(page) => setState({ page })}
        />
      ) : null}

      {tab === "weekly" ? (
        <ProjectWeekly
          projectId={id} week={state.week}
          onWeek={(week) => setState({ week }, { push: true })}
          query={weeklyQuery}
        />
      ) : null}

      <FormModal
        open={editing}
        title="프로젝트 수정"
        fields={PROJECT_FORM_FIELDS}
        initial={project}
        submitLabel="저장"
        onSubmit={submitEdit}
        onClose={() => setEditing(false)}
      />
    </div>
  );
}
