import React from "react";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import { Badge, Button, Callout, Card, EmptyState, ErrorState, PageHeader, Skeleton } from "../ui/kit.jsx";
import { Pager } from "../ui/Pager.jsx";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { useQueryState } from "../lib/useQueryState.js";
import { ProgressPair } from "./ProjectMetrics.jsx";
import { useDeptNames, useProjectList } from "./project-queries.js";
import {
  NO_HEALTH_CACHE, PROJECT_STATUS_KO, deptLabel, periodText,
} from "./project-format.js";

/* 프로젝트 목록 — 카드 격자.
 *
 * ## 조건은 주소에 둔다
 *
 * 티켓 화면이 방금 같은 결론에 도달했다(`lib/useQueryState.js`): 필터를 `useState` 에만 두면
 * 상세를 보고 돌아왔을 때 풀리고, 새로고침과 링크 공유도 안 된다. 같은 훅을 쓴다.
 *
 * ## 왜 조건이 '보관 포함' 하나인가
 *
 * 서버가 이 목록에서 받는 조건이 그것뿐이다(`app/projects/router.py::list_projects` 는
 * `include_archived` 와 페이지만 받는다). 상태나 부서 선택기를 여기 더 그리면 화면에서
 * 걸러야 하는데, 서버가 20건씩 자르는 목록을 화면에서 거르면 **그 한 페이지 안에서만**
 * 걸러져 "총 40건인데 2건만 보인다"가 된다. 티켓 필터 줄이 같은 함정을 기록해 두었다
 * (`screens/TicketFilterBar.jsx`). 조건을 늘리려면 서버가 먼저 받아야 한다.
 */

const PROJECT_SPEC = { page: 1, archived: false };
const PAGE_RESET = { reset: ["page"] };

const CARD_GRID = {
  display: "grid", gap: 2.5, alignItems: "start",
  gridTemplateColumns: {
    xs: "1fr",
    sm: "repeat(auto-fill, minmax(20rem, 1fr))",
    xxl: "repeat(auto-fill, minmax(24rem, 1fr))",
  },
};

/** 화면 상태 → 서버 질의. 기본값은 안 싣는다(주소도 질의도 깨끗해야 조건이 눈에 보인다). */
export function projectListQuery(filters) {
  const p = new URLSearchParams();
  if (filters.archived) p.set("include_archived", "true");
  if (filters.page > 1) p.set("page", String(filters.page));
  return p;
}

function MetaLine({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "4.5rem minmax(0, 1fr)" }, gap: 1 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="body2" sx={KO_WORD_BREAK}>{children}</Typography>
    </Box>
  );
}

function ProjectCard({ project, deptNames, onOpen }) {
  const p = project || {};
  const dept = deptLabel(p, deptNames);
  return (
    <Card component="article" sx={{ display: "grid", gap: 1.5, alignContent: "start" }}>
      <Stack direction="row" gap={1} sx={{ flexWrap: "wrap", alignItems: "center" }}>
        <Badge value={PROJECT_STATUS_KO[p.status] || p.status} />
        {/* 노션 진행 상태는 앱 상태와 **다른 축**이다(백로그/차질 같은 값이 여기 온다).
            하나로 뭉치면 가장 봐야 할 '차질' 이 사라진다(app/projects/models.py). */}
        {p.notion_status ? <Badge value={p.notion_status} /> : null}
        {p.archived_at ? <Badge value="보관됨" /> : null}
        {/* 노션에서 안 보인 회차가 있었다는 사실. 감추지 않는다 - 감추면 사용자는 값이 왜
            멈춰 있는지 알 방법이 없다. */}
        {p.notion_missing_at ? <Badge value="노션에서 확인 안 됨" kind="warn" /> : null}
      </Stack>

      <Button
        variant="ghost"
        onClick={() => onOpen(p)}
        sx={{ justifyContent: "flex-start", p: 0, minWidth: 0, textAlign: "left", fontWeight: 800, fontSize: "1.0625rem", ...KO_WORD_BREAK }}
      >
        {p.name || "이름 없음"}
      </Button>

      <Box sx={{ display: "grid", gap: 0.5 }}>
        {p.code ? <MetaLine label="코드">{p.code}</MetaLine> : null}
        {dept ? <MetaLine label="부서">{dept}</MetaLine> : null}
        <MetaLine label="기간">{periodText(p.starts_on, p.ends_on)}</MetaLine>
      </Box>

      {p.notion_sync_error ? (
        <Callout tone="warn">{"노션에 반영하지 못했습니다. " + p.notion_sync_error}</Callout>
      ) : null}

      <ProgressPair
        appPercent={p.progress_pct}
        notionPercent={p.notion_progress_pct}
        missingMeans="cache"
        footnote="계산식과 표본 수는 상세 화면에서 봅니다."
      />

      <Box sx={{ pt: 1.5, borderTop: 1, borderColor: "divider" }}>
        <Typography variant="body2" color="text.secondary">Health</Typography>
        <Typography sx={{ fontSize: "1.125rem", fontWeight: 800 }}>
          {p.health_score == null ? NO_HEALTH_CACHE : p.health_score + "점"}
        </Typography>
        {/* 점수 옆에는 이유가 있어야 하는데 목록 응답에는 이유가 없다. 지어내지 않고
            어디서 볼 수 있는지만 말한다(§불변 6). */}
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          감점 이유는 상세 화면에서 봅니다.
        </Typography>
      </Box>
    </Card>
  );
}

export function Projects() {
  const nav = useNavigate();
  const [filters, setFilters] = useQueryState(PROJECT_SPEC, PAGE_RESET);
  const qs = projectListQuery(filters).toString();
  const q = useProjectList(qs);
  const deptNames = useDeptNames();

  const open = React.useCallback(
    (p) => nav("/projects/" + p.id, { state: { from: "/projects" } }),
    [nav],
  );

  const data = q.data || {};
  const items = Array.isArray(data.items) ? data.items : [];

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="프로젝트" title="프로젝트" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5, maxWidth: "70ch", ...KO_WORD_BREAK }}>
        내가 볼 수 있는 프로젝트의 상태, 기간, 진행률, Health 를 한눈에 봅니다. 진행률은 포털이 다시 계산한 값과 Notion 값을 나란히 보여 줍니다.
      </Typography>

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
            <Box sx={CARD_GRID}>
              {items.map((p) => (
                <ProjectCard key={p.id} project={p} deptNames={deptNames} onOpen={open} />
              ))}
            </Box>
            <Pager
              page={data.page} pageSize={data.page_size} total={data.total}
              onPage={(page) => setFilters({ page })}
            />
          </>
        )}
    </div>
  );
}
