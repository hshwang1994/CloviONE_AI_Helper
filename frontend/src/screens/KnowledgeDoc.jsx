import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import StarRoundedIcon from "@mui/icons-material/StarRounded";
import StarOutlineRoundedIcon from "@mui/icons-material/StarOutlineRounded";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  ErrorState,
  MetaBar,
  Modal,
  ModalFooter,
  OverflowMenu,
  PageHeader,
  Section,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { DetailLayout } from "../ui/DetailLayout.jsx";
import { GRID_GAP } from "../ui/density.js";
import { DocComments } from "./DocComments.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { ProjectPicker } from "../ui/ProjectPicker.jsx";
import { TagPicker } from "../ui/TagPicker.jsx";
import { FONT_WEIGHT, KO_WORD_BREAK } from "../ui/theme.js";
import { fmtDateTimeCompact, objectParticle } from "../lib/format.js";
import { useListReturn } from "../lib/listReturn.js";
import { useCategories } from "./knowledge/queries.js";
import { PROJECT_NONE, PROJECT_UNASSIGNED_LABEL } from "./knowledge/constants.js";
import { celebrateCreated } from "../ui/celebrate.js";
import { ImageLightbox, useLightbox } from "../ui/ImageLightbox.jsx";

/* 문서 한 건 — 본문 편집 · 문서 정보 · 관계 · 첨부 · 댓글 (지시 22.6).
 *
 * ## 본문이 화면을 실제로 쓴다
 *
 * 예전 이 화면은 탭 둘(본문 · 이력)에 카드 하나였다. 본문 폭은 공통 상세 폭 문제 그대로라
 * 오른쪽이 비었고, 서버에 있는 기능 절반이 화면에 없었다 — 이동 · 관계 · 첨부 · 판 하나
 * 열어 보기가 전부 API 로만 존재했다.
 *
 * 지금은 두 열이다. 왼쪽이 편집기, 오른쪽이 「이 문서에 대한 것」이고, 둘 다 `fr` 트랙이라
 * 어느 폭에서도 오른쪽이 안 빈다(`ui/DetailLayout.jsx`). 좁은 화면에서는 곁열이 본문
 * 아래로 흐른다.
 *
 * ## 편집기를 늦게 싣는다 (D-198)
 *
 * TipTap 과 ProseMirror 는 무겁다. 문서를 여는 사람만 받으면 되고, 목록만 보는 사람의
 * 첫 로딩에 그 무게를 얹을 이유가 없다. **`React.lazy` 로 들여오는 것이 계약이고**
 * `knowledge-editor-lazy.test.jsx` 가 그것을 코드로 확인한다.
 *
 * ## 이력 화면이 「변경 없음」으로 차지 않게 한다
 *
 * 서버는 본문이 그대로면 판을 안 쌓고 `created_version: false` 로 답한다. 그 사실을
 * 화면이 구별해서 말한다 — 「저장했습니다」와 「저장했고 이력에 남겼습니다」는 다른 일이다.
 *
 * ## 되돌리기는 잠금 값을 함께 보낸다
 *
 * 되돌리기는 남의 편집을 통째로 덮는 동작이다. 이력을 열어 둔 사이에 누군가 저장했으면
 * 서버가 409 로 막고, 화면은 그 사실을 그대로 전한다 — 조용히 덮으면 사라진 사람은
 * 자기 글이 사라진 것도 모른다. */

const BlockEditor = React.lazy(() =>
  import("../ui/BlockEditor.jsx").then((m) => ({ default: m.BlockEditor })));

const CHANGE_LABEL = { added: "추가", removed: "삭제", changed: "수정", moved: "이동" };
const CHANGE_TONE = { added: "ok", removed: "danger", changed: "info", moved: "neutral" };

/** 관계 종류. 서버의 `DREL_KINDS` 와 같은 목록이다 — 갈라지면 만들 때 422 가 난다. */
const RELATION_KINDS = [
  { value: "relates_to", label: "관련 문서" },
  { value: "references", label: "참조하는 문서" },
  { value: "supersedes", label: "대체하는 문서" },
];

function useDocument(id) {
  return useQuery({
    queryKey: ["knowledge", "document", id],
    queryFn: () => api(`/api/knowledge/documents/${id}`),
    enabled: Boolean(id),
  });
}

function useVersions(id) {
  return useQuery({
    queryKey: ["knowledge", "versions", id],
    queryFn: () => api(`/api/knowledge/documents/${id}/versions`),
    enabled: Boolean(id),
  });
}

function humanSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function VersionDiff({ documentId, base, target }) {
  const diff = useQuery({
    queryKey: ["knowledge", "diff", documentId, base, target],
    queryFn: () =>
      api(`/api/knowledge/documents/${documentId}/diff?base=${base}&target=${target}`),
    enabled: Boolean(documentId && base && target),
  });

  if (diff.isLoading) return <Skeleton kind="section" lines={4} />;
  if (diff.isError) return <ErrorState error={diff.error} onRetry={() => diff.refetch()} />;

  const changes = diff.data?.changes || [];
  if (!changes.length) {
    return (
      <EmptyState
        title="두 판의 본문이 같습니다."
        help="고른 두 판 사이에 바뀐 문단이 없습니다."
      />
    );
  }

  return (
    <Stack spacing={1} component="ul" sx={{ listStyle: "none", p: 0, m: 0 }}>
      {changes.map((change) => (
        <Box
          key={`${change.block_id}-${change.change}`}
          component="li"
          sx={(theme) => ({
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: 1,
            p: 1.5,
          })}
        >
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
            <Badge value={CHANGE_LABEL[change.change] || change.change}
                   kind={CHANGE_TONE[change.change]} />
          </Stack>
          {change.before && (
            <Typography sx={{ ...KO_WORD_BREAK, textDecoration: "line-through" }}
                        color="text.secondary">
              {change.before}
            </Typography>
          )}
          {change.after && (
            <Typography sx={KO_WORD_BREAK}>{change.after}</Typography>
          )}
        </Box>
      ))}
    </Stack>
  );
}

