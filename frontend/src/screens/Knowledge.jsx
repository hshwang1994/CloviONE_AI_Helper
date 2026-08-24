import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  FormModal,
  ListEmptyState,
  PageHeader,
  Skeleton,
  useToast,
} from "../ui/kit.jsx";
import { DragItem, SortableList } from "../ui/DragDrop.jsx";
import { Pager } from "../ui/Pager.jsx";
import Chip from "@mui/material/Chip";
import StarRoundedIcon from "@mui/icons-material/StarRounded";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";

/* 지식 공간 — 공간 · 폴더 트리 · 문서 목록 (S7).
 *
 * ## 폴더와 권한은 다른 축이다
 *
 * 폴더는 **정리**다. 문서를 다른 폴더로 옮겨도 볼 수 있는 사람은 안 바뀐다(§5.3). 그래서
 * 이 화면의 폴더 트리에는 권한 표시가 하나도 없다 — 있으면 사람이 「여기로 옮기면 안
 * 보이게 되겠구나」라고 잘못 믿는다. 권한은 공간을 고르는 자리에서만 말한다.
 *
 * ## 폴더 정렬은 공용 부품을 쓴다
 *
 * `DragDrop.jsx` 한 곳이 포인터와 키보드를 함께 받고 스크린리더에 상황을 말한다. 여기서
 * 다시 만들면 그 둘 중 하나가 반드시 빠지고, 빠지는 것은 대개 키보드다 — 마우스로
 * 시험하면 빠진 것처럼 안 보이기 때문이다.
 *
 * ## 서버가 「몇 건이 올라왔는지」를 알려 준다
 *
 * 폴더를 지우면 그 아래 문서는 안 지워지고 공간 뿌리로 올라온다. 그 사실을 화면이 말하지
 * 않으면 사용자는 문서가 사라졌다고 믿는다. */

const SPACES_KEY = ["knowledge", "spaces"];

/* 한 화면에 보여 주는 문서 수. 서버 기본값과 같은 수다.
 *
 * 예전에는 화면이 `limit`·`offset`·`total` 을 하나도 안 썼다. 서버는 50건에서 자르고
 * 전체 건수를 함께 알려 줬는데 화면이 그 값을 안 읽어서, 문서 110건 중 **60건은 있다는
 * 사실 자체가** 사용자에게 안 보였다. 목록이 끊긴 자리에 아무 표시도 없으면 사람은 그것이
 * 전부라고 믿는다. */
const PAGE_SIZE = 50;

function useSpaces() {
  return useQuery({ queryKey: SPACES_KEY, queryFn: () => api("/api/knowledge/spaces") });
}

function useTree(spaceId) {
  return useQuery({
    queryKey: ["knowledge", "tree", spaceId],
    queryFn: () => api(`/api/knowledge/spaces/${spaceId}/tree`),
    enabled: Boolean(spaceId),
  });
}

/* 옛 문서 화면의 「문서 종류·업무 분야·기술 태그」 세 필터는 대신하지 않는다 — 그 셋은
 * `document_cache` 의 고정 상수 축이고 이관에서 태그(`document_tags`, 61/61)로 손실 없이
 * 들어왔다(S14 결정 D6). 여기서는 그 결과인 **태그 하나**로 좁힌다 — 서버가 이미
 * `tag` 질의를 받는다(`app/knowledge/service.py::list_documents`). */
function useTags() {
  return useQuery({ queryKey: ["knowledge", "tags"], queryFn: () => api("/api/knowledge/tags") });
}

function useDocuments({ spaceId, folderId, q, favorites, tag, page }) {
  return useQuery({
    queryKey: ["knowledge", "documents", spaceId, folderId, q, favorites, tag, page],
    queryFn: () => {
      const params = new URLSearchParams();
      if (spaceId) params.set("space_id", spaceId);
      if (folderId) params.set("folder_id", folderId);
      if (q) params.set("q", q);
      if (favorites) params.set("favorites", "true");
      if (tag) params.set("tag", tag);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String((page - 1) * PAGE_SIZE));
      return api(`/api/knowledge/documents?${params.toString()}`);
    },
    enabled: Boolean(spaceId),
  });
}

/* 트리를 평평하게 편다. 들여쓰기는 `depth` 가 만든다 — 화면이 재귀 컴포넌트를 쓰면
 * 끌어 놓기 대상이 계층마다 다른 목록이 되고, 그때부터 「형제 사이로 옮기기」를
 * 정확히 말할 수 없다. */
