import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Badge, Button, Card, DataTable, EmptyState, ErrorState, PageHeader, Skeleton, StatCard, useConfirm, useToast } from "../ui/kit.jsx";
import { bulkFailureNote, fmtDateTime, toUTCDate } from "../lib/format.js";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { useRowSelection, selectionColumn, BulkActions } from "../ui/bulkSelect.jsx";
import { safeExternal } from "../lib/safeUrl.js";
import { invalidateTicketViews } from "./ticket-views.js";
import { invalidateDocumentViews } from "./document-views.js";

/* 휴지통 — 삭제한 티켓/문서를 보관기간 동안 잡아둔다. 복원하면 원래 목록으로 돌아가고, 보관기간이
 * 지나면 백그라운드가 노션 원본을 보관처리하고 여기서 사라진다. 지금 바로 영구 삭제도 가능(권한 필요).
 * 문서 하위 페이지. 종류(티켓/문서)·제목·삭제한 사람·삭제일·삭제 예정일이 보인다.
 *
 * 2026-08 MUI 재설계: 화면 고유 CSS 클래스(.k-row-actions 등)에 기대지 않고 sx로 직접 그린다 —
 * 그 클래스들은 kit.css가 걷히면서 이미 규칙이 사라져 버튼이 서로 붙어 있었다. 열 너비도
 * screens.css의 nth-child가 아니라 열 정의(width)에 함께 적는다(열을 옮기면 폭도 따라간다). */

function typeKind(t) { return t === "ticket" ? "info" : "purple"; }

const DAY_MS = 24 * 60 * 60 * 1000;
// UA-10 확증 — 예전엔 상한도 total도 없어 "더 보기" 자체가 불가능했다. useChat.js의 대화
// 목록(AI-18)과 같은 값·같은 관용(더 보기는 상한을 늘려 처음부터 다시 받는다 — 그 사이 항목이
// 복원/영구삭제돼도 오프셋 이어붙이기처럼 중복·누락이 안 생긴다).
const TRASH_PAGE_SIZE = 100;

/* 24시간 안에 영구 삭제될 항목 수 — '보관기간이 지나면 사라진다'는 설명만으로는 언제가 그 순간인지
 * 알 수 없어서, 지금 손을 써야 하는 건수를 숫자로 앞에 내놓는다. */
export function urgentCount(items, nowMs) {
  const now = nowMs == null ? Date.now() : nowMs;
  return (items || []).filter((r) => {
    const d = toUTCDate(r && r.purge_after);
    return d != null && d.getTime() - now <= DAY_MS;
  }).length;
}

