import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { useToast } from "../ui/kit.jsx";
import {
  STALL_MS, CHAT_LAST_CONV_KEY, LIST_DRAWER_MEDIA,
  MAX_ATTACH_BYTES, MAX_TOTAL_ATTACH_BYTES, MAX_ATTACH_COUNT, ALLOWED_IMAGE_TYPES,
  b64Bytes, downscaleImage, msgAgeMs, newClientMessageId, pollDelayMs, rateLimitNoticeText,
} from "./chat-helpers.js";

/* AI 채팅의 상태 기계 — 쿼리·뮤테이션·폴링·전송·첨부를 전부 여기서 소유한다.
 *
 * 왜 화면에서 뽑았나: 이 화면의 값어치는 대부분 '느린 러너를 상대로 어떻게 버티는가'에 있다
 * (폴링 백오프와 포기, 낙관적 전송과 롤백, 멱등키 재사용, 스톨 복구 기준선, 유지보수·속도제한
 * 배너, 인코딩 도중 대화 전환 방어). 그 로직이 말풍선 마크업과 같은 파일에 섞여 있으면
 * 디자인을 손볼 때마다 함께 위험해진다. 마크업은 Chat.jsx가, 규칙은 여기가 진다.
 *
 * 계약: 훅은 JSX를 모른다. DOM 참조(textarea/스크롤 컨테이너 등)는 훅이 만들고 화면이 붙인다 —
 * 포커스 이동·스크롤 고정·자동 높이가 전부 상태 전이의 일부라서, 화면 쪽에 두면 두 곳으로 쪼개진다.
 */

/**
 * @param {{pasteEnabled?: boolean}} [options]
 *   `pasteEnabled` — 이 대화가 지금 **화면에 보이는 컴포저**인가. 문서 전역 붙여넣기
 *   리스너를 걸지 말지를 정한다. 기본은 true(전체 화면 `/chat` 처럼 항상 보이는 경우).
 *
 *   왜 옵션이 필요한가: `AssistantDrawer` 는 셸이 항상 마운트한다(닫아도 대화가 살아
 *   있어야 하므로 `keepMounted`). 그래서 이 훅도 모든 화면에서 돌고, 문서에 건 붙여넣기
 *   리스너가 **앱 전체의 Ctrl+V 를 가로챘다.** 팀 채팅 컴포저는 `preventDefault` 만 하고
 *   전파를 막지 않으므로, 방에 보낸 스샷이 동시에 열지도 않은 AI 대화의 첨부로 담겼다.
 */
