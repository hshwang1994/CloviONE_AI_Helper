import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  Modal,
  ModalFooter,
  PageHeader,
  Skeleton,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { fmtDateTime, affiliationOf, ARCHIVED_SUFFIX } from "../lib/format.js";
import { FONT_SIZE, FONT_WEIGHT, PROSE_MAX_WIDTH } from "../ui/theme.js";
import { boardCategoryKind, ideaStatusKind } from "../lib/badges.js";
import { buildPostsQuery, reactionMap } from "./board-helpers.js";
import { useQueryState } from "../lib/useQueryState.js";
import { SearchBox } from "../ui/filters.jsx";
import { DateCell } from "../ui/cells.jsx";

/* 게시판 목록 (팀 공간 §18). 순수 내부 기능 — 외부 호출 없음. 카테고리 필터·검색·정렬은
 * 페이지 안에서 처리하고, 글쓰기는 이 페이지의 버튼(모달)이다. 행을 누르면 상세로 이동한다.
 * 본문/제목은 React가 기본으로 textContent로 렌더하므로 XSS 없음(불변 §6).
 *
 * 2026-08 MUI 재설계: 손으로 쓴 .k-input/.board-* 마크업을 MUI 컴포넌트로 바꿨다. kit.css가
 * 걷히면서 .k-input에는 이미 아무 규칙도 남아 있지 않아 검색창·정렬 select가 브라우저 기본
 * 모양으로 떠 있었다 — 화면마다 손으로 스타일을 다시 붙이지 않고 테마 하나를 따르게 한다.
 * 열 너비는 열 정의에 함께 적는다(fixed + ellipsis): CSS nth-child로 잡으면 열 순서가 바뀔 때
 * 조용히 어긋난다.
 *
 * ## 종류가 둘인데 화면은 하나다 (7단계 #1)
 *
 * 기능 개선 제안 게시판은 이 화면을 **종류만 바꿔** 쓴다(`kind="idea"`). 화면을 복사했다면
 * 빈 상태 두 종류·검색·작성 모달·첨부 업로드·작성자 신원 렌더가 전부 두 벌이 되고, 다음에
 * 게시판을 고칠 때 한쪽만 고쳐진다 — 서버에서 표를 안 나눈 것과 정확히 같은 이유다.
 * 다른 것은 셋뿐이고 전부 `kind` 하나로 갈린다: 상태 필터/열, 기본 정렬, 화면 문구.
 */

const SORTS = [
  ["recent", "최신순"],
  ["views", "조회순"],
  ["likes", "공감순"],
];
const UPLOAD_ACCEPT = "image/png,image/jpeg,image/gif,image/webp,application/pdf";
const MAX_FILES = 5;
const MAX_FILE_BYTES = 10 * 1024 * 1024; // 서버 uploads.MAX_UPLOAD_BYTES와 동일(10MB)

/* 작성자 한 줄 — 사진 + 이름 + 소속(+보관됨). 목록·상세·댓글이 **같은 것**을 쓴다.
 *
 * 사용자 지시(#13/#8): "게시글과 댓글에는 작성자의 부서·팀·직책을 함께 표시한다",
 * "프로필 사진이 다른 사용자 화면에서도 보이는 구조인지 확인한다".
 * 표시 이름에는 유일성 제약이 없어(`app/users/models.py`) 이름만으로는 동명이인을
 * 구분할 수 없다 — 서버가 `people: {uid: identity(...)}` 로 보내는 것을 여기서 그린다
 * (채팅 말풍선 `ChatPane.jsx` 와 같은 규칙, 같은 `affiliationOf`).
 *
 * 자리를 세 곳에 베껴 두지 않는 이유는 규칙이 세 개라서다 — 없을 때 **안 그리는** 규칙은
 * 한 곳만 빠뜨려도 그 화면만 빈 괄호·빈 회색 원이 줄줄이 붙는다.
 */
