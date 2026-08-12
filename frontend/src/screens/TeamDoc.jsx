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
import { BASELINE_TRACKS, GRID_GAP } from "../ui/density.js";
import { docTypeKind } from "../lib/badges.js";
import { safeExternal } from "../lib/safeUrl.js";
import { ClickableImage, ImageLightbox, useLightbox } from "../ui/ImageLightbox.jsx";
import { EditableBody } from "../ui/EditableBody.jsx";
import { DocComments } from "./DocComments.jsx";
import { invalidateDocumentViews } from "./document-views.js";

/* 팀 공간 > 문서 상세 (§17). 메타는 캐시에서, 본문 블록은 실시간(Notion). 본문을 못 불러와도
 * 메타·원본 링크는 보여준다(장애 격리). 모든 텍스트는 {값}으로만 렌더(React 자동 이스케이프 —
 * 문서 안의 프롬프트처럼 보이는 문장도 그저 텍스트다, §11.3/§17.2).
 *
 * 2026-08 MUI 재설계: 폭은 두 층이다. **열 폭**은 기준선 `.ticket-layout`(DOC_DETAIL_GRID)이
 * 정하고 화면을 꽉 채우며, **글줄 길이**만 그 안에서 PROSE_MAX_WIDTH(78ch)가 잡는다.
 * 예전에는 격자 트랙을 78ch 로 못 박아 열이 폭을 다 못 쓰고 오른쪽이 비었다(티켓 상세와 같은 증상).
 * DocBody/safeExternal은 티켓 상세도 함께 쓰므로 export 이름과 prop 시그니처를 그대로 유지한다. */

// 정의는 `lib/safeUrl.js` 로 옮겼다 — 보안 원시함수가 화면 모듈에 있으니 다른 화면에서
// 아무도 찾아 쓰지 않았고, 실제로 배너·휴지통·개발리포트 세 곳이 무방비였다.
// 여기서 재수출하는 이유는 `Ticket.jsx` 와 `teamdoc.test.jsx` 가 이 경로로 가져오기 때문이다.
export { safeExternal };

/* 문서 상세의 두 열(본문 + 메타 레일). 기준선 `.ticket-layout` 과 같은 자리라 티켓 상세와
 * **같은 값**을 쓴다 — 성격이 같은 두 화면이 서로 다른 폭이면 같은 앱으로 안 보인다.
 * 왜 트랙에 `fr` 이 필요한지는 `Ticket.jsx` 의 DETAIL_GRID 주석에 적어 뒀다(같은 증상이었다). */
export const DOC_DETAIL_GRID = {
  display: "grid", alignItems: "start", gap: GRID_GAP,
  gridTemplateColumns: { xs: "1fr", lg: BASELINE_TRACKS.detail },
};

