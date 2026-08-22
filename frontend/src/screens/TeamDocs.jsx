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
  OverflowMenu,
  PageHeader,
  Tag,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { bulkFailureNote, fmtDateTime } from "../lib/format.js";
import { invalidateDocumentViews } from "./document-views.js";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import StarRoundedIcon from "@mui/icons-material/StarRounded";
import { MirrorNotice } from "../ui/MirrorNotice.jsx";
import { FilterActions, FilterRow, FilterSurface, ResultLine, ToolbarEnd, ToolbarRow, TOOLBAR_SEARCH_SX } from "../ui/FilterBar.jsx";
import { BodyEditor } from "../ui/BodyEditor.jsx";
import { useRowSelection, selectionColumn, BulkActions } from "../ui/bulkSelect.jsx";
import { DepartmentFilter, EntityCombobox, FilterSelect, SearchBox } from "../ui/filters.jsx";
import { Pager } from "../ui/Pager.jsx";
import { useQueryState } from "../lib/useQueryState.js";
import { DateCell } from "../ui/cells.jsx";

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
  // 부서 필터 (0060 §32). 주소에 두는 이유는 나머지 필터와 같다 — 상세를 보고 돌아왔을 때
  // 풀리면 안 되고, 링크로 "우리 팀 문서만" 을 공유할 수 있어야 한다.
  dept: "",
  sort: "recent", favorites: false, page: 1,
};
/* 필터를 건드리면 페이지는 처음으로. 예전에는 이걸 `firstRun` ref 로 흉내 냈는데,
 * 그 방식은 "복원한 page 를 지우지 않으려고 첫 렌더를 건너뛰는" 예외가 필요했다. */
const PAGE_RESET = { reset: ["page"] };

/** 서버가 받는 필터 키. 화면 상태에서 여기 있는 것만 API 로 나간다. */
const DOC_FILTER_KEYS = ["q", "doc_type", "work_field", "project", "tech"];


// 서버(app/team_docs/schemas.py::DocumentCreate)는 owner(소유자)도 받는데, 예전엔 이 폼에
// 칸이 없어 포털에서 만든 문서는 소유자를 영영 못 채웠다(문서 상세의 '소유자' 줄은 채워질
// 방법이 없는 값이었다) — 폼↔API 불일치.
const EMPTY_DOC = { title: "", doc_type: "", work_field: "", project: "", tech: [], status: "", priority: "", owner: "", memo: "", body: "" };

/* 선택 필드 — 렌더 함수 **밖**에 둔다. 예전에는 컴포넌트 본문 안에서 정의해서, 부모가 다시
 * 그려질 때마다 React가 '다른 타입'으로 보고 select를 통째로 새로 마운트했다(포커스·열린
 * 드롭다운이 매번 날아갔다). */
