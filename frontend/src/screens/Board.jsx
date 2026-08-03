import React, { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
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
  useToast,
} from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { boardCategoryKind } from "../lib/badges.js";
import { buildPostsQuery, reactionMap } from "./board-helpers.js";

/* 자유게시판 목록 (팀 공간 §18). 순수 내부 기능 — 외부 호출 없음. 카테고리 필터·검색·정렬은
 * 페이지 안에서 처리하고, 글쓰기는 이 페이지의 버튼(모달)이다. 행을 누르면 상세로 이동한다.
 * 본문/제목은 React가 기본으로 textContent로 렌더하므로 XSS 없음(불변 §6).
 *
 * 2026-08 MUI 재설계: 손으로 쓴 .k-input/.board-* 마크업을 MUI 컴포넌트로 바꿨다. kit.css가
 * 걷히면서 .k-input에는 이미 아무 규칙도 남아 있지 않아 검색창·정렬 select가 브라우저 기본
 * 모양으로 떠 있었다 — 화면마다 손으로 스타일을 다시 붙이지 않고 테마 하나를 따르게 한다.
 * 열 너비는 열 정의에 함께 적는다(fixed + ellipsis): CSS nth-child로 잡으면 열 순서가 바뀔 때
 * 조용히 어긋난다. */

const SORTS = [
  ["recent", "최신순"],
  ["views", "조회순"],
];
const UPLOAD_ACCEPT = "image/png,image/jpeg,image/gif,image/webp,application/pdf";
const MAX_FILES = 5;
const MAX_FILE_BYTES = 10 * 1024 * 1024; // 서버 uploads.MAX_UPLOAD_BYTES와 동일(10MB)

function useDebounced(value, ms) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/* 게시글 작성/수정 공용 모달. mode="create"면 새 글, mode="edit"면 기존 글 수정.
 * 첨부 업로드는 생성 직후(또는 기존 글에) 순차로 올린다(FormData). */
export function PostFormModal({ open, onClose, categories, mode = "create", post, onSaved }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [category, setCategory] = useState("자유");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [files, setFiles] = useState([]);

  useEffect(() => {
    if (!open) return;
    if (mode === "edit" && post) {
      setCategory(post.category);
      setTitle(post.title);
      setBody(post.body || "");
    } else {
      setCategory((categories && categories[0]) || "자유");
      setTitle("");
      setBody("");
    }
    setFiles([]);
  }, [open, mode, post, categories]);

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
          body: { category, title, body },
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
      if (failed && failed.length) {
        toast("글은 저장했지만 첨부 " + failed.length + "개를 올리지 못했습니다: " + failed.join(", "), "error");
      } else {
        toast(mode === "edit" ? "게시글을 수정했습니다." : "게시글을 등록했습니다.", "success");
      }
      onSaved && onSaved(target);
    },
    onError: (e) => toast((e && e.message) || "저장에 실패했습니다.", "error"),
  });

  const canSave = title.trim().length > 0 && !save.isPending;
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mode === "edit" ? "게시글 수정" : "새 게시글"}
      size="lg"
      footer={
        <ModalFooter
          onCancel={onClose}
          onSubmit={() => canSave && save.mutate()}
          submitLabel={mode === "edit" ? "수정" : "등록"}
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
  const byEmoji = reactionMap(reactions);
  const toggle = useMutation({
    mutationFn: async (emoji) => {
      const mine = byEmoji[emoji] && byEmoji[emoji].mine;
      await api("/api/board/reactions", {
        method: mine ? "DELETE" : "POST",
        body: { target_type: targetType, target_id: targetId, emoji },
      });
    },
    onSuccess: () => onChanged && onChanged(),
    onError: (e) => toast((e && e.message) || "반응을 저장하지 못했습니다.", "error"),
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
            sx={{ fontSize: "0.875rem" }}
          />
        );
      })}
    </Box>
  );
}

