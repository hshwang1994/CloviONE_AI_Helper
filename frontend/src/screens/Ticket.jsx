import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Button, Callout, Card, EmptyState, ErrorState, MetaBar, OverflowMenu, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { DETAIL_GRID, DetailLayout } from "../ui/DetailLayout.jsx";
import { GRID_GAP } from "../ui/density.js";
import { TicketEditModal } from "./MyTickets.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { TicketBody } from "./TicketBody.jsx";
import { TicketComments } from "./TicketComments.jsx";
import { TicketAttachments } from "./TicketAttachments.jsx";
import { TicketHistory } from "./TicketHistory.jsx";
import { ticketId, ticketMetaItems } from "./ticket-meta.jsx";
import { setItemTitle } from "../app/documentTitle.js";
import { useListReturn } from "../lib/listReturn.js";
import { useTicketSignals } from "../lib/ticketSignals.js";

/* 티켓 상세 — 문서처럼 우리 화면에서 내용을 읽고, '원본 열기'로 노션에 간다. 속성은 메타 레일에,
 * 본문은 TicketBody(읽기·편집·동기화 상태), 논의는 TicketComments 가 맡는다. 편집·삭제(휴지통)도 여기서.
 *
 * 2026-08 재설계 — 폭 정책이 이 화면의 핵심이다.
 *   열 폭: 기준선 `.ticket-layout`(아래 DETAIL_GRID)이 정한다. 비율 트랙이라 본문 열이
 *   화면을 꽉 채우고, 남는 폭은 속성 레일이 비율대로 나눠 갖는다. 본문 글줄은 그 열이
 *   정한다 — 열 안에 72ch 를 다시 걸면 카드는 넓은데 글만 왼쪽에 붙는다.
 * 2026-08-07 이전에는 격자 트랙 자체를 78ch 로 못 박아서, 열이 채우지 못한 폭이 오른쪽에
 * 그대로 남았다.
 * 좁은 화면에서는 레일이 본문 '위'로 온다(order) — 아래로 밀면 담당자·마감을 보려고 본문 전체를
 * 스크롤해 지나가야 한다. */

/* 속성 줄의 정본은 `ticket-meta.jsx` 다 — 미리보기(`TicketPeek`)와 같은 표를 본다(D-483).
   번호 폴백도 그쪽에 있다(`ticketId`). 아래 PageHeader 의 제목 폴백은 그대로 두는 것이
   맞다 — 거기서는 「제목이 없는 티켓」의 이름이 필요하다. */

/* 두 열 그리드의 정본은 **`ui/DetailLayout.jsx`** 다 (지시 8 · 14 · 16).
 *
 * 여기 있던 값을 그쪽으로 옮겼다. 이유는 곁열이 **없는** 상세 화면(게시글 · 기능 개선
 * 제안)이 같은 문제를 다른 모양으로 갖고 있었기 때문이다 — 한 계약이 둘 다 답해야 한다.
 * 이 이름은 그대로 다시 내보낸다: `density-contract.test.jsx` 가 이 이름으로 계약을
 * 확인하고 있고, 이름을 옮기면 그 검사가 조용히 아무것도 안 지키게 된다. */
export { DETAIL_GRID };


