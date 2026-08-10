import React, { useState } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import {
  PageHeader, Card, Badge, Button, DataTable, Modal, Skeleton,
  EmptyState, ErrorState, Callout, useConfirm, useToast,
} from "../ui/kit.jsx";
import { useRowSelection, selectionColumn } from "../ui/bulkSelect.jsx";
import { invalidateTicketViews } from "./ticket-views.js";

/* 온보딩 · 오프보딩 (PLAN Phase 6 — 관리자 백로그 최우선 항목)
 *
 * 계획서: *"퇴사자 보유 티켓 재배정 — ticket_cache+RBAC가 둘 다 필요한 유일한 항목이자 현재
 * 실제 운영 공백"*. 두 조각이 다 들어와 여기서 잇는다.
 *
 * **왜 DataScreen이 아닌가.** 이 화면은 목록이 아니라 마법사다: 사람을 고르고 → 그 사람이 든
 * 티켓을 **미리 보고** → 누구에게 옮길지 정한 뒤 → 실행하고 → 부분 실패를 확인한다. registry.js
 * 계약(엔드포인트 하나 + 열 + 액션)으로는 '미리 보여 주고 확인받는' 단계를 표현할 수 없다.
 * 대신 실행 이력은 같은 화면 아래에 표로 두고, 되돌리기를 그 자리에서 누를 수 있게 한다 —
 * 되돌릴 방법이 화면 안에 없으면 아무도 이 버튼을 못 쓴다.
 */

const STEP_HELP = [
  "1. 대상 고르기: 퇴사(또는 휴직)할 사람을 검색해 고릅니다.",
  "2. 미리 보기: 그 사람이 지금 담당 중인 티켓과 계정 상태를 확인합니다.",
  "3. 실행: 옮길 티켓과 후임을 정하고 실행합니다. 결과는 되돌릴 수 있습니다.",
];

/* `running` 은 **끝까지 가지 못한 실행**이다(C3). 실행은 요청 하나 안에서 끝나므로 목록에
   이 값이 보인다면 계정 처리 중에 무언가 터진 것이다 — 티켓은 이미 옮겨졌을 수 있으니
   "완료" 옆에 조용히 두면 안 된다. 라벨과 색이 둘 다 그 사실을 말해야 한다. */
const RUN_STATUS_KO = {
  running: "미완료", completed: "완료", partial: "부분 실패",
  undone: "되돌림", undo_partial: "되돌리기 부분 실패",
};
const MOVE_STATUS_KO = {
  // `pending` = 소스를 부르기 직전에 남긴 표시. 바뀌었는지 알 수 없는 유일한 상태다.
  pending: "확인 필요", moved: "옮김", skipped: "변경 없음", failed: "실패",
  reverted: "되돌림", revert_failed: "되돌리기 실패",
};
const MOVE_STATUS_KIND = {
  pending: "warn", moved: "ok", skipped: "neutral", failed: "danger",
  reverted: "ok", revert_failed: "danger",
};

