import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { FONT_SIZE, FONT_WEIGHT } from "./theme.js";

/* 마크다운 본문의 **미리보기**와 편집 표면의 **폭 규칙**.
 *
 * 예전에는 이 파일이 공용 본문 편집기이기도 했다. 그 편집기는 없어졌다 — 아래 주석 참고.
 * 지금 남은 것은 마크다운 문자열을 그대로 그리는 자리(주간 보고)가 쓰는 미리보기와,
 * 편집 표면을 감싸는 두 자리가 함께 쓰는 폭 헬퍼다. */

/* 🔴 `BODY_MAX_LINES = 100` 이 있었다. 백엔드 파서(`app/core/notion_blocks.py`)가 그만큼만
 * 읽던 시절의 짝이고, 그 상한은 Notion API 의 것이었다 — 밀어 넣을 곳이 없어져 파서도
 * 검증기도 더 이상 자르지 않는다. 본문은 길어질 수 있다. */

/* 편집 표면(툴바+입력 상자+미리보기)의 폭 — 이 컴포넌트를 감싸는 두 자리(새 티켓 설명의
 * MyTickets.jsx, 티켓/문서 본문 편집의 EditableBody.jsx)가 예전에는 각자 손으로 고정
 * rem/ch 상한(60rem, 78ch)을 박아 뒀다. 부모가 아무리 넓어져도 거기서 멈추니, 4K 등
 * 넓은 화면에서 편집기+미리보기가 폼/본문 열의 다른 부분보다 눈에 띄게 좁아 왼쪽으로
 * 쏠려 보였다.
 *
 * 이 편집기는 산문이 아니라 도구다(아래 BodyPreview 의 wide 설명 참고) — 읽기용 78ch 로
 * 묶을 이유가 없다. 그렇다고 무제한으로 늘리면, 자신을 담는 열 자체에 상한이 없는 자리
 * (티켓/문서 본문 열은 fr 트랙이라 위쪽 상한이 없다 — density.js BASELINE_TRACKS.detail)
 * 에서는 4K 화면의 입력 상자 한 줄이 3,000px 를 넘어 버린다. 그래서 컨테이너의 **실제
 * 폭**을 재서 충분히 넓어졌을 때만 멈춘다(round2 가 NT_FIELD_GRID 에 쓴 것과 같은
 * `@container` 관례) — 컨테이너가 이미 좁게 정해진 자리(예: 새 티켓 폼의 72rem 상한)에서는
 * 이 상한이 사실상 걸리지 않고 부모 폭을 그대로 따라간다.
 *
 * 두 자리가 같은 값을 쓰도록 여기서 한 번만 정의해 내보낸다 — 화면마다 다른 매직 넘버를
 * 새로 정하면 그 사이에서 또 어긋난다. */
export const EDITOR_WIDE_STOP_REM = 80;

/* `container-type` 은 조상에만 걸 수 있다 — 이 Box 로 편집 표면을 한 겹 더 감싸야
 * `editorSurfaceWidthSx` 의 `@container` 질의가 작동한다. */
export function editorContainerSx(containerName) {
  return { containerType: "inline-size", containerName };
}

/* 기본값은 100%(부모가 주는 만큼 그대로) — 컨테이너 질의를 못 알아듣는 브라우저는 이
 * 기본값으로 남는다(안전한 퇴화). 컨테이너 실측 폭이 EDITOR_WIDE_STOP_REM 을 넘어서면
 * 그때만 상한을 건다. */
export function editorSurfaceWidthSx(containerName) {
  return {
    width: "100%",
    [`@container ${containerName} (min-width: ${EDITOR_WIDE_STOP_REM}rem)`]: {
      maxWidth: `${EDITOR_WIDE_STOP_REM}rem`,
    },
  };
}

