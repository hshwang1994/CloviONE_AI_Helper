import React from "react";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import ConfirmationNumberOutlinedIcon from "@mui/icons-material/ConfirmationNumberOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import { Button } from "../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, ICON, KO_WORD_BREAK, remPx } from "../../ui/theme.js";

/* 「참고한 자료」 — 도우미가 도구로 확인한 티켓 · 문서 · 프로젝트 · 결재 · 게시글 (D-535 · D-538).
 *
 * 목록은 서버가 만든다(`structured.sources`, 경로가 있는 항목만 열두 개까지). 화면은 그 경로가 **앱 안 경로**일 때만 링크로
 * 그린다 — 허용한 다섯 갈래 밖의 값, 바깥 주소, `//` 로 시작하는 값은 버린다. 그림(`<img>`)은 그리지 않는다. 사람은 출처가
 * 아니다(서버가 싣지 않는다). */

export const SOURCE_ROUTE_PREFIXES = ["/knowledge/", "/tickets/", "/projects/", "/my-approvals", "/board/"];

const KINDS = {
  document: { label: "문서", Icon: DescriptionOutlinedIcon },
  ticket: { label: "티켓", Icon: ConfirmationNumberOutlinedIcon },
  project: { label: "프로젝트", Icon: FolderOutlinedIcon },
  approval: { label: "결재", Icon: FactCheckOutlinedIcon },
  board: { label: "게시글", Icon: ForumOutlinedIcon },
};

export function safeSourceRoute(route) {
  if (typeof route !== "string" || !route.startsWith("/") || route.startsWith("//")) return null;
  return SOURCE_ROUTE_PREFIXES.some((prefix) => route.startsWith(prefix)) ? route : null;
}

/* 옛 답(근거 검색 시절)의 `citations` 를 문서 출처로 옮긴다 — 지난 대화를 열어도 출처가 사라지지 않는다. */
export function messageSources(structured) {
  const st = structured || {};
  if (Array.isArray(st.sources)) return st.sources;
  if (Array.isArray(st.citations)) {
    const seen = new Set();
    return st.citations
      .filter((c) => c && c.document_id && !seen.has(c.document_id) && seen.add(c.document_id))
      .map((c) => ({ type: "document", id: c.document_id, title: c.document_title, route: c.route, where: c.where }));
  }
  return [];
}

function metaOf(source) {
  return [source.key, source.status, source.where].filter((v) => typeof v === "string" && v.trim());
}

export function SourceList({ sources, title = "참고한 자료", limit = 8 }) {
  const [showAll, setShowAll] = React.useState(false);
  const items = (Array.isArray(sources) ? sources : []).filter((s) => s && KINDS[s.type] && safeSourceRoute(s.route));
  if (!items.length) return null;
  const shown = showAll ? items : items.slice(0, limit);
  return (
    <Box component="section" aria-label={title || "참고한 자료"} sx={{ display: "grid", gap: 0.75, minWidth: 0 }}>
      {/* 머리글은 담는 쪽이 이미 같은 이름을 세웠으면(오른쪽 레일) 빼다 — 같은 낱말이 두 번 선다. */}
      {title ? (
        <Typography component="h3" sx={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold, color: "text.secondary" }}>
          {title}
        </Typography>
      ) : null}
      <Box component="ul" role="list" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.75, minWidth: 0 }}>
        {shown.map((source) => {
          const kind = KINDS[source.type];
          const Icon = kind.Icon;
          return (
            <Box key={`${source.type}:${source.id}`} component="li"
              sx={{ display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", columnGap: 1, alignItems: "start", minWidth: 0 }}>
              <Icon aria-hidden="true" sx={{ fontSize: remPx(ICON.mark), color: "text.secondary", mt: "0.1875rem" }} />
              <Box sx={{ minWidth: 0 }}>
                <Link href={"#" + safeSourceRoute(source.route)} underline="hover"
                  sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>
                  {source.title || "(제목 없음)"}
                </Link>
                <Box sx={{ display: "flex", flexWrap: "wrap", columnGap: 1, rowGap: 0, fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
                  <span>{kind.label}</span>
                  {metaOf(source).map((value, index) => <span key={index}>{value}</span>)}
                </Box>
              </Box>
            </Box>
          );
        })}
      </Box>
      {!showAll && items.length > limit ? (
        <Box>
          <Button size="sm" variant="ghost" onClick={() => setShowAll(true)}>{items.length - limit}개 더 보기</Button>
        </Box>
      ) : null}
    </Box>
  );
}
