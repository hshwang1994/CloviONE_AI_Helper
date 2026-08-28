import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import StarRoundedIcon from "@mui/icons-material/StarRounded";
import StarOutlineRoundedIcon from "@mui/icons-material/StarOutlineRounded";
import { api } from "../lib/api.js";
import { useAuth } from "../app/auth.jsx";
import { CONSOLE_WRITE_ROLES, MODERATOR_ROLES, hasRole } from "../lib/roles.js";
import {
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  FormModal,
  ListEmptyState,
  MetricStrip,
  Modal,
  ModalFooter,
  OverflowMenu,
  PageHeader,
  Section,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { FilterActions, FilterRow, FilterSurface, ResultLine, ToolbarRow } from "../ui/FilterBar.jsx";
import { DragItem, SortableList } from "../ui/DragDrop.jsx";
import { EntityCombobox, FilterSelect, SearchBox } from "../ui/filters.jsx";
import { Pager } from "../ui/Pager.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { ProjectPicker } from "../ui/ProjectPicker.jsx";
import { TagPicker } from "../ui/TagPicker.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { fmtDateTimeCompact } from "../lib/format.js";
import { useListMemory } from "../lib/listReturn.js";
import { SPACES_KEY, useKnowledgeSpaces } from "../lib/knowledgeSpaces.js";

/* 문서 작업공간 — 탐색기 · 목록 · 보조 정보 (지시 22.4).
 *
 * ## 무엇을 바꿨나
 *
 * 예전 이 화면은 「왼쪽 좁은 공간 칸 + 오른쪽 긴 카드 목록」이었다. 카드 한 장이 말하는
 * 것은 제목과 「사람이 쓴 문서입니다」 한 줄뿐이라, 문서가 백 건이 되면 훑어서 찾는 일이
 * 불가능했다. 문서를 고르는 사람이 실제로 쓰는 단서 — **누가 썼는가 · 어디에 있는가 ·
 * 언제 고쳤는가 · 무슨 내용인가** — 가 화면에 하나도 없었다.
 *
 * 지금은 표다. 표는 카드보다 밀도가 높고, 무엇보다 **열이 이름을 갖는다** — 같은 자리에
 * 같은 종류의 값이 서면 눈이 그 열만 훑는다.
 *
 * ## 세 칸의 역할이 다르다
 *
 *   탐색기 — 「어느 묶음을 볼까」 (공간 · 폴더 · 태그 · 내 것)
 *   목록   — 「그 안에서 무엇을 열까」
 *   곁열   — 「방금 보던 것과 자주 보는 것」
 *
 * 곁열은 **넓을 때만** 선다(지시 22.4). 1366 에서 세 칸을 우기면 목록이 좁아져 제목이
 * 두 줄로 접히는데, 그러면 밀도를 높이려고 표로 바꾼 의미가 없어진다.
 *
 * ## 요약 넷은 누르면 좁혀진다
 *
 * 장식용 숫자를 안 둔다. 각 수는 아래 목록의 조건 하나와 **같은 판정**을 쓴다
 * (`app/knowledge/service.py::workspace_summary`) — 서버가 세는 것과 화면이 좁히는 것이
 * 갈라지면 「최근 수정 12」를 눌렀는데 아홉 줄이 나온다. */

/* 공간 목록 질의는 `lib/knowledgeSpaces.js` 가 갖는다 — AI 작업공간과 같은 질의라
 * 두 벌로 두면 한쪽만 응답 모양을 잘못 읽는다(S19 에서 실제로 그랬다). 무효화 키는
 * 이 화면이 계속 쓰므로 그대로 다시 내보낸다. */
export { SPACES_KEY };

/* 한 쪽의 문서 수. `DataTable` 이 가상 스크롤을 쓰므로(§15.1) 스물다섯 줄로 조회 상한을
 * 만들 이유가 없어졌다 — 백 줄을 한 번에 받아도 화면은 보이는 줄만 그린다(가상화가
 * 렌더링을 감당하고, 쪽 나누기는 순수하게 조회량만 줄인다). */
const PAGE_SIZE = 100;

/* 이 목록의 **정체**. 상세를 열었다 돌아오면 조건과 스크롤이 이 이름으로 되살아난다. */
const LIST_KEY = "/knowledge";

/* 탐색기의 「보기」 넷. 값은 주소에 실린다 — 링크로 건네도 같은 화면이 선다.
 *
 * `recent` 만 다른 입구를 쓴다(`/api/knowledge/recent`). 최근 열람은 사람마다 다르고 길지
 * 않아서 쪽을 나눌 것이 없다 — 없는 쪽 나누기를 흉내 내지 않는다. */
const VIEW = { all: "", favorites: "favorites", drafts: "drafts", recent: "recent" };

const SORTS = [
  { value: "recent", label: "최근 수정순" },
  { value: "created", label: "만든 날짜순" },
  { value: "title", label: "제목순" },
];

function useTree(spaceId) {
  return useQuery({
    queryKey: ["knowledge", "tree", spaceId],
    queryFn: () => api(`/api/knowledge/spaces/${spaceId}/tree`),
    enabled: Boolean(spaceId),
  });
}

/* 옛 문서 화면의 「문서 종류·업무 분야·기술 태그」 세 필터는 대신하지 않는다 — 그 셋은
 * `document_cache` 의 고정 상수 축이고 이관에서 태그(`document_tags`, 61/61)로 손실 없이
 * 들어왔다(S14 결정 D6). 여기서는 그 결과인 **태그 하나**로 좁힌다. */
function useTags() {
  return useQuery({ queryKey: ["knowledge", "tags"], queryFn: () => api("/api/knowledge/tags") });
}

function useSummary() {
  return useQuery({
    queryKey: ["knowledge", "summary"],
    queryFn: () => api("/api/knowledge/summary"),
  });
}

function useTemplates() {
  return useQuery({
    queryKey: ["knowledge", "templates"],
    queryFn: () => api("/api/knowledge/templates"),
    staleTime: 600000,
  });
}

function useRecent() {
  return useQuery({
    queryKey: ["knowledge", "recent"],
    queryFn: () => api("/api/knowledge/recent?limit=8"),
  });
}

function useDocuments(params) {
  const { view, spaceId, folderId, q, tags, author, sort, page } = params;
  return useQuery({
    queryKey: ["knowledge", "documents", view, spaceId, folderId, q, tags, author, sort, page],
    queryFn: () => {
      if (view === VIEW.recent) return api("/api/knowledge/recent?limit=50");
      const search = new URLSearchParams();
      if (spaceId) search.set("space_id", spaceId);
      if (folderId) search.set("folder_id", folderId);
      if (q) search.set("q", q);
      // 다중 태그는 AND 다(app/knowledge/service.py::list_documents) — 서버가 같은 이름의
      // 반복 파라미터를 배열로 받는다.
      (tags || []).forEach((t) => search.append("tags", t));
      if (author) search.set("created_by", author);
      if (sort) search.set("sort", sort);
      if (view === VIEW.favorites) search.set("favorites", "true");
      if (view === VIEW.drafts) { search.set("mine", "true"); search.set("drafts", "true"); }
      search.set("limit", String(PAGE_SIZE));
      search.set("offset", String((page - 1) * PAGE_SIZE));
      return api(`/api/knowledge/documents?${search.toString()}`);
    },
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

/** 탐색기 한 줄. 고른 줄은 색과 `aria-current` 둘 다로 말한다. */
function NavRow({ label, count, selected, indent = 0, onClick, action }) {
  return (
    <Stack direction="row" alignItems="center" spacing={0.5} sx={{ width: "100%" }}>
      <Box
        component="button"
        type="button"
        onClick={onClick}
        aria-current={selected ? "true" : undefined}
        sx={(theme) => ({
          ...KO_WORD_BREAK,
          flex: 1,
          minWidth: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 1,
          textAlign: "left",
          background: selected ? theme.palette.action.selected : "none",
          border: "none",
          borderRadius: 1,
          cursor: "pointer",
          font: "inherit",
          color: "inherit",
          px: 1,
          py: 0.625,
          pl: `${0.75 + indent * 1.1}rem`,
          fontWeight: selected ? FONT_WEIGHT.semibold : FONT_WEIGHT.regular,
        })}
      >
        <Box component="span" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
          {label}
        </Box>
        {count == null ? null : (
          <Box component="span" sx={{ color: "text.secondary", fontSize: FONT_SIZE.caption }}>
            {count}
          </Box>
        )}
      </Box>
      {action}
    </Stack>
  );
}

/* 탐색기 — 「어느 묶음을 볼까」.
 *
 * 폴더는 **정리**다. 문서를 다른 폴더로 옮겨도 볼 수 있는 사람은 안 바뀐다(§5.3). 그래서
 * 폴더 줄에는 권한 표시가 하나도 없다 — 있으면 사람이 「여기로 옮기면 안 보이게 되겠구나」
 * 라고 잘못 믿는다. 권한은 공간을 고르는 자리에서만 말한다. */
function Explorer({
  spaces, spaceId, tree, folderId, view, tagVocab, selectedTags, summary,
  onView, onSpace, onFolder, onToggleTag, onNewFolder, onDeleteFolder, onReorderFolder, onNewSpace,
  onManageTags,
}) {
  const folders = flatten(tree.data?.folders || []);
  const labelOf = (id) => (folders.find((f) => f.id === id) || {}).name || "";

  return (
    <Card sx={{ display: "grid", gap: 2.5, alignContent: "start" }}>
      <Section title="보기">
        <Stack spacing={0.25}>
          <NavRow label="전체 문서" count={summary?.total} selected={view === VIEW.all}
                  onClick={() => onView(VIEW.all)} />
          <NavRow label="즐겨찾기" count={summary?.favorites} selected={view === VIEW.favorites}
                  onClick={() => onView(VIEW.favorites)} />
          <NavRow label="내 초안" count={summary?.drafts} selected={view === VIEW.drafts}
                  onClick={() => onView(VIEW.drafts)} />
          <NavRow label="최근 열람" selected={view === VIEW.recent}
                  onClick={() => onView(VIEW.recent)} />
        </Stack>
      </Section>

      {/* 「공간」이라는 낱말은 관리 화면에서만 쓴다(§11.2) — 여기서는 「프로젝트」다.
          조직 소유 공간(팀 문서)은 프로젝트가 아니므로 「공통 문서」로 부른다. */}
      <Section
        title="프로젝트"
        action={onNewSpace ? (
          <Button size="small" variant="ghost" onClick={onNewSpace}>공간 추가</Button>
        ) : null}
      >
        <Stack spacing={0.25}>
          <NavRow label="전체" selected={!spaceId} onClick={() => onSpace("")} />
          {spaces.map((space) => (
            <NavRow
              key={space.id}
              label={spaceDisplayName(space)}
              selected={spaceId === space.id}
              onClick={() => onSpace(space.id)}
            />
          ))}
        </Stack>
      </Section>

      {/* 폴더는 공간을 골랐을 때만 뜻이 있다. 안 골랐는데 빈 칸을 남겨 두면 「폴더가
          없다」로 읽힌다 — 실제로는 아직 안 물어본 것이다(지시 22.4). */}
      {spaceId ? (
        <Section
          title="폴더"
          action={<Button size="small" variant="ghost" onClick={onNewFolder}>폴더 추가</Button>}
        >
          {tree.isLoading ? <Skeleton kind="section" lines={3} /> : null}
          {!tree.isLoading && folders.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              폴더를 만들면 문서를 주제별로 모아 둘 수 있습니다.
            </Typography>
          ) : null}
          {folders.length > 0 ? (
            /* 트리가 길어지면 **탐색기 안에서만** 굴러간다 (지시 22.4). 이 칸이 페이지를
               늘리면 목록을 보려고 폴더를 지나쳐 내려가야 한다. */
            <Box sx={{ maxHeight: "18rem", overflowY: "auto" }}>
              <SortableList items={folders} labelOf={labelOf} onReorder={onReorderFolder}>
                {(folder) => (
                  <DragItem key={folder.id} id={folder.id} label={folder.name}>
                    <NavRow
                      label={folder.name}
                      indent={folder.depth}
                      selected={folderId === folder.id}
                      onClick={() => onFolder(folder.id)}
                      action={(
                        <Button size="small" variant="ghost" onClick={() => onDeleteFolder(folder)}>
                          삭제
                        </Button>
                      )}
                    />
                  </DragItem>
                )}
              </SortableList>
            </Box>
          ) : null}
        </Section>
      ) : null}

      {/* 태그 칸은 **비어 있어도 선다.** 태그가 하나도 없을 때가 관리 입구가 가장 필요한
          때다 — 없으면 사람은 태그를 문서 저장 화면에서만 만들 수 있다고 믿는다.
          열둘까지만 보여 준다: 그 아래는 목록 위의 「태그」 조건으로 고른다. */}
      <Section
        title="태그"
        action={<Button size="small" variant="ghost" onClick={onManageTags}>태그 관리</Button>}
      >
        {tagVocab.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
            문서에 태그를 붙이면 여기에서 태그로 좁힐 수 있습니다.
          </Typography>
        ) : (
          <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", rowGap: 0.5 }}>
            {tagVocab.slice(0, 12).map((t) => {
              const on = selectedTags.includes(t.name);
              return (
                <Chip
                  key={t.id}
                  component="button"
                  type="button"
                  clickable
                  size="small"
                  label={t.name}
                  aria-pressed={on}
                  color={on ? "primary" : "default"}
                  variant={on ? "filled" : "outlined"}
                  onClick={() => onToggleTag(t.name)}
                />
              );
            })}
          </Stack>
        )}
      </Section>
    </Card>
  );
}

/** 곁열 — 넓은 화면에서만 선다. 여기 있는 것은 전부 **바로 여는** 목록이다. */
function Rail({ recent, favorites, templates, onOpen, onTemplate }) {
  return (
    <Stack spacing={2}>
      <Card>
        <Section title="최근 열람">
          {recent.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              문서를 열면 여기에 쌓입니다.
            </Typography>
          ) : (
            <Stack spacing={0.75}>
              {recent.map((doc) => (
                <Box
                  key={doc.id}
                  component="button"
                  type="button"
                  onClick={() => onOpen(doc)}
                  sx={{
                    ...KO_WORD_BREAK, textAlign: "left", background: "none", border: "none",
                    cursor: "pointer", font: "inherit", color: "inherit", p: 0,
                  }}
                >
                  <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold }}>
                    {doc.title}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {doc.space_name}
                  </Typography>
                </Box>
              ))}
            </Stack>
          )}
        </Section>
      </Card>

      <Card>
        <Section title="즐겨찾기">
          {favorites.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              자주 보는 문서에 별을 달면 여기에 모입니다.
            </Typography>
          ) : (
            <Stack spacing={0.75}>
              {favorites.map((doc) => (
                <Box
                  key={doc.id}
                  component="button"
                  type="button"
                  onClick={() => onOpen(doc)}
                  sx={{
                    ...KO_WORD_BREAK, textAlign: "left", background: "none", border: "none",
                    cursor: "pointer", font: "inherit", color: "inherit", p: 0,
                  }}
                >
                  <Typography variant="body2">{doc.title}</Typography>
                </Box>
              ))}
            </Stack>
          )}
        </Section>
      </Card>

      <Card>
        <Section title="문서 템플릿">
          <Stack spacing={0.75}>
            {templates.filter((t) => !t.empty).map((t) => (
              <Box
                key={t.id}
                component="button"
                type="button"
                onClick={() => onTemplate(t.id)}
                sx={{
                  ...KO_WORD_BREAK, textAlign: "left", background: "none", border: "none",
                  cursor: "pointer", font: "inherit", color: "inherit", p: 0,
                }}
              >
                <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold }}>
                  {t.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">{t.help}</Typography>
              </Box>
            ))}
          </Stack>
        </Section>
      </Card>
    </Stack>
  );
}

