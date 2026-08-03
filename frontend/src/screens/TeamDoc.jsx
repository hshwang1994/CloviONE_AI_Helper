import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
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
import { docTypeKind } from "../lib/badges.js";

/* 팀 공간 > 문서 상세 (§17). 메타는 캐시에서, 본문 블록은 실시간(Notion). 본문을 못 불러와도
 * 메타·원본 링크는 보여준다(장애 격리). 모든 텍스트는 {값}으로만 렌더(React 자동 이스케이프 —
 * 문서 안의 프롬프트처럼 보이는 문장도 그저 텍스트다, §11.3/§17.2).
 *
 * 2026-08 MUI 재설계: 본문은 산문이라 줄 길이를 PROSE_MAX_WIDTH(78ch)로 묶고, 4K에서 남는 폭은
 * 줄이 아니라 **두 번째 열**(메타 레일)로 보낸다. DocBody/safeExternal은 티켓 상세도 함께 쓰므로
 * export 이름과 prop 시그니처를 그대로 유지한다. */

export function safeExternal(url) {
  // 원본/출처 링크는 http(s)만 새 탭으로 연다(javascript: 등 차단).
  if (typeof url !== "string") return null;
  if (/^https?:\/\//i.test(url)) return url;
  return null;
}

function DocBlock({ block }) {
  const t = block.text || "";
  switch (block.kind) {
    case "heading_1":
      return <Typography variant="h5" component="h2" sx={{ mt: 4, mb: 1 }}>{t}</Typography>;
    case "heading_2":
      return <Typography variant="h6" component="h3" sx={{ mt: 3, mb: 1 }}>{t}</Typography>;
    case "heading_3":
      return <Typography component="h4" sx={{ mt: 2.5, mb: 0.5, fontWeight: 720, fontSize: "1rem" }}>{t}</Typography>;
    case "bulleted":
    case "numbered":
      return <Box component="li" sx={{ mb: 0.5 }}>{t}</Box>;
    case "todo":
      return (
        <Typography component="div" sx={{ my: 0.5 }}>
          <Box component="span" aria-hidden="true" sx={{ mr: 1 }}>{block.checked ? "☑" : "☐"}</Box>{t}
        </Typography>
      );
    case "quote":
      return (
        <Box component="blockquote" sx={{
          my: 2, ml: 0, pl: 2, borderLeft: 3, borderColor: "primary.light",
          color: "text.secondary", fontStyle: "italic",
        }}>{t}</Box>
      );
    case "callout":
      return (
        <Box sx={{
          my: 2, p: 2, borderRadius: 2, border: 1, borderColor: "divider",
          bgcolor: "action.hover",
        }}>{t}</Box>
      );
    case "toggle":
      return <Typography component="div" sx={{ my: 1, fontWeight: 600 }}>{t}</Typography>;
    case "code":
      // 긴 한 줄이 페이지 전체 가로 스크롤을 만들지 않게 코드 상자 안에서만 스크롤한다.
      return (
        <Box component="pre" sx={{
          my: 2, p: 2, borderRadius: 2, border: 1, borderColor: "divider", bgcolor: "action.hover",
          overflowX: "auto", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: "0.8125rem", lineHeight: 1.6,
        }}>{t}</Box>
      );
    case "divider":
      return <Divider sx={{ my: 3 }} />;
    case "unsupported":
      return <Typography variant="body2" color="text.secondary" sx={{ my: 1 }}>{t}</Typography>;
    default:
      return t ? <Typography component="p" sx={{ my: 1.5, lineHeight: 1.75 }}>{t}</Typography> : null;
  }
}

export function DocBody({ blocks, blocksError, originalUrl }) {
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
    out.push(<Box component={Tag} key={"list-" + out.length} sx={{ my: 1.5, pl: 3 }}>{run.items}</Box>);
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
  // 산문 줄 길이 상한 — 3,000px짜리 한 줄은 눈이 다음 줄 첫 글자를 찾지 못한다.
  return <Box sx={{ maxWidth: PROSE_MAX_WIDTH, overflowWrap: "anywhere" }}>{out}</Box>;
}

/* 문서 메타 레일. 넓은 화면에서는 본문 옆 열, 좁은 화면에서는 본문 위로 흐른다. */
function DocMeta({ doc }) {
  const rows = [];
  if (doc.work_field) rows.push(["업무 분야", doc.work_field]);
  if (doc.tech_tags && doc.tech_tags.length) rows.push(["기술 태그", doc.tech_tags.join(", ")]);
  if (doc.projects && doc.projects.length) rows.push(["프로젝트", doc.projects.join(", ")]);
  if ((doc.author_names || []).length) rows.push(["작성자", doc.author_names.join(", ")]);
  if (doc.owner) rows.push(["소유자", doc.owner]);
  if (doc.priority) rows.push(["우선순위", doc.priority]);
  if (doc.doc_date) rows.push(["날짜", doc.doc_date]);
  if (doc.last_edited) rows.push(["수정", fmtDateTime(doc.last_edited)]);
  if (doc.has_files) rows.push(["첨부", "원본 문서에 첨부파일이 있습니다(원본에서 확인)."]);
  if (rows.length === 0) return null;
  return (
    <Card sx={{ p: 2.5 }}>
      <Box component="dl" sx={{
        m: 0, display: "grid", columnGap: 3, rowGap: 0,
        gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0,1fr))", lg: "1fr", uhd: "repeat(2, minmax(0,1fr))" },
      }}>
        {rows.map(([label, value]) => (
          <Box key={label} sx={{
            display: "grid", gridTemplateColumns: "6.5rem minmax(0,1fr)", gap: 1,
            py: 1, borderBottom: 1, borderColor: "divider", minWidth: 0,
          }}>
            <Box component="dt" sx={{ color: "text.secondary", fontSize: "0.875rem" }}>{label}</Box>
            <Box component="dd" sx={{ m: 0, minWidth: 0, overflowWrap: "anywhere", fontSize: "0.875rem" }}>{value}</Box>
          </Box>
        ))}
      </Box>
    </Card>
  );
}

