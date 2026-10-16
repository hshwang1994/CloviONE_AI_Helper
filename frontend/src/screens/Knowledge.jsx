import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import { api } from "../lib/api.js";
import { useAuth } from "../app/auth.jsx";
import { MODERATOR_ROLES, hasRole } from "../lib/roles.js";
import {
  Button,
  Callout,
  DataTable,
  ErrorState,
  FormModal,
  ListEmptyState,
  PageHeader,
  Segmented,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { failureText } from "../lib/failure.js";
import { useGuardedMutation } from "../lib/useGuardedMutation.js";
import { useResetScrollOnKeyChange } from "../lib/useInfiniteList.js";
import { useListMemory } from "../lib/listReturn.js";
import { SPACES_KEY, useKnowledgeSpaces } from "../lib/knowledgeSpaces.js";
import {
  LIST_KEY, PROJECT_NONE, VIEW, VIEW_OPTIONS, axisValueOf, navEntriesFrom,
} from "./knowledge/constants.js";
import {
  useCategories, useDocuments, useSummary, useTags, useTemplate, useTemplates,
} from "./knowledge/queries.js";
import { useAllProjects } from "./project-queries.js";
import { KnowledgeFilterBar } from "./knowledge/KnowledgeFilterBar.jsx";
import { buildDocumentColumns } from "./knowledge/documentColumns.jsx";
import { TaxonomyManager } from "./knowledge/TaxonomyManager.jsx";
import { NewDocumentModal } from "./knowledge/NewDocumentModal.jsx";

/* 문서 작업공간 — 보기 전환 · 탐색 줄 · 목록 (지시 22.4 개정 · 핸드오프 계획 D).
 *
 * ## 무엇을 바꿨나
 *
 * 옛 화면은 3칸(탐색기 20rem | 목록 | 곁열 19rem)이었고 검색·필터가 **중앙 칸 안**에
 * 서서 페이지 상단이 아니었다. 조건의 절반(보기·태그 칩)은 탐색기에, 나머지(검색·태그
 * 고르개·작성자·정렬)는 중앙에 흩어져 같은 축이 두 곳에 있었다.
 *
 * 지금은 다른 목록 화면과 같은 골격이다:
 *
 *   PageHeader → 보기 전환(세그먼티드 + 건수) → **전폭 탐색 줄**(검색 320 → 조건 → 정렬, 조건이 걸리면 조건 줄) → 목록
 *   → [구조 내비(프로젝트·폴더) | 목록]
 *
 * 좌측 내비에는 필터 줄이 대신할 수 없는 **구조** 둘만 남는다 — 공간과 폴더 트리.
 * 곁열은 없앴다: 최근 열람은 「보기」 축으로, 템플릿은 새 문서 모달로 들어갔고, 그만큼
 * 목록이 넓어져 제목 열이 산다(P-59).
 *
 * ## 보기 전환의 건수는 누르면 좁혀지는 그 목록의 수다
 *
 * 장식용 숫자를 안 둔다. 각 수는 아래 목록의 조건 하나와 **같은 판정**을 쓴다
 * (`app/knowledge/service.py::workspace_summary`). 예전에는 같은 축이 두 자리(요약 판독 줄 넷 + 필터 줄의
 * 「보기」 고르개)에 따로 섰다 — 이제 세그먼티드 하나가 둘을 합친다(핸드오프 계획 D · O-1). 「최근 열람」은
 * 사람마다 다른 발자국이라 건수가 없다. */

/* 공간 목록 질의는 `lib/knowledgeSpaces.js` 가 갖는다 — AI 작업공간과 같은 질의라
 * 두 벌로 두면 한쪽만 응답 모양을 잘못 읽는다(S19 에서 실제로 그랬다). */
export { SPACES_KEY };

export function Knowledge() {
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const auth = useAuth();
  const [params, setParams] = useSearchParams();
  useListMemory(LIST_KEY);

  /* 축은 **프로젝트** 하나다(§11.2 — 「공간」 낱말을 일반 사용자 화면에 쓰지 않는다).
     값은 프로젝트 id 또는 "none"(프로젝트 미지정 — 서버 센티널과 같은 값)이다.
     공간 id 는 이제 화면 어디에서도 안 만든다 — 서버가 정한다. */
  const project = params.get("project") || "";
  const q = params.get("q") || "";
  const tags = params.getAll("tags");
  const category = params.get("category") || "";
  const author = params.get("author") || "";
  const sort = params.get("sort") || "recent";
  const view = params.get("view") || VIEW.all;
  /* 🔴 `page` 는 **주소에 안 쓴다.** 「어디까지 봤는가」는 조건이 아니라 시야다. 옛 링크가
     들고 오는 값은 읽어서 그만큼 미리 받고(`resume`), 첫 `setQuery` 에서 정리된다. */
  const resumeChunks = Math.max(1, Number(params.get("page") || 1));

  /* 주소를 고칠 때 지금 조건을 그대로 들고 간다. `tags` 는 배열이라 다른 축과 다르게
     다룬다 — patch 에 `tags` 가 있으면 그 배열을 그대로 쓰고, 없으면 지금 값을 들고 간다. */
  const setQuery = (patch) => {
    const next = {};
    if (project) next.project = project;
    if (q) next.q = q;
    if (category) next.category = category;
    if (author) next.author = author;
    if (sort && sort !== "recent") next.sort = sort;
    if (view) next.view = view;
    const nextTags = "tags" in patch ? patch.tags : tags;
    delete patch.tags;
    Object.entries(patch).forEach(([key, value]) => {
      if (value === null || value === undefined || value === "" || value === false) {
        delete next[key];
      } else {
        next[key] = value === true ? "1" : String(value);
      }
    });
    if (nextTags && nextTags.length) next.tags = nextTags;
    setParams(next);
  };

  /* 검색 확정은 `SearchBox` 가 디바운스해서 부른다. **참조가 고정**돼야 한다 — 매 렌더마다
     새로 만들면 `React.memo` 가 깨져 글자마다 목록 전체가 다시 그려진다. */
  const setQueryRef = React.useRef(setQuery);
  setQueryRef.current = setQuery;
  const commitSearch = React.useCallback(
    (next) => setQueryRef.current({ q: next || null }),
    [],
  );

  const { query: spaces, items } = useKnowledgeSpaces();
  /* 🔴 좌측 내비·필터의 프로젝트 선택지는 **프로젝트 전체**에서 온다(공간 목록이 아니라).
     새 문서 모달의 ProjectPicker 와 같은 소스(`/api/projects`)라 두 곳이 같은 프로젝트
     집합을 본다 — 문서 0건 프로젝트가 좌측에서만 사라지던 어긋남을 없앤다. */
  const projectsList = useAllProjects();
  /* 「프로젝트 미지정」은 조건 없이 늘 선다 — `navEntriesFrom` 머리말의 이유다. */
  const navEntries = React.useMemo(
    () => navEntriesFrom(projectsList.rows),
    [projectsList.rows],
  );

  /* 옛 주소(`?space=`)와 저장된 화면 기억을 프로젝트 축으로 옮긴다 — 북마크·되돌아오기
     (listReturn 은 주소를 통째로 기억한다)가 조용히 죽지 않게. replace 라 히스토리에
     옛 축이 안 남는다. */
  React.useEffect(() => {
    const legacy = params.get("space");
    if (!legacy || !items.length) return;
    const space = items.find((s) => s.id === legacy);
    const next = new URLSearchParams(params);
    next.delete("space");
    if (space) next.set("project", axisValueOf(space));
    setParams(next, { replace: true });
  }, [params, items, setParams]);

  /* 자리가 **하나뿐이면** 그것을 연다. 폴더 트리는 자리를 고른 뒤에야 뜻이 있는데, 고를
     것이 하나인 화면에서 「전체」에 머무르면 내비의 절반이 비어 보인다.
     세는 것은 **프로젝트 선택지**다. 공간 목록을 세면 공간이 문서가 붙은 자리에만
     생기므로 프로젝트가 여럿인 화면에서도 하나로 세어 엉뚱한 자리가 켜진다. */
  /* 🔴 **둘 다 도착한 뒤에** 센다. 공간 질의가 프로젝트 질의보다 먼저 끝나는 찰나에는
     선택지가 「공통 문서」 하나뿐이라, 세는 시점을 안 막으면 그 찰나에 자동 선택이 걸려
     진입할 때마다 공통 문서로 접힌다(실브라우저에서 실제로 그랬다). */
  /* 🔴 세는 것은 **프로젝트 항목**뿐이다. 「프로젝트 미지정」이 늘 서게 된 뒤로
     `navEntries.length` 로 재면 프로젝트가 하나도 없는 조직에서 길이가 1 이 되어
     들어갈 때마다 미지정으로 접힌다 — 그 조직에는 자동으로 열 「자리」가 없다. */
  const axisReady = !spaces.isPending && !projectsList.isLoading;
  const projectEntries = navEntries.filter((e) => e.value !== PROJECT_NONE);
  React.useEffect(() => {
    if (!axisReady) return;
    if (!project && projectEntries.length === 1) {
      setParams({ project: projectEntries[0].value }, { replace: true });
    }
  }, [axisReady, project, projectEntries, setParams]);

  const tagsQuery = useTags();
  const categoriesQuery = useCategories();
  const summary = useSummary();
  const templates = useTemplates();
  const documents = useDocuments({
    view, project, q, tags, category, author, sort, resume: resumeChunks,
  });
  /* 조건이 바뀌면 목록 머리로 되돌린다. 첫 마운트에는 안 돈다(그 순간은 `listReturn` 이
     스크롤을 복원하는 자리다). */
  useResetScrollOnKeyChange(
    JSON.stringify([view, project, q, tags, category, author, sort]),
  );

  const [newDoc, setNewDoc] = React.useState(null);
  const [taxonomyOpen, setTaxonomyOpen] = React.useState(false);
  /* 고치는 중인 틀. 목록 응답에는 본문이 없어서 **id 만 들고** 있다가 서버가 본문을
     실어 주면 그때 편집 판을 채운다(`useTemplate`). `"new"` 는 아직 없는 틀이다. */
  const [templateId, setTemplateId] = React.useState(null);
  const openTemplate = useTemplate(templateId === "new" ? null : templateId);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["knowledge", "documents"] });
    qc.invalidateQueries({ queryKey: ["knowledge", "summary"] });
  };

  /* 어휘(태그·분류)를 고치면 **목록의 줄과 조건 후보가 함께** 달라진다 — 함께
     무효화한다. 하나만 무효화하면 이름을 고친 어휘가 필터에서는 새 이름, 줄에서는 옛
     이름이 된다. */
  const invalidateTags = () => {
    qc.invalidateQueries({ queryKey: ["knowledge", "tags"] });
    qc.invalidateQueries({ queryKey: ["knowledge", "documents"] });
  };
  const invalidateCategories = () => {
    qc.invalidateQueries({ queryKey: ["knowledge", "categories"] });
    qc.invalidateQueries({ queryKey: ["knowledge", "documents"] });
  };
  /* 🔴 틀을 고쳐도 **문서 목록은 안 건드린다.** 문서는 틀을 참조하지 않고 본문은 만들
     때 복사되므로, 목록을 함께 무효화하면 「틀을 고치면 문서도 바뀐다」는 그림을 화면이
     스스로 그리게 된다(0027 이 구조로 막은 그 일이다). */
  const invalidateTemplates = () => {
    qc.invalidateQueries({ queryKey: ["knowledge", "templates"] });
    qc.invalidateQueries({ queryKey: ["knowledge", "template"] });
  };

  /* 어휘 추가는 「추가」 단추뿐 아니라 이름 칸의 Enter 로도 나간다(`TaxonomyManager.jsx`). 단추는 추가 중에 꺼지지만
     Enter 처리기는 그렇지 않아서, Enter 를 두 번 치면 같은 이름이 두 번 나가고 둘째가 「이미 있습니다」로 실패했다.
     같은 이름은 끝나기 전에 한 번만 나간다(`useGuardedMutation`). 분류 추가도 같다. */
  const addTag = useGuardedMutation({
    mutationFn: (name) => api("/api/knowledge/tags", { method: "POST", body: { name } }),
    onSuccess: () => { invalidateTags(); toast("태그를 추가했습니다."); },
  });

  const renameTag = useMutation({
    mutationFn: ({ id, name }) =>
      api(`/api/knowledge/tags/${id}`, { method: "PATCH", body: { name } }),
    onSuccess: () => { invalidateTags(); toast("태그 이름을 수정했습니다."); },
  });

  const removeTag = useMutation({
    mutationFn: (id) => api(`/api/knowledge/tags/${id}`, { method: "DELETE" }),
    onSuccess: (result) => {
      invalidateTags();
      toast(
        result.detached
          ? `태그를 삭제하고 문서 ${result.detached}건에서 뗐습니다.`
          : "태그를 삭제했습니다.",
      );
    },
  });

  const addCategory = useGuardedMutation({
    mutationFn: (name) => api("/api/knowledge/categories", { method: "POST", body: { name } }),
    onSuccess: () => { invalidateCategories(); toast("분류를 추가했습니다."); },
  });

  const renameCategory = useMutation({
    mutationFn: ({ id, name }) =>
      api(`/api/knowledge/categories/${id}`, { method: "PATCH", body: { name } }),
    onSuccess: () => { invalidateCategories(); toast("분류 이름을 수정했습니다."); },
  });

  const removeCategory = useMutation({
    mutationFn: (id) => api(`/api/knowledge/categories/${id}`, { method: "DELETE" }),
    onSuccess: (result, deletedId) => {
      invalidateCategories();
      toast(
        result.detached
          ? `분류를 삭제했고 문서 ${result.detached}건이 미분류가 됐습니다.`
          : "분류를 삭제했습니다.",
      );
      /* 지운 분류가 지금 조건이면 조건도 푼다 — 남겨 두면 영원히 0건인 화면이 된다. */
      if (category && category === deletedId) setQuery({ category: null });
    },
  });

  const createTemplate = useMutation({
    mutationFn: (body) => api("/api/knowledge/templates", { method: "POST", body }),
    onSuccess: () => { invalidateTemplates(); setTemplateId(null); toast("틀을 추가했습니다."); },
  });

  const saveTemplate = useMutation({
    mutationFn: ({ id, body }) =>
      api(`/api/knowledge/templates/${id}`, { method: "PATCH", body }),
    onSuccess: () => {
      invalidateTemplates();
      setTemplateId(null);
      toast("틀을 수정했습니다. 이 틀로 이미 추가한 문서는 그대로입니다.");
    },
  });

  const removeTemplate = useMutation({
    mutationFn: (id) => api(`/api/knowledge/templates/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidateTemplates();
      setTemplateId(null);
      toast("틀을 삭제했습니다. 이 틀로 추가한 문서는 그대로 남습니다.");
    },
  });

  const createDocument = useMutation({
    mutationFn: (body) => api("/api/knowledge/documents", { method: "POST", body }),
    onSuccess: (doc) => {
      invalidate();
      setNewDoc(null);
      navigate(`/knowledge/${doc.id}`, { state: { from: LIST_KEY } });
    },
  });

  /* 목록의 별은 누르는 동안 꺼지지 않는 맨 단추다. 두 번 누르면 둘 다 화면이 아직 모르는 옛 상태로 같은 요청을
     만든다 — 같은 요청은 끝나기 전에 한 번만 나간다. */
  const favorite = useGuardedMutation({
    mutationFn: ({ id, on }) =>
      api(`/api/knowledge/documents/${id}/favorite?on=${on ? "true" : "false"}`, { method: "POST" }),
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ["knowledge", "recent"] });
    },
  });

  const archive = useMutation({
    mutationFn: (id) => api(`/api/knowledge/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast("문서를 휴지통으로 보냈습니다. 휴지통에서 복원할 수 있습니다.");
    },
  });

  const openDoc = React.useCallback(
    (doc) => navigate(`/knowledge/${doc.id}`, { state: { from: LIST_KEY } }),
    [navigate],
  );

  /* 실패는 토스트가 아니라 **그 자리**의 메시지 박스다(핸드오프 RULES §1 · 계획 표 6). 요청 상태에서 읽으므로
     다음 시도에 걷히고, 성공하면 다시 서지 않는다(`lib/failure.js`). 문장은 서버가 준 그대로다.
       · 분류 관리 창의 추가 · 이름 고치기 · 지우기 · 틀 → 그 창 안
       · 새 문서 만들기 → 그 창의 발 바로 위
       · 목록 줄의 별 · 휴지통으로 보내기 → 목록 바로 위
     창은 열 때 지난 실패를 걷는다 — 닫았다 다시 연 창에 옛 오류가 남지 않는다. */
  const taxonomyMutations = [
    addTag, renameTag, removeTag, addCategory, renameCategory, removeCategory,
    createTemplate, saveTemplate, removeTemplate,
  ];
  const taxonomyFailure = failureText(...taxonomyMutations.map((m) => [m, null]));
  const listFailure = failureText([favorite, null], [archive, null]);

  const tagRows = tagsQuery.data?.items || [];
  const categoryRows = categoriesQuery.data?.items || [];
  const templateRows = templates.data?.items || [];
  const summaryRow = summary.data;
  const rows = documents.rows;
  const total = documents.total ?? rows.length;
  const authors = documents.first?.authors || [];
  const role = (auth.data && auth.data.role) || "";
  /* 이름을 고치고 지우는 것은 그 어휘를 쓰는 **모든 문서**에 닿는다. 서버가 같은 기준으로
     막으므로(`DOCUMENT_DELETE` = 운영자군) 여기서 감추는 것은 방어가 아니라 안내다. */
  const canManageTaxonomy = hasRole(MODERATOR_ROLES, role);
  const listed = view === VIEW.recent;

  const toggleFavorite = React.useCallback(
    (doc) => favorite.mutate({ id: doc.id, on: !doc.is_favorite }),
    [favorite],
  );
  const archiveDoc = React.useCallback((doc) => archive.mutate(doc.id), [archive]);

  const columns = React.useMemo(
    () => buildDocumentColumns({
      onToggleFavorite: toggleFavorite, onOpen: openDoc, onArchive: archiveDoc, confirm,
    }),
    [archiveDoc, confirm, openDoc, toggleFavorite],
  );

  if (spaces.isLoading) return <Skeleton kind="page" lines={4} />;
  if (spaces.isError) {
    return <ErrorState error={spaces.error} onRetry={() => spaces.refetch()} />;
  }

  /* 🔴 「공간이 하나도 없으면 빈 화면」 이라는 조기 반환이 여기 있었다. 이제 틀렸다 —
     프로젝트가 선택이 된 뒤로 **공간이 하나도 없는 조직에서도 문서를 만들 수 있고**
     (서버가 첫 문서에서 공통 공간을 만든다), 그 화면에서 「관리자가 프로젝트를 만들면
     나타납니다」를 보여 주면 할 수 있는 일을 없다고 말하는 것이 된다. 목록이 비었을 때의
     안내는 아래 `ListEmptyState` 하나가 맡는다. */

  /* 「필터 초기화」가 지우는 축 = 칩이 서는 축 (D-388 · 조합 계약 C-1). 한 목록에서 관리한다.
     프로젝트는 **사람이 고른 자리일 때만** 조건이다 — 프로젝트가 하나뿐인 설치는 화면이 스스로 그
     프로젝트를 여는데, 그것을 조건으로 세면 아무것도 안 건 사람에게 「조건 1개」가 보인다. */
  const projectIsCondition = !!project
    && !(projectEntries.length === 1 && project === projectEntries[0].value);
  const hasFilter = !!(q || view || category || tags.length || author || projectIsCondition);
  const clearFilters = () => setQuery({
    q: null, view: null, category: null, tags: [], author: null,
    ...(projectIsCondition ? { project: null } : {}),
  });

  return (
    <>
      <PageHeader
        crumbRoot="팀 업무"
        area="문서"
        /* 사이드바 항목과 **같은 낱말**이어야 한다 (S14 · C2). */
        title="문서"
        description="팀이 쌓아 온 문서를 찾아보고 새로 씁니다."
        actions={(
          <>
            {/* 휴지통은 공용 화면이고 문서 조건으로 열린다 (지시 22.7). */}
            <Button href="#/team-docs/trash?kind=document">휴지통</Button>
            <Button onClick={() => { taxonomyMutations.forEach((m) => m.reset()); setTaxonomyOpen(true); }}>분류 관리</Button>
            <Button
              variant="primary"
              onClick={() => {
                createDocument.reset();
                setNewDoc({
                  /* 지금 서 있는 프로젝트가 기본값이다. 「전체」면 비워 둔다 —
                     프로젝트는 **선택**이라 아무거나 골라 주면 안 된다. */
                  title: "",
                  project_id: project === PROJECT_NONE ? "" : project,
                  category_id: "", tags: [], template: "blank",
                });
              }}
            >
              새 문서
            </Button>
          </>
        )}
      />

      {/* 보기 전환은 필터 바 위의 세그먼티드다(핸드오프 RULES §0 · 계획 D). 건수는 요약이 오면 붙는다 — 오기 전에는
          낱말만 선다(0 을 지어내지 않는다).
          🔴 「최근 24시간」이지 「최근 수정」이 아니다. 예전 타일은 `sort=recent` 만 걸어 전체를 정렬만 했다 —
          이름은 24시간을 말하는데 목록에는 작년 문서가 계속 있었다. 이제 서버가 창을 자른다. */}
      <Segmented
        ariaLabel="문서 보기"
        value={view}
        onChange={(next) => setQuery({ view: next || null })}
        sx={{ mb: 2 }}
        options={[
          { value: VIEW.all, label: "전체 문서", count: summaryRow ? summaryRow.total : undefined },
          ...VIEW_OPTIONS.map((o) => ({
            ...o,
            count: summaryRow
              ? { [VIEW.updated24]: summaryRow.recent, [VIEW.favorites]: summaryRow.favorites, [VIEW.drafts]: summaryRow.drafts }[o.value]
              : undefined,
          })),
        ]}
      />

      <KnowledgeFilterBar
        q={q}
        view={view}
        project={project}
        projectIsCondition={projectIsCondition}
        tags={tags}
        category={category}
        author={author}
        sort={sort}
        entries={navEntries}
        categories={categoryRows}
        authors={authors}
        onCommitSearch={commitSearch}
        onQuery={setQuery}
        onClearAll={clearFilters}
        total={total}
      />

      {/* 결과 수는 조건이 걸리면 필터 바 안 조건 줄이, 늘 목록 판 발이 말한다 — 목록 위 단독 「전체 N건」 줄은 없다
          (조합 계약 C-1). 「최근 열람」은 쪽을 안 나눈다 — 사람마다 다르고 길지 않다. */}
      {listFailure ? <Callout tone="danger" compact>{listFailure}</Callout> : null}

      {/* 🔴 좌측 레일이 없다. 폴더 축이 화면에서 걷히면서(문서 개편 5번) 레일에 남는
          것은 프로젝트 목록뿐이었는데, 그것은 이미 위 조건 줄의 고르개가 그린다 —
          같은 축을 두 자리에서 그리면 둘이 어긋나는 날이 온다. 목록은 `Projects.jsx` 와
          같은 전폭 골격으로 선다(그 화면 다섯이 이미 쓰는 한 벌이다).
          `LIST_RAIL_GRID` 는 조직 콘솔이 계속 쓰므로 `ui/density.js` 에 그대로 둔다. */}
      <Box sx={{ minWidth: 0 }}>
          {documents.isError ? (
            <ErrorState layout="region" error={documents.error} onRetry={() => documents.refetch()} />
          ) : (
            /* 목록 판 — 판이 곧 표 상자이고 받은 건수와 「문서 더 보기」는 판 안 발이다(조합 계약 C-3). 「최근 열람」은
               쪽을 안 나누므로 받은 행 수로 같은 문장을 쓴다. */
            <DataTable
              placement="surface"
              columns={columns}
              rows={rows}
              rowKey={(d) => d.id}
              onRow={openDoc}
              loading={documents.isLoading}
              emptyState={(
                <ListEmptyState
                  filtered={hasFilter}
                  onClear={clearFilters}
                  clearLabel="검색 조건 초기화"
                  filteredTitle="검색 조건에 맞는 문서가 없습니다."
                  filteredHelp="검색어와 분류, 태그, 작성자 조건을 풀면 전체 문서가 다시 나타납니다."
                  title="등록된 문서가 없습니다."
                  help="위의 '새 문서'로 문서를 추가하면 이 목록에 나타납니다."
                />
              )}
              /* 제목 · 요약 · 태그가 서는 두 줄 행 — 바닥 76(핸드오프 ACCEPTANCE E1 · J2). */
              rowHeight="tall"
              stickyHeader
              total={documents.total}
              /* 판정 기준이 `rows.length` 가 아니라 **전체 건수**다. 받은 행 수로 재면
                 묶음이 붙다가 60을 넘는 순간 가상화가 켜지면서 `<tbody>` 가 통째로
                 다시 마운트된다 — 굴리던 자리가 튄다. */
              virtualize={(documents.total ?? rows.length) > 60 ? {} : undefined}
              list={listed ? undefined : {
                total: documents.total,
                loaded: documents.loaded,
                hasNext: documents.hasNext,
                isFetchingNext: documents.isFetchingNext,
                onMore: documents.fetchNext,
                moreLabel: "문서 더 보기",
              }}
            />
        )}
      </Box>

      {/* 「공간 추가」 UI 는 걷었다 — 조직 공간(공통 문서)은 이관이 이미 만들었고,
          프로젝트 공간은 첫 문서를 만들 때 서버가 만든다(§14.2). 사용자가 공간이라는
          개념을 이해해야만 문서를 만들 수 있던 구조(§14.4 위반)의 마지막 조각이었다.
          서버의 `POST /api/knowledge/spaces` 와 `SPACE_ADMIN` 은 그대로 있다 —
          걷은 것은 화면의 진입점이지 방어가 아니다. */}
      <TaxonomyManager
        open={taxonomyOpen}
        onClose={() => { setTaxonomyOpen(false); setTemplateId(null); }}
        canManage={canManageTaxonomy}
        busy={
          addTag.isPending || renameTag.isPending || removeTag.isPending
          || addCategory.isPending || renameCategory.isPending || removeCategory.isPending
          || createTemplate.isPending || saveTemplate.isPending || removeTemplate.isPending
        }
        categories={categoryRows}
        tags={tagRows}
        templates={templateRows}
        error={taxonomyFailure}
        /* 새 틀은 서버에 없으니 그대로 넘기고, 있는 틀은 **본문이 온 뒤에** 넘긴다 —
           본문 없이 편집 판을 열면 사람이 빈 칸을 보고 저장해 본문을 지운다. */
        editingTemplate={
          templateId === "new" ? { id: "new" } : (openTemplate.data || null)
        }
        onOpenTemplate={(row) => setTemplateId(row.id)}
        onCancelTemplate={() => setTemplateId(null)}
        onCreateTemplate={(body) => createTemplate.mutate(body)}
        onSaveTemplate={(id, body) => saveTemplate.mutate({ id, body })}
        onRemoveTemplate={async (row) => {
          const ok = await confirm(
            "이 틀로 이미 추가한 문서는 그대로 남습니다. 앞으로 새 문서에서 고를 수 없습니다.",
            { title: `${row.name} 틀을 삭제할까요?`, confirmLabel: "삭제", danger: true },
          );
          if (ok) removeTemplate.mutate(row.id);
        }}
        onAddCategory={(name, done) => addCategory.mutate(name, { onSuccess: done })}
        onRenameCategory={(row, name, done) =>
          renameCategory.mutate({ id: row.id, name }, { onSuccess: done })}
        onRemoveCategory={async (row) => {
          /* 몇 건이 미분류가 되는지를 **묻는 문장에** 넣는다. */
          const used = row.document_count ?? 0;
          const ok = await confirm(
            used
              ? `문서 ${used}건이 미분류로 돌아갑니다. 문서 자체는 그대로 남습니다.`
              : "이 분류를 쓰는 문서가 없습니다.",
            { title: `${row.name} 분류를 삭제할까요?`, confirmLabel: "삭제", danger: used > 0 },
          );
          if (ok) removeCategory.mutate(row.id);
        }}
        onAddTag={(name, done) => addTag.mutate(name, { onSuccess: done })}
        onRenameTag={(row, name, done) =>
          renameTag.mutate({ id: row.id, name }, { onSuccess: done })}
        onRemoveTag={async (row) => {
          /* 몇 건에서 떼어지는지를 **묻는 문장에** 넣는다. 0건인 태그를 지우는 것과 서른
             건에서 떼는 것은 다른 일이다. */
          const used = row.document_count ?? 0;
          const ok = await confirm(
            used
              ? `문서 ${used}건에서 이 태그가 떨어집니다. 문서 자체는 그대로 남습니다.`
              : "이 태그를 쓰는 문서가 없습니다.",
            { title: `${row.name} 태그를 삭제할까요?`, confirmLabel: "삭제", danger: used > 0 },
          );
          if (ok) removeTag.mutate(row.id);
        }}
      />

      <NewDocumentModal
        open={Boolean(newDoc)}
        initial={newDoc || {
          title: "", project_id: "", category_id: "", tags: [], template: "blank",
        }}
        templates={templateRows}
        categories={categoryRows}
        busy={createDocument.isPending}
        error={failureText([createDocument, null])}
        onClose={() => setNewDoc(null)}
        onSubmit={(values) => {
          /* 🔴 공간 id 를 **화면이 만들지 않는다.** 프로젝트를 고르면 그 프로젝트로,
             안 고르면 아무것도 안 보낸다 — 서버가 조직 공통 공간을 찾거나 만든다
             (`service.resolve_or_create_common_space`). 예전에는 여기서 공간 목록을
             뒤져 `space_id` 를 지었고, 목록이 비었거나 둘 이상이면 빈 문자열이 나가
             「어느 프로젝트의 문서인지 골라 주세요」로 끝났다. */
          const chosen = values.project_id;
          createDocument.mutate({
            ...(chosen && chosen !== PROJECT_NONE ? { project_id: chosen } : {}),
            title: values.title.trim(),
            category_id: values.category_id || null,
            template: values.template || null,
            tag_names: values.tags && values.tags.length ? values.tags : null,
          });
        }}
      />
    </>
  );
}

export default Knowledge;
