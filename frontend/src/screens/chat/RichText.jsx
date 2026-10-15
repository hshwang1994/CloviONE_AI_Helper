import React from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import { copyText, parseBlocks, parseInline } from "../chat-helpers.js";
import { CODE_FONT, renderInline } from "./links.jsx";
import { ANYWHERE_BREAK } from "../../ui/columnTypes.js";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "../../ui/theme.js";

/* 리치 텍스트 — `parseBlocks` 결과를 머리글 · 문단 · 목록(한 단 중첩) · 인용 · 구분선 · 표 · 키-값 · 코드로 그린다(텍스트 노드
 * 전용 — innerHTML 은 없다). 줄 안의 「**굵게**」 · 인라인 코드 · 「[제목](경로)」는 `parseInline` 이 나누고, 링크는 **그 답의
 * 출처와 같은 경로**이거나 화면 길잡이 경로일 때만 앱 안 링크다(D-569 · D-581). 잘못된 마크다운은 글로 떨어진다.
 *
 * 가로로 굴러가는 칸을 만들지 않는다 — 코드와 표는 줄을 바꿔 판 폭 안에 선다(클로비 패널의 「스크롤 칸 하나」 계약,
 * `assistant_panel_e2e`). 코드 · 주소 · 키만 글자 단위로 끊고 한글 문장은 낱말 단위다(`keep-all`). */

const BODY = { fontSize: FONT_SIZE.body, lineHeight: 1.7, ...KO_WORD_BREAK };

function CodeBlock({ text }) {
  const [copied, setCopied] = React.useState("");
  return (
    <Box sx={{ position: "relative", borderRadius: 1.5, bgcolor: "background.inset", border: 1, borderColor: "rule" }}>
      <Tooltip title={copied || "코드 복사"}>
        <IconButton size="small" aria-label="코드 복사"
          onClick={() => copyText(text).then((ok) => { setCopied(ok ? "복사했습니다" : "복사하지 못했습니다"); setTimeout(() => setCopied(""), 1500); })}
          sx={{ position: "absolute", top: 4, right: 4 }}>
          {copied === "복사했습니다" ? <CheckRoundedIcon sx={{ fontSize: "1rem" }} /> : <ContentCopyRoundedIcon sx={{ fontSize: "0.9375rem" }} />}
        </IconButton>
      </Tooltip>
      <span className="sr-only" role="status" aria-live="polite">{copied}</span>
      <Box component="pre" sx={{ m: 0, p: 1.5, pr: 5, fontSize: FONT_SIZE.bodySm, lineHeight: 1.55 }}>
        {/* AI-34: 펜스 안 글은 해석하지 않고 원문 그대로 텍스트 노드로만 넣는다. */}
        <Box component="code" sx={{ fontFamily: CODE_FONT, whiteSpace: "pre-wrap", ...ANYWHERE_BREAK }}>{text}</Box>
      </Box>
    </Box>
  );
}

