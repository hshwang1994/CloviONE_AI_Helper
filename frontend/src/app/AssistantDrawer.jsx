import React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import InputBase from "@mui/material/InputBase";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import OpenInFullRoundedIcon from "@mui/icons-material/OpenInFullRounded";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import { useLocation, useNavigate } from "react-router-dom";
import { Button, Skeleton } from "../ui/kit.jsx";
import { MascotPose } from "../ui/Mascot.jsx";
import { useChat } from "../screens/useChat.js";

/* 클로비 AI 드로어 — 사용자 지적 Q2.
 *
 * 예전에는 클로비를 누르는 세 자리(상단바 버튼, 사이드바 카드, 우하단 FAB)가 전부
 * `navigate("/chat")` 이었다. 티켓을 보다가 물어보려고 누르면 **보던 화면이 사라진다** —
 * 물어볼 대상이 화면에 있는데 그 화면을 떠나야 하는 구조였다.
 *
 * 이제 오른쪽에서 드로어가 열린다. 하던 화면은 뒤에 그대로 있고, 드로어 머리에 **지금 보고
 * 있는 화면 이름**이 뜬다("현재 문맥"). 기준 목업의 `.ai-drawer` 와 같은 구조다:
 * 머리 + 문맥 줄 + 대화 + 제안 칩 + 컴포저.
 *
 * `/chat` 전체 화면은 **남긴다**. 긴 대화, 대화 목록 관리, 결과 카드 패널은 드로어 폭에
 * 들어가지 않는다. 드로어 머리의 '전체 화면' 버튼이 지금 대화 그대로 그리로 넘긴다.
 *
 * 대화 machinery 는 `useChat()` 을 그대로 쓴다 — 전송·폴링·재시도·점검모드·레이트리밋
 * 처리를 여기서 다시 쓰면 두 벌이 되고, 한쪽만 고쳐지는 순간 어긋난다. */

const WIDTH = { xs: "100%", sm: "28.75rem" };  // 기준: min(460px, 100vw)

const SUGGESTIONS = [
  "현재 화면의 핵심 내용을 요약해 줘",
  "우선 처리할 다음 작업을 추천해 줘",
  "관련 문서를 찾아 줘",
  "이번 주 마감인 티켓 알려줘",
];

/* 지금 어느 화면인지. 사이드바 라벨과 같은 말을 쓴다 — 드로어가 "현재 문맥: 내 티켓" 이라고
 * 하는데 사이드바에는 "티켓 목록" 이라고 적혀 있으면 같은 곳을 가리키는지 알 수 없다. */
