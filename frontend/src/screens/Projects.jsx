import React from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import {
  Badge, Button, Callout, Card, DataTable, EmptyState, ErrorState, FormModal,
  PageHeader, Skeleton, StatCard, useToast,
} from "../ui/kit.jsx";
import { Pager } from "../ui/Pager.jsx";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { useAuth } from "../app/auth.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { useCreateProject, useDeptNames, useProjectDashboard, useProjectList } from "./project-queries.js";
import {
  NO_HEALTH_CACHE, NO_PROGRESS_CACHE, PROJECT_FORM_FIELDS, PROJECT_STATUS_KO,
  PROJECT_WRITE_ROLES, deptLabel, percentText, periodText,
} from "./project-format.js";

/* 프로젝트 목록 — **요약 + 표**.
 *
 * ## 왜 카드 격자가 아니라 표인가 (사용자 지시)
 *
 * 카드 격자는 한 화면에 6~8건이 들어가고, 같은 항목(기간, 진행률, Health)이 카드마다 다른
 * 세로 위치에 놓여 **행끼리 비교가 안 된다.** 사용자가 지적한 것이 정확히 그것이다:
 * "저렇게 카드로 보여 주면 어떻게 보라는 것이냐". 표는 열이 고정이라 눈이 세로로 훑는다.
 *
 * ## 정렬 UI 를 만들지 않는 이유
 *
 * 🔴 `app/projects/router.py::list_projects` 가 받는 것은 `page` / `page_size` /
 * `include_archived` 뿐이다. **정렬 파라미터가 없다.** 여기서 화면 정렬을 붙이면 서버가 20건씩
 * 자른 **그 한 페이지 안에서만** 정렬되고, 2페이지로 넘기면 순서가 통째로 어긋난다 - 사용자
 * 눈에는 목록이 깨진 것으로 보이고 원인이 화면에 없어서 아무도 못 찾는다(같은 함정을 조건
 * 필터에서 이미 겪었다: `screens/TicketFilterBar.jsx`). 서버가 먼저 받아야 만든다. 지금은
 * 서버가 준 순서(최근 갱신 순)를 그대로 그린다.
 *
 * ## 요약을 화면에서 세지 않는 이유
 *
 * 같은 함정의 다른 얼굴이다. 목록은 20건씩 잘려 오므로 `items` 를 세면 "총 22건인데 요약은
 * 20건 기준" 이 된다. 집계는 서버가 별도 경로(`/api/projects/dashboard`)에서 자르지 않은
 * 표본으로 한다.
 *
 * ## 조건은 주소에 둔다
 *
 * 티켓 화면과 같은 결론이다(`lib/useQueryState.js`): 필터를 `useState` 에만 두면 상세를 보고
 * 돌아왔을 때 풀리고, 새로고침과 링크 공유도 안 된다.
 */

const PROJECT_SPEC = { page: 1, archived: false };
const PAGE_RESET = { reset: ["page"] };

/* 요약 타일 줄. 타일이 여덟 개라 lg 에서 4열이면 두 줄로 딱 떨어진다 - 5열로 두면 마지막
 * 세 개가 다음 줄에 흩어져 '상태별' 이 한 덩어리로 안 읽힌다(Dashboard.jsx 의 STAT_GRID 가
 * 같은 이유로 개수에 맞춰 열을 정한다). */
const SUMMARY_GRID = {
  xs: "1fr",
  sm: "repeat(2, minmax(0,1fr))",
  lg: "repeat(4, minmax(0,1fr))",
  xxl: "repeat(4, minmax(0,1fr))",
};

/** 화면 상태 → 서버 질의. 기본값은 안 싣는다(주소도 질의도 깨끗해야 조건이 눈에 보인다). */
export function projectListQuery(filters) {
  const p = new URLSearchParams();
  if (filters.archived) p.set("include_archived", "true");
  if (filters.page > 1) p.set("page", String(filters.page));
  return p;
}

/* 요약 줄. **숫자는 응답을 그대로 쓴다** - 여기서 더하거나 빼면 서버가 센 것과 갈라진다.
 *
 * 못 잰 것을 함께 말하는 것이 이 줄의 계약이다. "Health 하위 0건" 이 '다 건강하다' 인지
 * '아무것도 안 쟀다' 인지는 완전히 다른 사실이고, 안 말하면 화면이 조용히 후자를 전자처럼
 * 보이게 한다(app/projects/service.py::project_dashboard). */
