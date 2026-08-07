import React, { useRef } from "react";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import MuiButton from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";

/* 공용 본문 편집기 — 새 문서와 새 티켓 설명이 같은 서식(제목/글머리/번호/구분선/이모지)과
 * 라이브 미리보기를 쓴다. 서식 규칙은 백엔드 app/core/notion_blocks.py(markdown_to_blocks)와
 * 같아야 미리보기와 실제 저장 결과가 어긋나지 않는다. 서식 도구는 커서가 있는 '줄 맨 앞'에 표식을 붙인다.
 *
 * 2026-08 재설계: 마크업을 MUI로 옮겼다. 예전에는 `k-input docs-body-text` 같은 legacy 클래스에
 * 기대고 있었는데, 이 편집기는 MUI 폼 필드들 사이에 끼어 있어 혼자만 옛 모양으로 남아 있었다.
 * 캐럿 조작·미리보기 규칙은 한 줄도 바꾸지 않았다 — 그건 백엔드 파서와 맞춰 둔 계약이다. */

const BODY_EMOJIS = ["✅", "📌", "⚠️", "🔹", "👉", "🎯", "🎉", "💡"];
/* 백엔드 app/core/notion_blocks.py 의 MAX_BLOCKS 와 같은 값이다. 프런트에 두 번 적지 않으려고
 * 내보낸다 — 티켓 본문 편집(TicketBody.jsx)은 이 상한을 넘으면 저장 자체를 막는다. */
export const BODY_MAX_LINES = 100;

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

/* label: 입력 상자의 **접근 이름**이다.
 *
 * 왜 필요한가: 이 편집기가 곧 '본문 편집' 그 자체인 자리(티켓 본문·문서 본문)에서는 화면에
 * 딸린 <label> 이 없어, 스크린리더가 이름 없는 여러 줄 입력으로 읽었다 — "편집" 한 마디뿐이라
 * 무엇을 쓰는 칸인지 알 수 없다. 이 앱에서 가장 많이 쓰는 편집 표면이 그 상태였다.
 *
 * 넘기지 않으면 아무 것도 붙이지 않는다. 새 티켓·새 문서 폼은 화면에 보이는 <label htmlFor>
 * 로 이미 이름을 주고 있어서, 여기서 제 이름을 우기면 **보이는 라벨과 낭독되는 이름이 갈린다**. */
export function BodyEditor({ id, value, onChange, rows = 12, placeholder, label }) {
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

  /* 카드 배경(흰색)과 구별되는 옅은 표면 — theme.js 의 background.surface2 토큰을 그대로
   * 쓴다(표 머리·칸반 열이 이미 쓰는 것과 같은 위계). 예전에는 `variant="outlined"
   * color="inherit"` 라 배경이 투명이었고, 이모지 IconButton 은 배경 자체가 없어 흰 Card
   * 위에서 버튼 경계가 잘 안 보인다는 지적이 있었다. */
  const fmtBtn = {
    minWidth: 0, px: 1.5, minHeight: 32, fontSize: "0.8125rem",
    bgcolor: "background.surface2",
    borderColor: "divider",
    "&:hover": { bgcolor: (theme) => alpha(theme.palette.text.primary, 0.08), borderColor: "divider" },
  };
  const emojiBtn = {
    minWidth: 32, minHeight: 32, fontSize: "1rem",
    bgcolor: "background.surface2",
    border: "1px solid",
    borderColor: "divider",
    "&:hover": { bgcolor: (theme) => alpha(theme.palette.text.primary, 0.08) },
  };

  return (
    <>
      <Box
        role="group"
        aria-label={label ? label + " 서식 도구" : "본문 서식"}
        sx={{ display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap", mb: 1 }}
      >
        <MuiButton size="small" variant="outlined" color="inherit" sx={fmtBtn} onClick={() => prefixLine("## ")}>제목</MuiButton>
        <MuiButton size="small" variant="outlined" color="inherit" sx={fmtBtn} onClick={() => prefixLine("- ")}>글머리</MuiButton>
        <MuiButton size="small" variant="outlined" color="inherit" sx={fmtBtn} onClick={() => prefixLine("1. ")}>번호</MuiButton>
        <MuiButton size="small" variant="outlined" color="inherit" sx={fmtBtn} onClick={insertDivider}>구분선</MuiButton>
        <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />
        {BODY_EMOJIS.map((em) => (
          <IconButton
            key={em}
            size="small"
            aria-label={"이모지 " + em}
            onClick={() => insertAtCursor(em + " ")}
            sx={emojiBtn}
          >
            {em}
          </IconButton>
        ))}
      </Box>
      <TextField
        id={id}
        inputRef={ref}
        multiline
        minRows={rows}
        fullWidth
        size="small"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        /* placeholder 는 이름이 아니다 — 글자를 치는 순간 사라지고, 브라우저·리더에 따라
           아예 안 읽힌다. 이름은 label 로만 준다. */
        slotProps={{ htmlInput: label ? { "aria-label": label } : {} }}
      />
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2, mb: 0.5, fontWeight: 700 }}>
        미리보기
      </Typography>
      <BodyPreview text={value} wide />
    </>
  );
}

