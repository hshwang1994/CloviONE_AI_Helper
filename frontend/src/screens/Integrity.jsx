import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import { EntityCombobox } from "../ui/filters.jsx";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge, Button, Callout, Card, DataTable, EmptyState, ErrorState, PageHeader,
  MetricStrip, SectionTitle, Skeleton, useToast,
} from "../ui/kit.jsx";
import { OrgPath } from "../ui/OrgPath.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";

/* 조직 정합성 진단 — **닫아 버린 것을 사람에게 보여 주는 화면** (0060 §41).
 *
 * 이 제품의 접근 모델은 "소속을 모르면 닫는다" 다. 그 규칙만 있으면 안전하기는 한데
 * 아무도 원인을 못 찾는다 — 증상이 "권한이 없습니다" 가 아니라 **"목록이 비어 있음"** 이기
 * 때문이다. 그래서 닫는 규칙과 이 화면은 같은 배포에 있어야 한다.
 *
 * 화면이 하는 일은 둘뿐이다: **세고**, **일괄로 지정한다**. 추측해서 자동으로 고치지 않는다 —
 * "부서를 모르니 조직 직속으로 하자" 같은 추측은 언제나 넓히는 쪽으로 틀리고, 넓게 틀린
 * 것은 화면이 잘 보이기 때문에 아무도 신고하지 않는다.
 */

const SCOPE_KO = { global: "전체 관리자", org: "조직관리자", dept: "부서관리자" };

