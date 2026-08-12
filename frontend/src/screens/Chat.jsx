import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { alpha, useTheme } from "@mui/material/styles";
import ArrowDownwardRoundedIcon from "@mui/icons-material/ArrowDownwardRounded";
import AttachFileRoundedIcon from "@mui/icons-material/AttachFileRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import SendRoundedIcon from "@mui/icons-material/SendRounded";
import { Button, Card, ErrorState, PageHeader, Skeleton, useConfirm } from "../ui/kit.jsx";
import { useChat } from "./useChat.js";
import { dayKeyKST, mascotMode, structuredCards } from "./chat-helpers.js";
import { COLUMNS, THREAD_MAX } from "./chat/layout.js";
import { ConversationSidebar } from "./chat/ConversationSidebar.jsx";
import { DaySeparator, Message, TypingBubble } from "./chat/MessageThread.jsx";
import { MascotStatus, Welcome } from "./chat/WelcomeStatus.jsx";
import { ResultsRail } from "./chat/ResultsRail.jsx";

/* AI 채팅(§6.5) — 대화 목록 + 메시지 스레드 + 입력창 + (초광폭에서) 결과 레일.
 *
 * 이 파일은 화면을 **조립**만 한다. 조각은 모두 옮겨졌다:
 *   - 순수 함수·상수·정규식              → chat-helpers.js
 *   - 쿼리/뮤테이션/폴링/전송            → useChat.js
 *   - 열 폭 상수(COLUMNS/THREAD_MAX 등)  → chat/layout.js
 *   - 대화 목록 사이드바(목록+검색+항목)  → chat/ConversationSidebar.jsx
 *   - 리치 텍스트·URL 링크               → chat/RichText.jsx, chat/links.jsx
 *   - 결과 카드(TicketCard/CardStack)    → chat/TicketCard.jsx (기존 호출부 호환을 위해 이 파일도
 *                                          TicketCard를 재수출한다 — chat-card-chrome.test.jsx)
 *   - 말풍선 한 개(Message/타이핑/날짜)  → chat/MessageThread.jsx
 *   - 빈 화면·마스코트 상태 표시         → chat/WelcomeStatus.jsx
 *   - 결과 레일(≥xxl 세 번째 열)         → chat/ResultsRail.jsx
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
 * 레일이 생기는 이유: 4K에서 남는 폭을 글줄 길이로 쓰면 안 된다(§ PROSE_MAX_WIDTH). 티켓 카드는
 * 원래 말풍선 안에 끼어 스레드를 밀어내고 있었다 — 폭이 남을 때만 그것을 옆으로 꺼낸다.
 *
 * 이 화면은 앱 셸에서 유일하게 'flush'로 그려진다(app/AppShell.jsx가 pathname==="/chat"만
 * 특별 취급한다). 즉 높이와 스크롤은 이 화면이 직접 소유한다 — 바깥이 잡아 주지 않는다.
 * 스크롤 소유자는 **정확히 셋**이다: 대화 목록(사이드바 안 목록 칸), 스레드 본문(bodyRef),
 * 결과 레일. 셋은 서로 형제이지 서로의 안에 있지 않다 — 하나를 스크롤해도 다른 것이 같이
 * 움직이거나, 옛 목록을 보려고 두 스크롤바를 번갈아 만질 일이 없다(K-H3).
 */

// 기존 호출부 호환을 위한 재수출 — 이 화면이 소유하지 않는 어휘(우선순위)와 순수 헬퍼를
// 예전처럼 Chat.jsx에서도 가져다 쓸 수 있게 남긴다. 정의는 각 모듈이 하나씩만 가진다.
export {
  priorityKo, priorityKind, safeNotion, msgAgeMs, classifyLine, parseBlocks,
  pageNumberOrNull, bodyListStart, ticketPageStart, stripDuplicatedTicketLines,
  newClientMessageId,
} from "./chat-helpers.js";
// TicketCard의 정의는 chat/TicketCard.jsx 하나뿐이다 — chat-card-chrome.test.jsx가
// "./Chat.jsx"에서 그대로 가져다 쓰므로 여기서도 같은 것을 재수출한다.
export { TicketCard } from "./chat/TicketCard.jsx";

// ── 화면 ────────────────────────────────────────────────────────────────────