export function AuthorLine({ name, person, bold = false }) {
  const affiliation = affiliationOf(person);
  return (
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.625, minWidth: 0, maxWidth: "100%" }}>
      {/* 사진이 없으면 자리를 만들지 않는다 — 빈 회색 원이 줄줄이 붙으면 더 어수선하다. */}
      {person?.avatar_url ? (
        <Box
          component="img"
          src={person.avatar_url}
          alt=""
          loading="lazy"
          decoding="async"
          sx={{ width: 20, height: 20, borderRadius: "50%", objectFit: "cover", flexShrink: 0 }}
        />
      ) : null}
      <Box component="span" sx={{ fontWeight: bold ? FONT_WEIGHT.bold : "inherit", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
        {name || "알 수 없음"}
      </Box>
      {/* 소속이 없으면 아무것도 그리지 않는다 — 빈 괄호가 붙으면 그게 더 어수선하다. */}
      {affiliation ? (
        <Box component="span" sx={{ fontWeight: FONT_WEIGHT.regular, opacity: 0.75, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
          {affiliation}
        </Box>
      ) : null}
      {/* 떠난 사람이면 그렇다고 말한다 — 안 하면 답이 안 오는 글에 답글을 단다(N3). */}
      {person?.archived ? (
        <Box component="span" sx={{ fontWeight: FONT_WEIGHT.regular, opacity: 0.6, flexShrink: 0 }}>{ARCHIVED_SUFFIX}</Box>
      ) : null}
    </Box>
  );
}

/* 게시글 작성/수정 공용 모달. mode="create"면 새 글, mode="edit"면 기존 글 수정.
 * 첨부 업로드는 생성 직후(또는 기존 글에) 순차로 올린다(FormData).
 *
 * `kind` 는 **생성에만** 실린다. 수정에서 종류를 바꿀 수 있게 하면 상태가 붙은 제안이
 * 자유글이 되어 배지가 유령처럼 남는다 — 서버 스키마(PostUpdate)도 같은 이유로 안 받는다. */
export function PostFormModal({ open, onClose, categories, mode = "create", post, onSaved, kind = "free" }) {
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [category, setCategory] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [files, setFiles] = useState([]);
  // 열릴 때(또는 mode/post가 바뀔 때)의 값 스냅샷 — dirty(변경) 판정 기준(VIS-88, FormModal의
  // initialRef와 같은 패턴). edit이면 원본 글, create면 빈 값 + 기본 카테고리가 기준이다.
  const initialRef = useRef({ category: "", title: "", body: "" });
  // board-meta 쿼리(기본 카테고리의 출처)가 열려 있는 동안 배경에서 다시 응답하면, 값이 똑같아도
  // fetch/JSON.parse가 항상 새 배열을 만든다 — categories를 아래 이펙트의 의존성에 두면 그 새
  // 참조만으로 이펙트가 다시 돌아 사용자가 입력 중이던 제목·본문까지 빈 문자열로 되돌렸다.
  // ref로 최신값만 읽고 의존성에서는 뺀다: 모달이 열리는 "그 순간"의 카테고리로 기본값을 잡는
  // 것은 그대로 하되, 열려 있는 동안의 재조회는 더는 폼을 건드리지 않는다.
  const categoriesRef = useRef(categories);
  useEffect(() => { categoriesRef.current = categories; });

  useEffect(() => {
    if (!open) return;
    if (mode === "edit" && post) {
      setCategory(post.category);
      setTitle(post.title);
      setBody(post.body || "");
      initialRef.current = { category: post.category, title: post.title, body: post.body || "" };
    } else {
      // 기본 카테고리는 **서버가 준 첫 값**이다. 화면에 상수를 적어 두면 종류마다 다른
      // 목록에서 한쪽만 맞고, 그 순간 폼이 이 게시판에 없는 값을 보낸다.
      const cat = (categoriesRef.current && categoriesRef.current[0]) || "";
      setCategory(cat);
      setTitle("");
      setBody("");
      initialRef.current = { category: cat, title: "", body: "" };
    }
    setFiles([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- categories는 의도적으로 뺀다(위 주석).
  }, [open, mode, post]);

  const save = useMutation({
    mutationFn: async () => {
      // 1) 글 저장이 커밋 지점이다. 이게 성공하면 작업은 성공으로 본다.
      let target;
      if (mode === "edit" && post) {
        const res = await api("/api/board/posts/" + post.id, {
          method: "PATCH",
          body: { category, title, body },
        });
        target = res.post;
      } else {
        const res = await api("/api/board/posts", {
          method: "POST",
          body: { kind, category, title, body },
        });
        target = res.post;
      }
      // 2) 첨부는 best-effort — 하나 실패해도 글 저장을 되돌리거나 전체를 실패시키지 않는다.
      //    (예전엔 첨부 실패가 mutation 전체를 reject시켜 모달이 열린 채 남고, 다시 누르면
      //     글이 중복 생성됐다.) 실패한 파일명만 모아 경고로 알린다.
      const failed = [];
      for (const f of files.slice(0, MAX_FILES)) {
        try {
          const fd = new FormData();
          fd.append("file", f);
          await api("/api/board/posts/" + target.id + "/attachments", {
            method: "POST",
            body: fd,
          });
        } catch (e) {
          failed.push(f.name);
        }
      }
      return { target, failed };
    },
    onSuccess: ({ target, failed }) => {
      // 목록 캐시 무효화 — 없으면 30초 staleTime 안에 방금 만든/고친 글이 빠진 목록을 본다.
      qc.invalidateQueries({ queryKey: ["board"] });
      // home의 「최근 글」 위젯(Home.jsx recent.board)도 같은 자료를 보여준다 — 문서판과
      // 같은 결함 부류(L축 재감사, document-views.js 참고).
      qc.invalidateQueries({ queryKey: ["home"] });
      // 글 작성자 자신의 「내 글」(board-mine, Home.jsx MyBoardStats)도 새 글에서 바뀐다 —
      // 이 키는 지금까지 어떤 게시판 mutation에서도 무효화된 적이 없었다(L축 재감사).
      // 수정은 post_count를 안 바꾸지만, mode로 분기하는 비용보다 여기 한 줄이 더 싸다.
      qc.invalidateQueries({ queryKey: ["board-mine"] });
      if (failed && failed.length) {
        toast("글은 저장했지만 첨부 " + failed.length + "개를 올리지 못했습니다: " + failed.join(", ") + ". 다시 시도해 주세요.", "error");
      } else {
        toast(mode === "edit" ? "게시글을 수정했습니다." : "게시글을 추가했습니다.", "success");
      }
      onSaved && onSaved(target);
    },
    onError: (e) => toast((e && e.message) || "저장에 실패했습니다. 다시 시도해 주세요.", "error"),
  });

  const canSave = title.trim().length > 0 && !save.isPending;
  // 뭔가 바꿨으면 Esc·바깥 클릭·X·'취소' 전부에서 확인을 받는다(VIS-88) — 첨부까지 고른
  // 뒤 실수로 닫으면 전부 다시 해야 했다. `Modal`의 `dirty` prop은 Esc/바깥클릭/X만 지킨다
  // — 하단 '취소' 버튼은 onClose를 직접 불러 그 가드를 우회하므로(Games.jsx가 이미 겪은
  // 문제) 여기서도 requestClose로 감싼다.
  const dirty = files.length > 0 ||
    title !== initialRef.current.title ||
    body !== initialRef.current.body ||
    category !== initialRef.current.category;
  async function requestClose() {
    if (!dirty) { onClose(); return; }
    const ok = await confirm("입력한 내용이 저장되지 않았습니다. 창을 닫을까요?",
      { danger: true, title: "변경 사항 버리기", confirmLabel: "닫기" });
    if (ok) onClose();
  }
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mode === "edit" ? "게시글 수정" : "새 게시글"}
      size="lg"
      dirty={dirty}
      footer={
        <ModalFooter
          onCancel={requestClose}
          onSubmit={() => canSave && save.mutate()}
          submitLabel={mode === "edit" ? "수정" : "추가"}
          busy={save.isPending}
        />
      }
    >
      {/* 카테고리·제목은 한 줄에 나란히(넓은 화면) — 세로로만 쌓으면 본문 입력이 접힌 아래로 밀린다. */}
      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "1fr", sm: "12rem minmax(0,1fr)" } }}>
        <TextField
          id="board-cat"
          select
          size="small"
          label="카테고리"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          {(categories || []).map((c) => (
            <MenuItem key={c} value={c}>{c}</MenuItem>
          ))}
        </TextField>
        <TextField
          id="board-title"
          size="small"
          required
          label="제목"
          inputProps={{ maxLength: 200 }}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </Box>
      <TextField
        id="board-body"
        label="내용"
        size="small"
        fullWidth
        multiline
        minRows={8}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        sx={{ mt: 2.5 }}
      />
      <TextField
        id="board-files"
        type="file"
        size="small"
        fullWidth
        label={`첨부 (이미지 또는 PDF, 최대 ${MAX_FILES}개, 각 10MB)`}
        InputLabelProps={{ shrink: true }}
        inputProps={{ multiple: true, accept: UPLOAD_ACCEPT }}
        helperText={files.length > 0 ? files.map((f) => f.name).join(", ") : undefined}
        onChange={(e) => {
          const picked = Array.from(e.target.files || []);
          const tooBig = picked.filter((f) => f.size > MAX_FILE_BYTES).map((f) => f.name);
          let ok = picked.filter((f) => f.size <= MAX_FILE_BYTES);
          if (ok.length > MAX_FILES) ok = ok.slice(0, MAX_FILES);
          if (tooBig.length) toast("10MB를 넘어 제외했습니다: " + tooBig.join(", "), "error");
          setFiles(ok);
        }}
        sx={{ mt: 2.5 }}
      />
    </Modal>
  );
}

