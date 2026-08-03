import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import { Card, Badge, DataTable, EmptyState, ErrorState, Skeleton, Callout, StatCard, PageHeader, Modal, ModalFooter, Button, useToast } from "../ui/kit.jsx";
import { priorityKo, priorityKind } from "./Chat.jsx";
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
 * 난이도·우선순위·진행상태·마감 수정. 소유권/스키마 검증은 서버가 판단한다. 상태 색은 kit Badge. */

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
  if (onOpen) {
    return <button type="button" className="k-title-link" onClick={() => onOpen(t)}>{t.title || "제목 없음"}</button>;
  }
  return <span className="ticket-title-cell">{t.title || "제목 없음"}</span>;
}

// 목록 표 — 티켓/제목/상태/우선순위/난이도/예상WD/마감. 숫자·날짜는 우측 정렬(tabular-nums).
// onEdit/onClaim 을 주면 우측에 액션 열(편집·나에게 배정)이 붙는다. onOpen 을 주면 제목이 상세 링크.
export function ticketColumns({ showAssignee, onEdit, onClaim, onOpen } = {}) {
  const cols = [
    { key: "tid", label: "티켓", render: (t) => ticketId(t) },
    { key: "title", label: "제목", render: (t) => <TitleCell t={t} onOpen={onOpen} /> },
    { key: "status", label: "상태", render: (t) => (t.status ? <Badge value={t.status} /> : "-") },
    { key: "priority", label: "우선순위", render: (t) => (t.priority ? <Badge value={priorityKo(t.priority)} kind={priorityKind(t.priority)} /> : "-") },
    { key: "difficulty", label: "난이도", align: "right", render: (t) => (t.difficulty || "-") },
    { key: "est_wd", label: "예상 WD", align: "right", render: (t) => (t.est_wd != null ? t.est_wd : "-") },
    { key: "due", label: "마감", align: "right", render: (t) => (t.due || "-") },
  ];
  if (showAssignee) {
    cols.push({ key: "assignee_names", label: "담당자", render: (t) => ((t.assignee_names || []).join(", ") || "-") });
  }
  if (onEdit || onClaim) {
    cols.push({
      key: "_actions", label: "", align: "right",
      render: (t) => (
        <div className="k-row-actions">
          {onClaim ? <Button size="sm" variant="primary" onClick={() => onClaim(t)}>나에게 배정</Button> : null}
          {onEdit ? <Button size="sm" onClick={() => onEdit(t)}>편집</Button> : null}
        </div>
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

// 그룹 기준으로 묶어 '하나의 표'로 그린다(그룹마다 별도 table을 쓰면 열 너비가 어긋남). 기본은
// 프로젝트별, groupBy 를 주면 담당자별 등 다른 기준으로. 행 전체는 클릭 대상이 아니다 — 제목만 상세로.
export function GroupedTickets({ rows, columns, empty, groupBy }) {
  const cols = columns;
  const grouper = groupBy || groupByProject;
  const cls = (c) => [c.align ? "is-" + c.align : "", c.className || ""].filter(Boolean).join(" ");
  if (!rows.length) {
    return (
      <div className="k-table-wrap">
        <table className="k-table"><tbody>
          <tr><td className="k-table-empty" colSpan={cols.length}>{empty}</td></tr>
        </tbody></table>
      </div>
    );
  }
  return (
    <div className="k-table-wrap">
      <table className="k-table k-table--grouped">
        <thead>
          <tr>{cols.map((c) => <th key={c.key} scope="col" className={cls(c)}>{c.label}</th>)}</tr>
        </thead>
        {grouper(rows).map(([groupName, items]) => (
          <tbody key={groupName}>
            <tr className="k-group-row">
              <th colSpan={cols.length} scope="colgroup">
                <span className="k-group-name">{groupName}</span>
                <span className="k-group-count">{items.length}건</span>
              </th>
            </tr>
            {items.map((t) => (
              <tr key={t.id}>
                {cols.map((c) => (
                  <td key={c.key} data-label={c.label} className={cls(c)}>
                    {c.render ? c.render(t) : (t[c.key] == null || t[c.key] === "" ? "-" : String(t[c.key]))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

// 편집 모달용 후보/옵션은 모달이 열릴 때만 불러온다(enabled:open) — 목록 화면 초기 로드를 늘리지 않는다.
function useAssigneeOptions(open) {
  return useQuery({ queryKey: ["tickets", "assignees"], queryFn: () => api("/api/tickets/assignees"), enabled: open, retry: false, staleTime: 60000 });
}
function useTicketMeta(open) {
  return useQuery({ queryKey: ["tickets", "meta"], queryFn: () => api("/api/tickets/meta"), enabled: open, retry: false, staleTime: 300000 });
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
        <div className="k-field">
          <span className="k-field-label">담당자</span>
          {assigneesQ.isLoading ? <div className="k-field-help">불러오는 중…</div>
            : candidates.length === 0 ? <div className="k-field-help">배정 후보가 없습니다(Notion에 연결된 사용자 없음).</div>
            : (
              <div className="k-check-list">
                {candidates.map((c) => (
                  <label key={c.user_id} className="k-check">
                    <input type="checkbox" checked={form.assignees.includes(c.user_id)} onChange={() => toggleAssignee(c.user_id)} />
                    {" "}{c.display_name}
                  </label>
                ))}
              </div>
            )}
          <div className="k-field-help">선택한 사람으로 담당자를 설정합니다. 앱에 연결되지 않은 기존 담당자는 그대로 유지됩니다.</div>
        </div>
        <div className="k-field">
          <label className="k-field-label" htmlFor="te-status">진행상태</label>
          <select id="te-status" className="k-input" value={form.status} onChange={(e) => set("status", e.target.value)}>
            {statusOpts.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="k-field">
          <label className="k-field-label" htmlFor="te-prio">우선순위</label>
          <select id="te-prio" className="k-input" value={form.priority} onChange={(e) => set("priority", e.target.value)}>
            <option value="">없음</option>
            {prioOpts.map((p) => <option key={p} value={p}>{priorityKo(p)}</option>)}
          </select>
        </div>
        <div className="k-field">
          <label className="k-field-label" htmlFor="te-diff">난이도</label>
          <select id="te-diff" className="k-input" value={form.difficulty} onChange={(e) => set("difficulty", e.target.value)}>
            <option value="">없음</option>
            {diffOpts.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <div className="k-field">
          <label className="k-field-label" htmlFor="te-wd">예상 WD</label>
          <input id="te-wd" className="k-input" type="number" step="0.5" min="0" value={form.est_wd} onChange={(e) => set("est_wd", e.target.value)} />
        </div>
        <div className="k-field">
          <label className="k-field-label" htmlFor="te-due">마감일</label>
          <input id="te-due" className="k-input" type="date" value={form.due} onChange={(e) => set("due", e.target.value)} />
        </div>
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
function connCallout(data) {
  if (data && data.configured === false) {
    return <Callout tone="warn">Notion 연동이 아직 설정되지 않았습니다. 관리자에게 문의하세요.</Callout>;
  }
  if (data && data.mapped === false) {
    return <Callout tone="warn">내 계정이 Notion 사용자와 연결되어 있지 않아 내 티켓을 불러올 수 없습니다. 관리자에게 ‘Notion 사용자 연결’을 요청하세요.</Callout>;
  }
  if (data && data.ok === false && data.error) {
    return <Callout tone="danger">{data.error}</Callout>;
  }
  return null;
}

function useMine() {
  return useQuery({ queryKey: ["tickets", "mine"], queryFn: () => api("/api/tickets/mine"), retry: false });
}

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
      <PageHeader title="내 업무" />
      {q.isLoading ? <Card><Skeleton /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const data = q.data || {};
          const conn = connCallout(data);
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
              <div className="dash-grid">
                <StatCard value={active.length} label="진행 중인 내 티켓" active={focus === "active"} onClick={() => select("active")} />
                <StatCard value={due7.length} label="7일 내 마감" kind={due7.length ? "warn" : undefined} active={focus === "due7"} onClick={() => select("due7")} />
                <StatCard value={overdue.length} label="지연(기한 초과)" kind={overdue.length ? "danger" : undefined} active={focus === "overdue"} onClick={() => select("overdue")} />
                <StatCard value={done.length} label="완료" kind="ok" active={focus === "done"} onClick={() => select("done")} />
              </div>
              {overdue.length && focus !== "overdue" ? (
                <Callout tone="danger">마감이 지난 미완료 티켓이 {overdue.length}건 있습니다. <button type="button" className="k-link k-linkbtn" onClick={() => setFocus("overdue")}>여기서 보기</button> 또는 <a className="k-link" href="#/my-tickets">내 티켓에서 확인</a>하세요.</Callout>
              ) : null}
              <Card>
                <div className="c-card-head">
                  <h3>{cur ? cur.title + " (" + cur.rows.length + "건)" : "다가오는 내 티켓"}</h3>
                  {cur
                    ? <button type="button" className="k-link k-linkbtn" onClick={() => setFocus(null)}>필터 해제</button>
                    : <a className="k-link" href="#/my-tickets">전체 보기</a>}
                </div>
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
  return (
    <Card className="board-mini">
      <div className="c-card-head">
        <h3>내 게시판 활동</h3>
        <a className="k-link" href="#/board">자유게시판</a>
      </div>
      <div className="board-mini-stats">
        <div className="board-mini-stat"><span className="board-mini-num">{s.post_count}</span><span className="board-mini-label">내 글</span></div>
        <div className="board-mini-stat"><span className="board-mini-num">{s.comment_count_received}</span><span className="board-mini-label">받은 댓글</span></div>
        <div className="board-mini-stat"><span className="board-mini-num">{s.view_count_total}</span><span className="board-mini-label">조회</span></div>
      </div>
      {items.length === 0 ? (
        <p className="board-mini-empty">아직 작성한 글이 없습니다. <a className="k-link" href="#/board">첫 글 남기기</a></p>
      ) : (
        <ul className="board-mini-list">
          {items.map((p) => (
            <li key={p.id} className="board-mini-row">
              <a className="board-mini-title k-link" href={"#/board/" + p.id}>
                {p.is_pinned ? <Badge value="고정" kind="info" /> : null}
                <span className="board-mini-text">{p.title}</span>
              </a>
              <span className="board-mini-meta">댓글 {p.comment_count}, 조회 {p.view_count}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
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
      <PageHeader crumbRoot="내 업무" area="내 티켓" title="내 티켓" actions={headerActions} />
      {q.isLoading ? <Card><Skeleton /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const data = q.data || {};
          const conn = connCallout(data);
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
              <div className="c-toolbar-row">
                <label className="k-field-inline"><span className="k-field-label">상태</span>
                  <select className="c-filter" value={status} onChange={(e) => changeStatus(e.target.value)}>
                    <option value="active">진행 중(완료, 취소 제외)</option>
                    <option value="overdue">지연</option>
                    <option value="진행">진행</option>
                    <option value="검증">검증</option>
                    <option value="계획">계획</option>
                    <option value="이슈">이슈</option>
                    <option value="완료">완료</option>
                    <option value="취소">취소</option>
                    <option value="all">전체</option>
                  </select>
                </label>
                <span className="k-field-help">{rows.length}건</span>
              </div>
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
      <PageHeader crumbRoot="내 업무" area="미할당 티켓" title="미할당 티켓" actions={headerActions} />
      {q.isLoading ? <Card><Skeleton /></Card>
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (() => {
          const data = q.data || {};
          const conn = connCallout(data);
          if (conn) return conn;
          const rows = Array.isArray(data.tickets) ? data.tickets : [];
          const cols = [selectionColumn(sel, rows.map((r) => r.id)),
            ...ticketColumns({ onEdit: setEditing, onClaim: (t) => claim.mutate(t.id), onOpen: (t) => nav(ticketPath(t)) })];
          return (
            <Card>
              <p className="k-field-help">담당자가 지정되지 않은 활성 티켓입니다. ‘나에게 배정’을 누르면 담당자가 됩니다. 다른 사람 배정, 수정은 ‘편집’에서 하세요.</p>
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
      <PageHeader crumbRoot="내 업무" area="새 티켓" title="새 티켓" />
      {notConfigured ? (
        <Callout tone="warn">Notion 연동이 아직 설정되지 않아 티켓을 만들 수 없습니다. 관리자에게 문의하세요.</Callout>
      ) : (
        <Card>
          <p className="k-field-help">간단한 티켓을 바로 만듭니다. 배경, 요구사항이 많은 티켓은 <a className="k-link" href="#/chat">AI 도우미</a>가 더 정확합니다.</p>
          <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <div className="k-field">
              <label className="k-field-label" htmlFor="nt-title">제목<span className="k-req"> *</span></label>
              <input id="nt-title" className="k-input" value={form.title} onChange={(e) => set("title", e.target.value)} maxLength={200} placeholder="예: 서버 등록 IP 중복 방지" />
            </div>
            <div className="k-field">
              <label className="k-field-label" htmlFor="nt-proj">프로젝트{projects.length ? <span className="k-req"> *</span> : null}</label>
              <select id="nt-proj" className="k-input" value={form.project_id} onChange={(e) => set("project_id", e.target.value)} disabled={projectsQ.isLoading || !projects.length}>
                <option value="">{projectsQ.isLoading ? "불러오는 중…" : (projects.length ? "선택 안 함" : "프로젝트 없음")}</option>
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name || "(제목 없음)"}</option>)}
              </select>
            </div>
            <div className="k-field">
              <label className="k-field-label" htmlFor="nt-status">진행상태</label>
              <select id="nt-status" className="k-input" value={form.status} onChange={(e) => set("status", e.target.value)}>
                {withCurrent(meta.statuses, form.status).map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="k-field">
              <label className="k-field-label" htmlFor="nt-prio">우선순위</label>
              <select id="nt-prio" className="k-input" value={form.priority} onChange={(e) => set("priority", e.target.value)}>
                <option value="">없음</option>
                {withCurrent(meta.priorities, form.priority).map((p) => <option key={p} value={p}>{priorityKo(p)}</option>)}
              </select>
            </div>
            <div className="k-field">
              <label className="k-field-label" htmlFor="nt-diff">난이도</label>
              <select id="nt-diff" className="k-input" value={form.difficulty} onChange={(e) => set("difficulty", e.target.value)}>
                <option value="">없음</option>
                {withCurrent(meta.difficulties, form.difficulty).map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div className="k-field">
              <label className="k-field-label" htmlFor="nt-wd">예상 WD</label>
              <input id="nt-wd" className="k-input" type="number" step="0.5" min="0" value={form.est_wd} onChange={(e) => set("est_wd", e.target.value)} />
            </div>
            <div className="k-field">
              <label className="k-field-label" htmlFor="nt-due">마감일</label>
              <input id="nt-due" className="k-input" type="date" value={form.due} onChange={(e) => set("due", e.target.value)} />
            </div>
            <div className="k-field">
              <span className="k-field-label">담당자</span>
              {assigneesQ.isLoading ? <div className="k-field-help">불러오는 중…</div>
                : candidates.length === 0 ? <div className="k-field-help">배정 후보가 없습니다(Notion에 연결된 사용자 없음).</div>
                : (
                  <div className="k-check-list">
                    {candidates.map((c) => (
                      <label key={c.user_id} className="k-check">
                        <input type="checkbox" checked={form.assignees.includes(c.user_id)} onChange={() => toggleAssignee(c.user_id)} />
                        {" "}{c.display_name}{c.user_id === myId ? " (나)" : ""}
                      </label>
                    ))}
                  </div>
                )}
            </div>
            <div className="k-field">
              <label className="k-field-label" htmlFor="nt-desc">설명</label>
              <BodyEditor
                id="nt-desc"
                value={form.description}
                onChange={(v) => set("description", v)}
                rows={12}
                placeholder="배경, 요구사항을 적어주세요(선택). 위 도구로 제목, 글머리, 번호, 구분선, 이모지를 넣을 수 있고 아래 미리보기에서 실제 모양을 확인합니다."
              />
            </div>
            <div className="k-row-actions">
              <Button variant="primary" type="submit" disabled={create.isPending}>{create.isPending ? "생성 중…" : "티켓 만들기"}</Button>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