export function Chat() {
  const confirm = useConfirm();
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
    doSend, doRetry, pickFiles, clearDraft, prefillFromPrompt,
    composerLocked, sending, inputDisabled,
    stick, setStick, onScroll, sideOpen, setSideOpen, closeSideDrawer, listIsDrawer,
    bodyRef, fileRef, textareaRef, asideRef, sideToggleRef, aiQuota,
  } = ch;

  // AI-44: 하루 상한이 걸려 있을 때만 보인다 — 상한 행이 없는(fail-open) 설치에서는
  // "0/None" 같은 의미 없는 숫자로 컴포저를 어지럽히지 않는다.
  const aiQuotaDay = aiQuota.data && Array.isArray(aiQuota.data.periods)
    ? aiQuota.data.periods.find((p) => p.period === "day")
    : null;

  const convItems = (convs.data && convs.data.items) || [];
  const starting = send.isPending || createConv.isPending;

  /* 레일이 지는 것은 '마지막으로 결과를 들고 온 어시스턴트 메시지' 하나다. 스레드를 거슬러
   * 올라가며 처음 만나는 것을 쓴다 — 대화가 이어지면 사용자가 마지막으로 요청한 결과가
   * 계속 오른쪽에 남아 있어야 티켓 번호를 보며 다음 문장을 칠 수 있다. */
  const railMsg = railOpen
    ? [...items].reverse().find((m) => m.role === "assistant" && structuredCards(m).hasAny) || null
    : null;
  const railPayload = railMsg ? structuredCards(railMsg) : null;
  const railIsLast = !!railMsg && !!lastMsg && railMsg.id === lastMsg.id;

  /* 마스코트 단계 — 앱이 실제로 있는 상태만 넘긴다(mascotMode 주석 참고).
   * failed는 '지금 사용자가 갇혀 있는' 상태 셋을 합친다: 마지막 메시지가 실패했거나, 응답이
   * 임계 시간을 넘겨 지연됐거나, 폴링이 끊겨 스레드를 못 읽고 있거나. */
  const mascot = mascotMode({
    failed: (!!lastMsg && lastMsg.processing_status === "failed") || stalled || thread.isError,
    blocked: composerLocked,
    sending: starting,
    awaitingReply, busy,
    justAnswered,
    hasResult: !!lastMsg && structuredCards(lastMsg).hasAny,
    composerFocused,
  });

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
      <PageHeader crumbRoot="도우미" area="AI 도우미" title={cid ? activeTitle : "채팅"} />
      <Card
        sx={{
          p: 0, overflow: "hidden",
          height: { xs: "calc(100vh - 12rem)", md: "calc(100vh - 13rem)" },
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
      />

      {/* 스레드 열 — 높이와 스크롤은 이 화면이 직접 소유한다(셸이 flush로 넘긴다). */}
      <Box
        component="section"
        {...(sideOpen && listIsDrawer ? { inert: "", "aria-hidden": "true" } : {})}
        sx={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0, position: "relative" }}
      >
        {/* 대화 제목 헤더 — 특히 좁은 폭(서랍이 닫혀 어느 대화인지 모른다)에서 현재 대화를 알린다. */}
        <Paper
          elevation={0} square
          sx={{ display: "flex", alignItems: "center", gap: 1.5, px: { xs: 2, lg: 3 }, py: 1.25, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}
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
            sx={{ flex: 1, minWidth: 0, fontSize: "0.9375rem", fontWeight: 750, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
          >
            {cid ? activeTitle : "채팅"}
          </Typography>
          <MascotStatus mode={mascot} />
        </Paper>

        {/* 스레드 전체를 aria-live로 감싸면 1.5초 폴링마다 대화가 통째로 다시 낭독된다.
            스레드에서 aria-live를 걷어내고, 일시 상태만 이 작은 라이브 영역에서 알린다. */}
        <div className="sr-only" role="status" aria-live="polite">{busy ? "답변을 처리하고 있습니다." : ""}</div>
        <div className="sr-only" role="status" aria-live="polite">{answerAnnounce}</div>

        <Box ref={bodyRef} onScroll={onScroll} sx={{ position: "relative", flex: 1, minHeight: 0, overflowY: "auto", px: { xs: 2, sm: 3 }, py: 3, display: "flex", flexDirection: "column" }}>
          {/* flex:1 0 auto — 내용이 짧아도 열이 스크롤 높이를 꽉 채워 환영 화면의 margin:auto가
              실제로 세로 가운데를 잡는다. shrink는 0이라 길어지면 그대로 스크롤된다. */}
          <Box sx={{ width: "100%", maxWidth: THREAD_MAX, mx: "auto", flex: "1 0 auto", display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
            {!cid ? (
              // 대화 목록 조회가 실패/로딩 중이면 환영 화면 대신 그 상태를 보여준다, 좁은 폭에선 목록이
              // 닫힌 서랍 안에 있어 그 안의 오류/재시도가 안 보이므로, 여기(본문)에도 같은 신호가 있어야 한다.
              convs.isLoading ? <Skeleton lines={3} />
              : convs.isError ? <ErrorState error={convs.error} onRetry={() => convs.refetch()} />
              : (
                <Welcome mode={mascot} title="무엇을 도와드릴까요?" busy={starting} onPick={prefillFromPrompt}
                  help="대화 한 줄이면 티켓 생성, 조회, 요약까지 처리합니다. 아래 예시를 눌러 바로 시작해 보세요." />
              )
            ) : thread.isLoading ? <Skeleton lines={3} />
              : thread.isError && !items.length ? <ErrorState error={thread.error} onRetry={() => thread.refetch()} />
              : items.length === 0 ? (
                <Welcome mode={mascot} title="새 대화" busy={starting} onPick={prefillFromPrompt}
                  help="아래에 메시지를 입력하거나, 예시를 눌러 시작하세요." />
              )
              : (<>
                  {/* 폴링이 일시 실패해도 읽던 메시지를 지우지 않는다, 작은 안내만 띄우고 스레드는 유지. */}
                  {thread.isError ? (
                    <Alert severity="warning" variant="outlined" role="status" sx={{ alignSelf: "center", fontSize: "0.8125rem", py: 0 }}
                      action={<Button size="sm" variant="ghost" onClick={() => thread.refetch()}>새로고침</Button>}>
                      연결이 잠시 끊겼습니다.
                    </Alert>
                  ) : null}
                  {items.map((m, i) => {
                    // 앞 메시지와 KST 기준 날짜가 다르면(또는 첫 메시지면) 그 앞에 날짜 구분선을 끼운다.
                    const prev = i > 0 ? items[i - 1] : null;
                    const dk = dayKeyKST(m.created_at);
                    const showSep = !!dk && (!prev || dayKeyKST(prev.created_at) !== dk);
                    return (
                      <React.Fragment key={m.id}>
                        {showSep ? <DaySeparator at={m.created_at} /> : null}
                        {/* retrying은 이 메시지가 지금 재시도 중인지만 본다 — 뮤테이션의 전역 isPending을
                            그대로 쓰면 스레드의 다른 실패 메시지의 '다시 시도'까지 함께 잠긴다(과잉 제한).
                            sending은 선택 버튼·카드 '상세'를 눌러도 되는지다(useChat이 한 값으로 계산). */}
                        <Message m={m} onChoose={doSend} onRetry={doRetry} sending={sending}
                          retrying={retryingRef.current === m.id} isLast={i === items.length - 1}
                          hideCards={!!railMsg && railMsg.id === m.id} />
                      </React.Fragment>
                    );
                  })}
                  {/* 답변 대기 중이면 왼쪽에 어시스턴트 타이핑 말풍선(사용자 말풍선 안이 아니라). awaitingReply
                      자체가 이미 stalled를 제외하므로 별도 조건이 필요 없다. */}
                  {awaitingReply ? <TypingBubble /> : null}
                  {/* 응답이 임계 시간을 넘겨 지연되면 무한 대기 대신 수동 새로고침을 제공한다. 새로고침은 단순
                      재조회가 아니라 폴링 재시작 기준선(resumedAt)도 지금 시각으로 옮긴다, 안 그러면 created_at이
                      그대로라 재조회 직후 다시 즉시 stalled로 재계산돼 자동 폴링이 재개되지 않는 막다른 길이 된다. */}
                  {stalled ? (
                    <Alert severity="warning" variant="outlined" role="status" sx={{ alignSelf: "flex-start", fontSize: "0.8125rem" }}
                      action={<Button size="sm" variant="ghost" onClick={() => { setResumedAt(Date.now()); thread.refetch(); }}>새로고침</Button>}>
                      응답이 지연되고 있습니다.
                    </Alert>
                  ) : null}
                </>)}
            {/* 스크롤 컨테이너 안에서 sticky로 띄운다, 예전엔 열 기준(컴포저 바로 위 고정 거리)이라,
                여러 줄 초안+첨부 미리보기+글자 수로 컴포저가 커지면 이 버튼이 컴포저 안/뒤로 파묻혔다.
                스크롤 영역에 붙이면 컴포저 높이와 무관하게 항상 그 위에 뜬다. */}
            {!stick ? (
              <Box sx={{ position: "sticky", bottom: 0, alignSelf: "flex-end", mt: "auto", pt: 1, zIndex: 5 }}>
                <Button variant="primary" size="sm" onClick={() => setStick(true)} sx={{ borderRadius: "999px", boxShadow: 6 }}>
                  <ArrowDownwardRoundedIcon aria-hidden="true" sx={{ fontSize: "1rem", mr: 0.5 }} />맨 아래로
                </Button>
              </Box>
            ) : null}
          </Box>
        </Box>

        {/* 전폭 배경 띠 — 초광폭에서 상단 헤더는 전폭 구분선인데 컴포저만 카드 폭으로 떠 좌우에
            페이지 배경 여백이 생겨 미완성처럼 보였다. 띠로 감싸고 안쪽 내용만 스레드와 같은 폭으로
            가운데 정렬해 헤더가 콘텐츠를 감싸는 방식과 맞춘다. */}
        <Paper elevation={0} square sx={{ borderTop: 1, borderColor: "divider", flexShrink: 0 }}>
          <Box sx={{ width: "100%", maxWidth: THREAD_MAX, mx: "auto", px: { xs: 2, sm: 3 }, py: 1.5, display: "grid", gap: 1 }}>
            {pending.length ? (
              <>
                {/* Chip의 onDelete는 쓰지 않는다 — MUI가 삭제 아이콘을 tabIndex=-1로 만들어 키보드
                    사용자가 첨부를 뺄 방법이 사라진다. 이름이 붙은 진짜 버튼을 직접 둔다. */}
                <Stack direction="row" flexWrap="wrap" gap={0.75}>
                  {pending.map((a, i) => (
                    <Paper key={i} variant="outlined"
                      sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, pl: 0.5, pr: 0.25, py: 0.25, borderRadius: "999px", maxWidth: "18rem" }}>
                      {/* 보낼 이미지를 텍스트 칩이 아니라 실제 썸네일로 확인시킨다(로컬 data URL). */}
                      <Box component="img" src={"data:" + (a.media_type || "image/png") + ";base64," + a.data} alt=""
                        sx={{ width: "1.75rem", height: "1.75rem", objectFit: "cover", borderRadius: "50%", flexShrink: 0 }} />
                      <Typography sx={{ fontSize: "0.75rem", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.filename}</Typography>
                      <IconButton size="small" aria-label={"첨부 제거: " + a.filename}
                        onClick={() => setPending((p) => p.filter((_, j) => j !== i))}
                        sx={{ minWidth: "1.75rem", minHeight: "1.75rem", flexShrink: 0 }}>
                        <CloseRoundedIcon sx={{ fontSize: "0.9375rem" }} />
                      </IconButton>
                    </Paper>
                  ))}
                </Stack>
                {/* hover-only 툴팁은 모바일/터치에서 아예 안 보인다, 전송 전에 눈에 보이는 문장으로도 알린다. */}
                <Typography sx={{ fontSize: "0.75rem", color: "text.secondary" }}>전송 후에는 이미지 원본이 저장되지 않습니다, 파일 이름만 남습니다.</Typography>
              </>
            ) : null}
            {/* 글자 수는 입력이 있으면 늘 옅게 보여준다 — 상한이 갑자기 닥치지 않게(바닐라도 항상 표시).
                textarea의 maxLength=5000은 UTF-16 코드 유닛 기준이라, 서로게이트 쌍(이모지 등)이 섞이면
                Array.from(코드 포인트) 기준 길이는 실제 입력 가능 한도보다 작게 세어져 두 숫자가 어긋난다 —
                text.length(코드 유닛)로 맞춘다. */}
            {text.length > 0 ? (
              <Typography sx={{ textAlign: "right", fontSize: "0.75rem", color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>{text.length}/5000</Typography>
            ) : null}
            {/* 유지보수 모드 차단 안내 — 폴링 경고와 같은 지속 배너 패턴(사라지는 토스트 하나에만
                기대지 않는다). '다시 시도'를 눌러야 컴포저 잠금이 풀린다. */}
            {maintenanceNotice ? (
              <Alert severity="warning" role="status" sx={{ fontSize: "0.8125rem" }}
                action={<Button size="sm" variant="ghost" onClick={() => setMaintenanceNotice(null)}>다시 시도</Button>}>
                {maintenanceNotice}
              </Alert>
            ) : null}
            {rateLimitNotice ? (
              <Alert severity="warning" role="status" sx={{ fontSize: "0.8125rem" }}
                action={<Button size="sm" variant="ghost" onClick={() => setRateLimitNotice(null)}>닫기</Button>}>
                {rateLimitNotice}
              </Alert>
            ) : null}
            {/* 답변을 기다리는 동안 textarea는 계속 활성이라(placeholder는 'Enter 전송'을 약속) 입력이
                막혔다는 신호가 없어, Enter를 쳐도 사라지는 토스트로만 알렸다, 유지보수·속도제한 배너처럼
                지속되는 수동 힌트를 컴포저 위에 둔다. */}
            {(busy || awaitingReply) && !composerLocked ? (
              <Typography role="status" sx={{ textAlign: "center", fontSize: "0.75rem", color: "text.secondary" }}>
                답변을 기다리는 중입니다, 답변이 도착하면 다시 입력할 수 있습니다.
              </Typography>
            ) : null}
            {aiQuotaDay && aiQuotaDay.limit != null ? (
              <Typography sx={{ textAlign: "right", fontSize: "0.75rem", color: "text.secondary" }}>
                오늘 AI 사용량 {aiQuotaDay.used}/{aiQuotaDay.limit}
              </Typography>
            ) : null}
            <Box component="footer" sx={{ display: "flex", gap: 1, alignItems: "flex-end" }}>
              <Box component="input" ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" multiple
                aria-hidden="true" tabIndex={-1} onChange={(e) => pickFiles(e.target.files)} sx={{ display: "none" }} />
              {/* 전송과 같은 '어시스턴트가 아직 작업 중' 가드를 쓴다, 이전엔 이 버튼만 그 상태에서도
                  눌려, 첨부를 골라도 어차피 이번 턴엔 보낼 수 없는데 활성으로 보였다. */}
              <Tooltip title="이미지 첨부(PNG, JPEG, WebP)">
                <Box component="span" sx={{ flexShrink: 0 }}>
                  <IconButton aria-label="이미지 첨부" disabled={inputDisabled}
                    onClick={() => fileRef.current && fileRef.current.click()}
                    sx={{ border: 1, borderColor: "divider", borderRadius: 2.5, width: "2.75rem", height: "2.75rem", minWidth: "2.75rem", minHeight: "2.75rem" }}>
                    <AttachFileRoundedIcon sx={{ fontSize: "1.25rem" }} />
                  </IconButton>
                </Box>
              </Tooltip>
              {/* 네이티브 textarea를 유지한다 — 자동 높이(useChat의 useLayoutEffect)가 이 노드의
                  style.height를 직접 만진다. MUI의 다중행 입력은 자기 나름의 리사이즈를 또 하므로
                  둘이 겹치면 첫 글자에서 높이가 튄다. */}
              <Box
                component="textarea" ref={textareaRef} rows={1} value={text} maxLength={5000}
                aria-label="메시지 입력" disabled={composerLocked}
                placeholder="메시지를 입력하세요 (Enter 전송, Shift+Enter 줄바꿈)"
                onChange={(e) => setText(e.target.value)}
                onFocus={() => setComposerFocused(true)}
                onBlur={() => setComposerFocused(false)}
                onKeyDown={(e) => { if (e.nativeEvent.isComposing || e.keyCode === 229) return; if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); } }}
                sx={{
                  flex: 1, minWidth: 0, resize: "none", minHeight: "2.75rem", maxHeight: "10rem", boxSizing: "border-box",
                  font: "inherit", fontSize: "0.9375rem", lineHeight: 1.5, px: 1.75, py: 1.25,
                  border: 1, borderColor: "divider", borderRadius: 2.5,
                  bgcolor: "background.default", color: "text.primary",
                  transition: "border-color .15s ease, box-shadow .15s ease",
                  "&:focus": { outline: "none", borderColor: "primary.main", boxShadow: (t) => `0 0 0 3px ${alpha(t.palette.primary.main, 0.16)}` },
                  "&:disabled": { opacity: 0.6 },
                }}
              />
              <Button variant="primary" onClick={() => doSend()} disabled={inputDisabled || (!text.trim() && !pending.length)}
                sx={{ flexShrink: 0, minHeight: "2.75rem" }}>
                <SendRoundedIcon aria-hidden="true" sx={{ fontSize: "1.125rem", mr: 0.5 }} />전송
              </Button>
            </Box>
          </Box>
        </Paper>
      </Box>

      <ResultsRail railOpen={railOpen} railMsg={railMsg} railPayload={railPayload} railIsLast={railIsLast} doSend={doSend} sending={sending} />
    </Box>
      </Card>
    </Box>
  );
}
