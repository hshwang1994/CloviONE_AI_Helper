import React from "react";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import { Button as KitButton, FieldLabel, useToast } from "./kit.jsx";
import { isEmbeddableImageSrc } from "../lib/safeUrl.js";
import IconButton from "@mui/material/IconButton";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import { alpha } from "@mui/material/styles";
import { useEditor, EditorContent } from "@tiptap/react";
import { Extension, Node, mergeAttributes } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import TaskList from "@tiptap/extension-task-list";
import TaskItem from "@tiptap/extension-task-item";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import Image from "@tiptap/extension-image";
import Table from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableHeader from "@tiptap/extension-table-header";
import TableCell from "@tiptap/extension-table-cell";
import FormatBoldRoundedIcon from "@mui/icons-material/FormatBoldRounded";
import FormatItalicRoundedIcon from "@mui/icons-material/FormatItalicRounded";
import FormatUnderlinedRoundedIcon from "@mui/icons-material/FormatUnderlinedRounded";
import FormatStrikethroughRoundedIcon from "@mui/icons-material/FormatStrikethroughRounded";
import CodeRoundedIcon from "@mui/icons-material/CodeRounded";
import LooksOneRoundedIcon from "@mui/icons-material/LooksOneRounded";
import LooksTwoRoundedIcon from "@mui/icons-material/LooksTwoRounded";
import Looks3RoundedIcon from "@mui/icons-material/Looks3Rounded";
import FormatQuoteRoundedIcon from "@mui/icons-material/FormatQuoteRounded";
import TerminalRoundedIcon from "@mui/icons-material/TerminalRounded";
import HorizontalRuleRoundedIcon from "@mui/icons-material/HorizontalRuleRounded";
import FormatListBulletedRoundedIcon from "@mui/icons-material/FormatListBulletedRounded";
import FormatListNumberedRoundedIcon from "@mui/icons-material/FormatListNumberedRounded";
import ChecklistRoundedIcon from "@mui/icons-material/ChecklistRounded";
import TableChartRoundedIcon from "@mui/icons-material/TableChartRounded";
import InsertLinkRoundedIcon from "@mui/icons-material/InsertLinkRounded";
import InsertPhotoRoundedIcon from "@mui/icons-material/InsertPhotoRounded";
import InsertEmoticonRoundedIcon from "@mui/icons-material/InsertEmoticonRounded";
import UndoRoundedIcon from "@mui/icons-material/UndoRounded";
import RedoRoundedIcon from "@mui/icons-material/RedoRounded";
import { EmojiPicker } from "./EmojiPicker.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, RADIUS } from "./theme.js";

/* 블록 편집기 — 본문의 정본이 Block JSON 이라는 결정(D-198)의 화면 쪽 절반이다 (S7).
 *
 * ## 이 파일은 반드시 늦게 실려야 한다
 *
 * TipTap 과 ProseMirror 는 합쳐서 초기 번들 예산의 상당 부분을 먹는다. 문서를 안 여는
 * 사람의 첫 로딩에 그 무게를 얹지 않는다 — 그래서 부르는 쪽이 `React.lazy` 로 들여온다.
 * 이 파일을 정적으로 import 하는 순간 그 결정이 조용히 무너지므로,
 * `frontend/src/ui/block-editor-lazy.test.jsx` 가 그것을 코드로 확인한다.
 *
 * ## 티켓 본문도 이 편집기를 쓴다
 *
 * 예전에는 티켓 설명·본문이 `BodyEditor.jsx`(마크다운 문자열 + 글자 칩 툴바)를 썼고, 이
 * 자리에는 「둘은 서로 다른 자료를 다루는 서로 다른 도구라 합치지 않는다」고 적혀 있었다.
 * 그 문장은 자료가 달랐기 때문에 맞았고, **자료를 같게 만들면서 함께 없어졌다** —
 * `tickets.body_doc` 이 문서 본문과 같은 스키마이고 같은 검증기를 지난다
 * (`app/tickets/body_doc.py`). 마크다운은 이제 정본이 아니라 서버가 만드는 파생값이다.
 *
 * 정본이 문자열이면 「이 문장의 출처 위치」를 가리킬 수 없고(D-198) 버전 차이도 줄
 * 단위로만 볼 수 있다 — 티켓에서도 같은 이유로 정본을 문서로 옮겼다.
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
  "codeBlock", "horizontalRule", "image", "table", "taskList",
];

/* 서버가 준 `blockId` 를 편집 중에도 들고 있다가 그대로 돌려주는 전역 속성.
 *
 * **DOM 에도 싣는다** (S10). 인용을 누르면 그 문단까지 가야 하는데(`?block=<id>`),
 * JSON 에만 있으면 화면이 그 자리를 찾을 방법이 없다 — 본문 글자를 맞춰 보는 수밖에
 * 없고 그것은 같은 문장이 두 번 나오는 순간 틀린다.
 *
 * 붙여넣기로 같은 id 가 두 개 생길 수 있지만 서버의 `normalize` 가 중복을 보면 새 id 를
 * 발급하므로(app/knowledge/blocks.py) 저장 시점에 정리된다. */