export function useChat({ pasteEnabled = true, screenContext = null } = {}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [cid, setCid] = useState(null);
  const [text, setText] = useState("");
  const [pending, setPending] = useState([]); // 전송 대기 첨부(이미지)
  const [sideOpen, setSideOpen] = useState(false); // 좁은 화면 대화목록 드로어
  const [convFilter, setConvFilter] = useState(""); // 대화 목록 제목 검색(클라이언트측 — 전체 목록은 이미 불러와 있음)
  const [showArchived, setShowArchived] = useState(false); // 보관된 대화 보기
  const [composingNew, setComposingNew] = useState(false); // '새 대화' 클릭 후 첫 메시지 전까지 실제 생성을 미룸
  const [stick, setStick] = useState(true);
  const [resumedAt, setResumedAt] = useState(0); // 스톨 복구 '새로고침'이 눌린 시각(폴링 재시작 기준선)
  // 대화 목록이 지금 '서랍'인지(열로 상주하지 않는 폭인지). 서랍일 때만 배경 inert·포커스 이동·
  // 백드롭이 필요하다 — 열로 서 있는 목록에 그걸 걸면 목록이 통째로 키보드/스크린리더에서 사라진다.
  const [listIsDrawer, setListIsDrawer] = useState(false);
  // 컴포저에 포커스가 있는지 — 마스코트 'listening' 포즈의 유일한 근거다. 앱이 실제로 있는
  // 상태만 마스코트로 옮긴다는 규칙(chat-helpers.js mascotMode)을 지키려면 이 사실이 필요하다.
  const [composerFocused, setComposerFocused] = useState(false);
  // 유지보수 모드가 켜져 있으면 서버가 전송/재시도를 503(maintenance_mode)으로 막는다(app/settings/gate.py) —
  // 이전엔 그 사실이 8초짜리 토스트 하나로만 스쳐 지나가 새 요청이 다시 시도해도 같은 이유로 계속
  // 막히는 원인을 사용자가 알 길이 없었다. 지속되는 배너로 남겨 컴포저를 잠근 이유를 계속 보여준다.
  const [maintenanceNotice, setMaintenanceNotice] = useState(null);
  // 429(속도 제한)도 유지보수 배너와 같은 이유로 지속 배너를 쓴다 — 예전엔 사라지는 토스트뿐이라
  // 계속 재시도하는 사용자는 컴포저가 왜 막혀 있는지 매번 놓쳤다. 서버가 계산해 준 대기 시간을
  // 그대로 보여준다(RateLimitedError.retry_after_seconds).
  const [rateLimitNotice, setRateLimitNotice] = useState(null);
  const bodyRef = useRef(null);
  const fileRef = useRef(null);
  const textareaRef = useRef(null);
  const asideRef = useRef(null); // 드로어 열릴 때 포커스를 옮길 대상(a11y)
  const sideToggleRef = useRef(null); // 드로어를 닫을 때 포커스를 되돌릴 트리거 버튼(a11y)
  const sendingRef = useRef(false); // doSend 재진입(이중 제출) 방지 — 생성→전송 창 포함
  const pickFilesRef = useRef(null); // 붙여넣기 리스너가 항상 최신 pickFiles를 부르도록
  const draftMsgIdRef = useRef(null); // 작성 중인 초안의 멱등키 — 전송 실패 후 재전송에 같은 키를 재사용
  const retryingRef = useRef(null); // 재시도 이중 클릭 방지 — retry.isPending은 다음 렌더까지 반영이 늦어(비동기), 그 사이 두 번 클릭하면 중복 요청이 나간다
  const cidRef = useRef(null); // pickFiles의 비동기 인코딩이 끝난 시점의 '지금' cid를 읽기 위한 라이브 참조
  useEffect(() => { cidRef.current = cid; }, [cid]);
  // 컴포저 textarea 자동 높이 — text가 바뀔 때마다(첫 글자·붙여넣기·초안 복구·전송 후 비움 포함)
  // 같은 기준으로 다시 계산한다. 예전엔 onChange 인라인 + 여러 rAF에 흩어져 있어, 빈 입력창(rows=1)과
  // 첫 입력 사이에 높이가 튀어 보였다. useLayoutEffect라 페인트 전에 확정돼 깜빡임이 없다.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [text]);
  const pollFailRef = useRef(0); // 스레드 폴링 연속 실패 횟수(백오프·중단 판단용)
  // 이전 대화(A)에서 쌓인 연속 실패 횟수가 새로 연 대화(B)로 그대로 넘어오면, B의 첫 폴링이 단
  // 한 번만 실패해도(일시적 blip) 이미 5 이상인 카운터 때문에 refetchInterval이 즉시 자동 폴링을
  // 멈춰 버린다 — 대화를 바꿀 때마다 카운터를 새로 시작한다.
  useEffect(() => { pollFailRef.current = 0; }, [cid]);

  const convs = useQuery({
    queryKey: ["conversations", showArchived],
    queryFn: () => api("/api/conversations" + (showArchived ? "?include_archived=true" : "")),
    retry: false,
  });
  const thread = useQuery({
    queryKey: ["messages", cid],
    // 연속 폴링 실패 횟수를 추적한다(성공하면 0으로 리셋) — 아래 refetchInterval이 이 값으로
    // 백오프하거나 완전히 멈춘다. 워커/네트워크가 살아 있는 정상 실패(간헐적 5xx 등)와, 죽은
    // 서버에 무한히 재시도하는 것을 구분한다(바닐라 chat.js의 POLL_MAX_FAILURES와 같은 취지).
    queryFn: async () => {
      try {
        const res = await api("/api/conversations/" + cid + "/messages");
        pollFailRef.current = 0;
        return res;
      } catch (e) {
        pollFailRef.current += 1;
        throw e;
      }
    },
    enabled: !!cid,
    retry: false,
    refetchInterval: (q) => {
      const items = q.state.data && q.state.data.items;
      if (!Array.isArray(items) || !items.length) return false;
      const busy = items.some((m) => m.processing_status === "pending" || m.processing_status === "processing");
      // 답변이 폴링 사이에 도착해 "처리 중" 상태를 못 보고 지나칠 수 있다. 마지막이 사용자
      // 메시지면(아직 어시스턴트 답이 없음) 계속 폴링해 답변이 뜰 때까지 UI를 갱신한다.
      const last = items[items.length - 1];
      const awaiting = last && last.role === "user" && last.processing_status !== "failed";
      // 워커가 죽어 메시지가 'processing'에 얼어붙으면 영원히 폴링하던 문제 — 지연이 임계값을
      // 넘으면 자동 폴링을 멈춘다(사용자는 '새로고침'으로 수동 갱신).
      const inflight = busy ? [...items].reverse().find((m) => m.processing_status === "pending" || m.processing_status === "processing") : (awaiting ? last : null);
      if (inflight && msgAgeMs(inflight, resumedAt) > STALL_MS) return false;
      if (!(busy || awaiting)) return false;
      // 백오프·포기 규칙은 pollDelayMs 하나가 소유한다(chat-helpers.js) — 예전엔 이 콜백 안에
      // 인라인 산술로 있어서 가짜 타이머로 검증할 방법이 없었다.
      return pollDelayMs(pollFailRef.current);
    },
  });
  const items = (thread.data && thread.data.items) || [];
  // 스레드 전체를 aria-live로 감싸면 1.5초 폴링마다 대화가 통째로 다시 낭독된다.
  // 스레드에서 aria-live를 걷어내고, '처리 중' 같은 일시 상태만 작은 라이브 영역에서 알린다.
  const rawBusy = items.some((m) => m.processing_status === "pending" || m.processing_status === "processing");
  // 마지막이 사용자 메시지면(아직 어시스턴트 답 없음) 왼쪽에 어시스턴트 타이핑 말풍선을 띄운다.
  const lastMsg = items.length ? items[items.length - 1] : null;
  const rawAwaitingReply = !!lastMsg && lastMsg.role === "user" && lastMsg.processing_status !== "failed";
  // 처리 중 메시지가 임계 시간을 넘겼는지(폴링 중단·지연 안내에 사용).
  const inflightMsg = rawBusy ? [...items].reverse().find((m) => m.processing_status === "pending" || m.processing_status === "processing") : (rawAwaitingReply ? lastMsg : null);
  const stalled = !!inflightMsg && msgAgeMs(inflightMsg, resumedAt) > STALL_MS;
  // 지연이 STALL_MS를 넘기면 컴포저를 영구히 잠그지 않는다 — stalled 메시지는 busy/awaitingReply
  // 판정에서 제외해, '새로고침'을 누르지 않아도 사용자가 새 메시지를 작성·전송할 수 있게 한다
  // (이전엔 응답이 영영 오지 않으면 컴포저가 다시는 안 열리는 막다른 상태가 됐다).
  const busy = rawBusy && !stalled;
  const awaitingReply = rawAwaitingReply && !stalled;
  // 현재 대화 제목(좁은 화면에선 드로어가 닫혀 어느 대화인지 모른다) — 목록 캐시 우선, 없으면 스레드 응답.
  const activeConv = ((convs.data && convs.data.items) || []).find((c) => c.id === cid);
  const activeTitle = (activeConv && activeConv.title) || (thread.data && thread.data.conversation && thread.data.conversation.title) || "새 대화";
  // 도착한 답변을 스크린리더에 한 번 알린다(스레드 자체엔 aria-live를 두지 않아 폴링마다 재낭독되지 않음).
  const answered = !busy && !awaitingReply && !!lastMsg && lastMsg.role === "assistant" && !!lastMsg.content && lastMsg.processing_status !== "failed";
  const answerAnnounce = answered ? "답변이 도착했습니다." : "";

  /* '방금 답이 도착했다'는 짧은 창 — 마스코트의 responding/success 포즈는 이 안에서만 준다.
   * answered만 보고 포즈를 정하면, 옛 대화를 열어 스크롤만 하고 있어도 마스코트가 영원히
   * "답하는 중"으로 떠 있다. 그건 앱이 있지도 않은 상태를 연기하는 것이라 마스코트를 다시
   * 장식으로 되돌리는 짓이다(chat-helpers.js mascotMode 주석).
   * 처음 관찰(화면을 열며 이미 있던 답변)은 '도착'이 아니므로 건너뛰고 기준만 잡는다. */
  const [justAnswered, setJustAnswered] = useState(false);
  const answeredIdRef = useRef(null);
  const lastId = lastMsg ? lastMsg.id : null;
  useEffect(() => { answeredIdRef.current = null; setJustAnswered(false); }, [cid]);
  useEffect(() => {
    if (!answered || !lastId || answeredIdRef.current === lastId) return undefined;
    const first = answeredIdRef.current === null;
    answeredIdRef.current = lastId;
    if (first) return undefined;   // 열자마자 이미 있던 마지막 답변 — 방금 온 게 아니다
    setJustAnswered(true);
    const t = setTimeout(() => setJustAnswered(false), 2600);
    return () => clearTimeout(t);
  }, [answered, lastId]);

  const send = useMutation({
    // client_message_id는 서버가 필수로 요구한다(멱등·중복 방지). 8~64자. 첨부는 있을 때만.
    // screenContext(AssistantDrawer가 넘기는 routeContextLabel)는 이 서랍이 "현재 문맥: X"라고
    // 화면에 약속해 놓고도 실제로는 아무 데도 안 보내던 것을 고친 자리다(AI-30) — 전체화면
    // /chat에는 배경 화면이라는 개념이 없어 null로 둔다.
    mutationFn: ({ id, content, clientMessageId, attachments }) => api("/api/conversations/" + id + "/messages", { method: "POST", body: { content, client_message_id: clientMessageId, attachments: attachments && attachments.length ? attachments : undefined, screen_context: screenContext || undefined } }),
    // 낙관적 에코 — 보낸 메시지를 서버 왕복 전에 즉시 스레드에 띄운다(빈 화면 체감 제거).
    // 진행 중 폴링이 낙관적 항목을 덮어쓰지 않도록 cancelQueries로 먼저 멈춘다.
    onMutate: async ({ id, content, clientMessageId, attachments }) => {
      await qc.cancelQueries({ queryKey: ["messages", id] });
      const prev = qc.getQueryData(["messages", id]);
      const echo = {
        id: "tmp-" + clientMessageId, role: "user",
        // 서버는 이미지만 있고 본문이 빈 전송을 "(이미지 첨부)" 플레이스홀더로 치환해 저장한다
        // (app/chat/service.py). 낙관적 에코가 빈 content를 그대로 쓰면 <Message>가 <p>를 아예 안 그려
        // 첨부 칩만 남았다가, 후속 무효화로 서버 값이 오는 순간 말풍선에 문구가 갑자기 나타나는
        // 눈에 띄는 깜빡임이 생긴다 — 처음부터 서버와 같은 문구로 에코한다.
        content: content || (attachments && attachments.length ? "(이미지 첨부)" : content),
        processing_status: "done",
        structured: attachments && attachments.length ? { attachments: attachments.map((a) => a.filename) } : undefined,
      };
      qc.setQueryData(["messages", id], (old) => ({ ...(old || {}), items: [...((old && old.items) || []), echo] }));
      return { prev, id };
    },
    onError: (_e, _vars, ctx) => { if (ctx) qc.setQueryData(["messages", ctx.id], ctx.prev); },
    // 새 대화의 첫 메시지는 cid 상태가 아직 반영 전이라 closure의 cid가 낡을 수 있다.
    // 변이 변수의 id로 무효화해 정확한 스레드를 갱신한다.
    onSuccess: (_d, vars) => { qc.invalidateQueries({ queryKey: ["messages", vars.id] }); qc.invalidateQueries({ queryKey: ["conversations"] }); },
  });
  const renameConv = useMutation({
    mutationFn: ({ id, title }) => api("/api/conversations/" + id, { method: "PATCH", body: { title } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
    onError: (e) => toast(e.message || "이름을 바꾸지 못했습니다.", "error"),
  });
  const archiveConv = useMutation({
    mutationFn: ({ id, archived }) => api("/api/conversations/" + id, { method: "PATCH", body: { archived } }),
    // 현재 목록 캐시에서 즉시 반영한다. 그렇지 않으면 방금 보관한 대화가 stale 캐시에 남아
    // 자동 선택 이펙트가 그것을 다시 열어(보이지 않는 대화에 입력하는) 막다른 길이 된다.
    onSuccess: (_d, vars) => {
      // 지금 열려 있던 대화가 보관되면 그 대화용 초안(글+첨부)도 함께 비운다 — 안 그러면 뒤이어
      // 자동 선택된 다른 대화(또는 빈 화면)에 이 대화의 초안이 그대로 남아 엉뚱한 곳에 전송될 수 있다.
      if (vars.archived && vars.id === cid) { setCid(null); clearDraft(); }
      qc.setQueryData(["conversations", showArchived], (old) => {
        if (!old || !Array.isArray(old.items)) return old;
        if (!showArchived && vars.archived) return { ...old, items: old.items.filter((c) => c.id !== vars.id) };
        return { ...old, items: old.items.map((c) => (c.id === vars.id ? { ...c, archived: vars.archived } : c)) };
      });
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
    onError: (e) => toast(e.message || "보관 상태를 바꾸지 못했습니다.", "error"),
  });
  const deleteConv = useMutation({
    mutationFn: (id) => api("/api/conversations/" + id, { method: "DELETE", body: {} }),
    // 삭제한 행을 캐시에서 곧바로 제거한다(단순 invalidate만 하면 refetch 전까지 stale 목록이
    // 남아 자동 선택 이펙트가 방금 삭제한 대화를 다시 열어 404 '대화를 찾을 수 없습니다'로 갇힌다).
    onSuccess: (_d, id) => {
      // 삭제한 대화가 지금 열려 있던 대화면 그 초안도 함께 비운다(보관과 동일한 이유 — 위 archiveConv 참고).
      if (id === cid) { setCid(null); clearDraft(); }
      qc.setQueryData(["conversations", showArchived], (old) =>
        old && Array.isArray(old.items) ? { ...old, items: old.items.filter((c) => c.id !== id) } : old);
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
    onError: (e) => toast(e.message || "삭제하지 못했습니다.", "error"),
  });

  async function pickFiles(fileList) {
    // 인코딩(downscaleImage)은 비동기라 그 사이 사용자가 다른 대화로 전환할 수 있다 — 시작 시점의
    // cid를 남겨 두고, 끝날 때 지금 cid(cidRef, 라이브 참조)와 다르면 결과를 버린다. 안 그러면
    // A 대화에서 고른 이미지가 뒤늦게 B 대화의 컴포저에 나타나 엉뚱한 곳으로 전송될 수 있다.
    const startCid = cid;
    const files = Array.from(fileList || []);
    // 서버 상한(개당 3MB·합계 6MB·최대 3장·PNG/JPEG/WebP)을 왕복 전에 검사하되, 크기 검사는
    // 반드시 축소 뒤에 한다 — 폰 사진·스샷은 원본이 3MB를 쉽게 넘지만 축소하면 대부분 통과한다.
    const next = [...pending];   // 로컬 스냅숏(상태는 마지막에 한 번만 갱신 — 불변성 유지)
    let total = next.reduce((n, a) => n + b64Bytes(a.data), 0);
    // 거절 사유를 모아 한 번에 알린다 — 3장을 한꺼번에 넣으면 개별 토스트가 겹쳐 쌓이던 문제(바닐라처럼 통합).
    const badType = [], tooBig = [], failed = [];
    let hitCount = false, hitTotal = false;
    for (const f of files) {
      if (!ALLOWED_IMAGE_TYPES.includes(f.type)) { badType.push(f.name || "이미지"); continue; }
      if (next.length >= MAX_ATTACH_COUNT) { hitCount = true; break; }
      try {
        const enc = await downscaleImage(f);
        const bytes = b64Bytes(enc.data);
        if (bytes > MAX_ATTACH_BYTES) { tooBig.push(f.name || "이미지"); continue; }
        if (total + bytes > MAX_TOTAL_ATTACH_BYTES) { hitTotal = true; break; }
        next.push({ filename: (f.name || "capture.jpg").slice(0, 120), media_type: enc.media_type, data: enc.data });
        total += bytes;
      } catch (e) { failed.push(f.name || "이미지"); }
    }
    if (fileRef.current) fileRef.current.value = "";
    if (cidRef.current !== startCid) return;   // 인코딩 도중 다른 대화로 전환됨 — 이 결과는 버린다
    setPending(next);
    const reasons = [];
    if (badType.length) reasons.push("PNG, JPEG, WebP 이미지만 첨부할 수 있습니다(" + badType.join(", ") + ")");
    if (tooBig.length) reasons.push("축소 후에도 3MB를 넘어 제외(" + tooBig.join(", ") + ")");
    if (hitCount) reasons.push("이미지는 최대 " + MAX_ATTACH_COUNT + "장까지 첨부할 수 있습니다");
    if (hitTotal) reasons.push("첨부 이미지 전체 용량은 6MB를 넘을 수 없습니다");
    if (failed.length) reasons.push("처리하지 못한 이미지(" + failed.join(", ") + ")");
    if (reasons.length) toast(reasons.join(", "), "error");
  }
  pickFilesRef.current = pickFiles;
  // 재시도는 전용 엔드포인트로 같은 메시지를 다시 처리한다(새 메시지 생성·첨부 유실 방지).
  // conversationId는 클릭 시점의 cid를 변수로 함께 넘긴다 — onSuccess의 클로저 cid를 그대로 쓰면
  // (send 뮤테이션이 겪었던 것과 같은 문제) 재시도가 진행되는 사이 사용자가 다른 대화로 전환했을 때
  // 엉뚱한 대화의 캐시를 무효화한다(vars로 넘긴 값은 요청 시점 그대로 남는다 — send의 vars.id와 동일 패턴).
  const retry = useMutation({
    mutationFn: ({ messageId }) => api("/api/messages/" + messageId + "/retry", { method: "POST", body: {} }),
    onSuccess: (_d, vars) => { qc.invalidateQueries({ queryKey: ["messages", vars.conversationId] }); qc.invalidateQueries({ queryKey: ["conversations"] }); },
    onError: (e) => {
      // 세션 만료(401)면 다른 모든 401 경로(doSend·FormModal·DataScreen·Users)와 동일하게 로그인으로
      // 보낸다 — 예전엔 이 분기가 없어 '다시 시도' 중 세션이 끊기면 토스트만 뜨고 복구 경로가 없었다.
      if (e && e.status === 401) { window.location.href = "/login"; return; }
      if (e && e.status === 503 && e.body && e.body.error && e.body.error.code === "maintenance_mode") {
        setMaintenanceNotice((e.body.error && e.body.error.message) || "시스템 점검 중에는 새 요청이 차단됩니다. 잠시 후 다시 시도하세요.");
        return;
      }
      if (e && e.status === 429) { setRateLimitNotice(rateLimitNoticeText(e)); return; }
      toast(e.message || "다시 시도하지 못했습니다.", "error");
    },
    onSettled: () => { retryingRef.current = null; },
  });
  // 클릭 즉시(동기적으로) 같은 메시지의 재시도를 막는다 — retry.isPending은 다음 렌더까지 반영이
  // 늦어(비동기 React 상태), 그 창 안에 두 번 클릭하면 같은 메시지에 중복 재시도 요청이 나간다.
  function doRetry(m) {
    if (retryingRef.current === m.id) return;
    retryingRef.current = m.id;
    retry.mutate({ messageId: m.id, conversationId: cid });
  }
  const createConv = useMutation({
    mutationFn: () => api("/api/conversations", { method: "POST", body: {} }),
    onSuccess: (d) => { const id = d.conversation ? d.conversation.id : d.id; setCid(id); qc.invalidateQueries({ queryKey: ["conversations"] }); },
    // onError 토스트는 두지 않는다 — doSend의 catch가 이미 한 번 알린다(이중 토스트 방지).
  });

  // 새로고침 후에도 보던 대화를 이어서 연다 — 그냥 items[0](최신순 맨 위)을 열면, 최근에 손댄 적
  // 없는 옛 대화를 읽던 사용자가 새로고침 때마다 엉뚱한(가장 최근에 '바뀐') 대화로 튕겨나간다.
  // sessionStorage에 남겨 둔 id가 아직 목록에 있으면 그걸 열고, 없으면(삭제·다른 세션) items[0]로 폴백한다.
  useEffect(() => {
    if (!cid && !composingNew && convs.data && convs.data.items && convs.data.items.length) {
      let restoreId = null;
      try { restoreId = window.sessionStorage.getItem(CHAT_LAST_CONV_KEY); } catch (e) { /* 비보안 컨텍스트 등 */ }
      const found = restoreId && convs.data.items.find((c) => c.id === restoreId);
      setCid(found ? found.id : convs.data.items[0].id);
      // 대화 복원 직후 컴포저에 포커스를 둔다 — 키보드 사용자가 매번 직접 클릭해 들어가지 않아도 되게.
      textareaRef.current && textareaRef.current.focus();
    }
  }, [convs.data, cid, composingNew]);

  // 현재 열린 대화 id를 남겨 새로고침 후 복원에 쓴다(위 이펙트). 대화가 없으면(새 대화 작성 중 등) 지운다.
  useEffect(() => {
    try {
      if (cid) window.sessionStorage.setItem(CHAT_LAST_CONV_KEY, cid);
      else window.sessionStorage.removeItem(CHAT_LAST_CONV_KEY);
    } catch (e) { /* 비보안 컨텍스트 등 — 복원은 best-effort */ }
  }, [cid]);

  // 대화목록 드로어는 Esc로도 닫히게 한다(백드롭 탭 외 키보드 탈출구 제공).
  useEffect(() => {
    if (!sideOpen) return undefined;
    const onKey = (e) => { if (e.key === "Escape") closeSideDrawer(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [sideOpen]);

  // 서랍이 열리면 포커스를 그 안으로 옮긴다(열기 전엔 배경의 토글 버튼에 있었다) — 닫힘 상태에
  // inert를 걸던 것과 짝을 맞춰, 열림 상태에선 배경(스레드 열)을 inert 처리하고, 닫을 때는
  // 트리거 버튼으로 포커스를 되돌린다(closeSideDrawer).
  useEffect(() => {
    if (!listIsDrawer || !sideOpen) return;
    const el = asideRef.current;
    const first = el && el.querySelector("button, [href], input, [tabindex]:not([tabindex='-1'])");
    if (first) first.focus();
  }, [listIsDrawer, sideOpen]);
  function closeSideDrawer() {
    setSideOpen(false);
    if (listIsDrawer) requestAnimationFrame(() => { sideToggleRef.current && sideToggleRef.current.focus(); });
  }

  // 서랍/열 판정 — 닫힌 서랍은 화면 밖으로 밀려 있을 뿐 DOM에 남아 있어 키보드/스크린리더가
  // 여전히 도달한다. 서랍이고 닫혀 있으면 aside를 inert 처리한다(화면 쪽에서). 경계는 화면의
  // 그리드와 같은 상수를 쓴다(chat-helpers.js LIST_DOCK_PX).
  useEffect(() => {
    const mq = window.matchMedia(LIST_DRAWER_MEDIA);
    const on = () => setListIsDrawer(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  // 스샷 붙여넣기(Ctrl+V) — 클립보드의 이미지 파일을 컴포저로 바로 넣는다(가장 자연스러운 첨부).
  // 보이지 않는 컴포저는 붙여넣기를 가져가면 안 된다(위 pasteEnabled 주석) — 그때는 리스너를
  // 아예 걸지 않는다. 걸어 두고 안에서 무시하면 preventDefault 가 이미 나간 뒤라 늦다.
  useEffect(() => {
    if (!pasteEnabled) return undefined;
    const onPaste = (e) => {
      if (!e.clipboardData || !e.clipboardData.files || !e.clipboardData.files.length) return;
      const imgs = [];
      for (let i = 0; i < e.clipboardData.files.length; i++) {
        const f = e.clipboardData.files[i];
        if (f.type && f.type.indexOf("image/") === 0) imgs.push(f);
      }
      if (imgs.length && pickFilesRef.current) { e.preventDefault(); pickFilesRef.current(imgs); }
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [pasteEnabled]);

  useEffect(() => {
    if (stick && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [items, stick]);

  function onScroll() {
    const el = bodyRef.current;
    if (!el) return;
    setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 120);
  }

  // 대화를 바꾸거나 새 대화를 시작할 때 컴포저 초안을 비운다 — 초안(글+첨부)이 전역이라, 안 비우면
  // A 대화용으로 쓰던 초안이 B 대화(또는 새 대화)로 따라와 실수로 엉뚱한 곳에 전송될 수 있다.
  function clearDraft() {
    setText(""); setPending([]);
    draftMsgIdRef.current = null;   // 새 스레드의 첫 메시지는 새 멱등키를 쓰게 초기화
    setResumedAt(0);   // 스톨 복구 기준선도 새 스레드 기준으로 초기화(다른 대화의 낡은 기준선이 새지 않게)
    // 스레드 스크롤 컨테이너는 대화를 바꿔도 리마운트되지 않는 같은 DOM 노드다 — 이전 대화에서
    // 스크롤을 올려 stick=false가 된 채로 남아 있으면, 다음에 여는 대화(짧든 길든)가 맨 위에
    // 멈춰 보인다. 대화를 바꿀 때마다 '맨 아래 고정'을 다시 기본값으로 되돌린다.
    setStick(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  // 시작 예시 칩은 즉시 전송하지 않고 컴포저에 채운다(USER_GUIDE.md가 문서화한 동작) — 사용자가
  // 문장을 고치거나 맥락을 더할 기회 없이 바로 새 대화로 전송돼 버리던 문제.
  function prefillFromPrompt(p) {
    setText(p);   // 높이 자동조정은 text 변화에 반응하는 useLayoutEffect가 담당한다.
    requestAnimationFrame(() => { textareaRef.current && textareaRef.current.focus(); });
  }

  async function doSend(content) {
    if (sendingRef.current) return;   // 이중 제출 방지(생성→전송 사이 창 포함)
    const value = (content != null ? content : text).trim();
    const fromComposer = content == null;
    const atts = fromComposer ? pending : [];
    // 어시스턴트가 아직 이번 턴을 처리 중이면(busy/awaitingReply) 컴포저에서 새 메시지를 못 보내게 막는다 —
    // 안 막으면 겹치는 러너 작업이 생겨 맥락이 뒤섞인 답이 나온다. 선택 버튼/카드 '상세'(fromComposer=false)는
    // 그 턴에 한정된 원탭이라 sending(=send.isPending) 하나로 충분히 막혀 있어 그대로 둔다.
    if ((!value && !atts.length) || send.isPending) return;
    // 컴포저 placeholder는 'Enter 전송'을 약속하지만, 답변이 오는 동안 textarea 자체는 계속
    // 활성 상태라 키보드 사용자가 Send 버튼의 disabled 상태를 못 보고 조용히 씹히는 Enter를
    // 칠 수 있었다 — 여기서 이유를 한 줄로 알린다.
    // 이 가드는 컴포저뿐 아니라 선택 버튼·카드 '상세'(fromComposer=false)에도 적용한다 — 안 그러면
    // 재시도로 다른 메시지가 'pending'인 동안에도 선택/카드 클릭이 겹치는 러너 작업을 만들어 낼 수 있다.
    if (busy || awaitingReply) { toast("답변을 기다리는 중입니다."); return; }
    if (fromComposer && maintenanceNotice) { toast("시스템 점검 중에는 새 요청을 보낼 수 없습니다."); return; }
    if (fromComposer && rateLimitNotice) { toast("요청이 너무 잦습니다. 잠시 후 다시 시도하세요."); return; }
    sendingRef.current = true;
    if (fromComposer) {
      setText(""); setPending([]);   // 낙관적 비우기 — 실패하면 복구
      // 자동 확장된 textarea 높이를 되돌린다(안 하면 전송 후 빈 입력창이 계속 커진 채 남는다).
      if (textareaRef.current) textareaRef.current.style.height = "auto";
    }
    setStick(true);
    // 컴포저 초안은 초안당 하나의 멱등키를 쓴다 — 응답이 유실돼 재전송할 때 같은 키를 재사용해야
    // 서버 dedup(client_message_id)이 동작해 이중 기록/이중 쓰기(WRITE)를 막는다. 성공해야 새 키를 발급.
    const clientMessageId = fromComposer
      ? (draftMsgIdRef.current || (draftMsgIdRef.current = newClientMessageId()))
      : newClientMessageId();
    let createdId = null;   // 이번 전송을 위해 방금 생성한 대화 id(첫 전송 실패 시 정리 대상)
    try {
      let id = cid;
      if (!id) { const d = await createConv.mutateAsync(); id = d.conversation ? d.conversation.id : d.id; createdId = id; }
      setComposingNew(false);
      await send.mutateAsync({ id, content: value, clientMessageId, attachments: atts });
      if (fromComposer) draftMsgIdRef.current = null;   // 확정 성공 후에만 초안 키를 비운다
      // 새 대화가 방금 생성된 경우, 컴포저에 포커스를 되돌려 곧바로 이어 입력할 수 있게 한다.
      if (fromComposer) textareaRef.current && textareaRef.current.focus();
    } catch (e) {
      // 세션 만료(401)는 다른 화면(ErrorState)과 같은 로그인 복구 동작으로 통일한다 — 8초 뒤
      // 사라지는 토스트 하나에만 기대면, 대화 중 세션이 끊긴 사용자는 무엇이 잘못됐는지 놓치기 쉽다.
      if (e && e.status === 401) { window.location.href = "/login"; return; }
      // 첫 전송(대화를 방금 만든 경우)이 실패하면 메시지 0개짜리 '새 대화'가 목록에 남아 어지럽힌다 —
      // 조용히 정리한다(초안은 아래에서 컴포저에 복구하므로 같은 내용으로 곧바로 다시 보낼 수 있다).
      // deleteConv 뮤테이션은 쓰지 않는다 — 그 onSuccess가 clearDraft()로 방금 복구한 초안을 지운다.
      if (createdId) {
        const orphan = createdId;
        setCid(null);
        qc.setQueryData(["conversations", showArchived], (old) =>
          old && Array.isArray(old.items) ? { ...old, items: old.items.filter((c) => c.id !== orphan) } : old);
        api("/api/conversations/" + orphan, { method: "DELETE", body: {} }).then(
          () => qc.invalidateQueries({ queryKey: ["conversations"] }), () => {});
      }
      if (fromComposer) {
        setText(value); setPending(atts);   // 입력, 첨부 복구(유실 방지), 높이는 useLayoutEffect가 다시 계산.
      }
      // 유지보수 모드 차단(503)은 사라지는 토스트 대신 지속 배너로 알리고 컴포저를 잠근다, 아래
      // 배너의 '다시 시도' 버튼을 눌러야만 다시 입력할 수 있다(다음 요청도 여전히 막혀 있으면 배너가
      // 다시 뜬다).
      if (e && e.status === 503 && e.body && e.body.error && e.body.error.code === "maintenance_mode") {
        setMaintenanceNotice((e.body.error && e.body.error.message) || "시스템 점검 중에는 새 요청이 차단됩니다. 잠시 후 다시 시도하세요.");
      } else if (e && e.status === 429) {
        setRateLimitNotice(rateLimitNoticeText(e));
      } else {
        toast(e.message || "메시지를 보내지 못했습니다.", "error");
      }
    } finally {
      sendingRef.current = false;
    }
  }

  // 화면이 '지금 무엇을 눌러도 되는가'를 한 값으로 묻게 한다 — 예전엔 이 다섯 항의 논리합이
  // 전송·첨부·선택 버튼마다 손으로 복제돼 있어 한 곳만 고치면 조용히 어긋났다.
  const composerLocked = !!maintenanceNotice || !!rateLimitNotice;
  const sending = send.isPending || createConv.isPending || busy || awaitingReply || !!retryingRef.current;
  const inputDisabled = send.isPending || createConv.isPending || busy || awaitingReply || composerLocked;

  return {
    // 대화 선택·목록
    cid, setCid, convs, convFilter, setConvFilter, showArchived, setShowArchived,
    composingNew, setComposingNew, activeTitle,
    renameConv, archiveConv, deleteConv,
    // 스레드
    thread, items, busy, awaitingReply, stalled, answered, justAnswered, answerAnnounce, lastMsg,
    resumedAt, setResumedAt,
    // 컴포저
    text, setText, pending, setPending, composerFocused, setComposerFocused,
    maintenanceNotice, setMaintenanceNotice, rateLimitNotice, setRateLimitNotice,
    send, createConv, retry, retryingRef,
    doSend, doRetry, pickFiles, clearDraft, prefillFromPrompt,
    composerLocked, sending, inputDisabled,
    // 레이아웃·스크롤·드로어
    stick, setStick, onScroll, sideOpen, setSideOpen, closeSideDrawer, listIsDrawer,
    // DOM 참조(화면이 붙인다)
    bodyRef, fileRef, textareaRef, asideRef, sideToggleRef,
  };
}
