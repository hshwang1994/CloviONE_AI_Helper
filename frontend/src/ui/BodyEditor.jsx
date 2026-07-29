import React, { useRef } from "react";
import { Button } from "./kit.jsx";

/* 공용 본문 편집기 — 문서 새 문서와 새 티켓 설명이 같은 서식(제목/글머리/번호/구분선/이모지)과
 * 라이브 미리보기를 쓴다. 서식 규칙은 백엔드 app/core/notion_blocks.py(markdown_to_blocks)와 동일해야
 * 미리보기와 실제 저장 결과가 어긋나지 않는다. 서식 도구는 커서가 있는 '줄 맨 앞'에 표식을 붙인다. */

const BODY_EMOJIS = ["✅", "📌", "⚠️", "🔹", "👉", "🎯", "🎉", "💡"];
const BODY_MAX_LINES = 100;

export function BodyEditor({ id, value, onChange, rows = 12, placeholder }) {
  const ref = useRef(null);
  const caret = () => {
    const ta = ref.current;
    const val = value || "";
    const pos = ta && ta.selectionStart != null ? ta.selectionStart : val.length;
    return { val, pos };
  };
  const apply = (next, cursor) => {
    onChange(next);
    requestAnimationFrame(() => {
      const ta = ref.current;
      if (ta) { try { ta.focus(); ta.setSelectionRange(cursor, cursor); } catch (e) { /* noop */ } }
    });
  };
  const prefixLine = (prefix) => {
    const { val, pos } = caret();
    const lineStart = pos <= 0 ? 0 : val.lastIndexOf("\n", pos - 1) + 1;
    apply(val.slice(0, lineStart) + prefix + val.slice(lineStart), pos + prefix.length);
  };
  const insertDivider = () => {
    const { val, pos } = caret();
    const before = val.slice(0, pos);
    const chunk = (before && !before.endsWith("\n") ? "\n" : "") + "---\n";
    apply(before + chunk + val.slice(pos), pos + chunk.length);
  };
  const insertAtCursor = (text) => {
    const { val, pos } = caret();
    apply(val.slice(0, pos) + text + val.slice(pos), pos + text.length);
  };

  return (
    <>
      <div className="docs-body-toolbar" role="group" aria-label="본문 서식">
        <button type="button" className="docs-fmt-btn" onClick={() => prefixLine("## ")}>제목</button>
        <button type="button" className="docs-fmt-btn" onClick={() => prefixLine("- ")}>글머리</button>
        <button type="button" className="docs-fmt-btn" onClick={() => prefixLine("1. ")}>번호</button>
        <button type="button" className="docs-fmt-btn" onClick={insertDivider}>구분선</button>
        <span className="docs-fmt-sep" aria-hidden="true" />
        {BODY_EMOJIS.map((em) => (
          <button type="button" key={em} className="docs-fmt-emoji" aria-label={"이모지 " + em} onClick={() => insertAtCursor(em + " ")}>{em}</button>
        ))}
      </div>
      <textarea id={id} ref={ref} className="k-input docs-body-text" rows={rows} value={value}
        onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      <div className="docs-preview-label">미리보기</div>
      <BodyPreview text={value} />
    </>
  );
}

/* 본문 미리보기 — markdown_to_blocks와 같은 규칙으로 렌더(빈 줄=간격, 100줄 상한, 초과 경고).
 * 사용자 입력이므로 React가 기본 textContent 렌더(불변 §6 XSS 없음). */
export function BodyPreview({ text }) {
  const raw = (text || "").split("\n");
  const lines = raw.slice(0, BODY_MAX_LINES);
  const truncated = raw.length > BODY_MAX_LINES;
  const blocks = [];
  let list = null;
  const flush = () => { if (list) { blocks.push(list); list = null; } };
  lines.forEach((ln) => {
    const s = ln.trim();
    if (!s) { flush(); blocks.push({ type: "spacer" }); return; }
    if (s === "---" || s === "___" || s === "***") { flush(); blocks.push({ type: "hr" }); return; }
    if (s.startsWith("### ")) { flush(); blocks.push({ type: "h3", text: s.slice(4) }); return; }
    if (s.startsWith("## ")) { flush(); blocks.push({ type: "h2", text: s.slice(3) }); return; }
    if (s.startsWith("# ")) { flush(); blocks.push({ type: "h1", text: s.slice(2) }); return; }
    if (s.startsWith("- ") || s.startsWith("* ")) {
      if (!list || list.type !== "ul") { flush(); list = { type: "ul", items: [] }; }
      list.items.push(s.slice(2)); return;
    }
    const m = s.match(/^(\d+)\.\s+(.*)$/);
    if (m) {
      if (!list || list.type !== "ol") { flush(); list = { type: "ol", items: [] }; }
      list.items.push(m[2]); return;
    }
    flush();
    blocks.push({ type: "p", text: ln });
  });
  flush();
  if (blocks.length === 0) {
    return <div className="docs-preview docs-preview--empty">본문을 입력하면 실제 모양이 여기에 보입니다.</div>;
  }
  return (
    <div className="docs-preview">
      {blocks.map((b, i) => {
        if (b.type === "spacer") return <div key={i} className="docs-preview-spacer" aria-hidden="true" />;
        if (b.type === "hr") return <hr key={i} className="docs-preview-hr" />;
        if (b.type === "h1") return <div key={i} className="docs-preview-h1">{b.text}</div>;
        if (b.type === "h2") return <div key={i} className="docs-preview-h2">{b.text}</div>;
        if (b.type === "h3") return <div key={i} className="docs-preview-h3">{b.text}</div>;
        if (b.type === "ul") return <ul key={i} className="docs-preview-ul">{b.items.map((it, j) => <li key={j}>{it}</li>)}</ul>;
        if (b.type === "ol") return <ol key={i} className="docs-preview-ol">{b.items.map((it, j) => <li key={j}>{it}</li>)}</ol>;
        return <div key={i} className="docs-preview-p">{b.text}</div>;
      })}
      {truncated ? (
        <div className="docs-preview-trunc">이후 {raw.length - BODY_MAX_LINES}줄은 저장되지 않습니다(최대 {BODY_MAX_LINES}줄).</div>
      ) : null}
    </div>
  );
}