/* 🔴 **여기 마크다운 편집기가 있었다.**
 *
 * 글자 칩 열한 개(제목1·제목2·제목3·글머리·번호·체크·인용·코드·구분선·링크·이모지)로
 * 줄 맨 앞에 표식을 붙이는 편집기였고, 티켓 설명과 티켓 본문이 그것을 썼다. 굵게·기울임·
 * 밑줄·표·이미지가 없던 이유는 단추를 안 만들어서가 아니라 **저장할 자리가 없어서**였다 —
 * 본문 정본이 마크다운 문자열이었다.
 *
 * 지금은 티켓 본문도 문서와 같은 정본(Block JSON)을 쓰고, 두 곳 다 같은 편집기
 * (`ui/BlockEditor.jsx`, TipTap)로 고친다. 그래서 이 편집기는 소비처가 0 이 됐다.
 * 남는 것은 **편집 표면의 폭 규칙**(위 두 헬퍼)과 아래 **마크다운 미리보기**뿐이다 —
 * 미리보기는 주간 보고(`screens/ProjectWeekly.jsx`)가 마크다운 문자열을 그대로 그리는
 * 자리에서 계속 쓴다. */

/* wide=true 는 **편집 중 미리보기**용이다.
 * 기본값(78ch)은 '읽는 본문'의 줄 길이 상한이라 티켓 상세처럼 완성된 글을 볼 때 맞다.
 * 그런데 편집기 안에서는 입력 상자가 full width 인데 미리보기만 78ch 라, 두 상자의 폭이
 * 달라 "정렬이 어긋나 보인다"(1920 캡처에서 960px vs 675px). 편집 화면에서는 무엇을 쳤는지와
 * 어떻게 보일지를 **나란히 대조**하는 것이 목적이라 폭이 같아야 한다. */
