import React from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import { Button, Card, ErrorState, PageHeader, Skeleton, useConfirm } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import { PAGE_FILL_HEIGHT } from "../ui/density.js";
import { MascotPose } from "../ui/Mascot.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { useChat } from "./useChat.js";
import { copyText, formatConversationText, mascotMode, mascotStatusText } from "./chat-helpers.js";
import { COLUMNS, THREAD_MAX } from "./chat/layout.js";
import { ConversationSidebar } from "./chat/ConversationSidebar.jsx";
import { Composer } from "./chat/Composer.jsx";
import { MessageList } from "./chat/MessageList.jsx";
import { AssistantUnavailable, MascotStatus, Welcome } from "./chat/WelcomeStatus.jsx";
import { ResultsRail } from "./chat/ResultsRail.jsx";
import { citesSources } from "./chat/SourceList.jsx";
import { assistantOf, useAiStatus } from "../lib/useAiStatus.js";
import { useAuth } from "../app/auth.jsx";
import { setItemTitle } from "../app/documentTitle.js";

/* AI 채팅(§6.5) — 대화 목록 + 메시지 스레드 + 입력창 + (초광폭에서) 결과 레일.
 *
 * 이 파일은 화면을 **조립**만 한다. 조각은 모두 옮겨졌다:
 *   - 순수 함수·상수·정규식              → chat-helpers.js
 *   - 쿼리/뮤테이션/폴링/전송            → useChat.js
 *   - 열 폭 상수(COLUMNS/THREAD_MAX 등)  → chat/layout.js
 *   - 대화 목록 사이드바(목록+검색+항목)  → chat/ConversationSidebar.jsx
 *   - 리치 텍스트·URL 링크               → chat/RichText.jsx, chat/links.jsx
 *   - 말풍선 한 개(Message/타이핑/날짜)  → chat/MessageThread.jsx
 *   - 「참고한 자료」 목록                → chat/SourceList.jsx
 *   - 빈 화면 · 쓸 수 없음 · 마스코트      → chat/WelcomeStatus.jsx
 *   - 「참고한 자료」 레일(≥xxl 셋째 열)  → chat/ResultsRail.jsx
 * 예전엔 이 모든 것이 한 파일(1,070줄)에 있어서 레이아웃 하나를 손보려 해도 카드 마크업까지
 * 함께 위험해졌다. 조각마다 파일이 나뉜 지금도 **화면이 어떻게 나뉘는가**(아래 열 구성)는
 * 여기 한 곳에서만 결정한다 — 조각들은 자기가 어디 꽂히는지 모른다.
 *
 * 레이아웃(열 개수는 폭이 정한다. MUI Grid는 쓰지 않는다 — MUI 7에서 이름이 바뀌어
 * xs={12} 같은 예전 prop이 아무 말 없이 무시된다. CSS Grid를 직접 쓴다):
 *   < xl(1536)     1열. 대화 목록은 오버레이 서랍(오늘과 같다). 전역 사이드바가 이미 860부터
 *                  서 있어서, 여기서 목록까지 세우면 1024·1366 사내 장비의 대화 폭이 절반 아래가 된다.
 *   xl ~ xxl(2200) 2열. 대화 목록 + 스레드.
 *   ≥ xxl          3열. 대화 목록 + 스레드 + 결과 레일.
 * 서랍/열 경계는 chat-helpers.js의 LIST_DOCK_PX 하나를 훅과 공유한다 — 서랍의 inert·포커스
 * 반환이 그리드와 정확히 같은 지점에서 켜져야 한다.
 * 레일이 생기는 이유: 4K에서 남는 폭을 글줄 길이로 쓰면 안 된다(§ PROSE_MAX_WIDTH). 「참고한 자료」는 원래 말풍선
 * 아래에 서서 스레드를 길게 만든다 — 폭이 남을 때만 그것을 옆으로 꺼낸다.
 *
 * 이 화면도 다른 화면과 같은 `c-screen` + `PageHeader` 위의 판이다 — 셸의 'flush' 예외는 걷혔고(app/AppShell.jsx 는
 * `/chat` 에서 마스코트 단추만 감춘다), 판은 높이 고정(`PAGE_FILL_HEIGHT`)이다. 그래서 판 안의 높이와 스크롤은
 * 이 화면이 직접 소유한다 — 바깥 문서가 잡아 주지 않는다.
 * 스크롤 소유자는 **정확히 셋**이다: 대화 목록(사이드바 안 목록 칸), 스레드 본문(bodyRef),
 * 결과 레일. 셋은 서로 형제이지 서로의 안에 있지 않다 — 하나를 스크롤해도 다른 것이 같이
 * 움직이거나, 옛 목록을 보려고 두 스크롤바를 번갈아 만질 일이 없다(K-H3).
 */