/* 이모지 반응 바 — 대상(게시글/댓글)에 팔레트 이모지를 토글한다. mine이면 DELETE, 아니면 POST. */
export function Reactions({ targetType, targetId, reactions, palette, onChanged }) {
  const toast = useToast();
  const qc = useQueryClient();
  const byEmoji = reactionMap(reactions);
  const toggle = useMutation({
    mutationFn: async (emoji) => {
      const mine = byEmoji[emoji] && byEmoji[emoji].mine;
      await api("/api/board/reactions", {
        method: mine ? "DELETE" : "POST",
        body: { target_type: targetType, target_id: targetId, emoji },
      });
    },
    onSuccess: () => {
      onChanged && onChanged();
      // 게시글 반응은 Board.jsx 목록의 like_count 열(제안 게시판 기본 정렬 기준)에도
      // 나온다 — onChanged는 상세 화면 자신만 다시 부르므로(L축 재감사, 댓글/상태
      // 변경과 같은 결함), 목록도 함께 무효화한다. 댓글 반응은 목록에 안 나오는
      // 값이라 사실 필요 없지만, 대상 종류를 분기하는 비용보다 여기 한 줄이 더 싸다.
      qc.invalidateQueries({ queryKey: ["board"] });
    },
    onError: (e) => toast((e && e.message) || "반응을 저장하지 못했습니다. 다시 시도해 주세요.", "error"),
  });
  return (
    <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
      {(palette || []).map((emoji) => {
        const r = byEmoji[emoji];
        const mine = r && r.mine;
        const count = r ? r.count : 0;
        return (
          <Chip
            key={emoji}
            component="button"
            type="button"
            clickable
            size="small"
            disabled={toggle.isPending}
            onClick={() => toggle.mutate(emoji)}
            aria-pressed={mine ? true : false}
            color={mine ? "primary" : "default"}
            variant={mine ? "filled" : "outlined"}
            label={count > 0 ? `${emoji} ${count}` : emoji}
            sx={{ fontSize: FONT_SIZE.body }}
          />
        );
      })}
    </Box>
  );
}