function Findings({ finding, onFix }) {
  const [selected, setSelected] = React.useState(() => new Set());
  const toggle = (id) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  const allIds = finding.items.map((i) => i.id);
  const allChosen = allIds.length > 0 && allIds.every((id) => selected.has(id));

  const columns = [
    finding.fixable_here
      ? {
          key: "_pick", label: "", nowrap: true, width: "3rem",
          render: (r) => (
            <input
              type="checkbox"
              checked={selected.has(r.id)}
              onChange={() => toggle(r.id)}
              aria-label={`${r.display_name || r.title || r.name || r.id} 선택`}
            />
          ),
        }
      : null,
    {
      key: "name", label: "대상", identifier: true,
      render: (r) => r.display_name || r.title || r.name || r.id,
    },
    { key: "detail", label: "메모", render: (r) => r.email || r.reason || r.code || (r.projects || []).join(", ") || "-" },
  ].filter(Boolean);

  return (
    <Card sx={{ mb: 2.5 }}>
      <SectionTitle
        component="h2"
        title={finding.title}
        action={
          <Badge value={`${finding.count}건`} kind={finding.count ? "warn" : "ok"} />
        }
      />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{finding.why}</Typography>
      <Callout tone="info">{finding.remedy}</Callout>

      {/* `art` 는 예전에 `"done"` 이었다 — `lib/assets.js::ART` 에 없는 키라 일러스트가
          조용히 안 그려졌다(오류도 안 난다). 실제 키는 `success` 다. */}
      {finding.count === 0 ? (
        <EmptyState title="해당 없음" help="이 항목에서 정리할 것이 없습니다." art="success" />
      ) : (
        <>
          {finding.count > finding.items.length ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              전체 {finding.count}건 중 {finding.items.length}건만 표에 보입니다. 나머지는 정리한
              뒤 다시 열면 이어서 나타납니다.
            </Typography>
          ) : null}
          <Box sx={{ mt: 1.5 }}>
            <DataTable columns={columns} rows={finding.items} rowKey={(r) => r.id} />
          </Box>
          {finding.fixable_here ? (
            <Box sx={{ mt: 1.5, display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
              <Button
                size="sm" variant="ghost"
                onClick={() => setSelected(allChosen ? new Set() : new Set(allIds))}
              >
                {allChosen ? "선택 해제" : "이 표 전체 선택"}
              </Button>
              <Typography variant="body2" color="text.secondary">
                {selected.size}건 선택됨
              </Typography>
              <Box sx={{ flex: 1 }} />
              {onFix ? onFix([...selected], () => setSelected(new Set())) : null}
            </Box>
          ) : null}
        </>
      )}
    </Card>
  );
}

function MembershipFixer({ ids, onDone, departments }) {
  const [target, setTarget] = React.useState("");
  const toast = useToast();
  const qc = useQueryClient();
  const run = useMutation({
    mutationFn: () =>
      api("/api/admin/integrity/membership", {
        method: "POST",
        body: target === "__org__"
          ? { user_ids: ids, organization_direct: true }
          : { user_ids: ids, department_id: target },
      }),
    onSuccess: (res) => {
      toast(`${res.changed}명의 소속을 지정했습니다.`);
      onDone();
      qc.invalidateQueries({ queryKey: ["integrity"] });
    },
    onError: (err) => toast(err?.message || "지정하지 못했습니다.", "danger"),
  });

  return (
    <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
      {/* 소속은 Entity 다 — 조직이 자라면 후보도 자란다(W5 · R-5). 실측에서 이 자리가
          `plain_dropdown_for_entity` 로 잡혔다(`/integrity` 4 조합). 「조직 직속(부서 없음)」은
          부서 목록의 한 항목이 아니라 **부서를 안 붙인다**는 뜻이라 후보 맨 앞에 둔다. */}
      <EntityCombobox
        label="지정할 소속"
        value={target}
        onChange={setTarget}
        options={[{ value: "__org__", label: "조직 직속(부서 없음)" }]
          .concat(departments.map((d) => ({ value: d.id, label: d.name })))}
        allLabel="소속을 고르세요"
        sx={{ minWidth: "16rem" }}
      />
      <Button
        variant="primary" size="sm"
        disabled={!target || ids.length === 0 || run.isPending}
        onClick={() => run.mutate()}
      >
        선택한 {ids.length}명에 적용
      </Button>
    </Box>
  );
}

export function Integrity() {
  const q = useQuery({ queryKey: ["integrity"], queryFn: () => api("/api/admin/integrity") });
  // 부서 목록은 일괄 지정 드롭다운에만 쓴다 — 진단 응답에 끼워 넣으면 그 응답이 두 가지
  // 일을 하게 되고, 부서가 바뀔 때 진단 캐시까지 함께 무효화해야 한다.
  const depts = useQuery({
    queryKey: ["integrity", "departments"],
    queryFn: () => api("/api/admin/departments?active=true&page_size=200"),
  });

  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Card><Skeleton lines={6} /></Card>;

  const data = q.data;
  const departments = ((depts.data && depts.data.items) || []).map((d) => ({
    id: d.id, name: d.name,
  }));
  const admins = data.admins || { by_scope: {}, items: [], total: 0 };

  return (
    <Box className="c-screen">
      <PageHeader
        area="운영" title="조직 정합성"
        help="소속을 판정할 수 없어 화면에서 닫혀 있는 데이터를 모아 보여 줍니다. 여기서 지정하면 그 즉시 열립니다."
      />

      {data.total_issues === 0 ? (
        <Callout tone="ok">정리할 것이 없습니다. 모든 자원의 소속이 판정 가능합니다.</Callout>
      ) : (
        <Callout tone="warn">
          소속을 판정할 수 없는 항목이 모두 {data.total_issues}건 있습니다. 그동안 이 데이터는
          전체 관리자 외에는 아무에게도 보이지 않습니다.
        </Callout>
      )}

      <Box sx={{ mt: 2.5 }}>
        {data.findings.map((f) => (
          <Findings
            key={f.key}
            finding={f}
            onFix={
              f.key === "users_without_membership"
                ? (ids, reset) => (
                    <MembershipFixer ids={ids} onDone={reset} departments={departments} />
                  )
                : null
            }
          />
        ))}
      </Box>

      <Card>
        <SectionTitle
          component="h2"
          title="관리자 범위 현황"
          help="조직 관리자와 부서 관리자는 role=admin 과 관리 범위의 조합입니다. 전부 '전체 관리자'라면 범위 기능이 실제로는 쓰이지 않고 있다는 뜻입니다."
        />
        <MetricStrip
          ariaLabel="관리자 범위 현황"
          items={["global", "org", "dept"].map((k) => ({
            key: k,
            value: admins.by_scope[k] || 0,
            label: SCOPE_KO[k],
            kind: k === "global" && (admins.by_scope[k] || 0) === admins.total ? "warn" : undefined,
          }))}
          sx={{ mb: 2 }}
        />
        <DataTable
          columns={[
            { key: "display_name", label: "이름", identifier: true },
            { key: "role", label: "역할", nowrap: true },
            {
              key: "admin_scope", label: "관리 범위", nowrap: true,
              render: (r) => (
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold }}>
                    {SCOPE_KO[r.admin_scope] || r.admin_scope}
                  </Typography>
                  <OrgPath path={r.scope_path} />
                </Box>
              ),
            },
          ]}
          rows={admins.items}
          rowKey={(r) => r.id}
          empty="관리자 계정이 없습니다."
        />
      </Card>
    </Box>
  );
}

export default Integrity;