/* 인용을 눌러서 온 자리로 데려간다 (S10).
 *
 * 주소의 `?block=<블록 id>` 를 읽어 그 문단까지 스크롤하고 잠깐 표시한다. 블록 id 는
 * 판이 올라도 안 바뀌므로(D-198) 어제 만든 인용이 오늘도 같은 문장을 가리킨다.
 *
 * **못 찾으면 아무 일도 안 한다.** 문서 맨 위에 그대로 서는 것이 맞다 — 그 블록이 지워진
 * 문서에서 엉뚱한 문단을 표시하면 사람은 그것을 인용된 문장으로 읽는다. */
function useBlockAnchor(blockId, ready) {
  React.useEffect(() => {
    if (!blockId || !ready) return undefined;
    let attempts = 0;
    let timer = 0;
    const look = () => {
      const target = document.querySelector(`[data-block-id="${CSS.escape(blockId)}"]`);
      if (target) {
        target.scrollIntoView({
          block: "center",
          behavior: "smooth",
        });
        target.classList.add("k-cited");
        window.setTimeout(() => target.classList.remove("k-cited"), 2400);
        return;
      }
      if (attempts++ < 20) timer = window.setTimeout(look, 150);
    };
    look();
    return () => window.clearTimeout(timer);
  }, [blockId, ready]);
}

/** 곁열의 「문서 정보」 한 줄. 라벨이 먼저다 — 찾는 이름을 알고 보는 자리다. */
function InfoRow({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: "5.5rem minmax(0, 1fr)", gap: 1, py: 0.375 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Box sx={{ minWidth: 0, ...KO_WORD_BREAK }}>{children}</Box>
    </Box>
  );
}

/* 첨부 — 서버에 있는데 화면이 없던 기능 (지시 22.6).
 *
 * 파일은 우리 저장소에 있고 우리 라우트로 나간다. 인증이 걸린 같은 출처라 링크 하나면
 * 쿠키가 함께 간다.
 *
 * ## 그림은 보여 준다
 *
 * 예전에는 그림도 파일 이름 한 줄이었다. 문서를 열어 놓고 붙은 그림을 훑을 방법이 없고,
 * 하나 보려면 새 탭을 열어야 했다 — 티켓 화면은 같은 첨부를 이미 썸네일과 라이트박스로
 * 그리고 있었으므로 같은 첨부가 화면마다 다르게 다뤄지고 있었던 것이다.
 * 그림인지는 응답의 `mime_type` 으로 안다. 서버에 새 칸을 만들지 않는다. */
const IMAGE_MIME = /^image\//;