/* 태그 관리 — 어휘를 사람이 고칠 수 있게 한다 (지시 22-5 개정).
 *
 * ## 왜 이 창이 필요한가
 *
 * 태그는 지금까지 **문서를 저장할 때 곁다리로** 생겼다. 그래서 오타로 만든 태그를 고칠
 * 방법이 없었고 안 쓰는 태그를 치울 방법도 없었다 — 목록은 늘기만 했다. 운영의 태그
 * 열아홉 중 여덟이 고객사 이름이라, 계약이 끝나거나 이름이 바뀌면 누군가는 그것을 고쳐야 한다.
 *
 * ## 「몇 건에 붙어 있는가」를 먼저 보여 준다
 *
 * 지우려는 사람에게 필요한 것은 그 수다. 0건인 태그를 지우는 것과 서른 건에서 떼는 것은
 * 다른 일이고, 화면이 그 차이를 말하지 않으면 사람은 같은 마음으로 누른다.
 *
 * ## 고치고 지우는 것은 운영자군이다
 *
 * 이름을 고치면 그 태그를 쓰는 **모든 문서**의 표기가 바뀐다. 서버가 같은 기준으로 막으므로
 * (`DOCUMENT_DELETE`) 여기서 감추는 것은 방어가 아니라 안내다.
 */
