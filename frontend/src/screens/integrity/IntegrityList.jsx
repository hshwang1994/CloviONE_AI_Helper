import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { api } from "../../lib/api.js";
import { errorText } from "../../lib/failure.js";
import { roleLabel } from "../../lib/roles.js";
import { useInfiniteList, useResetScrollOnKeyChange } from "../../lib/useInfiniteList.js";
import { useQueryState } from "../../lib/useQueryState.js";
import { Button, Callout, CountChip, DataTable, ErrorState, useToast } from "../../ui/kit.jsx";
import { SettingRow, SettingRows } from "../../ui/adminKit.jsx";
import { selectionColumn, useRowSelection } from "../../ui/bulkSelect.jsx";
import { FilterBar } from "../../ui/FilterBar.jsx";
import { EntityCombobox, FilterSelect, SearchBox } from "../../ui/filters.jsx";
import { OrgPath } from "../../ui/OrgPath.jsx";
import { ProjectPicker } from "../../ui/ProjectPicker.jsx";
import { FONT_WEIGHT } from "../../ui/theme.js";
import {
  FIX_PICKER_LABEL, FIX_TARGET, KIND_UNIT, ORG_CHOICE, ORG_CHOICE_LABEL, SEARCH_PLACEHOLDER,
  applyLabel, columnsFor, fixBody,
} from "./checks.js";

/* 조직 정합성의 탭 본문 (계획 3.2, D-508).
 *
 * 탭 하나는 행을 가진 표 하나(사람 · 티켓 · 프로젝트와 문서 공간 · 회차)이고, 그 안의 검사는 「문제 종류」
 * 선택으로 바꾼다. 목록은 서버가 페이지로 준다(`GET /api/admin/integrity/checks/{key}`) - 예전 화면은 검사마다
 * 50건 표본만 그려 51번째 행부터는 볼 길이 없었다.
 *
 * 고치기는 전역 관리자만 한다(서버가 CONSOLE_WRITE + 전역 범위로 막는다). 그 사람에게만 선택 열과 작업 줄이
 * 서고, 부서 후보도 그때만 받는다 - 운영자와 감사자는 진단만 본다. 작업은 원래 수정 함수를 지나므로(서버
 * `POST /checks/{key}/fix`) 감사 기록이 각 화면에서 고친 것과 같다. */

export const INTEGRITY_KEY = ["integrity"];

const TAB_SPEC = { issue: "", q: "" };

/** 검사가 모두 0건인 탭 - 한 줄 안내와 검사 목록. 검사 목록은 이 탭이 무엇을 보는지 말한다.
 *
 * 🔴 줄이 판 끝까지 늘면 「0건」 칩이 이름에서 1,600px 떨어져 섰다(1920). 줄 묶음은 반 칸 폭이다(`SettingRows width="form"`,
 * D-590) — 칩이 이름 · 설명과 한 덩어리로 읽히고, 좁은 폭(두 칸 문턱 미만)에서는 판 폭을 다 쓴다. 줄은 설명이 잘리지 않는 일반
 * 줄이다(`compact` 의 한 줄 말줄임은 개인 설정 훑기 목록 몫이다 — 반 칸 폭에서 「…볼 수 없습니다」가 잘렸다). */
function ClearTab({ findings }) {
  return (
    <Box sx={{ display: "grid", gap: 1.5 }}>
      <Callout tone="ok" variant="inline">이 탭에서 정리할 항목이 없습니다.</Callout>
      <SettingRows width="form">
        {findings.map((f, i) => (
          <SettingRow
            key={f.key} label={f.title} description={f.why} action={<CountChip value="0건" />}
            last={i === findings.length - 1}
          />
        ))}
      </SettingRows>
    </Box>
  );
}

function useDepartments(enabled) {
  // 부서 목록은 작업 줄에만 쓴다 - 요약 응답에 끼워 넣으면 부서가 바뀔 때 진단 캐시까지 무효화해야 한다.
  // 페이지 인자는 없다 - 그 API 에 페이지가 없어서 전건이 온다(P-76).
  return useQuery({
    queryKey: ["integrity-departments"],
    queryFn: () => api("/api/admin/departments?active=true"),
    enabled,
  });
}

