import React from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import {
  ListEmptyState,
  Badge, Button, Callout, Card, DataTable, EmptyState, ErrorState, FormModal,
  MetricStrip, PageHeader, Skeleton, useToast,
} from "../ui/kit.jsx";
import { Pager } from "../ui/Pager.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { useAuth } from "../app/auth.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { DepartmentFilter } from "../ui/filters.jsx";
import { FilterActions, FilterRow, FilterSurface, ResultLine } from "../ui/FilterBar.jsx";
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

// `dept` 는 부서 필터 (0060 §32). 주소에 두는 이유는 나머지 조건과 같다 — 상세를 보고
// 돌아왔을 때 풀리면 안 되고, 링크로 "A-1 팀 프로젝트" 를 공유할 수 있어야 한다.
const PROJECT_SPEC = { page: 1, archived: false, dept: "" };
const PAGE_RESET = { reset: ["page"] };


/** 화면 상태 → 서버 질의. 기본값은 안 싣는다(주소도 질의도 깨끗해야 조건이 눈에 보인다). */
export function projectListQuery(filters) {
  const p = new URLSearchParams();
  if (filters.archived) p.set("include_archived", "true");
  // 주소 키(`dept`)와 API 키(`department_id`)가 다르다 — 옮겨 적는 자리는 여기 하나다.
  if (filters.dept) p.set("department_id", filters.dept);
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
  // PA-RC-0018 direction 4(0 지표 규칙): 프로젝트가 0건이면 여덟 타일 전부가 0/-다 —
  // 빈 상태 위에 값 없는 카드 벽을 먼저 그리는 대신, 아래 EmptyState 하나로만 말한다.
  // 이 total은 서버 집계(project_dashboard)라 목록 화면의 보관 필터와 무관하게 항상
  // 전체 기준이다(위 주석 "요약을 화면에서 세지 않는 이유" 참고) — 필터로 화면에 0건이
  // 보여도 조직에 프로젝트가 있으면 이 요약은 그대로 뜬다.
  if (!d.total) return null;
  const status = d.by_status || {};
  const progress = d.progress || {};
  const health = d.health || {};
  const trouble = health.trouble || {};
  const overdue = (d.milestones || {}).overdue || {};
  const avg = percentText(progress.average_pct);

  /* 지표를 성격으로 **두 묶음**으로 나눈다 (지시 2).
   *
   * 예전에는 타일 여덟 장이 한 격자에 깔렸고, 프로젝트가 적으면 그중 다섯이 `0`/`-` 라
   * 화면 절반을 "값이 없다"는 사실이 차지했다. 여덟 개가 같은 무게로 보이니 무엇이 핵심인지도
   * 알 수 없었다.
   *
   *   1) 구성 — 전체가 지배 판독값이고 상태별 넷이 그 옆에 붙는다. 합이 전체가 되는 관계다.
   *   2) 진행과 위험 — 성격이 다르다. 조치가 필요한지 보는 줄이라 따로 둔다.
   */
  return (
    <Box sx={{ mb: 2.5, display: "grid", gap: 1.5 }}>
      <MetricStrip
        ariaLabel="프로젝트 구성"
        items={[
          { key: "total", value: d.total, label: "전체", primary: true },
          { key: "active", value: status.active, label: "진행" },
          { key: "done", value: status.done, label: "완료" },
          { key: "on_hold", value: status.on_hold, label: "보류" },
          { key: "planned", value: status.planned, label: "계획" },
        ]}
      />
      <MetricStrip
        ariaLabel="진행과 위험"
        items={[
          {
            key: "progress",
            value: avg,
            label: "평균 진행률",
            /* 평균을 못 낼 수도 있다(계산된 프로젝트가 하나도 없음). 그때 0% 로 그리면
               "세어 봤더니 0" 이라는 거짓말이 된다 — null 은 '-' 로 그린다.
               각주는 그 숫자 바로 아래 붙인다(VIS-09). */
            note: "계산이 끝난 " + (progress.counted || 0) + "건만 셌습니다"
              + (progress.not_counted ? ", " + progress.not_counted + "건은 아직 계산하지 않았습니다" : "") + ".",
          },
          {
            key: "health",
            value: trouble.count,
            label: "Health 하위",
            kind: trouble.count > 0 ? "danger" : undefined,
            note: "Health 는 " + (health.unscored || 0) + "건을 아직 재지 않았습니다.",
          },
          {
            key: "overdue",
            value: overdue.count,
            label: "지연 마일스톤",
            kind: overdue.count > 0 ? "warn" : undefined,
          },
        ]}
      />
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
          <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}>
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
  /* «조건 때문에 0건» 판정 (C1 · W5). `archived` 도 조건이다 — 보관 스위치를 켠 채 0건인
     화면에 「프로젝트가 없습니다」라고 말하면 그 스위치가 원인이라는 사실이 사라진다.
     기본값은 주소에 안 실리므로(`useQueryState`) 여기서 **기본값과 다른가**로 센다. */
  const hasProjectFilter = React.useMemo(
    () => Object.keys(PROJECT_SPEC).some(
      (k) => k !== "page" && filters[k] !== PROJECT_SPEC[k] && filters[k] !== "" && filters[k] != null
    ),
    [filters]
  );
  const clearProjectFilters = React.useCallback(
    () => setFilters({ archived: false, dept: "", page: 1 }),
    [setFilters]
  );
  /* 결과 줄이 세는 것은 «지금 걸린 조건» 이다 — 기본값과 다른 축만 센다. */
  const activeProjectConditions = React.useMemo(
    () => Object.keys(PROJECT_SPEC).filter(
      (k) => k !== "page" && filters[k] !== PROJECT_SPEC[k] && filters[k] !== "" && filters[k] != null
    ),
    [filters]
  );
  const qs = projectListQuery(filters).toString();
  const q = useProjectList(qs);
  const dashboard = useProjectDashboard(filters.dept);
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
  /* 부서 이름은 **목록 응답이 함께 준다** (0060 §32).
   *
   * `useDeptNames` 는 `/api/admin/departments` 를 읽으므로 관리자에게만 값이 있다. 그런데
   * 이 열은 "이 프로젝트가 누구 것인가" 라 일반 사용자에게 더 필요하다 — 예전에는 그 사람
   * 화면에서만 전부 '-' 로 비어, 소속을 보여 주기로 한 결정이 정작 대상에게 안 보였다.
   *
   * 응답의 후보 목록은 **그 사람의 조회 범위 안**이라 이름이 새지 않는다. 관리자 쪽 맵을
   * 뒤에 겹쳐 두는 이유는 범위 밖 부서(전역 관리자가 보는 남의 조직)도 이름이 나와야 하기
   * 때문이다. */
  const deptNamesFromList = React.useMemo(() => {
    const out = {};
    for (const o of (data.departments && data.departments.options) || []) out[o.id] = o.name;
    return out;
  }, [data.departments]);
  const names = React.useMemo(
    () => ({ ...deptNamesFromList, ...deptNames }),
    [deptNamesFromList, deptNames],
  );
  const cols = React.useMemo(() => columns(names), [names]);

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
          <Button variant="primary" onClick={() => setCreating(true)}>새 프로젝트</Button>
        ) : null}
      />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5, ...KO_WORD_BREAK }}>
        내가 볼 수 있는 프로젝트의 상태, 기간, 진행률, Health를 한눈에 봅니다.
      </Typography>

      <Summary query={dashboard} />

      {/* 탐색 줄은 **판이 아니다** (지시 80 · W5). 이 화면만 `c-toolbar-card` 를 달고 남아
          있었다 — 독립 검수 실측: 1920 에서 잉크 폭 비 0.355, 3840 에서 0.234 로, W5 가
          「없앴다」고 적은 `/policies` 판(0.43)보다 오히려 나빴다. 나머지 넷과 같은 부품을 쓴다:
          scope(부서)가 먼저, 보기 방식(보관 포함)은 흐름 끝, 건수는 필터와 목록 **사이**. */}
      <FilterSurface>
        <FilterRow>
          {/* 후보는 이 응답이 들고 온다 — 서버가 계산한 내 조회 범위다. */}
          <DepartmentFilter
            departments={data.departments}
            value={filters.dept}
            onChange={(v) => setFilters({ dept: v })}
          />
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
          {hasProjectFilter ? (
            <FilterActions>
              <Button variant="ghost" size="sm" onClick={clearProjectFilters}>필터 지우기</Button>
            </FilterActions>
          ) : null}
        </FilterRow>
      </FilterSurface>
      <ResultLine total={data.total} conditions={activeProjectConditions} />

      {q.isPending ? <Card>{/* 표가 들어올 자리에는 표 모양을 그린다 (지시 20) - 빈 목록과 아직 안 온 목록은 다른 사실이다. */}<DataTable columns={cols} rows={[]} loading /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : items.length === 0 ? (
          <Card>
            {/* «정말 없다» 와 «조건 때문에 0건» 을 가른다 (C1 · W5).
                예전에는 `filters.archived` 로만 갈라져서, 부서나 검색어로 0건이 된 화면도
                「프로젝트가 없습니다」라고 말했다 — 게다가 그 조건을 그 자리에서 풀 수단이
                없었다. 조건이 하나라도 걸려 있으면 그 사실을 말하고 지울 길을 준다. */}
            <ListEmptyState
              filtered={hasProjectFilter}
              onClear={clearProjectFilters}
              filteredTitle="조건에 맞는 프로젝트가 없습니다"
              filteredHelp="지금 걸린 조건(검색어, 부서, 상태)에 맞는 프로젝트가 없습니다. 조건을 지우면 전체를 볼 수 있습니다."
              art="tickets"
              title="프로젝트가 없습니다"
              situation={filters.archived ? undefined : "지금 진행 중인 프로젝트가 없거나, 있는 프로젝트가 전부 보관돼 있습니다."}
              help={filters.archived
                ? "보관한 것까지 포함해도 볼 수 있는 프로젝트가 없습니다."
                : "보관한 프로젝트까지 보려면 위의 스위치를 켜세요."}
            />
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
                <Callout tone="danger">
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
        submitLabel="추가"
        onSubmit={submitCreate}
        onClose={() => setCreating(false)}
      />
    </div>
  );
}
