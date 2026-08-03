import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Callout,
  Card,
  ErrorState,
  PageHeader,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { boardCategoryKind } from "../lib/badges.js";
import { PostFormModal, Reactions } from "./Board.jsx";
import { splitComments } from "./board-helpers.js";

/* 게시글 상세 (팀 공간 §18). 본문·댓글은 {값}으로만 렌더(React 자동 이스케이프, 불변 §6).
 * 첨부 이미지는 같은 출처 인증 엔드포인트라 <img src>로 쿠키가 함께 전송된다(objectURL 불필요).
 *
 * 2026-08 MUI 재설계 — 레이아웃 규칙:
 * 본문은 산문이라 줄 길이를 PROSE_MAX_WIDTH(78ch)로 묶는다. 4K에서 남는 폭은 줄을 늘리는 데
 * 쓰지 않고 **두 번째 열**(메타 + 댓글 레일)로 보낸다. 3,000px짜리 한 줄은 눈이 다음 줄
 * 첫 글자를 못 찾는다. 레일 안의 댓글도 uhd에서는 두 갈래로 접어 폭을 실제로 쓴다. */

const PROSE_SX = {
  maxWidth: PROSE_MAX_WIDTH,
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
  lineHeight: 1.75,
  fontSize: "1rem",
};

function AttachmentList({ attachments }) {
  if (!attachments || attachments.length === 0) return null;
  const images = attachments.filter((a) => a.is_image);
  const files = attachments.filter((a) => !a.is_image);
  return (
    <Box sx={{ mt: 3, display: "grid", gap: 2 }}>
      {images.length > 0 ? (
        <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))" }}>
          {images.map((a) => (
            <Link key={a.id} href={a.url} target="_blank" rel="noreferrer noopener" sx={{ display: "block", minWidth: 0 }}>
              <Box
                component="img"
                src={a.url}
                alt={a.filename}
                loading="lazy"
                decoding="async"
                sx={{ width: "100%", aspectRatio: "1 / 1", objectFit: "cover", borderRadius: 2, border: 1, borderColor: "divider" }}
              />
            </Link>
          ))}
        </Box>
      ) : null}
      {files.length > 0 ? (
        <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.5 }}>
          {files.map((a) => (
            <li key={a.id}>
              <Link href={a.url} target="_blank" rel="noreferrer noopener" underline="hover">
                {a.filename}
              </Link>
            </li>
          ))}
        </Box>
      ) : null}
    </Box>
  );
}

function CommentComposer({ postId, parentId, palette, onDone, autoFocus }) {
  const toast = useToast();
  const [body, setBody] = useState("");
  const submit = useMutation({
    mutationFn: () =>
      api("/api/board/posts/" + postId + "/comments", {
        method: "POST",
        body: { body, parent_comment_id: parentId || null },
      }),
    onSuccess: () => { setBody(""); onDone && onDone(); },
    onError: (e) => toast((e && e.message) || "댓글을 남기지 못했습니다.", "error"),
  });
  return (
    <Box sx={{ mt: 1.5 }}>
      <TextField
        fullWidth
        size="small"
        multiline
        minRows={parentId ? 2 : 3}
        placeholder={parentId ? "답글 입력" : "댓글 입력"}
        inputProps={{ "aria-label": parentId ? "답글 입력" : "댓글 입력" }}
        value={body}
        autoFocus={autoFocus}
        onChange={(e) => setBody(e.target.value)}
      />
      <Stack direction="row" gap={1} justifyContent="flex-end" sx={{ mt: 1 }}>
        {parentId ? (
          <Button variant="ghost" size="sm" onClick={() => onDone && onDone()}>취소</Button>
        ) : null}
        <Button
          variant="primary"
          size="sm"
          disabled={!body.trim() || submit.isPending}
          onClick={() => body.trim() && submit.mutate()}
        >
          {parentId ? "답글 등록" : "댓글 등록"}
        </Button>
      </Stack>
    </Box>
  );
}