function ListBlock({ items, linkify, keyBase, nested = false }) {
  return (
    <Box component={items.some((it) => it.marker) ? "ol" : "ul"} role="list"
      sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: nested ? 0.25 : 0.5, ...(nested ? { mt: 0.5, pl: 0.5 } : null) }}>
      {items.map((it, ii) => (
        <Box key={ii} component="li"
          sx={{ display: "grid", gridTemplateColumns: "1.25rem minmax(0,1fr)", columnGap: 0.5, alignItems: "baseline",
                ...(nested ? { fontSize: FONT_SIZE.bodySm } : null) }}>
          <Box component="span" aria-hidden="true"
            sx={{ color: "text.secondary", fontVariantNumeric: "tabular-nums", textAlign: it.marker ? "right" : "center" }}>
            {it.marker || (nested ? "◦" : "•")} {/* clovi-allow-glyph: 목록 글머리표 */}
          </Box>
          <Box component="span" sx={{ minWidth: 0, ...KO_WORD_BREAK }}>
            {linkify(it.text, `${keyBase}-${ii}`)}
            {(it.subs || []).map((s, si) => (
              <Box key={si} component="span" sx={{ display: "block", fontSize: FONT_SIZE.bodySm, color: "text.secondary", ...KO_WORD_BREAK }}>
                {linkify(s, `${keyBase}-${ii}-s${si}`)}
              </Box>
            ))}
            {it.children && it.children.length ? (
              <ListBlock items={it.children} linkify={linkify} keyBase={`${keyBase}-${ii}-c`} nested />
            ) : null}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

function TableBlock({ head, rows, linkify, keyBase }) {
  const cols = Math.max(head.length, ...rows.map((r) => r.length));
  const grid = `repeat(${cols}, minmax(0, 1fr))`;
  const cell = { px: 1, py: 0.75, borderTop: 1, borderColor: "rule", fontSize: FONT_SIZE.bodySm, minWidth: 0, ...KO_WORD_BREAK };
  return (
    <Box role="table" sx={{ border: 1, borderColor: "rule", borderRadius: 1.5, overflow: "hidden" }}>
      <Box role="row" sx={{ display: "grid", gridTemplateColumns: grid, bgcolor: "background.inset" }}>
        {Array.from({ length: cols }, (_, ci) => (
          <Box key={ci} role="columnheader" sx={{ ...cell, borderTop: 0, fontWeight: FONT_WEIGHT.semibold }}>
            {linkify(head[ci] || "", `${keyBase}-h${ci}`)}
          </Box>
        ))}
      </Box>
      {rows.map((row, ri) => (
        <Box key={ri} role="row" sx={{ display: "grid", gridTemplateColumns: grid }}>
          {Array.from({ length: cols }, (_, ci) => (
            <Box key={ci} role="cell" sx={cell}>{linkify(row[ci] || "", `${keyBase}-${ri}-${ci}`)}</Box>
          ))}
        </Box>
      ))}
    </Box>
  );
}

export function RichText({ text, keyLinks, routeLinks }) {
  const linkify = (value, key) => renderInline(parseInline(value, { routeLinks, keyLinks }), key);
  return (
    <Box sx={{ display: "grid", gap: 1.25, minWidth: 0, ...BODY }}>
      {parseBlocks(text).map((b, bi) => {
        if (b.kind === "head") {
          return (
            <Typography key={bi} component="h4"
              sx={{ mt: bi === 0 ? 0 : 0.75, fontSize: FONT_SIZE.cardTitle, fontWeight: FONT_WEIGHT.bold, color: "text.primary", lineHeight: 1.45, ...KO_WORD_BREAK }}>
              {linkify(b.text, "h" + bi)}
              {b.note ? (
                <Box component="span" sx={{ ml: 1, fontWeight: FONT_WEIGHT.medium, fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>
                  {linkify(b.note, "hn" + bi)}
                </Box>
              ) : null}
            </Typography>
          );
        }
        if (b.kind === "list") return <ListBlock key={bi} items={b.items} linkify={linkify} keyBase={"li" + bi} />;
        if (b.kind === "code") return <CodeBlock key={bi} text={b.text} />;
        if (b.kind === "rule") return <Box key={bi} component="hr" sx={{ m: 0, border: 0, borderTop: 1, borderColor: "rule" }} />;
        if (b.kind === "quote") {
          return (
            <Box key={bi} component="blockquote"
              sx={{ m: 0, pl: 1.5, borderLeft: 3, borderColor: "rule", color: "text.secondary", whiteSpace: "pre-wrap" }}>
              {linkify(b.lines.join("\n"), "q" + bi)}
            </Box>
          );
        }
        if (b.kind === "table") return <TableBlock key={bi} head={b.head} rows={b.rows} linkify={linkify} keyBase={"t" + bi} />;
        if (b.kind === "kv") {
          return (
            <Box key={bi} component="dl" sx={{ m: 0, display: "grid", gap: 0.25 }}>
              {b.rows.map((r, ri) => (
                <Box key={ri} sx={{ display: "grid", gridTemplateColumns: "minmax(4.5rem,auto) minmax(0,1fr)", columnGap: 1.25 }}>
                  <Box component="dt" sx={{ color: "text.secondary" }}>{r.key}</Box>
                  <Box component="dd" sx={{ m: 0, ...KO_WORD_BREAK }}>{linkify(r.text, "kv" + bi + "-" + ri)}</Box>
                </Box>
              ))}
            </Box>
          );
        }
        return (
          <Typography key={bi} component="p" sx={{ m: 0, ...BODY, whiteSpace: "pre-wrap" }}>
            {linkify(b.lines.join("\n"), "p" + bi)}
          </Typography>
        );
      })}
    </Box>
  );
}
