import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Callout,
  ErrorState,
  PageHeader,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { boardCategoryKind } from "../lib/badges.js";
import { PostFormModal, Reactions } from "./Board.jsx";
import { splitComments } from "./board-helpers.js";

/* 게시글 상세 (팀 공간 §18). 본문·댓글은 {값}으로만 렌더(React 자동 이스케이프, 불변 §6).
 * 첨부 이미지는 같은 출처 인증 엔드포인트라 <img src>로 쿠키가 함께 전송된다(objectURL 불필요). */

function AttachmentList({ attachments }) {
  if (!attachments || attachments.length === 0) return null;
  const images = attachments.filter((a) => a.is_image);
  const files = attachments.filter((a) => !a.is_image);
  return (
    <div className="board-atts">
      {images.length > 0 ? (
        <div className="board-att-imgs">
          {images.map((a) => (
            <a key={a.id} href={a.url} target="_blank" rel="noreferrer noopener">
              <img className="board-att-img" src={a.url} alt={a.filename} loading="lazy" />
            </a>
          ))}
        </div>
      ) : null}
      {files.length > 0 ? (
        <ul className="board-att-files">
          {files.map((a) => (
            <li key={a.id}>
              <a className="k-link" href={a.url} target="_blank" rel="noreferrer noopener">
                {a.filename}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
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
    <div className="board-composer">
      <textarea
        className="k-input"
        rows={parentId ? 2 : 3}
        placeholder={parentId ? "답글 입력" : "댓글 입력"}
        value={body}
        autoFocus={autoFocus}
        onChange={(e) => setBody(e.target.value)}
      />
      <div className="board-composer-actions">
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
      </div>
    </div>
  );
}

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
    <li className={"board-comment" + (isReply ? " is-reply" : "")}>
      <div className="board-comment-meta">
        <span className="board-comment-author">{comment.author_name}</span>
        <span className="board-comment-time">{fmtDateTime(comment.created_at)}</span>
      </div>
      {editing ? (
        <div className="board-composer">
          <textarea className="k-input" rows={2} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="board-composer-actions">
            <Button variant="ghost" size="sm" onClick={() => { setEditing(false); setText(comment.body); }}>취소</Button>
            <Button variant="primary" size="sm" disabled={!text.trim() || saveEdit.isPending} onClick={() => saveEdit.mutate()}>저장</Button>
          </div>
        </div>
      ) : (
        <div className="board-comment-body">{comment.body}</div>
      )}
      <div className="board-comment-foot">
        <Reactions
          targetType="comment"
          targetId={comment.id}
          reactions={comment.reactions}
          palette={palette}
          onChanged={onChanged}
        />
        <div className="board-comment-actions">
          {!isReply ? (
            <button type="button" className="k-linkbtn" onClick={() => setReplying((v) => !v)}>답글</button>
          ) : null}
          {comment.can_edit ? (
            <>
              <button type="button" className="k-linkbtn" onClick={() => setEditing(true)}>수정</button>
              <button type="button" className="k-linkbtn is-danger" onClick={askDelete}>삭제</button>
            </>
          ) : null}
        </div>
      </div>
      {replying ? (
        <CommentComposer
          postId={postId}
          parentId={comment.id}
          palette={palette}
          autoFocus
          onDone={() => { setReplying(false); onChanged && onChanged(); }}
        />
      ) : null}
    </li>
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
        <Skeleton lines={8} />
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
    <div className="board-post-actions">
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
    </div>
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="자유게시판" title="게시글" actions={actions} />

      <article className="board-post">
        <div className="board-post-head">
          {post.is_pinned ? <Badge value="고정" kind="info" /> : null}
          <Badge value={post.category} kind={boardCategoryKind(post.category)} />
          <h1 className="board-post-title">{post.title}</h1>
          <div className="board-post-meta">
            <span>{post.author_name}</span>
            <span>{fmtDateTime(post.created_at)}</span>
            <span>조회 {post.view_count}</span>
          </div>
        </div>

        <div className="board-body">{post.body}</div>

        <AttachmentList attachments={post.attachments} />

        <div className="board-post-reactions">
          <Reactions
            targetType="post"
            targetId={post.id}
            reactions={post.reactions}
            palette={palette}
            onChanged={refetch}
          />
        </div>
      </article>

      <section className="board-comments">
        <h2 className="board-comments-title">댓글 {comments.length}</h2>
        <ul className="board-comment-list">
          {tops.length === 0 ? (
            <Callout tone="info">아직 댓글이 없습니다. 첫 댓글을 남겨 보세요.</Callout>
          ) : (
            tops.map((c) => (
              <React.Fragment key={c.id}>
                <CommentItem comment={c} postId={post.id} palette={palette} onChanged={refetch} />
                {(repliesByParent[c.id] || []).map((r) => (
                  <CommentItem key={r.id} comment={r} postId={post.id} palette={palette} isReply onChanged={refetch} />
                ))}
              </React.Fragment>
            ))
          )}
        </ul>
        <CommentComposer postId={post.id} palette={palette} onDone={refetch} />
      </section>

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
