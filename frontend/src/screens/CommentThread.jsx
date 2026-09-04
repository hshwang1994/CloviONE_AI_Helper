import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { Button, Card, ErrorState, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { FONT_SIZE, KO_WORD_BREAK } from "../ui/theme.js";
import { AuthorLine } from "./Board.jsx";

/* 댓글 타래 (티켓 · 문서 공용).
 *
 * 원래 이 코드는 TicketComments.jsx 한 곳에 있었고, 문서 댓글(사용자 지적 #9)을 만들면서
 * 그대로 복사할 뻔했다. 복사하면 **툼스톤 규약이 클라이언트에 두 벌** 생긴다 — 한쪽만
 * 고치는 날 "티켓에서는 '삭제된 댓글'이 남는데 문서에서는 행이 조용히 사라지는" 화면이
 * 되고, 사용자는 같은 낱말이 화면마다 다른 뜻이라는 걸 스스로 알아내야 한다.
 * 서버가 두 자원에 대해 같은 규약(쓰기마다 목록 전체 + 툼스톤)을 지키므로, 화면도 한 벌이면 된다.
 *
 * 서버는 쓰기(작성·수정·삭제)마다 **목록 전체**를 돌려준다. 그래서 여기서는 응답을 그대로
 * 캐시에 넣기만 하면 되고, 클라이언트가 목록을 직접 기워 맞추지 않는다.
 *
 * 폭은 담는 열(또는 페이지 전폭)을 그대로 쓴다. 댓글만 72ch 로 줄이면 바로 위 본문보다
 * 좁아 두 덩어리가 어긋난다. */

/* app/tickets/comments.py 와 app/team_docs/comments.py 의 MAX_COMMENT_CHARS 와 같은 값
 * (둘은 서로 같다). 여기 값은 입력을 잘라 주는 힌트일 뿐이고 실제 거절은 서버가 한다
 * (브라우저 제한만 믿지 않는다). 서버 값을 바꾸면 여기도 바꾼다. */
export const MAX_COMMENT_CHARS = 2000;

function TimeStamp({ value }) {
  return (
    <Typography component="span" variant="caption" color="text.secondary">
      {fmtDateTime(value)}
    </Typography>
  );
}

function Tombstone({ comment }) {
  return (
    <Box sx={{ py: 1.5, borderBottom: 1, borderColor: "divider" }}>
      <Typography variant="body2" color="text.disabled" sx={{ fontStyle: "italic" }}>
        {comment.author_name || "알 수 없음"}, 삭제된 댓글입니다
      </Typography>
    </Box>
  );
}

function CommentRow({ comment, person, busy, onEdit, onDelete }) {
  if (comment.deleted) return <Tombstone comment={comment} />;
  const edited = comment.updated_at && comment.updated_at !== comment.created_at;
  return (
    <Box sx={{ py: 1.5, borderBottom: 1, borderColor: "divider", "&:last-of-type": { borderBottom: 0 } }}>
      <Stack direction="row" gap={1} sx={{ alignItems: "center", flexWrap: "wrap", mb: 0.5 }}>
        {/* 댓글에서도 작성자의 소속·사진을 말한다(사용자 지시 #13/#8, 게시판과 같은 규칙) —
            동명이인이면 이름 두 글자로는 "누가 답을 달았는지"에 답할 수 없다. Board.jsx의
            AuthorLine을 그대로 쓴다: 자리를 두 벌로 만들면 규칙이 갈라진다.
            아바타·이름·시각은 **가운데 축**을 나눈다. baseline 이면 원이 글자보다 위에 선다. */}
        <AuthorLine name={comment.author_name} person={person} bold />
        <TimeStamp value={comment.created_at} />
        {edited ? (
          <Typography component="span" variant="caption" color="text.secondary">(수정됨)</Typography>
        ) : null}
        <Box sx={{ flex: 1 }} />
        {/* 두 조건을 **함께** 본다. 서버가 「이 사람은 고칠 수 있다」고 말해도, 이 화면이
            읽기 전용이면(핸들러를 안 준다) 자리를 만들지 않는다 — 예전에는 앞 조건만 봐서
            핸들러가 없는 단추가 그려졌고, 누르면 아무 일도 안 났다. */}
        {comment.can_edit && onEdit ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={onEdit}>수정</Button>
        ) : null}
        {comment.can_delete && onDelete ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={onDelete}>삭제</Button>
        ) : null}
      </Stack>
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", ...KO_WORD_BREAK }}>
        {comment.body}
      </Typography>
    </Box>
  );
}

/* `listUrl` 은 목록(GET)과 작성(POST)을 함께 쓰는 주소이고, `itemUrl(id)` 는 수정(PATCH)과
 * 삭제(DELETE) 주소를 만든다. 두 자원의 URL 모양이 같아서(`…/{id}/comments`,
 * `…/comments/{comment_id}`) 이 두 개면 충분하다. */
/** @param {boolean} [readOnly] 읽기만 — 쓰는 자리를 **그리지 않는다.**
 *
 * 휴지통에 있는 문서가 이 갈래를 쓴다. 서버가 그 문서의 쓰기를 404 로 막으므로
 * (`get_writable_document_or_404`) 작성 칸을 그대로 두면 사람은 글을 다 쓰고 나서야
 * 「문서를 찾지 못했습니다」를 본다 — 그 글은 아무 데도 안 남는다. 못 하는 일은
 * 실패하게 두는 것보다 **자리를 안 만드는 것**이 낫다. */