function Attachments({ documentId, items, onChanged, readOnly = false }) {
  const toast = useToast();
  const confirm = useConfirm();
  const inputRef = React.useRef(null);
  const lb = useLightbox();

  const images = items.filter((f) => IMAGE_MIME.test(f.mime_type || ""));
  const others = items.filter((f) => !IMAGE_MIME.test(f.mime_type || ""));
  const slides = images.map((f) => ({
    src: `/api/knowledge/attachments/${f.id}/content`, title: f.filename,
  }));

  const upload = useMutation({
    mutationFn: async (picked) => {
      const failed = [];
      for (const file of picked) {
        try {
          const form = new FormData();
          form.append("file", file);
          await api(`/api/knowledge/documents/${documentId}/attachments`,
                    { method: "POST", body: form });
        } catch {
          failed.push(file.name);
        }
      }
      return { failed };
    },
    onSuccess: ({ failed }) => {
      onChanged();
      if (failed.length) {
        toast(`파일 ${failed.length}개를 올리지 못했습니다: ${failed.join(", ")}`, "error");
      } else {
        toast("파일을 첨부했습니다.");
      }
    },
    onError: (e) => toast(e.message, "error"),
  });

  const remove = useMutation({
    mutationFn: (attachmentId) =>
      api(`/api/knowledge/attachments/${attachmentId}`, { method: "DELETE" }),
    onSuccess: () => { onChanged(); toast("첨부를 뗐습니다."); },
    onError: (e) => toast(e.message, "error"),
  });

  return (
    <Section
      title={`첨부 ${items.length}`}
      /* 휴지통 문서에는 올릴 자리를 안 만든다 — 서버가 404 로 막으므로 단추는 언제나
         실패하고, 사용자는 파일을 고르고 나서야 그것을 안다. */
      action={readOnly ? null : (
        <Button size="small" variant="ghost" onClick={() => inputRef.current?.click()}>
          파일 올리기
        </Button>
      )}
    >
      <Box
        component="input"
        ref={inputRef}
        type="file"
        multiple
        sx={{ display: "none" }}
        onChange={(e) => {
          /* `FileList` 는 살아 있는 목록이라 **동기적으로** 배열로 뜬다. 아래에서 입력을
             비우는 순간 그 목록도 비워지므로, 참조를 그대로 넘기면 아무것도 안 올라가면서
             성공 안내만 뜬다(티켓 첨부가 실제로 밟은 자리다). */
          const picked = Array.from(e.target.files || []);
          e.target.value = "";
          if (picked.length) upload.mutate(picked);
        }}
      />
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
          이 문서에 붙은 파일이 없습니다.
        </Typography>
      ) : (
        <Stack spacing={1.5}>
          {images.length ? (
            <Box sx={{
              display: "grid", gap: 1,
              gridTemplateColumns: "repeat(auto-fill, minmax(7rem, 1fr))",
            }}>
              {images.map((file, i) => (
                <Box
                  key={file.id}
                  component="button"
                  type="button"
                  onClick={() => lb.open(slides, i)}
                  aria-label={`${file.filename} 크게 보기`}
                  sx={{
                    p: 0, border: 0, background: "none", cursor: "zoom-in",
                    display: "block", width: "100%", minWidth: 0,
                    "&:focus-visible": {
                      outline: "3px solid", outlineColor: "primary.main", outlineOffset: 2,
                    },
                  }}
                >
                  {/* contain 이다 — 올린 그림을 잘라 보여 주지 않는다(§5). */}
                  <Box
                    component="img"
                    src={`/api/knowledge/attachments/${file.id}/content`}
                    alt={file.filename}
                    loading="lazy"
                    decoding="async"
                    sx={{
                      width: "100%", aspectRatio: "4 / 3", objectFit: "contain",
                      borderRadius: 2, border: 1, borderColor: "divider",
                      bgcolor: "action.hover", display: "block",
                    }}
                  />
                </Box>
              ))}
            </Box>
          ) : null}
          {others.map((file) => (
            <Stack key={file.id} direction="row" alignItems="center" spacing={1}>
              <Link
                href={`/api/knowledge/attachments/${file.id}/content`}
                target="_blank"
                rel="noreferrer"
                sx={{ ...KO_WORD_BREAK, flex: 1, minWidth: 0 }}
              >
                {file.filename}
              </Link>
              <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                {humanSize(file.size_bytes)}
              </Typography>
              {/* 🔴 `readOnly` 가 「파일 올리기」만 걷고 이 「삭제」는 놔뒀었다. 서버는
                  휴지통 문서의 첨부 떼기도 404 로 막으므로(`delete_attachment`), 남겨 두면
                  확인 창까지 지나고 나서야 「문서를 찾지 못했습니다」가 뜬다. */}
              {readOnly ? null : (
              <Button
                size="small"
                variant="ghost"
                onClick={async () => {
                  const ok = await confirm(
                    "이 문서에서 파일을 뗍니다. 파일 자체는 저장소에 남습니다.",
                    { title: `${file.filename}${objectParticle(file.filename)} 뗄까요?`, confirmLabel: "떼기" },
                  );
                  if (ok) remove.mutate(file.id);
                }}
              >
                삭제
              </Button>
              )}
            </Stack>
          ))}
          {/* 그림도 뗄 수 있어야 한다. 격자에는 단추를 겹치지 않고 이름 줄로 함께 센다 —
              작은 썸네일 위의 겹친 단추는 좁은 화면에서 그림을 가린다. */}
          {images.map((file) => (
            <Stack key={file.id} direction="row" alignItems="center" spacing={1}>
              <Link
                href={`/api/knowledge/attachments/${file.id}/content`}
                target="_blank"
                rel="noreferrer"
                sx={{ ...KO_WORD_BREAK, flex: 1, minWidth: 0 }}
              >
                {file.filename}
              </Link>
              <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                {humanSize(file.size_bytes)}
              </Typography>
              {/* 🔴 `readOnly` 가 「파일 올리기」만 걷고 이 「삭제」는 놔뒀었다. 서버는
                  휴지통 문서의 첨부 떼기도 404 로 막으므로(`delete_attachment`), 남겨 두면
                  확인 창까지 지나고 나서야 「문서를 찾지 못했습니다」가 뜬다. */}
              {readOnly ? null : (
              <Button
                size="small"
                variant="ghost"
                onClick={async () => {
                  const ok = await confirm(
                    "이 문서에서 파일을 뗍니다. 파일 자체는 저장소에 남습니다.",
                    { title: `${file.filename}${objectParticle(file.filename)} 뗄까요?`, confirmLabel: "떼기" },
                  );
                  if (ok) remove.mutate(file.id);
                }}
              >
                삭제
              </Button>
              )}
            </Stack>
          ))}
        </Stack>
      )}
      <ImageLightbox {...lb.props} />
    </Section>
  );
}

/* 관련 문서와 역링크 — 서버에 있는데 화면이 없던 기능 (지시 22.6 · 22.8).
 *
 * **양쪽이 다 보여야 잇는다**(서버가 그렇게 판정한다). 그래서 후보는 내가 볼 수 있는
 * 문서 목록에서 고르고, 목록에 없는 문서는 이을 수 없다 — 그것이 맞다. */