// 기존 호출부 호환을 위한 재수출 — 순수 헬퍼를 예전처럼 Chat.jsx에서도 가져다 쓸 수 있게 남긴다. 정의는 각 모듈이 하나씩만 가진다.
export { msgAgeMs, classifyLine, parseBlocks, newClientMessageId } from "./chat-helpers.js";

// ── 화면 ────────────────────────────────────────────────────────────────────

/* 입력창 한 줄의 높이 — 입력칸의 바닥, 보내기 단추, 첨부 도구가 서는 줄이 이 값 하나를 나눠 쓴다. */
const COMPOSER_LINE = "2.75rem";

export function Chat() {
  const confirm = useConfirm();
  const loc = useLocation();
  const theme = useTheme();
  // 세 번째 열(결과 레일)은 폭이 실제로 남을 때만 존재한다. 같은 판정을 CSS와 JS 두 곳에서 하면
  // 반드시 어긋나므로(카드가 두 벌 뜨거나 아예 사라진다) 여기 한 곳에서만 정한다.
  const railOpen = useMediaQuery(theme.breakpoints.up("xxl"));
  const ch = useChat();
  const {
    cid, setCid, convs, convFilter, setConvFilter, showArchived, setShowArchived,
    setComposingNew, activeTitle, renameConv, archiveConv, deleteConv,
    hasMoreConvs, loadMoreConvs,
    thread, items, busy, awaitingReply, stalled, justAnswered, answerAnnounce, lastMsg, setResumedAt,
    text, setText, pending, setPending, composerFocused, setComposerFocused,
    maintenanceNotice, setMaintenanceNotice, rateLimitNotice, setRateLimitNotice,
    send, createConv, retryingRef,
    doSend, doRetry, pickFiles, clearDraft, prefillFromPrompt, askInNewConversation,
    composerLocked, inputDisabled,
    doRegenerate, regenerating, doDeleteMessage, doFeedback,
    stick, setStick, onScroll, sideOpen, setSideOpen, closeSideDrawer, listIsDrawer,
    bodyRef, fileRef, textareaRef, asideRef, sideToggleRef, aiQuota,
  } = ch;

  /* AI 를 지금 쓸 수 있는가(D-538) — 서버가 판정한다. 모를 때(아직 안 읽음)는 막지 않는다. 쓸 수 없으면 판이 까닭을 말하고
     입력 칸이 닫힌다. 「찾지 못함」은 이 상태가 아니다 — 그것은 도구가 0건을 돌려준 정상 답이다. */
  const aiStatus = useAiStatus();
  const assistant = assistantOf(aiStatus);
  const unavailable = !!assistant && !assistant.available;
  /* 내 말풍선 옆 얼굴(D-557)은 `/api/me` 의 아바타다 — 앱 셸이 이미 들고 있다. */
  const auth = useAuth();
  const me = (auth && auth.data) || null;

  /* `/ai` 의 「AI 도우미에게 묻기」는 `?ask=` 로 온다 — 한 번만 읽어 새 대화로 보내고 주소에서 지운다. */
  const [params, setParams] = useSearchParams();
  const askRef = React.useRef(params.get("ask"));
  React.useEffect(() => {
    const question = (askRef.current || "").trim();
    if (!question) return;
    askRef.current = null;
    setParams({}, { replace: true });
    if (unavailable) { prefillFromPrompt(question); return; }
    askInNewConversation(question);
    // 처음 한 번만 읽는다 — 이후 렌더에서 다시 보내지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // VIS-133: 탭 제목을 실제 대화 제목으로(Ticket.jsx 등과 같은 이유·같은 패턴) — PageHeader가
  // 이미 같은 조건(cid가 있을 때만 activeTitle, 없으면 "채팅")으로 그리고 있어 그대로 맞춘다.
  React.useEffect(() => {
    setItemTitle(loc.pathname, cid ? activeTitle : "");
  }, [loc.pathname, cid, activeTitle]);

  // AI-44: 하루 상한이 걸려 있을 때만 보인다 — 상한 행이 없는(fail-open) 설치에서는
  // "0/None" 같은 의미 없는 숫자로 컴포저를 어지럽히지 않는다.
  const aiQuotaDay = aiQuota.data && Array.isArray(aiQuota.data.periods)
    ? aiQuota.data.periods.find((p) => p.period === "day")
    : null;

  const convItems = (convs.data && convs.data.items) || [];
  const starting = send.isPending || createConv.isPending;
  // AI-68: 대화 전체 복사 — MessageThread.jsx의 메시지 단위 복사와 같은 가벼운 패턴
  // (useToast 없이 로컬 상태 + sr-only 라이브 영역).
  const [convCopied, setConvCopied] = React.useState("");
  function copyWholeConversation() {
    copyText(formatConversationText(items)).then((ok) => {
      setConvCopied(ok ? "대화가 복사됐습니다" : "복사 실패");
      setTimeout(() => setConvCopied(""), 1500);
    });
  }

  /* 레일이 지는 것은 '마지막으로 출처를 인용한 도우미 답' 하나다. 스레드를 거슬러 올라가며 처음 만나는 것을 쓴다 — 대화가
   * 이어져도 마지막으로 찾은 자료가 오른쪽에 남아 있어야 그 문서와 티켓을 보며 다음 질문을 칠 수 있다. 아무것도 인용하지 않은
   * 답(「찾아본 자료」만 있는 답)은 레일에 서지 않고 자기 말풍선에 접힌다(P-133). */
  const railMsg = railOpen
    ? [...items].reverse().find((m) => m.role === "assistant" && citesSources(m.structured)) || null
    : null;
  const railIsLast = !!railMsg && !!lastMsg && railMsg.id === lastMsg.id;
  // 답을 기다리는 동안의 진행 문구 — 서버가 사용자 메시지에 적는다(`structured.progress`, D-535).
  const progressLabel = lastMsg && lastMsg.role === "user" && lastMsg.structured && lastMsg.structured.progress
    ? lastMsg.structured.progress.label : null;

  /* 마스코트 단계 — 앱이 실제로 있는 상태만 넘긴다(mascotMode 주석 참고).
   * failed는 '지금 사용자가 갇혀 있는' 상태 셋을 합친다: 마지막 메시지가 실패했거나, 응답이
   * 임계 시간을 넘겨 지연됐거나, 폴링이 끊겨 스레드를 못 읽고 있거나. */
  const mascot = mascotMode({
    failed: (!!lastMsg && lastMsg.processing_status === "failed") || stalled || thread.isError,
    blocked: composerLocked,
    sending: starting,
    awaitingReply, busy,
    justAnswered,
    hasResult: !!lastMsg && citesSources(lastMsg.structured),
    composerFocused,
  });

  /* 스레드가 비었을 때 목록이 그릴 것 — 대화 목록 · 스레드의 읽기 상태와 가용 상태가 정한다(공용 목록은 그 사정을 모른다). */
  const emptyNode = !cid
    ? (convs.isLoading ? <Skeleton lines={3} />
      : convs.isError ? <ErrorState layout="region" error={convs.error} onRetry={() => convs.refetch()} />
      : unavailable ? <AssistantUnavailable assistant={assistant} />
      : <Welcome mode={mascot} title="무엇을 도와드릴까요?" busy={starting} onPick={prefillFromPrompt}
          help="문서, 티켓, 프로젝트, 결재, 알림, 회의록을 내 권한 안에서 찾아 답합니다. 팀 채팅 대화는 찾지 않습니다." />)
    : thread.isLoading ? <Skeleton lines={3} />
    : thread.isError && !items.length ? <ErrorState layout="region" error={thread.error} onRetry={() => thread.refetch()} />
    : unavailable ? <AssistantUnavailable assistant={assistant} />
    : <Welcome mode={mascot} title="새 대화" busy={starting} onPick={prefillFromPrompt} help="아래에 질문을 입력하거나, 예시를 눌러 시작하세요." />;
  /* 말풍선 옆 얼굴(D-557) — 클로비는 마스코트, 나는 내 아바타. 클로비 패널과 같은 규칙이다. */
  const faces = {
    assistant: <MascotPose mode={busy ? "thinking" : "listening"} place="chatBubble" decorative />,
    user: <UserAvatar person={me} name={me && me.display_name} size="md" />,
  };

  /* AI 도우미도 다른 화면과 **같은 언어**로 그린다 (사용자 지적 S3, "지금은 너무 안이쁘다").
   *
   * 예전에는 이 화면만 제목도 빵 부스러기도 없이 맨바닥에 두 칸이 놓여 있었다. 앱의 다른
   * 화면은 전부 `c-screen` + `PageHeader` + 카드 표면 위에 있는데 여기만 아니라서, 들어오는
   * 순간 "덜 만든 화면" 으로 읽혔다. 방금 통합한 채팅방 껍데기(S1)와도 같은 모양으로 맞춘다.
   *
   * 격자 자체(열 수·서랍 전환·xxl 3열)는 건드리지 않는다 — 그 상태 기계는 테스트가 없고,
   * 지금 고치려는 것은 '어떻게 담기는가' 이지 '어떻게 동작하는가' 가 아니다. */
  return (
    <Box className="c-screen">
      {/* SEM-03 재확인(2026-08-13) — PageHeader에 실제(동적) 대화 제목을 넘긴다. 예전엔
          여기가 항상 "AI 도우미"라 아래 대화 제목 막대가 별도 h1을 또 만들어야 했다. */}
      {/* AI 작업공간으로 가는 입구(S10). 사이드바에 자기 항목을 안 만든 이유는
          `navConfig.js` 의 `/knowledge` 와 같다 — 한 그룹이 여섯 항목을 넘지 않고, IA 를
          다시 짜는 것은 Phase E 의 일이다. 그래서 **성격이 같은 화면**에 입구를 둔다.
          이 화면은 사내 기록 전체를 모델에 싣고(S11 이 걷어낸다), 저쪽은 권한을 통과한
          문서만 근거로 쓴다 — 사용자에게는 같은 종류의 일이라 여기가 정확한 자리다. */}
      <PageHeader
        crumbRoot="도우미"
        area="AI 도우미"
        title={cid ? activeTitle : "AI 도우미"}
        actions={<Button href="#/ai">문서에서 찾기</Button>}
      />
      {/* 판 높이는 화면 아래까지 서는 판의 정본 값이다(`PAGE_FILL_HEIGHT` — 채팅방 · 새 티켓과 같은 값, 높이 고정 판).
          clovi-allow-geometry: 채움 판의 높이다. 작업 공간 채움 모드(D-531)로 옮기면 계산값이 사라진다. */}
      <Card
        data-page-fill=""
        padding="none"
        sx={{
          overflow: "hidden",
          height: PAGE_FILL_HEIGHT,
          minHeight: "30rem",
          display: "grid",
        }}
      >
    <Box
      sx={{
        position: "relative", width: "100%", height: "100%", minHeight: 0,
        display: "grid", gridTemplateColumns: COLUMNS, bgcolor: "background.default",
      }}
    >
      {/* 대화 목록. 좁은 폭에서는 오버레이 서랍(오늘과 같은 동작), xl 이상에서는 열로 상주한다. */}
      <ConversationSidebar
        asideRef={asideRef} listIsDrawer={listIsDrawer} sideOpen={sideOpen}
        closeSideDrawer={closeSideDrawer} setSideOpen={setSideOpen}
        convs={convs} convItems={convItems} convFilter={convFilter} setConvFilter={setConvFilter}
        showArchived={showArchived} setShowArchived={setShowArchived}
        hasMoreConvs={hasMoreConvs} loadMoreConvs={loadMoreConvs}
        cid={cid} setCid={setCid} setComposingNew={setComposingNew} clearDraft={clearDraft}
        textareaRef={textareaRef}
        renameConv={renameConv} archiveConv={archiveConv} deleteConv={deleteConv} confirm={confirm}
        failure={ch.sidebarFailure}
      />

      {/* 스레드 열 — 높이와 스크롤은 이 화면이 직접 소유한다(판이 높이 고정이다). */}
      <Box
        component="section"
        {...(sideOpen && listIsDrawer ? { inert: "", "aria-hidden": "true" } : {})}
        sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, position: "relative" }}
      >
        {/* 대화 제목 헤더 — 특히 좁은 폭(서랍이 닫혀 어느 대화인지 모른다)에서 현재 대화를 알린다. */}
        {/* 머리 띠는 판이 아니라 스레드 열의 윗단이다 — 판 면(`background.paper`)과 아래 실선만 든다. */}
        <Box
          sx={{ display: "flex", alignItems: "center", gap: 1.5, px: { xs: 2, lg: 3 }, py: 1.25, borderBottom: 1, borderColor: "divider", flexShrink: 0, bgcolor: "background.paper" }}
        >
          {/* 앱 셸의 햄버거와 같은 방식으로 aria-expanded/aria-controls를 실제 토글 상태에 맞춘다,
              이전엔 '열기' 전용 편도 트리거라 열린 뒤에도 라벨, 상태가 안 바뀌었다.
              xl 이상에서는 목록이 상주하므로 이 버튼 자체가 필요 없다.
              키트의 Button이 아니라 MUI IconButton을 쓰는 이유: 서랍을 닫을 때 포커스를 이 버튼으로
              되돌려야 하는데(closeSideDrawer) 키트 Button은 ref를 전달하지 않아 sideToggleRef가
              영원히 null이 된다 — 포커스가 문서 맨 앞으로 튕기는 조용한 접근성 회귀가 된다. */}
          <IconButton
            ref={sideToggleRef} aria-controls="chat-conv-drawer" aria-expanded={sideOpen}
            aria-label={sideOpen ? "대화 목록 닫기" : "대화 목록 열기"}
            onClick={() => (sideOpen ? closeSideDrawer() : setSideOpen(true))}
            sx={{ display: { xs: "inline-flex", xl: "none" }, flexShrink: 0 }}
          >
            {sideOpen ? <CloseRoundedIcon aria-hidden="true" /> : <MenuRoundedIcon aria-hidden="true" />}
          </IconButton>
          {/* cid가 없어도(첫 방문, 새 대화 시작 직후) 빈 막대 대신 화면 이름을 보여준다.
              SEM-03 재확인 — 같은 값을 위 PageHeader가 이제 h1로 이미 보여준다(특히 좁은
              폭에서 서랍이 닫혀 있어도 여전히 이 막대가 필요해 h2로 남긴다 — 완전히
              없애면 그 상황에서 "지금 보는 대화가 뭔지" 신호가 사라진다). */}
          <Typography
            component="h2"
            sx={{ flex: 1, minWidth: 0, fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.bold, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {cid ? activeTitle : "AI 도우미"}
          </Typography>
          {/* AI-68: 대화 전체 복사 — 메시지가 있을 때만(빈 대화를 복사할 이유가 없다). */}
          {cid && items.length ? (
            <Tooltip title="대화 전체 복사">
              <IconButton aria-label="대화 전체 복사" onClick={copyWholeConversation} sx={{ flexShrink: 0 }}>
                <ContentCopyRoundedIcon aria-hidden="true" sx={{ fontSize: "1.125rem" }} />
              </IconButton>
            </Tooltip>
          ) : null}
          <span className="sr-only" role="status" aria-live="polite">{convCopied}</span>
          {/* 쓸 수 없을 때는 「대화를 시작해 보세요」라고 권하지 않는다 — 판 상태가 까닭을 말한다. */}
          <MascotStatus mode={mascot} text={mascotStatusText({ mode: mascot, unavailable, hasMessages: !!(cid && items.length) })} />
        </Box>

        {/* 스레드 전체를 aria-live로 감싸면 1.5초 폴링마다 대화가 통째로 다시 낭독된다.
            스레드에서 aria-live를 걷어내고, 일시 상태만 이 작은 라이브 영역에서 알린다. */}
        <div className="sr-only" role="status" aria-live="polite">{busy ? "답변을 처리하고 있습니다." : ""}</div>
        <div className="sr-only" role="status" aria-live="polite">{answerAnnounce}</div>

        <MessageList
          chat={ch} variant="page" progressLabel={progressLabel} faces={faces}
          showSourcesFor={(m) => !(railMsg && railMsg.id === m.id)}
          empty={emptyNode}
        />

        {/* 전폭 배경 띠 — 초광폭에서 상단 헤더는 전폭 구분선인데 컴포저만 카드 폭으로 떠 좌우에
            페이지 배경 여백이 생겨 미완성처럼 보였다. 띠로 감싸고 안쪽 내용만 스레드와 같은 폭으로
            가운데 정렬해 헤더가 콘텐츠를 감싸는 방식과 맞춘다. 입력창 자체는 클로비 패널과 같은 부품이다(D-557). */}
        <Box sx={{ borderTop: 1, borderColor: "divider", flexShrink: 0, bgcolor: "background.paper" }}>
          <Box sx={{ width: "100%", maxWidth: THREAD_MAX, mx: "auto", px: { xs: 2, sm: 3 }, py: 1.5 }}>
            <Composer
              chat={ch} unavailable={unavailable} assistant={assistant}
              ariaLabel="메시지 입력" placeholder="메시지를 입력하세요"
              showUnavailableNotice={!!(cid && items.length)}
              quotaLine={aiQuotaDay && aiQuotaDay.limit != null ? (
                /* AI-44: 하루 상한이 걸려 있을 때만 보인다 — 상한 행이 없는(fail-open) 설치에서는 의미 없는 숫자로 입력창을 어지럽히지 않는다. */
                <Typography sx={{ textAlign: "right", fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
                  오늘 AI 사용량 {aiQuotaDay.used}/{aiQuotaDay.limit}
                </Typography>
              ) : null}
            />
          </Box>
        </Box>
      </Box>

      <ResultsRail railOpen={railOpen} railMsg={railMsg} railIsLast={railIsLast} />
    </Box>
      </Card>
    </Box>
  );
}
