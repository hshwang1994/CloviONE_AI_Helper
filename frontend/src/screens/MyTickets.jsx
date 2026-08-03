import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { alpha } from "@mui/material/styles";
import { api } from "../lib/api.js";
import { Card, Badge, DataTable, EmptyState, ErrorState, Skeleton, Callout, StatCard, PageHeader, Modal, ModalFooter, Button, useToast } from "../ui/kit.jsx";
import { priorityKo, priorityKind } from "../lib/priority.js";
import { useAuth } from "../app/auth.jsx";
import { BodyEditor } from "../ui/BodyEditor.jsx";
import { useRowSelection, selectionColumn, BulkActions } from "../ui/bulkSelect.jsx";
import { TeamChatWidget } from "./TeamChatWidget.jsx";

// 일괄 삭제(휴지통) 뮤테이션 — page_ids 를 보내고, 결과(N건 삭제/M건 실패)를 토스트로 알린다.
function useBulkTrash(path, qc, toast, onDone) {
  return useMutation({
    mutationFn: (ids) => api(path, { method: "POST", body: { page_ids: ids } }),
    onSuccess: (res) => {
      const n = (res.trashed || []).length;
      const f = (res.failed || []).length;
      toast(f ? `${n}건을 휴지통으로 옮겼습니다. ${f}건은 권한이 없어 건너뛰었습니다.` : `${n}건을 휴지통으로 옮겼습니다.`, f ? "info" : "success");
      // refetchType:"all" — 지금 화면에 없는(비활성) 목록까지 즉시 다시 불러와, 삭제 후 어느 페이지로
      // 가도 최신으로 보이게 한다(이전엔 비활성 목록이 stale로만 남아 '자동 갱신 안 됨'처럼 보였다).
      qc.invalidateQueries({ queryKey: ["tickets"], refetchType: "all" });
      qc.invalidateQueries({ queryKey: ["team-docs"], refetchType: "all" });
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      onDone && onDone();
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
  });
}

/* 사용자 셀프서비스 — 내 업무(홈)·내 티켓·미할당 티켓.
 * 데이터는 /api/tickets/*(백엔드가 세션 사용자 기준으로 본인 것만 준다 — 브라우저는 notion id를
 * 주지 않는다). 편집은 도우미를 통해 수동으로 한다(Notion 직접 진입 없이) — 담당자 배정·예상 WD·
 * 난이도·우선순위·진행상태·마감 수정. 소유권/스키마 검증은 서버가 판단한다. 상태 색은 kit Badge.
 *
 * 2026-08 MUI 재설계: 표·툴바·폼을 MUI로 옮겼다. 예전에는 screens.css/kit.css의 px 값(.k-table
 * font-size:14px 등)에 묶여 있어 4K에서 글자만 그대로 남고 여백만 커졌다 — 이제 전부 rem/테마
 * 값이라 styles/root.css의 루트 폰트사이즈 레버 하나로 같이 커진다. px 폰트사이즈는 새로 쓰지 않는다. */

const TERMINAL = new Set(["완료", "취소"]);

function ticketId(t) { return t.tid != null ? "GIT-" + t.tid : "-"; }

// 행/‘상세’ 클릭 → 우리 화면의 티켓 상세로 간다(문서처럼). 원본(노션)은 상세에서 '원본 열기'로.
function ticketPath(t) { return "/tickets/" + (t && t.id); }

function todayISO() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function addDaysISO(iso, days) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function isActive(t) { return !TERMINAL.has(t.status || ""); }
function isOverdue(t, today) { return isActive(t) && t.due && t.due < today; }

function TitleCell({ t, onOpen }) {
  // 제목(이름)을 눌러야 상세로 간다 — 행 전체 클릭은 없앤다(체크박스 오클릭으로 상세 이동하던 불편 제거).
  // t.id가 없으면 링크로 만들지 않는다 — 스프린트 화면의 담당자별 목록은 서버가 아직 앱 티켓 id를
  // 주지 않는 행(reports의 _ticket_detail)을 섞어 받을 수 있는데, 그걸 링크로 그리면 '/tickets/undefined'
  // 라는 없는 경로로 보내게 된다(눌리는데 아무 데도 못 가는 링크보다 링크가 없는 편이 정직하다).
  // 링크는 강조색으로 그린다. 예전(.k-title-link)은 color:inherit + hover 밑줄이라 마우스를 올리기
  // 전까지 본문 텍스트와 구분되지 않았고, 스프린트 화면처럼 '링크인 제목'과 '링크 아닌 제목'이 한
  // 표에 섞이면 어느 쪽을 눌러야 하는지 알 방법이 아예 없다.
  if (onOpen && t.id) {
    return (
      <Link
        component="button"
        type="button"
        underline="hover"
        onClick={() => onOpen(t)}
        sx={{ font: "inherit", fontWeight: 650, textAlign: "left", color: "primary.main" }}
      >
        {t.title || "제목 없음"}
      </Link>
    );
  }
  return <Box component="span" sx={{ fontWeight: 620 }}>{t.title || "제목 없음"}</Box>;
}

// 목록 표 — 티켓/제목/상태/우선순위/난이도/예상WD/마감. 숫자·날짜는 우측 정렬.
// onEdit/onClaim 을 주면 우측에 액션 열(편집·나에게 배정)이 붙는다. onOpen 을 주면 제목이 상세 링크.
// width는 rem이다 — 4K에서 루트 폰트사이즈가 커지면 열 폭도 같이 커져야 글자와 비율이 맞는다.
export function ticketColumns({ showAssignee, onEdit, onClaim, onOpen } = {}) {
  const cols = [
    { key: "tid", label: "티켓", width: "7rem", render: (t) => ticketId(t) },
    { key: "title", label: "제목", render: (t) => <TitleCell t={t} onOpen={onOpen} /> },
    { key: "status", label: "상태", width: "7rem", render: (t) => (t.status ? <Badge value={t.status} /> : "-") },
    { key: "priority", label: "우선순위", width: "7rem", render: (t) => (t.priority ? <Badge value={priorityKo(t.priority)} kind={priorityKind(t.priority)} /> : "-") },
    { key: "difficulty", label: "난이도", align: "right", width: "5.5rem", render: (t) => (t.difficulty || "-") },
    { key: "est_wd", label: "예상 WD", align: "right", width: "6rem", render: (t) => (t.est_wd != null ? t.est_wd : "-") },
    { key: "due", label: "마감", align: "right", width: "7rem", render: (t) => (t.due || "-") },
  ];
  if (showAssignee) {
    cols.push({ key: "assignee_names", label: "담당자", width: "10rem", render: (t) => ((t.assignee_names || []).join(", ") || "-") });
  }
  if (onEdit || onClaim) {
    cols.push({
      key: "_actions", label: "", align: "right", width: onClaim ? "13rem" : "6rem",
      render: (t) => (
        <Stack direction="row" gap={1} justifyContent="flex-end" sx={{ flexWrap: "nowrap" }}>
          {onClaim ? <Button size="sm" variant="primary" onClick={() => onClaim(t)}>나에게 배정</Button> : null}
          {onEdit ? <Button size="sm" onClick={() => onEdit(t)}>편집</Button> : null}
        </Stack>
      ),
    });
  }
  return cols;
}

/* 편집 드롭다운 옵션 — 현재 값이 목록에 없으면(메타 미로딩·옵션 rename) 맨 앞에 끼워 넣어
 * '현재 값이 화면에서 사라지는' 문제를 막는다(kit FormField selNeedEmpty 와 같은 취지). */
function withCurrent(list, cur) {
  const opts = Array.isArray(list) ? list : [];
  if (cur && !opts.includes(cur)) return [cur, ...opts];
  return opts;
}
function sameSet(a, b) {
  return [...(a || [])].sort().join(",") === [...(b || [])].sort().join(",");
}

// 티켓을 프로젝트별로 묶는다(대표 프로젝트명 기준). 이름 없는 티켓은 '프로젝트 없음'으로 맨 뒤에.
function groupByProject(rows) {
  const map = new Map();
  for (const t of rows) {
    const key = t.project || "프로젝트 없음";
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(t);
  }
  return [...map.entries()].sort((a, b) => {
    if (a[0] === "프로젝트 없음") return 1;
    if (b[0] === "프로젝트 없음") return -1;
    return a[0].localeCompare(b[0]);
  });
}

/* 빈 값('' = 전체/없음)을 고를 수 있는 select에 반드시 함께 넘긴다.
 * MUI Select는 값이 ''이면 '아직 아무것도 안 골랐다'로 보고 라벨을 축소하지 않은 채 입력 자리에
 * 그대로 둔다 — 그러면 고른 값('전체'/'없음')이 화면에서 사라지고 상자가 빈 것처럼 보인다.
 * displayEmpty로 빈 값의 항목 라벨을 그리게 하고, 라벨은 항상 노치로 올린다. */
export const EMPTYABLE_SELECT = { SelectProps: { displayEmpty: true }, InputLabelProps: { shrink: true } };

// 좁은 화면(≤760px)에서 표를 카드 목록으로 바꾸는 기준 — kit.jsx의 DataTable과 같은 값을 쓴다.
// 두 표가 같은 폭에서 같이 전환되지 않으면 한 화면 안에서 표와 카드가 섞여 보인다.
const TABLE_CARD_BREAKPOINT = "(max-width:760px)";

function groupedCell(c, t) {
  if (c.render) return c.render(t);
  const v = t[c.key];
  return v == null || v === "" ? "-" : String(v);
}
// 그룹 안에서 같은 티켓이 여러 그룹에 들어갈 수 있어(담당자 다중 배정) 그룹별로만 유일하면 된다.
// 앱 id가 없는 행(스프린트 담당자별 파생 rows)도 안전하게 키를 얻도록 tid·인덱스로 폴백한다.
function groupedRowKey(t, i) {
  if (t && t.id != null) return String(t.id);
  if (t && t.tid != null) return "tid-" + t.tid;
  return "i-" + i;
}

/* 그룹 기준으로 묶어 '하나의 표'로 그린다(그룹마다 별도 table을 쓰면 열 너비가 어긋남). 기본은
 * 프로젝트별, groupBy 를 주면 담당자별 등 다른 기준으로. 행 전체는 클릭 대상이 아니다 — 제목만 상세로.
 *
 * MUI Table로 옮겼지만 그룹 머리행은 <tbody>를 그룹마다 하나씩 두는 기존 구조를 그대로 유지한다 —
 * colgroup 스코프 헤더라 스크린리더가 "이 아래 행들은 이 그룹" 이라고 읽을 수 있고, 열 폭은 하나의
 * <table>이 공유하므로 그룹 간에 어긋나지 않는다. */
export function GroupedTickets({ rows, columns, empty, groupBy }) {
  const cols = Array.isArray(columns) ? columns : [];
  const safeRows = Array.isArray(rows) ? rows : [];
  const grouper = groupBy || groupByProject;
  const narrow = useMediaQuery(TABLE_CARD_BREAKPOINT);

  if (!safeRows.length) {
    return (
      <Typography color="text.secondary" sx={{ py: 5, textAlign: "center" }}>
        {empty || "표시할 항목이 없습니다."}
      </Typography>
    );
  }

  const groups = grouper(safeRows);
  const groupHeading = (name, count) => (
    <>
      <Box component="span" sx={{ fontWeight: 750 }}>{name}</Box>
      <Box component="span" sx={{ ml: 1, color: "text.secondary", fontWeight: 500, fontSize: "0.8125rem" }}>{count}건</Box>
    </>
  );

  /* 좁은 화면에서는 가로 스크롤 표 대신 카드 목록으로 바꾼다 — 열 이름이 화면 밖으로 나가면
   * 어떤 값인지 알 수 없다. 카드에서는 라벨을 값 옆에 붙인다(kit DataTable과 같은 규칙). */
  if (narrow) {
    return (
      <Stack gap={2.5}>
        {groups.map(([groupName, items]) => (
          <Box key={groupName}>
            <Typography component="h3" sx={{ fontSize: "0.9375rem", mb: 1 }}>{groupHeading(groupName, items.length)}</Typography>
            <Stack gap={1.5}>
              {items.map((t, i) => (
                <Paper key={groupedRowKey(t, i)} variant="outlined" sx={{ p: 2, display: "grid", gap: 0.75 }}>
                  {cols.map((c) => c.label ? (
                    <Box key={c.key} sx={{ display: "grid", gridTemplateColumns: "7rem minmax(0,1fr)", gap: 1, alignItems: "start" }}>
                      <Typography variant="caption" color="text.secondary">{c.label}</Typography>
                      <Box sx={{ minWidth: 0, fontSize: "0.875rem", overflowWrap: "anywhere" }}>{groupedCell(c, t)}</Box>
                    </Box>
                  ) : (
                    // 라벨이 없는 열(선택 체크박스·행 작업)은 라벨 자리를 비우고 값만 보여준다.
                    <Box key={c.key} sx={{ minWidth: 0 }}>{groupedCell(c, t)}</Box>
                  ))}
                </Paper>
              ))}
            </Stack>
          </Box>
        ))}
      </Stack>
    );
  }

  return (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            {cols.map((c) => (
              <TableCell key={c.key} scope="col" align={c.align || "left"} sx={{ width: c.width, whiteSpace: "nowrap" }}>
                {c.label || null}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        {groups.map(([groupName, items]) => (
          <TableBody key={groupName}>
            <TableRow>
              <TableCell
                component="th"
                scope="colgroup"
                colSpan={cols.length}
                sx={{
                  bgcolor: (theme) => alpha(theme.palette.primary.main, 0.07),
                  fontSize: "0.8125rem",
                  color: "text.primary",
                  borderTop: 1, borderColor: "divider",
                }}
              >
                {groupHeading(groupName, items.length)}
              </TableCell>
            </TableRow>
            {items.map((t, i) => (
              <TableRow key={groupedRowKey(t, i)} hover>
                {cols.map((c) => (
                  <TableCell key={c.key} align={c.align || "left"} sx={{ overflowWrap: "anywhere", fontVariantNumeric: "tabular-nums" }}>
                    {groupedCell(c, t)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        ))}
      </Table>
    </TableContainer>
  );
}

// 편집 모달용 후보/옵션은 모달이 열릴 때만 불러온다(enabled:open) — 목록 화면 초기 로드를 늘리지 않는다.
function useAssigneeOptions(open) {
  return useQuery({ queryKey: ["tickets", "assignees"], queryFn: () => api("/api/tickets/assignees"), enabled: open, retry: false, staleTime: 60000 });
}
function useTicketMeta(open) {
  return useQuery({ queryKey: ["tickets", "meta"], queryFn: () => api("/api/tickets/meta"), enabled: open, retry: false, staleTime: 300000 });
}

/* 담당자 선택 목록 — 편집 모달과 새 티켓 폼이 같은 마크업을 쓴다(예전엔 .k-check-list를 두 곳에
 * 손으로 복사해 두어 한쪽만 고치면 조용히 어긋났다). 목록이 길어질 수 있어 높이를 제한하고 스크롤한다. */
function AssigneePicker({ loading, candidates, selected, onToggle, myId }) {
  if (loading) return <Typography variant="body2" color="text.secondary">불러오는 중…</Typography>;
  if (!candidates.length) return <Typography variant="body2" color="text.secondary">배정 후보가 없습니다(Notion에 연결된 사용자 없음).</Typography>;
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1, maxHeight: "12rem", overflow: "auto",
        display: "grid",
        // 후보가 많은 팀에서 한 줄에 하나씩만 쌓으면 스크롤이 길어진다 — 넓은 화면에서는 여러 열로.
        gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", xxl: "repeat(3, minmax(0,1fr))" },
      }}
    >
      {candidates.map((c) => (
        <FormControlLabel
          key={c.user_id}
          sx={{ m: 0 }}
          control={<Checkbox size="small" checked={selected.includes(c.user_id)} onChange={() => onToggle(c.user_id)} />}
          label={<Typography variant="body2">{c.display_name}{myId && c.user_id === myId ? " (나)" : ""}</Typography>}
        />
      ))}
    </Paper>
  );
}

/* 티켓 편집 모달 — Notion에 들어가지 않고 도우미로 담당자·예상 WD·난이도·우선순위·진행상태·마감을
 * 수정한다. 바뀐 필드만 PATCH 한다(exclude_unset). 소유권/스키마 검증은 서버가 판단한다. */
export function TicketEditModal({ ticket, open, onClose }) {
  const qc = useQueryClient();
  const toast = useToast();
  const assigneesQ = useAssigneeOptions(open);
  const metaQ = useTicketMeta(open);
  const [form, setForm] = React.useState(null);
  React.useEffect(() => {
    if (!open || !ticket) { setForm(null); return; }
    setForm({
      status: ticket.status || "",
      priority: ticket.priority || "",
      difficulty: ticket.difficulty || "",
      est_wd: ticket.est_wd != null ? String(ticket.est_wd) : "",
      due: ticket.due || "",
      assignees: [...(ticket.assignee_user_ids || [])],
    });
  }, [open, ticket]);
  const m = useMutation({
    mutationFn: (changes) => api(`/api/tickets/${ticket.id}`, { method: "PATCH", body: changes }),
    onSuccess: () => { toast("티켓을 저장했습니다.", "success"); qc.invalidateQueries({ queryKey: ["tickets"] }); onClose(); },
    onError: (e) => { toast((e && e.message) || "저장하지 못했습니다.", "error"); },
  });
  if (!open || !ticket || !form) return null;

  const meta = metaQ.data || {};
  const candidates = (assigneesQ.data && assigneesQ.data.assignees) || [];
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }));
  const toggleAssignee = (uid) => setForm((s) => ({
    ...s,
    assignees: s.assignees.includes(uid) ? s.assignees.filter((x) => x !== uid) : [...s.assignees, uid],
  }));

  function buildChanges() {
    const c = {};
    if (form.status !== (ticket.status || "")) c.status = form.status;
    if (form.priority !== (ticket.priority || "")) c.priority = form.priority;
    if (form.difficulty !== (ticket.difficulty || "")) c.difficulty = form.difficulty;
    const initWd = ticket.est_wd != null ? String(ticket.est_wd) : "";
    if (form.est_wd !== initWd) c.est_wd = form.est_wd === "" ? null : Number(form.est_wd);
    if (form.due !== (ticket.due || "")) c.due_date = form.due;
    if (!sameSet(form.assignees, ticket.assignee_user_ids || [])) c.assignee_user_ids = form.assignees;
    return c;
  }

  function submit() {
    if (!form.status) { toast("진행상태는 비울 수 없습니다.", "error"); return; }
    if (form.est_wd !== "" && Number.isNaN(Number(form.est_wd))) { toast("예상 WD에는 숫자를 입력하세요.", "error"); return; }
    const changes = buildChanges();
    if (Object.keys(changes).length === 0) { toast("변경한 내용이 없습니다.", "info"); return; }
    m.mutate(changes);
  }

  const footer = <ModalFooter onCancel={onClose} onSubmit={submit} submitLabel="저장" busy={m.isPending} />;
  const statusOpts = withCurrent(meta.statuses, form.status);
  const prioOpts = withCurrent(meta.priorities, form.priority);
  const diffOpts = withCurrent(meta.difficulties, form.difficulty);
  return (
    <Modal open={open} onClose={onClose} title={"티켓 편집" + (ticket.tid != null ? ", GIT-" + ticket.tid : "")} size="md" footer={footer}>
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Box sx={{ mb: 2.5 }}>
          <Typography component="span" variant="body2" sx={{ fontWeight: 700, display: "block", mb: 1 }}>담당자</Typography>
          <AssigneePicker loading={assigneesQ.isLoading} candidates={candidates} selected={form.assignees} onToggle={toggleAssignee} />
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
            선택한 사람으로 담당자를 설정합니다. 앱에 연결되지 않은 기존 담당자는 그대로 유지됩니다.
          </Typography>
        </Box>
        {/* 짧은 값 입력들은 넓은 화면에서 두 열로 접는다 — 한 열로 길게 쌓으면 모달이 세로로만 길어진다. */}
        <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))" } }}>
          <TextField id="te-status" select fullWidth size="small" label="진행상태" value={form.status} onChange={(e) => set("status", e.target.value)}>
            {statusOpts.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
          </TextField>
          <TextField id="te-prio" select fullWidth size="small" label="우선순위" {...EMPTYABLE_SELECT} value={form.priority} onChange={(e) => set("priority", e.target.value)}>
            <MenuItem value="">없음</MenuItem>
            {prioOpts.map((p) => <MenuItem key={p} value={p}>{priorityKo(p)}</MenuItem>)}
          </TextField>
          <TextField id="te-diff" select fullWidth size="small" label="난이도" {...EMPTYABLE_SELECT} value={form.difficulty} onChange={(e) => set("difficulty", e.target.value)}>
            <MenuItem value="">없음</MenuItem>
            {diffOpts.map((d) => <MenuItem key={d} value={d}>{d}</MenuItem>)}
          </TextField>
          <TextField id="te-wd" fullWidth size="small" label="예상 WD" type="number" inputProps={{ step: "0.5", min: "0" }}
            value={form.est_wd} onChange={(e) => set("est_wd", e.target.value)} />
          <TextField id="te-due" fullWidth size="small" label="마감일" type="date" InputLabelProps={{ shrink: true }}
            value={form.due} onChange={(e) => set("due", e.target.value)} />
        </Box>
        <button type="submit" className="sr-only" tabIndex={-1} aria-hidden="true" />
      </form>
    </Modal>
  );
}

// 미할당 티켓을 '나에게 배정'하는 뮤테이션 — 성공 시 목록을 다시 불러온다.
export function useClaim() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (id) => api(`/api/tickets/${id}/claim`, { method: "POST" }),
    onSuccess: () => { toast("나에게 배정했습니다.", "success"); qc.invalidateQueries({ queryKey: ["tickets"] }); },
    onError: (e) => { toast((e && e.message) || "배정하지 못했습니다.", "error"); }, });
}

// configured=false(토큰 미설정) / mapped=false(내 Notion 계정 미연결) 공통 안내.
// 반드시 '일반 함수'다, 컴포넌트로 <ConnState/>를 만들면 그 JSX 요소가 항상 truthy라
// `if (conn) return conn`가 언제나 참이 되어 본문(카드, 표)이 통째로 안 그려졌다(빈 화면 버그).
// 문제가 없으면 null을 돌려주고, 호출부는 그 null을 보고 본문을 그린다.
//
// 사내 대부분의 설치에서 이 화면의 첫인상이 바로 이 상태다(Notion 토큰이 없으면 항상 여기로 온다) —
// 경고 한 줄로 끝내지 말고 '지금 무엇을 하면 되는지'까지 EmptyState로 보여준다(kit §9와 같은 규칙).
// 팀 티켓·스프린트 화면도 같은 함수를 쓴다 — 예전엔 화면마다 같은 뜻의 문장을 따로 적어 두어
// 한 곳만 고치면 나머지가 옛 문구로 남았다(연동 미설정은 티켓 화면 전부가 동시에 맞는 상태다).
export function ticketConnState(data) {
  if (data && data.configured === false) {
    return (
      <EmptyState
        art="tickets"
        title="Notion 연동이 아직 설정되지 않았습니다"
        situation="티켓 데이터는 Notion 작업 DB에서 옵니다. 아직 연동 토큰이 등록되지 않아 목록을 불러올 수 없습니다."
        prerequisite="관리자 권한과 Notion 통합 토큰"
        steps={["관리자에게 Notion 연동 설정을 요청하세요.", "연동이 등록되면 이 화면을 새로고침하세요."]}
        expected="연동이 끝나면 담당자·상태·마감이 담긴 티켓 목록이 이 자리에 표시됩니다."
      />
    );
  }
  if (data && data.mapped === false) {
    return (
      <EmptyState
        art="tickets"
        title="내 계정이 Notion 사용자와 연결되어 있지 않습니다"
        situation="계정 연결이 없으면 어떤 티켓이 내 것인지 판단할 수 없어 목록을 불러올 수 없습니다."
        steps={["관리자에게 ‘Notion 사용자 연결’을 요청하세요.", "연결이 끝나면 이 화면을 새로고침하세요."]}
        expected="연결되면 내 담당 티켓이 이 자리에 표시됩니다."
      />
    );
  }
  if (data && data.ok === false && data.error) {
    return <Callout tone="danger">{data.error}</Callout>;
  }
  return null;
}

function useMine() {
  return useQuery({ queryKey: ["tickets", "mine"], queryFn: () => api("/api/tickets/mine"), retry: false });
}

/* 카드 제목줄(제목 + 오른쪽 링크) — 홈 위젯들이 공유하던 .c-card-head를 대신한다. */
function CardHead({ title, action }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2, flexWrap: "wrap", mb: 1.5 }}>
      <Typography component="h3" variant="h6" sx={{ fontSize: "1.0625rem", minWidth: 0 }}>{title}</Typography>
      {action}
    </Box>
  );
}

