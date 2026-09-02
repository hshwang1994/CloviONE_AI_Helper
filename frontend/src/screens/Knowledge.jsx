import React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import { api } from "../lib/api.js";
import { useAuth } from "../app/auth.jsx";
import { CONSOLE_WRITE_ROLES, MODERATOR_ROLES, hasRole } from "../lib/roles.js";
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  FormModal,
  ListCard,
  ListEmptyState,
  MetricStrip,
  PageHeader,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { ResultLine } from "../ui/FilterBar.jsx";
import { ListFooter } from "../ui/InfiniteScroll.jsx";
import { useResetScrollOnKeyChange } from "../lib/useInfiniteList.js";
import { useListMemory } from "../lib/listReturn.js";
import { SPACES_KEY, useKnowledgeSpaces } from "../lib/knowledgeSpaces.js";
import { LIST_KEY, VIEW } from "./knowledge/constants.js";
import {
  useCategories, useDocuments, useSummary, useTags, useTemplates, useTree,
} from "./knowledge/queries.js";
import { KnowledgeNav, flatten } from "./knowledge/KnowledgeNav.jsx";
import { KnowledgeFilterBar } from "./knowledge/KnowledgeFilterBar.jsx";
import { buildDocumentColumns } from "./knowledge/documentColumns.jsx";
import { TaxonomyManager } from "./knowledge/TaxonomyManager.jsx";
import { NewDocumentModal } from "./knowledge/NewDocumentModal.jsx";

