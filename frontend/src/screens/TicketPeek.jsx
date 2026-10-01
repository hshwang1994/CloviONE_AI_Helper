import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { api } from "../lib/api.js";
import { Button, Callout, ErrorState, MetaBar, Modal, Skeleton, ActionFooter, SectionTitle } from "../ui/kit.jsx";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { useTicketSignals } from "../lib/ticketSignals.js";
import { TicketEditModal } from "./MyTickets.jsx";
import { ticketMetaItems } from "./ticket-meta.jsx";
import { invalidateTicketViews } from "./ticket-views.js";

/* 티켓 **미리보기** — 작업 보드와 스프린트 회의가 같은 창을 연다 (D-483).
 *
 * ## 왜 상세로 안 보내는가
 *
 * 카드를 누르면 상세 화면으로 갔다. 그 순간 팀·회차·필터·탭·열의 스크롤·작성 중인
 * 회의록이 전부 화면 밖으로 나갔고, 「목록」은 내 티켓으로 떨어졌다. 회의 중에 티켓 하나를
 * 확인하는 일은 **그 화면을 떠나는 일이 아니다** — 지금 보던 자리 위에 잠깐 여는 것이다.
 *
 * ## 주소와 히스토리
 *
 * 열린 미리보기는 주소의 `peek` 이다(`useQueryState` — 주소가 유일한 진실). 여는 것은
 * **push** 라서 뒤로가기 한 번이 미리보기를 닫는다(모달 위에서 뒤로가기가 화면을 통째로
 * 떠나는 것이 가장 흔한 함정이다). 닫기 단추·Esc 는 우리가 밀어 넣은 그 항목을 **되돌린다**
 * (`-1`) — `peek` 없는 주소를 다시 push 하면 뒤로가기가 미리보기를 다시 열어 준다.
 * 딥링크로 `?peek=` 채로 들어온 경우는 되돌릴 항목이 없으므로 그때만 replace 다.
 *
 * 「티켓 상세 보기」는 현재 항목(미리보기)을 상세로 **갈아 끼운다**(replace). 그래야 상세에서
 * 뒤로가기·「목록」 한 번에 **미리보기 없는 원래 화면**으로 돌아온다 — 목록의 기억
 * (`useListMemory`)은 `peek` 을 빼고 적으므로 스크롤도 그대로다.
 *
 * ## 무엇을 보여 주나
 *
 * 상세의 속성 줄(`ticket-meta.jsx` — 같은 표)과 설명의 앞부분, 그리고 이 회차 안에서 할 수
 * 있는 일(빠른 수정 · 현재 회차에서 빼기). 본문 편집·댓글·첨부·이력은 상세의 일이다 — 그것
 * 까지 여기 넣으면 미리보기가 상세의 두 번째 사본이 된다. */

/** 미리보기 상태 훅 — `useQueryState` 의 `[state, setState]` 위에 얹는다. */
export function useTicketPeek(state, setState) {
  const navigate = useNavigate();
  const pushedRef = React.useRef(false);
  const pageId = state.peek || "";
  React.useEffect(() => {
    if (!pageId) pushedRef.current = false;
  }, [pageId]);

  const open = React.useCallback((cardOrId) => {
    const id = typeof cardOrId === "string" ? cardOrId : (cardOrId && (cardOrId.page_id || cardOrId.ticket_page_id));
    if (!id) return;
    pushedRef.current = true;
    setState({ peek: id }, { push: true });
  }, [setState]);

  const close = React.useCallback(() => {
    if (pushedRef.current) {
      pushedRef.current = false;
      navigate(-1);
      return;
    }
    setState({ peek: "" });
  }, [navigate, setState]);

  const detail = React.useCallback((id, from) => {
    const target = id || pageId;
    if (!target) return;
    const replace = pushedRef.current;
    pushedRef.current = false;
    navigate(`/tickets/${encodeURIComponent(target)}`, { state: { from }, replace });
  }, [navigate, pageId]);

  return { pageId, open, close, detail };
}

/** 설명의 앞부분 — 미리보기는 요약이지 본문이 아니다. */
const PREVIEW_CHARS = 600;

function previewText(markdown) {
  const text = String(markdown || "").replace(/\r/g, "").trim();
  if (!text) return "";
  return text.length > PREVIEW_CHARS ? `${text.slice(0, PREVIEW_CHARS).trimEnd()}…` : text;
}