const BlockId = Extension.create({
  name: "blockId",
  addGlobalAttributes() {
    return [{
      types: ANCHORED_NODES,
      attributes: {
        [BLOCK_ID_ATTR]: {
          default: null,
          parseHTML: (element) => element.getAttribute("data-block-id"),
          renderHTML: (attributes) =>
            attributes[BLOCK_ID_ATTR] ? { "data-block-id": attributes[BLOCK_ID_ATTR] } : {},
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

/* 그림 — 서버가 받는 주소의 그림만 읽는다(`lib/safeUrl.js::isEmbeddableImageSrc`).
 *
 * 🔴 메일이나 문서 편집기에서 본문을 복사해 붙여 넣으면 그림이 `cid:` · `file:` · `blob:` 주소를 들고 온다. 그 주소는
 * 이 제품 밖에서만 열려서 서버가 저장을 거절한다(422). 예전에는 편집기가 그 그림을 그대로 받아, 사용자는 깨진 그림
 * 상자를 본 채로 저장하다 실패했다(2026-09-16, 새 티켓에서 다섯 번). 기본 확장은 `data:` 만 걸렀다(`allowBase64`).
 * 읽는 규칙에서 거르면 붙여넣기 · 끌어 놓기 · HTML 로 채우기가 모두 같은 판정을 받는다. */
export const SafeImage = Image.extend({
  parseHTML() {
    return [{ tag: "img[src]", getAttrs: (el) => (isEmbeddableImageSrc(el.getAttribute("src")) ? null : false) }];
  },
});

/** 붙여 넣은 HTML 에서 본문에 넣을 수 없는 그림을 걷는다. 걷은 것이 없으면 받은 글자를 그대로 돌려준다.
 *  `dropped` 는 걷은 그림의 수다 — 편집기가 그 수로 한 번 알린다. */
export function dropUnembeddableImages(html) {
  if (typeof html !== "string" || !/<img\b/i.test(html) || typeof DOMParser === "undefined") return { html, dropped: 0 };
  const doc = new DOMParser().parseFromString(html, "text/html");
  const bad = [...doc.querySelectorAll("img")].filter((img) => !isEmbeddableImageSrc(img.getAttribute("src")));
  if (!bad.length) return { html, dropped: 0 };
  for (const img of bad) img.remove();
  return { html: doc.body.innerHTML, dropped: bad.length };
}

export const EMPTY_DOC = { type: "doc", content: [] };

/* 서식 도구 — **묶음 다섯**(REAUDIT §15.4). 글자 단추 열다섯 개가 한 줄로 늘어서 있던
 * 자리를 아이콘 + 묶음으로 다시 짰다.
 *
 * ## 목록은 **렌더러가 아는 것**과 정확히 같다 (지시 22.6)
 *
 * 서버의 `BLOCK_NODES`·`MARKS`(app/knowledge/blocks.py)가 그 목록이다. 거기 없는 노드를
 * 만드는 버튼을 두면 사용자는 그 서식을 쓰고 저장했다가 **다시 열었을 때 사라진 것**을
 * 본다 — 저장이 실패하는 것도 아니라서 원인을 짐작할 수 없다. 밑줄과 체크 목록이 이번에
 * 들어온 이유가 그것이다: 서버 스키마가 `underline` 마크와 `taskList`/`taskItem` 노드를
 * 받아들이도록 먼저 넓어졌다(파생·차이 계산·색인까지 함께).
 *
 * 이모지는 이번에 **새로 만들지 않는다** — `EmojiPicker.jsx` 가 이미 있고
 * `BodyEditor.jsx`(티켓 본문)가 같은 부품을 쓴다. 두 편집기가 같은 이모지 표를 쓰는 것이
 * 자연스럽다(REAUDIT §15.4 point 4, 기능 집합을 맞춘다). 툴바에 이모지 여덟 개를 박아
 * 권하던 옛 자리와는 다르다 — 여기도 **눌러서 여는 고르개**뿐이다.
 *
 * 멘션은 아직 없다. 이 파일의 `Mention` 노드는 **서버가 이미 보낸 멘션을 그리고 그대로
 * 돌려주는 것**만 한다 — `@` 를 치면 사용자·티켓·문서를 검색해 주는 자동완성이 없다.
 * 그 자동완성 없이 버튼만 두면 「눌렀는데 아무 일도 안 난다」가 되므로, 자동완성이 생기는
 * 날 버튼도 같이 생긴다. */
function toolButtonSx(active) {
  /* 선택은 **잉크(글자색) + 옅은 배경 물듦**으로 말한다 — MUI 기본 회색 `Mui-selected`
   * 채움은 이 제품이 이미 버린 어휘다(`screens/Activity.jsx` 의 D-289 실측: 옅은 회색
   * 채움이 다른 자리의 회색 hover 와 섞여 「선택 안 됨」으로 오독됐다). 여기서는 Brand
   * 잉크(`brand.core`)로 색을 주고 채움은 그 잉크의 옅은 알파일 뿐, 새 회색을 안 만든다. */
  return (theme) => ({
    color: active ? theme.palette.brand.core : theme.palette.text.secondary,
    backgroundColor: active ? alpha(theme.palette.brand.core, 0.12) : "transparent",
    borderRadius: 1,
    "&:hover": {
      backgroundColor: active
        ? alpha(theme.palette.brand.core, 0.18)
        : alpha(theme.palette.text.primary, 0.06),
    },
  });
}

const TOOL_GROUPS = [
  {
    id: "format", label: "서식",
    tools: [
      { id: "bold", label: "굵게", Icon: FormatBoldRoundedIcon, run: (c) => c.toggleBold(), on: "bold" },
      { id: "italic", label: "기울임", Icon: FormatItalicRoundedIcon, run: (c) => c.toggleItalic(), on: "italic" },
      { id: "underline", label: "밑줄", Icon: FormatUnderlinedRoundedIcon, run: (c) => c.toggleUnderline(), on: "underline" },
      { id: "strike", label: "취소선", Icon: FormatStrikethroughRoundedIcon, run: (c) => c.toggleStrike(), on: "strike" },
      { id: "code", label: "코드", Icon: CodeRoundedIcon, run: (c) => c.toggleCode(), on: "code" },
    ],
  },
  {
    id: "paragraph", label: "문단",
    tools: [
      { id: "h1", label: "제목1", Icon: LooksOneRoundedIcon, run: (c) => c.toggleHeading({ level: 1 }), on: ["heading", { level: 1 }] },
      { id: "h2", label: "제목2", Icon: LooksTwoRoundedIcon, run: (c) => c.toggleHeading({ level: 2 }), on: ["heading", { level: 2 }] },
      { id: "h3", label: "제목3", Icon: Looks3RoundedIcon, run: (c) => c.toggleHeading({ level: 3 }), on: ["heading", { level: 3 }] },
      { id: "quote", label: "인용", Icon: FormatQuoteRoundedIcon, run: (c) => c.toggleBlockquote(), on: "blockquote" },
      { id: "codeBlock", label: "코드 블록", Icon: TerminalRoundedIcon, run: (c) => c.toggleCodeBlock(), on: "codeBlock" },
      { id: "rule", label: "구분선", Icon: HorizontalRuleRoundedIcon, run: (c) => c.setHorizontalRule(), on: null },
    ],
  },
  {
    id: "list", label: "목록",
    tools: [
      { id: "bullet", label: "글머리", Icon: FormatListBulletedRoundedIcon, run: (c) => c.toggleBulletList(), on: "bulletList" },
      { id: "ordered", label: "번호", Icon: FormatListNumberedRoundedIcon, run: (c) => c.toggleOrderedList(), on: "orderedList" },
      { id: "checklist", label: "체크 목록", Icon: ChecklistRoundedIcon, run: (c) => c.toggleTaskList(), on: "taskList" },
    ],
  },
  {
    id: "insert", label: "삽입",
    tools: [
      {
        id: "table", label: "표",
        Icon: TableChartRoundedIcon,
        run: (c) => c.insertTable({ rows: 3, cols: 3, withHeaderRow: true }),
        on: "table",
      },
    ],
  },
  {
    id: "history", label: "실행",
    tools: [
      { id: "undo", label: "되돌리기", Icon: UndoRoundedIcon, run: (c) => c.undo(), on: null },
      { id: "redo", label: "다시 실행", Icon: RedoRoundedIcon, run: (c) => c.redo(), on: null },
    ],
  },
];

function isActive(editor, on) {
  if (!editor || on == null) return false;
  return Array.isArray(on) ? editor.isActive(on[0], on[1]) : editor.isActive(on);
}

/* 링크 주소를 묻는 가벼운 팝오버 — `window.prompt` 대신 쓴다. 브라우저 기본 대화상자는
 * 이 저장소의 브라우저 자동화 지침이 다루기 어려워하는 대상이고(포커스를 페이지 밖으로
 * 던진다), 이름도 없고 테마도 안 탄다. 앵커에서 여는 작은 팝오버는 이 파일의 이웃
 * (`EmojiPicker.jsx`)과 `columnFilter.jsx` 가 이미 쓰는 관례라 새 패턴이 아니다.
 *
 * 이미 링크인 자리에서 열면 현재 주소가 입력칸에 채워진다(`initialHref`) — 링크를
 * 지우려고 전부 다시 치게 하지 않는다. */
function LinkPopover({ anchorEl, initialHref, onClose, onSubmit, onRemove }) {
  const [href, setHref] = React.useState(initialHref || "");
  const hrefId = React.useId();
  React.useEffect(() => {
    if (anchorEl) setHref(initialHref || "");
  }, [anchorEl, initialHref]);

  const submit = (e) => {
    e.preventDefault();
    const trimmed = href.trim();
    if (trimmed) onSubmit(trimmed);
  };

  // Paper 자체에는 이름을 안 준다 — 안의 `TextField` 라벨("링크 주소")과 겹치면
  // `getByLabelText` 류 조회가 둘을 다 찾아 어느 쪽인지 알 수 없다. `ColumnFilterPopover`
  // 도 같은 이유로 안의 필드 라벨 하나에만 기댄다.
  return (
    <Popover
      open={!!anchorEl}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{ paper: { sx: { p: 1.5 } } }}
    >
      {/* 라벨은 칸 위(`FieldLabel`)이고, 단추는 칸 바닥 줄에 선다. */}
      <Box component="form" onSubmit={submit} sx={{ display: "flex", gap: 1, alignItems: "flex-end", width: "20rem" }}>
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <FieldLabel htmlFor={hrefId}>링크 주소</FieldLabel>
          <TextField
            id={hrefId}
            autoFocus
            size="small"
            fullWidth
            placeholder="https://"
            value={href}
            onChange={(e) => setHref(e.target.value)}
          />
        </Box>
        {initialHref ? (
          <KitButton size="sm" onClick={onRemove}>
            삭제
          </KitButton>
        ) : null}
        <KitButton type="submit" size="sm" variant="primary">
          적용
        </KitButton>
      </Box>
    </Popover>
  );
}

/* 편집기 한 대.
 *
 * `value` 는 서버가 준 Block JSON 이고 `onChange` 는 그것과 같은 모양을 돌려준다.
 * 부르는 쪽이 저장 시점을 정한다 — 여기서 저장을 부르지 않는 이유는 `DragDrop.jsx` 가
 * 낙관적 갱신을 안 하는 이유와 같다: 언제가 진실인지는 부르는 쪽이 알아야 한다. */
/* 편집 본문의 바닥(rem) — 핸드오프 RULES §7 「본문 min-height 240」. 루트 16px 에서 240px 이다. */
const EDITOR_BODY_MIN_REM = 15;

export function BlockEditor({ value, onChange, readOnly = false, label = "본문", ariaLabel, onPickImage, fill = false }) {
  const name = ariaLabel || label;
  /* 편집기 설정은 처음 한 번 만들어지므로 알림 함수는 ref 로 넘긴다 — 붙여넣기 때 지금의 함수를 부른다. */
  const toast = useToast();
  const toastRef = React.useRef(toast);
  toastRef.current = toast;
  const editor = useEditor({
    editable: !readOnly,
    /* 🔴 편집 영역의 **접근 이름**은 contenteditable 자신이 들어야 한다.
     *
     * 예전에는 `<EditorContent aria-label>` 로 감싸는 `div` 에만 붙였는데, 스크린리더가
     * 읽는 것은 그 안의 `contenteditable` 이라 편집기가 이름 없는 입력 상자였다. 그러면
     * 「무엇을 고치는 자리인가」를 들을 방법이 없다 — 티켓 본문인지 문서 본문인지도.
     * `role="textbox"` 도 함께 적는다: `contenteditable` 의 암묵 role 은 브라우저마다
     * 다르고, 이름과 역할이 함께 있어야 시험도 화면도 같은 것을 짚는다. */
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-label": name,
        "aria-multiline": "true",
      },
      /* 붙여 넣은 그림 중 본문에 넣을 수 없는 것을 먼저 걷고, 걷었으면 한 번 알린다(`SafeImage` 머리 주석).
         말없이 버리면 사용자는 그림이 왜 사라졌는지 모른다. */
      transformPastedHTML: (html) => {
        const { html: kept, dropped } = dropUnembeddableImages(html);
        if (dropped) {
          toastRef.current(`붙여 넣은 그림 ${dropped}개는 본문에 넣지 못했습니다. 웹 주소로 열리는 그림만 넣을 수 있습니다.`, "warn");
        }
        return kept;
      },
    },
    extensions: [
      StarterKit.configure({
        // 링크는 StarterKit 밖이다(별도 확장) — 아래에서 따로 등록한다.
        heading: { levels: [1, 2, 3] },
      }),
      /* 밑줄·체크 목록(REAUDIT §15.4). 서버 스키마(app/knowledge/blocks.py)가 `underline`
       * 마크와 `taskList`/`taskItem` 노드를 받아들이도록 먼저 넓어진 뒤에야 여기 넣을 수
       * 있었다 — 순서를 바꾸면(먼저 버튼부터) 쓰고 저장했다가 다시 열었을 때 사라진다. */
      Underline,
      TaskList,
      /* `nested: true` — 체크 목록 항목 안에 체크 목록을 또 넣을 수 있게 한다(Tab 로
       * 들여쓰기). 서버도 이것을 막지 않는다: `taskItem` 은 `listItem` 과 같은 자리라
       * `NODE_CHILDREN` 에 제 나름의 제한이 없다(중첩 `bulletList` 를 담는 `listItem` 과
       * 정확히 같은 모양이다). */
      TaskItem.configure({ nested: true }),
      /* 링크. 자동으로는 안 만든다(`autolink`·`linkOnPaste` 모두 끔) — 링크는 아래
       * 도구모음의 「링크」 단추로 사용자가 명시적으로 만든다. `openOnClick` 도 끈다 —
       * 편집 중에 링크를 누르면 커서를 두는 대신 새 탭이 열려서, 그 자리를 고치려던
       * 사용자가 매번 방해받는다. 읽기 전용 화면(`BlockView`)은 이 설정과 무관하게 그대로
       * 눌러 이동한다 — TipTap 의 클릭 가로채기(`openOnClick`)는 편집 가능할 때만 동작하고,
       * 읽기 전용에서는 보통의 `<a>` 태그가 그 일을 그대로 한다.
       * `rel="noopener noreferrer nofollow"` 는 외부 문서로 이동할 때 그 문서가
       * `window.opener` 로 이 화면을 조작하지 못하게 막는다(reverse tabnabbing). */
      Link.configure({
        openOnClick: false,
        autolink: false,
        linkOnPaste: false,
        HTMLAttributes: { target: "_blank", rel: "noopener noreferrer nofollow" },
      }),
      /* 이미지와 표. 둘 다 TipTap 공식 **MIT** 확장이다 — Pro 확장은 상용이라 못 쓴다(D-198).
       *
       * 여기 없으면 서버가 보낸 이미지·표 노드를 편집기가 모르고, ProseMirror 는 모르는
       * 노드를 만나면 **그 자리를 통째로 버린다.** 화면에는 오류가 아니라 빈 자리가 뜨고,
       * 그 상태로 저장하면 본문에서 그림과 표가 실제로 사라진다.
       *
       * `allowBase64` 는 끈다. 서버가 `data:` 를 거절하고(app/knowledge/blocks.py), 이미지
       * 바이트는 우리 첨부 저장소에 넣기로 했다(D4) — 편집기가 만들 수 있게 두면 저장할 때만
       * 거절당하는 값을 사용자가 화면에서 먼저 보게 된다.
       *
       * 표는 크기 조절을 안 켠다. 지금 필요한 것은 **원본 표가 보이는 것**이고, 열 너비
       * 손잡이는 편집 기능이라 읽기 전용 화면에 아무것도 더하지 않는다. */
      SafeImage.configure({ inline: false, allowBase64: false }),
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
      /* 빈 문서에 안내 글자를 흐리게 얹는다 — 여백만 있으면 "여기가 편집 자리인가"부터
       * 헷갈린다. `showOnlyWhenEditable` 은 이 확장의 기본값이라 읽기 전용(`BlockView`)의
       * 빈 문서에는 안 뜬다 — 안 뜨는 것이 맞다, 볼 줄만 아는 화면에 "입력하세요"는
       * 거짓말이다. */
      Placeholder.configure({ placeholder: `${label} 내용을 입력하세요…` }),
      BlockId,
      Mention,
    ],
    content: value || EMPTY_DOC,
    onUpdate: ({ editor: e }) => onChange?.(e.getJSON()),
  }, [readOnly]);

  // 이모지 팝오버의 열림 자리(앵커). `null` 이면 닫힌 것으로 본다(`ColumnFilterPopover`
  // 와 같은 관례).
  const [emojiAnchor, setEmojiAnchor] = React.useState(null);
  /* 링크 팝오버 — 앵커에 더해 **누른 순간의 선택 범위**(`from`·`to`)를 함께 담는다.
   * 팝오버가 열려 있는 동안 포커스가 입력칸으로 옮겨 가고, 그동안 ProseMirror 의 실시간
   * 선택(`editor.state.selection`)은 그대로라는 보장이 없다 — 포커스가 편집기 밖으로
   * 나가면 브라우저 native selection 이 바뀌고, ProseMirror 가 그것을 좇다가 문서 전체를
   * 가리키는 `AllSelection` 으로 떨어지는 경우를 실측했다(빈 문서에서 특히 그렇다). 그래서
   * "무엇에 링크를 걸지"는 **누른 순간 한 번** 확정해 들고 있는다 — 적용할 때 다시
   * `editor.state.selection` 을 읽으면 이미 달라져 있을 수 있다. */
  const [linkPopover, setLinkPopover] = React.useState(null);

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

  /* ── 편집기 상자 (핸드오프 RULES §7 · 새 티켓 시안 · UI 3차 조합 계약 C-5) ─────────────────────────────
   *
   * 편집 중인 편집기는 **상자 하나**다: 1px 테두리 · 모서리 6 안에 도구 줄(함몰면 + 아래 실선)과 본문(바닥 240)이 붙어
   * 선다. 예전에는 도구 줄(면 없음) · 구분선 · 테두리 본문이 세 덩어리로 떨어져 판 위에 흩어졌고, 본문이 판 높이를 채울
   * 방법이 없었다. 새 티켓 · 문서 편집 · 티켓 본문이 같은 상자를 쓴다.
   *
   *   도구 줄  30 아이콘 단추 · 묶음 사이 1px 세로선 · 되돌리기와 다시 실행은 오른쪽 끝(빈 공간 뒤)
   *   본문     바닥 240, 도구 줄 아래 남는 높이를 채울 수 있다(`fill` — 부르는 쪽이 세로 flex 로 둘 때)
   *
   * 읽기 전용(`BlockView`)은 상자가 없다 — 본문 글만 그대로 선다. */
  const history = TOOL_GROUPS.find((g) => g.id === "history");
  const leading = TOOL_GROUPS.filter((g) => g.id !== "history");
  const renderTool = (tool) => {
    const active = isActive(editor, tool.on);
    return (
      <Tooltip key={tool.id} title={tool.label}>
        {/* 아이콘 하나만으로는 스크린리더에 이름이 없다 — `aria-label` 을
            따로 준다(Tooltip 의 title 은 마우스 사용자를 위한 것일 뿐
            접근 이름을 자동으로 만들어 주지 않는다). */}
        <IconButton
          size="small"
          type="button"
          aria-label={tool.label}
          aria-pressed={tool.on ? active : undefined}
          onClick={() => tool.run(editor.chain().focus()).run()}
          sx={toolButtonSx(active)}
        >
          <tool.Icon fontSize="small" />
        </IconButton>
      </Tooltip>
    );
  };

  return (
    <Box
      data-editor-box={readOnly ? undefined : ""}
      sx={readOnly ? undefined : {
        display: "flex", flexDirection: "column", minWidth: 0,
        border: 1, borderColor: "divider", borderRadius: `${RADIUS.sm}px`, overflow: "hidden",
        bgcolor: "background.plate",
        ...(fill ? { flex: "1 1 auto" } : null),
      }}
    >
      {!readOnly && (
        <>
          <Stack
            direction="row"
            spacing={0.25}
            role="toolbar"
            aria-label={`${label} 서식`}
            data-editor-toolbar=""
            sx={{
              flexWrap: "wrap", rowGap: 0.5, alignItems: "center",
              px: 1, py: 0.75, bgcolor: "background.inset", borderBottom: 1, borderColor: "divider",
            }}
          >
            {leading.map((group, index) => (
              <React.Fragment key={group.id}>
                {/* 묶음을 세로선으로 나눈다 — REAUDIT §15.4 이 이름 붙인 서식·문단·목록·삽입이다. 첫 묶음 앞에는 안 긋는다.
                    실행(되돌리기 · 다시 실행)은 선 대신 빈 공간 뒤 오른쪽 끝에 선다. */}
                {index > 0 ? <Divider orientation="vertical" flexItem sx={{ my: 0.75, mx: 0.5 }} /> : null}
                <Stack direction="row" spacing={0.25} aria-label={group.label} sx={{ alignItems: "center" }}>
                  {group.tools.map(renderTool)}
                  {group.id === "insert" ? (
                    <>
                      <Tooltip title="링크">
                        <IconButton
                          size="small"
                          type="button"
                          aria-label="링크"
                          aria-pressed={isActive(editor, "link")}
                          onClick={(e) => {
                            // 지금 선택을 여기서 한 번 확정해 둔다 — 팝오버가 열려 있는
                            // 동안 포커스가 입력칸으로 옮겨 가면 편집기의 실시간 선택이
                            // 바뀔 수 있다(LinkPopover 위 docstring).
                            const { from, to } = editor.state.selection;
                            setLinkPopover({
                              anchorEl: e.currentTarget,
                              from,
                              to,
                              initialHref: editor.getAttributes("link").href || "",
                            });
                          }}
                          sx={toolButtonSx(isActive(editor, "link"))}
                        >
                          <InsertLinkRoundedIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      {/* 이미지는 **문서에 파일을 붙이는 일**이라 부르는 쪽이 그 방법을 안다.
                          바이트를 본문에 넣지 않는다(`allowBase64: false`) — 우리 첨부
                          저장소에 넣고 주소만 본문에 남긴다(D4). 주소를 못 받으면 아무것도
                          안 넣는다. */}
                      {onPickImage ? (
                        <Tooltip title="이미지">
                          <IconButton
                            size="small"
                            type="button"
                            aria-label="이미지"
                            onClick={async () => {
                              const src = await onPickImage();
                              if (src) editor.chain().focus().setImage({ src }).run();
                            }}
                            sx={toolButtonSx(false)}
                          >
                            <InsertPhotoRoundedIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      ) : null}
                      <Tooltip title="이모지">
                        <IconButton
                          size="small"
                          type="button"
                          aria-label="이모지"
                          aria-haspopup="dialog"
                          aria-expanded={!!emojiAnchor}
                          onClick={(e) => setEmojiAnchor(e.currentTarget)}
                          sx={toolButtonSx(false)}
                        >
                          <InsertEmoticonRoundedIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </>
                  ) : null}
                </Stack>
              </React.Fragment>
            ))}
            {history ? (
              /* 실행 묶음은 줄의 오른쪽 끝이다 — 남는 폭을 먹는 칸 안에서 오른쪽에 붙는다. 빈 공간 칸을 따로 두면 도구 줄이
                 두 줄로 접힐 때(1366 새 티켓 편집기 605px) 빈 공간은 첫 줄에 남고 실행 묶음만 둘째 줄 왼쪽에 섰다. */
              <Box sx={{ flex: "1 0 auto", display: "flex", justifyContent: "flex-end" }}>
                <Stack direction="row" spacing={0.25} aria-label={history.label} sx={{ alignItems: "center" }}>
                  {history.tools.map(renderTool)}
                </Stack>
              </Box>
            ) : null}
          </Stack>
          <LinkPopover
            anchorEl={linkPopover?.anchorEl}
            initialHref={linkPopover?.initialHref || ""}
            onClose={() => setLinkPopover(null)}
            onSubmit={(href) => {
              const { from, to } = linkPopover;
              // 「글이 골라져 있었는가」는 `from !== to` 가 아니라 **그 사이에 실제 글자가
              // 있는가**로 본다 — 포커스가 팝오버 입력칸으로 옮겨 가는 사이 ProseMirror 의
              // 선택이 문서 전체를 가리키는 `AllSelection` 으로 떨어지는 경우를 실측했다
              // (빈 문서에서, `from`·`to` 가 0·2 처럼 서로 달라도 그 사이에 글자가 없다).
              // MUI Popover 의 포커스 관리와 ProseMirror 의 선택 추적이 만나는 자리라 실
              // 브라우저에서도 안 일어난다고 장담할 수 없다.
              const selectedText = editor.state.doc.textBetween(from, to, "\n");
              if (selectedText) {
                // 실제로 글이 선택돼 있었다 — 그 범위를 다시 세운 뒤(위 state docstring)
                // 링크를 씌운다. `extendMarkRange` 는 그 범위가 이미 링크 안이면 링크
                // 전체로 넓힌다(수정 자리).
                editor.chain().focus().setTextSelection({ from, to })
                  .extendMarkRange("link").setLink({ href }).run();
                setLinkPopover(null);
                return;
              }
              // 선택 없이 눌렀다 — 걸 글자가 없으니 주소 글자 자체를 링크 글로 넣는다.
              // `from` 이 안 노드(text)를 받을 수 있는 자리(문단 안)인지 먼저 본다 — 못
              // 받는 자리(문단이 하나도 없는 빈 문서의 0번 자리, 또는 위에서 말한 선택
              // 어긋남)에 그대로 꽂으면 ProseMirror 가 자리를 통째로 버려 조용히 아무 일도
              // 안 난다. 못 받으면 새 문단으로 감싸 문서 끝에 넣는다 — 문서 끝은 항상
              // 유효한 자리다.
              const linkText = { type: "text", text: href, marks: [{ type: "link", attrs: { href } }] };
              const canInsertInline = editor.state.doc.resolve(from).parent.isTextblock;
              if (canInsertInline) {
                editor.chain().focus().insertContentAt(from, linkText).run();
              } else {
                editor.chain().focus().insertContentAt(
                  editor.state.doc.content.size,
                  { type: "paragraph", content: [linkText] },
                ).run();
              }
              setLinkPopover(null);
            }}
            onRemove={() => {
              const { from, to } = linkPopover;
              editor.chain().focus().setTextSelection({ from, to })
                .extendMarkRange("link").unsetLink().run();
              setLinkPopover(null);
            }}
          />
          <EmojiPicker
            anchorEl={emojiAnchor}
            onClose={() => setEmojiAnchor(null)}
            onPick={(emoji) => {
              setEmojiAnchor(null);
              editor.chain().focus().insertContent(emoji).run();
            }}
            ariaLabel="문서에 넣을 이모지 고르기"
          />
        </>
      )}
      <Box
        data-editor-body={readOnly ? undefined : ""}
        sx={(theme) => ({
          ...KO_WORD_BREAK,
          /* 본문은 상자 안 도구 줄 아래다 — 테두리는 상자가 든다. 바닥 240(`EDITOR_BODY_MIN_REM`)이고, 상자가 남는 높이를
             받으면(`fill`) 본문이 그만큼 자라 편집 자리가 판 바닥까지 선다. 본문 어디를 눌러도 편집 자리가 잡히게
             ProseMirror 가 본문 높이를 채운다. */
          px: readOnly ? 0 : 2,
          py: readOnly ? 0 : 1.75,
          minHeight: readOnly ? 0 : `${EDITOR_BODY_MIN_REM}rem`,
          ...(readOnly ? null : { display: "flex", flexDirection: "column", flex: "1 1 auto" }),
          fontSize: FONT_SIZE.body,
          ...(readOnly ? null : { "& > div": { flex: "1 1 auto", display: "flex", flexDirection: "column" } }),
          "& .ProseMirror": { outline: "none", ...(readOnly ? { minHeight: 0 } : { flex: "1 1 auto" }) },
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
          /* 본문 이미지. `max-width` 를 안 걸면 원본 폭 그대로 나와서 칸을 넘고, 넘은
           * 만큼 화면 전체가 가로로 밀린다 — 문서 하나가 레이아웃을 깨는 모양이다. */
          "& .ProseMirror img": {
            display: "block",
            maxWidth: "100%",
            height: "auto",
            borderRadius: 4,
            marginBlock: "0.6em",
          },
          /* 표. `table-layout: fixed` 로 칸 너비를 칸 수로 나눈다 — 자동 배치는 긴 글이
           * 든 칸 하나가 표를 칸 밖으로 밀어낸다. 줄바꿈 규약은 본문과 같다(한글은 어절). */
          "& .ProseMirror table": {
            borderCollapse: "collapse",
            tableLayout: "fixed",
            width: "100%",
            marginBlock: "0.8em",
          },
          "& .ProseMirror th, & .ProseMirror td": {
            border: `1px solid ${theme.palette.divider}`,
            padding: "0.4em 0.6em",
            verticalAlign: "top",
            textAlign: "start",
          },
          "& .ProseMirror th": {
            background: alpha(theme.palette.text.primary, 0.04),
            fontWeight: FONT_WEIGHT.semibold,
          },
          // 칸 안의 문단은 위아래 여백을 안 준다. 주면 한 줄짜리 표가 두 배로 높아진다.
          "& .ProseMirror th > p, & .ProseMirror td > p": { margin: 0 },
          /* 체크 목록. TipTap 의 기본 렌더는 `<ul><li><label><input type=checkbox>…` 다
           * (`@tiptap/extension-task-item`) — 손대지 않으면 브라우저 기본 글머리 점이
           * 체크박스 옆에 겹쳐 나온다(REAUDIT §15.4). 점을 지우고 체크박스·글을 가로로
           * 나란히 둔다. */
          "& .ProseMirror ul[data-type='taskList']": {
            listStyle: "none",
            paddingLeft: 0,
            marginBlock: "0.6em",
          },
          "& .ProseMirror ul[data-type='taskList'] li": {
            display: "flex",
            alignItems: "flex-start",
            gap: "0.5em",
          },
          // 중첩된 체크 목록(`nested: true`)은 항목의 글 아래, 체크박스 폭만큼 들여써야
          // 부모 항목과 같은 세로줄에서 시작하지 않는다.
          "& .ProseMirror ul[data-type='taskList'] ul[data-type='taskList']": {
            marginBlock: "0.2em 0",
            paddingLeft: "1.5em",
          },
          "& .ProseMirror ul[data-type='taskList'] li > label": {
            display: "flex",
            alignItems: "center",
            marginTop: "0.15em",
            userSelect: "none",
          },
          "& .ProseMirror ul[data-type='taskList'] li > div": { flex: 1, minWidth: 0 },
          "& .ProseMirror ul[data-type='taskList'] li > div > p": { margin: 0 },
          "& .k-mention": {
            color: theme.palette.primary.main,
            fontWeight: FONT_WEIGHT.medium,
          },
        })}
      >
        <EditorContent editor={editor} />
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