function Relations({ documentId, relations, backlinks, tickets, onChanged, readOnly = false }) {
  const toast = useToast();
  const [open, setOpen] = React.useState(false);
  const [target, setTarget] = React.useState("");
  const [kind, setKind] = React.useState("relates_to");
  const [q, setQ] = React.useState("");

  const candidates = useQuery({
    queryKey: ["knowledge", "documents", "relation-candidates", q],
    queryFn: () => api(`/api/knowledge/documents?limit=20${q ? `&q=${encodeURIComponent(q)}` : ""}`),
    enabled: open,
  });

  const add = useMutation({
    mutationFn: (body) =>
      api(`/api/knowledge/documents/${documentId}/relations`, { method: "POST", body }),
    onSuccess: () => { onChanged(); setOpen(false); setTarget(""); toast("문서를 이었습니다."); },
    onError: (e) => toast(e.message, "error"),
  });

  const drop = useMutation({
    mutationFn: (body) =>
      api(`/api/knowledge/documents/${documentId}/relations`, { method: "DELETE", body }),
    onSuccess: () => { onChanged(); toast("연결을 끊었습니다."); },
    onError: (e) => toast(e.message, "error"),
  });

  const rows = candidates.data?.items || [];

  return (
    <Section
      title={`관련 문서 ${relations.length}`}
      action={readOnly ? null : <Button size="small" variant="ghost" onClick={() => setOpen(true)}>문서 잇기</Button>}
    >
      <Stack spacing={1}>
        {relations.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
            이어 둔 문서가 없습니다.
          </Typography>
        ) : relations.map((rel) => (
          <Stack key={`${rel.document_id}-${rel.kind}`} direction="row" alignItems="center" spacing={1}>
            <Link href={`#/knowledge/${rel.document_id}`} sx={{ ...KO_WORD_BREAK, flex: 1, minWidth: 0 }}>
              {rel.title || rel.document_id}
            </Link>
            <Chip size="small" variant="outlined" label={rel.label || rel.kind} />
            <Button
              size="small"
              variant="ghost"
              onClick={() => drop.mutate({ to_document_id: rel.document_id, kind: rel.kind })}
            >
              삭제
            </Button>
          </Stack>
        ))}

        {/* 이 문서가 가리키는 티켓 (지시 22.8). 본문에서 티켓을 언급하면 여기 선다 —
            **볼 수 있는 티켓만** 나온다(문서가 보인다고 그 티켓이 보이는 것은 아니다). */}
        {tickets.length > 0 ? (
          <Box sx={{ mt: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold, mb: 0.5 }}>
              관련 티켓 {tickets.length}
            </Typography>
            <Stack spacing={0.5}>
              {tickets.map((t) => (
                <Link key={t.ticket_id} href={`#/tickets/${t.ticket_id}`} sx={KO_WORD_BREAK}>
                  {t.key ? `${t.key} ${t.title}` : t.title}
                </Link>
              ))}
            </Stack>
          </Box>
        ) : null}

        {backlinks.length > 0 ? (
          <Box sx={{ mt: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: FONT_WEIGHT.semibold, mb: 0.5 }}>
              이 문서를 인용한 문서 {backlinks.length}
            </Typography>
            <Stack spacing={0.5}>
              {backlinks.map((link) => (
                <Link
                  key={`${link.document_id}-${link.block_id}`}
                  href={`#/knowledge/${link.document_id}?block=${link.block_id}`}
                  sx={KO_WORD_BREAK}
                >
                  {link.title || link.document_id}
                </Link>
              ))}
            </Stack>
          </Box>
        ) : null}
      </Stack>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="문서 잇기"
        footer={(
          <ModalFooter
            onCancel={() => setOpen(false)}
            onSubmit={target ? () => add.mutate({ to_document_id: target, kind }) : undefined}
            submitLabel="잇기"
            busy={add.isPending}
          />
        )}
      >
        <Stack spacing={2}>
          <TextField
            label="문서 찾기"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            InputLabelProps={{ shrink: true }}
            helperText="내가 볼 수 있는 문서만 이을 수 있습니다."
            fullWidth
          />
          <TextField
            select
            label="이을 문서"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            InputLabelProps={{ shrink: true }}
            fullWidth
          >
            {rows.filter((d) => d.id !== documentId).map((d) => (
              <MenuItem key={d.id} value={d.id}>{d.title}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="관계"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            InputLabelProps={{ shrink: true }}
            fullWidth
          >
            {RELATION_KINDS.map((k) => (
              <MenuItem key={k.value} value={k.value}>{k.label}</MenuItem>
            ))}
          </TextField>
        </Stack>
      </Modal>
    </Section>
  );
}

export function KnowledgeDoc() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  /* 「목록으로」는 **주소**로 돌아간다 — 조건과 쪽과 스크롤이 살아 있는 그 목록이다
     (`lib/listReturn.js`). 경로만 알고 돌아가면 사용자가 방금 걸어 둔 조건을 다시 만든다. */
  const location = useLocation();
  const backTo = useListReturn(location.state?.from, "/knowledge");

  const doc = useDocument(id);
  const versions = useVersions(id);
  const categoriesQuery = useCategories();

  const [title, setTitle] = React.useState("");
  const [body, setBody] = React.useState(null);
  const [tags, setTags] = React.useState([]);
  const [categoryId, setCategoryId] = React.useState("");
  const [compareTo, setCompareTo] = React.useState(null);
  const [history, setHistory] = React.useState(false);
  const [moving, setMoving] = React.useState(false);
  const [moveProjectId, setMoveProjectId] = React.useState("");

  /* 서버가 준 값을 편집 상태의 출발점으로 삼는다. 문서 id 가 바뀔 때만 다시 잡는다 —
   * 매 응답마다 덮으면 사용자가 타이핑하는 중에 화면이 되감긴다. */
  React.useEffect(() => {
    if (!doc.data) return;
    setTitle(doc.data.title);
    setBody(doc.data.current?.body || null);
    setTags((doc.data.tags || []).map((t) => t.name));
    setCategoryId(doc.data.category?.id || "");
    setMoveProjectId(doc.data.project?.id || "");
    setCompareTo(null);
  }, [doc.data?.id]);

  useBlockAnchor(params.get("block"), Boolean(body));

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["knowledge", "document", id] });
    qc.invalidateQueries({ queryKey: ["knowledge", "documents"] });
  };

  const save = useMutation({
    mutationFn: (payload) =>
      api(`/api/knowledge/documents/${id}`, { method: "PUT", body: payload }),
    onSuccess: (result) => {
      refresh();
      qc.invalidateQueries({ queryKey: ["knowledge", "versions", id] });
      toast(
        result.created_version
          ? "저장했고 새 판을 이력에 남겼습니다."
          : "저장했습니다. 본문이 그대로라 새 판은 만들지 않았습니다.",
      );
      /* 🔴 **만든 순간이 아니라 저장한 순간이다** (사용자 지적). 「새 문서」는 빈 장을
         하나 세우고 편집기로 들여보내는 것뿐이라, 거기서 축하하면 아직 아무것도 안 쓴
         사람에게 종잇조각이 쏟아진다.

         그리고 **새 판이 실제로 남았을 때만**이다 — 서버가 본문이 그대로면
         `created_version` 을 안 준다(바로 위 문구가 그 사실을 말한다). 안 바뀐 저장을
         축하하면 저장 단추를 두 번 누른 사람이 두 번 축하받는다. */
      if (result.created_version) celebrateCreated();
    },
    onError: (e) => toast(e.message, "error"),
  });

  /* 즐겨찾기는 **내 목록**을 고치는 일이다 — 문서를 고치는 것이 아니라서 볼 수 있는
   * 사람이면 담을 수 있고, 담아도 남의 화면은 달라지지 않는다. */
  const favorite = useMutation({
    mutationFn: (on) =>
      api(`/api/knowledge/documents/${id}/favorite?on=${on ? "true" : "false"}`,
        { method: "POST" }),
    onSuccess: (result) => {
      refresh();
      toast(result.is_favorite ? "즐겨찾기에 담았습니다." : "즐겨찾기에서 뺐습니다.");
    },
    onError: (e) => toast(e.message, "error"),
  });

  const move = useMutation({
    mutationFn: ({ project_id }) =>
      api(`/api/knowledge/documents/${id}/move`, {
        method: "POST",
        body: { project_id: project_id || null, base_version: doc.data?.version },
      }),
    onSuccess: (_result, variables) => {
      refresh();
      setMoving(false);
      toast(
        variables.project_id && variables.project_id !== doc.data?.project?.id
          ? "문서를 다른 프로젝트로 옮겼습니다. 그 프로젝트를 볼 수 있는 사람만 이제 이 문서를 봅니다."
          : "문서를 옮겼습니다. 볼 수 있는 사람은 그대로입니다.",
      );
    },
    onError: (e) => toast(e.message, "error"),
  });

  const archive = useMutation({
    mutationFn: () => api(`/api/knowledge/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["knowledge", "documents"] });
      toast("문서를 휴지통으로 보냈습니다. 휴지통에서 되살릴 수 있습니다.");
      navigate(backTo);
    },
    onError: (e) => toast(e.message, "error"),
  });

  const restore = useMutation({
    mutationFn: (versionNo) =>
      api(`/api/knowledge/documents/${id}/versions/${versionNo}/restore`, {
        method: "POST",
        body: { base_version: doc.data?.version },
      }),
    onSuccess: () => {
      refresh();
      qc.invalidateQueries({ queryKey: ["knowledge", "versions", id] });
      toast("옛 판의 본문으로 새 판을 만들었습니다. 이력은 그대로 남아 있습니다.");
    },
    onError: (e) => toast(e.message, "error"),
  });

  /* 🔴 **휴지통에서 온 사람이 여기서 되살릴 수 있어야 한다.**
   *
   * 서버는 이 경로를 진작에 갖고 있었는데(`POST .../restore`) 화면에 입구가 없었다. 문서
   * 목록에서는 보관된 문서가 안 보이므로, 휴지통에서 제목을 눌러 여기까지 온 사람에게는
   * 되살리기가 **이 화면 말고 갈 곳이 없다.** */
  const unarchive = useMutation({
    mutationFn: () => api(`/api/knowledge/documents/${id}/restore`, { method: "POST" }),
    onSuccess: () => {
      refresh();
      qc.invalidateQueries({ queryKey: ["trash"] });
      toast("복원했습니다. 문서 목록에서 다시 볼 수 있습니다.", "success");
    },
    onError: (e) => toast(e.message, "error"),
  });

  /* 본문에 그림을 넣는 길 — **첨부로 올리고 주소만 본문에 남긴다** (D4 · 지시 22.6).
   *
   * 바이트를 본문에 넣지 않는다: `data:` 이미지는 판마다 통째로 복사되고, 서버가 그 스킴을
   * 거절한다(app/knowledge/blocks.py). 첨부로 올리면 그림이 첨부 목록에도 함께 서서
   * 「본문에 있는 그림」과 「붙인 파일」이 갈라지지 않는다.
   *
   * 파일 고르기는 사용자가 취소할 수 있다. 그때는 아무 일도 안 일어나야 하므로 약속이
   * 조용히 끝난다 — 오류로 만들면 취소가 실패로 보인다. */
  const pickImage = React.useCallback(() => new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.onchange = async () => {
      const file = (input.files || [])[0];
      if (!file) { resolve(null); return; }
      try {
        const form = new FormData();
        form.append("file", file);
        const made = await api(`/api/knowledge/documents/${id}/attachments`,
                              { method: "POST", body: form });
        refresh();
        resolve(`/api/knowledge/attachments/${made.id}/content`);
      } catch (e) {
        toast(e.message, "error");
        resolve(null);
      }
    };
    input.click();
  }), [id]);

  if (doc.isLoading) return <Skeleton kind="page" lines={5} />;
  if (doc.isError) return <ErrorState error={doc.error} onRetry={() => doc.refetch()} />;

  const data = doc.data;
  /* 🔴 **이 화면은 `archived` 를 한 번도 안 읽고 있었다.**
   *
   * 서버는 진작부터 `archived`·`archived_at`·`archiver` 를 다 실어 보냈는데
   * (`app/knowledge/router.py::_document_json`) 이 파일에는 그 낱말이 없었다. 그래서
   * 휴지통에서 제목을 눌러 온 사람에게 **평범한 살아 있는 문서**가 그대로 열렸다 —
   * 편집기, 저장 단추, 즐겨찾기, 그리고 이미 들어 있는 휴지통으로 「휴지통으로 보내기」까지.
   *
   * 그 화면에서 오타를 고치고 저장하면 「저장했습니다」가 떴다(서버 쪽 구멍은 이번에 함께
   * 막았다 — `get_writable_document_or_404`). 그리고 그 글은 보관기간이 끝나면 판째로
   * 사라진다. 사람은 저장됐다고 들었는데 그 글은 곧 없어진다. */
  const trashed = !!data.archived;
  /* 🔴 되살리기는 **아무나 못 한다** — 운영자군이거나 자기가 버린 것이어야 한다
   * (`app/knowledge/service.py::can_manage_trashed`, 서버가 403 을 낸다). 서버가 그 판정을
   * 응답에 실어 주므로(`can_manage`) 화면이 못 하는 단추를 안 그린다. 휴지통 표가 같은
   * 값으로 「권한 없음」을 적는 것과 같은 규칙이다. 값이 없는 옛 응답에서는 그리고 —
   * 서버가 어차피 다시 검사한다. */
  const canRestore = trashed && data.can_manage !== false;
  const current = data.current || {};
  const versionRows = versions.data?.items || [];
  const attachments = data.attachments || [];

  const submit = () => save.mutate({
    title,
    body,
    tag_names: tags,
    /* `null` 은 「미분류로 되돌린다」다 — 안 보내는 것과 다른 요청이고, 서버가
       `model_fields_set` 으로 그 차이를 읽는다. 이 화면은 분류 칸을 들고 있으므로
       언제나 보낸다. */
    category_id: categoryId || null,
    base_version: data.version,
  });

  const aside = (
    /* 판끼리의 간격은 `GRID_GAP`(24px) 하나다. 문서 상세는 티켓 상세와 성격이 같은
       화면이라(`DetailLayout` 을 함께 쓴다) 세로 리듬도 같아야 한다 — 예전에는 여기가
       16px, 티켓 곁열이 20px, 두 열 사이가 24px 로 셋이 갈렸다. */
    <Stack sx={{ minWidth: 0, gap: GRID_GAP }}>
      <Card>
        <Section title="문서 정보">
          <InfoRow label="작성자">
            {/* 🔴 두 가지 **다른 사실**을 함께 보여 준다.
                  · 계정 — 지금 이 문서를 누가 맡는가 (이메일이나 이름으로 이었고,
                    못 이으면 기본 계정이다)
                  · 원본 기록 — 원본에 누가 썼다고 적혀 있었나
                둘이 같으면 한 번만 쓴다. 다르면 둘 다 쓴다 — 앞엣것만 보이면 「이 사람이
                썼다」는 거짓말이 되고, 뒤엣것만 보이면 눌러도 프로필이 없는 이름이
                우리 계정처럼 읽힌다. */}
            <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
              {data.author ? <UserAvatar person={data.author} size="sm" /> : null}
              <Typography variant="body2">
                {data.author?.display_name || data.legacy_author_name || "-"}
              </Typography>
              {data.legacy_author_name
                && data.legacy_author_name !== data.author?.display_name ? (
                  <Typography variant="caption" color="text.secondary">
                    원본 기록 {data.legacy_author_name}
                  </Typography>
                ) : null}
            </Stack>
          </InfoRow>
          <InfoRow label="프로젝트">
            {/* §14.3 — 문서 상세의 프로젝트 이름은 그 프로젝트 상세로 가는 링크다.
                프로젝트가 없는 문서는 이을 곳이 없어 글자만 보인다. 그 글자는 목록의
                프로젝트 열과 **같은 상수**다 — 한쪽만 「공통 문서」라고 부르면 같은 문서가
                화면마다 다른 프로젝트에 있는 것처럼 읽힌다. */}
            {data.project ? (
              <Link href={`#/projects/${data.project.id}`}>{data.project.name}</Link>
            ) : PROJECT_UNASSIGNED_LABEL}
          </InfoRow>
          <InfoRow label="현재 판">
            {current.version_no != null ? `${current.version_no}판` : "아직 없습니다"}
          </InfoRow>
          <InfoRow label="마지막 수정">{fmtDateTimeCompact(data.updated_at)}</InfoRow>
          <InfoRow label="만든 날">{fmtDateTimeCompact(data.created_at)}</InfoRow>
        </Section>
      </Card>

      <Card>
        {/* 분류(카테고리·태그)도 **저장 버튼 하나**로 함께 저장된다. 별도 저장을 두면
            「태그만 저장했는데 본문이 안 저장됐다」가 생기고, 사용자는 어느 버튼이 무엇을
            저장하는지 못 외운다.
            🔴 그래서 **저장 단추가 없는 화면에서는 이 칸이 아무 데도 안 간다.** 휴지통
            문서에서 고르개를 그대로 두면 사용자가 분류를 바꾸고 화면을 떠났다가 「안
            바뀌었다」를 나중에 발견한다 — 오류조차 안 난다. 값만 글자로 보여 준다. */}
        {/* 읽기 전용일 때 제목이 「태그」인 이유: 분류 값은 **바로 위 맥락 줄이 이미
            말한다.** 같은 사실을 한 화면에 두 번 적으면 읽는 사람이 둘을 다른 것으로 읽는다. */}
        <Section title={trashed ? "태그" : "분류"}>
          {trashed ? (
            <Typography variant="body2" color={(data.tags || []).length ? "text.primary" : "text.secondary"}>
              {(data.tags || []).length
                ? (data.tags || []).map((t) => t.name).join(", ")
                : "태그 없음"}
            </Typography>
          ) : (
          <Stack spacing={2}>
            <TextField
              select
              size="small"
              label="분류"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              InputLabelProps={{ shrink: true }}
              fullWidth
            >
              <MenuItem value="">분류 없음</MenuItem>
              {(categoriesQuery.data?.items || []).map((c) => (
                <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
              ))}
            </TextField>
            <TagPicker
              layout="form"
              value={tags}
              onChange={setTags}
              helperText="저장을 누르면 본문과 함께 저장됩니다."
            />
          </Stack>
          )}
        </Section>
      </Card>

      <Card>
        <Relations
          documentId={id}
          relations={data.relations || []}
          backlinks={data.backlinks || []}
          tickets={data.ticket_mentions || []}
          onChanged={refresh}
          readOnly={trashed}
        />
      </Card>

      <Card>
        <Attachments documentId={id} items={attachments} onChanged={refresh} readOnly={trashed} />
      </Card>

      {/* 판을 씌우지 않는다. `CommentThread` 가 이미 자기 판과 제목(「댓글 N」)을 든다 —
          감싸면 제목이 두 번 서고 판이 판 안에 든다. 실브라우저 캡처에서 그대로 보였다. */}
      <DocComments documentId={id} readOnly={trashed} />
    </Stack>
  );

  return (
    <>
      <PageHeader
        crumbRoot="팀 업무"
        area="문서"
        title={data.title}
        actions={trashed ? (
          /* 휴지통에 있는 문서의 단추는 둘이다 — **되살리기**와 나가기. 나머지는 전부
             할 수 없는 일이라(서버가 404 로 막는다) 그려 두면 눌러 보고서야 알게 된다.
             특히 「휴지통으로 보내기」는 **이미 그 안에 있는 문서**에 대한 제안이었다. */
          <>
            {canRestore ? (
              <Button variant="primary" loading={unarchive.isPending} onClick={() => unarchive.mutate()}>
                복원
              </Button>
            ) : null}
            <Button onClick={() => setHistory((v) => !v)}>
              {history ? "이력 닫기" : `이력 ${versionRows.length}`}
            </Button>
            <Button onClick={() => navigate(backTo)}>목록으로</Button>
          </>
        ) : (
          <>
            <Button
              aria-pressed={Boolean(data.is_favorite)}
              loading={favorite.isPending}
              onClick={() => favorite.mutate(!data.is_favorite)}
            >
              {data.is_favorite
                ? <StarRoundedIcon sx={{ fontSize: "1.125rem" }} />
                : <StarOutlineRoundedIcon sx={{ fontSize: "1.125rem" }} />}
              {data.is_favorite ? "즐겨찾기 해제" : "즐겨찾기"}
            </Button>
            <Button onClick={() => setMoving(true)}>이동</Button>
            <Button onClick={() => setHistory((v) => !v)}>
              {history ? "이력 닫기" : `이력 ${versionRows.length}`}
            </Button>
            <Button variant="primary" loading={save.isPending} onClick={submit}>저장</Button>
            <OverflowMenu
              ariaLabel="문서 작업"
              items={[
                { label: "목록으로", onClick: () => navigate(backTo) },
                {
                  label: "휴지통으로 보내기",
                  onClick: async () => {
                    const ok = await confirm(
                      "휴지통에서 되살릴 수 있습니다. 판 이력과 댓글은 그대로 남습니다.",
                      { title: "이 문서를 휴지통으로 보낼까요?", confirmLabel: "보내기" },
                    );
                    if (ok) archive.mutate();
                  },
                },
              ]}
            />
          </>
        )}
      />

      {/* 🔴 **이 문서가 휴지통에 있다는 사실을 화면이 말한다.**
          누가 언제 버렸는지까지 적는다 — 그 둘이 「내가 되살릴 수 있는가」의 근거이기도 하다
          (`can_manage_trashed` 가 `archived_by` 를 본다). */}
      {trashed ? (
        <Callout
          tone="warn"
          title="이 문서는 휴지통에 있습니다"
          sx={{ mb: 2 }}
          action={canRestore ? (
            <Button size="sm" variant="primary" loading={unarchive.isPending}
              onClick={() => unarchive.mutate()}>복원</Button>
          ) : null}
        >
          {data.archiver?.display_name
            ? `${data.archiver.display_name}님이 ${fmtDateTimeCompact(data.archived_at)}에 버렸습니다. 보관기간이 지나면 판 이력과 댓글까지 함께 영구 삭제됩니다.`
            : "보관기간이 지나면 판 이력과 댓글까지 함께 영구 삭제됩니다. 계속 쓰려면 먼저 복원하세요."}
          {canRestore ? "" : " 되살리려면 이 문서를 버린 사람이나 운영자에게 요청하세요."}
        </Callout>
      ) : null}

      {/* 상단 맥락 — 「이 문서가 어디에 있고 지금 몇 판인가」 (지시 22.6). 본문을 읽다가
          확인하려고 곁열 끝까지 갔다 오지 않게 한 줄로 눕힌다. */}
      <MetaBar
        ariaLabel="문서 맥락"
        sx={{ mb: 2 }}
        items={[
          {
            key: "project", label: "프로젝트", rank: "primary",
            value: data.project
              ? <Link href={`#/projects/${data.project.id}`}>{data.project.name}</Link>
              : PROJECT_UNASSIGNED_LABEL,
          },
          { key: "category", label: "분류", value: data.category?.name || "분류 없음" },
          {
            key: "version", label: "현재 판",
            value: current.version_no != null ? `${current.version_no}판` : "-",
          },
          { key: "updated", label: "마지막 수정", value: fmtDateTimeCompact(data.updated_at) },
        ]}
      />

      <DetailLayout aside={aside}>
        <Stack sx={{ minWidth: 0, gap: GRID_GAP }}>
          <Card>
            <Stack spacing={2}>
              {/* 휴지통 문서는 **읽기 전용**이다. 편집기를 그대로 두면 사람이 고칠 수 있는
                  것처럼 보이고, 서버가 404 로 막으면 그제서야 알게 된다 — 그 순간까지 친
                  글은 아무 데도 안 남는다. 고칠 수 있게 하는 길은 「복원」 하나다. */}
              {trashed ? (
                /* 제목은 다시 안 적는다 — 페이지 머리가 이미 그 이름을 든다. 편집 칸을
                   읽기 전용 글자로 바꾸면 같은 제목이 화면에 두 번 선다. */
                <React.Suspense fallback={<Skeleton kind="section" lines={6} />}>
                  <BlockEditor value={body} onChange={undefined} readOnly />
                </React.Suspense>
              ) : (
                <>
                  <TextField
                    label="문서 제목"
                    InputLabelProps={{ shrink: true }}
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    inputProps={{ maxLength: 500 }}
                    fullWidth
                  />
                  <React.Suspense fallback={<Skeleton kind="section" lines={6} />}>
                    <BlockEditor value={body} onChange={setBody} onPickImage={pickImage} />
                  </React.Suspense>
                </>
              )}
            </Stack>
          </Card>

          {history ? (
            <Card>
              <Section title="판 이력">
                {versions.isLoading && <Skeleton kind="list" rows={4} />}
                {versions.isError && (
                  <ErrorState error={versions.error} onRetry={() => versions.refetch()} />
                )}
                {!versions.isLoading && versionRows.length === 0 && (
                  <EmptyState
                    title="아직 판이 없습니다."
                    help="본문을 저장하면 판이 하나씩 쌓입니다."
                  />
                )}
                <Stack spacing={1} component="ul" sx={{ listStyle: "none", p: 0, m: 0 }}>
                  {versionRows.map((version) => {
                    const isCurrent = version.version_no === versions.data?.current_version_no;
                    return (
                      <Box
                        key={version.id}
                        component="li"
                        sx={(theme) => ({
                          border: `1px solid ${theme.palette.divider}`,
                          borderRadius: 1,
                          p: 1.5,
                        })}
                      >
                        <Stack
                          direction={{ xs: "column", sm: "row" }}
                          spacing={1}
                          alignItems={{ sm: "center" }}
                        >
                          <Typography sx={{ fontWeight: FONT_WEIGHT.semibold, minWidth: "4rem" }}>
                            {version.version_no}판
                          </Typography>
                          {isCurrent && <Badge value="지금 보는 판" kind="info" />}
                          {version.source === "RESTORE" && <Badge value="되돌림" kind="neutral" />}
                          {version.ai_used && <Badge value="AI 사용" kind="neutral" />}
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{ ...KO_WORD_BREAK, flex: 1, minWidth: 0 }}
                          >
                            {version.change_reason || "사유를 적지 않았습니다."}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {fmtDateTimeCompact(version.created_at)}
                          </Typography>
                          <Stack direction="row" spacing={1}>
                            <Button
                              size="small"
                              disabled={isCurrent}
                              onClick={() => setCompareTo(version.version_no)}
                            >
                              지금 판과 비교
                            </Button>
                            {/* 🔴 휴지통 문서에는 안 그린다. 이력 **보기**는 남긴다 —
                                무엇을 잃는지가 되살릴지의 근거이고 읽기는 열려 있다.
                                되돌리기만 서버가 404 로 막는다(`restore_document_version`). */}
                            {trashed ? null : (
                            <Button
                              size="small"
                              disabled={isCurrent}
                              loading={restore.isPending}
                              onClick={async () => {
                                const ok = await confirm(
                                  "지금 본문을 지우지 않습니다. 옛 판의 내용으로 새 판을"
                                  + " 하나 더 쌓고, 이력은 그대로 남습니다.",
                                  {
                                    title: `${version.version_no}판으로 되돌릴까요?`,
                                    confirmLabel: "되돌리기",
                                  },
                                );
                                if (ok) restore.mutate(version.version_no);
                              }}
                            >
                              되돌리기
                            </Button>
                            )}
                          </Stack>
                        </Stack>
                      </Box>
                    );
                  })}
                </Stack>
              </Section>
            </Card>
          ) : null}

          {history && compareTo != null && versions.data?.current_version_no != null ? (
            <Card>
              <Section
                title={`${compareTo}판과 ${versions.data.current_version_no}판의 차이`}
                action={<Button size="small" onClick={() => setCompareTo(null)}>닫기</Button>}
              >
                <VersionDiff
                  documentId={id}
                  base={compareTo}
                  target={versions.data.current_version_no}
                />
              </Section>
            </Card>
          ) : null}
        </Stack>
      </DetailLayout>

      {/* 옮기는 축은 **프로젝트** 하나다. 폴더 칸은 폴더 축이 화면에서 걷히면서 함께
          없어졌다(문서 개편 1·5번). 프로젝트를 바꾸는 것은 볼 수 있는 사람을 바꾸는
          일이라(§5.3) 그 사실을 도움말이 말한다. */}
      <Modal
        open={moving}
        onClose={() => setMoving(false)}
        title="문서 옮기기"
        footer={(
          <ModalFooter
            onCancel={() => setMoving(false)}
            onSubmit={() => move.mutate({ project_id: moveProjectId })}
            submitLabel="옮기기"
            busy={move.isPending}
          />
        )}
      >
        <Stack spacing={2}>
          {/* 🔴 「프로젝트 미지정」을 `allLabel` 로 그리지 않는다. 그 prop 은 **빈 값**의
              이름만 바꾸므로 센티널 "none" 이 서버에 안 가고, 이동이 아무 오류 없이
              아무것도 안 한다. 값을 실제로 보내려면 후보에 넣어야 한다 —
              새 문서 대화상자가 쓰는 것과 같은 방법이다. */}
          <ProjectPicker
            layout="form"
            label="프로젝트"
            noAllOption
            value={moveProjectId}
            onChange={setMoveProjectId}
            extraOptions={[{ value: PROJECT_NONE, label: PROJECT_UNASSIGNED_LABEL }]}
            helperText={
              moveProjectId === PROJECT_NONE
                ? "조직의 모든 사람이 이 문서를 볼 수 있게 됩니다."
                : "이 문서를 볼 수 있는 사람이 그 프로젝트를 볼 수 있는 사람으로 바뀝니다."
            }
          />
        </Stack>
      </Modal>
    </>
  );
}

export default KnowledgeDoc;