/* 이 화면이 주소에 두는 상태. 기본값과 같은 값은 주소에 안 쓴다(lib/useQueryState.js).
 *
 * 예전에는 `useState` 네 개였고, 그래서 상세를 열었다가 돌아오면 필터가 풀렸다 — 티켓·
 * 문서에서 사용자가 두 번 지적한 그 증상이다. 주소가 유일한 진실이면 뒤로가기·새로고침·
 * 링크 공유가 한꺼번에 해결된다.
 *
 * **모듈 상수여야 한다.** 렌더마다 새 객체를 만들면 훅 안의 메모가 매번 깨진다.
 * 종류마다 다른 이유는 두 가지뿐이다: 아이디어에는 `status` 가 있고, 기본 정렬이 공감순이다
 * (제안 게시판에서 먼저 보고 싶은 것은 최신 글이 아니라 **많이 공감한 제안**이다). */
const FREE_SPEC = { category: "", q: "", sort: "recent" };
const IDEA_SPEC = { category: "", q: "", sort: "likes", status: "" };
const SPEC_BY_KIND = { free: FREE_SPEC, idea: IDEA_SPEC };

/* 종류마다 다른 것은 문구뿐이다. 화면 구조는 하나다.
 * BoardPost.jsx(상세)도 같은 표를 쓴다 — area(빵부스러기)가 "자유게시판"으로 박혀 있으면
 * 제안 글 상세를 열었을 때 목록은 "기능 개선 제안"인데 상세만 "자유게시판"이라 말해
 * 지금 보고 있는 게 어느 게시판인지 자기모순을 낸다. 한 표만 소유한다. */