function Summary({ query }) {
  if (query.isPending) return <Card><Skeleton lines={3} /></Card>;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;

  const d = query.data || {};
  const status = d.by_status || {};
  const progress = d.progress || {};
  const health = d.health || {};
  const trouble = health.trouble || {};
  const overdue = (d.milestones || {}).overdue || {};
  const avg = percentText(progress.average_pct);

  return (
    <Box sx={{ mb: 2.5 }}>
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: SUMMARY_GRID }}>
        <StatCard value={d.total} label="전체" />
        <StatCard value={status.active} label="진행" />
        <StatCard value={status.done} label="완료" />
        <StatCard value={status.on_hold} label="보류" />
        <StatCard value={status.planned} label="계획" />
        {/* 평균을 못 낼 수도 있다(계산된 프로젝트가 하나도 없음). 그때 0% 로 그리면
            "세어 봤더니 0" 이라는 거짓말이 된다 - StatCard 는 null 을 '-' 로 그린다. */}
        <StatCard value={avg} label="평균 진행률" />
        <StatCard
          value={trouble.count}
          label="Health 하위"
          kind={trouble.count > 0 ? "danger" : undefined}
        />
        <StatCard
          value={overdue.count}
          label="지연 마일스톤"
          kind={overdue.count > 0 ? "warn" : undefined}
        />
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5, ...KO_WORD_BREAK }}>
        {"평균 진행률은 계산이 끝난 " + (progress.counted || 0) + "건만 셌습니다"
          + (progress.not_counted ? ", " + progress.not_counted + "건은 아직 계산하지 않았습니다" : "")
          + ". Health 는 " + (health.unscored || 0) + "건을 아직 재지 않았습니다."}
      </Typography>
    </Box>
  );
}

/* 표의 열. 사용자가 요구한 여섯 가지다(이름·상태·부서·기간·진행률·Health).
 *
 * `deptNames` 를 인자로 받는 이유: 부서 이름은 관리자군만 받아 올 수 있다
 * (project-queries.js::useDeptNames). 이름을 모르는 사람에게 UUID 를 그리면 그건 정보가
 * 아니라 소음이라 아예 안 그린다(§불변 6, project-format.js::deptLabel). */
function columns(deptNames) {
  return [
    {
      key: "name", label: "이름", minWidth: "12rem",
      // 표의 어느 열이 '이 행이 무엇인가' 를 말하는지 알려 준다(kit.jsx::rowOpenLabel).
      rowName: (p) => p.name,
      render: (p) => (
        <Box sx={{ display: "grid", gap: 0.25, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 700, fontSize: "0.875rem", ...KO_WORD_BREAK }}>
            {p.name || "이름 없음"}
          </Typography>
          {p.code ? (
            <Typography variant="caption" color="text.secondary">{p.code}</Typography>
          ) : null}
        </Box>
      ),
    },
    {
      key: "status", label: "상태", minWidth: "8rem",
      render: (p) => (
        <Stack direction="row" gap={0.5} sx={{ flexWrap: "wrap", alignItems: "center" }}>
          <Badge value={PROJECT_STATUS_KO[p.status] || p.status} />
          {p.archived_at ? <Badge value="보관됨" /> : null}
          {/* 노션에서 안 보인 회차가 있었다는 사실. 감추면 사용자는 값이 왜 멈춰 있는지
              알 방법이 없다. */}
          {p.notion_missing_at ? <Badge value="노션에서 확인 안 됨" kind="warn" /> : null}
        </Stack>
      ),
    },
    {
      key: "dept_id", label: "부서", minWidth: "7rem",
      render: (p) => deptLabel(p, deptNames) || "-",
    },
    {
      key: "period", label: "기간", minWidth: "11rem", nowrap: true,
      render: (p) => periodText(p.starts_on, p.ends_on),
    },
    {
      key: "progress_pct", label: "진행률", align: "right", minWidth: "6rem", nowrap: true,
      // null 은 0% 가 아니다. 0 으로 그리면 "작업이 아직 안 붙은 프로젝트" 와 "붙었는데
      // 하나도 못 끝낸 프로젝트" 가 화면에서 똑같아진다(project-format.js 의 계약).
      render: (p) => percentText(p.progress_pct) || (
        <Typography component="span" variant="body2" color="text.secondary">
          {NO_PROGRESS_CACHE}
        </Typography>
      ),
    },
    {
      key: "health_score", label: "Health", align: "right", minWidth: "7rem", nowrap: true,
      render: (p) => (p.health_score == null ? (
        <Typography component="span" variant="body2" color="text.secondary">
          {NO_HEALTH_CACHE}
        </Typography>
      ) : p.health_score + "점"),
    },
  ];
}

