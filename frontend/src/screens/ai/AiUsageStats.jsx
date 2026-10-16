import React from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { useQueryState } from "../../lib/useQueryState.js";
import { Button, DataTable, EmptyState, ErrorState, Field, MetaBar, Segmented } from "../../ui/kit.jsx";
import { FilterSelect, SearchBox } from "../../ui/filters.jsx";
import { DateCell } from "../../ui/cells.jsx";
import { FilterBar } from "../../ui/FilterBar.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../../ui/theme.js";

/* AI 사용 통계 — 실제 사용량 분석 (계획 A6, D-543). 「AI 사용 통계」 그릇의 첫 탭이다.
 *
 * 위에서 아래로 「조건 · 기간 · 보기 기준 → 작은 지표 한 줄 → 나눔 표」다. 큰 KPI 카드를 여러 줄로 쌓지 않는다(카드가 아니다 —
 * 값과 작은 이름 한 줄). 보기 기준은 조건이 아니다(D-530): 조건 수 · 칩 · 「필터 초기화」에 들지 않는다. 기간은 세그먼티드이고
 * 「직접 선택」이면 날짜 칸 둘이 옆에 선다. 서버가 쓴 기간을 문장으로 보인다(`range_label`) — 빈 칸인데 30일을 쓰는 일이 없다.
 * 검색은 서버가 한다(보이는 범위 안 사람의 이름 · 이메일 · 기능 이름). 행을 누르면 같은 기간 · 조건의 호출 기록으로 간다.
 */

const SPEC = { period: "30d", from: "", to: "", group_by: "action", status: "", action: "", q: "" };
const PERIODS = [
  { value: "today", label: "오늘" }, { value: "7d", label: "7일" }, { value: "30d", label: "30일" },
  { value: "month", label: "이번 달" }, { value: "custom", label: "직접 선택" },
];
const VIEWS = [
  { value: "action", label: "기능" }, { value: "user", label: "사용자" },
  { value: "department", label: "부서" }, { value: "model", label: "모델" },
];
const STATUSES = [
  { value: "ok", label: "성공" }, { value: "error", label: "실패" },
  { value: "blocked_policy", label: "정책 차단" }, { value: "blocked_quota", label: "한도 초과" },
];
const VIEW_FILTER_KEY = { action: "action", user: "user_id", department: null, model: "model" };

function count(value) {
  return value == null ? "-" : Number(value).toLocaleString("ko-KR");
}

