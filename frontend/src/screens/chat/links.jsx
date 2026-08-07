import React from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Tooltip from "@mui/material/Tooltip";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";
import { useToast } from "../../ui/kit.jsx";
import { URL_RE, copyText, safeNotion } from "../chat-helpers.js";

/* 본문·카드 안 URL을 안전하게 그리는 두 부품 — 허용 도메인은 실제 링크로, 그 외는 복사 버튼으로.
 * TicketCard/CardStack, RichText(말풍선 프로즈)가 모두 이 게이트를 공유한다(같은 판정을 두 번
 * 정의하면 언젠가 한쪽만 고쳐진다). */

// allowlist에 걸려 링크로 열 수 없는 외부 URL, 죽은 텍스트처럼 보이지 않도록 클릭하면 주소를
// 복사하는 버튼으로 렌더한다(TicketCard, 관련 문서 폴백에서 공유).
export function PlainUrl({ url }) {
  const toast = useToast();
  return (
    <Tooltip title="외부 링크는 열 수 없습니다, 눌러서 주소를 복사합니다.">
      <Box
        component="button"
        type="button"
        onClick={() => copyText(url).then((ok) => toast(ok ? "주소를 복사했습니다." : "복사에 실패했습니다.", ok ? "success" : "error"))}
        sx={{
          font: "inherit", fontSize: "0.8125rem", border: 0, background: "none", p: 0, m: 0,
          textAlign: "left", cursor: "pointer", color: "text.secondary", overflowWrap: "anywhere",
          textDecoration: "underline dotted", textUnderlineOffset: "2px",
          "&:hover, &:focus-visible": { color: "text.primary", textDecorationStyle: "solid" },
        }}
      >
        {url}
      </Box>
    </Tooltip>
  );
}

// Notion 허용 도메인 링크 — 새 탭 고지는 시각(↗)과 낭독(sr-only) 둘 다로 준다.
export function NotionLink({ url, children }) {
  return (
    <Link
      href={url} target="_blank" rel="noreferrer noopener" underline="hover"
      sx={{ fontSize: "0.8125rem", fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 0.5, overflowWrap: "anywhere" }}
    >
      {children || "Notion에서 열기"}
      <OpenInNewRoundedIcon aria-hidden="true" sx={{ fontSize: "0.9375rem" }} />
      <span className="sr-only"> (새 탭에서 열림)</span>
    </Link>
  );
}

// 답변 프로즈 안에 맨 http(s):// URL이 섞여 있으면(구조화된 notion_url/ticket.url 필드가 아니라
// 그냥 문장 중간의 참조 링크) 이전엔 죽은 평문으로만 보였다, 구조화 필드와 같은 safeNotion 게이트로
// 링크(허용 도메인)/PlainUrl(그 외, 복사 폴백) 처리한다. 텍스트 노드만 쓴다(innerHTML 아님, CLAUDE.md §2).
export function linkifyText(text, keyBase) {
  const s = String(text == null ? "" : text);
  const parts = s.split(URL_RE);
  if (parts.length === 1) return s;
  return parts.map((part, i) => (i % 2 === 1)
    ? (safeNotion(part)
        ? <NotionLink key={keyBase + "-u" + i} url={part}>{part}</NotionLink>
        : <PlainUrl key={keyBase + "-u" + i} url={part} />)
    : part);
}
