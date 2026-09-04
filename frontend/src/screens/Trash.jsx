import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import Link from "@mui/material/Link";
import { Badge, Button, Card, DataTable, EmptyState, ErrorState, ListCard, MetricStrip, PageHeader, useConfirm, useToast } from "../ui/kit.jsx";
import { ListFooter } from "../ui/InfiniteScroll.jsx";
import { FilterRow, FilterSurface } from "../ui/FilterBar.jsx";
import { FilterSelect } from "../ui/filters.jsx";
import { bulkFailureNote, fmtDateTime, toUTCDate } from "../lib/format.js";
import { useRowSelection, selectionColumn, BulkActions } from "../ui/bulkSelect.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { invalidateDocumentViews } from "./document-views.js";
import { DateCell } from "../ui/cells.jsx";

/* 휴지통 — 삭제한 티켓/문서를 보관기간 동안 잡아둔다. 복원하면 원래 목록으로 돌아가고, 보관기간이
 * 지나면 백그라운드가 원본을 보관처리하고 여기서 사라진다. 지금 바로 영구 삭제도 가능(권한 필요).
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

/* 종류로 좁히는 조건. **서버가 좁힌다** — 화면에서만 거르면 상한 너머의 그 종류가 안
 * 보이면서 화면은 「이게 전부」라고 말한다. 문서 화면의 「휴지통」 버튼이 이 값을 걸고 연다
 * (`#/team-docs/trash?kind=document`). */
const KINDS = [
  { value: "ticket", label: "티켓" },
  { value: "document", label: "문서" },
];

/** 휴지통 줄이 **우리 문서**를 가리키면 그 id. 아니면 `null`.
 *
 * 서버가 `doc:<uuid>` 로 접두를 붙인다(`app/trash/router.py::DOC_PREFIX`). 옛 미러
 * 항목은 `source: "legacy"` 라 우리 쪽에 열 문서가 없다 — 접두만 보고 이으면 없는 화면으로
 * 보낸다. */
const DOC_PREFIX = "doc:";

function docIdOf(row) {
  if (!row || row.item_type !== "document" || row.source !== "knowledge") return null;
  const id = String(row.id || "");
  return id.startsWith(DOC_PREFIX) ? id.slice(DOC_PREFIX.length) : null;
}