/** 고른 행에 할 일 - 대상 고르개와 적용 단추. 선택 줄(발) 오른쪽에 선다. */
function FixControls({ finding, fix, ids, unit, onDone }) {
  const target = FIX_TARGET[fix];
  const [value, setValue] = React.useState("");
  const toast = useToast();
  const qc = useQueryClient();
  const depts = useDepartments(target === "membership" || target === "department");
  const run = useMutation({
    mutationFn: () => api(`/api/admin/integrity/checks/${finding.key}/fix`, {
      method: "POST", body: fixBody(fix, value, ids),
    }),
    onSuccess: (res) => {
      const skipped = Array.isArray(res.skipped) ? res.skipped : [];
      // 건너뛴 항목이 있으면 아래 안내가 말한다(`onDone`). 다 고쳤을 때만 토스트다.
      if (!skipped.length) toast(`${res.changed}${unit}을 고쳤습니다.`);
      onDone(res);
      qc.invalidateQueries({ queryKey: INTEGRITY_KEY });
    },
    onError: (err) => onDone(null, err),
  });
  const deptOptions = ((depts.data && depts.data.items) || []).map((d) => ({ value: d.id, label: d.name }));
  const needsValue = target != null;
  let picker = null;
  if (target === "membership") {
    picker = (
      <EntityCombobox
        layout="row" label={FIX_PICKER_LABEL[fix]} value={value} onChange={setValue}
        options={[{ value: ORG_CHOICE, label: ORG_CHOICE_LABEL[fix] }].concat(deptOptions)}
        loading={depts.isLoading} allLabel="소속을 고르세요" sx={{ minWidth: "16rem" }}
      />
    );
  } else if (target === "department") {
    picker = (
      <EntityCombobox
        layout="row" label={FIX_PICKER_LABEL[fix]} value={value} onChange={setValue} options={deptOptions}
        loading={depts.isLoading} allLabel="부서를 고르세요" sx={{ minWidth: "16rem" }}
      />
    );
  } else if (target === "project") {
    picker = (
      <ProjectPicker
        layout="row" label={FIX_PICKER_LABEL[fix]} value={value} onChange={setValue}
        allLabel="프로젝트를 고르세요" sx={{ minWidth: "16rem" }}
      />
    );
  }
  /* 선택 발은 밀집 줄(30)이다(`SelectionBar`) - 고르개는 칸 안 접두 이름으로, 적용 단추와 같은 높이 · 같은 윗선에 선다
     (D-526). 예전에는 라벨 위 36 칸 옆에 30 단추가 11px 떠 있었다. */
  return (
    <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
      {picker}
      <Button
        variant="primary" size="sm"
        disabled={ids.length === 0 || (needsValue && !value) || run.isPending}
        loading={run.isPending}
        onClick={() => run.mutate()}
      >
        {applyLabel(fix, ids.length, unit)}
      </Button>
    </Box>
  );
}

/** 작업 결과 - 오류와 건너뛴 항목. 다음에 적용하거나 다른 검사로 옮기면 걷힌다. */
function resultNotice(result, unit) {
  if (!result) return null;
  if (result.error) return { tone: "danger", text: errorText(result.error, "선택한 항목을 고치지 못했습니다. 잠시 후 다시 시도해 주세요.") };
  const skipped = Array.isArray(result.skipped) ? result.skipped : [];
  if (!skipped.length) return null;
  const first = skipped[0] || {};
  const who = first.title || first.id || "";
  return {
    tone: "warn",
    text: `${result.changed}${unit}을 고쳤습니다. ${skipped.length}${unit}은 고치지 못했습니다.`
      + (who ? ` ${who}: ${first.reason || ""}` : ` ${first.reason || ""}`),
  };
}