// 요약 카드 줄 — DataScreen(재설계 기준 화면)의 통계 카드 그리드와 같은 열 규칙을 쓴다.
const STAT_GRID = {
  display: "grid", gap: 2, mb: 2.5,
  gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", lg: "repeat(4, minmax(0,1fr))" },
};

/* 내 업무(홈), 상태별 요약 카드(누르면 아래 목록이 그 상태로 필터됨) + 지연 강조.
 * 카드=필터 선택: 누르면 그 상태가 '선택된 채로 유지'된다. 해제는 목록 위 '필터 해제'로 한다
 * (같은 카드를 다시 눌러도 풀리지 않는다 — 눌러 놓은 필터가 저절로 풀리면 헷갈린다는 피드백 반영). */
export function MyWork() {
  const q = useMine();
  const nav = useNavigate();
  const [focus, setFocus] = React.useState(null); // null | active | due7 | overdue | done
  const [editing, setEditing] = React.useState(null);
  const today = todayISO();
  const weekEnd = addDaysISO(today, 7);
  return (
    <div className="c-screen">
      <PageHeader title="내 업무" spot="mywork" />
      {q.isLoading ? <Card><Skeleton /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const data = q.data || {};
          const conn = ticketConnState(data);
          if (conn) return conn;
          const tickets = Array.isArray(data.tickets) ? data.tickets : [];
          const active = tickets.filter(isActive);
          const done = tickets.filter((t) => t.status === "완료");
          const overdue = tickets.filter((t) => isOverdue(t, today));
          // 마감 임박: 오늘부터 7일 이내. 라벨을 '이번 주'로 쓰면 실제 로직(오늘+7일 롤링)과 어긋나
          // 헷갈린다(예: 오늘이 7/28이면 8/3 마감도 잡힌다) — '7일 내 마감'으로 정확히 부른다.
          const due7 = active.filter((t) => t.due && t.due >= today && t.due <= weekEnd);
          const byDue = (rows) => [...rows].sort((a, b) => (a.due || "9999").localeCompare(b.due || "9999"));
          const views = {
            active: { title: "진행 중인 내 티켓", rows: active },
            due7: { title: "7일 내 마감", rows: due7 },
            overdue: { title: "지연(기한 초과)", rows: overdue },
            done: { title: "완료한 티켓", rows: done },
          };
          const cur = focus ? views[focus] : null;
          const select = (k) => setFocus(k);  // 선택 유지(같은 카드를 다시 눌러도 해제되지 않음)
          const listRows = cur ? byDue(cur.rows) : byDue(active).slice(0, 8);
          return (
            <>
              <Box sx={STAT_GRID}>
                <StatCard value={active.length} label="진행 중인 내 티켓" active={focus === "active"} onClick={() => select("active")} />
                <StatCard value={due7.length} label="7일 내 마감" kind={due7.length ? "warn" : undefined} active={focus === "due7"} onClick={() => select("due7")} />
                <StatCard value={overdue.length} label="지연(기한 초과)" kind={overdue.length ? "danger" : undefined} active={focus === "overdue"} onClick={() => select("overdue")} />
                <StatCard value={done.length} label="완료" kind="ok" active={focus === "done"} onClick={() => select("done")} />
              </Box>
              {overdue.length && focus !== "overdue" ? (
                <Box sx={{ mb: 2.5 }}>
                  <Callout tone="danger">
                    마감이 지난 미완료 티켓이 {overdue.length}건 있습니다.{" "}
                    <Link component="button" type="button" underline="hover" sx={{ font: "inherit" }} onClick={() => setFocus("overdue")}>여기서 보기</Link>
                    {" 또는 "}
                    <Link href="#/my-tickets" underline="hover">내 티켓에서 확인</Link>하세요.
                  </Callout>
                </Box>
              ) : null}
              <Card>
                <CardHead
                  title={cur ? cur.title + " (" + cur.rows.length + "건)" : "다가오는 내 티켓"}
                  action={cur
                    ? <Link component="button" type="button" underline="hover" onClick={() => setFocus(null)}>필터 해제</Link>
                    : <Link href="#/my-tickets" underline="hover">전체 보기</Link>}
                />
                <DataTable columns={ticketColumns({ onEdit: setEditing, onOpen: (t) => nav(ticketPath(t)) })}
                  rows={listRows} rowKey={(t) => t.id}
                  empty={cur ? "해당하는 티켓이 없습니다." : "진행 중인 티켓이 없습니다."} />
              </Card>
            </>
          );
        })()}
      <BoardActivity />
      <TeamChatWidget />
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}