function tokens(value) {
  if (value == null) return "-";
  if (value >= 1_000_000) return (value / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (value >= 10_000) return Math.round(value / 1_000) + "K";
  return count(value);
}

function seconds(ms) {
  return ms == null ? "-" : (ms / 1000).toFixed(1) + "초";
}

function percent(value) {
  return value == null ? "-" : value + "%";
}

function statsUrl(query) {
  const params = new URLSearchParams();
  params.set("period", query.period || "30d");
  if (query.period === "custom") {
    if (query.from) params.set("from", query.from);
    if (query.to) params.set("to", query.to);
  }
  params.set("group_by", query.group_by || "action");
  if (query.status) params.set("status", query.status);
  if (query.action) params.set("action", query.action);
  if (query.q) params.set("q", query.q);
  return "/api/admin/ai/usage/stats?" + params.toString();
}

/* 행을 누르면 같은 기간 · 조건의 호출 기록 — 고른 보기 기준의 값으로 좁힌다(부서는 기록의 조건 칸이 없어 기간 · 조건만 넘긴다). */
export function recordsHref(row, query, data) {
  const params = new URLSearchParams({ tab: "ai-usage-records" });
  if (data && data.from) params.set("from", data.from);
  if (data && data.to) params.set("to", data.to);
  if (query.status) params.set("status", query.status);
  if (query.action) params.set("action", query.action);
  const key = VIEW_FILTER_KEY[query.group_by || "action"];
  if (key && row.key) params.set(key, row.key);
  return "#/ai-usage?" + params.toString();
}

function CustomRange({ from, to, onApply }) {
  const [draft, setDraft] = React.useState({ from, to });
  React.useEffect(() => setDraft({ from, to }), [from, to]);
  return (
    <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start", flexWrap: "wrap" }}>
      <Field label="시작" htmlFor="ai-usage-from" width="sm">
        <TextField id="ai-usage-from" type="date" size="small" value={draft.from}
          onChange={(e) => setDraft((d) => ({ ...d, from: e.target.value }))} />
      </Field>
      <Field label="끝" htmlFor="ai-usage-to" width="sm" action={(
        <Button disabled={!draft.from || !draft.to} onClick={() => onApply(draft)}>적용</Button>
      )}>
        <TextField id="ai-usage-to" type="date" size="small" value={draft.to}
          onChange={(e) => setDraft((d) => ({ ...d, to: e.target.value }))} />
      </Field>
    </Box>
  );
}

export function AiUsageStats() {
  const [query, setQuery] = useQueryState(SPEC);
  const catalog = useQuery({ queryKey: ["ai-usage", "catalog"], queryFn: () => api("/api/admin/ai/usage/catalog"),
    staleTime: 300_000 });
  const ready = query.period !== "custom" || (query.from && query.to);
  const stats = useQuery({
    queryKey: ["ai-usage", "stats", query],
    queryFn: () => api(statsUrl(query)),
    enabled: Boolean(ready),
    placeholderData: keepPreviousData,
  });
  const data = stats.data;
  const totals = (data && data.totals) || {};
  const view = VIEWS.find((v) => v.value === (query.group_by || "action")) || VIEWS[0];
  const actions = ((catalog.data && catalog.data.actions) || [])
    .filter((a) => !a.retired || a.key === query.action)
    .map((a) => ({ value: a.key, label: a.retired ? `${a.label}` : a.label }));
  const conditionCount = [query.status, query.action, query.q].filter(Boolean).length;

  const metrics = [
    { key: "calls", label: "AI 요청", value: count(totals.calls) },
    { key: "success", label: "성공률", value: percent(totals.success_rate) },
    { key: "errors", label: "실패", value: count(totals.errors) },
    { key: "policy", label: "정책 차단", value: count(totals.blocked_policy) },
    { key: "in", label: "입력 토큰", value: tokens(totals.input_tokens) },
    { key: "out", label: "출력 토큰", value: tokens(totals.output_tokens) },
    { key: "latency", label: "평균 응답 시간", value: seconds(totals.avg_latency_ms) },
  ];
  const columns = [
    {
      key: "label", label: view.label, type: "name", rowLink: true,
      render: (r) => (r.email ? `${r.label} (${r.email})` : r.label),
      rowName: (r) => r.label,
    },
    { key: "calls", label: "요청", type: "count", render: (r) => count(r.calls) },
    { key: "success_rate", label: "성공률", type: "percent", render: (r) => percent(r.success_rate) },
    { key: "errors", label: "실패", type: "count", render: (r) => count(r.errors) },
    { key: "blocked_policy", label: "정책 차단", type: "count", render: (r) => count(r.blocked_policy) },
    { key: "blocked_quota", label: "한도 초과", type: "count", render: (r) => count(r.blocked_quota) },
    { key: "input_tokens", label: "입력 토큰", type: "count", render: (r) => tokens(r.input_tokens) },
    { key: "output_tokens", label: "출력 토큰", type: "count", render: (r) => tokens(r.output_tokens) },
    { key: "avg_latency_ms", label: "평균 응답 시간", type: "number", render: (r) => seconds(r.avg_latency_ms) },
    { key: "last_at", label: "최근 사용", type: "datetime", render: (r) => <DateCell value={r.last_at} /> },
  ];
  const empty = conditionCount
    ? <EmptyState title="검색 조건에 맞는 기록이 없습니다." action={(
      <Button size="sm" onClick={() => setQuery({ status: "", action: "", q: "" })}>필터 초기화</Button>
    )} />
    : <EmptyState title="이 기간에 AI 요청이 없습니다." help="기간을 넓히거나 AI 연결 상태를 확인하세요." />;

  return (
    <Box className="c-screen" data-testid="ai-usage-stats">
      <FilterBar
        search={(
          <SearchBox value={query.q} onSearch={(v) => setQuery({ q: v })} placeholder="사용자 이름, 이메일, 기능으로 검색"
            ariaLabel="사용자나 기능 검색" />
        )}
        end={(
          <Segmented ariaLabel="보기 기준" value={view.value} options={VIEWS}
            onChange={(v) => setQuery({ group_by: v })} />
        )}
        conditions={{
          chips: [
            query.q ? { key: "q", label: `검색: ${query.q}`, onDelete: () => setQuery({ q: "" }) } : null,
            query.status ? { key: "status", label: `결과: ${(STATUSES.find((s) => s.value === query.status) || {}).label || query.status}`, onDelete: () => setQuery({ status: "" }) } : null,
            query.action ? { key: "action", label: `기능: ${(actions.find((a) => a.value === query.action) || {}).label || query.action}`, onDelete: () => setQuery({ action: "" }) } : null,
          ].filter(Boolean),
          total: data ? data.total : null,
          onClearAll: conditionCount > 1 ? () => setQuery({ status: "", action: "", q: "" }) : null,
          clearLabel: "필터 초기화",
        }}
      >
        <FilterSelect label="결과" value={query.status} allLabel="전체" options={STATUSES}
          onChange={(v) => setQuery({ status: v })} />
        <FilterSelect label="기능" value={query.action} allLabel="전체" options={actions}
          onChange={(v) => setQuery({ action: v })} />
      </FilterBar>

      <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap", minWidth: 0 }}>
        <Segmented ariaLabel="기간" value={query.period || "30d"} options={PERIODS}
          onChange={(v) => setQuery({ period: v })} />
        {query.period === "custom" ? (
          <CustomRange from={query.from} to={query.to} onApply={(d) => setQuery({ from: d.from, to: d.to })} />
        ) : null}
        {data && data.range_label ? (
          <Typography sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }} data-testid="ai-usage-range">
            {data.range_label}
          </Typography>
        ) : null}
      </Box>

      {stats.isError ? (
        <ErrorState layout="region" error={stats.error} onRetry={() => stats.refetch()} />
      ) : (
        <>
          <MetaBar items={metrics} ariaLabel="이 기간의 지표" />
          <DataTable
            placement="surface"
            loading={stats.isLoading || !ready}
            columns={columns}
            rows={(data && data.items) || []}
            rowKey={(r) => r.key || "-"}
            rowHref={(r) => recordsHref(r, query, data)}
            emptyState={empty}
          />
        </>
      )}
    </Box>
  );
}

export default AiUsageStats;