export function Projects() {
  const nav = useNavigate();
  const toast = useToast();
  const auth = useAuth();
  const [filters, setFilters] = useQueryState(PROJECT_SPEC, PAGE_RESET);
  const [creating, setCreating] = React.useState(false);
  const qs = projectListQuery(filters).toString();
  const q = useProjectList(qs);
  const dashboard = useProjectDashboard();
  const deptNames = useDeptNames();
  const create = useCreateProject();

  const role = (auth.data && auth.data.role) || "";
  const canWrite = PROJECT_WRITE_ROLES.includes(role);

  const open = React.useCallback(
    (p) => nav("/projects/" + p.id, { state: { from: "/projects" } }),
    [nav],
  );

  const data = q.data || {};
  const items = Array.isArray(data.items) ? data.items : [];
  const cols = React.useMemo(() => columns(deptNames), [deptNames]);

  async function submitCreate(body) {
    const created = await create.mutateAsync(body);
    setCreating(false);
    toast("프로젝트를 만들었습니다.", "success");
    // 방금 만든 것을 바로 열어 준다. 목록으로 돌려보내면 사용자가 22건 중에서 자기가 방금
    // 만든 것을 다시 찾아야 한다.
    const made = created && created.project;
    if (made && made.id) nav("/projects/" + made.id, { state: { from: "/projects" } });
  }

  return (
    <div className="c-screen">
      <PageHeader
        crumbRoot="팀 공간" area="프로젝트" title="프로젝트"
        actions={canWrite ? (
          <Button variant="primary" onClick={() => setCreating(true)}>+ 새 프로젝트</Button>
        ) : null}
      />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5, maxWidth: "70ch", ...KO_WORD_BREAK }}>
        내가 볼 수 있는 프로젝트의 상태, 기간, 진행률, Health 를 한눈에 봅니다. 진행률은 포털이 작업을 다시 세어 계산한 값이고, 계산 근거는 상세 화면에서 봅니다.
      </Typography>

      <Summary query={dashboard} />

      <Card className="c-toolbar-card" sx={{ p: 2, mb: 2.5 }}>
        <Stack direction="row" gap={2} sx={{ flexWrap: "wrap", alignItems: "center" }}>
          <FormControlLabel
            sx={{ m: 0 }}
            control={
              <Switch
                size="small"
                checked={!!filters.archived}
                onChange={(e) => setFilters({ archived: e.target.checked })}
              />
            }
            label={<Typography variant="body2">보관한 프로젝트 포함</Typography>}
          />
        </Stack>
        {data.total != null ? (
          <Typography variant="body2" color="text.secondary" aria-live="polite" sx={{ mt: 1.5 }}>
            총 {data.total}건
          </Typography>
        ) : null}
      </Card>

      {q.isPending ? <Card><Skeleton lines={6} /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : items.length === 0 ? (
          <Card>
            {filters.archived ? (
              <EmptyState
                art="tickets"
                title="프로젝트가 없습니다"
                help="보관한 것까지 포함해도 볼 수 있는 프로젝트가 없습니다."
              />
            ) : (
              <EmptyState
                art="tickets"
                title="프로젝트가 없습니다"
                situation="지금 진행 중인 프로젝트가 없거나, 있는 프로젝트가 전부 보관돼 있습니다."
                help="보관한 프로젝트까지 보려면 위의 스위치를 켜세요."
              />
            )}
          </Card>
        ) : (
          <>
            <Card sx={{ p: 0, overflow: "hidden" }}>
              <DataTable
                columns={cols} rows={items} rowKey={(p) => p.id} onRow={open}
                empty="표시할 프로젝트가 없습니다."
              />
            </Card>
            {/* 노션에 못 밀어 넣은 프로젝트는 표 안에 문장을 넣을 자리가 없다(열이 여섯이다).
                표 아래 한 줄로 모아 말한다 - 감추면 사용자는 저장이 된 줄 안다. */}
            {items.filter((p) => p.notion_sync_error).map((p) => (
              <Box key={p.id} sx={{ mt: 1.5 }}>
                <Callout tone="warn">
                  {p.name + ": 노션에 반영하지 못했습니다. " + p.notion_sync_error + " 관리자에게 문의하세요."}
                </Callout>
              </Box>
            ))}
            <Pager
              page={data.page} pageSize={data.page_size} total={data.total}
              onPage={(page) => setFilters({ page })}
            />
          </>
        )}

      <FormModal
        open={creating}
        title="새 프로젝트"
        fields={PROJECT_FORM_FIELDS}
        initial={{ status: "active" }}
        submitLabel="만들기"
        onSubmit={submitCreate}
        onClose={() => setCreating(false)}
      />
    </div>
  );
}