export function CommentThread({ queryKey, listUrl, itemUrl, emptyHint, readOnly = false }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [draft, setDraft] = React.useState("");
  const [editingId, setEditingId] = React.useState(null);
  const [editDraft, setEditDraft] = React.useState("");

  const list = useQuery({
    queryKey,
    queryFn: () => api(listUrl),
    retry: false,
  });

  const applyList = (res) => { if (res) qc.setQueryData(queryKey, res); };
  const fail = (fallback) => (e) => toast((e && e.message) || fallback, "error");

  const create = useMutation({
    mutationFn: (body) => api(listUrl, { method: "POST", body: { body } }),
    onSuccess: (res) => { applyList(res); setDraft(""); },
    onError: fail("댓글을 추가하지 못했습니다. 다시 시도해 주세요."),
  });
  const update = useMutation({
    mutationFn: ({ id, body }) => api(itemUrl(id), { method: "PATCH", body: { body } }),
    onSuccess: (res) => { applyList(res); setEditingId(null); setEditDraft(""); },
    onError: fail("댓글을 수정하지 못했습니다. 다시 시도해 주세요."),
  });
  const remove = useMutation({
    mutationFn: (id) => api(itemUrl(id), { method: "DELETE" }),
    onSuccess: (res) => { applyList(res); toast("댓글을 삭제했습니다.", "success"); },
    onError: fail("댓글을 삭제하지 못했습니다. 다시 시도해 주세요."),
  });

  const busy = create.isPending || update.isPending || remove.isPending;
  const comments = (list.data && list.data.comments) || [];
  const liveCount = comments.filter((c) => !c.deleted).length;
  /* 댓글 작성자의 신원(부서·직책·사진). 사람 한 명당 한 줄만 오고 댓글은 uid로 찾아
   * 쓴다(Board.jsx의 people과 같은 모양) — 댓글마다 되풀이하면 응답이 부풀고, 옛
   * 캐시·응답에는 없을 수 있다. */
  const people = (list.data && list.data.people) || {};

  const submit = () => {
    const body = draft.trim();
    if (!body) return;
    create.mutate(body);
  };

  const askDelete = async (id) => {
    const ok = await confirm("이 댓글을 삭제합니다. 목록에는 ‘삭제된 댓글’로 남습니다. 계속할까요?", {
      title: "댓글 삭제", confirmLabel: "삭제", danger: true,
    });
    if (ok) remove.mutate(id);
  };

  return (
    <Card component="section" aria-label="댓글" sx={{ minWidth: 0 }}>
      <Typography component="h2" variant="h6" sx={{ fontSize: FONT_SIZE.sectionTitle, mb: 1 }}>
        댓글 {liveCount > 0 ? liveCount : ""}
      </Typography>

      {list.isPending ? <Skeleton lines={3} /> : null}
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : null}

      {!list.isPending && !list.isError && comments.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {emptyHint}
        </Typography>
      ) : null}

      <Box sx={{ display: "grid" }}>
        {comments.map((c) => (
          editingId === c.id ? (
            <Box key={c.id} sx={{ py: 1.5, borderBottom: 1, borderColor: "divider" }}>
              <TextField
                multiline minRows={3} fullWidth size="small" autoFocus
                value={editDraft}
                onChange={(e) => setEditDraft(e.target.value)}
                inputProps={{ maxLength: MAX_COMMENT_CHARS, "aria-label": "댓글 수정" }}
              />
              <Stack direction="row" gap={1} sx={{ mt: 1, justifyContent: "flex-end" }}>
                <Button size="sm" disabled={busy} onClick={() => { setEditingId(null); setEditDraft(""); }}>취소</Button>
                <Button size="sm" variant="primary" disabled={busy || !editDraft.trim()}
                  onClick={() => update.mutate({ id: c.id, body: editDraft.trim() })}>저장</Button>
              </Stack>
            </Box>
          ) : (
            <CommentRow
              key={c.id}
              comment={c}
              person={people[c.author_user_id]}
              busy={busy}
              /* 읽기 전용이면 수정·삭제 자리도 안 만든다 — `CommentRow` 는 핸들러가
                 없으면 그 단추를 안 그린다. */
              onEdit={readOnly ? null : () => { setEditingId(c.id); setEditDraft(c.body || ""); }}
              onDelete={readOnly ? null : () => askDelete(c.id)}
            />
          )
        ))}
      </Box>

      {/* 못 쓰는 자리에는 쓰는 칸을 안 만든다. 서버가 404 로 막는 문서(휴지통)에서
          칸을 그대로 두면 사람은 글을 다 쓰고 나서야 그것을 안다. */}
      {readOnly ? null : (
      <Box sx={{ mt: 2 }}>
        <TextField
          multiline minRows={3} fullWidth size="small"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="댓글을 입력하세요."
          inputProps={{ maxLength: MAX_COMMENT_CHARS, "aria-label": "댓글 입력" }}
        />
        <Stack direction="row" gap={1} sx={{ mt: 1, justifyContent: "flex-end", alignItems: "center" }}>
          <Typography variant="caption" color="text.secondary">
            {draft.length}/{MAX_COMMENT_CHARS}
          </Typography>
          <Button variant="primary" size="sm" disabled={busy || !draft.trim()} onClick={submit}>
            {create.isPending ? "추가 중…" : "댓글 추가"}
          </Button>
        </Stack>
      </Box>
      )}
    </Card>
  );
}
