import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { parseBlocks, parseInline } from "../chat-helpers.js";
import { renderInline } from "./links.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";

/* 리치 텍스트 — parseBlocks 결과를 머리글/목록/키-값/문단으로 렌더한다(텍스트 노드 전용).
 * 머리글은 본문(0.9375rem)보다 커야 '머리글'로 읽힌다. 크기는 전부 rem이라 4K에서 함께 커진다.
 *
 * 줄 안의 「**굵게**」는 굵게, 「[제목](경로)」는 **그 답의 출처와 같은 경로일 때만** 앱 안 링크다(A8, D-569) — 출처에 없는
 * 링크는 원래 글자 그대로 남는다. `routeLinks` 는 그 답의 출처 경로들, `keyLinks` 는 출처에 있는 티켓 키 → 경로다.
 * 코드 블록은 이 해석을 거치지 않는다. */
export function RichText({ text, keyLinks, routeLinks }) {
  const linkify = (value, key) => renderInline(parseInline(value, { routeLinks, keyLinks }), key);
  return (
    <>
      {parseBlocks(text).map((b, bi) => {
        if (b.kind === "head") {
          return (
            <Typography
              key={bi} component="h4"
              sx={{ mt: bi === 0 ? 0 : 1.5, mb: 0.5, fontSize: FONT_SIZE.sectionTitle, fontWeight: FONT_WEIGHT.bold, color: "text.primary", lineHeight: 1.4 }}
            >
              {linkify(b.text, "h" + bi)}
              {b.note ? <Box component="span" sx={{ ml: 1, fontWeight: FONT_WEIGHT.medium, fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{linkify(b.note, "hn" + bi)}</Box> : null}
            </Typography>
          );
        }
        if (b.kind === "list") {
          return (
            <Box
              key={bi} component="ul" role="list"
              sx={{ listStyle: "none", m: 0, mt: bi === 0 ? 0 : 1, p: 0, display: "grid", gap: 0.5 }}
            >
              {b.items.map((it, ii) => (
                <Box
                  key={ii} component="li"
                  sx={{ display: "grid", gridTemplateColumns: it.marker ? "auto minmax(0,1fr)" : "minmax(0,1fr)", columnGap: 0.75, alignItems: "baseline" }}
                >
                  {it.marker ? (
                    <Box component="span" sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>{it.marker}</Box>
                  ) : null}
                  <Box component="span" sx={{ ...KO_WORD_BREAK, "&::before": it.marker ? undefined : { content: '"· "', color: "text.secondary" } }}> {/* clovi-allow-glyph: 목록 글머리표 */}
                    {linkify(it.text, "li" + bi + "-" + ii)}
                  </Box>
                  {it.subs.map((s, si) => (
                    <Box
                      key={si} component="span"
                      sx={{ gridColumn: it.marker ? 2 : 1, fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}
                    >
                      {linkify(s, "li" + bi + "-" + ii + "-s" + si)}
                    </Box>
                  ))}
                </Box>
              ))}
            </Box>
          );
        }
        if (b.kind === "code") {
          // AI-34: 펜스 안 텍스트는 절대 linkifyText/블록 재분류를 거치지 않는다 — 원문
          // 그대로 텍스트 노드로만 넣는다(innerHTML 금지, CLAUDE.md §2). 긴 줄은 이 앱의
          // 다른 넓은 콘텐츠와 같은 관용(overflowX:auto)으로 가로 스크롤한다.
          return (
            <Box
              key={bi} component="pre"
              sx={{
                m: 0, mt: bi === 0 ? 0 : 1, p: 1.25, borderRadius: 1.5,
                bgcolor: "background.surface2", overflowX: "auto",
                fontSize: FONT_SIZE.bodySm, lineHeight: 1.5,
              }}
            >
              <Box component="code" sx={{ fontFamily: "monospace", whiteSpace: "pre" }}>
                {b.text}
              </Box>
            </Box>
          );
        }
        if (b.kind === "kv") {
          return (
            <Box key={bi} component="dl" sx={{ m: 0, mt: bi === 0 ? 0 : 1, display: "grid", gap: 0.25 }}>
              {b.rows.map((r, ri) => (
                <Box key={ri} sx={{ display: "grid", gridTemplateColumns: "minmax(4.5rem,auto) minmax(0,1fr)", columnGap: 1.25, fontSize: FONT_SIZE.body }}>
                  <Box component="dt" sx={{ color: "text.secondary" }}>{r.key}</Box>
                  <Box component="dd" sx={{ m: 0, ...KO_WORD_BREAK }}>{linkify(r.text, "kv" + bi + "-" + ri)}</Box>
                </Box>
              ))}
            </Box>
          );
        }
        return (
          <Typography key={bi} sx={{ m: 0, mt: bi === 0 ? 0 : 1, fontSize: "0.9375rem", lineHeight: 1.6, whiteSpace: "pre-wrap", ...KO_WORD_BREAK }}>
            {linkify(b.lines.join("\n"), "p" + bi)}
          </Typography>
        );
      })}
    </>
  );
}
