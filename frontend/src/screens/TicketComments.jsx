import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { Button, Callout, Card, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";

/* 티켓 댓글 (계획 Phase 3 §E).
 *
 * 서버는 쓰기(작성·수정·삭제)마다 **목록 전체**를 돌려준다. 그래서 여기서는 응답을 그대로
 * 캐시에 넣기만 하면 되고, 클라이언트가 목록을 직접 기워 맞추지 않는다 — 그렇게 하면 툼스톤
 * 규약이 서버와 클라 두 곳에 생겨 언젠가 갈라진다.
 *
 * 삭제된 댓글은 사라지지 않고 **툼스톤**으로 남는다. 자리를 남겨 둬야 "내가 보던 그 댓글이
 * 지워졌다"를 읽을 수 있다(행이 조용히 없어지면 사용자는 자기가 잘못 봤다고 생각한다).
 *
 * 폭: 댓글도 산문이라 78ch에서 멈춘다. */

/* app/tickets/comments.py 의 MAX_COMMENT_CHARS 와 같은 값. 여기 값은 입력을 잘라 주는 힌트일
 * 뿐이고 실제 거절은 서버가 한다(브라우저 제한만 믿지 않는다). 서버 값을 바꾸면 여기도 바꾼다. */
const MAX_COMMENT_CHARS = 2000;

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

function CommentRow({ comment, busy, onEdit, onDelete }) {
  if (comment.deleted) return <Tombstone comment={comment} />;
  const edited = comment.updated_at && comment.updated_at !== comment.created_at;
  return (
    <Box sx={{ py: 1.5, borderBottom: 1, borderColor: "divider", "&:last-of-type": { borderBottom: 0 } }}>
      <Stack direction="row" gap={1} sx={{ alignItems: "baseline", flexWrap: "wrap", mb: 0.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          {comment.author_name || "알 수 없음"}
        </Typography>
        <TimeStamp value={comment.created_at} />
        {edited ? (
          <Typography component="span" variant="caption" color="text.secondary">(수정됨)</Typography>
        ) : null}
        <Box sx={{ flex: 1 }} />
        {comment.can_edit ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={onEdit}>수정</Button>
        ) : null}
        {comment.can_delete ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={onDelete}>삭제</Button>
        ) : null}
      </Stack>
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
        {comment.body}
      </Typography>
    </Box>
  );
}

export function TicketComments({ ticketId }) {
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const key = ["ticket-comments", ticketId];
  const [draft, setDraft] = React.useState("");
  const [editingId, setEditingId] = React.useState(null);
  const [editDraft, setEditDraft] = React.useState("");

  const list = useQuery({
    queryKey: key,
    queryFn: () => api("/api/tickets/" + ticketId + "/comments"),
    retry: false,
  });

  const applyList = (res) => { if (res) qc.setQueryData(key, res); };
  const fail = (fallback) => (e) => toast((e && e.message) || fallback, "error");

  const create = useMutation({
    mutationFn: (body) => api("/api/tickets/" + ticketId + "/comments", { method: "POST", body: { body } }),
    onSuccess: (res) => { applyList(res); setDraft(""); },
    onError: fail("댓글을 등록하지 못했습니다."),
  });
  const update = useMutation({
    mutationFn: ({ id, body }) => api("/api/tickets/comments/" + id, { method: "PATCH", body: { body } }),
    onSuccess: (res) => { applyList(res); setEditingId(null); setEditDraft(""); },
    onError: fail("댓글을 수정하지 못했습니다."),
  });
  const remove = useMutation({
    mutationFn: (id) => api("/api/tickets/comments/" + id, { method: "DELETE" }),
    onSuccess: (res) => { applyList(res); toast("댓글을 삭제했습니다.", "success"); },
    onError: fail("댓글을 삭제하지 못했습니다."),
  });

  const busy = create.isPending || update.isPending || remove.isPending;
  const comments = (list.data && list.data.comments) || [];
  const liveCount = comments.filter((c) => !c.deleted).length;

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
    /* 카드는 본문 카드와 같은 폭(열 전체)이고, 줄 길이 상한은 카드가 아니라 **안쪽 내용**에
       건다. 카드 자체를 78ch로 줄이면 바로 위 본문 카드보다 좁아 보여 두 카드가 어긋난다
       (xl 미만에서 열이 열 전체 폭을 쓰기 때문). */
    <Card component="section" aria-label="댓글" sx={{ minWidth: 0 }}>
      <Typography component="h2" variant="h6" sx={{ fontSize: "1rem", mb: 1, maxWidth: PROSE_MAX_WIDTH }}>
        댓글 {liveCount > 0 ? liveCount : ""}
      </Typography>

      {list.isPending ? <Skeleton lines={3} /> : null}
      {list.isError ? (
        <Callout tone="danger">{(list.error && list.error.message) || "댓글을 불러오지 못했습니다."}</Callout>
      ) : null}

      {!list.isPending && !list.isError && comments.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: PROSE_MAX_WIDTH }}>
          아직 댓글이 없습니다. 이 티켓에 대한 논의를 여기에 남기세요.
        </Typography>
      ) : null}

      <Box sx={{ display: "grid", maxWidth: PROSE_MAX_WIDTH }}>
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
              busy={busy}
              onEdit={() => { setEditingId(c.id); setEditDraft(c.body || ""); }}
              onDelete={() => askDelete(c.id)}
            />
          )
        ))}
      </Box>

      <Box sx={{ mt: 2, maxWidth: PROSE_MAX_WIDTH }}>
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
            {create.isPending ? "등록 중…" : "댓글 등록"}
          </Button>
        </Stack>
      </Box>
    </Card>
  );
}
