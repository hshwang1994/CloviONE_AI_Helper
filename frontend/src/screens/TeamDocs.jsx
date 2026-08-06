import React, { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Callout,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  Modal,
  ModalFooter,
  PageHeader,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { docTypeKind } from "../lib/badges.js";
import { BodyEditor } from "../ui/BodyEditor.jsx";
import { useRowSelection, selectionColumn, BulkActions } from "../ui/bulkSelect.jsx";
import { SearchBox } from "../ui/filters.jsx";
import { Pager } from "../ui/Pager.jsx";
import { useQueryState } from "../lib/useQueryState.js";

const PRIORITIES = ["높음", "보통", "낮음"];
const STATUSES = ["초안", "활성", "서명됨", "만료됨"];

/* 팀 공간 > 문서 목록 (§17). Notion "문서" DB의 로컬 캐시를 읽는다 — Notion이 느리거나 죽어도
 * 마지막 정상 동기화 목록이 그대로 뜬다(장애 격리). 본문/원본은 상세에서 본다.
 *
 * 2026-08 MUI 재설계: 열 너비는 계속 **열 정의 안에**(width) 둔다 — 예전처럼 screens.css의
 * `.docs-table .k-table th:nth-child(n)`으로 잡으면 열을 하나 옮기거나 선택 체크박스 열이
 * 앞에 붙는 순간 폭이 한 칸씩 밀렸다(실제로 제목 폭을 먹은 적이 있다). 필터·검색 컨트롤은
 * 손으로 쓴 .k-input 마크업(이미 규칙이 사라져 브라우저 기본 모양이었다) 대신 MUI로 그린다. */

const SORTS = [
  ["recent", "최근 수정순"],
  ["title", "제목순"],
];

/* 이 화면이 주소에 두는 상태. 기본값과 같은 값은 주소에 안 쓴다(lib/useQueryState.js).
 *
 * 예전에는 같은 값들이 `useState` 일곱 개에 있고 `useEffect` 가 그걸 주소에 베껴 쓰는
 * 구조였다. 진실이 둘이라 **브라우저 뒤로가기처럼 주소만 바뀌는 이동에서는 화면이 안
 * 따라왔다** — 사용자가 지적한 그 증상이다. 이제 주소가 유일한 진실이다. */
const DOC_SPEC = {
  q: "", doc_type: "", work_field: "", project: "", tech: "",
  sort: "recent", favorites: false, page: 1,
};
/* 필터를 건드리면 페이지는 처음으로. 예전에는 이걸 `firstRun` ref 로 흉내 냈는데,
 * 그 방식은 "복원한 page 를 지우지 않으려고 첫 렌더를 건너뛰는" 예외가 필요했다. */
const PAGE_RESET = { reset: ["page"] };

/** 서버가 받는 필터 키. 화면 상태에서 여기 있는 것만 API 로 나간다. */
const DOC_FILTER_KEYS = ["q", "doc_type", "work_field", "project", "tech"];

function SyncBanner({ sync, canSync, onSync, syncing }) {
  if (!sync) return null;
  const last = sync.last_success_at ? fmtDateTime(sync.last_success_at) : "없음";
  const tone = sync.status === "error" ? "warn" : "info";
  return (
    <Stack direction={{ xs: "column", sm: "row" }} gap={1.5} alignItems={{ sm: "center" }} sx={{ mb: 2.5 }}>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Callout tone={tone}>
          마지막 동기화: {last}, 문서 {sync.doc_count}개
          {sync.status === "error" ? ", 최근 동기화 실패(마지막 정상 데이터 표시 중)" : ""}
        </Callout>
      </Box>
      {canSync ? (
        <Button size="sm" onClick={onSync} disabled={syncing}>
          {syncing ? "동기화 중" : "지금 동기화"}
        </Button>
      ) : null}
    </Stack>
  );
}

const EMPTY_DOC = { title: "", doc_type: "", work_field: "", project: "", tech: [], status: "", priority: "", memo: "", body: "" };

/* 선택 필드 — 렌더 함수 **밖**에 둔다. 예전에는 컴포넌트 본문 안에서 정의해서, 부모가 다시
 * 그려질 때마다 React가 '다른 타입'으로 보고 select를 통째로 새로 마운트했다(포커스·열린
 * 드롭다운이 매번 날아갔다). */
function DocSelect({ id, label, value, onChange, values, required }) {
  return (
    <TextField
      id={id}
      select
      size="small"
      fullWidth
      label={label}
      required={!!required}
      value={value}
      onChange={onChange}
    >
      <MenuItem value="">선택 안 함</MenuItem>
      {(values || []).map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
    </TextField>
  );
}

function DocCreateModal({ open, onClose, options, onCreated }) {
  const toast = useToast();
  const [f, setF] = useState(EMPTY_DOC);
  useEffect(() => { if (open) setF(EMPTY_DOC); }, [open]);
  const set = (k) => (e) => setF((prev) => ({ ...prev, [k]: e.target.value }));
  const opts = options || { doc_types: [], work_fields: [], tech_tags: [], projects: [] };
  const toggleTech = (t) =>
    setF((prev) => ({ ...prev, tech: prev.tech.includes(t) ? prev.tech.filter((x) => x !== t) : [...prev.tech, t] }));

  // 프로젝트 선택지는 Notion 전체 프로젝트(문서 유무 무관, 사용자 피드백). 실패 시 필터 프로젝트로 폴백.
  const projectsQ = useQuery({
    queryKey: ["team-docs-all-projects"],
    queryFn: () => api("/api/team-docs/projects"),
    enabled: open,
  });
  const projectOptions = (projectsQ.data && projectsQ.data.projects) || opts.projects || [];

  const create = useMutation({
    mutationFn: () => api("/api/team-docs", {
      method: "POST",
      body: {
        title: f.title,
        document_type: f.doc_type || null,
        work_field: f.work_field || null,
        tech_tags: f.tech,
        project: f.project || null,
        status: f.status || null,
        priority: f.priority || null,
        memo: f.memo,
        body: f.body,
      },
    }),
    onSuccess: (res) => { toast("문서를 생성했습니다.", "success"); onCreated && onCreated(res.document); },
    onError: (e) => toast((e && e.message) || "문서 생성에 실패했습니다.", "error"),
  });

  // 필수(§9): 제목·문서 종류·업무 분야.
  const canSave = f.title.trim().length > 0 && !!f.doc_type && !!f.work_field && !create.isPending;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="새 문서"
      size="lg"
      footer={<ModalFooter onCancel={onClose} onSubmit={() => canSave && create.mutate()} submitLabel="생성" busy={create.isPending} />}
    >
      <TextField
        id="doc-title" size="small" fullWidth required label="제목"
        inputProps={{ maxLength: 200 }} value={f.title} onChange={set("title")}
      />
      {/* 표시 순서: 문서 종류 → 업무 분야 → 프로젝트 → 기술 태그 (§8). 문서 종류·업무 분야 필수. */}
      <Box sx={{ display: "grid", gap: 2.5, mt: 2.5, gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))" } }}>
        <DocSelect id="doc-type" label="문서 종류" value={f.doc_type} onChange={set("doc_type")} values={opts.doc_types} required />
        <DocSelect id="doc-field" label="업무 분야" value={f.work_field} onChange={set("work_field")} values={opts.work_fields} required />
        <DocSelect id="doc-proj" label="프로젝트" value={f.project} onChange={set("project")} values={projectOptions} />
        <DocSelect id="doc-status" label="상태" value={f.status} onChange={set("status")} values={STATUSES} />
        <DocSelect id="doc-priority" label="우선순위" value={f.priority} onChange={set("priority")} values={PRIORITIES} />
      </Box>
      <Box sx={{ mt: 2.5 }}>
        <Typography variant="body2" color="text.secondary" component="div" id="doc-tech-label" sx={{ mb: 1 }}>기술 태그</Typography>
        <Box role="group" aria-labelledby="doc-tech-label" sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          {(opts.tech_tags || []).map((t) => (
            <Chip
              key={t}
              component="button" type="button" clickable size="small" label={t}
              aria-pressed={f.tech.includes(t)}
              color={f.tech.includes(t) ? "primary" : "default"}
              variant={f.tech.includes(t) ? "filled" : "outlined"}
              onClick={() => toggleTech(t)}
            />
          ))}
        </Box>
      </Box>
      <TextField
        id="doc-memo" size="small" fullWidth multiline minRows={2} label="메모"
        value={f.memo} onChange={set("memo")} sx={{ mt: 2.5 }}
      />
      <Box sx={{ mt: 2.5 }}>
        <Typography component="label" htmlFor="doc-body" variant="body2" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          본문
        </Typography>
        <BodyEditor
          id="doc-body"
          value={f.body}
          onChange={(v) => setF((prev) => ({ ...prev, body: v }))}
          rows={12}
          placeholder="본문을 입력하세요. 위 도구는 줄 맨 앞에 서식 표시(##, -, 1., ---)를 붙입니다. 아래 미리보기에서 실제 문서 모양을 확인하세요."
        />
      </Box>
    </Modal>
  );
}

/* 목록 필터의 선택 상자 — DocSelect와 같은 이유로 모듈 최상위에 둔다(렌더마다 재마운트 방지). */
function FilterSelect({ label, value, onChange, values }) {
  return (
    <TextField
      select size="small" label={label} value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <MenuItem value="">{label} 전체</MenuItem>
      {(values || []).map((v) => <MenuItem key={v} value={v}>{v}</MenuItem>)}
    </TextField>
  );
}

export function TeamDocs() {
  const confirm = useConfirm();
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  // 필터/검색/정렬/페이지는 URL 쿼리가 든다 — 문서 상세를 보고 뒤로 오면 그대로 복원되도록
  // (사용자 피드백: 뒤로 오면 필터가 풀림). 티켓 목록 화면들과 같은 훅을 쓴다.
  const [query, setQuery] = useQueryState(DOC_SPEC, PAGE_RESET);
  const { q, doc_type: docType, work_field: workField, project, tech, sort, favorites, page } = query;
  const setPage = (p) => setQuery({ page: p });
  /* 검색어 확정은 `SearchBox` 가 디바운스해서 부른다. **참조가 고정**돼야 한다 — 매 렌더마다
     새로 만들면 `React.memo` 가 깨져 글자마다 이 화면(카드 20장)이 다시 그려진다. */
  const commitSearch = React.useCallback((next) => setQuery({ q: next }), [setQuery]);
  /* 보기(카드/표). 기본은 **카드** — 기준 목업이 카드 격자이고, 문서는 훑어보며 고르는
     화면이다. 고른 보기는 기억한다: 표로 일하는 사람이 화면을 옮길 때마다 다시 바꾸게
     하면 그건 선택지가 아니라 잔소리다. */
  const [view, setView] = useState(() => {
    try { return window.localStorage.getItem("team-docs-view") === "table" ? "table" : "cards"; }
    catch (e) { return "cards"; }
  });
  const changeView = (next) => {
    setView(next);
    try { window.localStorage.setItem("team-docs-view", next); } catch (e) { /* ignore */ }
  };
  const [composing, setComposing] = useState(false);
  const sel = useRowSelection();

  const filters = useQuery({ queryKey: ["team-docs-filters"], queryFn: () => api("/api/team-docs/filters") });

  /* 화면 상태 → 서버 질의. 주소의 표기와 API 의 표기가 한 군데(favorites)에서 다르다:
     주소는 `1`, API 는 `true` 다. 옮겨 적는 자리를 하나로 모아 둔다. */
  const params = new URLSearchParams();
  for (const key of DOC_FILTER_KEYS) { if (query[key]) params.set(key, query[key]); }
  if (favorites) params.set("favorites", "true");
  params.set("sort", sort);
  params.set("page", String(page));
  const qs = params.toString();
  const list = useQuery({
    queryKey: ["team-docs", qs],
    queryFn: () => api("/api/team-docs?" + qs),
    // 필터/페이지가 바뀌어도 이전 결과를 유지해 표가 통째로 스켈레톤으로 깜빡이지 않게 한다
    // (레포 관례: DataScreen/Users/NotificationBell도 동일).
    placeholderData: keepPreviousData,
  });

  // 보이는 문서 집합이 바뀌면(검색·필터·페이지) 선택을 비운다 — 숨겨진 문서가 선택된 채 남지 않게.
  useEffect(() => { sel.clear(); }, [qs]); // eslint-disable-line react-hooks/exhaustive-deps

  const bulkTrash = useMutation({
    mutationFn: (ids) => api("/api/team-docs/trash-bulk", { method: "POST", body: { page_ids: ids } }),
    onSuccess: (res) => {
      const n = (res.trashed || []).length;
      const f = (res.failed || []).length;
      toast(f ? `${n}건을 휴지통으로 옮겼습니다. ${f}건은 권한이 없어 건너뛰었습니다.` : `${n}건을 휴지통으로 옮겼습니다.`, f ? "info" : "success");
      qc.invalidateQueries({ queryKey: ["team-docs"], refetchType: "all" });
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      sel.clear();
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
  });

  const sync = useMutation({
    mutationFn: () => api("/api/team-docs/sync", { method: "POST" }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["team-docs"] });
      qc.invalidateQueries({ queryKey: ["team-docs-filters"] });
      const st = res && res.sync;
      if (st && st.status === "error") toast("동기화 실패: " + (st.error || "Notion 연결 확인 필요"), "error");
      else toast("동기화했습니다. 문서 " + (st ? st.doc_count : 0) + "개.", "success");
    },
    onError: (e) => toast((e && e.message) || "동기화하지 못했습니다.", "error"),
  });

  const opts = filters.data || { doc_types: [], work_fields: [], tech_tags: [], projects: [] };

  const columns = [
    {
      key: "title", label: "제목",
      // 제목(이름)을 눌러야 상세로 간다(행 전체 클릭 없음 — 체크박스 오클릭 방지).
      render: (d) => (
        <Link
          component="button" type="button" underline="hover" color="inherit"
          onClick={() => nav("/team-docs/" + d.id)}
          sx={{
            display: "inline-flex", alignItems: "center", gap: 0.75, minWidth: 0, maxWidth: "100%",
            font: "inherit", fontWeight: 600, textAlign: "left",
            "&:hover": { color: "primary.main" },
          }}
        >
          {d.is_favorite ? <Box component="span" aria-label="즐겨찾기" sx={{ color: "warning.main", flexShrink: 0 }}>★</Box> : null}
          <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>{d.title || "제목 없음"}</Box>
        </Link>
      ),
    },
    { key: "document_type", label: "문서 종류", width: "12%", render: (d) => (d.document_type ? <Badge value={d.document_type} kind={docTypeKind(d.document_type)} /> : "-") },
    { key: "work_field", label: "업무 분야", width: "13%", render: (d) => d.work_field || "-" },
    { key: "tech_tags", label: "기술 태그", width: "13%", render: (d) => (d.tech_tags || []).join(", ") || "-" },
    { key: "projects", label: "프로젝트", width: "10%", render: (d) => (d.projects || []).join(", ") || "-" },
    { key: "author", label: "작성자", width: "13%", render: (d) => (d.author_names || []).join(", ") || d.owner || "-" },
    { key: "last_edited", label: "수정", align: "right", width: "15%", render: (d) => (d.last_edited ? fmtDateTime(d.last_edited) : "-") },
  ];

  const items = (list.data && list.data.items) || [];
  // 선택 열에도 폭을 준다 — table-layout:fixed에서 폭 없는 열은 남는 공간을 균등 분배받는다.
  // 폭을 안 주면 체크박스 한 칸이 제목과 같은 폭(둘 다 '나머지의 절반')을 먹었다.
  const selCol = { ...selectionColumn(sel, items.map((d) => d.id)), width: "3.5rem" };
  const hasFilter = DOC_FILTER_KEYS.some((key) => !!query[key]) || favorites;
  // 한 번에 지운다. 예전에는 setter 일곱 개를 줄줄이 불렀는데, 그러면 새 필터를 넣을 때마다
  // 여기 한 줄을 같이 고쳐야 하고 안 고치면 '지우기'가 그 필터만 남긴다.
  const clearFilters = () => setQuery({ q: "", doc_type: "", work_field: "", project: "", tech: "", favorites: false });
  const neverSynced = !(list.data && list.data.sync && list.data.sync.last_success_at);

  return (
    <div className="c-screen">
      <PageHeader
        area={null}
        title="문서"
        spot="docs"
        actions={<>
          <BulkActions count={sel.selected.size} onClear={sel.clear}>
            <Button size="sm" variant="danger" disabled={bulkTrash.isPending}
              /* 문서는 **Notion 원본이 보관기간 뒤 삭제되는** 작업이다 (E1) — 되돌릴 수 있는 창이
                 있다는 것과 그 창이 닫히면 사라진다는 것을 둘 다 말한다. */
              onClick={async () => {
                const n = sel.selected.size;
                if (!(await confirm(
                  `문서 ${n}건을 휴지통으로 보냅니다. 보관기간이 지나면 Notion 원본도 삭제됩니다.`,
                  { danger: true, title: "선택 삭제", confirmLabel: `${n}건 삭제` }))) return;
                bulkTrash.mutate([...sel.selected]);
              }}>선택 삭제</Button>
          </BulkActions>
          <Button variant="primary" onClick={() => setComposing(true)}>새 문서</Button>
        </>}
      />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: PROSE_MAX_WIDTH }}>
        Notion 팀 문서를 검색하고 새 문서를 만들 수 있습니다.
      </Typography>

      <SyncBanner
        sync={list.data && list.data.sync}
        canSync={list.data && list.data.can_sync}
        onSync={() => sync.mutate()}
        syncing={sync.isPending}
      />

      {/* 필터가 일곱 개라 한 줄에 밀어 넣지 않고 자동 줄바꿈 그리드로 둔다(DataScreen과 같은 규칙).
       * 화면이 넓어지면 열이 늘어 한 줄에 담긴다 — 4K에서 필터 바가 세 줄로 접히지 않게. */}
      <Card className="c-toolbar-card" sx={{ p: 2, mb: 2.5 }}>
        <Box sx={{
          display: "grid", gap: 1.5, alignItems: "center",
          gridTemplateColumns: {
            xs: "1fr",
            sm: "repeat(auto-fit, minmax(11rem, 1fr))",
            xxl: "repeat(auto-fit, minmax(13rem, 1fr))",
          },
        }}>
          <SearchBox
            value={q}
            onSearch={commitSearch}
            placeholder="제목, 메모, 작성자 검색"
            ariaLabel="검색"
          />
          <FilterSelect label="문서 종류" value={docType} onChange={(v) => setQuery({ doc_type: v })} values={opts.doc_types} />
          <FilterSelect label="업무 분야" value={workField} onChange={(v) => setQuery({ work_field: v })} values={opts.work_fields} />
          <FilterSelect label="프로젝트" value={project} onChange={(v) => setQuery({ project: v })} values={opts.projects} />
          <FilterSelect label="기술 태그" value={tech} onChange={(v) => setQuery({ tech: v })} values={opts.tech_tags} />
          <TextField
            select size="small" label="정렬" value={sort}
            onChange={(e) => setQuery({ sort: e.target.value })}
          >
            {SORTS.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
          </TextField>
          <Chip
            component="button" type="button" clickable label="★ 즐겨찾기"
            aria-pressed={favorites}
            color={favorites ? "primary" : "default"}
            variant={favorites ? "filled" : "outlined"}
            onClick={() => setQuery({ favorites: !favorites })}
            sx={{ justifySelf: "start" }}
          />
          {hasFilter ? <Button size="sm" onClick={clearFilters}>필터 지우기</Button> : null}
        </Box>
        {/* 보기 전환. 필터 줄 안이 아니라 그 아래 오른쪽에 둔다 — 필터는 '무엇을 볼지',
            이건 '어떻게 볼지'다. 섞으면 필터를 하나 더 건 것처럼 읽힌다. */}
        <Box role="group" aria-label="목록 보기 방식"
          sx={{ display: "flex", justifyContent: "flex-end", gap: 0.5, mt: 1.5 }}>
          {[["cards", "카드"], ["table", "표"]].map(([v, label]) => (
            <Button
              key={v} size="sm"
              variant={view === v ? "primary" : "default"}
              aria-pressed={view === v}
              onClick={() => changeView(v)}
            >
              {label}
            </Button>
          ))}
        </Box>
      </Card>

      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.isPending ? (
        <Card><Skeleton lines={6} /></Card>
      ) : items.length === 0 ? (
        // 세 갈래를 구분한다: 아직 한 번도 동기화 안 됨 / 필터가 걸려 결과 없음 / 진짜로 비어 있음.
        // 예전엔 앞의 둘만 나뉘어 있어, 필터를 걸어 0건이 된 사용자에게도 '동기화하세요'만 떴다.
        neverSynced ? (
          <EmptyState
            art="docs"
            title="문서가 없습니다"
            help="아직 동기화되지 않았습니다. 운영자가 '지금 동기화'를 눌러 Notion 문서를 불러올 수 있습니다."
          />
        ) : hasFilter ? (
          <EmptyState
            art="search"
            title="검색 결과가 없습니다"
            help="조건에 맞는 문서가 없습니다. 검색어나 필터를 지워 보세요."
            action={<Button variant="primary" onClick={clearFilters}>필터 지우기</Button>}
          />
        ) : (
          <EmptyState
            art="docs"
            title="문서가 없습니다"
            help="위 ‘새 문서’로 첫 문서를 만들면 Notion 팀 문서에 함께 반영됩니다."
            action={<Button variant="primary" onClick={() => setComposing(true)}>새 문서</Button>}
          />
        )
      ) : (
        view === "cards" ? (
          <>
            {/* 기준 목업과 같은 3열 격자. 좁아지면 2열 → 1열로 접힌다. */}
            <Box sx={{
              display: "grid", gap: 2.25,
              gridTemplateColumns: {
                xs: "1fr", sm: "repeat(2, minmax(0, 1fr))", lg: "repeat(3, minmax(0, 1fr))",
                xxl: "repeat(4, minmax(0, 1fr))",
              },
            }}>
              {items.map((d) => (
                <DocCard
                  key={d.id} doc={d}
                  selected={sel.selected.has(d.id)}
                  onToggle={() => sel.toggle(d.id)}
                  onOpen={() => nav("/team-docs/" + d.id)}
                />
              ))}
            </Box>
            <Pager page={list.data.page} pageSize={list.data.page_size}
              total={list.data.total} onPage={setPage} />
          </>
        ) : (
          <Card className="c-list-card">
            <DataTable
              columns={[selCol, ...columns]}
              fixed ellipsis
              rows={items}
              rowKey={(d) => d.id}
            />
            <Pager
              page={list.data.page}
              pageSize={list.data.page_size}
              total={list.data.total}
              onPage={setPage}
            />
          </Card>
        )
      )}

      <DocCreateModal
        open={composing}
        onClose={() => setComposing(false)}
        options={filters.data}
        onCreated={(doc) => {
          setComposing(false);
          qc.invalidateQueries({ queryKey: ["team-docs"] });
          qc.invalidateQueries({ queryKey: ["team-docs-filters"] });
          if (doc && doc.id) nav("/team-docs/" + doc.id);
        }}
      />
    </div>
  );
}