export function Trash() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [limit, setLimit] = useState(TRASH_PAGE_SIZE);
  const q = useQuery({
    queryKey: ["trash", limit],
    queryFn: () => api("/api/trash?limit=" + limit),
    refetchInterval: 15000,
    // AI-18과 같은 이유 — "더 보기"가 상한을 늘려 새 쿼리 키로 다시 받는 동안 이전 목록을
    // 그대로 보여준다(없으면 15초 폴링과 무관하게 매번 스켈레톤이 깜빡인다).
    placeholderData: keepPreviousData,
  });
  const sel = useRowSelection();

  const bulkMsg = (res, verb) => {
    const changed = (res.restored || res.purged) || [];
    const n = changed.length;
    const failed = res.failed || [];
    // UA-25 — 실패 사유를 "권한이 없어"로 뭉개지 않는다. 실제로는 이미 처리됨·권한·Notion
    // 보관 실패 3종이 섞일 수 있고, Notion 장애일 때 이 문구 때문에 관리자가 다른 계정으로
    // 헛되이 재시도했다.
    toast(`${n}건을 ${verb}했습니다.` + bulkFailureNote(failed), failed.length ? "info" : "success");
    qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
    // 복원한 티켓은 홈·스프린트에도 다시 나타나야 한다 — 그 키 목록은 ticket-views.js 가 안다.
    invalidateTicketViews(qc, { refetchType: "all" });
    // 문서 쪽도 마찬가지 — document-views.js의 ["team-doc"] 접두어(id 없이)가 상세 캐시
    // 전부를 한 번에 잡는다(예전엔 FN-14 수정 때 notion_page_id별로 손으로 순회했다).
    invalidateDocumentViews(qc, { refetchType: "all" });
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

  // FN-14 — id가 아니라 행 전체(row)를 넘긴다(mutationFn이 row.id를 쓴다). onSuccess는 더는
  // row 데이터가 필요 없다 — document-views.js의 ["team-doc"] 접두어(id 없이)가 상세 캐시
  // 전부를 한 번에 잡는다(예전엔 notion_page_id별로 손으로 순회했다).
  const restore = useMutation({
    mutationFn: (row) => api("/api/trash/" + row.id + "/restore", { method: "POST" }),
    onSuccess: () => {
      toast("복원했습니다. 원래 목록에서 다시 볼 수 있습니다.", "success");
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      invalidateTicketViews(qc, { refetchType: "all" });
      invalidateDocumentViews(qc, { refetchType: "all" });
    },
    onError: (e) => toast((e && e.message) || "복원하지 못했습니다.", "error"),
  });
  const purge = useMutation({
    mutationFn: (row) => api("/api/trash/" + row.id + "/purge", { method: "POST" }),
    onSuccess: () => {
      toast("영구 삭제했습니다. 원본이 보관처리됐습니다.", "success");
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      // restore와 대칭을 맞춘다 — 예전엔 purge만 이 둘이 빠져 있어 티켓/문서 목록이 영구
      // 삭제 뒤에도 최대 staleTime 동안 그 항목을 계속 보여줄 수 있었다(FN-14와 같은 자리에서
      // 함께 고친다).
      invalidateTicketViews(qc, { refetchType: "all" });
      invalidateDocumentViews(qc, { refetchType: "all" });
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
  });

  const days = (q.data && q.data.retention_days) || 7;
  const items = (q.data && q.data.items) || [];
  // UA-10 확증 — total이 지금 받은 개수보다 크면 상한(TRASH_PAGE_SIZE) 너머에 더 있다는 뜻.
  const total = (q.data && q.data.total) || 0;
  const hasMore = items.length < total;
  const loadMore = () => setLimit((n) => n + TRASH_PAGE_SIZE);
  const manageable = new Set(items.filter((i) => i.can_manage).map((i) => i.id));
  // 선택 열에도 폭을 준다 — table-layout:fixed에서 폭 없는 열은 남는 공간을 균등 분배받아,
  // 체크박스 한 칸이 제목과 같은 폭을 먹고 제목이 곧바로 잘렸다.
  const selCol = { ...selectionColumn(sel, items.map((i) => i.id), { eligible: (id) => manageable.has(id) }), width: "3.5rem" };
  const purgeSelected = async () => {
    const ok = await confirm(`선택한 ${sel.selected.size}건을 영구 삭제합니다. 노션 원본이 보관처리되어 목록에서 사라집니다(노션 휴지통에서 30일 내 복구 가능). 계속할까요?`,
      { title: "선택 영구 삭제", confirmLabel: "영구 삭제", danger: true });
    if (ok) bulkPurge.mutate([...sel.selected]);
  };
  /* 열 너비는 열 정의에 함께 적는다(fixed + ellipsis) — 예전처럼 CSS nth-child로 잡으면
   * 선택 체크박스 열이 앞에 붙는 순간 한 칸씩 밀려 엉뚱한 열의 폭이 된다. */
  const columns = [
    selCol,
    { key: "type_label", label: "종류", width: "7rem", render: (r) => <Badge value={r.type_label} kind={typeKind(r.item_type)} /> },
    {
      key: "title", label: "제목",
      // rowName: 휴지통에서 행을 구별하는 값은 제목이다(ui/rowName.js). 여기가 영구 삭제를
      // 고르는 표라, 어느 줄을 고르는지 낭독되지 않으면 되돌릴 수 없는 실수가 난다.
      rowName: (r) => r.title || "제목 없음",
      render: (r) => (safeExternal(r.url)
        ? <Link href={safeExternal(r.url)} target="_blank" rel="noreferrer noopener" underline="hover">{r.title || "제목 없음"}</Link>
        : <span>{r.title || "제목 없음"}</span>),
    },
    { key: "deleted_by", label: "삭제한 사람", width: "11rem" },
    { key: "deleted_at", label: "삭제일", align: "right", width: "12rem", render: (r) => fmtDateTime(r.deleted_at) },
    { key: "purge_after", label: "삭제 예정", align: "right", width: "12rem", render: (r) => fmtDateTime(r.purge_after) },
    {
      key: "_actions", label: "", align: "right", width: "14rem",
      render: (r) => (r.can_manage ? (
        <Stack direction="row" gap={1} justifyContent="flex-end">
          <Button size="sm" variant="primary" disabled={restore.isPending} onClick={() => restore.mutate(r)}>복원</Button>
          <Button size="sm" variant="danger" disabled={purge.isPending}
            onClick={async () => {
              const ok = await confirm("지금 영구 삭제하면 노션 원본이 보관처리되어 목록에서 사라집니다(노션 휴지통에서 30일 내 복구 가능). 계속할까요?",
                { title: "영구 삭제", confirmLabel: "영구 삭제", danger: true });
              if (ok) purge.mutate(r);
            }}>영구 삭제</Button>
        </Stack>
      ) : <Typography variant="body2" color="text.secondary">권한 없음</Typography>),
    },
  ];

  const headerActions = (
    <BulkActions count={sel.selected.size} onClear={sel.clear}>
      <Button size="sm" variant="primary" disabled={bulkRestore.isPending}
        onClick={() => bulkRestore.mutate([...sel.selected])}>선택 복원</Button>
      <Button size="sm" variant="danger" disabled={bulkPurge.isPending} onClick={purgeSelected}>선택 영구 삭제</Button>
    </BulkActions>
  );

  const tickets = items.filter((r) => r.item_type === "ticket").length;
  const docs = items.length - tickets;
  const urgent = urgentCount(items);

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="문서" area="휴지통" title="휴지통" actions={headerActions} />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: PROSE_MAX_WIDTH }}>
        삭제한 티켓과 문서를 {days}일 동안 보관합니다. 그 전에 복원하면 원래 목록으로 돌아옵니다. 기간이 지나면 노션 원본이 자동으로 정리됩니다. 보관기간은 관리자 설정에서 바꿀 수 있습니다.
      </Typography>

      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : q.isPending ? <Card><Skeleton lines={5} /></Card>
        : items.length === 0 ? (
          /* 자산(empty-trash.png)이 처음부터 있었는데 어디에도 연결돼 있지 않았다. */
          <EmptyState
            art="trash"
            title="휴지통이 비어 있습니다"
            // WF1 R5 — 예전엔 여기서 "{days}일 동안 여기 보관됩니다"를 또 말했다, 바로 위
            // 상시 안내문(항상 보임, 빈 상태여도 사라지지 않는다)이 이미 같은 사실을 말한다.
            help="아직 지운 티켓이나 문서가 없습니다. 실수로 지웠다면 이 화면에서 되돌릴 수 있습니다."
          />
        ) : (
          <>
            {/* 요약 줄 — '보관기간이 지나면 사라진다'만으로는 언제가 그 순간인지 알 수 없다.
             * 24시간 안에 사라질 건수를 숫자로 먼저 보여준다(0이면 톤 없이 중립). */}
            <Box sx={{
              display: "grid", gap: 2, mb: 2.5,
              gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", lg: "repeat(4, minmax(0,1fr))" },
            }}>
              <StatCard value={items.length} label="보관 중" />
              <StatCard value={tickets} label="티켓" />
              <StatCard value={docs} label="문서" />
              <StatCard value={urgent} label="24시간 내 영구 삭제" kind={urgent > 0 ? "warn" : undefined} />
            </Box>
            <Card className="c-list-card">
              <DataTable columns={columns} rows={items} rowKey={(r) => r.id} fixed ellipsis
                empty="휴지통이 비어 있습니다." />
              {/* UA-10 확증 — 상한(기본 100개)보다 많을 때만 보인다. 대부분은 그 이하라 아무것도
                  안 보이던 예전 그대로다(ConversationSidebar의 "대화 더 보기"와 같은 관용). */}
              {hasMore ? (
                <Box sx={{ display: "flex", justifyContent: "center", pt: 2 }}>
                  <Button size="sm" variant="ghost" disabled={q.isFetching} onClick={loadMore}>
                    {q.isFetching ? "불러오는 중…" : "휴지통 더 보기"}
                  </Button>
                </Box>
              ) : null}
            </Card>
          </>
        )}
    </div>
  );
}