function CheckList({ finding, findings, q, onIssue, onSearch, canFix }) {
  const nav = useNavigate();
  const fix = canFix && finding.fixes && finding.fixes.length ? finding.fixes[0] : null;
  const unit = KIND_UNIT[finding.kind] || "건";
  const list = useInfiniteList({
    key: [...INTEGRITY_KEY, "check", finding.key, q],
    rowId: (r) => (r && r.id) || undefined,
    fetch: (params) => api(`/api/admin/integrity/checks/${finding.key}?` + new URLSearchParams({
      ...Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v)])),
      ...(q ? { q } : {}),
    }).toString()),
  });
  useResetScrollOnKeyChange(`${finding.key}|${q}`);
  const selection = useRowSelection();
  const [result, setResult] = React.useState(null);
  const { clear } = selection;
  React.useEffect(() => { clear(); setResult(null); }, [q, clear]);

  const ids = list.rows.map((r) => r.id);
  const columns = [fix ? selectionColumn(selection, ids) : null, ...columnsFor(finding.kind)].filter(Boolean);
  /* 링크가 없는 행(팀 없는 회차 - 작업 보드는 팀의 회차만 보여 준다)은 열지 않는다. 막다른 링크를 걸지 않는다. */
  const linked = list.rows.some((r) => r && r.link);
  const notice = resultNotice(result, unit);

  return (
    <Box sx={{ display: "grid", rowGap: 2 }}>
      <FilterBar
        search={(
          <SearchBox
            value={q} onSearch={onSearch}
            placeholder={SEARCH_PLACEHOLDER[finding.kind] || "검색"} ariaLabel="정합성 항목 검색"
          />
        )}
        conditions={q ? {
          chips: [{ key: "q", label: `검색: ${q}`, onDelete: () => onSearch("") }],
          total: list.total, unit, onClearAll: () => onSearch(""),
        } : undefined}
      >
        <FilterSelect
          label="문제 종류" value={finding.key} onChange={onIssue} noAllOption size="XL"
          /* 칸에는 짧은 이름이 선다(D-530 — 검사 제목은 문장이라 칸에서 여섯 글자 뒤로 잘렸다). 고른 검사의 문장은 아래 머리가 말한다. */
          options={findings.map((f) => ({ value: f.key, label: `${f.short || f.title} ${f.count}건` }))}
        />
      </FilterBar>
      <Callout tone="info" variant="inline">{finding.why} {finding.remedy}</Callout>
      {notice ? <Callout tone={notice.tone} compact>{notice.text}</Callout> : null}
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : (
        <DataTable
          placement="surface"
          columns={columns}
          rows={list.rows}
          rowKey={(r) => r.id}
          loading={list.isLoading}
          rowSelected={fix ? (r) => selection.selected.has(r.id) : undefined}
          onRow={linked ? (r) => { if (r.link) nav(r.link.replace(/^#/, "")); } : undefined}
          rowHref={linked ? (r) => r.link || undefined : undefined}
          empty={q ? "검색 조건에 맞는 항목이 없습니다." : "정리할 항목이 없습니다."}
          list={{
            total: list.total, loaded: list.loaded, hasNext: list.hasNext,
            isFetchingNext: list.isFetchingNext, onMore: list.fetchNext, unit, moreLabel: "항목 더 보기",
          }}
          selection={fix ? {
            count: selection.selected.size,
            unit,
            onClear: clear,
            actions: (
              <FixControls
                finding={finding} fix={fix} ids={[...selection.selected]} unit={unit}
                onDone={(res, err) => { setResult(err ? { error: err } : res); clear(); }}
              />
            ),
          } : undefined}
        />
      )}
    </Box>
  );
}

/** 탭 하나 - 검사를 고르고(`?issue=`), 검색하고(`?q=`), 고친다. */
export function IntegrityTab({ findings, canFix }) {
  const [state, setState] = useQueryState(TAB_SPEC);
  const open = findings.filter((f) => f.count > 0);
  if (!open.length) return <ClearTab findings={findings} />;
  /* 주소가 가리키는 검사가 이 탭에 없으면(다른 탭에서 온 `?issue=`) 건수가 있는 첫 검사다. 0건 검사도
     고를 수 있다 - 방금 다 고친 목록이 사라지지 않고 「정리할 항목이 없습니다」로 남는다. */
  const current = findings.find((f) => f.key === state.issue) || open[0];
  return (
    <CheckList
      key={current.key}
      finding={current}
      findings={findings}
      q={state.q}
      canFix={canFix}
      onIssue={(key) => setState({ issue: key, q: "" })}
      onSearch={(q) => setState({ q })}
    />
  );
}

const SCOPE_KO = { global: "전체 관리자", org: "조직관리자", dept: "부서관리자" };

const ADMIN_COLUMNS = [
  /* 「이름」이 그 행의 제목이다(D-501). */
  { key: "display_name", label: "이름", type: "title", rowName: (r) => r.display_name || r.id },
  { key: "email", label: "이메일", type: "identifier" },
  /* 역할은 서버 값(`system_admin`)이 아니라 관리 콘솔의 역할 이름이다 - 말줄임 힌트에도 서버 값이 새지 않는다. */
  { key: "role_label", label: "역할", type: "enum" },
  {
    key: "admin_scope", label: "관리 범위", type: "text",
    render: (r) => (
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold }}>
          {SCOPE_KO[r.admin_scope] || r.admin_scope}
        </Typography>
        <OrgPath path={r.scope_path} />
      </Box>
    ),
  },
];

const ADMIN_SPEC = { q: "" };

/** 관리자 범위 현황 - 참고 목록이라 선택 열도 작업도 없다. */
export function AdminScopeList({ summary }) {
  const [state, setState] = useQueryState(ADMIN_SPEC);
  const q = state.q;
  const list = useInfiniteList({
    key: [...INTEGRITY_KEY, "admins", q],
    rowId: (r) => (r && r.id) || undefined,
    fetch: (params) => api("/api/admin/integrity/admins?" + new URLSearchParams({
      ...Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v)])),
      ...(q ? { q } : {}),
    }).toString()),
  });
  const rows = React.useMemo(
    () => list.rows.map((r) => ({ ...r, role_label: roleLabel(r.role) })),
    [list.rows],
  );
  const allGlobal = summary && summary.total > 0 && (summary.by_scope.global || 0) === summary.total;
  return (
    <Box sx={{ display: "grid", rowGap: 2 }}>
      {allGlobal ? (
        <Callout tone="info" variant="inline">
          모든 관리자가 전체 관리자라서 조직, 부서 범위 기능은 아직 쓰이지 않습니다.
        </Callout>
      ) : null}
      <FilterBar
        search={(
          <SearchBox value={q} onSearch={(next) => setState({ q: next })} placeholder="이름, 이메일 검색" ariaLabel="관리자 검색" />
        )}
      />
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : (
        <DataTable
          placement="surface"
          columns={ADMIN_COLUMNS}
          rows={rows}
          rowKey={(r) => r.id}
          loading={list.isLoading}
          empty="관리자 계정이 없습니다."
          list={{
            total: list.total, loaded: list.loaded, hasNext: list.hasNext,
            isFetchingNext: list.isFetchingNext, onMore: list.fetchNext, unit: "명", moreLabel: "관리자 더 보기",
          }}
        />
      )}
    </Box>
  );
}
