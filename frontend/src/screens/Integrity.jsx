import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { EntityCombobox } from "../ui/filters.jsx";
import { api } from "../lib/api.js";
import { failureText } from "../lib/failure.js";
import { CONSOLE_WRITE_ROLES } from "../lib/roles.js";
import { useAuth } from "../app/auth.jsx";
import {
  Button, Callout, Card, CountChip, DataTable, ErrorState, PageHeader,
  Section, SectionTitle, Skeleton, useToast,
} from "../ui/kit.jsx";
import { StatusSummaryCard } from "../ui/StatusKpi.jsx";
import { SettingRow } from "../ui/adminKit.jsx";
import { selectionColumn, useRowSelection } from "../ui/bulkSelect.jsx";
import { OrgPath } from "../ui/OrgPath.jsx";
import { FONT_WEIGHT } from "../ui/theme.js";
import { GRID_GAP, pairTracks } from "../ui/density.js";

/* 정리할 항목 : 관리자 범위 — 회의 화면의 2:1 보다 오른쪽을 조금 넓게 둔다(세 열 표가 든다). */
const ADMIN_SCOPE_PAIR = "minmax(0, 1.6fr) minmax(0, 1fr)";

/* 조직 정합성 진단 — **닫아 버린 것을 사람에게 보여 주는 화면** (0060 §41).
 *
 * 이 제품의 접근 모델은 "소속을 모르면 닫는다" 다. 그 규칙만 있으면 안전하기는 한데
 * 아무도 원인을 못 찾는다 — 증상이 "권한이 없습니다" 가 아니라 **"목록이 비어 있음"** 이기
 * 때문이다. 그래서 닫는 규칙과 이 화면은 같은 배포에 있어야 한다.
 *
 * 화면이 하는 일은 둘뿐이다: **세고**, **일괄로 지정한다**. 추측해서 자동으로 고치지 않는다 —
 * "부서를 모르니 조직 직속으로 하자" 같은 추측은 언제나 넓히는 쪽으로 틀리고, 넓게 틀린
 * 것은 화면이 잘 보이기 때문에 아무도 신고하지 않는다.
 *
 * ## 판은 정리할 것이 있는 항목에만 준다
 *
 * 예전에는 항목 여섯이 건수와 무관하게 각각 판이었다 — 0건인 항목도 제목·설명·안내 상자·
 * 클로비 그림을 갖춘 250px 판을 차지해, 정상인 설치에서 이 화면이 1,500px 를 넘겼다. 이제
 * 건수가 있는 항목만 판(제목 + 건수 + 표 + 지정 줄)이고, 0건은 이름과 「0건」 표지의 줄 하나다.
 */

const SCOPE_KO = { global: "전체 관리자", org: "조직관리자", dept: "부서관리자" };

/* 행을 구별하는 이름 — 화면의 「대상」 열과 선택 체크박스의 접근 이름이 같은 값을 쓴다. */
const targetName = (r) => r.display_name || r.title || r.name || r.id;

/* 건수가 있는 항목 하나 — 판이다. 선택 열은 공용 `selectionColumn` 이라 다른 목록 화면과
   같은 체크박스(전체 선택 머리 칸 포함)를 쓴다. */