const ROUTE_TITLES = [
  [/^\/$|^\/me$/, "오늘의 업무"],
  [/^\/my-tickets/, "내 티켓"],
  [/^\/unassigned/, "미할당 티켓"],
  [/^\/team-tickets/, "팀 티켓"],
  [/^\/new-ticket/, "새 티켓"],
  [/^\/tickets\//, "티켓 상세"],
  [/^\/sprint/, "스프린트 회의"],
  [/^\/team-docs\/trash/, "문서 휴지통"],
  [/^\/team-docs\//, "문서 상세"],
  [/^\/team-docs/, "문서"],
  [/^\/chat-rooms/, "채팅방"],
  [/^\/board\//, "게시글"],
  [/^\/board/, "자유게시판"],
  [/^\/ideas/, "기능 개선 제안"],
  [/^\/games/, "놀이"],
  [/^\/trash/, "휴지통"],
  [/^\/profile/, "내 프로필"],
  [/^\/admin/, "관리자 콘솔"],
];

export function routeContextLabel(pathname) {
  const hit = ROUTE_TITLES.find(([re]) => re.test(pathname || "/"));
  return hit ? hit[1] : "ClovirAssist";
}

export function AssistantDrawer({ open, onClose }) {
  const nav = useNavigate();
  const loc = useLocation();
  const chat = useChat();
  const bodyRef = React.useRef(null);
  const context = routeContextLabel(loc.pathname);

  // 새 답이 오면 아래로 붙인다. 드로어는 좁아서 스크롤이 금방 생긴다.
  React.useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat.items.length, chat.busy]);

  const hasThread = chat.items.length > 0;

  return (
    <Drawer
      anchor="right"
      open={!!open}
      onClose={onClose}
      /* keepMounted — 드로어를 닫아도 대화가 살아 있어야 한다. 언마운트하면 물어본 내용이
         사라지고, 다시 열었을 때 "아까 뭐라고 했더라" 가 된다. */
      ModalProps={{ keepMounted: true }}
      /* 상단바가 `zIndex.drawer + 1` 로 떠 있어서(AppShell), 기본 z-index(=drawer)로 두면
         드로어 머리 줄(마스코트·닫기 버튼)이 상단바 **뒤에 깔린다**. 열려 있는 동안에는
         이 패널이 화면의 주인이므로 그 위로 올린다. */
      sx={{ zIndex: (t) => t.zIndex.drawer + 2 }}
      PaperProps={{
        "aria-label": "클로비 AI 도우미",
        sx: { width: WIDTH, display: "grid", gridTemplateRows: "auto auto 1fr auto" },
      }}
    >
      {/* 머리 */}
      <Box sx={{
        display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.5,
        borderBottom: 1, borderColor: "divider",
      }}>
        <MascotPose mode={chat.busy ? "thinking" : "listening"} size="2.25rem" decorative />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 750, lineHeight: 1.2 }}>클로비</Typography>
          <Typography sx={{ fontSize: "0.8125rem", color: "text.secondary" }}>
            {chat.busy ? "답변을 정리하고 있어요" : "현재 화면을 기준으로 도와드려요"}
          </Typography>
        </Box>
        <IconButton
          aria-label="전체 화면으로 열기"
          onClick={() => { onClose(); nav(chat.cid ? `/chat?c=${chat.cid}` : "/chat"); }}
          size="small"
        >
          <OpenInFullRoundedIcon fontSize="small" />
        </IconButton>
        <IconButton aria-label="AI 도우미 닫기" onClick={onClose} size="small">
          <CloseRoundedIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* 문맥 줄 — 이 드로어의 존재 이유다. 어느 화면을 두고 묻는지 사람과 클로비가 같이 본다. */}
      <Box sx={{
        px: 2, py: 1, fontSize: "0.8125rem",
        bgcolor: (t) => alpha(t.palette.primary.main, 0.06),
        borderBottom: 1, borderColor: "divider",
      }}>
        현재 문맥: <Box component="strong" sx={{ fontWeight: 750 }}>{context}</Box>
      </Box>

      {/* 대화 */}
      <Box ref={bodyRef} sx={{ minHeight: 0, overflowY: "auto", px: 2, py: 2, display: "grid", gap: 1.5, alignContent: "start" }}>
        {!hasThread ? (
          <Box sx={{ display: "grid", justifyItems: "center", textAlign: "center", gap: 1, py: 2 }}>
            <MascotPose mode="listening" size="4rem" decorative />
            <Typography sx={{ fontWeight: 750 }}>무엇을 도와드릴까요?</Typography>
            <Typography sx={{ fontSize: "0.8125rem", color: "text.secondary", maxWidth: "20rem", lineHeight: 1.6 }}>
              지금 보고 있는 화면의 티켓, 문서, 사용자를 기준으로 물어볼 수 있습니다.
            </Typography>
          </Box>
        ) : chat.items.map((m) => (
          <Box
            key={m.id}
            sx={{
              justifySelf: m.role === "user" ? "end" : "start",
              maxWidth: "88%", px: 1.75, py: 1.25, borderRadius: 2,
              bgcolor: (t) => (m.role === "user"
                ? alpha(t.palette.primary.main, 0.12)
                : t.palette.action.hover),
            }}
          >
            {/* 본문은 텍스트로만 그린다(React 자동 이스케이프). 팀 채팅의 `ChatBubbleText` 는
                멘션·읽음 표시를 다루는 다른 계약이라 여기서는 쓰지 않는다. */}
            <Typography sx={{ fontSize: "0.875rem", lineHeight: 1.65, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {m.content || ""}
            </Typography>
          </Box>
        ))}
        {chat.busy ? <Box sx={{ justifySelf: "start", width: "60%" }}><Skeleton lines={2} /></Box> : null}

        {/* 제안 칩 — 빈 화면에서 "무엇을 물어볼 수 있는지" 를 보여 준다. 대화가 시작되면
            자리를 비켜 준다(칩이 계속 남아 있으면 대화가 아니라 메뉴처럼 보인다). */}
        {!hasThread ? (
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, justifyContent: "center", mt: 1 }}>
            {SUGGESTIONS.map((s) => (
              <Chip
                key={s} label={s} size="small" variant="outlined" clickable
                onClick={() => chat.prefillFromPrompt(s)}
                sx={{ fontSize: "0.75rem" }}
              />
            ))}
          </Box>
        ) : null}
      </Box>

      {/* 컴포저 */}
      <Box
        component="form"
        onSubmit={(e) => { e.preventDefault(); chat.doSend(); }}
        sx={{ display: "flex", gap: 1, alignItems: "center", p: 1.5, borderTop: 1, borderColor: "divider" }}
      >
        <InputBase
          value={chat.text}
          onChange={(e) => chat.setText(e.target.value)}
          placeholder="클로비에게 질문하세요"
          inputProps={{ "aria-label": "클로비에게 질문" }}
          disabled={chat.inputDisabled}
          sx={{
            flex: 1, px: 1.5, py: 0.75, borderRadius: 2,
            border: 1, borderColor: "divider", bgcolor: "background.default",
          }}
        />
        <Button
          type="submit" variant="primary"
          disabled={chat.inputDisabled || !chat.text.trim()}
          aria-label="질문 전송"
        >
          <SendRoundedIcon fontSize="small" />
        </Button>
      </Box>
    </Drawer>
  );
}