function flatten(nodes, out = []) {
  for (const node of nodes || []) {
    out.push(node);
    flatten(node.children, out);
  }
  return out;
}

function FolderTree({ spaceId, folders, selected, onSelect, onReorder, onCreate, onDelete }) {
  const rows = flatten(folders);

  if (!rows.length) {
    return (
      <Stack spacing={1}>
        <EmptyState
          title="폴더가 아직 없습니다."
          help="폴더를 만들면 문서를 주제별로 모아 둘 수 있습니다."
          action={<Button onClick={onCreate}>폴더 추가</Button>}
        />
      </Stack>
    );
  }

  const labelOf = (id) => (rows.find((f) => f.id === id) || {}).name || "";

  return (
    <Stack spacing={1}>
      <SortableList items={rows} labelOf={labelOf} onReorder={onReorder}>
        {(folder) => (
          <DragItem key={folder.id} id={folder.id} label={folder.name}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ width: "100%" }}>
              <Box
                component="button"
                type="button"
                onClick={() => onSelect(folder.id)}
                aria-current={selected === folder.id ? "true" : undefined}
                sx={{
                  ...KO_WORD_BREAK,
                  flex: 1,
                  minWidth: 0,
                  textAlign: "left",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  font: "inherit",
                  color: "inherit",
                  // 계층은 들여쓰기로 보인다 — `depth` 는 트리거가 만든 값이라 화면이
                  // 다시 세지 않는다(세면 옮긴 직후 한 회차 어긋난다).
                  pl: `${folder.depth * 1.2}rem`,
                  fontWeight: selected === folder.id ? FONT_WEIGHT.semibold : FONT_WEIGHT.regular,
                }}
              >
                {folder.name}
              </Box>
              <Button size="small" variant="ghost" onClick={() => onDelete(folder)}>
                삭제
              </Button>
            </Stack>
          </DragItem>
        )}
      </SortableList>
      <Box>
        <Button size="small" onClick={onCreate}>폴더 추가</Button>
      </Box>
    </Stack>
  );
}

