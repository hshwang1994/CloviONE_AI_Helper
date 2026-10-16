import React from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import { Badge, Button, Callout, Card, ErrorState, OverflowMenu, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import { useWorkspaceFill } from "../ui/Workspace.jsx";
import { MascotPose } from "../ui/Mascot.jsx";
import { UserAvatar } from "../ui/UserAvatar.jsx";
import { useChat } from "./useChat.js";
import { copyText, formatConversationText, mascotMode } from "./chat-helpers.js";
import { CHAT_FLOW_HEIGHT, CHAT_FLOW_HEIGHT_PHONE, DRAWER_WIDTH, LIST_WIDTH, SOURCES_WIDTH } from "./chat/layout.js";
import { useChatLayout } from "./chat/useChatLayout.js";
import { ConversationSidebar, InlineRename } from "./chat/ConversationSidebar.jsx";
import { Composer } from "./chat/Composer.jsx";
import { MessageList } from "./chat/MessageList.jsx";
import { AssistantUnavailable, Welcome } from "./chat/WelcomeStatus.jsx";
import { SourcesPanel } from "./chat/SourcesPanel.jsx";
import { AnswerLinkContext } from "./chat/links.jsx";
import { citesSources, panelSources } from "./chat/SourceList.jsx";
import { assistantOf, useAiStatus } from "../lib/useAiStatus.js";
import { useAuth } from "../app/auth.jsx";
import { setItemTitle } from "../app/documentTitle.js";

/* AI 도우미 전체 화면 — 대화 목록 · 대화 · 참고 자료 (AI 채팅 개선 회차).
 *
 * **주소가 정본이다.** `/chat` 은 새 대화 초안이고 `/chat/:id` 는 그 대화다. 목록에서 고르면 주소가 바뀌고(뒤로 · 앞으로 ·
 * 새로고침이 그대로 그 대화), 첫 전송은 대화를 만든 뒤 `/chat/<id>` 로 바뀐다. 가운데 머리의 제목은 그 id 의 스레드 응답이
 * 정본이고, 페이지 제목은 「AI 도우미」다(예전에는 h1 과 가운데 머리가 같은 대화 제목을 되풀이했고 긴 제목이 h1 을 두 줄로 밀었다).
 *
 * 틀은 채팅방과 같은 어휘다 — 목록 · 대화(· 참고 자료)가 각자 카드이고, 몇 칸이 서는지는 카드가 놓인 폭이 정한다
 * (`chat/useChatLayout.js`: wide 세 칸 · medium 두 칸 · narrow · mobile 은 대화만 + 목록 서랍). 창이 1200×600 이상이면 채움
 * 모드라 페이지가 굴러가지 않고 세 칸이 각자 굴러간다. 입력은 대화 카드 아래에 붙박이다. */

// 기존 호출부 호환을 위한 재수출 — 순수 헬퍼의 정의는 chat-helpers.js 하나다.
export { msgAgeMs, classifyLine, parseBlocks, newClientMessageId } from "./chat-helpers.js";

function ConversationDrawer({ open, onClose, mobile, children, labelledBy }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!open) return undefined;
    const el = ref.current;
    const first = el && el.querySelector("button, [href], input, [tabindex]:not([tabindex='-1'])");
    if (first) first.focus();
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  return (
    <>
      {open ? (
        <Box onClick={onClose} aria-hidden="true"
          sx={{ position: "absolute", inset: 0, zIndex: 15, bgcolor: (t) => alpha(t.palette.common.black, 0.36) }} />
      ) : null}
      <Box
        ref={ref} id="chat-conv-drawer" role="dialog" aria-modal={open ? "true" : undefined} aria-labelledby={labelledBy}
        {...(!open ? { inert: "", "aria-hidden": "true" } : {})}
        sx={{
          position: "absolute", top: 0, left: 0, bottom: 0, zIndex: 20, width: mobile ? "100%" : DRAWER_WIDTH,
          bgcolor: "background.paper", borderRight: mobile ? 0 : 1, borderColor: "rule", boxShadow: open ? 8 : 0,
          transform: open ? "none" : "translateX(-100%)", transition: "transform .2s ease", display: "flex", flexDirection: "column",
        }}
      >
        {mobile ? (
          <Box sx={{ display: "flex", justifyContent: "flex-end", px: 1, pt: 1 }}>
            <IconButton size="small" aria-label="대화 목록 닫기" onClick={onClose}><CloseRoundedIcon /></IconButton>
          </Box>
        ) : null}
        <Box sx={{ flex: 1, minHeight: 0 }}>{children}</Box>
      </Box>
    </>
  );
}

