import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
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
  ErrorState,
  PageHeader,
  Skeleton,
  Tag,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { KO_WORD_BREAK, PROSE_MAX_WIDTH } from "../ui/theme.js";

/* 본문(78ch)보다 조금 넓은 상한. 본문은 산문이라 78ch 에서 멈추는 게 맞지만,
   그 아래 댓글 목록까지 78ch 로 묶으면 답글 들여쓰기에서 또 좁아져 한 줄에
   몇 글자 안 들어간다. 화면 전체로 늘리지도 않는다 — 4K 에서 3,000px 짜리
   한 줄은 눈이 다음 줄 첫 글자를 못 찾는다. */
const PROSE_MAX_WIDTH_WIDE = "min(100%, 68rem)";
import { ideaStatusKind } from "../lib/badges.js";
import { AuthorLine, COPY, PostFormModal, Reactions } from "./Board.jsx";
import { splitComments } from "./board-helpers.js";
import { ImageLightbox, useLightbox } from "../ui/ImageLightbox.jsx";
import { useTicketProjects } from "./ticket-options.js";
import { EMPTYABLE_SELECT } from "../ui/filters.jsx";
import { setItemTitle } from "../app/documentTitle.js";

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
  ...KO_WORD_BREAK,
  lineHeight: 1.75,
  fontSize: "1rem",
};