export function Offboarding() {
  const [q, setQ] = useState("");
  const [targetId, setTargetId] = useState(null);
  const qc = useQueryClient();
  const toast = useToast();

  // 검색은 사용자 목록 API를 그대로 쓴다(관리 범위가 이미 걸려 있다 — 부서 관리자는 자기
  // 서브트리만 검색된다). 별도 '오프보딩 대상 목록' 엔드포인트를 새로 만들지 않는다.
  const searchQ = useQuery({
    queryKey: ["offboarding-search", q],
    queryFn: () => api("/api/admin/users?page_size=20" + (q ? "&q=" + encodeURIComponent(q) : "")),
    enabled: !targetId,
    retry: false,
  });
  const previewQ = useQuery({
    queryKey: ["offboarding-preview", targetId],
    queryFn: () => api("/api/admin/offboarding/preview/" + targetId),
    enabled: !!targetId,
    retry: false,
  });

  return (
    <div className="c-screen">
      <PageHeader area="사용자" title="온보딩, 오프보딩"
        actions={targetId ? <Button onClick={() => setTargetId(null)}>다른 사람 고르기</Button> : null} />
      <Callout>
        <Box component="p" sx={{ m: 0 }}>
          퇴사, 부서 이동 시 <strong>보유 티켓을 후임에게 옮기고</strong> 계정을 비활성화, 보관합니다.
          실행 전에 무엇이 바뀌는지 먼저 보여 주고, 실행한 뒤에도 <strong>되돌릴 수 있습니다</strong>.
        </Box>
        {STEP_HELP.map((line) => (
          <Box component="p" key={line} sx={{ m: 0, mt: 0.75 }}>{line}</Box>
        ))}
      </Callout>

      {!targetId ? (
        <TargetPicker q={q} setQ={setQ} query={searchQ} onPick={setTargetId} />
      ) : previewQ.isLoading ? (
        <Card><Skeleton lines={6} /></Card>
      ) : previewQ.isError ? (
        <ErrorState error={previewQ.error} onRetry={() => previewQ.refetch()} />
      ) : (
        <OffboardPlan
          preview={previewQ.data}
          onDone={() => {
            qc.invalidateQueries({ queryKey: ["offboarding-runs"] });
            qc.invalidateQueries({ queryKey: ["offboarding-preview", targetId] });
            qc.invalidateQueries({ queryKey: ["users"] });
            // 실행은 보유 티켓의 담당자를 후임(또는 미할당)으로 바꾼다 — 내 티켓·팀 티켓·
            // 스프린트·홈·월간 리포트가 이미 그 티켓을 캐시해 두고 있었다면(오프보딩 전에
            // 열어 본 탭 등) 이 화면만 새로고침되고 나머지는 옛 담당자를 그대로 보여준다.
            // 어떤 키가 티켓을 그리는지는 ticket-views.js 한 곳이 안다.
            invalidateTicketViews(qc, { refetchType: "all" });
          }}
          toast={toast}
        />
      )}

      <RunHistory />
    </div>
  );
}

/* 1단계 — 대상 고르기. */
function TargetPicker({ q, setQ, query, onPick }) {
  const items = (query.data && query.data.items) || [];
  const columns = [
    { key: "display_name", label: "이름" },
    { key: "email", label: "이메일" },
    { key: "department", label: "부서", render: (r) => r.department || "-" },
    { key: "title", label: "직책", render: (r) => r.title || "-" },
    { key: "active", label: "상태", render: (r) => (
      <Box sx={{ display: "inline-flex", gap: 0.75, flexWrap: "wrap" }}>
        <Badge value={r.active ? "active" : "disabled"} />
        {r.archived_at ? <Badge value="보관됨" kind="neutral" /> : null}
      </Box>
    ) },
    { key: "notion_mapping_status", label: "Notion 연결", render: (r) => <Badge value={r.notion_mapping_status} /> },
  ];
  return (
    <>
      <Card sx={{ p: 2, mb: 2.5 }}>
        <TextField
          type="search" size="small" fullWidth value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="이메일 또는 이름으로 검색"
          inputProps={{ "aria-label": "오프보딩 대상 검색" }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchRoundedIcon fontSize="small" /></InputAdornment> }}
        />
      </Card>
      {query.isLoading ? (
        <Card><Skeleton lines={5} /></Card>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState art="search" title="조건에 해당하는 사용자가 없습니다"
          help="검색어를 지우거나 다른 이름으로 찾아보세요." />
      ) : (
        <Card>
          <DataTable columns={columns} rows={items} rowKey={(r) => r.id} onRow={(r) => onPick(r.id)} />
        </Card>
      )}
    </>
  );
}