export function Trash() {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [limit, setLimit] = useState(TRASH_PAGE_SIZE);
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") || "";
  const setKind = (next) => setParams(next ? { kind: next } : {});
  const q = useQuery({
    queryKey: ["trash", limit, kind],
    queryFn: () => api(`/api/trash?limit=${limit}${kind ? `&kind=${kind}` : ""}`),
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
    onError: (e) => toast((e && e.message) || "복원하지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  const bulkPurge = useMutation({
    mutationFn: (ids) => api("/api/trash/purge-bulk", { method: "POST", body: { ids } }),
    onSuccess: (res) => bulkMsg(res, "영구 삭제"),
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다. 다시 시도해 주세요.", "error"),
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
    onError: (e) => toast((e && e.message) || "복원하지 못했습니다. 다시 시도해 주세요.", "error"),
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
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const days = (q.data && q.data.retention_days) || 7;
  // 문서 정책은 티켓과 따로다(D-352) — 그쪽의 다음 단계는 「행을 지우는 것」이라 되돌릴 수
  // 없고, 그래서 끌 수 있다. 화면은 둘을 구별해서 말한다.
  const docAuto = !q.data || q.data.document_autopurge !== false;
  const docDays = (q.data && q.data.document_retention_days) || days;
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
    // 🔴 문구가 사실과 달랐다. 예전에는 영구 삭제가 노션 페이지를 보관처리하는 것이었고
    // 되돌릴 여지는 **노션 휴지통**이 줬다. 지금은 이 서버가 정본이라 행을 진짜로 지우고
    // (`repository_native.archive`) 딸린 댓글·첨부도 CASCADE 로 함께 사라진다. 되돌릴 수
    // 없는 동작을 「30일 내 복구 가능」이라고 말하면 사용자는 그것을 믿고 누른다.
    const ok = await confirm(`선택한 ${sel.selected.size}건을 영구 삭제합니다. 댓글과 첨부까지 함께 지워지고 되돌릴 수 없습니다. 계속할까요?`,
      { title: "선택 영구 삭제", confirmLabel: "영구 삭제", danger: true });
    if (ok) bulkPurge.mutate([...sel.selected]);
  };
  /* 열 너비는 열 정의가 든다(`type` + `ellipsis`) — 예전처럼 CSS nth-child로 잡으면
   * 선택 체크박스 열이 앞에 붙는 순간 한 칸씩 밀려 엉뚱한 열의 폭이 된다.
   * `fixed` 는 걷었다 — 그 배치에서는 `type` 이 주는 폭이 뜻을 잃는다(`kit.jsx::DataTable`). */
  const columns = [
    selCol,
    { key: "type_label", label: "종류", type: "status", minWidth: "7rem", render: (r) => <Badge value={r.type_label} kind={typeKind(r.item_type)} /> },
    {
      key: "title", label: "제목", type: "title",
      // rowName: 휴지통에서 행을 구별하는 값은 제목이다(ui/rowName.js). 여기가 영구 삭제를
      // 고르는 표라, 어느 줄을 고르는지 낭독되지 않으면 되돌릴 수 없는 실수가 난다.
      rowName: (r) => r.title || "제목 없음",
      /* 🔴 제목이 **우리 문서**로 가는 링크다.
       *
       * 예전에는 옛 Notion 주소로 나가는 링크였고, 정본이 이 서버로 넘어오면서 그 주소가
       * 여는 것이 낡은 사본이 되어 걷어냈다(서버도 응답에서 `url` 을 뺐다). 그런데
       * **대체를 안 놓았다.** 그래서 이 표에서 지우려는 것이 무엇인지 제목 말고는 볼
       * 방법이 없었다 — 영구 삭제는 되돌릴 수 없는데도 그렇다. 사용자가 물어서 드러났다.
       *
       * 서버는 이미 열어 준다: `get_scoped_document_or_404` 는 권한만 보고 `archived` 를
       * 안 막는다(운영의 휴지통 문서로 확인 — 본문 1,442자를 그대로 돌려준다). 막고 있던
       * 것은 화면뿐이었다.
       *
       * 새 탭으로 연다. 이 표는 고른 줄과 일괄 선택을 들고 있어서, 같은 탭에서 나갔다
       * 오면 그 선택이 사라진다.
       *
       * 옛 미러 항목(`source: "legacy"`)과 티켓은 그대로 평문이다 — 전자는 우리 쪽에
       * 열 문서가 없고, 후자는 이 회차의 물음이 아니다. 없는 링크를 만들지 않는다. */
      render: (r) => {
        const id = docIdOf(r);
        return id ? (
          <Link href={`#/knowledge/${id}`} target="_blank" rel="noreferrer">
            {r.title || "제목 없음"}
          </Link>
        ) : <span>{r.title || "제목 없음"}</span>;
      },
    },
    {
      /* 「어느 프로젝트의 문서였나」 (지시 22.7). 옛 미러 항목은 이 값을 모른다 — 그 개념이
         없는 표에서 왔다. 없는 값을 「-」로 지어내지 않고 자리를 비운다. */
      key: "place", label: "프로젝트", type: "name", minWidth: "10rem",
      /* 폴더 줄은 걷었다 — 폴더 축이 화면에서 사라져(문서 개편 1·5번) 복원한 뒤 그
         폴더를 볼 자리가 없다. 응답의 `folder` 는 그대로 온다. */
      render: (r) => (r.space ? <Typography variant="body2">{r.space}</Typography> : ""),
    },
    { key: "deleted_by", label: "삭제한 사람", type: "name", minWidth: "11rem" },
    { key: "deleted_at", label: "삭제일", type: "datetime", render: (r) => <DateCell value={r.deleted_at} /> },
    {
      /* 🔴 「삭제 예정」이 비어 있는 것과 「자동으로 안 지운다」는 다른 사실이다.
         문서 휴지통의 자동 영구 삭제는 끌 수 있고(설정 `document_trash_autopurge`), 꺼져
         있으면 서버가 이 값을 안 싣는다 — 그때 빈 칸을 두면 사람은 「곧 사라지는데 날짜만
         안 보인다」로 읽는다. */
      key: "purge_after", label: "삭제 예정", type: "datetime",
      render: (r) => (r.purge_after
        ? <DateCell value={r.purge_after} />
        : <Typography variant="body2" color="text.secondary">자동 삭제 안 함</Typography>),
    },
    {
      key: "_actions", label: "", type: "actions", minWidth: "14rem",
      render: (r) => (r.can_manage ? (
        <Stack direction="row" gap={1} justifyContent="flex-end">
          <Button size="sm" variant="primary" disabled={restore.isPending} onClick={() => restore.mutate(r)}>복원</Button>
          <Button size="sm" variant="danger" disabled={purge.isPending}
            onClick={async () => {
              const ok = await confirm("지금 영구 삭제하면 댓글과 첨부까지 함께 지워지고 되돌릴 수 없습니다. 계속할까요?",
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
      {/* PA-RC-0039: crumbRoot를 더 이상 손으로 고정하지 않는다 — AppShell의 CrumbRootProvider가
          지금 경로가 속한 navConfig 그룹에서 유도한다(부모 /team-docs와 항상 같은 값). 여기서
          "문서"를 계속 하드코딩하면 PA-RC-0031이 그 그룹 이름을 바꿀 때 부모만 따라가고 이
          자식은 옛 이름에 남아 갈라진다. */}
      <PageHeader
        area="휴지통" title="휴지통" actions={headerActions}
        description={
          docAuto
            ? `삭제한 티켓은 ${days}일, 문서는 ${docDays}일 동안 보관합니다. 그 전에 복원하면 원래 목록으로 돌아옵니다. 기간이 지나면 문서는 영구 삭제됩니다.`
            : `삭제한 티켓을 ${days}일 동안 보관합니다. 문서는 자동으로 지워지지 않으며, 영구 삭제는 사람이 누를 때만 실행됩니다.`
        }
      />

      {/* 좁히는 축은 하나다 — 종류. 「삭제한 사람」과 「공간」은 이 표에 조건으로 안 건다:
          휴지통은 대개 몇십 줄이고, 없는 서버 조건을 화면에서 흉내 내면 상한 너머가
          조용히 빠진다. */}
      <FilterSurface>
        <FilterRow>
          <FilterSelect
            label="종류"
            allLabel="전체"
            value={kind}
            onChange={setKind}
            options={KINDS}
          />
        </FilterRow>
      </FilterSurface>

      {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : q.isPending ? <Card>{/* 표가 들어올 자리에는 표 모양을 그린다 (지시 20) - 빈 목록과 아직 안 온 목록은 다른 사실이다. */}<DataTable columns={columns} rows={[]} loading /></Card>
        : items.length === 0 ? (
          /* 자산(empty-trash.png)이 처음부터 있었는데 어디에도 연결돼 있지 않았다. */
          <EmptyState
            layout="page"
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
            <MetricStrip
              ariaLabel="휴지통 요약"
              items={[
                {
                  key: "all", value: total || items.length, label: "보관 중", primary: true,
                  active: !kind, onClick: () => setKind(""),
                },
                {
                  key: "tickets", value: tickets, label: "티켓",
                  active: kind === "ticket", onClick: () => setKind("ticket"),
                },
                {
                  key: "docs", value: docs, label: "문서",
                  active: kind === "document", onClick: () => setKind("document"),
                },
                { key: "urgent", value: urgent, label: "24시간 내 영구 삭제", kind: urgent > 0 ? "warn" : undefined },
              ]}
              sx={{ mb: 2.5 }}
            />
            <ListCard>
              <DataTable columns={columns} rows={items} rowKey={(r) => r.id} ellipsis
                empty="휴지통이 비어 있습니다." />
              {/* 🔴 여기만 **자동 로딩을 안 켠다**(`autoMaxRows={0}`) — 문서화된 예외다.
                  `/api/trash` 는 티켓과 문서 **두 원천을 각각 상한으로 받아 합쳐** 정렬한다
                  (`app/trash/router.py`). offset 이 없고, 얹으면 두 원천 사이 경계에서 항목이
                  중복·누락된다. 그래서 이 화면은 「상한을 키워 처음부터 다시 받는」 관용을
                  **의도적으로** 유지하고(`Trash.jsx` 머리말), 굴릴 때마다 100→200→300 을 연달아
                  다시 받는 일이 없게 단추로만 받는다. 문구는 다른 목록과 같은 부품이 낸다. */}
              <ListFooter
                total={total} loaded={items.length}
                hasNext={hasMore} isFetchingNext={q.isFetching} onMore={loadMore}
                autoMaxRows={0}
                moreLabel="휴지통 더 보기"
              />
            </ListCard>
          </>
        )}
    </div>
  );
}