/* 문서 작업공간 — 상단 탐색 줄 · 좌측 구조 내비 · 목록 (지시 22.4 개정).
 *
 * ## 무엇을 바꿨나
 *
 * 옛 화면은 3칸(탐색기 20rem | 목록 | 곁열 19rem)이었고 검색·필터가 **중앙 칸 안**에
 * 서서 페이지 상단이 아니었다. 조건의 절반(보기·태그 칩)은 탐색기에, 나머지(검색·태그
 * 고르개·작성자·정렬)는 중앙에 흩어져 같은 축이 두 곳에 있었다.
 *
 * 지금은 다른 목록 화면과 같은 골격이다:
 *
 *   PageHeader → 요약 타일 → **전폭 탐색 줄**(검색 + 조건 전부) → 조건 칩 → 건수 줄
 *   → [구조 내비(프로젝트·폴더) | 목록]
 *
 * 좌측 내비에는 필터 줄이 대신할 수 없는 **구조** 둘만 남는다 — 공간과 폴더 트리.
 * 곁열은 없앴다: 최근 열람은 「보기」 축으로, 템플릿은 새 문서 모달로 들어갔고, 그만큼
 * 목록이 넓어져 제목 열이 산다(P-59).
 *
 * ## 요약 넷은 누르면 좁혀진다
 *
 * 장식용 숫자를 안 둔다. 각 수는 아래 목록의 조건 하나와 **같은 판정**을 쓴다
 * (`app/knowledge/service.py::workspace_summary`). */

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

  const spaceId = params.get("space") || "";
  const folderId = params.get("folder") || "";
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
    if (spaceId) next.space = spaceId;
    if (folderId) next.folder = folderId;
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

  /* 공간이 **하나뿐이면** 그것을 연다. 폴더 트리는 공간을 고른 뒤에야 뜻이 있는데, 고를
     것이 하나인 화면에서 「전체」에 머무르면 내비의 절반이 비어 보인다. */
  React.useEffect(() => {
    if (!spaceId && items.length === 1) {
      setParams({ space: items[0].id }, { replace: true });
    }
  }, [spaceId, items, setParams]);

  const tree = useTree(spaceId);
  const tagsQuery = useTags();
  const categoriesQuery = useCategories();
  const summary = useSummary();
  const templates = useTemplates();
  const documents = useDocuments({
    view, spaceId, folderId, q, tags, category, author, sort, resume: resumeChunks,
  });
  /* 조건이 바뀌면 목록 머리로 되돌린다. 첫 마운트에는 안 돈다(그 순간은 `listReturn` 이
     스크롤을 복원하는 자리다). */
  useResetScrollOnKeyChange(
    JSON.stringify([view, spaceId, folderId, q, tags, category, author, sort]),
  );

  const [folderForm, setFolderForm] = React.useState(false);
  const [spaceForm, setSpaceForm] = React.useState(false);
  const [newDoc, setNewDoc] = React.useState(null);
  const [taxonomyOpen, setTaxonomyOpen] = React.useState(false);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["knowledge", "documents"] });
    qc.invalidateQueries({ queryKey: ["knowledge", "summary"] });
  };

  const createFolder = useMutation({
    mutationFn: (body) => api("/api/knowledge/folders", { method: "POST", body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["knowledge", "tree", spaceId] });
      setFolderForm(false);
      toast("폴더를 만들었습니다.");
    },
    onError: (e) => toast(e.message, "error"),
  });

  const moveFolder = useMutation({
    mutationFn: ({ id, before_id, after_id }) =>
      api(`/api/knowledge/folders/${id}`, { method: "PATCH", body: { before_id, after_id } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["knowledge", "tree", spaceId] }),
    onError: (e) => toast(e.message, "error"),
  });

  const removeFolder = useMutation({
    mutationFn: (id) => api(`/api/knowledge/folders/${id}`, { method: "DELETE" }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["knowledge", "tree", spaceId] });
      invalidate();
      const moved = data?.documents_moved_to_root || 0;
      toast(
        moved
          ? `폴더를 지웠고 문서 ${moved}건이 정리 안 함 상태가 됐습니다.`
          : "폴더를 지웠습니다.",
      );
    },
    onError: (e) => toast(e.message, "error"),
  });

  const createSpace = useMutation({
    mutationFn: (body) => api("/api/knowledge/spaces", { method: "POST", body }),
    onSuccess: (space) => {
      qc.invalidateQueries({ queryKey: SPACES_KEY });
      setSpaceForm(false);
      toast("공간을 만들었습니다.");
      if (space?.id) setParams({ space: space.id });
    },
    onError: (e) => toast(e.message, "error"),
  });

  /* 어휘(태그·카테고리)를 고치면 **목록의 줄과 조건 후보가 함께** 달라진다 — 함께
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

  const addTag = useMutation({
    mutationFn: (name) => api("/api/knowledge/tags", { method: "POST", body: { name } }),
    onSuccess: () => { invalidateTags(); toast("태그를 추가했습니다."); },
    onError: (e) => toast(e.message, "error"),
  });

  const renameTag = useMutation({
    mutationFn: ({ id, name }) =>
      api(`/api/knowledge/tags/${id}`, { method: "PATCH", body: { name } }),
    onSuccess: () => { invalidateTags(); toast("태그 이름을 고쳤습니다."); },
    onError: (e) => toast(e.message, "error"),
  });

  const removeTag = useMutation({
    mutationFn: (id) => api(`/api/knowledge/tags/${id}`, { method: "DELETE" }),
    onSuccess: (result) => {
      invalidateTags();
      toast(
        result.detached
          ? `태그를 지웠고 문서 ${result.detached}건에서 뗐습니다.`
          : "태그를 지웠습니다.",
      );
    },
    onError: (e) => toast(e.message, "error"),
  });

  const addCategory = useMutation({
    mutationFn: (name) => api("/api/knowledge/categories", { method: "POST", body: { name } }),
    onSuccess: () => { invalidateCategories(); toast("카테고리를 추가했습니다."); },
    onError: (e) => toast(e.message, "error"),
  });

  const renameCategory = useMutation({
    mutationFn: ({ id, name }) =>
      api(`/api/knowledge/categories/${id}`, { method: "PATCH", body: { name } }),
    onSuccess: () => { invalidateCategories(); toast("카테고리 이름을 고쳤습니다."); },
    onError: (e) => toast(e.message, "error"),
  });

  const removeCategory = useMutation({
    mutationFn: (id) => api(`/api/knowledge/categories/${id}`, { method: "DELETE" }),
    onSuccess: (result, deletedId) => {
      invalidateCategories();
      toast(
        result.detached
          ? `카테고리를 지웠고 문서 ${result.detached}건이 미분류가 됐습니다.`
          : "카테고리를 지웠습니다.",
      );
      /* 지운 분류가 지금 조건이면 조건도 푼다 — 남겨 두면 영원히 0건인 화면이 된다. */
      if (category && category === deletedId) setQuery({ category: null });
    },
    onError: (e) => toast(e.message, "error"),
  });

  const createDocument = useMutation({
    mutationFn: (body) => api("/api/knowledge/documents", { method: "POST", body }),
    onSuccess: (doc) => {
      invalidate();
      setNewDoc(null);
      navigate(`/knowledge/${doc.id}`, { state: { from: LIST_KEY } });
    },
    onError: (e) => toast(e.message, "error"),
  });

  const favorite = useMutation({
    mutationFn: ({ id, on }) =>
      api(`/api/knowledge/documents/${id}/favorite?on=${on ? "true" : "false"}`, { method: "POST" }),
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ["knowledge", "recent"] });
    },
    onError: (e) => toast(e.message, "error"),
  });

  const archive = useMutation({
    mutationFn: (id) => api(`/api/knowledge/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast("문서를 휴지통으로 보냈습니다. 휴지통에서 되살릴 수 있습니다.");
    },
    onError: (e) => toast(e.message, "error"),
  });

  const openDoc = React.useCallback(
    (doc) => navigate(`/knowledge/${doc.id}`, { state: { from: LIST_KEY } }),
    [navigate],
  );

  const folders = flatten(tree.data?.folders || []);
  const tagRows = tagsQuery.data?.items || [];
  const categoryRows = categoriesQuery.data?.items || [];
  const templateRows = templates.data?.items || [];
  const summaryRow = summary.data;
  const rows = documents.rows;
  const total = documents.total ?? rows.length;
  const authors = documents.first?.authors || [];
  const role = (auth.data && auth.data.role) || "";
  const canMakeSpace = hasRole(CONSOLE_WRITE_ROLES, role);
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

  if (!items.length) {
    return (
      <>
        <PageHeader crumbRoot="팀 업무" area="문서" title="문서" />
        <EmptyState
          layout="page"
          art="docs"
          title="볼 수 있는 프로젝트 문서가 없습니다."
          help="관리자가 프로젝트를 만들면 여기에 나타납니다."
        />
      </>
    );
  }

  /* 「필터 지우기」가 지우는 축 = 조건을 세는 축 (D-388). 한 목록에서 관리한다.
     프로젝트(공간)는 여기 없다 — 그것은 조건이 아니라 **지금 서 있는 자리**다(좌측
     내비가 그 상태를 그린다). 공간이 하나뿐인 설치는 화면이 스스로 그 공간을 여는데,
     그것을 조건으로 세면 아무것도 안 건 사람에게 「조건 1개」가 보인다. */
  const activeConditions = [
    q ? "검색어" : "",
    view ? "보기" : "",
    folderId ? "폴더" : "",
    category ? "분류" : "",
    tags.length ? "태그" : "",
    author ? "작성자" : "",
  ].filter(Boolean);
  const hasFilter = activeConditions.length > 0;
  const clearFilters = () => setQuery({
    q: null, view: null, folder: null, category: null, tags: [], author: null,
  });
  const folderName = (folders.find((f) => f.id === folderId) || {}).name || "";

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
            <Button onClick={() => setTaxonomyOpen(true)}>분류 관리</Button>
            <Button
              variant="primary"
              onClick={() => setNewDoc({
                title: "", space_id: spaceId || items[0].id, folder_id: folderId || "",
                category_id: "", tags: [], template: "blank",
              })}
            >
              새 문서
            </Button>
          </>
        )}
      />

      {summaryRow ? (
        <MetricStrip
          ariaLabel="문서 요약"
          sx={{ mb: 2 }}
          items={[
            {
              key: "total", label: "전체 문서", value: summaryRow.total, primary: true,
              active: view === VIEW.all && !folderId,
              onClick: () => setQuery({ view: null, folder: null }),
            },
            {
              key: "recent", label: "최근 수정", value: summaryRow.recent,
              note: "최근 24시간",
              active: sort === "recent" && view === VIEW.all,
              onClick: () => setQuery({ view: null, sort: "recent" }),
            },
            {
              key: "favorites", label: "즐겨찾기", value: summaryRow.favorites,
              active: view === VIEW.favorites,
              onClick: () => setQuery({ view: VIEW.favorites }),
            },
            {
              key: "drafts", label: "내 초안", value: summaryRow.drafts,
              note: "아직 고치지 않은 내 문서",
              active: view === VIEW.drafts,
              onClick: () => setQuery({ view: VIEW.drafts }),
            },
          ]}
        />
      ) : null}

      <KnowledgeFilterBar
        q={q}
        view={view}
        spaceId={spaceId}
        folderId={folderId}
        folderName={folderName}
        tags={tags}
        category={category}
        author={author}
        sort={sort}
        spaces={items}
        categories={categoryRows}
        authors={authors}
        onCommitSearch={commitSearch}
        onQuery={setQuery}
        onClearAll={clearFilters}
        hasFilter={hasFilter}
      />

      {/* 「최근 열람」은 쪽을 안 나눈다 — 사람마다 다르고 길지 않다. */}
      <ResultLine total={total} conditions={activeConditions} />

      <Box
        sx={{
          display: "grid",
          alignItems: "start",
          gap: 2,
          /* 좌측 내비는 구조(프로젝트·폴더)만 든다. 17rem 은 옛 실측에서 줄이 45px
             잘렸던 폭이다 — 제목과 「폴더 추가」가 한 줄에 서는 칸이라 18rem 을 준다. */
          gridTemplateColumns: { xs: "1fr", lg: "18rem minmax(0, 1fr)" },
        }}
      >
        <KnowledgeNav
          spaces={items}
          spaceId={spaceId}
          tree={tree}
          folderId={folderId}
          onSpace={(next) => setQuery({ space: next || null, folder: null })}
          onFolder={(next) => setQuery({ folder: next || null })}
          onNewFolder={() => setFolderForm(true)}
          onDeleteFolder={(folder) => removeFolder.mutate(folder.id)}
          onReorderFolder={({ id, beforeId, afterId }) =>
            moveFolder.mutate({ id, before_id: beforeId, after_id: afterId })}
          onNewSpace={canMakeSpace ? () => setSpaceForm(true) : null}
        />

        <Box sx={{ minWidth: 0 }}>
          {documents.isError ? (
            <ErrorState error={documents.error} onRetry={() => documents.refetch()} />
          ) : (
            <ListCard>
              {!documents.isLoading && rows.length === 0 ? (
                <ListEmptyState
                  filtered={hasFilter}
                  onClear={clearFilters}
                  clearLabel="검색, 필터 지우기"
                  filteredTitle="조건에 맞는 문서가 없습니다"
                  filteredHelp="검색어와 분류, 태그, 작성자 조건을 풀면 전체 문서가 다시 나타납니다."
                  title="문서가 아직 없습니다."
                  help="위의 새 문서로 만들면 이 목록에 나타납니다."
                />
              ) : (
                <DataTable
                  columns={columns}
                  rows={rows}
                  rowKey={(d) => d.id}
                  onRow={openDoc}
                  loading={documents.isLoading}
                  stickyHeader
                  total={documents.total}
                  /* 판정 기준이 `rows.length` 가 아니라 **전체 건수**다. 받은 행 수로 재면
                     묶음이 붙다가 60을 넘는 순간 가상화가 켜지면서 `<tbody>` 가 통째로
                     다시 마운트된다 — 굴리던 자리가 튄다. */
                  virtualize={(documents.total ?? rows.length) > 60 ? {} : undefined}
                />
              )}
              {!documents.isLoading && !documents.isError && !listed ? (
                <ListFooter
                  total={documents.total}
                  loaded={documents.loaded}
                  hasNext={documents.hasNext}
                  isFetchingNext={documents.isFetchingNext}
                  onMore={documents.fetchNext}
                  moreLabel="문서 더 보기"
                />
              ) : null}
            </ListCard>
          )}
        </Box>
      </Box>

      <FormModal
        open={folderForm}
        title="폴더 추가"
        fields={[
          { name: "name", label: "폴더 이름", required: true, maxLength: 200 },
          {
            name: "parent_id",
            label: "상위 폴더",
            type: "select",
            options: [{ value: "", label: "없음" }].concat(
              folders.map((f) => ({ value: f.id, label: f.name })),
            ),
          },
        ]}
        initial={{ name: "", parent_id: folderId || "" }}
        submitLabel="만들기"
        onClose={() => setFolderForm(false)}
        onSubmit={(values) =>
          createFolder.mutateAsync({
            space_id: spaceId,
            name: values.name,
            parent_id: values.parent_id || null,
          })}
      />

      {/* 공간 만들기는 관리자만 본다 (`SPACE_ADMIN`). 서버가 같은 요청을 403 으로 막으므로
          숨기는 것은 안내이지 방어가 아니다. */}
      <FormModal
        open={spaceForm}
        title="문서 공간 추가"
        fields={[
          { name: "name", label: "공간 이름", required: true, maxLength: 200 },
          {
            name: "slug", label: "주소", required: true, maxLength: 64,
            help: "영문 소문자와 숫자, 붙임표만 씁니다.",
          },
          {
            name: "owner_kind", label: "누구의 공간인가", type: "select", required: true,
            options: [
              { value: "organization", label: "조직 전체" },
              { value: "unset", label: "정하지 않음" },
            ],
            help: "부서와 프로젝트 공간은 관리 콘솔에서 대상을 골라 만듭니다.",
          },
        ]}
        initial={{ name: "", slug: "", owner_kind: "organization" }}
        submitLabel="만들기"
        onClose={() => setSpaceForm(false)}
        onSubmit={(values) => createSpace.mutateAsync(values)}
      />

      <TaxonomyManager
        open={taxonomyOpen}
        onClose={() => setTaxonomyOpen(false)}
        canManage={canManageTaxonomy}
        busy={
          addTag.isPending || renameTag.isPending || removeTag.isPending
          || addCategory.isPending || renameCategory.isPending || removeCategory.isPending
        }
        categories={categoryRows}
        tags={tagRows}
        onAddCategory={(name, done) => addCategory.mutate(name, { onSuccess: done })}
        onRenameCategory={(row, name, done) =>
          renameCategory.mutate({ id: row.id, name }, { onSuccess: done })}
        onRemoveCategory={async (row) => {
          /* 몇 건이 미분류가 되는지를 **묻는 문장에** 넣는다. */
          const used = row.document_count ?? 0;
          const ok = await confirm(
            used
              ? `문서 ${used}건이 미분류로 돌아갑니다. 문서 자체는 그대로 남습니다.`
              : "이 카테고리를 쓰는 문서가 없습니다.",
            { title: `${row.name} 카테고리를 삭제할까요?`, confirmLabel: "삭제", danger: used > 0 },
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
          title: "", space_id: "", folder_id: "", category_id: "", tags: [], template: "blank",
        }}
        spaces={items}
        templates={templateRows}
        categories={categoryRows}
        busy={createDocument.isPending}
        onClose={() => setNewDoc(null)}
        onSubmit={(values) => createDocument.mutate({
          space_id: values.space_id,
          title: values.title.trim(),
          folder_id: values.folder_id || null,
          category_id: values.category_id || null,
          template: values.template || null,
          tag_names: values.tags && values.tags.length ? values.tags : null,
        })}
      />
    </>
  );
}

export default Knowledge;