/* 내 게시판 활동 위젯 — 홈에서 본인이 쓴 최근 글 + 요약(글 수·받은 댓글·조회)을 보여준다.
 * 게시판이 꺼져 있거나(404) 로딩 중이면 조용히 숨긴다(홈의 다른 부분에 영향 없이). */
function BoardActivity() {
  const q = useQuery({ queryKey: ["board-mine"], queryFn: () => api("/api/board/mine"), retry: false });
  if (q.isError || !q.data) return null;
  const items = q.data.items || [];
  const s = q.data.summary || { post_count: 0, comment_count_received: 0, view_count_total: 0 };
  const stat = (num, label) => (
    <Box sx={{ display: "grid", gap: 0.25 }}>
      <Typography component="span" sx={{ fontSize: "1.375rem", fontWeight: 800, lineHeight: 1.1 }}>{num}</Typography>
      <Typography component="span" variant="caption" color="text.secondary">{label}</Typography>
    </Box>
  );
  return (
    <Card sx={{ mt: 2.5 }}>
      <CardHead title="내 게시판 활동" action={<Link href="#/board" underline="hover">자유게시판</Link>} />
      <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(3, minmax(0,1fr))", maxWidth: "32rem", mb: 2 }}>
        {stat(s.post_count, "내 글")}
        {stat(s.comment_count_received, "받은 댓글")}
        {stat(s.view_count_total, "조회")}
      </Box>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          아직 작성한 글이 없습니다. <Link href="#/board" underline="hover">첫 글 남기기</Link>
        </Typography>
      ) : (
        <Stack component="ul" gap={1} sx={{ listStyle: "none", m: 0, p: 0 }}>
          {items.map((p) => (
            <Box
              component="li"
              key={p.id}
              sx={{
                display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 2,
                py: 0.75, borderBottom: 1, borderColor: "divider", "&:last-of-type": { borderBottom: 0 },
              }}
            >
              <Link href={"#/board/" + p.id} underline="hover" sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0, color: "text.primary" }}>
                {p.is_pinned ? <Badge value="고정" kind="info" /> : null}
                <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.title}</Box>
              </Link>
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>댓글 {p.comment_count}, 조회 {p.view_count}</Typography>
            </Box>
          ))}
        </Stack>
      )}
    </Card>
  );
}