export function Knowledge() {
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();

  const spaceId = params.get("space") || "";
  const folderId = params.get("folder") || "";
  const q = params.get("q") || "";
  const favorites = params.get("favorites") === "1";
  const tag = params.get("tag") || "";
  const page = Math.max(1, Number(params.get("page") || 1));

  /* 주소를 고칠 때 지금 조건을 그대로 들고 간다 — 쪽을 넘겼다고 검색어가 사라지면
   * 사용자는 방금 무엇을 보고 있었는지 다시 만들어야 한다. `page` 는 조건이 바뀌면
   * 1로 돌아간다: 세 번째 쪽을 보다가 검색을 하면 결과가 한 쪽뿐인데 빈 화면이 뜬다. */
  const setQuery = (patch, { keepPage = false } = {}) => {
    const next = { space: spaceId };
    if (folderId) next.folder = folderId;
    if (q) next.q = q;
    if (favorites) next.favorites = "1";
    if (tag) next.tag = tag;
    if (keepPage && page > 1) next.page = String(page);
    Object.entries(patch).forEach(([key, value]) => {
      if (value === null || value === undefined || value === "" || value === false) {
        delete next[key];
      } else {
        next[key] = value === true ? "1" : String(value);
      }
    });
    setParams(next);
  };

  const spaces = useSpaces();
  const items = spaces.data?.items || [];

  /* 공간을 안 고르면 첫 번째를 연다. 빈 화면을 보여 주고 「고르세요」라고 말하면
   * 대부분의 사람에게 공간은 하나뿐이라 한 번 더 누르는 일만 늘어난다. */
  React.useEffect(() => {
    if (!spaceId && items.length) {
      setParams({ space: items[0].id }, { replace: true });
    }
  }, [spaceId, items, setParams]);

  const tree = useTree(spaceId);
  const documents = useDocuments({ spaceId, folderId, q, favorites, tag, page });
  const tags = useTags();
  const tagRows = tags.data?.items || [];

  const [folderForm, setFolderForm] = React.useState(false);
  const [docForm, setDocForm] = React.useState(false);

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
      qc.invalidateQueries({ queryKey: ["knowledge", "documents"] });
      const moved = data?.documents_moved_to_root || 0;
      toast(
        moved
          ? `폴더를 지웠고 문서 ${moved}건이 공간 첫 화면으로 올라왔습니다.`
          : "폴더를 지웠습니다.",
      );
    },
    onError: (e) => toast(e.message, "error"),
  });

  const createDocument = useMutation({
    mutationFn: (body) => api("/api/knowledge/documents", { method: "POST", body }),
    onSuccess: (doc) => {
      qc.invalidateQueries({ queryKey: ["knowledge", "documents"] });
      setDocForm(false);
      navigate(`/knowledge/${doc.id}`);
    },
    onError: (e) => toast(e.message, "error"),
  });

  if (spaces.isLoading) return <Skeleton kind="page" lines={4} />;
  if (spaces.isError) {
    return <ErrorState error={spaces.error} onRetry={() => spaces.refetch()} />;
  }

  if (!items.length) {
    return (
      <>
        <PageHeader area="팀 업무" title="지식 공간" />
        <EmptyState
          title="볼 수 있는 지식 공간이 없습니다."
          help="관리자가 공간을 만들면 여기에 나타납니다."
        />
      </>
    );
  }

  const rows = documents.data?.items || [];
  const folderRows = flatten(tree.data?.folders || []);

  return (
    <>
      <PageHeader
        area="팀 업무"
        /* 사이드바 항목과 **같은 낱말**이어야 한다 (S14 · C2). 「문서」를 눌러 왔는데 화면
           제목이 「지식 공간」이면 사용자는 다른 데로 왔다고 읽는다. */
        title="문서"
        actions={
          <>
            {/* 휴지통 입구는 옛 문서 목록 화면에 있었다 (S14 · C2). 그 화면이 사라지면서
                입구가 통째로 없어지면 사람이 지운 티켓과 문서를 되살릴 길이 주소를
                직접 치는 것뿐이 된다. */}
            <Button href="#/team-docs/trash">휴지통</Button>
            <Button onClick={() => setDocForm(true)}>새 문서</Button>
          </>
        }
      />

      <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="flex-start">
        <Card sx={{ width: { xs: "100%", md: "20rem" }, flexShrink: 0 }}>
          <Stack spacing={2}>
            <TextField
              select
              size="small"
              label="공간"
              InputLabelProps={{ shrink: true }}
              value={spaceId}
              onChange={(e) => setParams({ space: e.target.value })}
            >
              {items.map((s) => (
                <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>
              ))}
            </TextField>

            <Box
              component="button"
              type="button"
              onClick={() => setQuery({ folder: null, page: null })}
              aria-current={folderId ? undefined : "true"}
              sx={{
                textAlign: "left", background: "none", border: "none", cursor: "pointer",
                font: "inherit", color: "inherit", fontWeight: folderId ? FONT_WEIGHT.regular : FONT_WEIGHT.semibold,
              }}
            >
              전체 문서
            </Box>

            {tree.isLoading ? (
              <Skeleton kind="section" lines={3} />
            ) : (
              <FolderTree
                spaceId={spaceId}
                folders={tree.data?.folders || []}
                selected={folderId}
                onSelect={(id) => setQuery({ folder: id, page: null })}
                onCreate={() => setFolderForm(true)}
                onDelete={(folder) => removeFolder.mutate(folder.id)}
                onReorder={({ id, beforeId, afterId }) =>
                  moveFolder.mutate({ id, before_id: beforeId, after_id: afterId })}
              />
            )}
          </Stack>
        </Card>

        <Card sx={{ flex: 1, minWidth: 0 }}>
          <Stack spacing={2}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ sm: "center" }}>
              <TextField
                size="small"
                label="문서 찾기"
                InputLabelProps={{ shrink: true }}
                defaultValue={q}
                sx={{ flex: 1, minWidth: 0 }}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  setQuery({ q: e.target.value.trim(), page: null });
                }}
              />
              {/* 옛 문서 종류·업무 분야·기술 태그 필터를 대신한다 — 그 축은 태그로 손실 없이
                  들어왔다(S14 · C2, D6). 태그가 하나도 없으면 상자를 안 그린다: 빈 상자는
                  「고를 게 있는데 안 보인다」로 읽힌다. */}
              {tagRows.length > 0 ? (
                <TextField
                  select
                  size="small"
                  label="분류"
                  InputLabelProps={{ shrink: true }}
                  value={tag}
                  sx={{ minWidth: "8rem" }}
                  onChange={(e) => setQuery({ tag: e.target.value || null, page: null })}
                >
                  <MenuItem value="">전체</MenuItem>
                  {tagRows.map((t) => (
                    <MenuItem key={t.id} value={t.slug}>{t.name}</MenuItem>
                  ))}
                </TextField>
              ) : null}
              {/* 즐겨찾기는 **내용 필터**다(무엇을 볼지). 켜짐과 꺼짐을 색과 `aria-pressed`
                  둘 다로 말한다 — 색만으로 말하면 켜졌는지 스크린리더가 모른다. */}
              <Chip
                component="button" type="button" clickable label="즐겨찾기만"
                aria-pressed={favorites}
                color={favorites ? "primary" : "default"}
                variant={favorites ? "filled" : "outlined"}
                onClick={() => setQuery({ favorites: !favorites, page: null })}
              />
            </Stack>

            {documents.isLoading && <Skeleton kind="list" rows={5} />}
            {documents.isError && (
              <ErrorState error={documents.error} onRetry={() => documents.refetch()} />
            )}
            {/* 0건에는 **두 얼굴**이 있다 — 「문서가 아예 없다」와 「조건 때문에 0건이다」는
                다른 사실이고 다음 행동도 다르다. 그 분기는 공용 부품이 든다(W5). */}
            {!documents.isLoading && !documents.isError && rows.length === 0 && (
              <ListEmptyState
                filtered={Boolean(favorites || q || tag)}
                onClear={() => setQuery({ q: null, favorites: false, tag: null, page: null })}
                clearLabel="검색, 필터 지우기"
                filteredTitle="조건에 맞는 문서가 없습니다"
                filteredHelp="검색어와 즐겨찾기 조건을 풀면 전체 문서가 다시 나타납니다."
                title="문서가 아직 없습니다."
                help="새 문서를 만들면 이 목록에 나타납니다."
                action={<Button onClick={() => setDocForm(true)}>새 문서</Button>}
              />
            )}

            <Stack spacing={1}>
              {rows.map((doc) => (
                <Box
                  key={doc.id}
                  component="button"
                  type="button"
                  onClick={() => navigate(`/knowledge/${doc.id}`)}
                  sx={(theme) => ({
                    ...KO_WORD_BREAK,
                    textAlign: "left",
                    background: "none",
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 1,
                    cursor: "pointer",
                    font: "inherit",
                    color: "inherit",
                    p: 1.5,
                  })}
                >
                  <Stack direction="row" alignItems="center" spacing={0.75}>
                    <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, minWidth: 0 }}>
                      {doc.title}
                    </Typography>
                    {doc.is_favorite ? (
                      <StarRoundedIcon
                        aria-label="즐겨찾기" role="img"
                        sx={{ color: "warning.main", flexShrink: 0, fontSize: "1rem" }}
                      />
                    ) : null}
                  </Stack>
                  <Typography variant="body2" color="text.secondary">
                    {doc.source_type === "AI" ? "AI가 만든 문서입니다." : "사람이 쓴 문서입니다."}
                  </Typography>
                  {/* 종류(doc_type)와 태그. 옛 문서 종류·업무 분야·기술 태그 필터가 여기로
                      옮겨 왔다(S14 · D6) — 골라 좁히는 자리(위 「분류」)뿐 아니라 목록 각
                      줄에서도 보여야 「손실 없이 이관됐다」가 눈으로 확인된다. */}
                  {(doc.doc_type || doc.tags?.length > 0) && (
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mt: 0.5, rowGap: 0.5 }}>
                      {doc.doc_type ? (
                        <Chip size="small" variant="outlined" label={doc.doc_type} />
                      ) : null}
                      {(doc.tags || []).map((t) => (
                        <Chip key={t.id} size="small" label={t.name} />
                      ))}
                    </Stack>
                  )}
                </Box>
              ))}
            </Stack>

            {/* 「몇 건 중 어디쯤인가」를 여기서 말한다. 서버가 한 쪽씩 잘라 주므로 이 줄이
                없으면 51번째 문서는 있다는 사실 자체가 화면에서 사라진다. */}
            {!documents.isLoading && !documents.isError && (
              <Pager
                page={page}
                pageSize={PAGE_SIZE}
                total={documents.data?.total}
                onPage={(next) => setQuery({ page: next > 1 ? next : null }, { keepPage: true })}
              />
            )}
          </Stack>
        </Card>
      </Stack>

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
              folderRows.map((f) => ({ value: f.id, label: f.name })),
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

      <FormModal
        open={docForm}
        title="새 문서"
        fields={[{ name: "title", label: "문서 제목", required: true, maxLength: 500 }]}
        initial={{ title: "" }}
        submitLabel="만들기"
        onClose={() => setDocForm(false)}
        onSubmit={(values) =>
          createDocument.mutateAsync({
            space_id: spaceId,
            title: values.title,
            folder_id: folderId || null,
          })}
      />
    </>
  );
}

export default Knowledge;