export function Ticket() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  /* 「목록」은 **왔던 목록의 그 상태**로 돌아간다 (지시 19). 어디서 왔는지는 목록이
     `state.from` 으로 남겼고, 그 목록이 어떤 조건·페이지·스크롤이었는지는
     `lib/listReturn.js` 가 기억한다. 딥링크로 바로 들어왔으면 내 티켓으로 간다. */
  const backToList = useListReturn(loc.state && loc.state.from, "/my-tickets");
  const signalsOf = useTicketSignals();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);

  const detail = useQuery({
    queryKey: ["ticket", id],
    queryFn: () => api("/api/tickets/" + id),
    retry: false,
  });

  // VIS-133: 탭 제목을 나브 라벨("티켓")이 아니라 실제 티켓 제목으로 — 여러 티켓 탭을
  // 열어 두면 구분이 안 됐다. 데이터가 아직 없으면(로딩/오류) 빈 문자열이라 documentTitle.js가
  // 자동으로 나브 라벨로 되돌아간다.
  const ticketTitle = detail.data && detail.data.ticket ? detail.data.ticket.title : "";
  React.useEffect(() => {
    setItemTitle(loc.pathname, ticketTitle);
  }, [loc.pathname, ticketTitle]);

  const trash = useMutation({
    mutationFn: () => api("/api/tickets/" + id + "/trash", { method: "POST" }),
    onSuccess: () => {
      toast("티켓을 휴지통으로 옮겼습니다.", "success");
      // 티켓을 그리는 질의 키는 ticket-views.js 한 곳이 안다(홈·스프린트도 이 티켓을 세고 있다).
      invalidateTicketViews(qc, { refetchType: "all" });
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      // 지운 뒤에도 왔던 목록으로 돌아간다 — 지우기 전에 보던 조건이 그대로다.
      nav(backToList);
    },
  });
  /* 휴지통으로 보내기 실패는 머리 바로 아래 — 누른 단추 곁에 남고 다시 누르면 걷힌다. */
  const trashFailure = trash.isError ? ((trash.error && trash.error.message) || "삭제하지 못했습니다. 다시 시도해 주세요.") : null;

  if (detail.isError) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" actions={<Button onClick={() => nav(backToList)}>목록</Button>} />
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      </div>
    );
  }
  if (detail.isPending) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" />
        <Card><Skeleton lines={8} /></Card>
      </div>
    );
  }

  const data = detail.data || {};
  if (data.configured === false) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" actions={<Button onClick={() => nav(backToList)}>목록</Button>} />
        {/* 연동 미설정은 이 화면에서 가장 흔한 '데이터 없음'이다 — 경고 한 줄로 끝내지 않고
            무엇이 필요한지·연동 후 무엇이 보이는지까지 알려준다(목록 화면들과 같은 규칙). */}
        {/* 이 갈래는 더 이상 안 열린다 — 티켓의 정본이 이 서버라 사람이 채워 넣을 접속
            설정이 없다(S14 · D-284). 응답 모양은 남아 있으므로 갈래도 남기되, 없어진
            절차를 안내하지는 않는다. */}
        <EmptyState
          art="tickets"
          title="지금은 이 티켓을 열 수 없습니다"
          situation="서버가 티켓을 읽지 못했습니다."
          steps={["잠시 뒤 이 화면을 새로고침해 보세요.", "계속 같으면 관리자에게 문의하세요."]}
          expected="다시 열면 제목, 속성, 본문이 이 자리에 표시됩니다."
          action={<Button variant="primary" onClick={() => nav(backToList)}>내 티켓으로</Button>}
        />
      </div>
    );
  }
  if (data.ok === false) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" actions={<Button onClick={() => nav(backToList)}>목록</Button>} />
        <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}</Callout>
      </div>
    );
  }

  const t = data.ticket || {};
  const signals = signalsOf(t);
  const actions = (
    <Stack direction="row" gap={1} sx={{ flexWrap: "wrap" }}>
      {/* 「목록」은 페이지 머리 동작이라 보조(흰 면 34)다 — 오류 · 빈 상태의 같은 단추와 같다(핸드오프 RULES §3, 글자 단추는 목록 안 부수 동작). */}
      <Button onClick={() => nav(backToList)}>목록</Button>
      {/* 이 화면에서 가장 자주 하는 일은 수정이다 — 이 앱 안에서 바로 되는 유일한
          쓰기 동작이라 primary 자리를 준다. */}
      {/* VIS-135: 본문 카드 안에도 별도의 "본문 수정"(EditableBody.jsx)이 있어, 둘의 차이가
          화면에 설명 없이는 안 보였다. 이 버튼은 상태·우선순위·담당자·마감 같은 속성을
          여는 것이라는 것을 툴팁으로 밝힌다 — 본문 텍스트는 이 모달이 안 건드린다. */}
      {data.can_edit === false ? null : (
        <Tooltip describeChild title="상태, 담당자, 마감 등 속성을 수정합니다. 본문 텍스트는 아래 '본문 수정'에서 고칩니다.">
          <Button variant="primary" onClick={() => setEditing(true)}>수정</Button>
        </Tooltip>
      )}
      {/* 삭제는 넘침 메뉴로 내렸다. 빨간 solid 버튼으로 머리에 있으면 가장 자주 하는
          일(수정)과 시선을 다툰다(지시 11 · 12). 확인 대화는 그대로다.

          여기 「원본 열기」가 함께 있었다. 그 링크는 티켓 1,133건 전부가 app.notion.com
          을 가리켰는데, 정본이 이 서버로 넘어온 뒤로 그 주소가 여는 것은 우리가 더 이상
          쓰지 않는 낡은 사본이다. 서버도 응답에서 `url` 을 걷었다. */}
      <OverflowMenu
        ariaLabel="티켓 더 보기"
        items={[
          {
            key: "trash", label: "삭제", tone: "danger", disabled: trash.isPending,
            onClick: async () => {
              const ok = await confirm("이 티켓을 휴지통으로 옮깁니다. 보관기간이 지나면 원본이 삭제됩니다. 계속할까요?",
                { title: "티켓 삭제", confirmLabel: "휴지통으로", danger: true });
              if (ok) trash.mutate();
            },
          },
        ]}
      />
    </Stack>
  );

  // 속성 줄 — 미리보기와 **같은 표**(`ticket-meta.jsx`). 무게(rank)·칸 종류(type)의 이유도 그쪽에 있다.
  const meta = ticketMetaItems(t, signals);

  /* 부속 레일 — 본문에 딸린 것들이다. 첨부가 먼저고(무엇에 대한 파일인지 본문을 보면서
     확인한다) 그다음이 논의, 마지막이 이력이다. 좁은 화면에서 한 열로 접히면 본문 → 첨부
     → 댓글 → 이력 순서 그대로 쌓인다 — 논의가 대상보다 먼저 나오지 않는다.

     **활동 이력이 마지막인 이유**: 이 티켓을 열고 가장 먼저 하는 일은 지금 무엇이 달려
     있고 무슨 말이 오갔는지 보는 것이고, 「언제 이렇게 됐나」는 그다음에 묻는 질문이다.
     그래도 화면 안에 있어야 한다 — 예전에는 이 기록을 보려면 일반 사용자가 못 여는 감사
     화면으로 가야 했고, 그 자리는 그냥 비어 있었다(S18). */
  const rail = (
    <Box data-testid="ticket-detail-rail" sx={{ minWidth: 0, display: "grid", gap: GRID_GAP, alignContent: "start" }}>
      <TicketAttachments
        ticketId={id}
        attachments={data.attachments}
        canEdit={data.can_edit !== false}
        onChanged={() => detail.refetch()}
      />
      <TicketComments ticketId={id} />
      <TicketHistory key={id} ticketId={id} />
    </Box>
  );

  return (
    <div className="c-screen">
      {/* SEM-03 재확인(2026-08-13) — 예전엔 여기 title이 ticketId(t)(예: "GIT-57")였다
          (VIS-133과 같은 원인 — PageHeader가 ID를 h1으로 차지해 화면이 진짜 제목을 넣을
          자리가 없어 카드 안에 h1을 하나 더 만들었다). PageHeader가 실제 제목을 h1로
          보여주게 하고, 아래 카드의 중복 h1은 없앤다. ticketId는 사라지지 않고 위 meta의
          '티켓 번호'로 옮겨 계속 보인다. */}
      <PageHeader crumbRoot="내 업무" area="티켓" title={t.title || ticketId(t)} actions={actions} />
      {trashFailure ? <Callout tone="danger" compact>{trashFailure}</Callout> : null}
      {/* 속성은 상단 전폭 한 줄이다 (지시 7). 예전에는 오른쪽 레일 맨 위에 세로로 쌓여
          있었고, 본문을 읽다가 마감을 확인하려면 시선이 화면 오른쪽 끝까지 갔다 와야 했다.
          훑는 정보라 눕히는 편이 짧다 — 그리고 그 자리를 비워 준 레일은 본문과 나란히
          읽는 것(첨부·댓글)이 갖는다. */}
      <Box data-testid="ticket-detail-meta" sx={{ mb: 2.5 }}>
        {meta.length ? (
          <MetaBar ariaLabel="티켓 속성" items={meta} />
        ) : (
          <Card><EmptyState layout="inline" title="표시할 속성이 없습니다." /></Card>
        )}
      </Box>
      {/* 폭 계약은 `ui/DetailLayout.jsx` 한 곳이다 — 곁열이 없는 상세 화면(게시글 · 기능
          개선 제안)과 같은 부품을 쓴다. lg+ 에서는 본문이 1열, `aside` 가 2열에 놓이고
          좁은 화면에서는 DOM 순서 그대로 한 열로 흐른다. */}
      <DetailLayout aside={rail}>
        <Box data-testid="ticket-detail-main" sx={{ minWidth: 0, display: "grid", gap: GRID_GAP, alignContent: "start" }}>
          {/* 본문 판은 넘침을 자르지 않는다 — 본문을 고치는 동안 판 발(취소 · 저장)이 긴 본문에서 화면 아래에 따라와야 한다
              (`EditableBody` 의 `ActionFooter sticky`, MUI Card 뿌리의 `overflow: hidden` 을 푼다 — 새 티켓 폼 판과 같은 이유). */}
          <Card component="article" sx={{ minWidth: 0, overflow: "visible" }}>
            {/* SEM-03 재확인 — 제목은 이제 위 PageHeader가 h1로 보여준다. 여기서 같은 글자를
                또 반복하지 않는다. 상태/우선순위 배지는 VIS-134로 오른쪽 '속성' 카드로
                옮겼다(라벨 없이 여기 있으면 어느 값이 무엇인지 구별이 안 됐다) — 본문은
                본문만 그린다. */}
            <TicketBody
              ticketId={id}
              blocks={data.blocks}
              blocksError={data.blocks_error}
              body={data.body}
              bodyMarkdown={data.body_markdown}
              bodyVersion={data.body_version}
              onSaved={() => detail.refetch()}
            />
          </Card>
        </Box>
      </DetailLayout>
      <TicketEditModal ticket={t} open={editing} onClose={() => { setEditing(false); detail.refetch(); }} />
    </div>
  );
}