/** 미리보기 창 하나.
 *
 * props
 *   `pageId`     열 티켓(주소의 `peek`). 비면 안 그린다
 *   `onClose`    닫기(위 훅의 `close`)
 *   `onDetail`   「티켓 상세 보기」(위 훅의 `detail`)
 *   `from`       상세의 「목록」이 돌아올 화면 키(`/work-board` · `/sprint`)
 *   `sprints`    회차 목록 — 이 티켓이 어느 회차에 있는지 이름으로 말하려고
 *   `actions`    회차 안에서 할 수 있는 일 `[{ key, label, onClick, tone, disabled }]`
 *   `quickEdit`  빠른 수정을 열 수 있는가(편집 권한). 기본 참
 *   `projectScope` 빠른 수정의 프로젝트 후보를 좁힐 팀 `{ teamId, note }`
 */
export function TicketPeek({ pageId, onClose, onDetail, from, sprints, actions, quickEdit = true, projectScope }) {
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);
  const signalsOf = useTicketSignals();
  // 상세 화면과 **같은 키**다 — 미리보기에서 읽은 것이 상세에서 곧바로 캐시로 서고,
  // 상세에서 고친 것이 돌아온 미리보기에도 그대로다.
  const detail = useQuery({
    queryKey: ["ticket", pageId],
    queryFn: () => api("/api/tickets/" + encodeURIComponent(pageId)),
    enabled: !!pageId,
    retry: false,
  });
  const data = detail.data || {};
  const t = data.ticket || null;
  const sprint = t && t.sprint_id && Array.isArray(sprints)
    ? sprints.find((s) => s && s.id === t.sprint_id) || null
    : null;
  const title = t ? `${t.key ? `${t.key} ` : ""}${t.title || "제목 없음"}` : "티켓";

  if (!pageId) return null;

  /* 발은 `ActionFooter` 하나다(표 5 가 허용한 치환) — 회차 작업 · 빠른 수정이 왼쪽 묶음, 「티켓 상세 보기」가
     오른쪽이다. 예전에는 30 과 34 단추가 한 발에 섞이고 빈 상자로 밀어냈다. 발의 단추는 34 다(핸드오프 RULES §3). */
  const footer = (
    <ActionFooter
      placement="modal"
      extra={(
        <>
          {(actions || []).map((a) => (
            <Button
              key={a.key || a.label}
              variant={a.tone === "danger" ? "danger" : "secondary"}
              disabled={a.disabled}
              onClick={() => a.onClick(t)}
            >
              {a.label}
            </Button>
          ))}
          {quickEdit && t && data.can_edit !== false ? (
            <Button variant="secondary" onClick={() => setEditing(true)}>빠른 수정</Button>
          ) : null}
        </>
      )}
    >
      {/* 닫기는 창의 X 와 Esc 가 맡는다 — 같은 이름의 단추가 둘이면 낭독기가 둘을 구별하지 못한다. */}
      <Button variant="primary" onClick={() => onDetail(pageId, from)} disabled={!t}>티켓 상세 보기</Button>
    </ActionFooter>
  );

  return (
    <>
      <Modal open title={title} size="md" onClose={onClose} footer={footer}>
        {detail.isPending ? <Skeleton lines={6} /> : null}
        {detail.isError ? <ErrorState error={detail.error} onRetry={() => detail.refetch()} layout="inline" /> : null}
        {t ? (
          <Stack spacing={2} data-testid="ticket-peek">
            <MetaBar ariaLabel="티켓 속성" items={ticketMetaItems(t, signalsOf(t))} />
            {sprint ? (
              <Callout variant="inline" tone="info" title="회차">
                {sprint.name}
              </Callout>
            ) : t.sprint_id ? null : (
              <Callout variant="inline" tone="info" title="회차">
                어느 회차에도 담기지 않은 백로그 티켓입니다.
              </Callout>
            )}
            {previewText(data.body_markdown) ? (
              <Box>
                <SectionTitle spacing="tight" component="h3" title="설명"  />
                <Typography
                  variant="body2"
                  component="p"
                  sx={{ ...KO_WORD_BREAK, whiteSpace: "pre-wrap", color: "text.secondary", m: 0 }}
                >
                  {previewText(data.body_markdown)}
                </Typography>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                설명이 아직 없습니다. 본문과 댓글은 상세에서 봅니다.
              </Typography>
            )}
          </Stack>
        ) : null}
      </Modal>
      {/* 빠른 수정은 **목록이 이미 쓰는 부품**이다. 저장하면 티켓을 그리는 질의가 전부
          낡는다(`ticket-views.js`) — 미리보기 자신(`["ticket", id]`)도 그 표에 있다. */}
      {t ? (
        <TicketEditModal
          ticket={t}
          open={editing}
          projectScope={projectScope}
          onClose={() => { setEditing(false); invalidateTicketViews(qc); }}
        />
      ) : null}
    </>
  );
}
