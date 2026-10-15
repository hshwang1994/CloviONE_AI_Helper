import React from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import KeyboardDoubleArrowLeftRoundedIcon from "@mui/icons-material/KeyboardDoubleArrowLeftRounded";
import KeyboardDoubleArrowRightRoundedIcon from "@mui/icons-material/KeyboardDoubleArrowRightRounded";
import OpenInFullRoundedIcon from "@mui/icons-material/OpenInFullRounded";
import { useLocation, useNavigate } from "react-router-dom";
import { Button, EmptyState, Skeleton } from "../ui/kit.jsx";
import { APPBAR_HEIGHT, BREAKPOINTS, FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import { MascotPose } from "../ui/Mascot.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { useChat } from "../screens/useChat.js";
import { QUICK_PROMPTS } from "../screens/chat-helpers.js";
import { Composer } from "../screens/chat/Composer.jsx";
import { MessageList } from "../screens/chat/MessageList.jsx";
import { AssistantUnavailable } from "../screens/chat/WelcomeStatus.jsx";
import { SCREEN_SUGGESTIONS, screenContextLine, screenTargetFor } from "../screens/chat/screenContext.js";
import { assistantOf, useAiStatus } from "../lib/useAiStatus.js";
import { useAuth } from "./auth.jsx";

/* 클로비 패널 — **모달이 아니다**(D-557).
 *
 * 예전에는 MUI temporary `Drawer` 였다. 모달이라 백드롭이 본문을 덮고 초점을 가두며 `body` 스크롤을 잠갔는데, 그 잠금이
 * `body` 에 `overflow:hidden` + `padding-right:<스크롤바 폭>` 을 넣어 스크롤바 자리가 빈 띠로 남고 고정 머리와 본문이
 * 어긋났다 — 「패널을 열면 오른쪽에 여백이 생기고 화면이 왼쪽으로 밀린다」가 그것이다. 패널을 열어도 보던 화면은 그대로
 * 쓸 수 있어야 한다(물어볼 대상이 그 화면에 있다).
 *
 * 그래서 머리 아래 오른쪽에 **고정된 측면 판**(`position:fixed`)이다. 본문의 폭 · 스크롤 · 여백을 건드리지 않고, 백드롭이
 * 없으며, 초점을 가두지 않는다. 열릴 때 입력 칸으로 초점이 가고, 닫히면 열었던 자리로 돌아간다. Esc 는 판 안에서만 닫는다.
 * 폭은 460(펼치면 720), 600 미만에서는 전체 폭이다. 모달(1300) · 토스트(1400) 아래, 상단바(1201) 바로 위(1202)다.
 *
 * 닫아도 **마운트는 유지**한다(`display:none`) — 언마운트하면 물어본 내용이 사라지고 다시 열었을 때 「아까 뭐라고 했더라」가
 * 된다. 대화 machinery 는 `useChat()` 그대로이고(전송 · 폴링 · 재시도 · 점검 · 속도 제한을 두 벌로 만들지 않는다), 입력창과
 * 말풍선 목록은 전체 화면 `/chat` 과 **같은 부품**(`Composer` · `MessageList`)이다.
 *
 * `/chat` 전체 화면은 남는다 — 긴 대화 · 대화 목록 관리 · 출처 레일은 패널 폭에 들어가지 않는다. */

export const PANEL_WIDTH = "28.75rem";
export const PANEL_WIDTH_WIDE = "45rem";
export const PANEL_WIDE_KEY = "clovi.panel.wide";

/* 대상이 없는 화면의 제안 — 전체 화면 AI 도우미의 시작 예시 앞쪽 넷과 같다(같은 일을 다른 말로 약속하지 않는다). */
const SUGGESTIONS = QUICK_PROMPTS.slice(0, 4);

/* PA-RC-0020: 진입점을 헤더 칩 하나로 모으면서 전역 단축키가 필요해졌다 — `CommandPalette.jsx` 의 Ctrl/Cmd+K 와 같은 모양.
 * `Ctrl+/`(Cmd+/) 다 — K 는 팔레트가 쓰고, 한 글자 단축키는 입력창에 그 글자를 치는 것과 구별이 안 된다. */
export function useAssistantHotkey(setOpen, enabled = true) {
  React.useEffect(() => {
    // AI 도우미를 쓸 수 없는 사람에게는 단축키도 없다(D-538) — 열어 봐야 403 이다.
    if (!enabled) return undefined;
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen, enabled]);
}

function readWide() {
  try { return window.localStorage.getItem(PANEL_WIDE_KEY) === "1"; } catch { return false; }
}

export function AssistantPanel({ open, onClose }) {
  const nav = useNavigate();
  const loc = useLocation();
  const auth = useAuth();
  const me = (auth && auth.data) || null;
  const target = screenTargetFor(loc.pathname);
  /* 열려 있을 때만 붙여넣기를 가져간다 — 안 그러면 보이지도 않는 입력창이 앱 전체의 Ctrl+V 를 삼킨다. */
  // AI-32: 처음 열릴 때까지 ai-quota · conversations 쿼리를 미루고, 한 번 열리면 계속 켜 둔다.
  const [everOpened, setEverOpened] = React.useState(!!open);
  React.useEffect(() => { if (open) setEverOpened(true); }, [open]);
  const chat = useChat({ pasteEnabled: !!open, screenContext: target, dataEnabled: everOpened });
  const aiStatus = useAiStatus({ enabled: everOpened });
  const assistant = assistantOf(aiStatus);
  const unavailable = !!assistant && !assistant.available;
  const suggestions = target ? SCREEN_SUGGESTIONS[target.kind] : SUGGESTIONS;
  const hasThread = chat.items.length > 0;
  const [wide, setWide] = React.useState(readWide);
  const panelRef = React.useRef(null);
  const openerRef = React.useRef(null);

  /* 초점 — 열릴 때 입력 칸으로, 닫히면 열었던 자리(클로비 단추)로. 모달의 초점 가둠은 없다. */
  React.useEffect(() => {
    if (open) {
      openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const el = chat.textareaRef.current;
      if (el && !el.disabled) el.focus({ preventScroll: true });
    } else if (openerRef.current && document.contains(openerRef.current)) {
      openerRef.current.focus({ preventScroll: true });
      openerRef.current = null;
    }
    // 열림 · 닫힘에만 반응한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function toggleWide() {
    setWide((v) => {
      const next = !v;
      try { window.localStorage.setItem(PANEL_WIDE_KEY, next ? "1" : "0"); } catch { /* 저장 못 해도 동작은 같다 */ }
      return next;
    });
  }

  // 답을 기다리는 동안의 진행 문구 — 서버가 사용자 메시지에 적는다(`structured.progress`, D-535).
  const progressLabel = chat.lastMsg && chat.lastMsg.role === "user" && chat.lastMsg.structured && chat.lastMsg.structured.progress
    ? chat.lastMsg.structured.progress.label : null;

  const faces = {
    assistant: <MascotPose mode={chat.busy ? "thinking" : "listening"} place="chatBubble" decorative />,
    user: <UserAvatar person={me} name={me && me.display_name} size="md" />,
  };

  const empty = unavailable ? (
    <AssistantUnavailable assistant={assistant} layout="card" />
  ) : (
    <Box sx={{ display: "grid", gap: 1.5 }}>
      {/* 대화가 없는 패널은 판 하나가 빈 자리다 — 판 빈 상태(card)이고 클로비는 판 계약 크기(72)다(D-485). */}
      <EmptyState
        layout="card"
        icon={<MascotPose mode="listening" place="emptyCard" decorative />}
        title="무엇을 도와드릴까요?"
        help={target ? screenContextLine(target) : "문서, 티켓, 프로젝트, 결재, 알림, 회의록을 내 권한 안에서 찾아 답합니다. 팀 채팅 대화는 찾지 않습니다."}
      />
      {/* 제안 칩 — 빈 화면에서 무엇을 물어볼 수 있는지 보여 준다. 대화가 시작되면 비켜 준다. */}
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, justifyContent: "center" }}>
        {suggestions.map((s) => (
          <Button key={s} size="sm" onClick={() => chat.prefillFromPrompt(s)}>{s}</Button>
        ))}
      </Box>
      {chat.thread && chat.thread.isLoading ? <Skeleton lines={2} /> : null}
    </Box>
  );

  return (
    <Box
      ref={panelRef}
      component="aside"
      role="complementary"
      aria-label="클로비 AI 도우미"
      data-assistant-panel={open ? "open" : "closed"}
      data-assistant-wide={wide ? "" : undefined}
      hidden={!open}
      onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}
      sx={(t) => ({
        position: "fixed", right: 0, bottom: 0,
        top: `${APPBAR_HEIGHT.xs}px`,
        [`@media (min-width:${BREAKPOINTS.xxl}px)`]: { top: `${APPBAR_HEIGHT.xxl}px` },
        [`@media (min-width:${BREAKPOINTS.uhd}px)`]: { top: `${APPBAR_HEIGHT.uhd}px` },
        width: { xs: "100%", sm: wide ? PANEL_WIDTH_WIDE : PANEL_WIDTH },
        maxWidth: "100vw",
        zIndex: t.zIndex.drawer + 2,
        display: open ? "flex" : "none", flexDirection: "column",
        bgcolor: "background.paper", color: "text.primary",
        borderLeft: 1, borderColor: "divider",
        boxShadow: t.shadows[8],
        "&[hidden]": { display: "none" },
      })}
    >
      {/* 머리 */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.25, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
        <MascotPose mode={chat.busy ? "thinking" : "listening"} place="assistantHead" decorative />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.bold, lineHeight: 1.2 }}>클로비</Typography>
          <Typography sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {/* 상태 한 줄 — 기다리는 중이면 서버의 진행 문구, 아니면 짧은 사실(머리의 단추 넷 옆에 설 자리가 좁다). */}
            {chat.busy ? (progressLabel || "답변을 정리하고 있습니다.") : "질문을 기다리고 있습니다."}
          </Typography>
        </Box>
        {hasThread ? (
          <Tooltip title="새 대화">
            <IconButton
              aria-label="새 대화" size="small"
              onClick={() => {
                chat.clearDraft();
                chat.setComposingNew(true);
                chat.setCid(null);
                chat.textareaRef.current && chat.textareaRef.current.focus();
              }}
            >
              <AddRoundedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        ) : null}
        <Tooltip title={wide ? "좁게 보기" : "넓게 보기"}>
          <IconButton aria-label={wide ? "좁게 보기" : "넓게 보기"} aria-pressed={wide} size="small" onClick={toggleWide}
            sx={{ display: { xs: "none", sm: "inline-flex" } }}>
            {wide ? <KeyboardDoubleArrowRightRoundedIcon fontSize="small" /> : <KeyboardDoubleArrowLeftRoundedIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <Tooltip title="전체 화면으로 열기">
          <IconButton aria-label="전체 화면으로 열기" size="small" onClick={() => { onClose(); nav(chat.cid ? "/chat/" + chat.cid : "/chat"); }}>
            <OpenInFullRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <IconButton aria-label="AI 도우미 닫기" size="small" onClick={onClose}>
          <CloseRoundedIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* 문맥 줄 — 지금 보는 대상이 있을 때만 선다(그때만 서버가 그 대상을 싣는다). */}
      {target ? (
        <Box sx={{
          px: 2, py: 1, fontSize: FONT_SIZE.bodySm, flexShrink: 0,
          bgcolor: (t) => alpha(t.palette.primary.main, 0.06), borderBottom: 1, borderColor: "divider",
        }}>
          {screenContextLine(target)}
        </Box>
      ) : null}

      {/* 대화 — 자기 스크롤 칸. */}
      <MessageList chat={chat} variant="panel" empty={empty} progressLabel={progressLabel} faces={faces} />

      {/* 입력 — 아래 고정. */}
      <Box sx={{ borderTop: 1, borderColor: "divider", p: 1.5, flexShrink: 0, bgcolor: "background.paper" }}>
        <Composer
          chat={chat} unavailable={unavailable} assistant={assistant}
          ariaLabel="클로비에게 질문" placeholder="클로비에게 질문하세요"
          showUnavailableNotice={hasThread}
        />
      </Box>
    </Box>
  );
}