export function Board() {
  const nav = useNavigate();
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("recent");
  const [qInput, setQInput] = useState("");
  const q = useDebounced(qInput, 300);
  const [composing, setComposing] = useState(false);

  const meta = useQuery({ queryKey: ["board-meta"], queryFn: () => api("/api/board/meta") });
  const categories = (meta.data && meta.data.categories) || [];

  const list = useQuery({
    queryKey: ["board", category, q, sort],
    queryFn: () => api("/api/board/posts?" + buildPostsQuery({ category, q, sort })),
  });

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
          <Box component="span" sx={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis" }}>{p.title}</Box>
          {p.comment_count > 0 ? (
            <Box component="span" sx={{ color: "primary.main", fontWeight: 700, fontSize: "0.8125rem", flexShrink: 0 }}>
              [{p.comment_count}]
            </Box>
          ) : null}
        </Box>
      ),
    },
    { key: "category", label: "카테고리", width: "8rem", render: (p) => <Badge value={p.category} kind={boardCategoryKind(p.category)} /> },
    { key: "author_name", label: "작성자", width: "9rem" },
    { key: "view_count", label: "조회", align: "right", width: "6rem" },
    { key: "created_at", label: "작성", align: "right", width: "12rem", render: (p) => fmtDateTime(p.created_at) },
  ];

  const writeBtn = <Button variant="primary" onClick={() => setComposing(true)}>글쓰기</Button>;
  const items = (list.data && list.data.items) || [];
  // 검색·카테고리가 걸려 있을 때의 '결과 없음'과, 게시판 자체가 비어 있는 '첫 글을 써 보세요'는
  // 사용자가 해야 할 일이 정반대다 — 예전엔 둘 다 "아직 게시글이 없습니다"로 뭉개져 있어서,
  // 검색어를 잘못 친 사람에게 "첫 이야기를 남겨 보세요"라고 안내했다.
  const hasFilter = !!(q || category);
  const clearFilters = () => { setQInput(""); setCategory(""); };

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="자유게시판" title="자유게시판" actions={writeBtn} spot="board" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: PROSE_MAX_WIDTH }}>
        팀원과 자유롭게 이야기를 나누는 공간입니다.
      </Typography>

      <Card className="c-toolbar-card" sx={{ p: 2, mb: 2.5 }}>
        <Box sx={{
          display: "grid", gap: 1.5, alignItems: "center",
          gridTemplateColumns: { xs: "1fr", lg: "minmax(0,1fr) auto" },
        }}>
          <Box role="group" aria-label="카테고리" sx={{ display: "flex", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
            <Chip
              component="button" type="button" clickable label="전체"
              aria-pressed={category === ""}
              color={category === "" ? "primary" : "default"}
              variant={category === "" ? "filled" : "outlined"}
              onClick={() => setCategory("")}
            />
            {categories.map((c) => (
              <Chip
                key={c}
                component="button" type="button" clickable label={c}
                aria-pressed={category === c}
                color={category === c ? "primary" : "default"}
                variant={category === c ? "filled" : "outlined"}
                onClick={() => setCategory(c)}
              />
            ))}
          </Box>
          <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", sm: "minmax(12rem,1fr) 9rem" } }}>
            <TextField
              type="search"
              size="small"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="제목, 내용, 작성자 검색"
              inputProps={{ "aria-label": "검색" }}
              InputProps={{ startAdornment: <InputAdornment position="start"><SearchRoundedIcon fontSize="small" /></InputAdornment> }}
            />
            <TextField
              select size="small" value={sort}
              onChange={(e) => setSort(e.target.value)}
              inputProps={{ "aria-label": "정렬" }}
            >
              {SORTS.map(([v, label]) => <MenuItem key={v} value={v}>{label}</MenuItem>)}
            </TextField>
          </Box>
        </Box>
      </Card>

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
            title="아직 게시글이 없습니다"
            help="위 ‘글쓰기’로 팀원과 나누고 싶은 첫 이야기를 남겨 보세요."
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
            onRow={(p) => nav("/board/" + p.id)}
          />
        </Card>
      )}

      <PostFormModal
        open={composing}
        onClose={() => setComposing(false)}
        categories={categories}
        mode="create"
        onSaved={(post) => { setComposing(false); nav("/board/" + post.id); }}
      />
    </div>
  );
}