/* 목록 화면 위 툴바(상태 필터 + 건수) — 내 티켓·미할당·팀 티켓이 같은 모양을 쓴다.
 * DataScreen의 필터 바와 같은 자동 줄바꿈 그리드다 — 화면이 넓어지면 한 줄에 담기고 좁으면 접힌다. */
export function TicketToolbar({ children, count }) {
  return (
    <Box
      sx={{
        display: "grid", gap: 1.5, alignItems: "center", mb: 2,
        gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fit, minmax(11rem, max-content))" },
      }}
    >
      {children}
      {count != null ? (
        <Typography variant="body2" color="text.secondary" aria-live="polite">{count}건</Typography>
      ) : null}
    </Box>
  );
}

// 티켓 상태 필터 — 내 티켓·팀 티켓이 같은 어휘를 쓴다(한쪽만 고치면 두 화면의 필터가 어긋난다).
// withOverdue: '지연'은 상태가 아니라 마감 기준 파생값이라, 그 계산이 있는 화면(내 티켓)에서만 준다.
export function StatusFilter({ value, onChange, withOverdue }) {
  return (
    <TextField select size="small" label="상태" value={value} onChange={(e) => onChange(e.target.value)} sx={{ minWidth: "13rem" }}>
      <MenuItem value="active">진행 중(완료, 취소 제외)</MenuItem>
      {withOverdue ? <MenuItem value="overdue">지연</MenuItem> : null}
      <MenuItem value="진행">진행</MenuItem>
      <MenuItem value="검증">검증</MenuItem>
      <MenuItem value="계획">계획</MenuItem>
      <MenuItem value="이슈">이슈</MenuItem>
      <MenuItem value="완료">완료</MenuItem>
      <MenuItem value="취소">취소</MenuItem>
      <MenuItem value="all">전체</MenuItem>
    </TextField>
  );
}

