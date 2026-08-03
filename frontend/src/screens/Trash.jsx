import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { Badge, Button, Card, DataTable, ErrorState, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { useRowSelection, selectionColumn, BulkActions } from "../ui/bulkSelect.jsx";

/* 휴지통 — 삭제한 티켓/문서를 보관기간 동안 잡아둔다. 복원하면 원래 목록으로 돌아가고, 보관기간이
 * 지나면 백그라운드가 노션 원본을 보관처리하고 여기서 사라진다. 지금 바로 영구 삭제도 가능(권한 필요).
 * 문서 하위 페이지. 종류(티켓/문서)·제목·삭제한 사람·삭제일·삭제 예정일이 보인다. */

function typeKind(t) { return t === "ticket" ? "info" : "purple"; }

export function Trash() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["trash"], queryFn: () => api("/api/trash"), refetchInterval: 15000 });
  const sel = useRowSelection();

  const bulkMsg = (res, verb) => {
    const n = ((res.restored || res.purged) || []).length;
    const f = (res.failed || []).length;
    toast(f ? `${n}건을 ${verb}했습니다. ${f}건은 권한이 없어 건너뛰었습니다.` : `${n}건을 ${verb}했습니다.`, f ? "info" : "success");
    qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
    qc.invalidateQueries({ queryKey: ["tickets"], refetchType: "all" });
    qc.invalidateQueries({ queryKey: ["team-docs"], refetchType: "all" });
    sel.clear();
  };
  const bulkRestore = useMutation({
    mutationFn: (ids) => api("/api/trash/restore-bulk", { method: "POST", body: { ids } }),
    onSuccess: (res) => bulkMsg(res, "복원"),
    onError: (e) => toast((e && e.message) || "복원하지 못했습니다.", "error"),
  });
  const bulkPurge = useMutation({
    mutationFn: (ids) => api("/api/trash/purge-bulk", { method: "POST", body: { ids } }),
    onSuccess: (res) => bulkMsg(res, "영구 삭제"),
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
  });

  const restore = useMutation({
    mutationFn: (id) => api("/api/trash/" + id + "/restore", { method: "POST" }),
    onSuccess: () => {
      toast("복원했습니다. 원래 목록에서 다시 볼 수 있습니다.", "success");
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      qc.invalidateQueries({ queryKey: ["tickets"], refetchType: "all" });
      qc.invalidateQueries({ queryKey: ["team-docs"], refetchType: "all" });
    },
    onError: (e) => toast((e && e.message) || "복원하지 못했습니다.", "error"),
  });
  const purge = useMutation({
    mutationFn: (id) => api("/api/trash/" + id + "/purge", { method: "POST" }),
    onSuccess: () => { toast("영구 삭제했습니다. 원본이 보관처리됐습니다.", "success"); qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" }); },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
  });

  const days = (q.data && q.data.retention_days) || 7;
  const items = (q.data && q.data.items) || [];
  const manageable = new Set(items.filter((i) => i.can_manage).map((i) => i.id));
  const selCol = selectionColumn(sel, items.map((i) => i.id), { eligible: (id) => manageable.has(id) });
  const purgeSelected = async () => {
    const ok = await confirm(`선택한 ${sel.selected.size}건을 영구 삭제합니다. 노션 원본이 보관처리되어 목록에서 사라집니다(노션 휴지통에서 30일 내 복구 가능). 계속할까요?`,
      { title: "선택 영구 삭제", confirmLabel: "영구 삭제", danger: true });
    if (ok) bulkPurge.mutate([...sel.selected]);
  };
  const columns = [
    selCol,
    { key: "type_label", label: "종류", render: (r) => <Badge value={r.type_label} kind={typeKind(r.item_type)} /> },
    {
      key: "title", label: "제목",
      render: (r) => (r.url
        ? <a className="k-link" href={r.url} target="_blank" rel="noreferrer noopener">{r.title || "제목 없음"}</a>
        : <span>{r.title || "제목 없음"}</span>),
    },
    { key: "deleted_by", label: "삭제한 사람" },
    { key: "deleted_at", label: "삭제일", align: "right", render: (r) => fmtDateTime(r.deleted_at) },
    { key: "purge_after", label: "삭제 예정", align: "right", render: (r) => fmtDateTime(r.purge_after) },
    {
      key: "_actions", label: "", align: "right",
      render: (r) => (r.can_manage ? (
        <div className="k-row-actions">
          <Button size="sm" variant="primary" disabled={restore.isPending} onClick={() => restore.mutate(r.id)}>복원</Button>
          <Button size="sm" variant="danger" disabled={purge.isPending}
            onClick={async () => {
              const ok = await confirm("지금 영구 삭제하면 노션 원본이 보관처리되어 목록에서 사라집니다(노션 휴지통에서 30일 내 복구 가능). 계속할까요?",
                { title: "영구 삭제", confirmLabel: "영구 삭제", danger: true });
              if (ok) purge.mutate(r.id);
            }}>영구 삭제</Button>
        </div>
      ) : <span className="devrep-z">권한 없음</span>),
    },
  ];

  const headerActions = (
    <BulkActions count={sel.selected.size} onClear={sel.clear}>
      <Button size="sm" variant="primary" disabled={bulkRestore.isPending}
        onClick={() => bulkRestore.mutate([...sel.selected])}>선택 복원</Button>
      <Button size="sm" variant="danger" disabled={bulkPurge.isPending} onClick={purgeSelected}>선택 영구 삭제</Button>
    </BulkActions>
  );
  return (
    <div className="c-screen">
      <PageHeader crumbRoot="문서" area="휴지통" title="휴지통" actions={headerActions} />
      <p className="k-page-help">삭제한 티켓과 문서를 {days}일 동안 보관합니다. 그 전에 복원하면 원래 목록으로 돌아옵니다. 기간이 지나면 노션 원본이 자동으로 정리됩니다. 보관기간은 관리자 설정에서 바꿀 수 있습니다.</p>
      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : q.isPending ? <Card><Skeleton lines={5} /></Card>
        : (
          <Card>
            <DataTable columns={columns} rows={items} rowKey={(r) => r.id}
              empty="휴지통이 비어 있습니다." />
          </Card>
        )}
    </div>
  );
}
