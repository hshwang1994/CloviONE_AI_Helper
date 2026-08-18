import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Badge, Button, Callout, Card, EmptyState, ErrorState, MetaBar, OverflowMenu, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { BASELINE_TRACKS, GRID_GAP } from "../ui/density.js";
import { safeExternal } from "./TeamDoc.jsx";
import { TicketEditModal } from "./MyTickets.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { TicketBody } from "./TicketBody.jsx";
import { TicketComments } from "./TicketComments.jsx";
import { TicketAttachments } from "./TicketAttachments.jsx";
import { priorityKo, priorityKind } from "../lib/priority.js";
import { setItemTitle } from "../app/documentTitle.js";

/* 티켓 상세 — 문서처럼 우리 화면에서 내용을 읽고, '원본 열기'로 노션에 간다. 속성은 메타 레일에,
 * 본문은 TicketBody(읽기·편집·동기화 상태), 논의는 TicketComments 가 맡는다. 편집·삭제(휴지통)도 여기서.
 *
 * 2026-08 재설계 — 폭 정책이 이 화면의 핵심이고, **두 층으로 나뉜다.**
 *   1) 열 폭: 기준선 `.ticket-layout`(아래 DETAIL_GRID)이 정한다. 비율 트랙이라 본문 열이
 *      화면을 꽉 채우고, 남는 폭은 속성 레일이 비율대로 나눠 갖는다.
 *   2) 글줄 길이: 그 열 **안에서** PROSE_MAX_WIDTH(78ch)가 잡는다. 산문은 줄이 길수록
 *      읽기 어렵다(눈이 다음 줄 첫 글자를 못 찾는다).
 * 2026-08-07 이전에는 (1)을 (2)로 대신했다 — 격자 트랙 자체를 78ch 로 못 박아서, 열이
 * 채우지 못한 폭이 오른쪽에 그대로 남았다(사용자 지적 "왼쪽으로 쏠려있다"). 둘은 다른 문제다.
 * 좁은 화면에서는 레일이 본문 '위'로 온다(order) — 아래로 밀면 담당자·마감을 보려고 본문 전체를
 * 스크롤해 지나가야 한다. */

function ticketId(t) { return t && t.tid != null ? "GIT-" + t.tid : "티켓"; }

/* 두 열 그리드 — 기준선 `.ticket-layout` 을 그대로 쓴다.
 *
 * 예전 값은 `minmax(0, 78ch) minmax(18rem, 26rem)` 이었고, 이것이 사용자가 본
 * "티켓 상세가 왼쪽으로 쏠려있다"의 원인이다. **두 트랙 모두 상한이 고정값**이라
 * 격자가 컨테이너보다 좁게 멈추고 오른쪽을 빈 채로 남긴다: 1920 기준 본문 열
 * 1,592px 중 78ch(약 600px) + 26rem(416px) + 간격만 쓰고 550px 가까이가 그냥 비었다.
 * 바깥 셸의 `mx:"auto"` 는 이걸 못 고친다 — 가운데로 옮길 뿐 폭을 채우지 않는다.
 *
 * 기준선은 두 트랙을 다 `fr` 로 둔다(1.5 : 0.65). 남는 폭이 본문과 레일에 비율대로 배분돼
 * 어느 폭에서도 오른쪽이 비지 않고, 레일에는 300px 하한이 있어 짜부라지지도 않는다.
 * 본문이 레일보다 2.3배 넓으므로 "본문이 속성보다 좁다"(Q1)도 그대로 지켜진다.
 *
 * 한 열로 접히는 지점은 lg(1200)다. 기준선은 960px 이하에서 한 열이 되는데, 우리 셸은
 * 사이드바 264px 를 더 빼므로 그보다 한 단 위에서 접는 것이 같은 여유가 된다.
 * 문서 상세(TeamDoc)도 같은 값을 쓴다 — 성격이 같은 두 화면이 다른 폭이면 안 된다. */
export const DETAIL_GRID = {
  display: "grid", gap: GRID_GAP, alignItems: "start",
  gridTemplateColumns: { xs: "1fr", lg: BASELINE_TRACKS.detail },
};