/* 2·3단계 — 미리 보기 + 실행. */
function OffboardPlan({ preview, onDone, toast }) {
  const user = preview.user;
  const tickets = preview.tickets || [];
  const selection = useRowSelection();
  const [successor, setSuccessor] = useState("");
  const [deactivate, setDeactivate] = useState(true);
  const [archive, setArchive] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const confirm = useConfirm();

  // 처음 열 때 모든 티켓을 선택해 둔다 — 전형적인 의도는 '전부 옮긴다'이고, 빼야 할 건만
  // 체크를 푸는 편이 하나씩 켜는 것보다 실수가 적다. 서버는 여전히 보낸 목록만 처리한다.
  const ids = tickets.map((t) => t.id);
  // 이 이펙트는 previewQ.data '객체' 자체가 아니라 그 안의 '티켓 id 집합'에만 반응해야 한다.
  // 예전엔 [preview]에 매여 있어, 티켓 집합은 그대로인데 다른 값(예: Notion에서 마감일만
  // 바뀜)이 달라진 새 응답이 배경 재조회(재연결 등, staleTime 경과 후)로 와도 매번 재실행돼
  // 사람이 방금 뺀 체크를 조용히 되살렸다 — 그 상태로 실행하면 일부러 제외한 티켓까지
  // 함께 옮겨진다. 실제로 티켓 구성이 달라졌을 때만(다른 사람으로 전환은 이 컴포넌트 자체가
  // 다시 마운트되므로 별도 처리가 필요 없다) 다시 전체 선택한다.
  const idsKey = ids.join(",");
  const prevIdsKeyRef = React.useRef(null);
  React.useEffect(() => {
    if (prevIdsKeyRef.current === idsKey) return;
    prevIdsKeyRef.current = idsKey;
    selection.setAll(ids, true);
  }, [idsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const chosen = ids.filter((id) => selection.selected.has(id));
  const columns = [
    selectionColumn(selection, ids),
    { key: "tid", label: "티켓", render: (t) => (t.tid != null ? "GIT-" + t.tid : "-") },
    { key: "title", label: "제목" },
    { key: "status", label: "상태", render: (t) => <Badge value={t.status} /> },
    { key: "due", label: "마감", render: (t) => t.due || "-" },
    { key: "assignee_names", label: "현재 담당자", render: (t) => (t.assignee_names || []).join(", ") || "-" },
  ];

  async function run() {
    const who = successor
      ? (preview.successor_candidates.find((c) => c.user_id === successor) || {}).display_name
      : null;
    const message = [
      `${user.display_name}(${user.email}) 오프보딩을 실행합니다.`,
      chosen.length
        ? `티켓 ${chosen.length}건을 ${who ? who + "에게 옮깁니다" : "미할당으로 되돌립니다"}.`
        : "옮길 티켓은 없습니다.",
      deactivate ? "계정을 비활성화합니다(로그인 불가)." : "",
      archive ? "계정을 보관합니다(목록에서 감춤)." : "",
      "실행 후 아래 ‘실행 이력’에서 되돌릴 수 있습니다.",
    ].filter(Boolean).join("\n");
    if (!(await confirm(message, { danger: true, title: "오프보딩 실행", confirmLabel: "실행" }))) return;

    setBusy(true);
    try {
      const res = await api("/api/admin/offboarding/run/" + user.id, {
        method: "POST",
        body: {
          ticket_page_ids: chosen,
          successor_user_id: successor || null,
          deactivate, archive, note: note || null,
        },
      });
      setResult(res);
      onDone();
      const run = res.run;
      // 부분 실패를 성공 토스트로 덮지 않는다 — 12건 중 3건이 실패했으면 그 숫자를 말한다.
      if (run.ticket_failed) toast(`티켓 ${run.ticket_moved}건을 옮기고 ${run.ticket_failed}건은 실패했습니다.`, "error");
      else toast("오프보딩을 실행했습니다.", "success");
    } catch (e) {
      if (e && e.status === 401) { toast("로그인이 필요합니다. 로그인 화면으로 이동합니다.", "error"); window.setTimeout(() => { window.location.href = "/login"; }, 1200); return; }
      toast(e.message, "error");
    } finally { setBusy(false); }
  }

  if (result) return <RunResult result={result} />;

  return (
    <>
      <Card sx={{ p: 2.5, mb: 2.5 }}>
        <Typography variant="h6" sx={{ mb: 1.5 }}>{user.display_name}, {user.email}</Typography>
        <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", xxl: "repeat(4, minmax(0,1fr))" } }}>
          {(preview.onboarding || []).map((check) => (
            <Box key={check.key} sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
              <Badge value={check.ok ? "완료" : "미완"} kind={check.ok ? "ok" : "warn"} />
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2">{check.label}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: "anywhere" }}>{check.value}</Typography>
              </Box>
            </Box>
          ))}
        </Box>
      </Card>

      {preview.open_run ? (
        <Box sx={{ mb: 2.5 }}>
          <Callout tone="warn">이 사람에 대해 아직 되돌리지 않은 오프보딩 실행이 있습니다({fmtDateTime(preview.open_run.created_at)}). 아래 ‘실행 이력’에서 먼저 확인하세요.</Callout>
        </Box>
      ) : null}
      {preview.tickets_error ? (
        <Box sx={{ mb: 2.5 }}>
          <Callout tone="warn">보유 티켓을 불러오지 못했습니다: {preview.tickets_error}: 이 상태로 실행하면 옮기지 못한 티켓이 그대로 남습니다.</Callout>
        </Box>
      ) : !preview.notion_mapped ? (
        <Box sx={{ mb: 2.5 }}>
          <Callout tone="warn">이 계정은 Notion 사용자와 연결되어 있지 않아 담당 티켓을 조회할 수 없습니다. 계정 처리만 진행할 수 있습니다.</Callout>
        </Box>
      ) : null}

      <Card sx={{ mb: 2.5 }}>
        <Box sx={{ p: 2, pb: 0 }}>
          <Typography variant="subtitle1">보유 티켓 {tickets.length}건, 선택 {chosen.length}건</Typography>
        </Box>
        {tickets.length ? (
          <DataTable columns={columns} rows={tickets} rowKey={(t) => t.id} />
        ) : (
          <Box sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary">옮길 티켓이 없습니다. 계정 처리만 진행합니다.</Typography>
          </Box>
        )}
      </Card>

      <Card sx={{ p: 2.5 }}>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0,1fr))" } }}>
          <TextField
            select size="small" label="후임(티켓을 받을 사람)" value={successor}
            SelectProps={{ displayEmpty: true }} InputLabelProps={{ shrink: true }}
            onChange={(e) => setSuccessor(e.target.value)}
            helperText="비워 두면 선택한 티켓이 미할당으로 돌아갑니다(미할당 트리아지에서 다시 배정)."
          >
            <MenuItem value="">(후임 없음. 미할당으로)</MenuItem>
            {(preview.successor_candidates || []).map((c) => (
              <MenuItem key={c.user_id} value={c.user_id}>
                {c.display_name}, {c.email}{c.department ? ", " + c.department : ""}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            size="small" label="메모(선택)" value={note} onChange={(e) => setNote(e.target.value)}
            helperText="왜 오프보딩하는지 남겨 두면 이력에서 바로 읽힙니다."
          />
        </Box>
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mt: 1.5 }}>
          <FormControlLabel control={<Checkbox size="small" checked={deactivate} onChange={(e) => setDeactivate(e.target.checked)} />}
            label={<Typography variant="body2">계정 비활성화(로그인 불가)</Typography>} />
          <FormControlLabel control={<Checkbox size="small" checked={archive} onChange={(e) => setArchive(e.target.checked)} />}
            label={<Typography variant="body2">계정 보관(목록에서 감춤)</Typography>} />
        </Box>
        <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 2 }}>
          <Button variant="danger" disabled={busy} onClick={run}>
            {busy ? "실행 중…" : "오프보딩 실행"}
          </Button>
        </Box>
      </Card>
    </>
  );
}

