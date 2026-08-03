import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import InputAdornment from "@mui/material/InputAdornment";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
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
  useToast,
} from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { docTypeKind } from "../lib/badges.js";
import { BodyEditor } from "../ui/BodyEditor.jsx";
import { useRowSelection, selectionColumn, BulkActions } from "../ui/bulkSelect.jsx";

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

function useDebounced(value, ms) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

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
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  // 필터/검색/정렬/페이지 상태는 URL 쿼리에 저장한다 — 문서 상세를 보고 뒤로 오면 그대로
  // 복원되도록(사용자 피드백: 뒤로 오면 필터가 풀림). 초기값은 URL에서 읽는다.
  const [sp, setSp] = useSearchParams();
  const [docType, setDocType] = useState(() => sp.get("doc_type") || "");
  const [workField, setWorkField] = useState(() => sp.get("work_field") || "");
  const [project, setProject] = useState(() => sp.get("project") || "");
  const [tech, setTech] = useState(() => sp.get("tech") || "");
  const [sort, setSort] = useState(() => sp.get("sort") || "recent");
  const [favorites, setFavorites] = useState(() => sp.get("favorites") === "1");
  const [qInput, setQInput] = useState(() => sp.get("q") || "");
  const q = useDebounced(qInput, 300);
  const [page, setPage] = useState(() => Number(sp.get("page")) || 1);
  const [composing, setComposing] = useState(false);
  const sel = useRowSelection();

  // 필터/검색/정렬이 바뀌면 1페이지로 되돌린다(다른 필터의 3페이지에 머무르지 않게). 단 첫
  // 렌더(=URL에서 복원)는 건너뛴다 — 복원한 page를 지우지 않기 위함.
  const firstRun = useRef(true);
  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return; }
    setPage(1);
  }, [q, docType, workField, project, tech, sort, favorites]);

  // 현재 필터 상태를 URL에 반영(replace — 키 입력마다 히스토리가 쌓이지 않게). 상세로 이동 전
  // 마지막 URL이 이 필터를 담고 있어, 뒤로 오면 그대로 복원된다.
  useEffect(() => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (docType) p.set("doc_type", docType);
    if (workField) p.set("work_field", workField);
    if (project) p.set("project", project);
    if (tech) p.set("tech", tech);
    if (favorites) p.set("favorites", "1");
    if (sort && sort !== "recent") p.set("sort", sort);
    if (page > 1) p.set("page", String(page));
    setSp(p, { replace: true });
  }, [q, docType, workField, project, tech, favorites, sort, page, setSp]);

  const filters = useQuery({ queryKey: ["team-docs-filters"], queryFn: () => api("/api/team-docs/filters") });

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (docType) params.set("doc_type", docType);
  if (workField) params.set("work_field", workField);
  if (project) params.set("project", project);
  if (tech) params.set("tech", tech);
  if (favorites) params.set("favorites", "true");
  params.set("sort", sort);
  params.set("page", String(page));
  const list = useQuery({
    queryKey: ["team-docs", q, docType, workField, project, tech, sort, favorites, page],
    queryFn: () => api("/api/team-docs?" + params.toString()),
    // 필터/페이지가 바뀌어도 이전 결과를 유지해 표가 통째로 스켈레톤으로 깜빡이지 않게 한다
    // (레포 관례: DataScreen/Users/NotificationBell도 동일).
    placeholderData: keepPreviousData,
  });

  // 보이는 문서 집합이 바뀌면(검색·필터·페이지) 선택을 비운다 — 숨겨진 문서가 선택된 채 남지 않게.
  useEffect(() => { sel.clear(); }, [q, docType, workField, project, tech, sort, favorites, page]); // eslint-disable-line react-hooks/exhaustive-deps

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
  const hasFilter = !!(q || docType || workField || project || tech || favorites);
  const clearFilters = () => {
    setQInput(""); setDocType(""); setWorkField(""); setProject(""); setTech(""); setFavorites(false); setPage(1);
  };
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
              onClick={() => bulkTrash.mutate([...sel.selected])}>선택 삭제</Button>
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
          <TextField
            type="search"
            size="small"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder="제목, 메모, 작성자 검색"
            inputProps={{ "aria-label": "검색" }}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchRoundedIcon fontSize="small" /></InputAdornment> }}
            sx={{ gridColumn: { sm: "span 2" } }}
          />
          <FilterSelect label="문서 종류" value={docType} onChange={setDocType} values={opts.doc_types} />
          <FilterSelect label="업무 분야" value={workField} onChange={setWorkField} values={opts.work_fields} />
          <FilterSelect label="프로젝트" value={project} onChange={setProject} values={opts.projects} />
          <FilterSelect label="기술 태그" value={tech} onChange={setTech} values={opts.tech_tags} />
          <TextField
            select size="small" label="정렬" value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            {SORTS.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
          </TextField>
          <Chip
            component="button" type="button" clickable label="★ 즐겨찾기"
            aria-pressed={favorites}
            color={favorites ? "primary" : "default"}
            variant={favorites ? "filled" : "outlined"}
            onClick={() => setFavorites((v) => !v)}
            sx={{ justifySelf: "start" }}
          />
          {hasFilter ? <Button size="sm" onClick={clearFilters}>필터 지우기</Button> : null}
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

function Pager({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil((total || 0) / (pageSize || 20)));
  if (pages <= 1) return null;
  return (
    <Box component="nav" aria-label="페이지 이동"
      sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 2, pt: 2, mt: 1, borderTop: 1, borderColor: "divider" }}>
      <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>이전</Button>
      <Typography variant="body2" color="text.secondary" aria-live="polite" sx={{ minWidth: "8rem", textAlign: "center" }}>
        {page} / {pages}{total != null ? `, 총 ${total}건` : ""}
      </Typography>
      <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>다음</Button>
    </Box>
  );
}