export function BodyPreview({ text, wide = false }) {
  /* 🔴 여기 100줄에서 자르는 규칙과 「이후 N줄은 저장되지 않습니다」 경고가 있었다.
     서버 파서가 그만큼만 읽어서 「미리보기가 저장 결과보다 길어지지 않게」 맞춰 둔
     것이었는데, **그 파서가 더 이상 안 자른다** — 100줄·1900자는 Notion 으로 밀어 넣던
     시절의 상한이고 밀어 넣을 곳이 없어졌다. 안 잘리는데 잘린다고 말하면 안 된다. */
  const lines = (text || "").split("\n");
  const blocks = [];
  let list = null;
  const flush = () => { if (list) { blocks.push(list); list = null; } };
  /* 코드 구간 안에서는 서식을 **해석하지 않는다** — 서버 파서와 같은 규칙이다
     (`app/core/notion_blocks.py`). 두 곳이 갈라지면 사용자가 본 미리보기와 저장 결과가
     다른데, 그 어긋남은 저장한 뒤에야 보인다. */
  let code = null;
  lines.forEach((ln) => {
    const s = ln.trim();
    if (s.startsWith("```")) {
      if (code === null) { flush(); code = []; }
      else { blocks.push({ type: "code", text: code.join("\n") }); code = null; }
      return;
    }
    if (code !== null) { code.push(ln); return; }
    if (!s) { flush(); blocks.push({ type: "spacer" }); return; }
    if (s === "---" || s === "___" || s === "***") { flush(); blocks.push({ type: "hr" }); return; }
    if (s.startsWith("### ")) { flush(); blocks.push({ type: "h3", text: s.slice(4) }); return; }
    if (s.startsWith("## ")) { flush(); blocks.push({ type: "h2", text: s.slice(3) }); return; }
    if (s.startsWith("# ")) { flush(); blocks.push({ type: "h1", text: s.slice(2) }); return; }
    // **글머리보다 먼저 본다** — 체크 목록도 `- ` 로 시작한다.
    const todo = s.match(/^[-*]\s+\[([ xX])\]\s*(.*)$/);
    if (todo) {
      if (!list || list.type !== "todo") { flush(); list = { type: "todo", items: [] }; }
      list.items.push({ text: todo[2], checked: todo[1].toLowerCase() === "x" }); return;
    }
    if (s.startsWith("- ") || s.startsWith("* ")) {
      if (!list || list.type !== "ul") { flush(); list = { type: "ul", items: [] }; }
      list.items.push(s.slice(2)); return;
    }
    const m = s.match(/^(\d+)\.\s+(.*)$/);
    if (m) {
      if (!list || list.type !== "ol") { flush(); list = { type: "ol", items: [] }; }
      list.items.push(m[2]); return;
    }
    if (s.startsWith("> ")) { flush(); blocks.push({ type: "quote", text: s.slice(2) }); return; }
    flush();
    blocks.push({ type: "p", text: ln });
  });
  flush();
  // 닫히지 않은 울타리도 코드로 보여 준다 — 서버가 같은 판단을 한다.
  if (code !== null) blocks.push({ type: "code", text: code.join("\n") });

  const shell = {
    border: 1, borderColor: "divider", borderRadius: 2, p: 2,
    bgcolor: "background.default",
    /* 읽는 본문은 줄 길이를 제한한다 — 4K에서 한 줄이 3,000px가 되면 읽을 수 없다.
       편집 중 미리보기(wide)는 위 입력 상자와 폭을 맞춘다(위 주석 참조). */
    maxWidth: wide ? "100%" : "78ch",
  };

  if (blocks.length === 0) {
    /* REAUDIT C19 — 이 자리는 "빈 회색 띠"로 읽혔다. 글자는 있었지만(아래 문장) 상자가
       한 줄 높이라 테두리 안쪽 여백만 있는 얇은 띠로 보이고, 눈이 스치면 안내문이 있는지도
       모른다. 안내 상자라는 것을 실제로 알아보게 최소 높이를 주고 가운데로 모은다 — 다른
       빈 자리(EmptyState)가 이미 쓰는 "여기에 무엇이 올지 알려준다"는 원칙을 이 작은
       자리에도 지킨다(전체 EmptyState 부품은 이 편집기 폭에 비해 과하다). */
    return (
      <Box
        sx={{
          ...shell, color: "text.secondary", fontSize: FONT_SIZE.body,
          minHeight: "4rem", display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center",
        }}
      >
        본문을 입력하면 실제 모양이 여기에 보입니다.
      </Box>
    );
  }
  return (
    <Box sx={{ ...shell, display: "grid", gap: 0.5 }}>
      {blocks.map((b, i) => {
        if (b.type === "spacer") return <Box key={i} sx={{ height: "0.5rem" }} aria-hidden="true" />;
        if (b.type === "hr") return <Divider key={i} sx={{ my: 1 }} />;
        if (b.type === "h1") return <Typography key={i} variant="h6" component="h2" sx={{ mt: 1 }}>{b.text}</Typography>;
        if (b.type === "h2") return <Typography key={i} component="h3" sx={{ fontWeight: FONT_WEIGHT.extrabold, fontSize: FONT_SIZE.sectionTitle, mt: 1 }}>{b.text}</Typography>;
        if (b.type === "h3") return <Typography key={i} component="h4" sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body, mt: 0.5 }}>{b.text}</Typography>;
        if (b.type === "ul") return <Box component="ul" key={i} sx={{ m: 0, pl: 3 }}>{b.items.map((it, j) => <li key={j}>{it}</li>)}</Box>;
        if (b.type === "ol") return <Box component="ol" key={i} sx={{ m: 0, pl: 3 }}>{b.items.map((it, j) => <li key={j}>{it}</li>)}</Box>;
        if (b.type === "todo") {
          return (
            <Box component="ul" key={i} sx={{ m: 0, pl: 0, listStyle: "none" }}>
              {b.items.map((it, j) => (
                <Box component="li" key={j} sx={{ display: "flex", gap: 1, alignItems: "baseline" }}>
                  {/* 상세 화면(`ui/DocBody.jsx`)이 쓰는 것과 **같은 글리프**다. 미리보기와
                      실제 화면이 다른 모양이면 미리보기가 미리보기가 아니다. */}
                  <Box component="span" aria-hidden="true">{it.checked ? "☑" : "☐"}</Box>
                  <Box component="span">{it.text}</Box>
                </Box>
              ))}
            </Box>
          );
        }
        if (b.type === "quote") {
          return (
            <Box
              component="blockquote" key={i}
              sx={{ my: 1, ml: 0, pl: 2, borderLeft: 3, borderColor: "primary.light", color: "text.secondary", fontStyle: "italic" }}
            >
              {b.text}
            </Box>
          );
        }
        if (b.type === "code") {
          return (
            <Box
              component="pre" key={i}
              sx={{
                my: 1, p: 1.5, borderRadius: 2, border: 1, borderColor: "divider", bgcolor: "action.hover",
                overflowX: "auto", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                fontSize: FONT_SIZE.bodySm, lineHeight: 1.6,
              }}
            >
              {b.text}
            </Box>
          );
        }
        return <Typography key={i} variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{b.text}</Typography>;
      })}
    </Box>
  );
}