function DocBlock({ block, onImage }) {
  const t = block.text || "";
  switch (block.kind) {
    case "image":
      /* 사용자 지시 §4 — 티켓·문서에 붙은 이미지를 화면에서 바로 보고, 눌러서 크게 본다.
         예전에는 이미지 블록이 "[image] 원본에서 확인"이라는 회색 글씨로만 나왔다. */
      return (
        <Box sx={{ my: 2 }}>
          <ClickableImage src={block.url} alt={t || "본문 이미지"} onOpen={() => onImage && onImage(block)}
            sx={{ border: 1, borderColor: "divider" }} />
          {t ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>{t}</Typography>
          ) : null}
        </Box>
      );
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
  // 훅은 조기 return 보다 먼저 부른다(Rules of Hooks) — 아래에 오류·빈 본문 분기가 있다.
  const lb = useLightbox();
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
  // 본문 안의 이미지 전부를 한 벌로 모아 두면 확대 보기에서 좌우로 넘길 수 있다 —
  // 한 장씩 열고 닫는 것보다 여러 장 붙은 티켓에서 훨씬 빠르다.
  const shots = blocks.filter((b) => b && b.kind === "image" && b.url);
  const openImage = (block) => {
    const at = shots.findIndex((s) => s === block);
    lb.open(shots.map((s) => ({ src: s.url, title: s.text || undefined })), at < 0 ? 0 : at);
  };
  blocks.forEach((b, i) => {
    if (b.kind === "bulleted" || b.kind === "numbered") {
      if (run && run.kind !== b.kind) flush();
      if (!run) run = { kind: b.kind, items: [] };
      run.items.push(<DocBlock key={i} block={b} />);
    } else {
      flush();
      out.push(<DocBlock key={i} block={b} onImage={openImage} />);
    }
  });
  flush();
  // 산문 줄 길이 상한 — 3,000px짜리 한 줄은 눈이 다음 줄 첫 글자를 찾지 못한다.
  return (
    <Box sx={{ maxWidth: PROSE_MAX_WIDTH, overflowWrap: "anywhere" }}>
      {out}
      <ImageLightbox {...lb.props} />
    </Box>
  );
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
      // ["team-doc"] 접두어가 이 상세 자신의 캐시(id 포함)도 함께 잡는다 — 목록으로 이동은
      // 하지만, 사용자가 브라우저 뒤로가기로 이 상세에 돌아오면 staleTime(30초) 동안 방금
      // 지운 문서가 그대로 보였다(TeamDocs.jsx 선택 삭제와 같은 이유). home의 「최근 문서」도
      // 함께 무효화(L축 재감사).
      invalidateDocumentViews(qc, { refetchType: "all" });
      nav("/team-docs");
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
  });

  const fav = useMutation({
    mutationFn: (on) => api("/api/team-docs/" + id + "/favorite?on=" + (on ? "true" : "false"), { method: "POST" }),
    onSuccess: () => { detail.refetch(); qc.invalidateQueries({ queryKey: ["team-docs"] }); },
    onError: (e) => toast((e && e.message) || "즐겨찾기를 바꾸지 못했습니다.", "error"),
  });

  // 문서 열람 제한 토글(SEC-10) — 운영자만 보인다(doc.can_restrict). 켜면 이후로는 운영자군·
  // 작성자 본인 외에는 이 문서가 목록·상세 어디에도 안 보인다(app/team_docs/service.py
  // doc_in_scope). 목록도 함께 무효화한다 — 안 하면 방금 제한한 문서가 목록에 그대로 남는다.
  const restrict = useMutation({
    mutationFn: (on) => api("/api/team-docs/" + id + "/restrict?on=" + (on ? "true" : "false"), { method: "POST" }),
    onSuccess: () => {
      detail.refetch();
      // 제한을 켜면 이 문서가 home의 「최근 문서」에서도 사라져야 한다(L축 재감사).
      invalidateDocumentViews(qc);
    },
    onError: (e) => toast((e && e.message) || "열람 제한을 바꾸지 못했습니다.", "error"),
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
      {doc.can_restrict ? (
        <Button
          variant={doc.restricted ? "danger" : "default"}
          disabled={restrict.isPending}
          onClick={async () => {
            const next = !doc.restricted;
            const ok = await confirm(
              next
                ? "이 문서를 열람 제한합니다. 이후로는 운영자와 작성자 본인만 볼 수 있고, 그 외에는 목록에서도 사라집니다. 원본 Notion 콘텐츠는 바뀌지 않습니다."
                : "이 문서의 열람 제한을 해제합니다. 범위 안(부서 등)의 모든 사용자가 다시 볼 수 있습니다.",
              { title: next ? "문서 열람 제한" : "열람 제한 해제", danger: next, confirmLabel: next ? "제한" : "해제" },
            );
            if (ok) restrict.mutate(next);
          }}
        >
          {doc.restricted ? "🔒 제한 해제" : "열람 제한"}
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
      {/* SEM-03 재확인(2026-08-13) — 2026-08-12 "구현완료" 기록은 grep -c 'component="h1"'로
          이 파일 자체의 리터럴만 셌다(1개, 아래 문서 제목 하나) — PageHeader가 kit.jsx 안에서
          내부적으로 만드는 h1("문서")은 다른 파일 소스라 그 grep에 안 걸려, 실제로는 h1이
          둘이었던 것을 놓쳤다(실제 렌더 검사로 재확인). PageHeader에 진짜 제목을 넘기고
          아래 중복 Typography는 없앤다(같은 글자를 화면 맨 위와 카드 맨 위에서 두 번 읽지
          않게). */}
      <PageHeader crumbRoot="" area="문서" title={doc.title || "제목 없음"} actions={actions} />

      {/* 1열: 제목 + 본문. 2열: 메타 + 댓글 레일. lg부터 갈라진다.
          사용자 지시: "댓글 기능은 본문이 아니라 오른쪽에 배치." 두 Box 모두 order를
          두지 않는다 — xs(한 열)에서는 DOM 순서 그대로 본문 → 메타 → 댓글로 쌓이고,
          lg+(두 열)에서는 첫 자식이 1열, 둘째 자식이 2열에 자동으로 놓인다(티켓 상세와
          같은 방식, Ticket.jsx의 DETAIL_GRID 주석 참고). 예전에는 댓글을 격자의 세 번째
          자식으로 그냥 붙였는데, 그러면 2열 격자의 자동 배치가 댓글을 1열(본문 쪽) 다음
          행에 놓아 "댓글이 본문 열에 있다"는 사용자 지적의 원인이 됐다. */}
      <Box sx={DOC_DETAIL_GRID}>
        <Box data-testid="doc-detail-main" sx={{ minWidth: 0, display: "grid", gap: 2.5, alignContent: "start" }}>
          <Card component="article" sx={{ minWidth: 0 }}>
            <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center" sx={{ mb: 2 }}>
              {doc.status ? <Badge value={doc.status} /> : null}
              {doc.document_type ? <Badge value={doc.document_type} kind={docTypeKind(doc.document_type)} /> : null}
              {doc.restricted ? <Badge value="🔒 열람 제한" kind="warn" /> : null}
            </Stack>
            {doc.restricted ? (
              <Box sx={{ mb: 2.5 }}>
                <Callout tone="warn">
                  이 문서는 열람이 제한되어 있습니다. 운영자와 작성자 본인만 볼 수 있고, 다른
                  사용자에게는 목록에서도 보이지 않습니다.
                </Callout>
              </Box>
            ) : null}
            {/* 읽기와 편집을 한 패널이 맡는다(사용자 지적 #9). 티켓 본문과 **같은 컴포넌트**라
                "저장은 됐지만 원본과 어긋남" 같은 상태를 두 화면이 똑같이 다룬다.
                소스 본문 렌더러는 여기서 넘긴다 — 폭 상한은 화면이 정할 일이고, 그래야
                ui/EditableBody 가 화면 모듈을 되짚어 import 하지 않는다(순환 import). */}
            <EditableBody
              editorId={"doc-body-" + id}
              endpoint={"/api/team-docs/" + id + "/body"}
              invalidateKeys={[["team-docs"], ["team-doc", id]]}
              blocks={detail.data.blocks}
              bodyMarkdown={detail.data.body_markdown}
              bodyVersion={detail.data.body_version}
              bodyIsLocal={detail.data.body_is_local}
              bodySyncError={detail.data.body_sync_error}
              onSaved={() => detail.refetch()}
              sourceView={(
                <DocBody blocks={detail.data.blocks} blocksError={detail.data.blocks_error}
                  originalUrl={original} />
              )}
            />
          </Card>
        </Box>

        <Box data-testid="doc-detail-rail" sx={{ minWidth: 0, display: "grid", gap: 2.5, alignContent: "start" }}>
          <DocMeta doc={doc} />
          <DocComments pageId={id} />
        </Box>
      </Box>
    </div>
  );
}