/* 댓글 한 건. 목록 시맨틱(<li>)은 부모가 만든다 — 답글은 최상위 댓글 안에 중첩된 <ul>로 들어가야
 * 하는데, 이 컴포넌트가 스스로 <li>를 그리면 최상위 댓글이 <li> 안의 <li>가 되어 무효 마크업이 된다. */
function CommentItem({ comment, postId, palette, isReply, onChanged }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [editing, setEditing] = useState(false);
  const [replying, setReplying] = useState(false);
  const [text, setText] = useState(comment.body);

  const saveEdit = useMutation({
    mutationFn: () =>
      api("/api/board/comments/" + comment.id, { method: "PATCH", body: { body: text } }),
    onSuccess: () => { setEditing(false); onChanged && onChanged(); },
    onError: (e) => toast((e && e.message) || "수정하지 못했습니다.", "error"),
  });
  const remove = useMutation({
    mutationFn: () => api("/api/board/comments/" + comment.id, { method: "DELETE" }),
    onSuccess: () => onChanged && onChanged(),
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
  });

  const askDelete = async () => {
    const ok = await confirm("이 댓글을 삭제할까요?", { danger: true, confirmLabel: "삭제" });
    if (ok) remove.mutate();
  };

  return (
    <Paper
      component="article"
      variant="outlined"
      sx={{
        p: 2, minWidth: 0,
        // 답글은 부모 댓글에 딸린 것임을 왼쪽 선으로 보인다(들여쓰기는 부모 목록이 준다).
        borderLeft: isReply ? 3 : 1,
        borderLeftColor: isReply ? "primary.light" : "divider",
      }}
    >
      <Stack direction="row" gap={1.5} alignItems="baseline" flexWrap="wrap">
        <Typography variant="body2" sx={{ fontWeight: 700 }}>{comment.author_name}</Typography>
        <Typography variant="caption" color="text.secondary">{fmtDateTime(comment.created_at)}</Typography>
      </Stack>
      {editing ? (
        <Box sx={{ mt: 1 }}>
          <TextField
            fullWidth size="small" multiline minRows={2} value={text}
            inputProps={{ "aria-label": "댓글 수정" }}
            onChange={(e) => setText(e.target.value)}
          />
          <Stack direction="row" gap={1} justifyContent="flex-end" sx={{ mt: 1 }}>
            <Button variant="ghost" size="sm" onClick={() => { setEditing(false); setText(comment.body); }}>취소</Button>
            <Button variant="primary" size="sm" disabled={!text.trim() || saveEdit.isPending} onClick={() => saveEdit.mutate()}>저장</Button>
          </Stack>
        </Box>
      ) : (
        <Typography sx={{ my: 1, whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: "0.9375rem" }}>
          {comment.body}
        </Typography>
      )}
      <Stack direction="row" gap={1} alignItems="center" justifyContent="space-between" flexWrap="wrap">
        <Reactions
          targetType="comment"
          targetId={comment.id}
          reactions={comment.reactions}
          palette={palette}
          onChanged={onChanged}
        />
        <Stack direction="row" gap={0.5}>
          {!isReply ? (
            <Button variant="ghost" size="sm" onClick={() => setReplying((v) => !v)}>답글</Button>
          ) : null}
          {comment.can_edit ? (
            <>
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>수정</Button>
              <Button variant="ghost" size="sm" color="error" onClick={askDelete}>삭제</Button>
            </>
          ) : null}
        </Stack>
      </Stack>
      {replying ? (
        <CommentComposer
          postId={postId}
          parentId={comment.id}
          palette={palette}
          autoFocus
          onDone={() => { setReplying(false); onChanged && onChanged(); }}
        />
      ) : null}
    </Paper>
  );
}

/* 메타 레일 — 작성자·시각·조회수·첨부 수. 좁은 화면에서는 본문 아래로 흐르고, 넓은 화면에서는
 * 본문 옆 열에 붙는다. 라벨/값 쌍은 폭이 넓어지면 2~3열로 접어 세로로 길게 늘어지지 않게 한다. */
