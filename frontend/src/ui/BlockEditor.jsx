import React from "react";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import MuiButton from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import { alpha } from "@mui/material/styles";
import { useEditor, EditorContent } from "@tiptap/react";
import { Extension, Node, mergeAttributes } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK } from "./theme.js";

/* 블록 편집기 — 본문의 정본이 Block JSON 이라는 결정(D-198)의 화면 쪽 절반이다 (S7).
 *
 * ## 이 파일은 반드시 늦게 실려야 한다
 *
 * TipTap 과 ProseMirror 는 합쳐서 초기 번들 예산의 상당 부분을 먹는다. 문서를 안 여는
 * 사람의 첫 로딩에 그 무게를 얹지 않는다 — 그래서 부르는 쪽이 `React.lazy` 로 들여온다.
 * 이 파일을 정적으로 import 하는 순간 그 결정이 조용히 무너지므로,
 * `frontend/src/ui/block-editor-lazy.test.jsx` 가 그것을 코드로 확인한다.
 *
 * ## 왜 `BodyEditor.jsx` 를 안 쓰는가
 *
 * 그쪽은 **마크다운 문자열**을 다룬다. 정본이 문자열이면 「이 문장의 출처 위치」를 가리킬
 * 수 없고(D-198), 버전 차이도 줄 단위로만 볼 수 있다. 둘은 서로 다른 자료를 다루는 서로
 * 다른 도구라 합치지 않는다 — 옛 문서(Notion 미러)는 그대로 `BodyEditor` 를 쓴다.
 *
 * ## 블록 id 를 돌려주는 것이 이 편집기의 계약이다
 *
 * 서버가 최상위 블록마다 `blockId` 를 붙여 보낸다. 그 값이 인용의 앵커이고, 저장할 때
 * **그대로 돌려줘야** 안 건드린 문단의 인용이 계속 같은 곳을 가리킨다. 서버에도 폴백이
 * 있지만(자리로 물려주기) 그것은 문단을 끼워 넣으면 어긋난다 — 정확한 쪽은 여기다. */

const BLOCK_ID_ATTR = "blockId";

/* `blockId` 를 붙일 노드들. 서버의 `BLOCK_NODES`(app/knowledge/blocks.py)와 같은 목록이다.
 * 여기 없는 노드에 붙이면 서버가 모르는 속성이 되어 저장 때 사라지고, 여기 빠진 노드는
 * 앵커 없이 저장돼 서버가 새 id 를 발급한다 — 둘 다 인용이 끊기는 길이다. */
const ANCHORED_NODES = [
  "paragraph", "heading", "bulletList", "orderedList", "blockquote",
  "codeBlock", "horizontalRule",
];

/* 서버가 준 `blockId` 를 편집 중에도 들고 있다가 그대로 돌려주는 전역 속성. */
const BlockId = Extension.create({
  name: "blockId",
  addGlobalAttributes() {
    return [{
      types: ANCHORED_NODES,
      attributes: {
        [BLOCK_ID_ATTR]: {
          default: null,
          // DOM 을 거치지 않는다 — 이 값은 화면에 그릴 것이 아니라 JSON 에만 사는 값이다.
          rendered: false,
        },
      },
    }];
  },
});

/* 멘션. `@tiptap/extension-mention` 을 쓰지 않는 이유는 그것이 자동완성 팝업을 위해
 * `tippy.js` 를 함께 끌고 오기 때문이다 — 지금 필요한 것은 **서버가 보낸 멘션을 그리고
 * 그대로 돌려주는 것**뿐이다. 자동완성이 필요해지는 날 그 확장을 들이면 되고, 그때까지
 * 안 쓰는 팝업 라이브러리를 번들에 넣지 않는다. */
const Mention = Node.create({
  name: "mention",
  group: "inline",
  inline: true,
  atom: true,
  addAttributes() {
    return {
      kind: { default: "user" },
      id: { default: "" },
      label: { default: "" },
    };
  },
  parseHTML() {
    return [{ tag: "span[data-mention-id]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(
      {
        "data-mention-id": HTMLAttributes.id,
        "data-mention-kind": HTMLAttributes.kind,
        class: "k-mention",
      },
    ), `@${HTMLAttributes.label || HTMLAttributes.id}`];
  },
  renderText({ node }) {
    return `@${node.attrs.label || node.attrs.id}`;
  },
});

export const EMPTY_DOC = { type: "doc", content: [] };

/* 서식 도구. 이모지를 안 쓴다 — 화면에서 이모지를 전수 제거한 결정과 같은 자리이고,
 * 도구가 스스로 그것을 권하면 안 된다(`BodyEditor.jsx` 가 같은 이유로 여덟 개를 없앴다). */
const TOOLS = [
  { id: "bold", label: "굵게", run: (c) => c.toggleBold(), on: "bold" },
  { id: "italic", label: "기울임", run: (c) => c.toggleItalic(), on: "italic" },
  { id: "strike", label: "취소선", run: (c) => c.toggleStrike(), on: "strike" },
  { id: "code", label: "코드", run: (c) => c.toggleCode(), on: "code" },
  { id: "h2", label: "제목", run: (c) => c.toggleHeading({ level: 2 }), on: ["heading", { level: 2 }] },
  { id: "bullet", label: "글머리", run: (c) => c.toggleBulletList(), on: "bulletList" },
  { id: "ordered", label: "번호", run: (c) => c.toggleOrderedList(), on: "orderedList" },
  { id: "quote", label: "인용", run: (c) => c.toggleBlockquote(), on: "blockquote" },
  { id: "rule", label: "구분선", run: (c) => c.setHorizontalRule(), on: null },
];