function Findings({ finding, onFix }) {
  const selection = useRowSelection();
  const allIds = finding.items.map((i) => i.id);

  const columns = [
    finding.fixable_here ? selectionColumn(selection, allIds) : null,
    { key: "name", label: "대상", identifier: true, rowName: targetName, render: targetName },
    { key: "detail", label: "메모", type: "text", render: (r) => r.email || r.reason || r.code || (r.projects || []).join(", ") || "-" },
  ].filter(Boolean);

  return (
    <Card>
      <SectionTitle
        component="h3"
        title={finding.title}
        help={finding.why}
        action={<CountChip value={`${finding.count}건`} />}
      />
      <Callout tone="info" variant="inline">{finding.remedy}</Callout>
      {/* 판 안 보조 표 — 머리 · 발이 판 여백을 거슬러 판 가장자리까지 편다(`placement="card"`, 조합 계약 C-3). 건수는 제목
          옆 칩이 말하므로 발은 잘린 목록일 때만 선다 — 그 문장이 발 문장이다.
          소속 지정 줄은 발의 선택 묶음이 아니다: 선택이 0건이어도 서는 지정 폼이고, 적용한 뒤 선택을 비워도 건너뛴 사람을
          말하는 상자를 들고 있어야 한다(R5-04). 선택이 없으면 비는 발 오른쪽 칸과 뜻이 다르다. */}
      <Box sx={{ mt: 1.5 }}>
        <DataTable
          placement="card"
          list={false}
          columns={columns} rows={finding.items} rowKey={(r) => r.id}
          note={finding.count > finding.items.length
            ? `전체 ${finding.count}건 중 ${finding.items.length}건만 표에 보입니다. 나머지는 정리한 뒤 다시 열면 이어서 나타납니다.`
            : undefined}
        />
      </Box>
      {finding.fixable_here ? (
        <Box sx={{ mt: 1.5, display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="body2" color="text.secondary">
            {selection.selected.size}건 선택됨
          </Typography>
          <Box sx={{ flex: 1 }} />
          {onFix ? onFix([...selection.selected], selection.clear) : null}
        </Box>
      ) : null}
    </Card>
  );
}

/* 0건 항목들 — 판 없이 줄 하나씩. 이름과 «왜 문제인가» 는 남기고 안내(remedy)는 뺀다 —
   정리할 것이 없는 항목에 정리하는 법을 적어 두면 읽을 사람이 없다. */
function ClearFindings({ findings }) {
  return (
    <Box>
      {findings.map((f, i) => (
        <SettingRow
          key={f.key}
          label={f.title}
          description={f.why}
          last={i === findings.length - 1}
          action={<CountChip value="0건" />}
        />
      ))}
    </Box>
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
      /* 🔴 **건너뛴 사람을 말하지 않으면 아무도 모른다**(R5-04). 서버는 행마다 사유를 함께
         주는데(`app/integrity/service.py::_skip_reason` — 없는 계정·보관·비활성·이미 소속
         있음) 화면은 바뀐 건수만 읽고 있었다. 50명을 골랐는데 48명만 바뀐 회차가 「48명의
         소속을 지정했습니다」로 끝나면, 남은 둘은 다음에 이 화면을 다시 열 때까지 없는
         사람이 된다. 사유는 종류가 몇 개뿐이라 첫 사유 하나로 요약한다 — 전부 나열하면
         토스트가 화면을 덮는다. */
      const skipped = Array.isArray(res.skipped) ? res.skipped : [];
      // 건너뛴 사람은 이 줄 아래 메시지 박스가 말한다(`skippedNotice`) — 다 지정했을 때만 토스트다.
      if (!skipped.length) toast(`${res.changed}명의 소속을 지정했습니다.`);
      onDone();
      qc.invalidateQueries({ queryKey: ["integrity"] });
    },
  });
  /* 지정 실패(오류)와 건너뛴 사람(주의) — 다음에 적용하면 걷힌다. 문구는 토스트 때와 같다. */
  const runFailure = failureText([run, "지정하지 못했습니다."]);
  const skippedRows = !runFailure && run.isSuccess && run.data && Array.isArray(run.data.skipped) ? run.data.skipped : [];
  const skippedFirst = skippedRows[0] || {};
  const skippedWho = skippedFirst.display_name || skippedFirst.user_id || "";
  const skippedNotice = skippedRows.length
    ? `${run.data.changed}명의 소속을 지정했습니다. ${skippedRows.length}명은 지정하지 못했습니다.`
      + (skippedWho ? ` ${skippedWho}: ${skippedFirst.reason || ""}` : ` ${skippedFirst.reason || ""}`)
    : null;

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
      {runFailure || skippedNotice ? (
        <Callout tone={runFailure ? "danger" : "warn"} compact sx={{ flexBasis: "100%" }}>{runFailure || skippedNotice}</Callout>
      ) : null}
    </Box>
  );
}