function PostMeta({ post }) {
  const rows = [
    ["작성자", post.author_name],
    ["작성", fmtDateTime(post.created_at)],
    ["조회", String(post.view_count == null ? 0 : post.view_count)],
    ["카테고리", post.category],
  ];
  const attCount = (post.attachments || []).length;
  if (attCount > 0) rows.push(["첨부", attCount + "개"]);
  return (
    <Card sx={{ p: 2.5 }}>
      <Box sx={{
        display: "grid", columnGap: 3, rowGap: 0,
        gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", xxl: "1fr", uhd: "repeat(2, minmax(0,1fr))" },
      }}>
        {rows.map(([label, value]) => (
          <Box key={label} sx={{
            display: "grid", gridTemplateColumns: "6rem minmax(0,1fr)", gap: 1,
            py: 1, borderBottom: 1, borderColor: "divider", minWidth: 0,
          }}>
            <Typography variant="body2" color="text.secondary">{label}</Typography>
            <Box sx={{ minWidth: 0, overflowWrap: "anywhere", fontSize: "0.875rem" }}>{value}</Box>
          </Box>
        ))}
      </Box>
    </Card>
  );
}

export function BoardPost() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const [editing, setEditing] = useState(false);

  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ["board-meta"], queryFn: () => api("/api/board/meta") });
  const detail = useQuery({
    queryKey: ["board-post", id],
    queryFn: () => api("/api/board/posts/" + id),
  });

  // 진입 시 한 번만 조회수를 올린다(GET은 더 이상 올리지 않는다 — 반응·댓글 refetch로
  // 조회수가 부풀던 문제 해결). 실패는 무시(집계는 부가 정보).
  const viewedRef = useRef(null);
  useEffect(() => {
    if (!id || viewedRef.current === id) return;
    viewedRef.current = id;
    api("/api/board/posts/" + id + "/view", { method: "POST" }).catch(() => {});
  }, [id]);

  const palette = (meta.data && meta.data.reaction_emojis) || [];
  const refetch = () => detail.refetch();

  const pin = useMutation({
    mutationFn: (pinned) =>
      api("/api/board/posts/" + id + "/pin?pinned=" + (pinned ? "true" : "false"), { method: "POST" }),
    onSuccess: () => { refetch(); qc.invalidateQueries({ queryKey: ["board"] }); },
    onError: (e) => toast((e && e.message) || "고정 상태를 바꾸지 못했습니다.", "error"),
  });
  const remove = useMutation({
    mutationFn: () => api("/api/board/posts/" + id, { method: "DELETE" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["board"] }); toast("게시글을 삭제했습니다.", "success"); nav("/board"); },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
  });

  if (detail.isError) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="팀 공간" area="자유게시판" title="게시글" />
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      </div>
    );
  }
  if (detail.isPending) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="팀 공간" area="자유게시판" title="게시글" />
        <Card><Skeleton lines={8} /></Card>
      </div>
    );
  }

  const post = detail.data.post;
  const comments = post.comments || [];
  const { tops, repliesByParent } = splitComments(comments);

  const askDeletePost = async () => {
    const ok = await confirm("이 게시글을 삭제할까요?", { danger: true, confirmLabel: "삭제" });
    if (ok) remove.mutate();
  };

  const actions = (
    <>
      <Button variant="ghost" onClick={() => nav("/board")}>목록</Button>
      {post.can_moderate ? (
        <Button onClick={() => pin.mutate(!post.is_pinned)} disabled={pin.isPending}>
          {post.is_pinned ? "고정 해제" : "공지 고정"}
        </Button>
      ) : null}
      {post.can_edit ? (
        <>
          <Button onClick={() => setEditing(true)}>수정</Button>
          <Button variant="danger" onClick={askDeletePost} disabled={remove.isPending}>삭제</Button>
        </>
      ) : null}
    </>
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="자유게시판" title="게시글" actions={actions} />

      {/* 1열: 산문(78ch 상한). 2열: 메타 + 댓글 레일. lg부터 갈라진다 — 그 아래에서는 레일이
          본문 밑으로 자연스럽게 흐른다(소스 순서 = 읽는 순서라 스크린리더도 그대로 따라간다). */}
      <Box sx={{
        display: "grid", alignItems: "start",
        columnGap: { lg: 4, xxl: 6 }, rowGap: 3,
        gridTemplateColumns: { xs: "1fr", lg: `minmax(0, ${PROSE_MAX_WIDTH}) minmax(18rem, 1fr)` },
      }}>
        <Card component="article" sx={{ minWidth: 0 }}>
          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            {post.is_pinned ? <Badge value="고정" kind="info" /> : null}
            <Badge value={post.category} kind={boardCategoryKind(post.category)} />
          </Stack>
          <Typography variant="h4" component="h1" sx={{ mt: 1, overflowWrap: "anywhere" }}>{post.title}</Typography>
          <Stack direction="row" gap={2} flexWrap="wrap" sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">{post.author_name}</Typography>
            <Typography variant="body2" color="text.secondary">{fmtDateTime(post.created_at)}</Typography>
            <Typography variant="body2" color="text.secondary">조회 {post.view_count}</Typography>
          </Stack>

          {post.body && String(post.body).trim() ? (
            <Typography component="div" sx={{ ...PROSE_SX, mt: 3 }}>{post.body}</Typography>
          ) : (
            // 제목만 있는 글(첨부만 올린 경우 등) — 빈 여백만 두면 로딩 실패처럼 보인다.
            <Typography variant="body2" color="text.secondary" sx={{ mt: 3 }}>본문 내용이 없습니다.</Typography>
          )}

          <AttachmentList attachments={post.attachments} />

          <Box sx={{ mt: 3 }}>
            <Reactions
              targetType="post"
              targetId={post.id}
              reactions={post.reactions}
              palette={palette}
              onChanged={refetch}
            />
          </Box>
        </Card>

        <Box sx={{ display: "grid", gap: 3, minWidth: 0 }}>
          <PostMeta post={post} />

          <Box component="section" sx={{ minWidth: 0 }}>
            <Typography variant="h6" component="h2" sx={{ mb: 1.5 }}>댓글 {comments.length}</Typography>
            {tops.length === 0 ? (
              <Callout tone="info">아직 댓글이 없습니다. 첫 댓글을 남겨 보세요.</Callout>
            ) : (
              /* 레일이 아주 넓어지는 4K에서는 댓글 묶음을 두 갈래로 접는다 — 한 줄이 2,000px가
                 되는 대신 폭을 실제로 쓴다. 답글은 자기 최상위 댓글 안에 중첩된 목록으로 남는다. */
              <Box component="ul" sx={{
                listStyle: "none", m: 0, p: 0, display: "grid", gap: 1.5, alignItems: "start",
                gridTemplateColumns: { xs: "1fr", uhd: "repeat(2, minmax(0,1fr))" },
              }}>
                {tops.map((c) => (
                  <Box component="li" key={c.id} sx={{ minWidth: 0, display: "grid", gap: 1.5 }}>
                    <CommentItem comment={c} postId={post.id} palette={palette} onChanged={refetch} />
                    {(repliesByParent[c.id] || []).length ? (
                      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, pl: { xs: 1.5, sm: 3 }, display: "grid", gap: 1.5 }}>
                        {(repliesByParent[c.id] || []).map((r) => (
                          <Box component="li" key={r.id} sx={{ minWidth: 0 }}>
                            <CommentItem comment={r} postId={post.id} palette={palette} isReply onChanged={refetch} />
                          </Box>
                        ))}
                      </Box>
                    ) : null}
                  </Box>
                ))}
              </Box>
            )}
            <CommentComposer postId={post.id} palette={palette} onDone={refetch} />
          </Box>
        </Box>
      </Box>

      <PostFormModal
        open={editing}
        onClose={() => setEditing(false)}
        categories={(meta.data && meta.data.categories) || []}
        mode="edit"
        post={post}
        onSaved={() => { setEditing(false); refetch(); }}
      />
    </div>
  );
}