function TagManager({ open, onClose, tags, canManage, busy, onAdd, onRename, onRemove }) {
  const [name, setName] = React.useState("");
  const [editing, setEditing] = React.useState(null);
  const [draft, setDraft] = React.useState("");

  React.useEffect(() => {
    if (!open) { setName(""); setEditing(null); setDraft(""); }
  }, [open]);

  const add = () => {
    const clean = name.trim();
    if (!clean) return;
    onAdd(clean, () => setName(""));
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="태그 관리"
      footer={<ModalFooter onCancel={onClose} cancelLabel="닫기" />}
    >
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} alignItems="flex-start">
          <TextField
            label="새 태그"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
            InputLabelProps={{ shrink: true }}
            inputProps={{ maxLength: 80 }}
            size="small"
            fullWidth
          />
          <Button variant="primary" disabled={!name.trim() || busy} onClick={add}>추가</Button>
        </Stack>

        {tags.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
            아직 태그가 없습니다. 문서를 쓰면서 적은 태그도 여기에 모입니다.
          </Typography>
        ) : (
          <Stack spacing={0.5} sx={{ maxHeight: "22rem", overflowY: "auto" }}>
            {tags.map((tag) => (
              <Stack
                key={tag.id}
                direction="row"
                spacing={1}
                alignItems="center"
                sx={(theme) => ({
                  py: 0.75, borderBottom: `1px solid ${theme.palette.divider}`,
                })}
              >
                {editing === tag.id ? (
                  <>
                    <TextField
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      size="small"
                      autoFocus
                      inputProps={{ maxLength: 80 }}
                      sx={{ flex: 1, minWidth: 0 }}
                    />
                    <Button
                      size="small"
                      variant="primary"
                      disabled={!draft.trim() || busy}
                      onClick={() => onRename(tag, draft.trim(), () => setEditing(null))}
                    >
                      저장
                    </Button>
                    <Button size="small" variant="ghost" onClick={() => setEditing(null)}>취소</Button>
                  </>
                ) : (
                  <>
                    <Typography sx={{ ...KO_WORD_BREAK, flex: 1, minWidth: 0 }}>{tag.name}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                      문서 {tag.document_count ?? 0}건
                    </Typography>
                    {canManage ? (
                      <>
                        <Button
                          size="small"
                          variant="ghost"
                          onClick={() => { setEditing(tag.id); setDraft(tag.name); }}
                        >
                          수정
                        </Button>
                        <Button size="small" variant="ghost" onClick={() => onRemove(tag)}>
                          삭제
                        </Button>
                      </>
                    ) : null}
                  </>
                )}
              </Stack>
            ))}
          </Stack>
        )}

        {canManage ? null : (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
            태그 이름을 고치거나 지우는 것은 운영자만 할 수 있습니다. 새 태그는 누구나 추가할 수 있습니다.
          </Typography>
        )}
      </Stack>
    </Modal>
  );
}