export function Ticket() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
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
      nav("/my-tickets");
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다. 다시 시도해 주세요.", "error"),
  });

  if (detail.isError) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" actions={<Button onClick={() => nav("/my-tickets")}>목록</Button>} />
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
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" actions={<Button onClick={() => nav("/my-tickets")}>목록</Button>} />
        {/* 연동 미설정은 이 화면에서 가장 흔한 '데이터 없음'이다 — 경고 한 줄로 끝내지 않고
            무엇이 필요한지·연동 후 무엇이 보이는지까지 알려준다(목록 화면들과 같은 규칙). */}
        <EmptyState
          art="tickets"
          title="Notion 연동이 아직 설정되지 않았습니다"
          situation="티켓 본문은 Notion 페이지에서 실시간으로 읽어옵니다. 연동 토큰이 없으면 이 티켓을 열 수 없습니다."
          prerequisite="관리자 권한과 Notion 통합 토큰"
          steps={["관리자에게 Notion 연동 설정을 요청하세요.", "연동이 추가되면 이 화면을 새로고침하세요."]}
          expected="연동이 끝나면 제목, 속성, 본문이 이 자리에 표시됩니다."
          action={<Button variant="primary" onClick={() => nav("/my-tickets")}>내 티켓으로</Button>}
        />
      </div>
    );
  }
  if (data.ok === false) {
    return (
      <div className="c-screen">
        <PageHeader crumbRoot="내 업무" area="티켓" title="티켓" actions={<Button onClick={() => nav("/my-tickets")}>목록</Button>} />
        <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."}</Callout>
      </div>
    );
  }

  const t = data.ticket || {};
  const original = safeExternal(t.url);
  const actions = (
    <Stack direction="row" gap={1} sx={{ flexWrap: "wrap" }}>
      <Button variant="ghost" onClick={() => nav("/my-tickets")}>목록</Button>
      {/* VIS-132: 이 화면에서 가장 자주 하는 일은 수정이다 — 이 앱 안에서 바로 되는 유일한
          쓰기 동작이고, 원본 열기는 Notion으로 나가는 보조 참조다(TeamDoc.jsx의 "원본
          열기"와 다르다 — 거기는 경쟁하는 인앱 수정 버튼이 아예 없어 원본 열기 자체가
          사실상 그 화면의 주 동작이다). 그래서 여기서만 수정을 primary로, 원본 열기를
          default로 바꾼다. */}
      {/* VIS-135: 본문 카드 안에도 별도의 "본문 수정"(EditableBody.jsx)이 있어, 둘의 차이가
          화면에 설명 없이는 안 보였다. 이 버튼은 상태·우선순위·담당자·마감 같은 속성을
          여는 것이라는 것을 툴팁으로 밝힌다 — 본문 텍스트는 이 모달이 안 건드린다. */}
      {data.can_edit === false ? null : (
        <Tooltip describeChild title="상태, 담당자, 마감 등 속성을 수정합니다. 본문 텍스트는 아래 '본문 수정'에서 고칩니다.">
          <Button variant="primary" onClick={() => setEditing(true)}>수정</Button>
        </Tooltip>
      )}
      {/* 원본 열기와 삭제는 넘침 메뉴로 내렸다. 삭제는 빨간 solid 버튼으로 머리에 있으면
          가장 자주 하는 일(수정)과 시선을 다투고, 원본 열기는 Notion 으로 나가는 보조
          참조라 주 동작 자리를 차지할 이유가 없다(지시 11 · 12). 확인 대화는 그대로다. */}
      <OverflowMenu
        ariaLabel="티켓 더 보기"
        items={[
          original ? {
            key: "original", label: "원본 열기",
            onClick: () => window.open(original, "_blank", "noopener,noreferrer"),
          } : null,
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

  const meta = [
    // VIS-134: 예전엔 상태/우선순위가 라벨 없이 본문 카드 맨 위에 칩 두 개로만 있었다 —
    // "높음" 칩만 보고 그게 우선순위인지 난이도인지 알 수 없었다. 편집 폼(TicketEditModal)도
    // 이 둘을 project/assignee/due/difficulty와 같은 한 폼에서 다뤄, 화면만 임의로 갈라 둘
    // 이유가 없었다 — 라벨과 함께 한 속성 줄로 합친다. 가장 먼저 훑는 두 값이라 맨 앞이다.
    t.status ? { key: "status", label: "상태", value: <Badge value={t.status} /> } : null,
    t.priority ? { key: "priority", label: "우선순위", value: <Badge value={priorityKo(t.priority)} kind={priorityKind(t.priority)} /> } : null,
    // SEM-03 재확인 — PageHeader의 h1이 이제 원시 ID(GIT-57 등) 대신 실제 제목을 보여준다
    // (VIS-133과 같은 원인). 그 ID는 지원 문의 등에서 여전히 참조되는 값이라 사라지면 안
    // 되므로 메타로 옮긴다.
    { key: "tid", label: "티켓 번호", value: ticketId(t) },
    t.project ? { key: "project", label: "프로젝트", value: t.project } : null,
    (t.assignee_names || []).length ? { key: "assignee", label: "담당자", value: t.assignee_names.join(", ") } : null,
    t.difficulty ? { key: "difficulty", label: "난이도", value: t.difficulty } : null,
    t.est_wd != null ? { key: "est", label: "예상 WD", value: t.est_wd } : null,
    t.act_wd != null ? { key: "act", label: "실제 WD", value: t.act_wd } : null,
    t.due ? { key: "due", label: "마감", value: t.due } : null,
  ].filter(Boolean);

  return (
    <div className="c-screen">
      {/* SEM-03 재확인(2026-08-13) — 예전엔 여기 title이 ticketId(t)(예: "GIT-57")였다
          (VIS-133과 같은 원인 — PageHeader가 ID를 h1으로 차지해 화면이 진짜 제목을 넣을
          자리가 없어 카드 안에 h1을 하나 더 만들었다). PageHeader가 실제 제목을 h1로
          보여주게 하고, 아래 카드의 중복 h1은 없앤다. ticketId는 사라지지 않고 위 meta의
          '티켓 번호'로 옮겨 계속 보인다. */}
      <PageHeader crumbRoot="내 업무" area="티켓" title={t.title || ticketId(t)} actions={actions} />
      {/* 속성은 상단 전폭 한 줄이다 (지시 7). 예전에는 오른쪽 레일 맨 위에 세로로 쌓여
          있었고, 본문을 읽다가 마감을 확인하려면 시선이 화면 오른쪽 끝까지 갔다 와야 했다.
          훑는 정보라 눕히는 편이 짧다 — 그리고 그 자리를 비워 준 레일은 본문과 나란히
          읽는 것(첨부·댓글)이 갖는다. */}
      <Box data-testid="ticket-detail-meta" sx={{ mb: 2.5 }}>
        {meta.length ? (
          <MetaBar ariaLabel="티켓 속성" items={meta} />
        ) : (
          <Card><Typography variant="body2" color="text.secondary">표시할 속성이 없습니다.</Typography></Card>
        )}
      </Box>
      <Box sx={DETAIL_GRID}>
        {/* 본문 열 — 본문만 그린다. 첨부와 댓글은 오른쪽 레일이고, 속성은 위 전폭 줄이다
            (지시 7). lg+ 에서는 첫 자식이 1열, 둘째 자식이 2열에 자동으로 놓인다 — CSS
            트릭 없이 배치와 좁은 화면 순서가 같이 풀린다. */}
        <Box data-testid="ticket-detail-main" sx={{ minWidth: 0, display: "grid", gap: 2.5, alignContent: "start" }}>
          <Card component="article" sx={{ minWidth: 0 }}>
            {/* SEM-03 재확인 — 제목은 이제 위 PageHeader가 h1로 보여준다. 여기서 같은 글자를
                또 반복하지 않는다. 상태/우선순위 배지는 VIS-134로 오른쪽 '속성' 카드로
                옮겼다(라벨 없이 여기 있으면 어느 값이 무엇인지 구별이 안 됐다) — 본문은
                본문만 그린다. */}
            <TicketBody
              ticketId={id}
              blocks={data.blocks}
              blocksError={data.blocks_error}
              bodyMarkdown={data.body_markdown}
              bodyVersion={data.body_version}
              bodyIsLocal={data.body_is_local}
              bodySyncError={data.body_sync_error}
              originalUrl={original}
              onSaved={() => detail.refetch()}
            />
          </Card>
        </Box>

        {/* 부속 레일 — 본문에 딸린 것들이다. 첨부가 먼저고(무엇에 대한 파일인지 본문을
            보면서 확인한다) 그다음이 논의다. order 는 두지 않는다: 좁은 화면에서 한 열로
            접히면 DOM 순서 그대로 본문 → 첨부 → 댓글로 쌓인다 — 논의가 대상보다 먼저
            나오지 않는다. */}
        <Box data-testid="ticket-detail-rail" sx={{ minWidth: 0, display: "grid", gap: 2.5, alignContent: "start" }}>
          <TicketAttachments
            ticketId={id}
            attachments={data.attachments}
            canEdit={data.can_edit !== false}
            onChanged={() => detail.refetch()}
          />
          <TicketComments ticketId={id} />
        </Box>
      </Box>
      <TicketEditModal ticket={t} open={editing} onClose={() => { setEditing(false); detail.refetch(); }} />
    </div>
  );
}
