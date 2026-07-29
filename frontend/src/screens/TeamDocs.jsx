import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Callout,
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
import { docTypeKind } from "../lib/badges.js";
import { BodyEditor } from "../ui/BodyEditor.jsx";

const PRIORITIES = ["높음", "보통", "낮음"];
const STATUSES = ["초안", "활성", "서명됨", "만료됨"];

/* 팀 공간 > 문서 목록 (§17). Notion "문서" DB의 로컬 캐시를 읽는다 — Notion이 느리거나 죽어도
 * 마지막 정상 동기화 목록이 그대로 뜬다(장애 격리). 본문/원본은 상세에서 본다. */

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
    <div className="docs-sync">
      <Callout tone={tone}>
        마지막 동기화: {last}, 문서 {sync.doc_count}개
        {sync.status === "error" ? ", 최근 동기화 실패(마지막 정상 데이터 표시 중)" : ""}
      </Callout>
      {canSync ? (
        <Button size="sm" onClick={onSync} disabled={syncing}>
          {syncing ? "동기화 중" : "지금 동기화"}
        </Button>
      ) : null}
    </div>
  );
}

const EMPTY_DOC = { title: "", doc_type: "", work_field: "", project: "", tech: [], status: "", priority: "", memo: "", body: "" };

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
  const Select = ({ id, label, k, values, req }) => (
    <div className="k-field">
      <label className="k-field-label" htmlFor={id}>{label}{req ? <span className="k-req"> *</span> : null}</label>
      <select id={id} className="k-input" value={f[k]} onChange={set(k)}>
        <option value="">선택 안 함</option>
        {values.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
    </div>
  );

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="새 문서"
      size="lg"
      footer={<ModalFooter onCancel={onClose} onSubmit={() => canSave && create.mutate()} submitLabel="생성" busy={create.isPending} />}
    >
      <div className="k-field">
        <label className="k-field-label" htmlFor="doc-title">제목<span className="k-req"> *</span></label>
        <input id="doc-title" className="k-input" maxLength={200} value={f.title} onChange={set("title")} />
      </div>
      {/* 표시 순서: 문서 종류 → 업무 분야 → 프로젝트 → 기술 태그 (§8). 문서 종류·업무 분야 필수. */}
      <Select id="doc-type" label="문서 종류" k="doc_type" values={opts.doc_types} req />
      <Select id="doc-field" label="업무 분야" k="work_field" values={opts.work_fields} req />
      <Select id="doc-proj" label="프로젝트" k="project" values={projectOptions} />
      <div className="k-field">
        <label className="k-field-label">기술 태그</label>
        <div className="docs-tag-picker" role="group" aria-label="기술 태그">
          {(opts.tech_tags || []).map((t) => (
            <button
              type="button"
              key={t}
              className={"docs-tag-chip" + (f.tech.includes(t) ? " is-on" : "")}
              aria-pressed={f.tech.includes(t)}
              onClick={() => toggleTech(t)}
            >{t}</button>
          ))}
        </div>
      </div>
      <Select id="doc-status" label="상태" k="status" values={STATUSES} />
      <Select id="doc-priority" label="우선순위" k="priority" values={PRIORITIES} />
      <div className="k-field">
        <label className="k-field-label" htmlFor="doc-memo">메모</label>
        <textarea id="doc-memo" className="k-input" rows={2} value={f.memo} onChange={set("memo")} />
      </div>
      <div className="k-field">
        <label className="k-field-label" htmlFor="doc-body">본문</label>
        <BodyEditor
          id="doc-body"
          value={f.body}
          onChange={(v) => setF((prev) => ({ ...prev, body: v }))}
          rows={12}
          placeholder="본문을 입력하세요. 위 도구는 줄 맨 앞에 서식 표시(##, -, 1., ---)를 붙입니다. 아래 미리보기에서 실제 문서 모양을 확인하세요."
        />
      </div>
    </Modal>
  );
}