function AttachmentList({ attachments }) {
  const lb = useLightbox();
  if (!attachments || attachments.length === 0) return null;
  const images = attachments.filter((a) => a.is_image);
  const files = attachments.filter((a) => !a.is_image);
  const slides = images.map((a) => ({ src: a.url, title: a.filename }));
  return (
    <Box sx={{ mt: 3, display: "grid", gap: 2 }}>
      {images.length > 0 ? (
        <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))" }}>
          {/* 예전에는 새 탭으로 열었다 — 이미지 한 장 보려고 앱을 떠나고, 돌아오면 스크롤
              위치를 잃는다. 이제 제자리에서 확대해 보고 좌우로 넘긴다(사용자 지시 §4). */}
          {images.map((a, i) => (
            <Box
              key={a.id}
              component="button"
              type="button"
              onClick={() => lb.open(slides, i)}
              aria-label={a.filename + " 크게 보기"}
              sx={{
                p: 0, border: 0, background: "none", cursor: "zoom-in",
                display: "block", minWidth: 0,
                "&:focus-visible": { outline: "3px solid", outlineColor: "primary.main", outlineOffset: 2 },
              }}
            >
              <Box
                component="img"
                src={a.url}
                alt={a.filename}
                loading="lazy"
                decoding="async"
                /* objectFit:"cover" + 강제 1:1 이 **정사각형이 아닌 사용자 이미지를 전부
                   잘라냈다** — 사용자가 "이미지가 잘리고 콘텐츠 영역만 보인다"고 지적한 것이
                   여기다. 타일 크기는 그대로 두되(격자가 흐트러지지 않게) 이미지는 통째로
                   보이게 contain 으로 바꾼다. 남는 면은 옅은 판으로 채워 빈칸처럼 안 보이게. */
                sx={{
                  width: "100%", aspectRatio: "1 / 1", objectFit: "contain",
                  borderRadius: 2, border: 1, borderColor: "divider",
                  bgcolor: "action.hover", display: "block",
                }}
              />
            </Box>
          ))}
          <ImageLightbox {...lb.props} />
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
  const qc = useQueryClient();
  const [body, setBody] = useState("");
  const submit = useMutation({
    mutationFn: () =>
      api("/api/board/posts/" + postId + "/comments", {
        method: "POST",
        body: { body, parent_comment_id: parentId || null },
      }),
    onSuccess: () => {
      setBody("");
      onDone && onDone();
      // 댓글 수는 이 상세 화면 밖에서도 보인다 — Board.jsx 목록의 comment_count 열,
      // Home.jsx 「최근 글」 위젯(recent.board[].comment_count), 글쓴이 자신의 「받은
      // 댓글」(board-mine). onDone은 이 상세 화면만 다시 부르므로(L축 재감사) 셋 다
      // 명시적으로 무효화한다.
      qc.invalidateQueries({ queryKey: ["board"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      qc.invalidateQueries({ queryKey: ["board-mine"] });
    },
    onError: (e) => toast((e && e.message) || "댓글을 남기지 못했습니다. 다시 시도해 주세요.", "error"),
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
          {parentId ? "답글 추가" : "댓글 추가"}
        </Button>
      </Stack>
    </Box>
  );
}

/* 삭제된 댓글의 자리 — 본문 없는 툼스톤. CommentThread.jsx(티켓·문서 공용 댓글)와 같은
 * 규약이다: 행이 조용히 사라지면 그 답글(자식)만 남아 부모 없는 대화처럼 보인다. */
function CommentTombstone({ comment, isReply }) {
  return (
    <Paper
      component="article" variant="outlined"
      sx={{
        p: 2, minWidth: 0,
        borderLeft: isReply ? 3 : 1,
        borderLeftColor: isReply ? "primary.light" : "divider",
      }}
    >
      <Typography variant="body2" color="text.disabled" sx={{ fontStyle: "italic" }}>
        {comment.author_name || "알 수 없음"}, 삭제된 댓글입니다
      </Typography>
    </Paper>
  );
}

/* 댓글 한 건. 목록 시맨틱(<li>)은 부모가 만든다 — 답글은 최상위 댓글 안에 중첩된 <ul>로 들어가야
 * 하는데, 이 컴포넌트가 스스로 <li>를 그리면 최상위 댓글이 <li> 안의 <li>가 되어 무효 마크업이 된다. */
function CommentItem({ comment, postId, palette, isReply, person, onChanged }) {
  const toast = useToast();
  const qc = useQueryClient();
  if (comment.deleted) return <CommentTombstone comment={comment} isReply={isReply} />;
  // CommentThread.jsx(티켓·문서 공용 댓글)와 같은 판정 — 수정된 댓글에는 "(수정됨)" 표시.
  const edited = comment.updated_at && comment.updated_at !== comment.created_at;
  const confirm = useConfirm();
  const [editing, setEditing] = useState(false);
  const [replying, setReplying] = useState(false);
  const [text, setText] = useState(comment.body);

  // 수정은 본문만 바꾼다 — comment_count 등 다른 화면이 보는 집계는 안 바뀌므로
  // onChanged(상세 재조회)만으로 충분하다(remove와 달리 폭넓은 무효화가 필요 없다).
  const saveEdit = useMutation({
    mutationFn: () =>
      api("/api/board/comments/" + comment.id, { method: "PATCH", body: { body: text } }),
    onSuccess: () => { setEditing(false); onChanged && onChanged(); },
    onError: (e) => toast((e && e.message) || "수정하지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  const remove = useMutation({
    mutationFn: () => api("/api/board/comments/" + comment.id, { method: "DELETE" }),
    onSuccess: () => {
      onChanged && onChanged();
      // 댓글 작성과 대칭 — 삭제도 comment_count를 바꾼다(CommentComposer.submit 주석 참고).
      qc.invalidateQueries({ queryKey: ["board"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      qc.invalidateQueries({ queryKey: ["board-mine"] });
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다. 다시 시도해 주세요.", "error"),
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
      <Stack direction="row" gap={1.5} alignItems="center" flexWrap="wrap">
        {/* 댓글에서도 작성자의 소속·사진을 말한다(사용자 지시 #13/#8) — 동명이인이면
            이름 두 글자로는 "누가 답을 달았는지"에 답할 수 없다. */}
        <Typography variant="body2" component="div">
          <AuthorLine name={comment.author_name} person={person} bold />
        </Typography>
        <Typography variant="caption" color="text.secondary">{fmtDateTime(comment.created_at)}</Typography>
        {edited ? (
          <Typography component="span" variant="caption" color="text.secondary">(수정됨)</Typography>
        ) : null}
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
        <Typography sx={{ my: 1, whiteSpace: "pre-wrap", ...KO_WORD_BREAK, fontSize: "0.9375rem" }}>
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
            /* text state는 마운트 시 한 번만 comment.body로 초기화된다(useState 초깃값).
               이 세션 안의 다른 동작(새 댓글 등록 등)이 상세를 재조회해 comment.body가
               그 사이 바뀌어도(다른 세션이 먼저 고친 경우 등) text는 리마운트 없이는
               따라가지 않는다 — "수정"을 누르는 순간 지금 comment.body로 다시 채워,
               옛 내용으로 최신 내용을 덮어쓰는 잃어버린 갱신을 막는다(취소 버튼과 같은 규칙). */
            <Button variant="ghost" size="sm" onClick={() => { setText(comment.body); setEditing(true); }}>수정</Button>
          ) : null}
          {comment.can_delete ? (
            <Button variant="ghost" size="sm" color="error" onClick={askDelete}>삭제</Button>
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


/* 제안 상태 줄 (7단계 #1) — **아이디어 글에만** 그린다.
 *
 * 다음 상태로 넘기는 것은 운영자만이고(`can_change_status`), 감추는 것은 편의일 뿐 통제는
 * 서버가 한다. '진행' 은 티켓을 만드는 자리라 프로젝트를 함께 고르게 한다 — 티켓 스키마가
 * 프로젝트를 요구하므로, 안 고르고 누르면 서버가 거절하고 상태는 그대로 남는다.
 *
 * 티켓 생성이 실패하면 상태도 안 바뀐다(app/board/service.py 에 이유를 적어 두었다).
 * 그래서 여기서는 실패를 토스트로만 알리고 화면 상태를 손대지 않는다 — 다시 누르면 된다.
 */
function IdeaStatusBar({ post, onChanged }) {
  const statuses = post.next_statuses || [];
  const toast = useToast();
  const qc = useQueryClient();
  /* 앱은 해시 라우터다(app/App.jsx) — `window.open("/tickets/…")` 로 보내면 해시가 빠진
     주소로 나가 티켓이 아니라 앱 바깥으로 떨어진다. 이동은 라우터에게 시킨다. */
  const nav = useNavigate();
  const [target, setTarget] = useState("");
  const [projectId, setProjectId] = useState("");
  const goingToProgress = target === "진행";
  /* 프로젝트 후보는 **진행으로 넘길 때만** 부른다. 상세를 열 때마다 Notion 왕복을 하나
     더 붙일 이유가 없다(ticket-options.js 의 `enabled` 규약). */
  const projects = useTicketProjects(goingToProgress);
  const projectRows = (projects.data && projects.data.projects) || [];

  const move = useMutation({
    mutationFn: () =>
      api("/api/board/posts/" + post.id + "/status", {
        method: "POST",
        body: { status: target, project_id: goingToProgress ? projectId || null : null },
      }),
    onSuccess: () => {
      setTarget("");
      setProjectId("");
      toast("제안 상태를 바꿨습니다.", "success");
      onChanged && onChanged();
      // 상태 배지는 Board.jsx 목록에도 나온다(idea_status 열) — onChanged는 이 상세
      // 화면만 다시 부르므로(L축 재감사, 댓글·반응과 같은 결함) 목록도 무효화한다.
      qc.invalidateQueries({ queryKey: ["board"] });
    },
    onError: (e) => toast((e && e.message) || "상태를 바꾸지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  const canMove = !!target && !move.isPending && (!goingToProgress || !!projectId);
  return (
    <Callout tone="info">
      <Stack direction="row" gap={1.5} alignItems="center" flexWrap="wrap">
        <Typography variant="body2" component="span">진행 상태</Typography>
        <Badge value={post.idea_status || "제안"} kind={ideaStatusKind(post.idea_status)} />
        {/* 만들어진 티켓으로 바로 건너간다 - 이 연결이 없으면 '진행' 은 그냥 글자다. */}
        {post.ticket_page_id ? (
          <Button variant="ghost" size="sm" onClick={() => nav("/tickets/" + post.ticket_page_id)}>
            연결된 티켓 보기
          </Button>
        ) : null}
        {post.can_change_status ? (
          <>
            {/* {...EMPTYABLE_SELECT} 가 없으면 MUI Select는 value=""를 "아직 안 골랐다"로 보고
                MenuItem의 라벨("상태 바꾸기")을 그리지 않는다 — 상자가 통째로 빈 채로 보여
                여기 무슨 선택지가 있는지조차 알 수 없었다(ui/filters.jsx의 EMPTYABLE_SELECT
                주석과 같은 함정, 다른 select들은 이미 이걸 쓴다). */}
            <TextField
              select size="small" value={target} sx={{ minWidth: "10rem" }}
              onChange={(e) => setTarget(e.target.value)}
              inputProps={{ "aria-label": "다음 상태" }}
              {...EMPTYABLE_SELECT}
            >
              <MenuItem value="">상태 바꾸기</MenuItem>
              {statuses.map((s) => <MenuItem key={s} value={s}>{s}</MenuItem>)}
            </TextField>
            {goingToProgress ? (
              <TextField
                select size="small" value={projectId} sx={{ minWidth: "12rem" }}
                onChange={(e) => setProjectId(e.target.value)}
                inputProps={{ "aria-label": "티켓 프로젝트" }}
                helperText={projects.isError ? "프로젝트 목록을 불러오지 못했습니다. 다시 시도해 주세요." : "티켓이 들어갈 프로젝트"}
                {...EMPTYABLE_SELECT}
              >
                <MenuItem value="">프로젝트 선택</MenuItem>
                {projectRows.map((p) => <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>)}
              </TextField>
            ) : null}
            <Button variant="primary" size="sm" disabled={!canMove} onClick={() => move.mutate()}>
              적용
            </Button>
          </>
        ) : null}
      </Stack>
    </Callout>
  );
}

export function BoardPost() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const toast = useToast();
  const confirm = useConfirm();
  const [editing, setEditing] = useState(false);

  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ["board-meta"], queryFn: () => api("/api/board/meta") });
  const detail = useQuery({
    queryKey: ["board-post", id],
    queryFn: () => api("/api/board/posts/" + id),
  });

  // VIS-133: 탭 제목을 실제 글 제목으로(Ticket.jsx·TeamDoc.jsx와 같은 이유·같은 패턴).
  const postTitle = detail.data && detail.data.post ? detail.data.post.title : "";
  useEffect(() => {
    setItemTitle(loc.pathname, postTitle);
  }, [loc.pathname, postTitle]);

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
    onSuccess: () => { refetch(); qc.invalidateQueries({ queryKey: ["board"] }); qc.invalidateQueries({ queryKey: ["home"] }); },
    onError: (e) => toast((e && e.message) || "고정 상태를 바꾸지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  const remove = useMutation({
    mutationFn: () => api("/api/board/posts/" + id, { method: "DELETE" }),
    onSuccess: () => {
      // home의 「최근 글」 위젯도 함께 무효화 — 안 하면 지운 글이 홈 탭엔 그대로 남는다(L축 재감사).
      qc.invalidateQueries({ queryKey: ["board"] });
      qc.invalidateQueries({ queryKey: ["home"] });
      // 삭제도 글쓴이의 「내 글」(board-mine)을 바꾼다 — 이 키는 지금까지 어디서도
      // 무효화된 적이 없었다(Board.jsx save mutation과 같은 이유, L축 재감사).
      qc.invalidateQueries({ queryKey: ["board-mine"] });
      toast("게시글을 삭제했습니다.", "success"); nav("/board");
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  // 로딩·오류 상태에서는 아직 post.kind를 모른다(주소만으로는 자유/제안을 가를 수 없다 —
  // 상세 라우트가 둘 다 "/board/:id" 하나를 같이 쓴다, 위 boardArea 주석 참고). 이 두 상태에서
  // area를 "자유게시판"으로 단정하면, 제안 글을 열 때(또는 그 글의 조회가 실패할 때) 로딩
  // 스켈레톤·오류 화면이 실제로는 다른 게시판인 글을 "자유게시판"이라 잘못 말한다 — 아래
  // boardArea가 고치는 것과 같은 자기모순을 이 두 상태에서 그대로 재현한다. 모를 때는
  // PageHeader의 정한 관례대로 area를 비운다(TeamDocs.jsx의 area={null}과 같은 패턴) — 틀린
  // 답을 단정하는 대신 빵부스러기 줄 자체를 생략한다.
  if (detail.isError) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="팀 공간" area={null} title="게시글" spot="board" />
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      </div>
    );
  }
  if (detail.isPending) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="팀 공간" area={null} title="게시글" spot="board" />
        <Card><Skeleton lines={8} /></Card>
      </div>
    );
  }

  const post = detail.data.post;
  const isIdea = post.kind === "idea";
  // 목록(Board.jsx)과 같은 표를 쓴다 — "목록" 버튼은 이미 종류로 갈리는데(위 actions)
  // 빵부스러기만 "자유게시판"으로 박혀 있으면, 제안 글을 열었을 때 목록은 "기능 개선
  // 제안"이라 하고 상세는 "자유게시판"이라 해 같은 화면 안에서 말이 갈렸다.
  const boardArea = (COPY[isIdea ? "idea" : "free"] || COPY.free).area;
  const comments = post.comments || [];
  /* 글쓴이·댓글 작성자의 신원(부서·직책·사진). 사람 한 명당 한 줄만 오고 댓글은 uid 로
     찾아 쓴다 — 댓글마다 되풀이하면 상세 응답이 댓글 수만큼 부푼다. 옛 캐시에는 없다. */
  const people = post.people || {};
  const { tops, repliesByParent } = splitComments(comments);

  const askDeletePost = async () => {
    const ok = await confirm("이 게시글을 삭제할까요?", { danger: true, confirmLabel: "삭제" });
    if (ok) remove.mutate();
  };

  const actions = (
    <>
      {/* 상세는 하나지만 **온 곳은 둘**이다. 제안을 열었다가 '목록'을 누르면 자유게시판이
          뜨는 것은 길을 잃는 것이다 - 종류를 보고 돌려보낸다. */}
      <Button variant="ghost" onClick={() => nav(isIdea ? "/ideas" : "/board")}>목록</Button>
      {post.can_moderate ? (
        <Button onClick={() => pin.mutate(!post.is_pinned)} disabled={pin.isPending}>
          {post.is_pinned ? "고정 해제" : "공지 고정"}
        </Button>
      ) : null}
      {post.can_edit ? <Button onClick={() => setEditing(true)}>수정</Button> : null}
      {post.can_delete ? (
        <Button variant="danger" onClick={askDeletePost} disabled={remove.isPending}>삭제</Button>
      ) : null}
    </>
  );

  return (
    <div className="c-screen">
      {/* 목록(Board.jsx)은 spot="board" 를 주는데 상세 세 상태는 전부 안 줘서, 목록에서
          글을 열면 일러스트가 사라졌다 — 같은 화면군인데 장식이 들쭉날쭉했다. */}
      {/* SEM-03 재확인(2026-08-13) — PageHeader에 실제 제목을 넘긴다(예전엔 "게시글"만
          보여줘 화면 안에 h1이 하나 더 필요했다). */}
      <PageHeader crumbRoot="팀 공간" area={boardArea} title={post.title} actions={actions} spot="board" />

      {/* 1열: 산문(78ch 상한). 2열: 메타 + 댓글 레일. lg부터 갈라진다 — 그 아래에서는 레일이
          본문 밑으로 자연스럽게 흐른다(소스 순서 = 읽는 순서라 스크린리더도 그대로 따라간다). */}
      <Box sx={{ display: "grid", rowGap: 3, maxWidth: PROSE_MAX_WIDTH_WIDE }}>
        <Card component="article" sx={{ minWidth: 0 }}>
          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            {post.is_pinned ? <Tag label="고정" /> : null}
            <Tag label={post.category} />
            {/* 🔴 상태 배지는 **종류로** 가른다(값이 아니라). 값으로 가르면 서버가 실수로
                실어 보낸 `idea_status` 가 자유게시글에 그대로 그려진다. */}
            {isIdea && post.idea_status ? (
              <Badge value={post.idea_status} kind={ideaStatusKind(post.idea_status)} />
            ) : null}
          </Stack>
          {/* SEM-03 재확인 — 제목은 이제 위 PageHeader가 h1로 보여준다. 카드 안에서 같은
              글자를 또 한 번 반복하지 않는다. */}
          <Stack direction="row" gap={2} flexWrap="wrap" alignItems="center" sx={{ mt: 1 }}>
            {/* 글쓴이가 누구인지 — 이름 옆에 소속과 사진(사용자 지시 #13/#8). */}
            <Typography variant="body2" color="text.secondary" component="div">
              <AuthorLine name={post.author_name} person={people[post.author_user_id]} />
            </Typography>
            <Typography variant="body2" color="text.secondary">{fmtDateTime(post.created_at)}</Typography>
            <Typography variant="body2" color="text.secondary">조회 {post.view_count}</Typography>
          </Stack>

          {/* 제안이면 상태 줄이 본문 **위에** 온다 - 이 글을 열어 가장 먼저 알고 싶은 것이
              "이 제안은 어떻게 됐나"이기 때문이다. 자유게시글에는 아예 없다. */}
          {isIdea ? (
            <Box sx={{ mt: 2 }}>
              {/* key={post.id} — "/board/:id"는 다른 제안으로 이동해도(알림 딥링크 등 인앱
                  이동) BoardPost 인스턴스가 재사용된다. key가 없으면 IdeaStatusBar 안의
                  target/projectId(useState)가 리마운트되지 않고 그대로 남아, A 글에서 고른
                  "다음 상태"가 B 글 드롭다운에도 이미 선택된 채로 뜬다 — 두 제안이 같은 상태
                  어휘("진행" 등)를 쓰므로 그대로 "적용"을 누르면 B 글이 사용자가 고르지 않은
                  상태로 바뀐다(board-post-idea-status-stale.test.jsx, CommentComposer의
                  key={post.id}와 같은 이유). */}
              <IdeaStatusBar key={post.id} post={post} onChanged={refetch} />
            </Box>
          ) : null}

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

        {/* 댓글은 **본문 아래 전체 폭**이다. 예전에는 메타와 함께 오른쪽 곁열에 있었는데,
            댓글은 글에 대한 대화지 글의 속성이 아니다 — 좁은 칸에 밀어 넣으면 한 줄에 대여섯
            글자가 들어가고 답글 들여쓰기까지 겹치면 읽을 수가 없다. 기준 목업도 본문 아래
            전체 폭이고, 여기서는 기준이 맞다.
            소스 순서(본문 → 메타 → 댓글)는 그대로라 스크린리더가 읽는 차례도 그대로다. */}
        <Box component="section" sx={{ minWidth: 0 }}>
            <Typography variant="h6" component="h2" sx={{ mb: 1.5 }}>댓글 {comments.length}</Typography>
            {tops.length === 0 ? (
              <Typography color="text.secondary">아직 댓글이 없습니다. 첫 댓글을 남겨 보세요.</Typography>
            ) : (
              /* 레일이 아주 넓어지는 4K에서는 댓글 묶음을 두 갈래로 접는다 — 한 줄이 2,000px가
                 되는 대신 폭을 실제로 쓴다. 답글은 자기 최상위 댓글 안에 중첩된 목록으로 남는다. */
              <Box component="ul" sx={{
                listStyle: "none", m: 0, p: 0, display: "grid", gap: 1.5, alignItems: "start",
                gridTemplateColumns: { xs: "1fr", uhd: "repeat(2, minmax(0,1fr))" },
              }}>
                {tops.map((c) => (
                  <Box component="li" key={c.id} sx={{ minWidth: 0, display: "grid", gap: 1.5 }}>
                    <CommentItem comment={c} postId={post.id} palette={palette} person={people[c.author_user_id]} onChanged={refetch} />
                    {(repliesByParent[c.id] || []).length ? (
                      <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, pl: { xs: 1.5, sm: 3 }, display: "grid", gap: 1.5 }}>
                        {(repliesByParent[c.id] || []).map((r) => (
                          <Box component="li" key={r.id} sx={{ minWidth: 0 }}>
                            <CommentItem comment={r} postId={post.id} palette={palette} isReply person={people[r.author_user_id]} onChanged={refetch} />
                          </Box>
                        ))}
                      </Box>
                    ) : null}
                  </Box>
                ))}
              </Box>
            )}
          {/* key={post.id} — "/board/:id"는 다른 글로 이동해도(알림 딥링크 등 인앱 이동)
              BoardPost 자체가 리마운트되지 않는다. key가 없으면 이 컴포저가 그대로 남아
              A 글에 쓰던 초안이 B 글 댓글창까지 따라와 "등록"을 누르면 엉뚱한 글에 달린다
              (board-post-comment-stale-draft.test.jsx). */}
          <CommentComposer key={post.id} postId={post.id} palette={palette} onDone={refetch} />
        </Box>
      </Box>

      <PostFormModal
        open={editing}
        onClose={() => setEditing(false)}
        /* 이 글의 종류에 맞는 카테고리는 **상세 응답이** 준다. 화면 진입 시 부르는 메타는
           종류를 모르고(주소로 바로 들어올 수 있다) 자유게시판 것을 받아 온다 - 그걸 쓰면
           제안을 고칠 때 '맛집'이 뜨고, 저장하면 서버가 거절한다. */
        categories={post.categories || (meta.data && meta.data.categories) || []}
        mode="edit"
        post={post}
        onSaved={() => { setEditing(false); refetch(); }}
      />
    </div>
  );
}