export function TeamDoc() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();

  const detail = useQuery({
    queryKey: ["team-doc", id],
    queryFn: () => api("/api/team-docs/" + id),
  });

  const trash = useMutation({
    mutationFn: () => api("/api/team-docs/" + id + "/trash", { method: "POST" }),
    onSuccess: () => {
      toast("문서를 휴지통으로 옮겼습니다.", "success");
      qc.invalidateQueries({ queryKey: ["team-docs"], refetchType: "all" });
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      nav("/team-docs");
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
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
        <Card><Skeleton lines={8} /></Card>
      </div>
    );
  }

  const doc = detail.data.document;
  const original = safeExternal(doc.original_url) || safeExternal(doc.url) || safeExternal(doc.source_url);

  const actions = (
    <>
      <Button variant="ghost" onClick={() => nav("/team-docs")}>목록</Button>
      <Button onClick={() => fav.mutate(!doc.is_favorite)} disabled={fav.isPending}>
        {doc.is_favorite ? "★ 즐겨찾기 해제" : "☆ 즐겨찾기"}
      </Button>
      {original ? (
        <Button variant="primary" onClick={() => window.open(original, "_blank", "noopener,noreferrer")}>
          원본 열기
        </Button>
      ) : null}
      <Button variant="danger" disabled={trash.isPending}
        onClick={async () => {
          const ok = await confirm("이 문서를 휴지통으로 옮깁니다. 보관기간이 지나면 원본이 삭제됩니다. 계속할까요?",
            { title: "문서 삭제", confirmLabel: "휴지통으로", danger: true });
          if (ok) trash.mutate();
        }}>삭제</Button>
    </>
  );

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="" area="문서" title="문서" actions={actions} />

      {/* 1열: 제목 + 본문(78ch 상한). 2열: 메타 레일. lg부터 갈라진다. */}
      <Box sx={{
        display: "grid", alignItems: "start",
        columnGap: { lg: 4, xxl: 6 }, rowGap: 3,
        gridTemplateColumns: { xs: "1fr", lg: `minmax(0, ${PROSE_MAX_WIDTH}) minmax(18rem, 1fr)` },
      }}>
        <Card component="article" sx={{ minWidth: 0 }}>
          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            {doc.status ? <Badge value={doc.status} /> : null}
            {doc.document_type ? <Badge value={doc.document_type} kind={docTypeKind(doc.document_type)} /> : null}
          </Stack>
          <Typography variant="h4" component="h1" sx={{ mt: 1, mb: 3, overflowWrap: "anywhere" }}>
            {doc.title || "제목 없음"}
          </Typography>
          <DocBody blocks={detail.data.blocks} blocksError={detail.data.blocks_error} originalUrl={original} />
        </Card>

        <DocMeta doc={doc} />
      </Box>
    </div>
  );
}