/* 본문 미리보기 — body_children(백엔드)과 같은 규칙으로 마크다운 표식을 렌더해 실제 문서 모양을
 * 보여준다. 연속한 글머리/번호는 한 목록으로 묶는다. 서버 데이터가 아닌 사용자 입력이므로 React가
 * 기본으로 textContent 렌더(불변 §6 XSS 없음). */
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
      render: (d) => (
        <span className="docs-title-cell">
          {d.is_favorite ? <span className="docs-star" aria-label="즐겨찾기">★</span> : null}
          <span className="docs-title-text">{d.title || "제목 없음"}</span>
        </span>
      ),
    },
    { key: "document_type", label: "문서 종류", render: (d) => (d.document_type ? <Badge value={d.document_type} kind={docTypeKind(d.document_type)} /> : "-") },
    { key: "work_field", label: "업무 분야", render: (d) => d.work_field || "-" },
    { key: "tech_tags", label: "기술 태그", render: (d) => (d.tech_tags || []).join(", ") || "-" },
    { key: "projects", label: "프로젝트", render: (d) => (d.projects || []).join(", ") || "-" },
    { key: "author", label: "작성자", render: (d) => (d.author_names || []).join(", ") || d.owner || "-" },
    { key: "last_edited", label: "수정", align: "right", render: (d) => (d.last_edited ? fmtDateTime(d.last_edited) : "-") },
  ];

  const Selector = ({ label, value, onChange, values }) => (
    <select className="k-input docs-filter" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}>
      <option value="">{label} 전체</option>
      {values.map((v) => <option key={v} value={v}>{v}</option>)}
    </select>
  );

  return (
    <div className="c-screen">
      <PageHeader
        area={null}
        title="문서"
        actions={<Button variant="primary" onClick={() => setComposing(true)}>새 문서</Button>}
      />
      <p className="k-page-help">Notion 팀 문서를 검색하고 새 문서를 만들 수 있습니다.</p>

      <SyncBanner
        sync={list.data && list.data.sync}
        canSync={list.data && list.data.can_sync}
        onSync={() => sync.mutate()}
        syncing={sync.isPending}
      />

      <div className="docs-filters">
        <input
          className="k-input docs-search"
          type="search"
          placeholder="제목, 메모, 작성자 검색"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          aria-label="검색"
        />
        <Selector label="문서 종류" value={docType} onChange={setDocType} values={opts.doc_types} />
        <Selector label="업무 분야" value={workField} onChange={setWorkField} values={opts.work_fields} />
        <Selector label="프로젝트" value={project} onChange={setProject} values={opts.projects} />
        <Selector label="기술 태그" value={tech} onChange={setTech} values={opts.tech_tags} />
        <select className="k-input docs-filter" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="정렬">
          {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <button
          type="button"
          className={"docs-fav-toggle" + (favorites ? " is-on" : "")}
          onClick={() => setFavorites((v) => !v)}
          aria-pressed={favorites}
        >★ 즐겨찾기</button>
      </div>

      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.isPending ? (
        <Skeleton lines={6} />
      ) : (list.data.items || []).length === 0 ? (
        <EmptyState
          title="문서가 없습니다"
          help={
            list.data.sync && list.data.sync.last_success_at
              ? "조건에 맞는 문서가 없습니다. 필터를 바꿔 보세요."
              : "아직 동기화되지 않았습니다. 운영자가 '지금 동기화'를 눌러 Notion 문서를 불러올 수 있습니다."
          }
        />
      ) : (
        <>
          <div className="docs-table">
            <DataTable
              columns={columns}
              rows={list.data.items}
              rowKey={(d) => d.id}
              onRow={(d) => nav("/team-docs/" + d.id)}
            />
          </div>
          <Pager
            page={list.data.page}
            pageSize={list.data.page_size}
            total={list.data.total}
            onPage={setPage}
          />
        </>
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
    <div className="docs-pager">
      <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>이전</Button>
      <span className="docs-pager-info">{page} / {pages}</span>
      <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>다음</Button>
    </div>
  );
}
