/* 틀의 본문을 **사람이 고칠 수 있는 글자**로 바꾸고 되돌린다.
 *
 * ## 왜 편집기를 하나 더 넣지 않는가
 *
 * 틀은 문서가 아니라 **뼈대**다. 실제 시드 셋을 재 보면 쓰는 마디가 다섯뿐이다 —
 * `heading` · `paragraph` · `bulletList` · `orderedList` · `listItem`. 표도 이미지도
 * 링크도 없다. 그 다섯을 위해 창 안에 ProseMirror 를 하나 더 띄우면 「본문 편집기가 둘」이
 * 되고, 둘 중 하나만 고쳐지는 날이 온다.
 *
 * 그래서 마크다운을 닮은 글자 한 판으로 바꾼다. `##` 은 제목, `-` 는 글머리, `1.` 은
 * 번호, 나머지는 문단이다. 다섯 마디가 **양방향으로 정확히** 왕복한다 — 왕복이 안 되면
 * 고치려고 연 사람이 본문을 잃는다. 그 왕복은 시드 셋으로 시험한다.
 *
 * ## 여기서 만든 JSON 도 서버가 다시 본다
 *
 * 이 함수가 정본이 아니다. 서버의 `blocks.normalize` 가 저장 직전에 한 번 더 걸러
 * 모르는 마디를 거절한다(저장 XSS 를 막는 자리가 거기 하나다). 여기서는 **읽고 쓰기
 * 편한 모양**만 만든다. */

const HEADING = /^(#{1,3})\s+(.*)$/;
const BULLET = /^[-*]\s+(.*)$/;
const ORDERED = /^\d+[.)]\s+(.*)$/;

function textOf(node) {
  if (!node) return "";
  if (node.type === "text") return node.text || "";
  return (node.content || []).map(textOf).join("");
}

/** Block JSON → 글자. 모르는 마디는 **글자만 남긴다** — 지우면 고치려고 연 사람이
 *  본문을 잃고, 그 손실은 저장을 누른 뒤에야 보인다. */
export function bodyToText(body) {
  const blocks = (body && body.content) || [];
  const lines = [];
  blocks.forEach((node) => {
    if (node.type === "heading") {
      const level = Math.min(3, Math.max(1, (node.attrs && node.attrs.level) || 2));
      lines.push(`${"#".repeat(level)} ${textOf(node)}`);
      return;
    }
    if (node.type === "bulletList" || node.type === "orderedList") {
      (node.content || []).forEach((item, i) => {
        const mark = node.type === "bulletList" ? "-" : `${i + 1}.`;
        lines.push(`${mark} ${textOf(item)}`);
      });
      return;
    }
    lines.push(textOf(node));
  });
  return lines.join("\n");
}

function paragraph(text) {
  return text
    ? { type: "paragraph", content: [{ type: "text", text }] }
    : { type: "paragraph" };
}

function listItem(text) {
  return { type: "listItem", content: [paragraph(text)] };
}

/** 글자 → Block JSON. 붙어 있는 같은 종류의 목록 줄은 **한 목록으로 묶는다** — 줄마다
 *  목록을 하나씩 만들면 왕복은 되지만 화면에서 글머리 사이가 벌어진다. */
export function textToBody(text) {
  const content = [];
  let list = null;

  const flush = () => { if (list) { content.push(list); list = null; } };

  (text || "").split("\n").forEach((raw) => {
    const line = raw.trimEnd();
    const heading = HEADING.exec(line);
    if (heading) {
      flush();
      content.push({
        type: "heading",
        attrs: { level: heading[1].length },
        content: heading[2] ? [{ type: "text", text: heading[2] }] : [],
      });
      return;
    }
    const bullet = BULLET.exec(line);
    if (bullet) {
      if (!list || list.type !== "bulletList") { flush(); list = { type: "bulletList", content: [] }; }
      list.content.push(listItem(bullet[1]));
      return;
    }
    const ordered = ORDERED.exec(line);
    if (ordered) {
      if (!list || list.type !== "orderedList") { flush(); list = { type: "orderedList", content: [] }; }
      list.content.push(listItem(ordered[1]));
      return;
    }
    flush();
    content.push(paragraph(line.trim()));
  });
  flush();

  /* 서버는 빈 문서를 거절한다. 아무것도 안 적은 틀은 문단 하나로 시작한다. */
  return { type: "doc", content: content.length ? content : [paragraph("")] };
}