/* 새 문서 — 제목과 공간이 필수이고 나머지 셋은 선택이다 (지시 22.5).
 *
 * ## 「공개 범위」를 안 묻는다
 *
 * 시안에는 그 칸이 있다. 그런데 이 제품에서 문서의 가시성은 **공간이 정한다**(§5.3) —
 * 문서마다 범위를 따로 고르게 하면 없는 권한 모델을 새로 만드는 것이고, 사용자는 자기가
 * 고른 값이 실제로 지켜진다고 믿는다. 대신 공간을 고르는 자리에서 그 공간이 누구 것인지를
 * 말한다.
 *
 * ## 틀 미리보기는 **이름과 설명**이다
 *
 * 본문까지 미리 그리려면 네 벌의 Block JSON 을 받아야 한다. 고르는 사람이 알고 싶은 것은
 * 「이 틀이 무엇을 채워 주는가」이고, 그건 한 문장이면 된다. */
/** 공간 목록의 표시 이름 — 프로젝트 소유는 그 이름 그대로, 조직 소유는 「공통 문서」로
 * 부른다(§11.2). "공간"이라는 낱말을 일반 사용자 화면에 쓰지 않는다. */
function spaceDisplayName(space) {
  return space.owner_kind === "organization" ? "공통 문서" : space.name;
}