function isActive(editor, on) {
  if (!editor || on == null) return false;
  return Array.isArray(on) ? editor.isActive(on[0], on[1]) : editor.isActive(on);
}

/* 편집기 한 대.
 *
 * `value` 는 서버가 준 Block JSON 이고 `onChange` 는 그것과 같은 모양을 돌려준다.
 * 부르는 쪽이 저장 시점을 정한다 — 여기서 저장을 부르지 않는 이유는 `DragDrop.jsx` 가
 * 낙관적 갱신을 안 하는 이유와 같다: 언제가 진실인지는 부르는 쪽이 알아야 한다. */
export function BlockEditor({ value, onChange, readOnly = false, label = "본문" }) {
  const editor = useEditor({
    editable: !readOnly,
    extensions: [
      StarterKit.configure({
        // 링크는 StarterKit 밖이다(별도 확장). 지금은 붙여 넣은 링크를 **그대로 보존**하되
        // 편집기가 새로 만들지는 않는다 — 서버가 위험한 스킴을 떼어 내므로 저장은 안전하고,
        // 도구를 안 주는 것은 아직 그 UI 를 설계하지 않았기 때문이다.
        heading: { levels: [1, 2, 3] },
      }),
      BlockId,
      Mention,
    ],
    content: value || EMPTY_DOC,
    onUpdate: ({ editor: e }) => onChange?.(e.getJSON()),
  }, [readOnly]);

  /* 밖에서 문서가 바뀌면(되돌리기·다른 판 열람) 편집기 내용을 갈아 끼운다.
   * `emitUpdate: false` 로 넣는다 — 안 그러면 넣자마자 `onUpdate` 가 돌아 부르는 쪽이
   * 「사용자가 고쳤다」로 오해하고, 그 상태로 저장하면 안 한 편집이 판으로 쌓인다. */
  React.useEffect(() => {
    if (!editor || !value) return;
    const current = JSON.stringify(editor.getJSON());
    if (current === JSON.stringify(value)) return;
    editor.commands.setContent(value, false);
  }, [editor, value]);

  React.useEffect(() => () => editor?.destroy(), [editor]);

  if (!editor) return null;

  return (
    <Box>
      {!readOnly && (
        <>
          <Stack
            direction="row"
            spacing={0.5}
            role="toolbar"
            aria-label={`${label} 서식`}
            sx={{ flexWrap: "wrap", rowGap: 0.5, mb: 1 }}
          >
            {TOOLS.map((tool) => (
              <MuiButton
                key={tool.id}
                size="small"
                type="button"
                variant={isActive(editor, tool.on) ? "contained" : "text"}
                aria-pressed={tool.on ? isActive(editor, tool.on) : undefined}
                onClick={() => tool.run(editor.chain().focus()).run()}
                sx={{ minWidth: 0, px: 1, fontSize: FONT_SIZE.bodySm }}
              >
                {tool.label}
              </MuiButton>
            ))}
          </Stack>
          <Divider sx={{ mb: 1 }} />
        </>
      )}
      <Box
        sx={(theme) => ({
          ...KO_WORD_BREAK,
          border: readOnly ? "none" : `1px solid ${theme.palette.divider}`,
          borderRadius: 1,
          px: readOnly ? 0 : 1.5,
          py: readOnly ? 0 : 1,
          minHeight: readOnly ? 0 : "16rem",
          fontSize: FONT_SIZE.body,
          "& .ProseMirror": { outline: "none", minHeight: readOnly ? 0 : "14rem" },
          "& .ProseMirror h1, & .ProseMirror h2, & .ProseMirror h3": {
            fontWeight: FONT_WEIGHT.semibold,
            marginBlock: "0.8em 0.4em",
          },
          "& .ProseMirror blockquote": {
            borderLeft: `3px solid ${theme.palette.divider}`,
            paddingLeft: "0.9em",
            marginInlineStart: 0,
            color: theme.palette.text.secondary,
          },
          "& .ProseMirror pre": {
            background: alpha(theme.palette.text.primary, 0.06),
            borderRadius: 4,
            padding: "0.7em 0.9em",
            // 코드는 글자 단위로 끊는다 — 한글 산문과 다른 규약이다(CLAUDE.md §10).
            overflowWrap: "anywhere",
          },
          "& .k-mention": {
            color: theme.palette.primary.main,
            fontWeight: FONT_WEIGHT.medium,
          },
        })}
      >
        <EditorContent editor={editor} aria-label={label} />
      </Box>
    </Box>
  );
}

/* 읽기 전용 렌더. 목록·이력 화면이 본문을 보여 줄 때 쓴다 — 편집기를 그대로 재사용하는
 * 이유는 **같은 스키마로 그려야** 편집할 때와 볼 때의 모양이 안 갈리기 때문이다. */
export function BlockView({ value, label = "본문" }) {
  return <BlockEditor value={value} readOnly label={label} />;
}

export default BlockEditor;
