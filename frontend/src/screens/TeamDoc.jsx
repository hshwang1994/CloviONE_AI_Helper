import React from "react";
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
  useToast,
} from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";
import { docTypeKind } from "../lib/badges.js";

/* 팀 공간 > 문서 상세 (§17). 메타는 캐시에서, 본문 블록은 실시간(Notion). 본문을 못 불러와도
 * 메타·원본 링크는 보여준다(장애 격리). 모든 텍스트는 {값}으로만 렌더(React 자동 이스케이프 —
 * 문서 안의 프롬프트처럼 보이는 문장도 그저 텍스트다, §11.3/§17.2). */

function safeExternal(url) {
  // 원본/출처 링크는 http(s)만 새 탭으로 연다(javascript: 등 차단).
  if (typeof url !== "string") return null;
  if (/^https?:\/\//i.test(url)) return url;
  return null;
}

function DocBlock({ block }) {
  const t = block.text || "";
  switch (block.kind) {
    case "heading_1": return <h2 className="doc-h1">{t}</h2>;
    case "heading_2": return <h3 className="doc-h2">{t}</h3>;
    case "heading_3": return <h4 className="doc-h3">{t}</h4>;
    case "bulleted": return <li className="doc-li">{t}</li>;
    case "numbered": return <li className="doc-li">{t}</li>;
    case "todo": return <div className="doc-todo">{block.checked ? "☑" : "☐"} {t}</div>;
    case "quote": return <blockquote className="doc-quote">{t}</blockquote>;
    case "callout": return <div className="doc-callout">{t}</div>;
    case "toggle": return <div className="doc-toggle">{t}</div>;
    case "code": return <pre className="doc-code">{t}</pre>;
    case "divider": return <hr className="doc-divider" />;
    case "unsupported": return <div className="doc-unsupported">{t}</div>;
    default: return t ? <p className="doc-p">{t}</p> : null;
  }
}

function DocBody({ blocks, blocksError, originalUrl }) {
  if (blocksError) {
    return (
      <Callout tone="warn">
        본문을 불러오지 못했습니다({blocksError}). 원본에서 확인해 주세요.
      </Callout>
    );
  }
  if (!blocks || blocks.length === 0) {
    return <Callout tone="info">본문 내용이 없습니다. 원본 문서를 확인해 주세요.</Callout>;
  }
  // 연속한 목록 항목(bulleted/numbered)을 <ul>/<ol>로 묶는다 — bare <li>는 번호가
  // 문서 전체 카운터를 공유해 잘못 매겨지고 목록 시맨틱(스크린리더)도 잃는다(검수 결함).
  const out = [];
  let run = null;
  const flush = () => {
    if (!run) return;
    const Tag = run.kind === "numbered" ? "ol" : "ul";
    out.push(<Tag key={"list-" + out.length} className="doc-list">{run.items}</Tag>);
    run = null;
  };
  blocks.forEach((b, i) => {
    if (b.kind === "bulleted" || b.kind === "numbered") {
      if (run && run.kind !== b.kind) flush();
      if (!run) run = { kind: b.kind, items: [] };
      run.items.push(<DocBlock key={i} block={b} />);
    } else {
      flush();
      out.push(<DocBlock key={i} block={b} />);
    }
  });
  flush();
  return <div className="doc-body">{out}</div>;
}

export function TeamDoc() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();

  const detail = useQuery({
    queryKey: ["team-doc", id],
    queryFn: () => api("/api/team-docs/" + id),
  });

  const fav = useMutation({
    mutationFn: (on) => api("/api/team-docs/" + id + "/favorite?on=" + (on ? "true" : "false"), { method: "POST" }),
    onSuccess: () => { detail.refetch(); qc.invalidateQueries({ queryKey: ["team-docs"] }); },
    onError: (e) => toast((e && e.message) || "즐겨찾기를 바꾸지 못했습니다.", "error"),
  });

  if (detail.isError) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="" area="문서" title="문서" />
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      </div>
    );
  }
  if (detail.isPending) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="" area="문서" title="문서" />
        <Skeleton lines={8} />
      </div>
    );
  }

  const doc = detail.data.document;
  const original = safeExternal(doc.original_url) || safeExternal(doc.url) || safeExternal(doc.source_url);

  const actions = (
    <div className="doc-actions">
      <Button variant="ghost" onClick={() => nav("/team-docs")}>목록</Button>
      <Button onClick={() => fav.mutate(!doc.is_favorite)} disabled={fav.isPending}>
        {doc.is_favorite ? "★ 즐겨찾기 해제" : "☆ 즐겨찾기"}
      </Button>
      {original ? (
        <Button variant="primary" onClick={() => window.open(original, "_blank", "noopener,noreferrer")}>
          원본 열기
        </Button>
      ) : null}
    </div>
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="" area="문서" title="문서" actions={actions} />

      <article className="doc-detail">
        <div className="doc-head">
          {doc.status ? <Badge value={doc.status} /> : null}
          {doc.document_type ? <Badge value={doc.document_type} kind={docTypeKind(doc.document_type)} /> : null}
          <h1 className="doc-title">{doc.title || "제목 없음"}</h1>
        </div>

        <dl className="doc-meta">
          {doc.work_field ? <><dt>업무 분야</dt><dd>{doc.work_field}</dd></> : null}
          {doc.tech_tags && doc.tech_tags.length ? <><dt>기술 태그</dt><dd>{doc.tech_tags.join(", ")}</dd></> : null}
          {doc.projects && doc.projects.length ? <><dt>프로젝트</dt><dd>{doc.projects.join(", ")}</dd></> : null}
          {(doc.author_names || []).length ? <><dt>작성자</dt><dd>{doc.author_names.join(", ")}</dd></> : null}
          {doc.owner ? <><dt>소유자</dt><dd>{doc.owner}</dd></> : null}
          {doc.priority ? <><dt>우선순위</dt><dd>{doc.priority}</dd></> : null}
          {doc.doc_date ? <><dt>날짜</dt><dd>{doc.doc_date}</dd></> : null}
          {doc.last_edited ? <><dt>수정</dt><dd>{fmtDateTime(doc.last_edited)}</dd></> : null}
          {doc.has_files ? <><dt>첨부</dt><dd>원본 문서에 첨부파일이 있습니다(원본에서 확인).</dd></> : null}
        </dl>

        <DocBody blocks={detail.data.blocks} blocksError={detail.data.blocks_error} originalUrl={original} />
      </article>
    </div>
  );
}