export const COPY = {
  free: {
    area: "자유게시판",
    title: "자유게시판",
    lead: "팀원과 자유롭게 이야기를 나누는 공간입니다.",
    empty: "아직 게시글이 없습니다",
    emptyHelp: "위 ‘글쓰기’로 팀원과 나누고 싶은 첫 이야기를 남겨 보세요.",
    writeLabel: "글쓰기",
    route: "/board/",
  },
  idea: {
    area: "기능 개선 제안",
    title: "기능 개선 제안",
    lead: "ClovirAssist 를 어떻게 고치면 좋을지 제안하고, 공감으로 우선순위를 정합니다.",
    empty: "아직 제안이 없습니다",
    emptyHelp: "위 ‘제안하기’로 불편한 점이나 있으면 좋겠는 기능을 남겨 보세요.",
    writeLabel: "제안하기",
    route: "/board/",
  },
};

function BoardScreen({ kind = "free" }) {
  const nav = useNavigate();
  const isIdea = kind === "idea";
  const copy = COPY[kind] || COPY.free;
  const [query, setQuery] = useQueryState(SPEC_BY_KIND[kind] || FREE_SPEC);
  const { category, q, sort } = query;
  // 자유게시판 스펙에는 `status` 자체가 없다 — 주소에 실려 와도 읽지 않는다.
  const status = isIdea ? query.status : "";
  const [composing, setComposing] = useState(false);

  /* 검색어 확정은 `SearchBox` 가 디바운스해서 부른다. **참조가 고정**돼야 한다 —
     매 렌더마다 새로 만들면 React.memo 가 깨져 글자마다 목록이 다시 그려진다. */
  const commitSearch = React.useCallback((next) => setQuery({ q: next }), [setQuery]);

  /* 메타는 종류마다 다르다(카테고리·상태 목록). 질의 키에 종류를 넣지 않으면 두 게시판이
     같은 캐시를 나눠 쓰며 서로의 카테고리를 그린다. */
  const meta = useQuery({
    queryKey: ["board-meta", kind],
    // 자유게시판은 `kind` 를 안 싣는다(목록 쿼리와 같은 규칙) — 서버 기본값이 자유라,
    // 안 싣는 쪽이 예전 요청과 글자 그대로 같다.
    queryFn: () => api("/api/board/meta" + (isIdea ? "?kind=idea" : "")),
  });
  const categories = (meta.data && meta.data.categories) || [];
  /* 상태 칩을 그릴지는 **서버가 준 목록**으로 정한다. 자유게시판에는 빈 배열이 온다 —
     화면에 `kind === "idea"` 판정을 하나 더 적으면 규칙이 두 군데가 된다. */
  const statuses = (isIdea && meta.data && meta.data.statuses) || [];

  const list = useQuery({
    queryKey: ["board", kind, category, q, sort, status],
    queryFn: () => api("/api/board/posts?" + buildPostsQuery({ kind, category, q, sort, status })),
  });

  /* 작성자 신원 묶음(부서·직책·사진). 사람 한 명당 한 줄만 오고 행은 uid 로 찾아 쓴다 —
     행마다 신원을 되풀이하면 목록 응답이 그만큼 부푼다. 옛 응답·캐시에는 없을 수 있다. */
  const people = (list.data && list.data.people) || {};

  /* 폭은 열 정의에 함께 적는다(DataTable fixed + ellipsis) — 제목만 남는 폭을 전부 갖고
   * 나머지는 내용 길이와 무관하게 고정된다. 4K에서도 제목 열만 넓어진다. */
  const columns = [
    {
      key: "title",
      label: "제목",
      // 첫 열이 render()를 쓰면 DataTable이 행 열기 버튼의 이름을 못 만든다 — openLabel로 넘긴다.
      openLabel: (p) => "상세 보기: " + (p.title || ""),
      render: (p) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0 }}>
          {p.is_pinned ? <Badge value="고정" kind="info" /> : null}
          <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, overflow: "hidden", textOverflow: "ellipsis" }}>{p.title}</Box>
          {p.comment_count > 0 ? (
            <Box component="span" sx={{ color: "primary.dark", fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.bodySm, flexShrink: 0 }}>
              [{p.comment_count}]
            </Box>
          ) : null}
        </Box>
      ),
    },
    { key: "category", label: "카테고리", width: "8rem", render: (p) => <Badge value={p.category} kind={boardCategoryKind(p.category)} /> },
    /* 🔴 상태 열은 **아이디어일 때만** 붙는다. 자유게시글에 상태 배지를 그리면
       "이 글은 검토중"이라는 뜻 없는 말이 되고, 서버가 실수로 값을 실어 보내는 날
       (`idea_status` 가 응답에 남는 경우) 그대로 화면에 나온다. 그래서 값이 아니라
       **종류**로 가른다 — 값으로 가르면 잘못 실려 온 값이 그대로 통과한다. */
    ...(isIdea
      ? [
          {
            key: "idea_status",
            label: "상태",
            width: "7rem",
            render: (p) =>
              p.idea_status ? <Badge value={p.idea_status} kind={ideaStatusKind(p.idea_status)} /> : null,
          },
        ]
      : []),
    /* VIS-141: `like_count`는 아이디어 전용 값이 아니다 — `list_posts`(app/board/router.py)가
       두 종류 모두에 `repository.like_counts()`로 채워 준다(위 Reactions 컴포넌트 onSuccess의
       주석 참고). 그런데 이 열은 `isIdea`일 때만 그려져, 자유게시판은 댓글 수([N] 배지)는
       보이는데 반응 수는 화면 어디서도 못 봤다 — "볼 만한 글" 신호가 절반만 있었다. */
    {
      key: "like_count",
      label: "공감",
      align: "right",
      width: "6rem",
      render: (p) => "👍 " + (p.like_count || 0),
    },
    {
      key: "author_name",
      label: "작성자",
      // 이름만 있던 칸이라 9rem 이면 소속이 붙는 순간 첫 두 글자만 남는다.
      width: "16rem",
      render: (p) => <AuthorLine name={p.author_name} person={people[p.author_user_id]} />,
    },
    { key: "view_count", label: "조회", align: "right", width: "6rem" },
    { key: "created_at", label: "작성", align: "right", width: "11rem", nowrap: true, render: (p) => <DateCell value={p.created_at} /> },
  ];

  const writeBtn = <Button variant="primary" onClick={() => setComposing(true)}>{copy.writeLabel}</Button>;
  const items = (list.data && list.data.items) || [];
  // 검색·카테고리가 걸려 있을 때의 '결과 없음'과, 게시판 자체가 비어 있는 '첫 글을 써 보세요'는
  // 사용자가 해야 할 일이 정반대다 — 예전엔 둘 다 "아직 게시글이 없습니다"로 뭉개져 있어서,
  // 검색어를 잘못 친 사람에게 "첫 이야기를 남겨 보세요"라고 안내했다.
  const hasFilter = !!(q || category || status);
  const clearFilters = () => setQuery({ q: "", category: "", ...(isIdea ? { status: "" } : {}) });

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area={copy.area} title={copy.title} actions={writeBtn} spot="board" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: PROSE_MAX_WIDTH }}>
        {copy.lead}
      </Typography>

      {/* SEM-02(PA-F-031): h1 하나뿐이라 필터·목록이 스크린리더 제목 탐색에서 구획 없는
          한 덩어리였다. 시각은 그대로(.sr-only), DataScreen.jsx/TeamDocs.jsx와 같은 패턴. */}
      <Typography component="h2" className="sr-only">필터</Typography>
      <Card className="c-toolbar-card" sx={{ p: 2, mb: 2.5 }}>
        {/* VIS-92: 예전엔 카테고리(왼쪽)·검색+정렬(오른쪽) 순이었다 — 다른 필터 화면(표
            기반 목록 28개 + 티켓 필터 4개)은 전부 "왼쪽 검색 + 오른쪽 필터"라 이 화면만
            좌우가 뒤집혀 있었다(DS-12/DS-13에 이은 네 번째 관용 불일치). 카테고리는 칩
            묶음이라 값 개수만큼 자유롭게 줄바꿈해야 하므로(TicketFilterBar의 select처럼
            고정 폭 칸에 넣지 않는다) 그리드 자체를 새로 쓰지 않고, 기존 두 열의 순서와
            폭 배분(가변 열이 칩 쪽)만 검색이 먼저 오도록 뒤집는다. */}
        <Box sx={{
          display: "grid", gap: 1.5, alignItems: "center",
          gridTemplateColumns: { xs: "1fr", lg: "auto minmax(0,1fr)" },
        }}>
          <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", sm: "minmax(12rem,1fr) 9rem" } }}>
            <SearchBox
              value={q}
              onSearch={commitSearch}
              placeholder="제목, 내용, 작성자 검색"
              ariaLabel="검색"
              sx={undefined}
            />
            <TextField
              select size="small" value={sort}
              onChange={(e) => setQuery({ sort: e.target.value })}
              inputProps={{ "aria-label": "정렬" }}
            >
              {SORTS.map(([v, label]) => <MenuItem key={v} value={v}>{label}</MenuItem>)}
            </TextField>
          </Box>
          <Box role="group" aria-label="카테고리" sx={{ display: "flex", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
            <Chip
              component="button" type="button" clickable label="전체"
              aria-pressed={category === ""}
              color={category === "" ? "primary" : "default"}
              variant={category === "" ? "filled" : "outlined"}
              onClick={() => setQuery({ category: "" })}
            />
            {categories.map((c) => (
              <Chip
                key={c}
                component="button" type="button" clickable label={c}
                aria-pressed={category === c}
                color={category === c ? "primary" : "default"}
                variant={category === c ? "filled" : "outlined"}
                onClick={() => setQuery({ category: c })}
              />
            ))}
          </Box>
        </Box>
        {statuses.length > 0 ? (
          <Box
            role="group"
            aria-label="상태"
            sx={{ display: "flex", gap: 1, flexWrap: "wrap", minWidth: 0, mt: 1.5 }}
          >
            <Chip
              component="button" type="button" clickable label="전체 상태"
              aria-pressed={status === ""}
              color={status === "" ? "primary" : "default"}
              variant={status === "" ? "filled" : "outlined"}
              onClick={() => setQuery({ status: "" })}
            />
            {statuses.map((s) => (
              <Chip
                key={s}
                component="button" type="button" clickable label={s}
                aria-pressed={status === s}
                color={status === s ? "primary" : "default"}
                variant={status === s ? "filled" : "outlined"}
                onClick={() => setQuery({ status: s })}
              />
            ))}
          </Box>
        ) : null}
      </Card>

      <Typography component="h2" className="sr-only">목록</Typography>
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.isPending ? (
        <Card><Skeleton lines={6} /></Card>
      ) : items.length === 0 ? (
        hasFilter ? (
          <EmptyState
            art="search"
            title="검색 결과가 없습니다"
            help="조건에 맞는 게시글이 없습니다. 검색어를 지우거나 카테고리를 ‘전체’로 되돌려 보세요."
            action={<Button variant="primary" onClick={clearFilters}>검색, 카테고리 지우기</Button>}
          />
        ) : (
          <EmptyState
            art="board"
            title={copy.empty}
            help={copy.emptyHelp}
            action={writeBtn}
          />
        )
      ) : (
        <Card className="c-list-card">
          <DataTable
            columns={columns}
            rows={items}
            rowKey={(p) => p.id}
            fixed
            ellipsis
            onRow={(p) => nav(copy.route + p.id)}
          />
        </Card>
      )}

      <PostFormModal
        open={composing}
        onClose={() => setComposing(false)}
        categories={categories}
        kind={kind}
        mode="create"
        onSaved={(post) => { setComposing(false); nav(copy.route + post.id); }}
      />
    </div>
  );
}

/* 두 게시판은 **같은 화면**이다. 종류만 다르다 — 라우트가 그 하나를 정한다. */
export function Board() {
  return <BoardScreen kind="free" />;
}

export function IdeaBoard() {
  return <BoardScreen kind="idea" />;
}
