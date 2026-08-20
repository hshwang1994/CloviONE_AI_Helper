import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api.js";
import { useAuth } from "../../app/auth.jsx";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { Callout, Button, DataTable, Modal, EmptyState, ErrorState, useConfirm, useToast } from "../../ui/kit.jsx";
import { handleApiError } from "./apiError.js";
import { JsonBlock } from "./JsonBlock.jsx";
import { successMessageFor } from "./successMessages.js";

/* 하위 리소스 드로어 — 액션의 subList로 지정한 엔드포인트(버전·실행 이력 등)를 조회해 표로 보여준다.
 * subList.rowAction이 있으면 각 하위 행에 작업(예: 특정 버전으로 롤백)을 건다. */
export function SubListDrawer({ view, onClose, onActed }) {
  const { a, row } = view;
  const sl = a.subList;
  const confirm = useConfirm();
  const toast = useToast();
  const auth = useAuth();
  const role = (auth && auth.data && auth.data.role) || null;
  // 하위 행 작업(롤백·재시도 등)도 role 게이트 — 백엔드 RBAC와 일치시켜 권한 없는 버튼을 숨긴다.
  const canDoRa = (ra) => !ra.roles || (role != null && ra.roles.includes(role));
  const [subPage, setSubPage] = useState(1);
  const [subFilters, setSubFilters] = useState({});
  const [subInfo, setSubInfo] = useState(null);   // 조회형 하위 행 작업(예: 버전 비교 diff) 결과 모달
  // 하위 행 작업 실행 중 — 부모 drawer의 busyKey와 동일한 패턴으로 '어느 행의 어느 액션'인지
  // key로 구분한다(예전엔 단순 boolean이라 하나를 누르면 이 하위 목록의 모든 행·모든 액션 버튼이
  // 동시에 '처리 중…'으로 바뀌었다 — localInfo처럼 네트워크 호출조차 없는 동기 작업까지 포함해).
  const [subBusyKey, setSubBusyKey] = useState(null);
  const subBusy = subBusyKey != null;
  const subRowKey = (r) => r.id != null ? r.id : (r.version != null ? r.version : JSON.stringify(r).slice(0, 24));
  const setSubFilter = (k, v) => { setSubFilters((s) => ({ ...s, [k]: v })); setSubPage(1); };
  // endpoint는 (row, {page, filters})로 호출한다(기존 subList는 2번째 인자를 무시하므로 하위호환).
  const q = useQuery({
    queryKey: ["sub", a.label, row.id, subPage, JSON.stringify(subFilters)],
    queryFn: () => api(sl.endpoint(row, { page: subPage, filters: subFilters })),
    retry: false,
  });
  const rawRows = (q.data && q.data[sl.itemsKey || "items"]) || [];
  // sl.filterRows(row, parentRow) — 백엔드가 이 하위 목록을 부모 행 기준으로 필터할 쿼리 파라미터를
  // 지원하지 않을 때(예: 템플릿 목록엔 policy_id 필터가 없다) 이미 받아 온 전체 목록을 화면에서
  // 직접 거른다(DataScreen 메인 목록의 clientFilter와 동일한 발상).
  const rows = sl.filterRows ? rawRows.filter((r) => sl.filterRows(r, row)) : rawRows;
  const total = q.data && q.data.total;
  const pageSize = (q.data && q.data.page_size) || 20;
  // 부모 목록의 페이저와 동일한 fallback — total이 없는 하위 목록 응답도(paginated:true인데 total
  // 미포함) 이번 페이지가 꽉 찼으면 '다음'을 계속 켜 둔다(DataScreen.jsx 메인 페이저와 동일한 이유).
  const totalPages = (sl.paginated && total != null) ? Math.max(1, Math.ceil(total / pageSize)) : null;
  async function act(ra, subRow, key) {
    // 조회형(로컬) 하위 행 작업 — 네트워크 호출 없이 이미 불러온 하위 행 데이터를 그대로 안내 모달로
    // 보여준다(예: 실행 이력 목록에서는 60자로 자르는 보낸 페이로드/응답 요약의 전체 텍스트 보기).
    // 동기 작업이라 busy 상태를 걸 필요가 없다(예전엔 이것도 subBusy를 켜서 다른 모든 행의 버튼까지
    // '처리 중…'으로 바꿨다 — 네트워크 호출이 전혀 없는데도).
    if (ra.localInfo) { setSubInfo({ title: ra.label, body: ra.localInfo(subRow, row) }); return; }
    // 조회형(GET) 하위 행 작업 — 목록 갱신·드로어 닫기 없이 결과를 안내 모달로 보여준다(예: 버전 비교 diff).
    if (ra.info) {
      setSubBusyKey(key);
      try { const res = await api(ra.path(subRow, row), { method: ra.method || "GET" }); setSubInfo({ title: ra.label, body: ra.info(res) }); }
      catch (e) { handleApiError(e, toast); }
      finally { setSubBusyKey(null); }
      return;
    }
    // confirm은 path/when/body와 동일하게 (하위 행, 부모 행) 두 인자를 받는다 — 부모 행 상태에 따라
    // 다른 경고를 붙여야 하는 롤백(예: 예약 워크플로 경고)을 지원한다.
    if (ra.confirm && !(await confirm(ra.confirm(subRow, row), { danger: ra.variant === "danger", confirmLabel: ra.label }))) return;
    setSubBusyKey(key);
    try {
      const res = await api(ra.path(subRow, row), { method: ra.method || "POST", body: ra.body ? ra.body(subRow) : {} });
      // 승인 게이트가 걸리면 202 approval_pending — 성공으로 오인하지 않게 안내(예: 연동 롤백).
      if (res && (res.status === "approval_pending" || res.approval_pending)) toast("승인 요청이 접수되었습니다. 관리자 승인 후 반영됩니다.", "info");
      else toast(successMessageFor(ra.label), "success");
      onActed();
      // keepOpen — 이 하위 행 작업이 지금 보고 있는 바로 이 목록 안의 항목을 제자리에서 바꿀 뿐이면
      // (예: 실행 이력의 '재시도') 드로어를 닫지 않고 하위 목록만 다시 불러온다. 방금 누른 결과를
      // 보려고 재시도했는데 곧바로 드로어가 닫혀 다시 열어야 했던 것을 없앤다. 그 외(예: 버전
      // 롤백처럼 하위 목록을 벗어나는 게 자연스러운 작업)는 기존처럼 닫는다.
      if (ra.keepOpen) q.refetch(); else onClose();
    } catch (e) { handleApiError(e, toast); }
    finally { setSubBusyKey(null); }
  }
  // subList는 단일 rowAction(하위호환) 또는 rowActions 배열(롤백+비교 등 다중)을 받는다. when은 (하위행, 부모행).
  const rowActions = sl.rowActions || (sl.rowAction ? [sl.rowAction] : []);
  const cols = rowActions.length
    ? [...sl.columns, { key: "_act", label: "", render: (r) => {
        const visible = rowActions.filter((ra) => (!ra.when || ra.when(r, row)) && canDoRa(ra));
        // sl.actionHint(하위 행, 부모 행), 액션이 when()으로 숨겨졌을 때, 왜 숨겨졌는지 이유를 그
        // 빈 자리에 대신 보여준다(예: 스케줄 재시도가 부모 스케줄 비활성으로 숨겨진 경우, 예전엔
        // 버튼만 조용히 사라지고 아무 설명도 없었다).
        if (!visible.length && sl.actionHint) {
          const hint = sl.actionHint(r, row);
          if (hint) return <span>{hint}</span>;
        }
        return <>{visible.map((ra, i) => {
          const key = subRowKey(r) + ":" + ra.label;
          // 클릭한 그 버튼만 라벨이 '처리 중…'으로 바뀐다(disabled는 중복 제출 방지를 위해 전체에
          // 걸지만, 라벨은 실제로 진행 중인 액션 하나만, 부모 drawer의 busyKey와 동일한 패턴).
          return <Button key={i} size="sm" variant={ra.variant || "default"} disabled={subBusy} onClick={() => act(ra, r, key)}>{subBusyKey === key ? "처리 중…" : ra.label}</Button>;
        })}</>;
      } }]
    : sl.columns;
  return (
    <Modal open onClose={onClose} title={sl.title || a.label}>
      {/* sl.hint, 이 하위 목록의 동작 중 암묵적 규칙(예: '비교'가 어느 두 버전을 비교하는지)이
       * 목록만 봐서는 드러나지 않을 때 짧은 안내를 붙인다(폼 필드 도움말과 동일한 스타일 재사용). */}
      {sl.hint ? <div className="k-field-help">{sl.hint}</div> : null}
      {/* 부모 DataScreen 툴바와 동일한 필터 유형(select/date/text)을 지원한다, 예전엔 select만
       * 지원해 오늘날 없는 sl.filters의 date/text 사용처가 생겨도 조용히 <select>로 잘못 렌더될
       * 뻔한 계약 불일치가 있었다(공용 목록 필터 규칙과 통일). */}
      {/* 2026-08 MUI 전환. 예전에는 날것의 <input>/<select> 에 .c-filter 클래스를 붙였는데,
          날짜 필터가 쓰던 .c-filter-date 와 .c-filter-date-label 은 **정의된 CSS 규칙이 아예
          없었다** — 라벨과 입력이 스타일 없이 그대로 떴다. 이제 MUI TextField 가 라벨·테두리·
          포커스 링을 전부 갖고 오므로 그 죽은 클래스도 함께 사라진다. */}
      {(sl.filters || []).length ? (
        <Stack direction="row" gap={1.5} flexWrap="wrap" sx={{ mb: 2 }}>
          {(sl.filters).map((f) => f.type === "date" ? (
            <TextField
              key={f.key} type="date" size="small" label={f.label}
              InputLabelProps={{ shrink: true }} sx={{ minWidth: "11rem" }}
              value={subFilters[f.key] || ""} onChange={(e) => setSubFilter(f.key, e.target.value)}
            />
          ) : f.type === "text" ? (
            <TextField
              InputLabelProps={{ shrink: true }}
              key={f.key} size="small" label={f.label} sx={{ minWidth: "12rem" }}
              value={subFilters[f.key] || ""} onChange={(e) => setSubFilter(f.key, e.target.value)}
            />
          ) : (
            <TextField
              InputLabelProps={{ shrink: true }}
              key={f.key} select size="small" label={f.label} sx={{ minWidth: "11rem" }}
              value={subFilters[f.key] || ""} onChange={(e) => setSubFilter(f.key, e.target.value)}
            >
              <MenuItem value="">{f.label}: 전체</MenuItem>
              {(f.options || []).map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </TextField>
          ))}
        </Stack>
      ) : null}
      {/* 부모 목록의 capWarning Callout과 동일한 경고 — 이 하위 목록도 백엔드가 페이지당 최대 500건을
       * 반환한다(app/prompts/router.py). paginated가 아니면(전체를 한 번에 받는 하위 목록) 500건에
       * 닿았을 때 '더 있을 수 있음'을 알린다(안 알리면 잘린 데이터가 조용히 사라진 것처럼 보인다). */}
      {/* filterRows(클라이언트 필터)를 쓰는 하위 목록은 필터 후 행 수(rows)가 아니라 서버가 돌려준
       * 원본(rawRows)이 500건 상한에 닿았는지로 판정해야 한다 — 그렇지 않으면 필터로 몇 건만 남은
       * 경우 상한 경고가 안 떠서, 잘린 원본 때문에 누락된 항목이 있는데도 완전한 목록처럼 보였다
       * (예: 정책의 '이 정책을 쓰는 템플릿' — 발행·롤백 전 영향 범위를 이 불완전한 목록으로 오판할 수 있다). */}
      {!sl.paginated && (sl.filterRows ? rawRows.length >= 500 : rows.length >= 500) ? (
        <Callout tone="warn">{sl.filterRows
          ? "원본 목록이 500건으로 제한되어 이 필터 결과가 불완전할 수 있습니다. 일부 관련 항목이 누락됐을 수 있습니다."
          : "결과가 500건으로 제한되어 일부 항목이 보이지 않을 수 있습니다."}</Callout>
      ) : null}
      {q.isLoading ? <DataTable columns={cols} rows={[]} loading />
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : rows.length === 0 ? <EmptyState title={sl.emptyTitle || "표시할 항목이 없습니다"} help={sl.emptyHelp} />
        : <>
            <DataTable columns={cols} rows={rows} rowKey={(r) => r.id || r.version || JSON.stringify(r).slice(0, 24)} />
            {sl.paginated ? (
              <Stack component="nav" aria-label="페이지 이동" direction="row" gap={1.5}
                sx={{ alignItems: "center", justifyContent: "center", mt: 2 }}>
                <Button size="sm" disabled={subPage <= 1} onClick={() => setSubPage((p) => Math.max(1, p - 1))}>이전</Button>
                <Typography component="span" aria-live="polite" variant="body2" color="text.secondary">
                  {totalPages != null ? `${subPage} / ${totalPages}${total != null ? `, 총 ${total}건` : ""}` : `${subPage}페이지`}
                </Typography>
                <Button size="sm" disabled={totalPages != null ? subPage >= totalPages : rows.length < pageSize} onClick={() => setSubPage((p) => p + 1)}>다음</Button>
              </Stack>
            ) : null}
          </>}
      {subInfo ? (
        <Modal open onClose={() => setSubInfo(null)} title={subInfo.title} size="md"
          footer={<div className="k-footer-row"><div className="k-footer-main"><Button variant="primary" onClick={() => setSubInfo(null)}>확인</Button></div></div>}>
          <JsonBlock>{subInfo.body}</JsonBlock>
        </Modal>
      ) : null}
    </Modal>
  );
}