/* 실행 결과 — 부분 실패를 숨기지 않는다. */
function RunResult({ result }) {
  const run = result.run;
  const moves = result.moves || [];
  return (
    <Card sx={{ p: 2.5, mb: 2.5 }}>
      <Typography variant="h6" sx={{ mb: 1 }}>실행 결과</Typography>
      <Callout tone={run.ticket_failed ? "warn" : "info"}>
        티켓 {run.ticket_total}건 중 <strong>{run.ticket_moved}건 이동</strong>
        {run.ticket_failed ? <>, <strong>{run.ticket_failed}건 실패</strong></> : null}.
        {run.deactivated ? " 계정을 비활성화했습니다." : ""}
        {run.archived ? " 계정을 보관했습니다." : ""}
        {" "}아래 ‘실행 이력’에서 되돌릴 수 있습니다.
      </Callout>
      {moves.length ? (
        <Box sx={{ mt: 2 }}>
          <DataTable columns={MOVE_COLUMNS} rows={moves} rowKey={(m) => m.id} />
        </Box>
      ) : null}
    </Card>
  );
}

const MOVE_COLUMNS = [
  { key: "tid", label: "티켓", render: (m) => (m.tid != null ? "GIT-" + m.tid : m.ticket_page_id) },
  { key: "title", label: "제목", render: (m) => m.title || "-" },
  { key: "status", label: "결과", render: (m) => <Badge value={MOVE_STATUS_KO[m.status] || m.status} kind={MOVE_STATUS_KIND[m.status]} /> },
  { key: "error", label: "사유", render: (m) => m.error || "-" },
];

const RUN_PAGE_SIZE = 20;

