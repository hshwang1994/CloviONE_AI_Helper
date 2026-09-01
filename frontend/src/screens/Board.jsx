import React, { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { useListMemory } from "../lib/listReturn.js";
import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  ListCard,
  Modal,
  ModalFooter,
  PageHeader,
  Tag,
  useConfirm,
  useToast,
} from "../ui/kit.jsx";
import { fmtDateTime, affiliationOf, ARCHIVED_SUFFIX } from "../lib/format.js";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { CONTROL, FONT_SIZE, FONT_WEIGHT, remPx } from "../ui/theme.js";
import { ideaStatusKind } from "../lib/badges.js";
import { buildPostsQuery, reactionMap } from "./board-helpers.js";
import { useQueryState } from "../lib/useQueryState.js";
import { SearchBox } from "../ui/filters.jsx";
import { FilterRow, FilterSurface, ResultLine, ToolbarEnd, ToolbarRow } from "../ui/FilterBar.jsx";
import { DateCell } from "../ui/cells.jsx";
import { ListFooter } from "../ui/InfiniteScroll.jsx";
import { useInfiniteList } from "../lib/useInfiniteList.js";

/* 게시판 목록 (팀 공간 §18). 순수 내부 기능 — 외부 호출 없음. 카테고리 필터·검색·정렬은
 * 페이지 안에서 처리하고, 글쓰기는 이 페이지의 버튼(모달)이다. 행을 누르면 상세로 이동한다.
 * 본문/제목은 React가 기본으로 textContent로 렌더하므로 XSS 없음(불변 §6).
 *
 * 2026-08 MUI 재설계: 손으로 쓴 .k-input/.board-* 마크업을 MUI 컴포넌트로 바꿨다. kit.css가
 * 걷히면서 .k-input에는 이미 아무 규칙도 남아 있지 않아 검색창·정렬 select가 브라우저 기본
 * 모양으로 떠 있었다 — 화면마다 손으로 스타일을 다시 붙이지 않고 테마 하나를 따르게 한다.
 * 열 너비는 열 정의가 **뜻으로** 정한다(`ui/columnTypes.js`): CSS nth-child로 잡으면 열
 * 순서가 바뀔 때 조용히 어긋난다.
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
    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.625, minWidth: 0, maxWidth: "100%", lineHeight: 1.25, fontSize: FONT_SIZE.bodySm }}>
      {/* **사진이 없어도 자리가 있다.** 예전에는 없으면 아무것도 안 그렸는데, 그러면
          같은 목록에서 어떤 줄에는 원이 있고 어떤 줄에는 없어 왼쪽 모서리가 들쭉날쭉했다.
          지금은 사진이 없는 사람도 자기 그림을 갖는다(`UserAvatar` → `DefaultAvatar`). */}
      <UserAvatar person={person} name={name} size="inline" />
      <Box component="span" sx={{ fontWeight: bold ? FONT_WEIGHT.bold : "inherit", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", lineHeight: 1.25 }}>
        {name || "알 수 없음"}
      </Box>
      {/* 소속이 없으면 아무것도 그리지 않는다 — 빈 괄호가 붙으면 그게 더 어수선하다. */}
      {affiliation ? (
        <Box component="span" sx={{ fontWeight: FONT_WEIGHT.regular, opacity: 0.75, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", lineHeight: 1.25 }}>
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
          InputLabelProps={{ shrink: true }}
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
          InputLabelProps={{ shrink: true }}
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
        InputLabelProps={{ shrink: true }}
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
            /* 높이를 **작은 버튼과 맞춘다** (S18). 이 칩은 댓글의 동작 줄에서
               「답글·수정·삭제」(`Button size="sm"`, 30px)와 한 줄에 선다. MUI 의
               `Chip size="small"` 은 24px 이라 같은 줄의 컨트롤 아홉이 두 높이로
               갈렸다(`control_baseline_mismatch`, 6px 차이 — S18 실측). 한 줄 안에서
               같은 종류의 컨트롤은 한 높이를 갖는다.

               🔴 **px 가 아니라 토큰이다** (S22). S18 은 그 값을 `30` 이라고 적었는데,
               옆의 작은 버튼은 `remPx(CONTROL.buttonSm)` 이라 4K 레버(`styles/root.css` 가
               루트 폰트사이즈를 16→18→20 으로 올린다)를 함께 탄다. 그래서 3072·3840 에서만
               버튼이 37.5px 로 자라고 이 칩은 30px 에 남아 **다시 7.5px 어긋났다** — 같은
               결함이 같은 자리에서 두 번 났고, 두 번째는 px 리터럴이 원인이다. */
            sx={{ fontSize: FONT_SIZE.body, height: remPx(CONTROL.buttonSm) }}
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
/* `page` 도 여기 있다 (S15).
 *
 * 서버는 이 목록을 **20건에서 자르고 총 건수를 함께 준다**(app/board/router.py). 그런데
 * 화면은 그 총 건수를 「총 87건」이라고 적어 놓고 쪽을 넘길 길을 주지 않았다 — 21번째
 * 글부터는 존재한다는 사실만 보이고 열 방법이 없었다. 조건을 바꾸면 첫 쪽으로 돌아온다
 * (`PAGE_RESET`): 세 번째 쪽을 보다가 검색을 하면 결과가 한 쪽뿐인데 빈 화면이 뜬다. */
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
    lead: "팀원과 자유롭게 이야기를 나눕니다.",
    empty: "아직 게시글이 없습니다",
    emptyHelp: "‘글쓰기’로 팀원과 나누고 싶은 첫 이야기를 남길 수 있습니다.",
    writeLabel: "글쓰기",
    route: "/board/",
  },
  idea: {
    area: "기능 개선 제안",
    title: "기능 개선 제안",
    lead: "불편한 점이나 있으면 좋겠는 기능을 올리고, 공감으로 순서를 정합니다.",
    empty: "아직 제안이 없습니다",
    emptyHelp: "‘제안하기’로 불편한 점이나 있으면 좋겠는 기능을 남길 수 있습니다.",
    writeLabel: "제안하기",
    route: "/board/",
  },
};

function BoardScreen({ kind = "free" }) {
  const nav = useNavigate();
  const isIdea = kind === "idea";
  /* 글을 열었다 돌아오면 분류·검색·정렬·페이지·스크롤이 그대로다 (지시 19). 두 게시판은
     같은 화면이지만 **다른 목록**이라 기억도 따로 한다. */
  useListMemory(isIdea ? "/ideas" : "/board");
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

  const list = useInfiniteList({
    key: ["board", kind, category, q, sort, status],
    rowId: (p) => (p && p.id) || undefined,
    fetch: ({ page }) => api("/api/board/posts?" + buildPostsQuery({ kind, category, q, sort, status, page })),
  });

  /* 작성자 신원 묶음(부서·직책·사진). 사람 한 명당 한 줄만 오고 행은 uid 로 찾아 쓴다 —
     행마다 신원을 되풀이하면 목록 응답이 그만큼 부푼다. 옛 응답·캐시에는 없을 수 있다. */
  const people = (list.first && list.first.people) || {};

  /* 폭은 열의 **뜻**에서 나온다(`type`) — 제목만 남는 폭을 전부 갖고 나머지는 내용 폭에
   * 붙는다. 4K에서도 제목 열만 넓어진다.
   *
   * 🔴 이 표는 예전에 `fixed` 로 그려졌고 그것이 열을 부쉈다(S19). `type` 이 주는 폭
   * (`SHRINK = "1%"` + 바닥값)은 auto 배치에서만 「내용만큼」이라는 뜻이고, fixed 배치는
   * 그 1% 를 글자 그대로 읽으면서 바닥값을 무시한다 — 실측에서 분류·상태·공감·조회·작성
   * 다섯 열이 1920 에서 15.6px 로 섰다. 배치 결정은 이제 `DataTable` 이 혼자 갖는다. */
  const columns = [
    {
      key: "title",
      label: "제목",
      type: "title",
      // 첫 열이 render()를 쓰면 DataTable이 행 열기 버튼의 이름을 못 만든다 — openLabel로 넘긴다.
      openLabel: (p) => "상세 보기: " + (p.title || ""),
      render: (p) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minWidth: 0 }}>
          {/* 고정은 상태가 아니라 이 글의 속성이다 — 색 등급을 매기지 않는다(지시 11). */}
          {p.is_pinned ? <Tag label="고정" /> : null}
          <Box component="span" sx={{ fontWeight: FONT_WEIGHT.semibold, overflow: "hidden", textOverflow: "ellipsis" }}>{p.title}</Box>
          {p.comment_count > 0 ? (
            <Box component="span" sx={{ color: "primary.dark", fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.bodySm, flexShrink: 0 }}>
              [{p.comment_count}]
            </Box>
          ) : null}
        </Box>
      ),
    },
    { key: "category", label: "카테고리", type: "enum", hideNarrow: true, render: (p) => <Tag label={p.category} /> },
    /* 🔴 상태 열은 **아이디어일 때만** 붙는다. 자유게시글에 상태 배지를 그리면
       "이 글은 검토중"이라는 뜻 없는 말이 되고, 서버가 실수로 값을 실어 보내는 날
       (`idea_status` 가 응답에 남는 경우) 그대로 화면에 나온다. 그래서 값이 아니라
       **종류**로 가른다 — 값으로 가르면 잘못 실려 온 값이 그대로 통과한다. */
    ...(isIdea
      ? [
          {
            key: "idea_status",
            label: "상태",
            type: "status",
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
      type: "count",
      sortable: true,
      render: (p) => "👍 " + (p.like_count || 0),
    },
    {
      key: "author_name",
      label: "작성자",
      // 이름 자리다. 바닥값 9rem 이면 소속이 붙는 순간 첫 두 글자만 남아 더 넓게 잡는다.
      type: "name", minWidth: "16rem",
      render: (p) => <AuthorLine name={p.author_name} person={people[p.author_user_id]} />,
    },
    /* 좁은 화면(900~1200)에서 먼저 접히는 둘. 분류는 바로 위 칩이 이미 말하고, 조회 수는
       어느 글을 열지 정하는 데 가장 덜 쓰인다 — 행을 열면 둘 다 상세에 있다. */
    { key: "view_count", label: "조회", type: "count", sortable: true, hideNarrow: true },
    { key: "created_at", label: "작성", type: "datetime", sortable: true, render: (p) => <DateCell value={p.created_at} /> },
  ];

  const writeBtn = <Button variant="primary" onClick={() => setComposing(true)}>{copy.writeLabel}</Button>;
  const items = list.rows;
  // 검색·카테고리가 걸려 있을 때의 '결과 없음'과, 게시판 자체가 비어 있는 '첫 글을 써 보세요'는
  // 사용자가 해야 할 일이 정반대다 — 예전엔 둘 다 "아직 게시글이 없습니다"로 뭉개져 있어서,
  // 검색어를 잘못 친 사람에게 "첫 이야기를 남겨 보세요"라고 안내했다.
  const hasFilter = !!(q || category || status);
  const clearFilters = () => setQuery({ q: "", category: "", ...(isIdea ? { status: "" } : {}) });
  const boardSortKey = sort === "views" ? "view_count" : sort === "likes" ? "like_count" : "created_at";
  const onBoardSort = (key) => {
    const next = key === "view_count" ? "views" : key === "like_count" ? "likes" : "recent";
    setQuery({ sort: next });
  };

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area={copy.area} title={copy.title} actions={writeBtn} description={copy.lead} />

      {/* SEM-02(PA-F-031): h1 하나뿐이라 필터·목록이 스크린리더 제목 탐색에서 구획 없는
          한 덩어리였다. 시각은 그대로(.sr-only), DataScreen.jsx/TeamDocs.jsx와 같은 패턴. */}
      <Typography component="h2" className="sr-only">필터</Typography>
      {/* 판이 아니다 — 지시 80이 이 화면을 이름으로 지목했다("Control 은 화면 좌측 일부만
          사용하지만 Container 는 Page 전체 폭"). 그리고 정렬 select 가 혼자 두 번째 줄에
          떨어져 있던 것(지시 76이 역시 이 화면을 이름으로 지목했다)의 원인은 배치가 아니라
          `SearchBox` 의 기본 인자였다 — `sx={undefined}` 가 기본값을 되살려 검색창이 2칸을
          먹었다. 부품에서 고쳤으므로 여기서는 그냥 «검색은 도구 줄, 정렬은 그 줄 오른쪽 끝,
          분류 칩은 내용 필터 줄» 이라는 원래 뜻대로 놓는다. */}
      <FilterSurface>
        <ToolbarRow>
          <SearchBox
            value={q}
            onSearch={commitSearch}
            placeholder="제목, 내용, 작성자 검색"
            ariaLabel="검색"
          />
          <ToolbarEnd>
            <TextField
              select size="small" label="정렬" value={sort}
              InputLabelProps={{ shrink: true }}
              onChange={(e) => setQuery({ sort: e.target.value })}
              sx={{ minWidth: "10rem" }}
            >
              {SORTS.map(([v, label]) => <MenuItem key={v} value={v}>{label}</MenuItem>)}
            </TextField>
          </ToolbarEnd>
        </ToolbarRow>
        <FilterRow>
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
          {statuses.length > 0 ? (
            <Box role="group" aria-label="상태" sx={{ display: "flex", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
              <Chip
                component="button" type="button" clickable label="전체 상태"
                aria-pressed={status === ""}
                color={status === "" ? "primary" : "default"}
                variant={status === "" ? "filled" : "outlined"}
                onClick={() => setQuery({ status: "" })}
              />
              {statuses.map((st) => (
                <Chip
                  key={st}
                  component="button" type="button" clickable label={st}
                  aria-pressed={status === st}
                  color={status === st ? "primary" : "default"}
                  variant={status === st ? "filled" : "outlined"}
                  onClick={() => setQuery({ status: st })}
                />
              ))}
            </Box>
          ) : null}
        </FilterRow>
      </FilterSurface>
      {list.first ? (
        <ResultLine
          total={list.total != null ? list.total : items.length}
          conditions={[q, category, status].filter(Boolean)}
        />
      ) : null}

      <Typography component="h2" className="sr-only">목록</Typography>
      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.isLoading ? (
        <Card>{/* 표가 들어올 자리에는 표 모양을 그린다 (지시 20) - 빈 목록과 아직 안 온 목록은 다른 사실이다. */}<DataTable columns={columns} rows={[]} loading /></Card>
      ) : items.length === 0 ? (
        hasFilter ? (
          <EmptyState
            layout="page"
            art="search"
            title="검색 결과가 없습니다"
            help="조건에 맞는 게시글이 없습니다. 검색어를 지우거나 카테고리를 ‘전체’로 되돌려 보세요."
            action={<Button variant="primary" onClick={clearFilters}>검색, 카테고리 지우기</Button>}
          />
        ) : (
          /* 🔴 여기에 «글쓰기» 를 다시 두지 않는다 (S19) — 상단 행동과 같은 일이다.
             `copy.emptyHelp` 가 그 버튼을 이름으로 가리킨다. 조건 때문에 0건인 위쪽
             갈래는 다르다: «조건 지우기» 는 상단에 없는 **다른 행동**이라 CTA 를 갖는다. */
          <EmptyState
            layout="page"
            art="board"
            title={copy.empty}
            help={copy.emptyHelp}
          />
        )
      ) : (
        <ListCard>
          <DataTable
            columns={columns}
            rows={items}
            rowKey={(p) => p.id}
            ellipsis
            sort={{ key: boardSortKey, dir: "desc" }}
            onSort={onBoardSort}
            /* 어디서 왔는지를 남긴다 — 상세의 「목록」이 그 목록의 **그 상태**로
               돌아가는 근거다(`lib/listReturn.js`). 두 게시판이 상세를 공유하므로
               이 값이 없으면 제안 글에서 자유게시판으로 떨어진다. */
            onRow={(p) => nav(copy.route + p.id, { state: { from: isIdea ? "/ideas" : "/board" } })}
          />
          {/* 서버가 자른 목록에는 더 받을 길이 있어야 한다 — 없으면 위 결과 줄이 말하는
              건수의 대부분이 열 수 없는 숫자가 된다. */}
          <ListFooter
            total={list.total} loaded={list.loaded}
            hasNext={list.hasNext} isFetchingNext={list.isFetchingNext} onMore={list.fetchNext}
            moreLabel="글 더 보기"
          />
        </ListCard>
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