/* 본문 미리보기 — markdown_to_blocks와 같은 규칙으로 렌더(빈 줄=간격, 100줄 상한, 초과 경고).
 * 사용자 입력이므로 React가 기본 textContent 렌더(불변 §6 XSS 없음). */
/* wide=true 는 **편집 중 미리보기**용이다.
 * 기본값(78ch)은 '읽는 본문'의 줄 길이 상한이라 티켓 상세처럼 완성된 글을 볼 때 맞다.
 * 그런데 편집기 안에서는 입력 상자가 full width 인데 미리보기만 78ch 라, 두 상자의 폭이
 * 달라 "정렬이 어긋나 보인다"(1920 캡처에서 960px vs 675px). 편집 화면에서는 무엇을 쳤는지와
 * 어떻게 보일지를 **나란히 대조**하는 것이 목적이라 폭이 같아야 한다. */
export function BodyPreview({ text, wide = false }) {
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

  const shell = {
    border: 1, borderColor: "divider", borderRadius: 2, p: 2,
    bgcolor: "background.default",
    /* 읽는 본문은 줄 길이를 제한한다 — 4K에서 한 줄이 3,000px가 되면 읽을 수 없다.
       편집 중 미리보기(wide)는 위 입력 상자와 폭을 맞춘다(위 주석 참조). */
    maxWidth: wide ? "100%" : "78ch",
  };

  if (blocks.length === 0) {
    return (
      <Box sx={{ ...shell, color: "text.secondary", fontSize: "0.875rem" }}>
        본문을 입력하면 실제 모양이 여기에 보입니다.
      </Box>
    );
  }
  return (
    <Box sx={{ ...shell, display: "grid", gap: 0.5 }}>
      {blocks.map((b, i) => {
        if (b.type === "spacer") return <Box key={i} sx={{ height: "0.5rem" }} aria-hidden="true" />;
        if (b.type === "hr") return <Divider key={i} sx={{ my: 1 }} />;
        if (b.type === "h1") return <Typography key={i} variant="h6" sx={{ mt: 1 }}>{b.text}</Typography>;
        if (b.type === "h2") return <Typography key={i} sx={{ fontWeight: 780, fontSize: "1rem", mt: 1 }}>{b.text}</Typography>;
        if (b.type === "h3") return <Typography key={i} sx={{ fontWeight: 700, fontSize: "0.9375rem", mt: 0.5 }}>{b.text}</Typography>;
        if (b.type === "ul") return <Box component="ul" key={i} sx={{ m: 0, pl: 3 }}>{b.items.map((it, j) => <li key={j}>{it}</li>)}</Box>;
        if (b.type === "ol") return <Box component="ol" key={i} sx={{ m: 0, pl: 3 }}>{b.items.map((it, j) => <li key={j}>{it}</li>)}</Box>;
        return <Typography key={i} variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{b.text}</Typography>;
      })}
      {truncated ? (
        <Typography variant="caption" color="warning.main" sx={{ mt: 1 }}>
          이후 {raw.length - BODY_MAX_LINES}줄은 저장되지 않습니다(최대 {BODY_MAX_LINES}줄).
        </Typography>
      ) : null}
    </Box>
  );
}