export function Integrity() {
  const auth = useAuth();
  const role = auth.data ? auth.data.role : null;
  /* 일괄 지정은 **전역 관리자**만 할 수 있다 — 서버가 그렇게 막는다(`app/integrity/router.py`
     `POST /membership` = CONSOLE_WRITE + `_require_global`). 이 화면 자체는 운영자·감사자도
     여는데(진단은 읽기다), 그 역할에게 지정 폼을 그리면 누르는 순간 403 이고, 부서 후보를
     받는 요청(`/api/admin/departments` 는 admin 이상)도 화면을 열 때마다 403 으로 실패했다.
     그래서 폼도 후보 요청도 지정할 수 있는 사람에게만 있다. */
  const canAssign = role != null && CONSOLE_WRITE_ROLES.includes(role)
    && (!auth.data || !auth.data.admin_scope || auth.data.admin_scope === "global");
  const q = useQuery({ queryKey: ["integrity"], queryFn: () => api("/api/admin/integrity") });
  // 부서 목록은 일괄 지정 드롭다운에만 쓴다 — 진단 응답에 끼워 넣으면 그 응답이 두 가지
  // 일을 하게 되고, 부서가 바뀔 때 진단 캐시까지 함께 무효화해야 한다. `page_size` 는
  // 없다 — 그 API 에 페이지가 없어서 전건이 온다(P-76: 있는 척하는 인자를 지웠다).
  const depts = useQuery({
    queryKey: ["integrity", "departments"],
    queryFn: () => api("/api/admin/departments?active=true"),
    enabled: canAssign,
  });

  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Card><Skeleton lines={6} /></Card>;

  const data = q.data;
  const departments = ((depts.data && depts.data.items) || []).map((d) => ({
    id: d.id, name: d.name,
  }));
  const admins = data.admins || { by_scope: {}, items: [], total: 0 };
  const findings = data.findings || [];
  const open = findings.filter((f) => f.count > 0);
  const clear = findings.filter((f) => !(f.count > 0));

  return (
    <Box className="c-screen">
      <PageHeader
        area="운영" title="조직 정합성"
        description="조직 정합성 규칙이 소속을 정할 수 없어 자동으로 닫아 둔 항목을 모아 봅니다."
        help="소속을 판정할 수 없어 화면에서 닫혀 있는 데이터를 모았습니다. 여기서 지정하면 바로 열립니다."
      />

      {data.total_issues === 0 ? (
        <Callout tone="ok">정리할 것이 없습니다. 모든 자원의 소속이 판정 가능합니다.</Callout>
      ) : (
        <Callout tone="warn">
          소속을 판정할 수 없는 항목이 모두 {data.total_issues}건 있습니다. 그동안 이 데이터는
          전체 관리자 외에는 아무에게도 보이지 않습니다.
        </Callout>
      )}

      {/* 왼쪽이 정리할 항목, 오른쪽이 관리자 범위 — 예전에는 둘이 세로로 이어져 관리자 범위
          표를 보려면 판 여섯을 지나야 했다. 짝은 **xl 부터**다: 1366 에서 세 열짜리 표를 3분의 1
          폭에 넣으면 「관리 범위」 열이 잘린다(실측). 그 아래에서는 한 열로 선다. */}
      <Box sx={{ mt: 2.5, ...pairTracks(ADMIN_SCOPE_PAIR), gridTemplateColumns: { xs: "minmax(0, 1fr)", xl: ADMIN_SCOPE_PAIR } }}>
        <Section titleAs="h2" title="정리할 항목" rule sx={{ mb: 0 }}>
          {open.length ? (
            <Box sx={{ display: "grid", gap: GRID_GAP, mb: clear.length ? GRID_GAP : 0 }}>
              {open.map((f) => (
                <Findings
                  key={f.key}
                  finding={f}
                  onFix={
                    f.key === "users_without_membership" && canAssign
                      ? (ids, reset) => (
                          <MembershipFixer ids={ids} onDone={reset} departments={departments} />
                        )
                      : null
                  }
                />
              ))}
            </Box>
          ) : null}
          {clear.length ? <ClearFindings findings={clear} /> : null}
        </Section>

        <Section
          titleAs="h2"
          title="관리자 범위 현황"
          help="조직이나 부서 관리자는 admin과 범위의 조합입니다. 전부 ‘전체’면 범위 기능은 쓰이지 않는 것입니다."
          rule
          sx={{ mb: 0 }}
        >
          {/* 범위 셋의 합이 관리자 전체인 구성이다 — 상태 요약 카드(계획 표 7). */}
          <StatusSummaryCard
            ariaLabel="관리자 범위 현황"
            total={admins.total}
            items={["global", "org", "dept"].map((k) => ({
              key: k,
              value: admins.by_scope[k] || 0,
              label: SCOPE_KO[k],
              kind: k === "global" && (admins.by_scope[k] || 0) === admins.total ? "warn" : undefined,
            }))}
            sx={{ mb: 2 }}
          />
          {/* 목록 판 — 판이 곧 표 상자다(조합 계약 C-3). */}
          <DataTable
              placement="surface"
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
        </Section>
      </Box>
    </Box>
  );
}

export default Integrity;