/* 실행 이력 + 되돌리기. 되돌릴 방법이 화면 안에 없으면 아무도 실행 버튼을 못 쓴다.
 *
 * 페이지를 둔다 — 이 표는 감사 이력이라 지우지 않고 계속 쌓인다(휴지통처럼 보관기간이
 * 지나 스스로 줄지 않는다). 20건에서 자르고 다음 페이지로 갈 길을 안 주면, 21번째
 * 실행부터는 화면에서 조용히 사라져 아무도 다시 못 찾는다(내 활동 피드 Activity.jsx와
 * 같은 이유로 같은 방식을 쓴다). */
function RunHistory() {
  const [sel, setSel] = useState(null);
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const query = useQuery({
    queryKey: ["offboarding-runs", page],
    queryFn: () => api(`/api/admin/offboarding?page=${page}&page_size=${RUN_PAGE_SIZE}`),
    retry: false,
    // 페이지를 넘길 때 표가 통째로 Skeleton으로 사라졌다 나타나지 않게 한다.
    placeholderData: keepPreviousData,
  });
  const detailQ = useQuery({
    queryKey: ["offboarding-run", sel && sel.id],
    queryFn: () => api("/api/admin/offboarding/" + sel.id),
    enabled: !!sel,
    retry: false,
  });
  const items = (query.data && query.data.items) || [];
  const total = query.data && query.data.total;
  const totalPages = total != null ? Math.max(1, Math.ceil(total / RUN_PAGE_SIZE)) : null;

  async function undo(run) {
    const message = [
      `${run.user_name || "대상"} 의 오프보딩을 되돌립니다.`,
      run.ticket_moved ? `옮긴 티켓 ${run.ticket_moved}건을 원래 담당자에게 되돌립니다.` : "",
      run.deactivated ? "계정을 다시 활성화합니다." : "",
      run.archived ? "계정 보관을 해제합니다." : "",
    ].filter(Boolean).join("\n");
    if (!(await confirm(message, { title: "오프보딩 되돌리기", confirmLabel: "되돌리기" }))) return;
    setBusy(true);
    try {
      const res = await api("/api/admin/offboarding/" + run.id + "/undo", { method: "POST", body: {} });
      qc.invalidateQueries({ queryKey: ["offboarding-runs"] });
      qc.invalidateQueries({ queryKey: ["offboarding-run", run.id] });
      qc.invalidateQueries({ queryKey: ["users"] });
      // 되돌리기도 티켓 담당자를 다시 바꾼다(후임 → 원래 담당자) — 실행과 같은 이유로
      // 티켓을 그리는 화면 전부를 함께 무효화한다.
      invalidateTicketViews(qc, { refetchType: "all" });
      if (res.revert_failed) toast(`${res.revert_failed}건을 되돌리지 못했습니다. 상세에서 사유를 확인하세요.`, "error");
      else toast("되돌렸습니다.", "success");
      setSel(null);
    } catch (e) { toast(e.message, "error"); }
    finally { setBusy(false); }
  }

  const columns = [
    { key: "created_at", label: "실행", render: (r) => fmtDateTime(r.created_at) },
    // 서버가 이름을 못 주면(탈퇴 계정 등) raw UUID 대신 '알 수 없음'을 보여준다(E-4 UUID 노출).
    { key: "user_name", label: "대상", render: (r) => r.user_name || "알 수 없음" },
    { key: "successor_name", label: "후임", render: (r) => r.successor_name || "(없음)" },
    { key: "status", label: "상태", render: (r) => (
      <Badge value={RUN_STATUS_KO[r.status] || r.status}
        kind={r.status === "completed" ? "ok" : r.status === "undone" ? "neutral" : "warn"} />
    ) },
    { key: "ticket_moved", label: "티켓", render: (r) => `${r.ticket_moved}/${r.ticket_total}` + (r.ticket_failed ? ` (실패 ${r.ticket_failed})` : "") },
    { key: "actor_name", label: "실행자", render: (r) => r.actor_name || "-" },
  ];

  const detail = (detailQ.data && detailQ.data.run) || sel;

  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="h6" sx={{ mb: 1.5 }}>실행 이력</Typography>
      {query.isLoading ? (
        <Card><Skeleton lines={3} /></Card>
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : items.length === 0 && page === 1 ? (
        <EmptyState title="아직 실행한 오프보딩이 없습니다"
          help="위에서 대상을 고르고 실행하면 여기에 기록이 남고, 그 자리에서 되돌릴 수 있습니다." />
      ) : (
        <Card>
          <DataTable columns={columns} rows={items} rowKey={(r) => r.id} onRow={setSel} />
          {/* 감사 이력은 지워지지 않고 계속 쌓인다 — 20건을 넘으면 다음 페이지로 갈 길을
              준다(Activity.jsx와 같은 이유, 같은 방식). */}
          <Box
            component="nav"
            aria-label="페이지 이동"
            sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 2, p: 2, borderTop: 1, borderColor: "divider" }}
          >
            <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>이전</Button>
            <Typography variant="body2" color="text.secondary" aria-live="polite" sx={{ minWidth: "8rem", textAlign: "center" }}>
              {totalPages != null ? `${page} / ${totalPages}, 총 ${total}건` : `${page}페이지`}
            </Typography>
            <Button
              size="sm"
              disabled={totalPages != null ? page >= totalPages : items.length < RUN_PAGE_SIZE}
              onClick={() => setPage((p) => p + 1)}
            >
              다음
            </Button>
          </Box>
        </Card>
      )}

      <Modal open={!!sel} onClose={() => setSel(null)} size="lg"
        title={sel ? (sel.user_name || "오프보딩") + " 실행 상세" : ""}
        footer={sel ? (
          <Box className="k-footer-row" sx={{ px: 3, py: 2 }}>
            <Box className="k-footer-main">
              {!sel.undone_at ? (
                <Button variant="primary" disabled={busy} onClick={() => undo(sel)}>
                  {busy ? "되돌리는 중…" : "되돌리기"}
                </Button>
              ) : null}
              {/* offboarding_run은 감사 로그의 유효한 object_type이고(app/offboarding/router.py)
                  이제 OBJ_ROUTE에도 있다 — 이 화면은 admin/system_admin 전용(navConfig.js
                  SCREEN_ROLES.offboarding)이라 audit 접근 역할의 부분집합이라 별도 role 게이트가
                  필요 없다(MEGA CYCLE G). */}
              <Button href={"#/audit?object_type=offboarding_run&object_id=" + sel.id}>
                감사 로그에서 보기
              </Button>
            </Box>
          </Box>
        ) : null}>
        {detail ? (
          <>
            <Box sx={{ display: "grid", columnGap: 4, gridTemplateColumns: { xs: "1fr", xxl: "repeat(2, minmax(0,1fr))" } }}>
              {/* 이름이 없으면(탈퇴 계정 등) raw UUID 대신 '알 수 없음'을 보여준다(E-4 UUID 노출) */}
              <Row label="대상">{detail.user_name || "알 수 없음"}</Row>
              <Row label="후임">{detail.successor_name || "(없음. 미할당으로 되돌림)"}</Row>
              <Row label="실행자">{detail.actor_name || "알 수 없음"}</Row>
              <Row label="상태">{RUN_STATUS_KO[detail.status] || detail.status}</Row>
              <Row label="티켓">{`${detail.ticket_moved}/${detail.ticket_total}건 이동, 실패 ${detail.ticket_failed}건`}</Row>
              <Row label="계정 변경">{[detail.deactivated ? "비활성화" : null, detail.archived ? "보관" : null].filter(Boolean).join(", ") || "없음"}</Row>
              <Row label="메모">{detail.note || "-"}</Row>
              <Row label="되돌린 시각">{detail.undone_at ? fmtDateTime(detail.undone_at) : "-"}</Row>
            </Box>
            {detail.undo_error ? <Box sx={{ mt: 2 }}><Callout tone="warn">{detail.undo_error}</Callout></Box> : null}
            {(detail.moves || []).length ? (
              <Box sx={{ mt: 2 }}>
                <DataTable columns={MOVE_COLUMNS} rows={detail.moves} rowKey={(m) => m.id} />
              </Box>
            ) : null}
          </>
        ) : null}
      </Modal>
    </Box>
  );
}

function Row({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "10rem minmax(0,1fr)" }, gap: 1,
               py: 1.25, borderBottom: 1, borderColor: "divider", minWidth: 0 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Box sx={{ minWidth: 0, overflowWrap: "anywhere" }}>{children}</Box>
    </Box>
  );
}

export default Offboarding;