/* 내 티켓, 상태 필터 + 전체 목록 + 편집. */
export function MyTickets() {
  const q = useMine();
  const nav = useNavigate();
  const [status, setStatus] = React.useState("active");
  const [editing, setEditing] = React.useState(null);
  const toast = useToast();
  const qc = useQueryClient();
  const sel = useRowSelection();
  const bulk = useBulkTrash("/api/tickets/trash-bulk", qc, toast, () => { sel.clear(); q.refetch(); });
  const today = todayISO();
  // 상태 필터를 바꾸면 선택을 비운다(숨겨진 항목이 선택된 채 남지 않게).
  const changeStatus = (v) => { setStatus(v); sel.clear(); };
  const headerActions = (
    <BulkActions count={sel.selected.size} onClear={sel.clear}>
      <Button size="sm" variant="danger" disabled={bulk.isPending} onClick={() => bulk.mutate([...sel.selected])}>선택 삭제</Button>
    </BulkActions>
  );
  return (
    <div className="c-screen">
      <PageHeader crumbRoot="내 업무" area="내 티켓" title="내 티켓" spot="mywork" actions={headerActions} />
      {q.isLoading ? <Card><Skeleton /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const data = q.data || {};
          const conn = ticketConnState(data);
          if (conn) return conn;
          const all = Array.isArray(data.tickets) ? data.tickets : [];
          const rows = status === "all" ? all
            : status === "active" ? all.filter(isActive)
            : status === "overdue" ? all.filter((t) => isOverdue(t, today))
            : all.filter((t) => t.status === status);
          const cols = [selectionColumn(sel, rows.map((r) => r.id)),
            ...ticketColumns({ showAssignee: true, onEdit: setEditing, onOpen: (t) => nav(ticketPath(t)) })];
          return (
            <Card>
              <TicketToolbar count={rows.length}>
                <StatusFilter value={status} onChange={changeStatus} withOverdue />
              </TicketToolbar>
              <GroupedTickets rows={rows} columns={cols} empty="조건에 맞는 티켓이 없습니다." />
            </Card>
          );
        })()}
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}