function NewDocumentModal({
  open, onClose, onSubmit, busy, spaces, folders, templates, initial,
}) {
  const [values, setValues] = React.useState(initial);
  React.useEffect(() => { if (open) setValues(initial); }, [open, initial]);

  const set = (patch) => setValues((prev) => ({ ...prev, ...patch }));
  const chosen = templates.find((t) => t.id === values.template) || templates[0];
  const spaceRow = spaces.find((s) => s.id === values.space_id);
  const canSubmit = Boolean((values.title || "").trim() && values.space_id);
  /* 화살표 함수를 JSX 안에 안 둔다. `=>` 의 `>` 가 뒤따르는 라벨과 짝지어져 UX 동사표
     검사(`ux-writing-verb-table.test.js`)의 JSX 텍스트 추출을 오탐시킨다 — 검사의 알려진
     한계라 소비처가 피한다. */
  const submit = () => onSubmit(values);

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="새 문서 만들기"
      size="lg"
      dirty={Boolean((values.title || "").trim())}
      /* 「만들기」를 **감추지 않고 비활성으로** 둔다. 조건을 못 채운 사람에게 필요한 것은
         버튼이 사라지는 것이 아니라 「무엇이 모자란가」이고, 그 답은 필수 표시가 붙은 두
         칸(제목·공간)에 있다. */
      footer={(
        <ModalFooter
          onCancel={onClose}
          onSubmit={submit}
          disabled={!canSubmit}
          submitLabel="만들기"
          busy={busy}
        />
      )}
    >
      <Box sx={{ display: "grid", gap: 3, gridTemplateColumns: { xs: "1fr", md: "1fr 16rem" } }}>
        <Stack spacing={2}>
          <TextField
            label="문서 제목"
            required
            autoFocus
            value={values.title}
            onChange={(e) => set({ title: e.target.value })}
            inputProps={{ maxLength: 500 }}
            InputLabelProps={{ shrink: true }}
            fullWidth
          />
          <TextField
            select
            required
            label="프로젝트"
            value={values.space_id}
            onChange={(e) => set({ space_id: e.target.value, folder_id: "" })}
            InputLabelProps={{ shrink: true }}
            helperText={
              spaceRow
                ? "이 프로젝트를 볼 수 있는 사람이 이 문서를 볼 수 있습니다."
                : "문서가 속할 프로젝트를 고릅니다."
            }
            fullWidth
          >
            {spaces.map((s) => (
              <MenuItem key={s.id} value={s.id}>{spaceDisplayName(s)}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="폴더"
            value={values.folder_id}
            onChange={(e) => set({ folder_id: e.target.value })}
            InputLabelProps={{ shrink: true }}
            helperText="폴더는 정리 자리입니다. 문서를 볼 수 있는 사람은 바뀌지 않습니다."
            fullWidth
          >
            <MenuItem value="">폴더 없음</MenuItem>
            {folders.map((f) => (
              <MenuItem key={f.id} value={f.id}>{"　".repeat(f.depth) + f.name}</MenuItem>
            ))}
          </TextField>
          <TagPicker
            value={values.tags}
            onChange={(next) => set({ tags: next })}
            helperText="검색하거나 없는 이름을 적어 새로 만듭니다."
          />
        </Stack>

        <Stack spacing={1.5}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.semibold }}>템플릿</Typography>
          <Stack spacing={0.75}>
            {templates.map((t) => (
              <Box
                key={t.id}
                component="button"
                type="button"
                onClick={() => set({ template: t.id })}
                aria-pressed={values.template === t.id}
                sx={(theme) => ({
                  ...KO_WORD_BREAK,
                  textAlign: "left",
                  cursor: "pointer",
                  font: "inherit",
                  color: "inherit",
                  p: 1.25,
                  borderRadius: 1,
                  border: `1px solid ${values.template === t.id
                    ? theme.palette.primary.main : theme.palette.divider}`,
                  background: values.template === t.id ? theme.palette.action.selected : "none",
                })}
              >
                <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold }}>
                  {t.name}
                </Typography>
              </Box>
            ))}
          </Stack>
          {chosen ? (
            <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
              {chosen.help}
            </Typography>
          ) : null}
        </Stack>
      </Box>
    </Modal>
  );
}

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
  const author = params.get("author") || "";
  const sort = params.get("sort") || "recent";
  const view = params.get("view") || VIEW.all;
  const page = Math.max(1, Number(params.get("page") || 1));

  /* 주소를 고칠 때 지금 조건을 그대로 들고 간다 — 쪽을 넘겼다고 검색어가 사라지면
   * 사용자는 방금 무엇을 보고 있었는지 다시 만들어야 한다. `page` 는 조건이 바뀌면
   * 1로 돌아간다: 세 번째 쪽을 보다가 검색을 하면 결과가 한 쪽뿐인데 빈 화면이 뜬다.
   *
   * `tags` 는 배열이라 다른 축과 다르게 다룬다 — patch 에 `tags` 가 있으면 그 배열을
   * 그대로 쓰고, 없으면 지금 값을 들고 간다(react-router 의 `setParams` 는 배열 값을
   * 같은 키 반복으로 직렬화한다). */
  const setQuery = (patch, { keepPage = false } = {}) => {
    const next = {};
    if (spaceId) next.space = spaceId;
    if (folderId) next.folder = folderId;
    if (q) next.q = q;
    if (author) next.author = author;
    if (sort && sort !== "recent") next.sort = sort;
    if (view) next.view = view;
    if (keepPage && page > 1) next.page = String(page);
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
    (next) => setQueryRef.current({ q: next || null, page: null }),
    [],
  );

  const { query: spaces, items } = useKnowledgeSpaces();

  /* 공간이 **하나뿐이면** 그것을 연다. 폴더 트리는 공간을 고른 뒤에야 뜻이 있는데, 고를
     것이 하나인 화면에서 「모든 공간」에 머무르면 탐색기의 절반이 비어 보인다. 둘 이상이면
     안 고른다 — 그때는 「전체」가 실제로 다른 답이다. */
  React.useEffect(() => {
    if (!spaceId && items.length === 1) {
      setParams({ space: items[0].id }, { replace: true });
    }
  }, [spaceId, items, setParams]);

  const tree = useTree(spaceId);
  const tagsQuery = useTags();
  const summary = useSummary();
  const templates = useTemplates();
  const recent = useRecent();
  const documents = useDocuments({ view, spaceId, folderId, q, tags, author, sort, page });

  const [folderForm, setFolderForm] = React.useState(false);
  const [spaceForm, setSpaceForm] = React.useState(false);
  const [newDoc, setNewDoc] = React.useState(null);
  const [tagForm, setTagForm] = React.useState(false);

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

  /* 태그 어휘를 고치면 **목록의 줄과 조건 후보가 함께** 달라진다 — 셋을 같이 무효화한다.
     하나만 무효화하면 이름을 고친 태그가 필터에서는 새 이름, 줄에서는 옛 이름이 된다. */
  const invalidateTags = () => {
    qc.invalidateQueries({ queryKey: ["knowledge", "tags"] });
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
  const templateRows = templates.data?.items || [];
  const summaryRow = summary.data;
  const rows = documents.data?.items || [];
  const total = documents.data?.total ?? rows.length;
  const authors = documents.data?.authors || [];
  const role = (auth.data && auth.data.role) || "";
  const canMakeSpace = hasRole(CONSOLE_WRITE_ROLES, role);
  /* 이름을 고치고 지우는 것은 그 태그를 쓰는 **모든 문서**에 닿는다. 서버가 같은 기준으로
     막으므로(`DOCUMENT_DELETE` = 운영자군) 여기서 감추는 것은 방어가 아니라 안내다. */
  const canManageTags = hasRole(MODERATOR_ROLES, role);
  const listed = view === VIEW.recent;

  const columns = React.useMemo(() => [
    {
      key: "star", label: "별", type: "select", width: "3rem",
      render: (doc) => (
        <Box
          component="button"
          type="button"
          aria-label={doc.is_favorite ? `${doc.title} 즐겨찾기 해제` : `${doc.title} 즐겨찾기`}
          aria-pressed={Boolean(doc.is_favorite)}
          onClick={(e) => {
            e.stopPropagation();
            favorite.mutate({ id: doc.id, on: !doc.is_favorite });
          }}
          sx={{
            background: "none", border: "none", cursor: "pointer", p: 0, lineHeight: 0,
            color: doc.is_favorite ? "warning.main" : "text.disabled",
          }}
        >
          {doc.is_favorite
            ? <StarRoundedIcon sx={{ fontSize: "1.125rem" }} />
            : <StarOutlineRoundedIcon sx={{ fontSize: "1.125rem" }} />}
        </Box>
      ),
    },
    {
      key: "title", label: "제목", type: "title", minWidth: "16rem", rowName: (d) => d.title,
      render: (doc) => (
        <Box sx={{ display: "grid", gap: 0.25, minWidth: 0 }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, fontSize: FONT_SIZE.body, ...KO_WORD_BREAK }}>
            {doc.title}
          </Typography>
          {doc.excerpt ? (
            <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>
              {doc.excerpt}
            </Typography>
          ) : null}
          {/* 제목 칸의 칩은 기술 태그만이다(§11.3) — doc_type 은 폴더 열 옆의 보조 글자로
              내린다. 프로젝트 이름이 태그로 안 남는 것도 같은 원칙(0024)의 결과다. */}
          {(doc.tags || []).length > 0 ? (
            <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", rowGap: 0.5, mt: 0.25 }}>
              {(doc.tags || []).map((t) => <Chip key={t.id} size="small" label={t.name} />)}
            </Stack>
          ) : null}
        </Box>
      ),
    },
    {
      key: "place", label: "프로젝트", type: "name", minWidth: "10rem",
      render: (doc) => (
        <Box sx={{ display: "grid", gap: 0.25, minWidth: 0 }}>
          <Typography variant="body2" sx={KO_WORD_BREAK}>
            {doc.project ? doc.project.name : "공통 문서"}
          </Typography>
          {doc.folder_path ? (
            <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>
              {doc.folder_path}
            </Typography>
          ) : null}
          {/* doc_type 은 칩이 아니라 폴더 옆의 보조 글자다(§11.3) — 기술 태그와 섞이면
              "이 문서가 다루는 기술"과 "이 문서의 종류"가 같은 모양으로 보인다. */}
          {doc.doc_type ? (
            <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>
              {doc.doc_type}
            </Typography>
          ) : null}
        </Box>
      ),
    },
    {
      key: "author", label: "작성자", type: "name", minWidth: "8rem",
      render: (doc) => (
        <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
          <UserAvatar person={doc.author} size="sm" />
          <Typography variant="body2" sx={KO_WORD_BREAK}>
            {doc.author?.display_name || "-"}
          </Typography>
        </Stack>
      ),
    },
    {
      key: "updated_at", label: "최종 수정", type: "datetime", minWidth: "9rem",
      render: (doc) => fmtDateTimeCompact(doc.updated_at),
    },
    {
      /* 첨부와 댓글이 있다는 사실은 **문서를 고르는 근거**다. 열어 봐야 아는 값이면
         목록에서 못 고른다. 0 은 안 그린다 — 대부분이 0 이라 그리면 소음이다. */
      key: "counts", label: "첨부, 댓글", type: "enum", minWidth: "8rem",
      render: (doc) => {
        const c = doc.counts || {};
        const parts = [];
        if (c.attachments) parts.push(`첨부 ${c.attachments}`);
        if (c.comments) parts.push(`댓글 ${c.comments}`);
        if (c.relations) parts.push(`관련 ${c.relations}`);
        return parts.length ? (
          <Typography variant="caption" color="text.secondary">{parts.join(", ")}</Typography>
        ) : "";
      },
    },
    {
      key: "more", label: "작업", type: "actions", width: "6.5rem",
      render: (doc) => (
        <OverflowMenu
          ariaLabel={`${doc.title} 작업`}
          items={[
            { label: "문서 열기", onClick: () => openDoc(doc) },
            {
              label: "휴지통으로 보내기",
              onClick: async () => {
                const ok = await confirm(
                  "휴지통에서 되살릴 수 있습니다. 판 이력과 댓글은 그대로 남습니다.",
                  { title: `${doc.title}을(를) 휴지통으로 보낼까요?`, confirmLabel: "보내기" },
                );
                if (ok) archive.mutate(doc.id);
              },
            },
          ]}
        />
      ),
    },
  ], [archive, confirm, favorite, openDoc]);

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

  const hasFilter = Boolean(q || tags.length || author || folderId || view);

  return (
    <>
      <PageHeader
        crumbRoot="팀 업무"
        area="문서"
        /* 사이드바 항목과 **같은 낱말**이어야 한다 (S14 · C2). 「문서」를 눌러 왔는데 화면
           제목이 「지식 공간」이면 사용자는 다른 데로 왔다고 읽는다. */
        title="문서"
        description="팀이 쌓아 온 문서를 찾아보고 새로 씁니다."
        actions={(
          <>
            {/* 휴지통은 공용 화면이고 문서 조건으로 열린다 (지시 22.7). 문서 전용 휴지통을
                따로 만들면 티켓과 문서를 각각 다른 곳에서 되살리게 된다. */}
            <Button href="#/team-docs/trash?kind=document">휴지통</Button>
            <Button
              variant="primary"
              onClick={() => setNewDoc({
                title: "", space_id: spaceId || items[0].id, folder_id: folderId || "",
                tags: [], template: "blank",
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
              onClick: () => setQuery({ view: null, folder: null, page: null }),
            },
            {
              key: "recent", label: "최근 수정", value: summaryRow.recent,
              note: "최근 24시간",
              active: sort === "recent" && view === VIEW.all,
              onClick: () => setQuery({ view: null, sort: "recent", page: null }),
            },
            {
              key: "favorites", label: "즐겨찾기", value: summaryRow.favorites,
              active: view === VIEW.favorites,
              onClick: () => setQuery({ view: VIEW.favorites, page: null }),
            },
            {
              key: "drafts", label: "내 초안", value: summaryRow.drafts,
              note: "아직 고치지 않은 내 문서",
              active: view === VIEW.drafts,
              onClick: () => setQuery({ view: VIEW.drafts, page: null }),
            },
          ]}
        />
      ) : null}

      <Box
        sx={{
          display: "grid",
          alignItems: "start",
          gap: 2,
          gridTemplateColumns: {
            xs: "1fr",
            /* 🔴 17rem 이었다. 그 폭에서는 탐색기 안의 줄이 **45px 잘렸다** — 「공간 추가」·
               「폴더 추가」·「태그 관리」가 판 밖으로 나가고 `overflow:hidden` 이라 스크롤로도
               못 봤다(실브라우저 캡처의 `content_clipped`). 제목과 조작기가 한 줄에 서는
               칸이라 그만큼 넓어야 한다. */
            md: "20rem minmax(0, 1fr)",
            /* 곁열은 **넓을 때만** 선다 (지시 22.4). 1366 에서 세 칸을 우기면 목록이
               좁아져 제목이 두 줄로 접힌다. */
            xl: "20rem minmax(0, 1fr) 19rem",
          },
        }}
      >
        <Explorer
          spaces={items}
          spaceId={spaceId}
          tree={tree}
          folderId={folderId}
          view={view}
          tagVocab={tagRows}
          selectedTags={tags}
          summary={summaryRow}
          onView={(next) => setQuery({ view: next || null, page: null })}
          onSpace={(next) => setQuery({ space: next || null, folder: null, page: null })}
          onFolder={(next) => setQuery({ folder: next || null, page: null })}
          onToggleTag={(name) => setQuery({
            tags: tags.includes(name) ? tags.filter((t) => t !== name) : [...tags, name],
            page: null,
          })}
          onNewFolder={() => setFolderForm(true)}
          onDeleteFolder={(folder) => removeFolder.mutate(folder.id)}
          onReorderFolder={({ id, beforeId, afterId }) =>
            moveFolder.mutate({ id, before_id: beforeId, after_id: afterId })}
          onNewSpace={canMakeSpace ? () => setSpaceForm(true) : null}
          onManageTags={() => setTagForm(true)}
        />

        <Box sx={{ minWidth: 0 }}>
          <FilterSurface>
            <ToolbarRow>
              <SearchBox
                value={q}
                onSearch={commitSearch}
                placeholder="문서 제목, 내용 검색"
                ariaLabel="문서 검색"
              />
            </ToolbarRow>
            <FilterRow>
              {/* 다중 선택은 AND 다 — 고른 태그를 전부 가진 문서로 좁힌다(§11.3).
                  값은 이름 배열이라 문서 저장 계약과 같다(slug 를 화면이 따로 안 다룬다). */}
              <TagPicker
                label="기술 태그"
                value={tags}
                onChange={(next) => setQuery({ tags: next, page: null })}
              />
              {/* 사람은 **기수가 무한히 자라는 대상**이다 — 사람이 늘면 후보도 는다. 평범한
                  드롭다운으로 두면 이름을 알면서도 목록을 눈으로 훑게 된다(C2 · R-5).
                  공간 고르개가 같은 이유로 이 부품을 쓴다. */}
              <EntityCombobox
                label="작성자"
                allLabel="전체"
                value={author}
                onChange={(v) => setQuery({ author: v || null, page: null })}
                options={authors}
              />
              <FilterSelect
                label="정렬"
                value={sort}
                onChange={(v) => setQuery({ sort: v, page: null })}
                options={SORTS}
              />
              {hasFilter ? (
                <FilterActions>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setQuery({
                      q: null, tags: [], author: null, folder: null, view: null, page: null,
                    })}
                  >
                    필터 지우기
                  </Button>
                </FilterActions>
              ) : null}
            </FilterRow>
          </FilterSurface>

          {/* 「최근 열람」은 쪽을 안 나눈다 — 사람마다 다르고 길지 않다. 그 사실을 건수
              줄이 그대로 말한다. */}
          <ResultLine total={total} />

          {documents.isError ? (
            <ErrorState error={documents.error} onRetry={() => documents.refetch()} />
          ) : (
            <Card>
              {!documents.isLoading && rows.length === 0 ? (
                <ListEmptyState
                  filtered={hasFilter}
                  onClear={() => setQuery({
                    q: null, tags: [], author: null, folder: null, view: null, page: null,
                  })}
                  clearLabel="검색, 필터 지우기"
                  filteredTitle="조건에 맞는 문서가 없습니다"
                  filteredHelp="검색어와 태그, 작성자 조건을 풀면 전체 문서가 다시 나타납니다."
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
                  virtualize={rows.length > 60 ? {} : undefined}
                />
              )}
            </Card>
          )}

          {!documents.isLoading && !documents.isError && !listed ? (
            <Pager
              page={page}
              pageSize={PAGE_SIZE}
              total={documents.data?.total}
              onPage={(next) => setQuery({ page: next > 1 ? next : null }, { keepPage: true })}
            />
          ) : null}
        </Box>

        <Box sx={{ display: { xs: "none", xl: "block" }, minWidth: 0 }}>
          <Rail
            recent={recent.data?.items || []}
            favorites={(rows || []).filter((d) => d.is_favorite).slice(0, 5)}
            templates={templateRows}
            onOpen={openDoc}
            onTemplate={(id) => setNewDoc({
              title: "", space_id: spaceId || items[0].id, folder_id: folderId || "",
              tags: [], template: id,
            })}
          />
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

      <TagManager
        open={tagForm}
        tags={tagRows}
        canManage={canManageTags}
        busy={addTag.isPending || renameTag.isPending || removeTag.isPending}
        onClose={() => setTagForm(false)}
        onAdd={(name, done) => addTag.mutate(name, { onSuccess: done })}
        onRename={(tag, name, done) =>
          renameTag.mutate({ id: tag.id, name }, { onSuccess: done })}
        onRemove={async (tag) => {
          /* 몇 건에서 떼어지는지를 **묻는 문장에** 넣는다. 0건인 태그를 지우는 것과 서른
             건에서 떼는 것은 다른 일이고, 확인 문구가 그 차이를 말해야 한다. */
          const used = tag.document_count ?? 0;
          const ok = await confirm(
            used
              ? `문서 ${used}건에서 이 태그가 떨어집니다. 문서 자체는 그대로 남습니다.`
              : "이 태그를 쓰는 문서가 없습니다.",
            { title: `${tag.name} 태그를 삭제할까요?`, confirmLabel: "삭제", danger: used > 0 },
          );
          if (ok) removeTag.mutate(tag.id);
        }}
      />

      <NewDocumentModal
        open={Boolean(newDoc)}
        initial={newDoc || { title: "", space_id: "", folder_id: "", tags: [], template: "blank" }}
        spaces={items}
        folders={folders}
        templates={templateRows}
        busy={createDocument.isPending}
        onClose={() => setNewDoc(null)}
        onSubmit={(values) => createDocument.mutate({
          space_id: values.space_id,
          title: values.title.trim(),
          folder_id: values.folder_id || null,
          template: values.template || null,
          tag_names: values.tags && values.tags.length ? values.tags : null,
        })}
      />
    </>
  );
}

export default Knowledge;
