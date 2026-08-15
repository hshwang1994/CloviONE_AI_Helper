import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Badge, Button, Callout, Card, EmptyState, ErrorState, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { BASELINE_TRACKS, GRID_GAP } from "../ui/density.js";
import { safeExternal } from "./TeamDoc.jsx";
import { TicketEditModal } from "./MyTickets.jsx";
import { invalidateTicketViews } from "./ticket-views.js";
import { TicketBody } from "./TicketBody.jsx";
import { TicketComments } from "./TicketComments.jsx";
import { TicketAttachments } from "./TicketAttachments.jsx";
import { priorityKo, priorityKind } from "../lib/priority.js";

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

/* 속성 필드 그리드 — 4K 반응형 계약(계획서 '상세/폼' 행): xxl(2200)에서 2열, uhd(3000)에서 3열.
 * 레일은 본문이 78ch에서 멈춘 뒤 남는 폭을 전부 받으므로 3,840px에서는 2,000px가 넘는다.
 * 그 폭에 라벨-값 한 쌍을 한 줄씩 쌓으면 오른쪽이 통째로 빈 캔버스가 된다. */
const META_GRID = {
  display: "grid",
  gridTemplateColumns: {
    xs: "1fr",
    xxl: "repeat(2, minmax(0, 1fr))",
    uhd: "repeat(3, minmax(0, 1fr))",
  },
  columnGap: 3,
};

function MetaRow({ label, children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "7rem minmax(0,1fr)" }, gap: 1, py: 1, borderBottom: 1, borderColor: "divider" }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Box sx={{ minWidth: 0, fontSize: "0.875rem", overflowWrap: "anywhere" }}>{children}</Box>
    </Box>
  );
}

export function Ticket() {
  const { id } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const qc = useQueryClient();
  const [editing, setEditing] = React.useState(false);

  const detail = useQuery({
    queryKey: ["ticket", id],
    queryFn: () => api("/api/tickets/" + id),
    retry: false,
  });

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
          steps={["관리자에게 Notion 연동 설정을 요청하세요.", "연동이 등록되면 이 화면을 새로고침하세요."]}
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
      {data.can_edit === false ? null : <Button onClick={() => setEditing(true)}>편집</Button>}
      {original ? (
        <Button variant="primary" onClick={() => window.open(original, "_blank", "noopener,noreferrer")}>원본 열기</Button>
      ) : null}
      <Button variant="danger" disabled={trash.isPending}
        onClick={async () => {
          const ok = await confirm("이 티켓을 휴지통으로 옮깁니다. 보관기간이 지나면 원본이 삭제됩니다. 계속할까요?",
            { title: "티켓 삭제", confirmLabel: "휴지통으로", danger: true });
          if (ok) trash.mutate();
        }}>삭제</Button>
    </Stack>
  );

  const meta = [
    // SEM-03 재확인 — PageHeader의 h1이 이제 원시 ID(GIT-57 등) 대신 실제 제목을 보여준다
    // (VIS-133과 같은 원인). 그 ID는 지원 문의 등에서 여전히 참조되는 값이라 사라지면 안
    // 되므로 메타로 옮긴다.
    ["티켓 번호", ticketId(t)],
    t.project ? ["프로젝트", t.project] : null,
    (t.assignee_names || []).length ? ["담당자", t.assignee_names.join(", ")] : null,
    t.difficulty ? ["난이도", t.difficulty] : null,
    t.est_wd != null ? ["예상 WD", t.est_wd] : null,
    t.act_wd != null ? ["실제 WD", t.act_wd] : null,
    t.due ? ["마감", t.due] : null,
  ].filter(Boolean);

  return (
    <div className="c-screen">
      {/* SEM-03 재확인(2026-08-13) — 예전엔 여기 title이 ticketId(t)(예: "GIT-57")였다
          (VIS-133과 같은 원인 — PageHeader가 ID를 h1으로 차지해 화면이 진짜 제목을 넣을
          자리가 없어 카드 안에 h1을 하나 더 만들었다). PageHeader가 실제 제목을 h1로
          보여주게 하고, 아래 카드의 중복 h1은 없앤다. ticketId는 사라지지 않고 위 meta의
          '티켓 번호'로 옮겨 계속 보인다. */}
      <PageHeader crumbRoot="내 업무" area="티켓" title={t.title || ticketId(t)} actions={actions} />
      <Box sx={DETAIL_GRID}>
        {/* 본문 열 — 첨부는 본문 **바로 아래**다(무엇에 대한 파일인지 먼저 보여야 한다).
            댓글은 더 이상 여기 없다 — 사용자 지시대로 속성 레일로 옮겼다(아래 우측 컬럼).
            두 Box 모두 order를 두지 않는다: xs(한 열)에서는 DOM 순서 그대로 본문 →
            속성 → 댓글로 쌓이고, lg+(두 열)에서는 첫 자식이 자동으로 1열, 둘째 자식이
            2열에 놓인다 — CSS 트릭 없이 두 목표(레일 배치·좁은 화면 순서)가 같이 풀린다. */}
        <Box data-testid="ticket-detail-main" sx={{ minWidth: 0, display: "grid", gap: 2.5, alignContent: "start" }}>
          <Card component="article" sx={{ minWidth: 0 }}>
            {/* SEM-03 재확인 — 제목은 이제 위 PageHeader가 h1로 보여준다. 여기서 같은 글자를
                또 반복하지 않는다(배지 아래 여백은 유지). */}
            <Stack direction="row" gap={1} sx={{ flexWrap: "wrap", alignItems: "center", mb: 2 }}>
              {t.status ? <Badge value={t.status} /> : null}
              {t.priority ? <Badge value={priorityKo(t.priority)} kind={priorityKind(t.priority)} /> : null}
            </Stack>
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
          <TicketAttachments
            ticketId={id}
            attachments={data.attachments}
            canEdit={data.can_edit !== false}
            onChanged={() => detail.refetch()}
          />
        </Box>

        {/* 속성 레일 — 사용자 지시: "댓글 기능은 본문이 아니라 오른쪽에 배치." 속성 카드
            바로 아래에 댓글을 둔다(속성을 먼저 보고 논의를 본다). 예전에는 이 Box에
            `order:{xs:-1}`를 줘서 좁은 화면에서 본문보다 먼저 보이게 했었는데, 지금은
            댓글도 이 Box 안에 있으므로 그대로 두면 댓글까지 본문보다 앞으로 올라간다
            (그건 원래 댓글을 레일에 넣지 않았던 이유이기도 하다 — 논의가 대상보다 먼저
            나오면 안 된다). 그래서 order를 없앴다: 좁은 화면에서도 DOM 순서(본문 → 속성 →
            댓글)를 그대로 따른다. */}
        <Box data-testid="ticket-detail-rail" sx={{ minWidth: 0, display: "grid", gap: 2.5, alignContent: "start" }}>
          <Card>
            <Typography component="h2" variant="h6" sx={{ fontSize: "1rem", mb: 1 }}>속성</Typography>
            {meta.length ? (
              <Box sx={META_GRID}>
                {meta.map(([label, value]) => <MetaRow key={label} label={label}>{value}</MetaRow>)}
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">표시할 속성이 없습니다.</Typography>
            )}
          </Card>
          <TicketComments ticketId={id} />
        </Box>
      </Box>
      <TicketEditModal ticket={t} open={editing} onClose={() => { setEditing(false); detail.refetch(); }} />
    </div>
  );
}
