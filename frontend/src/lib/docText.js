/* 본문 문서(ProseMirror)에서 **글자만** 뽑는 작은 헬퍼.
 *
 * 서버에도 같은 일을 하는 것이 있다(`app/knowledge/blocks.py::to_text`). 여기 따로 두는
 * 이유는 화면이 **저장하기 전에** 물어야 하는 것들이 있기 때문이다 — 「작성 도움」의 절이
 * 이미 들어갔는가, 설명이 비었는가. 저장 왕복을 한 번 하고 나서야 알 수 있으면 그것은
 * 도움이 아니다.
 *
 * 파생값을 만드는 자리가 아니다. 저장되는 마크다운·평문은 **서버가** 정본 문서에서
 * 파생시킨다(`app/tickets/body_doc.py`) — 여기서 만든 값을 저장에 실어 보내지 않는다.
 * 두 곳이 각자 파생시키면 한쪽만 고쳐지는 날이 온다.
 */

/** 문서 전체의 글자. 블록 사이는 줄바꿈이다. */
export function docText(doc) {
  const lines = [];
  walk(doc, lines);
  return lines.join("\n");
}

function walk(node, lines) {
  if (!node || typeof node !== "object") return;
  if (node.type === "text") {
    if (lines.length === 0) lines.push("");
    lines[lines.length - 1] += node.text || "";
    return;
  }
  const block = BLOCK_TYPES.has(node.type);
  if (block) lines.push("");
  for (const child of node.content || []) walk(child, lines);
}

const BLOCK_TYPES = new Set([
  "paragraph", "heading", "blockquote", "codeBlock", "listItem", "taskItem",
  "tableHeader", "tableCell",
]);

/** 문서가 비었는가. 공백만 있는 것도 비었다고 본다. */
export function docIsEmpty(doc) {
  return !docText(doc).trim();
}

/** 이 문서에 이 제목이 이미 있는가. 「작성 도움」이 절을 두 번 넣지 않게 한다. */
export function docHasHeading(doc, text) {
  const want = String(text || "").trim();
  if (!want) return false;
  return (doc && doc.content ? doc.content : []).some(
    (n) => n && n.type === "heading" && plain(n).trim() === want,
  );
}

function plain(node) {
  const lines = [];
  for (const child of node.content || []) walk(child, lines);
  return lines.join("");
}

/** 문서 끝에 「제목 + 빈 글머리 한 줄」을 붙인다. 예시 문장은 안 넣는다 —
 * 남의 문장이 자기 티켓에 남으면 안 된다(`WritingAidButton` 의 그 규칙). */
export function appendSection(doc, heading, level = 2) {
  const base = doc && doc.type === "doc" ? doc : { type: "doc", content: [] };
  return {
    ...base,
    content: [
      ...(base.content || []),
      { type: "heading", attrs: { level }, content: [{ type: "text", text: heading }] },
      {
        type: "bulletList",
        content: [{ type: "listItem", content: [{ type: "paragraph" }] }],
      },
    ],
  };
}