function DocSelect({ id, label, value, onChange, values, required }) {
  return (
    <TextField
      InputLabelProps={{ shrink: true }}
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

export function DocCreateModal({ open, onClose, options, onCreated }) {
  const toast = useToast();
  const confirm = useConfirm();
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
        owner: f.owner,
        memo: f.memo,
        body: f.body,
      },
    }),
    onSuccess: (res) => { toast("문서를 추가했습니다.", "success"); onCreated && onCreated(res.document); },
    onError: (e) => toast((e && e.message) || "문서 추가에 실패했습니다. 다시 시도해 주세요.", "error"),
  });

  // 필수(§9): 제목·문서 종류·업무 분야.
  const canSave = f.title.trim().length > 0 && !!f.doc_type && !!f.work_field && !create.isPending;

  // 뭔가 입력했으면 Esc·바깥 클릭·X·'취소' 전부에서 확인을 받는다(VIS-88) — 이 폼은 필드가
  // 많아(제목·종류·분야·프로젝트·태그·소유자·메모·본문) 실수로 닫으면 다시 채워야 할 양이 크다.
  // `Modal`의 `dirty` prop은 Esc/바깥클릭/X만 지킨다 — 하단 '취소' 버튼은 onClose를 직접
  // 불러 그 가드를 우회하므로(Games.jsx가 이미 겪은 문제) 여기서도 requestClose로 감싼다.
  const dirty = JSON.stringify(f) !== JSON.stringify(EMPTY_DOC);
  async function requestClose() {
    if (!dirty) { onClose(); return; }
    const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?",
      { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
    if (ok) onClose();
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="새 문서"
      size="lg"
      dirty={dirty}
      footer={<ModalFooter onCancel={requestClose} onSubmit={() => canSave && create.mutate()} submitLabel="추가" busy={create.isPending} />}
    >
      <TextField
        InputLabelProps={{ shrink: true }}
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
        {/* 서버가 받는 owner(app/team_docs/schemas.py, 최대 200자) 칸. 문서 상세(TeamDoc.jsx
            DocMeta)는 값이 있으면 '소유자' 줄을 보여 주는데, 이 칸이 없으면 포털에서 만든
            문서는 그 값을 절대 채울 수 없었다. */}
        <TextField
          InputLabelProps={{ shrink: true }}
          id="doc-owner" size="small" fullWidth label="소유자"
          helperText="이 문서를 책임지는 사람(선택)"
          inputProps={{ maxLength: 200 }} value={f.owner} onChange={set("owner")}
        />
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
        InputLabelProps={{ shrink: true }}
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

/* 이 자리에 있던 로컬 `FilterSelect` 사본은 지웠다 (W5).
 *
 * 공용 부품(`ui/filters.jsx::FilterSelect`)과 이름도 뜻도 같았는데 **한 가지가 빠져
 * 있었다** — `EMPTYABLE_SELECT`(`displayEmpty` + 라벨 항상 위). MUI 는 값이 `""` 이면
 * "아직 아무것도 안 골랐다"로 보고 라벨을 입력 자리에 그대로 둔 채 선택 항목을 안 그린다.
 * 필터의 기본 상태가 바로 그 빈 값이라, 이 화면의 필터 넷(문서 종류·업무 분야·프로젝트·
 * 기술 태그)은 배포본에서 **라벨만 있고 값이 없는 빈 상자**로 보였다. 바로 옆 부서 필터는
 * 공용 부품이라 「내 범위 전체」가 정상으로 보였고 — 그래서 같은 줄에 라벨 처리 두 종류가
 * 서 있었다. 같은 뜻의 부품이 두 벌이면 한쪽만 고쳐지는 날이 온다는 그 실패다. */

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

  const filters = useQuery({ queryKey: ["team-docs-filters"], queryFn: () => api("/api/team-docs/filters"), retry: false });

  /* 화면 상태 → 서버 질의. 주소의 표기와 API 의 표기가 한 군데(favorites)에서 다르다:
     주소는 `1`, API 는 `true` 다. 옮겨 적는 자리를 하나로 모아 둔다. */
  const params = new URLSearchParams();
  for (const key of DOC_FILTER_KEYS) { if (query[key]) params.set(key, query[key]); }
  // 주소 키(`dept`)와 API 키(`department_id`)가 다르다 — 옮겨 적는 자리는 여기 하나다.
  if (query.dept) params.set("department_id", query.dept);
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
    // 기본 재시도(최대 3회, 지수 백오프)면 실패가 isError로 뜨기까지 ~7초 걸려 그동안
    // 스켈레톤이 "영원히 로딩 중"처럼 보인다(FAIL-03) — 다른 화면(Users/Diagnostics/
    // DataScreen)과 같은 규약으로 맞춤.
    retry: false,
  });

  // 보이는 문서 집합이 바뀌면(검색·필터·페이지) 선택을 비운다 — 숨겨진 문서가 선택된 채 남지 않게.
  useEffect(() => { sel.clear(); }, [qs]); // eslint-disable-line react-hooks/exhaustive-deps

  const bulkTrash = useMutation({
    mutationFn: (ids) => api("/api/team-docs/trash-bulk", { method: "POST", body: { page_ids: ids } }),
    onSuccess: (res) => {
      const n = (res.trashed || []).length;
      const failed = res.failed || [];
      // UA-25 — Trash.jsx와 같은 이유로 실제 사유를 보여준다(전엔 항상 "권한이 없어"였다).
      toast(`${n}건을 휴지통으로 옮겼습니다.` + bulkFailureNote(failed), failed.length ? "info" : "success");
      // document-views.js의 ["team-doc"] 접두어(id 없이)가 방금 지운 문서 각각의 상세 캐시를
      // 한 번에 잡는다 — 예전엔 이걸 몰라 매번 손으로 순회했다. home의 「최근 문서」 위젯도
      // 같이 무효화한다(L축 재감사 — 문서를 지워도 홈 탭은 안 바뀌던 것과 같은 결함 부류).
      invalidateDocumentViews(qc, { refetchType: "all" });
      sel.clear();
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const sync = useMutation({
    mutationFn: () => api("/api/team-docs/sync", { method: "POST" }),
    onSuccess: (res) => {
      invalidateDocumentViews(qc);
      qc.invalidateQueries({ queryKey: ["team-docs-filters"] });
      const st = res && res.sync;
      if (st && st.status === "error") toast("동기화 실패: " + (st.error || "Notion 연결 확인 필요"), "error");
      else toast("동기화했습니다. 문서 " + (st ? st.doc_count : 0) + "개.", "success");
    },
    onError: (e) => toast((e && e.message) || "동기화하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const opts = filters.data || { doc_types: [], work_fields: [], tech_tags: [], projects: [] };

  const columns = [
    {
      key: "title", label: "제목",
      // rowName: 문서를 구별하는 값은 제목이다(ui/rowName.js) — 선택 체크박스가 이 값을
      // 접근 이름에 쓴다. render 가 있어 표가 원시 값을 읽을 수 없으니 여기서 직접 준다.
      rowName: (d) => d.title || "제목 없음",
      // 제목(이름)을 눌러야 상세로 간다(행 전체 클릭 없음 — 체크박스 오클릭 방지).
      render: (d) => (
        <Link
          component="button" type="button" underline="hover" color="inherit"
          onClick={() => nav("/team-docs/" + d.id)}
          sx={{
            display: "inline-flex", alignItems: "center", gap: 0.75, minWidth: 0, maxWidth: "100%",
            font: "inherit", fontWeight: FONT_WEIGHT.semibold, textAlign: "left",
            // QAH-07 — dark 모드 4개 accent 전부 대비 미달(최저 2.81) 실측, primary.dark로 교체(QAH-03/05와 같은 대비 보강 토큰).
            "&:hover": { color: "primary.dark" },
          }}
        >
          {/* 예전에는 ★ 글자였다(지시 28: 장식 글리프 금지). 아이콘은 한 패밀리에서만
              가져온다 — 글자 크기·기준선에 따라 모양이 흔들리지 않는다. */}
          {d.is_favorite ? <StarRoundedIcon aria-label="즐겨찾기" role="img" sx={{ color: "warning.main", flexShrink: 0, fontSize: "1rem" }} /> : null}
          {/* SEC-10: 목록에서도 제한된 문서를 한눈에 구별한다 — 이 목록에 뜬다는 것 자체가
              이미 운영자/작성자 범위를 지났다는 뜻이므로(doc_in_scope) 값을 보여줘도 안전하다. */}
          {/* 예전에는 자물쇠 이모지였다(지시 28). 상태는 Design System 의 어휘로 말한다 —
              기능(SEC-10 열람 제한)은 그대로다. */}
          {d.restricted ? <Box sx={{ flexShrink: 0 }}><Tag label="열람 제한" tone="warn" /></Box> : null}
          <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>{d.title || "제목 없음"}</Box>
        </Link>
      ),
    },
    { key: "document_type", label: "문서 종류", width: "12%", render: (d) => (d.document_type ? <Tag label={d.document_type} /> : "-") },
    { key: "work_field", label: "업무 분야", width: "13%", render: (d) => d.work_field || "-" },
    { key: "tech_tags", label: "기술 태그", width: "13%", render: (d) => (d.tech_tags || []).join(", ") || "-" },
    { key: "projects", label: "프로젝트", width: "10%", render: (d) => (d.projects || []).join(", ") || "-" },
    { key: "author", label: "작성자", width: "13%", render: (d) => (d.author_names || []).join(", ") || d.owner || "-" },
    { key: "last_edited", label: "수정", align: "right", width: "11rem", nowrap: true, render: (d) => <DateCell value={d.last_edited} /> },
  ];

  const items = (list.data && list.data.items) || [];
  // 선택 열에도 폭을 준다 — table-layout:fixed에서 폭 없는 열은 남는 공간을 균등 분배받는다.
  // 폭을 안 주면 체크박스 한 칸이 제목과 같은 폭(둘 다 '나머지의 절반')을 먹었다.
  const selCol = { ...selectionColumn(sel, items.map((d) => d.id)), width: "3.5rem" };
  // 부서도 "걸린 필터" 다 — 빼면 "필터 지우기" 를 눌러도 목록이 그대로라 버튼이 고장 난
  // 것처럼 보인다.
  const hasFilter = DOC_FILTER_KEYS.some((key) => !!query[key]) || favorites || !!query.dept;
  /* 결과 줄이 «조건 N개» 를 말할 때 세는 것 — «필터가 걸렸는가»(hasFilter)와 같은 집합이다.
     두 목록이 갈라지면 "조건 0개인데 필터 지우기 버튼이 있다" 같은 자기모순이 생긴다. */
  const activeDocConditions = DOC_FILTER_KEYS.filter((key) => !!query[key])
    .concat(favorites ? ["favorites"] : [])
    .concat(query.dept ? ["dept"] : []);
  // 한 번에 지운다. 예전에는 setter 일곱 개를 줄줄이 불렀는데, 그러면 새 필터를 넣을 때마다
  // 여기 한 줄을 같이 고쳐야 하고 안 고치면 '지우기'가 그 필터만 남긴다.
  const clearFilters = () => setQuery({
    q: "", doc_type: "", work_field: "", project: "", tech: "", dept: "", favorites: false,
  });
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
          {/* PA-RC-0031: 사이드바에서 '휴지통' 단독 메뉴 항목을 없애고(문서 화면 안의 상태이지
              형제 메뉴가 아니었다) 이 화면 안의 진입점으로 옮긴다 — 라우트(#/team-docs/trash)
              자체는 그대로 살아 있다, 도달하는 방법만 바뀐다. */}
          <Button href="#/team-docs/trash">휴지통</Button>
          {/* 지식 공간(S7)의 입구. 사이드바 항목을 안 만든 이유는 navConfig.js 의
              ROUTE_OWNER 주석에 적었다 — 한 그룹이 여섯 항목을 넘지 않는다는 계약이
              있고, 사용자에게 이 화면과 지식 공간은 같은 종류의 일이다. 이관(S13·S14)이
              끝나면 두 화면이 실제로 하나가 된다. */}
          <Button href="#/knowledge">지식 공간</Button>
          <Button variant="primary" onClick={() => setComposing(true)}>새 문서</Button>
          {/* 수동 동기화는 운영 동작이다 — 예전에는 화면 맨 위 상시 배너 옆에서 첫 번째
              버튼 자리를 차지했다(지시 29). 기능은 그대로 두고 자리만 넘침 메뉴로 옮긴다.
              동기화가 실패했을 때는 MirrorNotice 가 복구 동작으로 다시 꺼내 준다. */}
          <OverflowMenu
            ariaLabel="문서 목록 더 보기"
            items={[
              (list.data && list.data.can_sync) ? {
                key: "sync",
                label: sync.isPending ? "동기화 중" : "지금 동기화",
                disabled: sync.isPending,
                onClick: () => sync.mutate(),
              } : null,
            ]}
          />
        </>}
      />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Notion 팀 문서를 검색하고 새 문서를 만듭니다.
      </Typography>

      <MirrorNotice
        sync={list.data && list.data.sync}
        canSync={list.data && list.data.can_sync}
        onSync={() => sync.mutate()}
        syncing={sync.isPending}
        unit="문서"
      />

      {/* 필터가 일곱 개라 한 줄에 밀어 넣지 않고 자동 줄바꿈 그리드로 둔다(DataScreen과 같은 규칙).
       * 화면이 넓어지면 열이 늘어 한 줄에 담긴다 — 4K에서 필터 바가 세 줄로 접히지 않게.
       * SEM-02(PA-F-031): h1 하나뿐이라 필터·목록이 스크린리더 제목 탐색에서 구획 없는
       * 한 덩어리였다. 시각은 그대로(.sr-only), DataScreen.jsx와 같은 패턴. */}
      <Typography component="h2" className="sr-only">필터</Typography>
      {/* 판이 아니다 — 지시 80. 윗줄은 "어떻게 볼지"(검색이 지배하고 정렬·보기가 오른쪽
          끝), 아랫줄은 "무엇을 볼지"(내용 필터). 두 줄이면 충분하고 각 줄이 한 가지
          질문만 답한다(지시 5). */}
      <FilterSurface>
        <ToolbarRow>
          <SearchBox
            value={q}
            onSearch={commitSearch}
            placeholder="제목, 메모, 작성자 검색"
            ariaLabel="검색"
            sx={TOOLBAR_SEARCH_SX}
          />
          <ToolbarEnd>
            <TextField
              select size="small" label="정렬" value={sort}
              InputLabelProps={{ shrink: true }}
              onChange={(e) => setQuery({ sort: e.target.value })}
              sx={{ minWidth: "10rem" }}
            >
              {SORTS.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}
            </TextField>
            <Box role="group" aria-label="목록 보기 방식" sx={{ display: "flex", gap: 0.5 }}>
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
          </ToolbarEnd>
        </ToolbarRow>
        {/* 순서는 C2 가 정한다: scope(부서) → entity(프로젝트) → 분류(종류·분야·태그). */}
        <FilterRow>
          {/* 부서 후보는 **이 응답이** 들고 온다(서버가 계산한 내 조회 범위). 별도 질의를
              만들지 않는 이유: 목록과 후보가 다른 시점의 범위를 말하면 고를 수는 있는데
              결과가 비는 상자가 생긴다. */}
          <DepartmentFilter
            departments={list.data && list.data.departments}
            value={query.dept}
            onChange={(v) => setQuery({ dept: v })}
          />
          {/* 프로젝트는 Entity 다 — 후보가 업무가 쌓이는 만큼 자라고 이름이 길다. */}
          <EntityCombobox
            label="프로젝트" value={project} onChange={(v) => setQuery({ project: v })}
            options={opts.projects}
          />
          <FilterSelect label="문서 종류" value={docType} onChange={(v) => setQuery({ doc_type: v })} options={opts.doc_types} />
          <FilterSelect label="업무 분야" value={workField} onChange={(v) => setQuery({ work_field: v })} options={opts.work_fields} />
          <FilterSelect label="기술 태그" value={tech} onChange={(v) => setQuery({ tech: v })} options={opts.tech_tags} />
          {/* 즐겨찾기는 내용 필터다(무엇을 볼지) — 별 글리프는 뺐다(지시 28). 켜짐/꺼짐은
              칩의 채움과 `aria-pressed` 가 이미 말한다. */}
          <Chip
            component="button" type="button" clickable label="즐겨찾기만"
            aria-pressed={favorites}
            color={favorites ? "primary" : "default"}
            variant={favorites ? "filled" : "outlined"}
            onClick={() => setQuery({ favorites: !favorites })}
          />
          {hasFilter ? (
            <FilterActions>
              <Button variant="ghost" size="sm" onClick={clearFilters}>필터 지우기</Button>
            </FilterActions>
          ) : null}
        </FilterRow>
      </FilterSurface>
      {list.data ? <ResultLine total={list.data.total != null ? list.data.total : (list.data.items || []).length} conditions={activeDocConditions} /> : null}

      <Typography component="h2" className="sr-only">목록</Typography>
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.isPending ? (
        <Card>{/* 표가 들어올 자리에는 표 모양을 그린다 (지시 20) - 빈 목록과 아직 안 온 목록은 다른 사실이다. */}<DataTable columns={columns} rows={[]} loading /></Card>
      ) : items.length === 0 ? (
        // 세 갈래를 구분한다: 아직 한 번도 동기화 안 됨 / 필터가 걸려 결과 없음 / 진짜로 비어 있음.
        // 예전엔 앞의 둘만 나뉘어 있어, 필터를 걸어 0건이 된 사용자에게도 '동기화하세요'만 떴다.
        neverSynced ? (
          <EmptyState
            art="docs"
            title="문서가 없습니다"
            help="아직 동기화되지 않았습니다. 운영자가 ‘지금 동기화’를 누르면 Notion 문서를 불러옵니다."
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
            help="위 ‘새 문서’로 첫 문서를 추가하면 Notion 팀 문서에 함께 반영됩니다."
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
          invalidateDocumentViews(qc);
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
        {/* 문서 종류·업무 분야는 분류다 — 상태 배지와 같은 모양을 쓰지 않는다(지시 11). */}
        {doc.document_type ? <Tag label={doc.document_type} /> : null}
        {doc.work_field ? <Tag label={doc.work_field} /> : null}
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
          fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle, lineHeight: 1.4, textAlign: "left",
          // QAH-07 — 위 테이블뷰 제목 링크와 같은 결함(dark 모드 대비 미달, 최저 2.81).
          "&:hover": { color: "primary.dark" },
        }}
      >
        {doc.is_favorite ? <StarRoundedIcon aria-label="즐겨찾기" role="img" sx={{ color: "warning.main", fontSize: "1rem" }} /> : null}
        {doc.restricted ? <Tag label="열람 제한" tone="warn" /> : null}
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
        fontSize: FONT_SIZE.bodySm, color: "text.secondary",
      }}>
        <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {author || "작성자 없음"}
        </Box>
        <Box component="span" sx={{ flexShrink: 0 }}>{doc.last_edited ? fmtDateTime(doc.last_edited) : "-"}</Box>
      </Box>
    </Card>
  );
}