function ThreadHeader({
  title, cid, archived, listDocked, sideOpen, onToggleList, toggleRef, renaming, setRenaming, onRename,
  menuItems, sourcesToggle,
}) {
  // 이름을 다 고치면 초점을 「대화 동작」 단추로 돌려준다(칸이 사라지며 초점이 문서 처음으로 떨어지지 않게).
  const menuRef = React.useRef(null);
  const doneRenaming = () => {
    setRenaming(false);
    requestAnimationFrame(() => {
      const button = menuRef.current && menuRef.current.querySelector("button");
      if (button) button.focus();
    });
  };
  return (
    <Box component="header"
      sx={{ display: "flex", alignItems: "center", gap: 1, px: { xs: 1.5, sm: 2.5 }, minHeight: "3.5rem",
            borderBottom: 1, borderColor: "rule", flexShrink: 0, minWidth: 0 }}>
      {!listDocked ? (
        <IconButton ref={toggleRef} size="small" aria-controls="chat-conv-drawer" aria-expanded={sideOpen}
          aria-label={sideOpen ? "대화 목록 닫기" : "대화 목록 열기"} onClick={onToggleList} sx={{ flexShrink: 0, ml: -0.5 }}>
          <MenuRoundedIcon aria-hidden="true" />
        </IconButton>
      ) : null}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        {renaming ? (
          <InlineRename value={title} label={title} onSave={onRename} onDone={doneRenaming}
            sx={{ fontSize: FONT_SIZE.body, maxWidth: "36rem" }} />
        ) : (
          <Typography component="h2" title={title}
            sx={{ fontSize: FONT_SIZE.cardTitle, fontWeight: FONT_WEIGHT.bold, lineHeight: 1.35, overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {title}
          </Typography>
        )}
      </Box>
      {archived ? <Badge value="archived" /> : null}
      {sourcesToggle}
      {cid && menuItems.length ? (
        <Box ref={menuRef} sx={{ display: "flex", flexShrink: 0 }}>
          <OverflowMenu size="sm" ariaLabel="대화 동작" items={menuItems} />
        </Box>
      ) : null}
    </Box>
  );
}

/* 참고 자료 판을 사람이 닫았는가 — 이 브라우저에만 남는 편의다(다른 기기 · 다른 사람과 나누지 않는다). */
const SOURCES_HIDDEN_KEY = "chat.sources.hidden";
function readHidden() {
  try { return window.localStorage.getItem(SOURCES_HIDDEN_KEY) === "1"; } catch (e) { return false; }
}
function writeHidden(v) {
  try { window.localStorage.setItem(SOURCES_HIDDEN_KEY, v ? "1" : "0"); } catch (e) { /* 저장소를 못 쓰면 이번 화면에서만 */ }
}

export function Chat() {
  const confirm = useConfirm();
  const toast = useToast();
  const navigate = useNavigate();
  const params = useParams();
  const routeId = params.id || null;
  /* 지금 주소의 대화 — 이동할 때 곧바로 바꾼다. 같은 줄을 한 그림 안에 두 번 눌러도(그 사이 화면이 다시 그려지지 않아도) 같은
     주소를 두 번 쌓지 않는다(뒤로 가기가 같은 대화에 머물던 자리). 「새 대화」를 거듭 눌러도 초안 주소는 하나다. */
  const openedRef = React.useRef(routeId);
  openedRef.current = routeId;
  const onOpen = React.useCallback((id, opts) => {
    const next = id || null;
    if (next === openedRef.current) return;
    openedRef.current = next;
    navigate(next ? `/chat/${next}` : "/chat", opts);
  }, [navigate]);
  const fill = useWorkspaceFill();
  const gridRef = React.useRef(null);
  const mode = useChatLayout(gridRef);
  const listDocked = mode === "wide" || mode === "medium";
  const mobile = mode === "mobile";
  const ch = useChat({ conversationId: routeId, onOpen });
  const {
    cid, convs, convFilter, setConvFilter, showArchived, setShowArchived,
    activeTitle, threadConv, renameConv, archiveConv, deleteConv, archiveEmpty, emptyTotal,
    hasMoreConvs, loadMoreConvs, thread, items, busy, awaitingReply, stalled, justAnswered, answerAnnounce, lastMsg,
    send, createConv, clearDraft, prefillFromPrompt, askInNewConversation, composerLocked, composerFocused, textareaRef,
    aiQuota,
  } = ch;

  const aiStatus = useAiStatus();
  const assistant = assistantOf(aiStatus);
  const unavailable = !!assistant && !assistant.available;
  const auth = useAuth();
  const me = (auth && auth.data) || null;

  /* `/ai` 의 「AI 도우미에게 묻기」는 `?ask=` 로 온다 — 한 번만 읽어 새 대화로 보내고 주소에서 지운다(보내면 `/chat/<id>`). */
  const [searchParams, setSearchParams] = useSearchParams();
  const askRef = React.useRef(searchParams.get("ask"));
  React.useEffect(() => {
    const question = (askRef.current || "").trim();
    if (!question) return;
    askRef.current = null;
    setSearchParams({}, { replace: true });
    if (unavailable) { prefillFromPrompt(question); return; }
    askInNewConversation(question);
    // 처음 한 번만 읽는다 — 이후 그림에서 다시 보내지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* 탭 제목은 그 대화 제목이다(VIS-133). 초안이면 화면 이름만. */
  React.useEffect(() => { setItemTitle(cid ? `/chat/${cid}` : "/chat", cid ? activeTitle : ""); }, [cid, activeTitle]);

  // ── 목록 서랍(좁은 틀) ────────────────────────────────────────────────────────────────────────────
  const [sideOpen, setSideOpen] = React.useState(false);
  const toggleRef = React.useRef(null);
  const closeSide = React.useCallback(() => {
    setSideOpen(false);
    requestAnimationFrame(() => toggleRef.current && toggleRef.current.focus());
  }, []);
  React.useEffect(() => { if (listDocked) setSideOpen(false); }, [listDocked]);

  // ── 대화 머리 ─────────────────────────────────────────────────────────────────────────────────────
  const [renaming, setRenaming] = React.useState(false);
  React.useEffect(() => { setRenaming(false); }, [cid]);
  const [copied, setCopied] = React.useState("");
  const archived = !!(threadConv && threadConv.archived);
  const menuItems = cid ? [
    { key: "rename", label: "이름 바꾸기", onClick: () => setRenaming(true) },
    items.length ? {
      key: "copy", label: "대화 전체 복사",
      onClick: () => copyText(formatConversationText(items)).then((ok) => {
        setCopied(ok ? "대화를 복사했습니다." : "복사하지 못했습니다.");
        setTimeout(() => setCopied(""), 1500);
      }),
    } : null,
    { key: "archive", label: archived ? "보관함에서 꺼내기" : "보관하기",
      onClick: () => archiveConv.mutateAsync({ id: cid, archived: !archived }).then(() => {
        qcRefresh();
        toast(archived ? "대화를 보관함에서 꺼냈습니다." : "대화를 보관했습니다. 보관함에서 다시 꺼낼 수 있습니다.", "success");
      }, () => {}) },
    { key: "delete", label: "삭제", tone: "danger",
      onClick: async () => {
        if (await confirm(`「${activeTitle}」 대화를 삭제합니다. 되돌릴 수 없습니다.`, { danger: true, title: "대화 삭제", confirmLabel: "삭제" })) {
          deleteConv.mutate(cid);
        }
      } },
  ].filter(Boolean) : [];
  function qcRefresh() { thread.refetch(); }

  // ── 참고 자료 판 ──────────────────────────────────────────────────────────────────────────────────
  const answers = items.filter((m) => m.role === "assistant" && panelSources(m.structured).length > 0);
  const [selectedId, setSelectedId] = React.useState(null);
  React.useEffect(() => { setSelectedId(null); }, [cid]);
  const latestAnswer = answers.length ? answers[answers.length - 1] : null;
  const panelMsg = (selectedId && answers.find((m) => m.id === selectedId)) || latestAnswer;
  const [hidden, setHidden] = React.useState(readHidden);
  const sourcesDocked = mode === "wide" && !!panelMsg && !hidden;
  const [activeRoute, setActiveRoute] = React.useState(null);
  const linkCtx = React.useMemo(() => ({ onHover: sourcesDocked ? setActiveRoute : null }), [sourcesDocked]);
  const sourcesToggle = mode === "wide" && panelMsg ? (
    <Button size="sm" variant="ghost" aria-pressed={!hidden} aria-controls="chat-sources"
      sx={!hidden ? { color: "primary.main", fontWeight: FONT_WEIGHT.semibold } : null}
      onClick={() => { setHidden((v) => { writeHidden(!v); return !v; }); }}>
      참고 자료 {panelSources(panelMsg.structured).length}
    </Button>
  ) : null;

  // ── 상태 ──────────────────────────────────────────────────────────────────────────────────────────
  const starting = send.isPending || createConv.isPending;
  const progressLabel = lastMsg && lastMsg.role === "user" && lastMsg.structured && lastMsg.structured.progress
    ? lastMsg.structured.progress.label : null;
  const mascot = mascotMode({
    failed: (!!lastMsg && lastMsg.processing_status === "failed") || stalled || thread.isError,
    blocked: composerLocked, sending: starting, awaitingReply, busy, justAnswered,
    hasResult: !!lastMsg && citesSources(lastMsg.structured), composerFocused,
  });
  const notFound = !!cid && thread.isError && !items.length && thread.error && [403, 404].includes(thread.error.status);
  const emptyNode = !cid
    ? (unavailable ? <AssistantUnavailable assistant={assistant} />
      : <Welcome mode={mascot} title="무엇을 도와드릴까요?" busy={starting} onPick={prefillFromPrompt}
          help="문서, 티켓, 프로젝트, 결재, 알림, 회의록을 내 권한 안에서 찾아 답합니다. 팀 채팅 대화는 찾지 않습니다." />)
    : thread.isLoading ? <Skeleton lines={3} />
    : notFound ? (
      <ErrorState layout="region" error={thread.error} title="대화를 찾을 수 없습니다"
        help="지워졌거나 열 수 없는 대화입니다. 새 대화를 시작해 주세요."
        action={<Button onClick={() => onOpen(null)}>새 대화 시작</Button>} />
    )
    : thread.isError && !items.length ? <ErrorState layout="region" error={thread.error} onRetry={() => thread.refetch()} />
    : unavailable ? <AssistantUnavailable assistant={assistant} />
    : <Welcome mode={mascot} title="새 대화" busy={starting} onPick={prefillFromPrompt} help="아래에 질문을 입력하거나, 예시를 눌러 시작하세요." />;
  const faces = {
    assistant: <MascotPose mode="listening" place="chatBubble" decorative />,
    thinking: <MascotPose mode="thinking" place="chatBubble" decorative />,
    user: <UserAvatar person={me} name={me && me.display_name} size="md" />,
  };
  const aiQuotaDay = aiQuota.data && Array.isArray(aiQuota.data.periods)
    ? aiQuota.data.periods.find((p) => p.period === "day") : null;

  const onSelect = (id) => {
    if (id !== cid) clearDraft();
    onOpen(id);
    if (!listDocked) setSideOpen(false);
    requestAnimationFrame(() => textareaRef.current && textareaRef.current.focus());
  };
  const onNew = () => {
    clearDraft();
    onOpen(null);
    if (!listDocked) setSideOpen(false);
    requestAnimationFrame(() => textareaRef.current && textareaRef.current.focus());
  };
  const sidebar = (
    <ConversationSidebar
      headingId="chat-conv-heading"
      convs={convs} convItems={(convs.data && convs.data.items) || []} convFilter={convFilter} setConvFilter={setConvFilter}
      showArchived={showArchived} setShowArchived={setShowArchived}
      cid={cid} onSelect={onSelect} onNew={onNew}
      renameConv={renameConv} archiveConv={archiveConv} deleteConv={deleteConv} confirm={confirm} toast={toast}
      hasMoreConvs={hasMoreConvs} loadMoreConvs={loadMoreConvs} failure={ch.sidebarFailure}
      emptyTotal={emptyTotal} onArchiveEmpty={() => archiveEmpty.mutate(cid)}
    />
  );
  const columns = mode === "wide"
    ? (sourcesDocked ? `${LIST_WIDTH} minmax(0,1fr) ${SOURCES_WIDTH}` : `${LIST_WIDTH} minmax(0,1fr)`)
    : mode === "medium" ? `${LIST_WIDTH} minmax(0,1fr)` : "minmax(0,1fr)";

  return (
    <Box className="c-screen" data-workspace={fill ? "fill" : "flow"} sx={fill ? { flex: "1 1 auto", minHeight: 0 } : null}>
      <PageHeader crumbRoot="내 업무" area="AI 도우미" title="AI 도우미" actions={<Button href="#/ai">문서에서 찾기</Button>} />
      <Box
        ref={gridRef} data-chat-layout={mode} data-page-fill=""
        sx={{
          display: "grid", gridTemplateColumns: columns, gap: { xs: 1.5, md: 2 }, minWidth: 0, minHeight: 0,
          ...(fill ? { flex: "1 1 auto", gridTemplateRows: "minmax(0,1fr)" }
            : { height: { xs: CHAT_FLOW_HEIGHT_PHONE, sm: CHAT_FLOW_HEIGHT }, minHeight: "28rem" }),
        }}
      >
        {listDocked ? (
          <Card padding="none" component="section" aria-labelledby="chat-conv-heading"
            sx={{ overflow: "hidden", minHeight: 0, minWidth: 0, display: "flex", flexDirection: "column" }}>
            {sidebar}
          </Card>
        ) : null}
        <Card padding="none" component="section" aria-label="대화"
          sx={{ overflow: "hidden", minHeight: 0, minWidth: 0, display: "flex", flexDirection: "column", position: "relative" }}>
          <Box sx={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}
            {...(sideOpen && !listDocked ? { inert: "", "aria-hidden": "true" } : {})}>
            <ThreadHeader
              title={cid ? activeTitle : "새 대화"} cid={cid} archived={archived} listDocked={listDocked}
              sideOpen={sideOpen} onToggleList={() => (sideOpen ? closeSide() : setSideOpen(true))} toggleRef={toggleRef}
              renaming={renaming} setRenaming={setRenaming}
              onRename={(title) => renameConv.mutateAsync({ id: cid, title })}
              menuItems={menuItems} sourcesToggle={sourcesToggle}
            />
            <span className="sr-only" role="status" aria-live="polite">{copied}</span>
            {archived ? (
              <Box sx={{ px: { xs: 1.5, sm: 2.5 }, pt: 1.5, flexShrink: 0 }}>
                <Callout tone="info" compact
                  action={<Button size="sm" onClick={() => archiveConv.mutateAsync({ id: cid, archived: false }).then(qcRefresh, () => {})}>보관함에서 꺼내기</Button>}>
                  보관한 대화입니다. 꺼내면 대화 목록에 다시 섭니다.
                </Callout>
              </Box>
            ) : null}
            {/* 스레드 전체를 aria-live 로 감싸면 폴링마다 대화가 통째로 다시 낭독된다 — 일시 상태만 작은 라이브 영역에서 알린다. */}
            <div className="sr-only" role="status" aria-live="polite">{busy ? "답변을 처리하고 있습니다." : ""}</div>
            <div className="sr-only" role="status" aria-live="polite">{answerAnnounce}</div>
            <AnswerLinkContext.Provider value={linkCtx}>
              <MessageList
                chat={ch} variant="page" progressLabel={progressLabel} faces={faces} empty={emptyNode}
                panelDocked={mode === "wide" && !hidden} selectedAnswerId={panelMsg ? panelMsg.id : null}
                onShowSources={(id) => { setSelectedId(id); if (hidden) { setHidden(false); writeHidden(false); } }}
              />
            </AnswerLinkContext.Provider>
            <Box sx={{ borderTop: 1, borderColor: "rule", flexShrink: 0, px: { xs: 1.5, sm: 2.5 }, py: 1.5 }}>
              <Box sx={{ maxWidth: "52rem", mx: "auto" }}>
                <Composer
                  chat={ch} unavailable={unavailable} assistant={assistant}
                  ariaLabel="메시지 입력" placeholder="메시지를 입력하세요"
                  showUnavailableNotice={!!(cid && items.length)}
                  quotaLine={aiQuotaDay && aiQuotaDay.limit != null ? (
                    /* AI-44: 하루 상한이 걸려 있을 때만 보인다. */
                    <Typography sx={{ textAlign: "right", fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
                      오늘 AI 사용량 {aiQuotaDay.used}/{aiQuotaDay.limit}
                    </Typography>
                  ) : null}
                />
              </Box>
            </Box>
          </Box>
          {!listDocked ? (
            <ConversationDrawer open={sideOpen} onClose={closeSide} mobile={mobile} labelledBy="chat-conv-heading">
              {sidebar}
            </ConversationDrawer>
          ) : null}
        </Card>
        {sourcesDocked ? (
          <Card padding="none" id="chat-sources" sx={{ overflow: "hidden", minHeight: 0, minWidth: 0, display: "flex", flexDirection: "column" }}>
            <SourcesPanel
              headingId="chat-sources-heading" message={panelMsg} isLatest={!!latestAnswer && panelMsg.id === latestAnswer.id}
              activeRoute={activeRoute} onClose={() => { setHidden(true); writeHidden(true); }}
            />
          </Card>
        ) : null}
      </Box>
    </Box>
  );
}
