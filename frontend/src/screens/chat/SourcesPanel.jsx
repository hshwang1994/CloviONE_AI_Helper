import React from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import { FONT_SIZE, FONT_WEIGHT, ICON, KO_WORD_BREAK, remPx } from "../../ui/theme.js";
import { fmtTime, safeSourceRoute, stripBlock } from "../chat-helpers.js";
import { SOURCE_KINDS, panelSources } from "./SourceList.jsx";

/* 참고 자료 판 — **고른 답**이 쓴 자료다(AI 채팅 개선 회차). 예전 레일은 마지막으로 인용한 답의 출처 전부라, 본문 목록과 같은 문서
 * 열 개를 되풀이했다. 지금은
 *   - 고른 답(기본은 그런 자료가 있는 마지막 답, 답 아래 「참고 자료 n」을 누르면 그 답)의 인용 출처에서 본문 결과 목록에 이미 선
 *     항목을 뺀 것이다(`panelSources`). 대화가 바뀌면 다시 정한다(화면이 정한다).
 *   - 항목은 종류 아이콘 · 제목(두 줄, 전체는 `title`) · 종류와 자리(공간 · 키 · 상태)다. 누르면 앱 안 원문으로 간다.
 *   - 답 안 링크에 올리거나 초점을 주면 같은 자료가 강조되고 보이는 자리로 굴러온다(`activeRoute`).
 * 판은 넓은 틀에서만 서고(그 대화에 이런 자료가 있을 때), 사람이 닫을 수 있다. 다른 틀에서는 답 아래 접기로 선다. */

export function SourcesPanel({ message, isLatest, activeRoute, onClose, headingId }) {
  const sources = message ? panelSources(message.structured) : [];
  const activeKey = activeRoute ? stripBlock(activeRoute) : null;
  const listRef = React.useRef(null);
  React.useEffect(() => {
    if (!activeKey || !listRef.current) return;
    const node = listRef.current.querySelector(`[data-source-route="${activeKey.replace(/"/g, "")}"]`);
    if (node && node.scrollIntoView) node.scrollIntoView({ block: "nearest" });
  }, [activeKey]);
  return (
    <Box component="aside" aria-labelledby={headingId} data-sources-panel=""
      sx={{ display: "flex", flexDirection: "column", minHeight: 0, height: "100%", minWidth: 0 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, minHeight: "3.5rem", borderBottom: 1, borderColor: "rule", flexShrink: 0 }}>
        <Typography component="h2" id={headingId} sx={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold }}>참고 자료</Typography>
        <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
          {sources.length}개
        </Typography>
        <Box sx={{ flex: 1 }} />
        {message && message.created_at ? (
          <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }} title="이 자료를 쓴 답의 시각">
            {fmtTime(message.created_at)} 답
          </Typography>
        ) : null}
        {onClose ? (
          <IconButton size="small" aria-label="참고 자료 닫기" onClick={onClose}>
            <CloseRoundedIcon sx={{ fontSize: "1.125rem" }} />
          </IconButton>
        ) : null}
      </Box>
      <Box ref={listRef} sx={{ flex: 1, minHeight: 0, overflowY: "auto", px: 1, py: 1.25 }}>
        {!isLatest && message ? (
          <Typography sx={{ px: 1, pb: 1, fontSize: FONT_SIZE.caption, color: "text.secondary", ...KO_WORD_BREAK }}>
            앞 답의 자료입니다. 다른 답의 참고 자료 단추를 누르면 그 답의 자료로 바뀝니다.
          </Typography>
        ) : null}
        <Box component="ul" role="list" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 0.25 }}>
          {sources.map((source) => {
            const kind = SOURCE_KINDS[source.type];
            const Icon = kind.Icon;
            const route = safeSourceRoute(source.route);
            const key = stripBlock(route);
            const active = activeKey && key === activeKey;
            const meta = [kind.label, source.key, source.status, source.where].filter((v) => typeof v === "string" && v.trim());
            return (
              <Box key={`${source.type}:${source.id}`} component="li" data-source-route={key} data-active={active ? "" : undefined}
                sx={{ borderRadius: 1.5, transition: "background-color .15s ease, box-shadow .15s ease",
                      bgcolor: active ? "background.inset" : "transparent",
                      boxShadow: (t) => (active ? `inset 3px 0 0 ${t.palette.primary.main}` : "none"),
                      "&:hover": { bgcolor: "action.hover" } }}>
                <Box component="a" href={"#" + route} title={source.title || "(제목 없음)"}
                  sx={{ display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", columnGap: 1, alignItems: "start",
                        px: 1, py: 0.875, color: "inherit", textDecoration: "none", borderRadius: 1.5,
                        "&:focus-visible": { outline: (t) => `2px solid ${t.palette.focusRing}`, outlineOffset: "-2px" } }}>
                  <Icon aria-hidden="true" sx={{ fontSize: remPx(ICON.mark), color: "text.secondary", mt: "0.1875rem" }} />
                  <Box sx={{ minWidth: 0, display: "grid", gap: 0.25 }}>
                    <Box component="span"
                      sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, color: active ? "primary.main" : "text.primary",
                            display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", ...KO_WORD_BREAK }}>
                      {source.title || "(제목 없음)"}
                    </Box>
                    <Box component="span" sx={{ display: "flex", flexWrap: "wrap", columnGap: 1, fontSize: FONT_SIZE.caption,
                                                color: "text.secondary", minWidth: 0, ...KO_WORD_BREAK }}>
                      {meta.map((value, i) => <span key={i}>{value}</span>)}
                    </Box>
                  </Box>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Box>
    </Box>
  );
}
