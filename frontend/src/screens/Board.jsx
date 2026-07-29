import React, { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api.js";
import {
  Badge,
  Button,
  Callout,
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
import { boardCategoryKind } from "../lib/badges.js";
import { buildPostsQuery, reactionMap } from "./board-helpers.js";

/* 자유게시판 목록 (팀 공간 §18). 순수 내부 기능 — 외부 호출 없음. 카테고리 필터·검색·정렬은
 * 페이지 안에서 처리하고, 글쓰기는 이 페이지의 버튼(모달)이다. 행을 누르면 상세로 이동한다.
 * 본문/제목은 React가 기본으로 textContent로 렌더하므로 XSS 없음(불변 §6). */

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
      <div className="k-field">
        <label className="k-field-label" htmlFor="board-cat">카테고리</label>
        <select
          id="board-cat"
          className="k-input"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          {(categories || []).map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>
      <div className="k-field">
        <label className="k-field-label" htmlFor="board-title">
          제목<span className="k-req"> *</span>
        </label>
        <input
          id="board-title"
          className="k-input"
          maxLength={200}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="k-field">
        <label className="k-field-label" htmlFor="board-body">내용</label>
        <textarea
          id="board-body"
          className="k-input"
          rows={8}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
      </div>
      <div className="k-field">
        <label className="k-field-label" htmlFor="board-files">
          첨부 (이미지 또는 PDF, 최대 {MAX_FILES}개, 각 10MB)
        </label>
        <input
          id="board-files"
          className="k-input"
          type="file"
          multiple
          accept={UPLOAD_ACCEPT}
          onChange={(e) => {
            const picked = Array.from(e.target.files || []);
            const tooBig = picked.filter((f) => f.size > MAX_FILE_BYTES).map((f) => f.name);
            let ok = picked.filter((f) => f.size <= MAX_FILE_BYTES);
            if (ok.length > MAX_FILES) ok = ok.slice(0, MAX_FILES);
            if (tooBig.length) toast("10MB를 넘어 제외했습니다: " + tooBig.join(", "), "error");
            setFiles(ok);
          }}
        />
        {files.length > 0 ? (
          <p className="board-file-names">{files.map((f) => f.name).join(", ")}</p>
        ) : null}
      </div>
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
    <div className="board-reactions">
      {(palette || []).map((emoji) => {
        const r = byEmoji[emoji];
        const mine = r && r.mine;
        const count = r ? r.count : 0;
        return (
          <button
            key={emoji}
            type="button"
            className={"board-react" + (mine ? " is-mine" : "")}
            disabled={toggle.isPending}
            onClick={() => toggle.mutate(emoji)}
            aria-pressed={mine ? true : false}
          >
            <span className="board-react-emoji">{emoji}</span>
            {count > 0 ? <span className="board-react-count">{count}</span> : null}
          </button>
        );
      })}
    </div>
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

  const columns = [
    {
      key: "title",
      label: "제목",
      render: (p) => (
        <span className="board-title-cell">
          {p.is_pinned ? <Badge value="고정" kind="info" /> : null}
          <span className="board-title-text">{p.title}</span>
          {p.comment_count > 0 ? <span className="board-cc">[{p.comment_count}]</span> : null}
        </span>
      ),
    },
    { key: "category", label: "카테고리", render: (p) => <Badge value={p.category} kind={boardCategoryKind(p.category)} /> },
    { key: "author_name", label: "작성자" },
    { key: "view_count", label: "조회", align: "right" },
    { key: "created_at", label: "작성", align: "right", render: (p) => fmtDateTime(p.created_at) },
  ];

  const actions = (
    <Button variant="primary" onClick={() => setComposing(true)}>글쓰기</Button>
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="팀 공간" area="자유게시판" title="자유게시판" actions={actions} />
      <p className="k-page-help">팀원과 자유롭게 이야기를 나누는 공간입니다.</p>

      <div className="board-filters">
        <div className="board-cats" role="group" aria-label="카테고리">
          <button
            type="button"
            className={"board-cat-chip" + (category === "" ? " is-on" : "")}
            onClick={() => setCategory("")}
          >전체</button>
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              className={"board-cat-chip" + (category === c ? " is-on" : "")}
              onClick={() => setCategory(c)}
            >{c}</button>
          ))}
        </div>
        <div className="board-tools">
          <input
            className="k-input board-search"
            type="search"
            placeholder="제목, 내용, 작성자 검색"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            aria-label="검색"
          />
          <select
            className="k-input board-sort"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            aria-label="정렬"
          >
            {SORTS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </div>
      </div>

      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : list.isPending ? (
        <Skeleton lines={6} />
      ) : (list.data.items || []).length === 0 ? (
        <EmptyState
          title="아직 게시글이 없습니다"
          help="위 ‘글쓰기’로 팀원과 나누고 싶은 첫 이야기를 남겨 보세요."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={list.data.items}
          rowKey={(p) => p.id}
          onRow={(p) => nav("/board/" + p.id)}
        />
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