/* 미할당 티켓 — 담당자 없는 활성 티켓. '나에게 배정'(claim) 또는 편집으로 담당자를 지정한다. */
export function Unassigned() {
  const q = useQuery({ queryKey: ["tickets", "unassigned"], queryFn: () => api("/api/tickets/unassigned"), retry: false });
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(null);
  const claim = useClaim();
  const sel = useRowSelection();
  const bulk = useBulkTrash("/api/tickets/trash-bulk", qc, toast, () => { sel.clear(); q.refetch(); });
  const headerActions = (
    <BulkActions count={sel.selected.size} onClear={sel.clear}>
      <Button size="sm" variant="danger" disabled={bulk.isPending} onClick={() => bulk.mutate([...sel.selected])}>선택 삭제</Button>
    </BulkActions>
  );
  return (
    <div className="c-screen">
      <PageHeader crumbRoot="내 업무" area="미할당 티켓" title="미할당 티켓" spot="mywork" actions={headerActions} />
      {q.isLoading ? <Card><Skeleton /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const data = q.data || {};
          const conn = ticketConnState(data);
          if (conn) return conn;
          const rows = Array.isArray(data.tickets) ? data.tickets : [];
          const cols = [selectionColumn(sel, rows.map((r) => r.id)),
            ...ticketColumns({ onEdit: setEditing, onClaim: (t) => claim.mutate(t.id), onOpen: (t) => nav(ticketPath(t)) })];
          return (
            <Card>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: "70ch" }}>
                담당자가 지정되지 않은 활성 티켓입니다. ‘나에게 배정’을 누르면 담당자가 됩니다. 다른 사람 배정, 수정은 ‘편집’에서 하세요.
              </Typography>
              <GroupedTickets rows={rows} columns={cols} empty="담당자 없는 티켓이 없습니다." />
            </Card>
          );
        })()}
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}

