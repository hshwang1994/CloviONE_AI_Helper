import React from "react";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Typography from "@mui/material/Typography";
import { Callout } from "./kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, PROSE_MAX_WIDTH } from "./theme.js";
import { BASELINE_TRACKS, GRID_GAP } from "./density.js";
import { ClickableImage, ImageLightbox, useLightbox } from "./ImageLightbox.jsx";
import { linkifyText } from "../screens/chat/links.jsx";

/* 저장된 본문 블록을 화면에 푸는 renderer.
 *
 * 옛 문서 상세 화면(`screens/TeamDoc.jsx`) 안에 있었다. 그 화면은 정본 문서 화면
 * (`/knowledge`)으로 합쳐지면서 없어졌는데(S14 · C2), 이 renderer 는 **티켓 상세도 함께
 * 쓴다**(`screens/TicketBody.jsx`). 화면 하나에 딸린 물건이 아니라 두 화면이 공유하는
 * 부품이므로 여기로 옮긴다 — 화면 모듈에 두면 그 화면이 사라지는 날 같이 사라진다.
 *
 * 모든 텍스트는 {값}으로만 그린다(React 자동 이스케이프) — 문서 안의 프롬프트처럼 보이는
 * 문장도 그저 텍스트다.
 */

/* 문서 상세의 두 열(본문 + 메타 레일). 기준선 `.ticket-layout` 과 같은 자리라 티켓 상세와
 * **같은 값**을 쓴다 — 성격이 같은 두 화면이 서로 다른 폭이면 같은 앱으로 안 보인다.
 * 왜 트랙에 `fr` 이 필요한지는 `Ticket.jsx` 의 DETAIL_GRID 주석에 적어 뒀다(같은 증상이었다). */
export const DOC_DETAIL_GRID = {
  display: "grid", alignItems: "start", gap: GRID_GAP,
  gridTemplateColumns: { xs: "1fr", lg: BASELINE_TRACKS.detail },
};

function DocBlock({ block, index, onImage }) {
  const t = block.text || "";
  // 본문 안 URL이 평문이라 클릭할 수 없었다(user_team-doc-detail 재확인) — 팀 채팅
  // 말풍선(chat/RichText.jsx)이 이미 쓰는 linkifyText를 그대로 재사용한다(전부 복사 버튼,
  // 텍스트 노드만 쓴다, innerHTML 아님). code는 원문 그대로 둔다(RichText.jsx의 같은 판단과
  // 동일 — 코드 안 문자열을 링크로 오인하면 안 됨).
  const lt = linkifyText(t, "b" + index);
  switch (block.kind) {
    case "image":
      /* 사용자 지시 §4 — 티켓·문서에 붙은 이미지를 화면에서 바로 보고, 눌러서 크게 본다.
         예전에는 이미지 블록이 "[image] 원본에서 확인"이라는 회색 글씨로만 나왔다. */
      return (
        <Box sx={{ my: 2 }}>
          <ClickableImage src={block.url} alt={t || "본문 이미지"} onOpen={() => onImage && onImage(block)}
            sx={{ border: 1, borderColor: "divider" }} />
          {t ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>{lt}</Typography>
          ) : null}
        </Box>
      );
    case "heading_1":
      return <Typography variant="h5" component="h2" sx={{ mt: 4, mb: 1 }}>{lt}</Typography>;
    case "heading_2":
      return <Typography variant="h6" component="h3" sx={{ mt: 3, mb: 1 }}>{lt}</Typography>;
    case "heading_3":
      return <Typography component="h4" sx={{ mt: 2.5, mb: 0.5, fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.sectionTitle }}>{lt}</Typography>;
    case "bulleted":
    case "numbered":
      return <Box component="li" sx={{ mb: 0.5 }}>{lt}</Box>;
    case "todo":
      return (
        <Typography component="div" sx={{ my: 0.5 }}>
          <Box component="span" aria-hidden="true" sx={{ mr: 1 }}>{block.checked ? "☑" : "☐"}</Box>{lt}
        </Typography>
      );
    case "quote":
      return (
        <Box component="blockquote" sx={{
          my: 2, ml: 0, pl: 2, borderLeft: 3, borderColor: "primary.light",
          color: "text.secondary", fontStyle: "italic",
        }}>{lt}</Box>
      );
    case "callout":
      return (
        <Box sx={{
          my: 2, p: 2, borderRadius: 2, border: 1, borderColor: "divider",
          bgcolor: "action.hover",
        }}>{lt}</Box>
      );
    case "toggle":
      return <Typography component="div" sx={{ my: 1, fontWeight: FONT_WEIGHT.semibold }}>{lt}</Typography>;
    case "code":
      // 긴 한 줄이 페이지 전체 가로 스크롤을 만들지 않게 코드 상자 안에서만 스크롤한다.
      return (
        <Box component="pre" sx={{
          my: 2, p: 2, borderRadius: 2, border: 1, borderColor: "divider", bgcolor: "action.hover",
          overflowX: "auto", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: FONT_SIZE.bodySm, lineHeight: 1.6,
        }}>{t}</Box>
      );
    case "divider":
      return <Divider sx={{ my: 3 }} />;
    case "unsupported":
      return <Typography variant="body2" color="text.secondary" sx={{ my: 1 }}>{t}</Typography>;
    default:
      return t ? <Typography component="p" sx={{ my: 1.5, lineHeight: 1.75 }}>{lt}</Typography> : null;
  }
}

export function DocBody({ blocks, blocksError }) {
  // 훅은 조기 return 보다 먼저 부른다(Rules of Hooks) — 아래에 오류·빈 본문 분기가 있다.
  const lb = useLightbox();
  if (blocksError) {
    return (
      <Callout tone="danger">
        본문을 불러오지 못했습니다({blocksError}). 잠시 후 새로고침해 주세요.
      </Callout>
    );
  }
  if (!blocks || blocks.length === 0) {
    /* 빈 상태는 안내가 아니다 - `안내` 라벨을 붙이면 읽을 것이 없다는 사실보다 라벨이 먼저
       읽힌다. 평문으로 둔다. */
    return <Typography color="text.secondary">본문 내용이 없습니다.</Typography>;
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
      run.items.push(<DocBlock key={i} index={i} block={b} />);
    } else {
      flush();
      out.push(<DocBlock key={i} index={i} block={b} onImage={openImage} />);
    }
  });
  flush();
  // 산문 줄 길이 상한 — 3,000px짜리 한 줄은 눈이 다음 줄 첫 글자를 찾지 못한다.
  return (
    <Box sx={{ maxWidth: PROSE_MAX_WIDTH, ...KO_WORD_BREAK }}>
      {out}
      <ImageLightbox {...lb.props} />
    </Box>
  );
}