/* 문서 카드 — 기준 목업의 문서 격자와 같은 구조: 분류 칩 → 제목 → 요약 → 작성자·수정일.
 *
 * 왜 카드인가: 문서는 **훑어보며 고르는** 화면이다. 표는 열 일곱 개를 같은 무게로 늘어놓아
 * "무엇에 관한 문서인지" 가 제목 한 칸에만 담긴다. 카드는 분류를 먼저 보여 주고 제목에
 * 공간을 준다(기준 목업이 그렇게 하고, 사용자가 그 화면을 기준으로 지목했다).
 *
 * 표를 없애지는 않는다 — 실제 문서가 **104건**이라 한 번에 훑거나 여러 건을 골라 지우는
 * 일이 실재한다. 보기 전환을 둔다(카드가 기본). 계획서가 "관리자 대량 목록은 표 유지" 로
 * 갈랐는데, 문서는 사용자 화면이면서 대량이라 **둘 다 필요한 유일한 화면**이다. */
function DocCard({ doc, selected, onToggle, onOpen }) {
  const tags = [...(doc.tech_tags || []), ...(doc.projects || [])].filter(Boolean);
  const author = (doc.author_names || []).join(", ") || doc.owner || "";
  return (
    <Card
      sx={{
        display: "grid", gridTemplateRows: "auto auto 1fr auto", gap: 1, p: 2.25,
        outline: selected ? 2 : 0, outlineColor: "primary.main", outlineOffset: "-2px",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
        {doc.document_type ? <Badge value={doc.document_type} kind={docTypeKind(doc.document_type)} /> : null}
        {doc.work_field ? <Badge value={doc.work_field} kind="neutral" /> : null}
        <Box sx={{ flex: 1 }} />
        {/* 여러 건 고르기는 카드에서도 된다 — 보기를 바꿨다고 할 수 있던 일이 사라지면
            그건 개선이 아니라 기능 축소다. */}
        <Box
          component="input" type="checkbox" checked={selected} onChange={onToggle}
          aria-label={`${doc.title || "제목 없음"} 선택`}
          sx={{ m: 0, cursor: "pointer", flexShrink: 0 }}
        />
      </Box>
      <Link
        component="button" type="button" underline="hover" color="inherit" onClick={onOpen}
        sx={{
          display: "flex", alignItems: "flex-start", gap: 0.75, font: "inherit",
          fontWeight: 700, fontSize: "1rem", lineHeight: 1.4, textAlign: "left",
          "&:hover": { color: "primary.main" },
        }}
      >
        {doc.is_favorite ? <Box component="span" aria-label="즐겨찾기" sx={{ color: "warning.main" }}>★</Box> : null}
        <Box component="span">{doc.title || "제목 없음"}</Box>
      </Link>
      <Typography
        variant="body2" color="text.secondary"
        sx={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}
      >
        {tags.length ? tags.join(", ") : "분류 정보가 없습니다."}
      </Typography>
      <Box sx={{
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1,
        pt: 1, borderTop: 1, borderColor: "divider",
        fontSize: "0.8125rem", color: "text.secondary",
      }}>
        <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {author || "작성자 없음"}
        </Box>
        <Box component="span" sx={{ flexShrink: 0 }}>{doc.last_edited ? fmtDateTime(doc.last_edited) : "-"}</Box>
      </Box>
    </Card>
  );
}