/* 새 티켓 — 채팅 없이 폼으로 생성(제목·프로젝트 필수). 담당자 기본값은 나(연결된 경우).
 * 복잡한 배경/요구사항이 필요한 티켓은 AI 도우미가 더 낫다 — 여기선 빠른 생성에 집중한다. */
export function NewTicket() {
  const auth = useAuth();
  const myId = auth.data && auth.data.id;
  const qc = useQueryClient();
  const toast = useToast();
  const projectsQ = useQuery({ queryKey: ["tickets", "projects"], queryFn: () => api("/api/tickets/projects"), retry: false, staleTime: 300000 });
  const assigneesQ = useQuery({ queryKey: ["tickets", "assignees"], queryFn: () => api("/api/tickets/assignees"), retry: false, staleTime: 60000 });
  const metaQ = useTicketMeta(true);
  const [form, setForm] = React.useState({ title: "", project_id: "", status: "", priority: "", difficulty: "", est_wd: "", due: "", assignees: [], description: "" });
  const meApplied = React.useRef(false);
  // 후보가 로드되면 최초 1회 '나'를 기본 담당자로 체크(연결된 경우).
  React.useEffect(() => {
    if (meApplied.current) return;
    const cands = (assigneesQ.data && assigneesQ.data.assignees) || [];
    if (myId && cands.some((c) => c.user_id === myId)) {
      meApplied.current = true;
      setForm((s) => ({ ...s, assignees: s.assignees.length ? s.assignees : [myId] }));
    }
  }, [assigneesQ.data, myId]);
  // 진행상태 기본값(계획)을 메타 로드 후 한 번 채운다.
  const statusApplied = React.useRef(false);
  React.useEffect(() => {
    if (statusApplied.current) return;
    const st = (metaQ.data && metaQ.data.statuses) || [];
    if (st.length) {
      statusApplied.current = true;
      setForm((s) => ({ ...s, status: s.status || (st.includes("계획") ? "계획" : st[0]) }));
    }
  }, [metaQ.data]);

  const create = useMutation({
    mutationFn: (body) => api("/api/tickets", { method: "POST", body }),
    onSuccess: () => { toast("티켓을 생성했습니다.", "success"); qc.invalidateQueries({ queryKey: ["tickets"] }); window.location.hash = "#/my-tickets"; },
    onError: (e) => { toast((e && e.message) || "생성하지 못했습니다.", "error"); },
  });

  const meta = metaQ.data || {};
  const candidates = (assigneesQ.data && assigneesQ.data.assignees) || [];
  const projects = (projectsQ.data && projectsQ.data.projects) || [];
  const set = (k, v) => setForm((s) => ({ ...s, [k]: v }));
  const toggleAssignee = (uid) => setForm((s) => ({ ...s, assignees: s.assignees.includes(uid) ? s.assignees.filter((x) => x !== uid) : [...s.assignees, uid] }));
  const notConfigured = (projectsQ.data && projectsQ.data.configured === false) || (metaQ.data && metaQ.data.configured === false);

  function submit() {
    if (!form.title.trim()) { toast("제목을 입력하세요.", "error"); return; }
    if (projects.length && !form.project_id) { toast("프로젝트를 선택하세요.", "error"); return; }
    if (form.est_wd !== "" && Number.isNaN(Number(form.est_wd))) { toast("예상 WD에는 숫자를 입력하세요.", "error"); return; }
    const body = { title: form.title.trim() };
    if (form.project_id) body.project_id = form.project_id;
    if (form.status) body.status = form.status;
    if (form.priority) body.priority = form.priority;
    if (form.difficulty) body.difficulty = form.difficulty;
    if (form.est_wd !== "") body.est_wd = Number(form.est_wd);
    if (form.due) body.due_date = form.due;
    if (form.assignees.length) body.assignee_user_ids = form.assignees;
    if (form.description.trim()) body.description = form.description.trim();
    create.mutate(body);
  }

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="내 업무" area="새 티켓" title="새 티켓" spot="mywork" />
      {notConfigured ? (
        <Callout tone="warn">Notion 연동이 아직 설정되지 않아 티켓을 만들 수 없습니다. 관리자에게 문의하세요.</Callout>
      ) : (
        <Card>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5, maxWidth: "70ch" }}>
            간단한 티켓을 바로 만듭니다. 배경, 요구사항이 많은 티켓은 <Link href="#/chat" underline="hover">AI 도우미</Link>가 더 정확합니다.
          </Typography>
          {/* 본문(설명)은 산문이라 줄이 길어지면 읽기 어렵다 — 폼 자체를 CONTENT 폭 전체로 늘리지 않고
              읽기 좋은 폭에서 멈춘다. 짧은 값 입력들만 넓은 화면에서 두 열로 접는다. */}
          <Box component="form" onSubmit={(e) => { e.preventDefault(); submit(); }} sx={{ maxWidth: "72rem" }}>
            <TextField id="nt-title" fullWidth size="small" required label="제목" sx={{ mb: 2.5 }}
              value={form.title} onChange={(e) => set("title", e.target.value)} inputProps={{ maxLength: 200 }}
              placeholder="예: 서버 등록 IP 중복 방지" />
            <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", xxl: "repeat(3, minmax(0,1fr))" }, mb: 2.5 }}>
              <TextField id="nt-proj" select fullWidth size="small" label="프로젝트" required={!!projects.length} {...EMPTYABLE_SELECT}
                value={form.project_id} onChange={(e) => set("project_id", e.target.value)}
                disabled={projectsQ.isLoading || !projects.length}>
                <MenuItem value="">{projectsQ.isLoading ? "불러오는 중…" : (projects.length ? "선택 안 함" : "프로젝트 없음")}</MenuItem>
                {projects.map((p) => <MenuItem key={p.id} value={p.id}>{p.name || "(제목 없음)"}</MenuItem>)}
              </TextField>
              <TextField id="nt-status" select fullWidth size="small" label="진행상태" value={form.status} onChange={(e) => set("status", e.target.value)}>
                {withCurrent(meta.statuses, form.status).map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
              </TextField>
              <TextField id="nt-prio" select fullWidth size="small" label="우선순위" {...EMPTYABLE_SELECT} value={form.priority} onChange={(e) => set("priority", e.target.value)}>
                <MenuItem value="">없음</MenuItem>
                {withCurrent(meta.priorities, form.priority).map((p) => <MenuItem key={p} value={p}>{priorityKo(p)}</MenuItem>)}
              </TextField>
              <TextField id="nt-diff" select fullWidth size="small" label="난이도" {...EMPTYABLE_SELECT} value={form.difficulty} onChange={(e) => set("difficulty", e.target.value)}>
                <MenuItem value="">없음</MenuItem>
                {withCurrent(meta.difficulties, form.difficulty).map((d) => <MenuItem key={d} value={d}>{d}</MenuItem>)}
              </TextField>
              <TextField id="nt-wd" fullWidth size="small" label="예상 WD" type="number" inputProps={{ step: "0.5", min: "0" }}
                value={form.est_wd} onChange={(e) => set("est_wd", e.target.value)} />
              <TextField id="nt-due" fullWidth size="small" label="마감일" type="date" InputLabelProps={{ shrink: true }}
                value={form.due} onChange={(e) => set("due", e.target.value)} />
            </Box>
            <Box sx={{ mb: 2.5 }}>
              <Typography component="span" variant="body2" sx={{ fontWeight: 700, display: "block", mb: 1 }}>담당자</Typography>
              <AssigneePicker loading={assigneesQ.isLoading} candidates={candidates} selected={form.assignees} onToggle={toggleAssignee} myId={myId} />
            </Box>
            <Box sx={{ mb: 2.5, maxWidth: "60rem" }}>
              <Typography component="label" htmlFor="nt-desc" variant="body2" sx={{ fontWeight: 700, display: "block", mb: 1 }}>설명</Typography>
              <BodyEditor
                id="nt-desc"
                value={form.description}
                onChange={(v) => set("description", v)}
                rows={12}
                placeholder="배경, 요구사항을 적어주세요(선택). 위 도구로 제목, 글머리, 번호, 구분선, 이모지를 넣을 수 있고 아래 미리보기에서 실제 모양을 확인합니다."
              />
            </Box>
            <Stack direction="row" gap={1} justifyContent="flex-end">
              <Button variant="primary" type="submit" disabled={create.isPending}>{create.isPending ? "생성 중…" : "티켓 만들기"}</Button>
            </Stack>
          </Box>
        </Card>
      )}
    </div>
  );
}
