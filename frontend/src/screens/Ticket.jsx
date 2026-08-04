import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Badge, Button, Callout, Card, EmptyState, ErrorState, PageHeader, Skeleton, useConfirm, useToast } from "../ui/kit.jsx";
import { PROSE_MAX_WIDTH } from "../ui/theme.js";
import { safeExternal } from "./TeamDoc.jsx";
import { TicketEditModal } from "./MyTickets.jsx";
import { TicketBody } from "./TicketBody.jsx";
import { TicketComments } from "./TicketComments.jsx";
import { TicketAttachments } from "./TicketAttachments.jsx";
import { priorityKo, priorityKind } from "../lib/priority.js";

/* 티켓 상세 — 문서처럼 우리 화면에서 내용을 읽고, '원본 열기'로 노션에 간다. 속성은 메타 레일에,
 * 본문은 TicketBody(읽기·편집·동기화 상태), 논의는 TicketComments 가 맡는다. 편집·삭제(휴지통)도 여기서.
 *
 * 2026-08 재설계 — 폭 정책이 이 화면의 핵심이다.
 * 본문은 산문이라 줄이 길어질수록 읽기 어려워진다(눈이 다음 줄 첫 글자를 못 찾는다). 그래서
 * 본문 열은 PROSE_MAX_WIDTH(78ch)에서 멈추고, 화면이 넓어져서 남는 폭은 **줄 길이가 아니라
 * 두 번째 열(속성·활동 레일)** 로 보낸다. 3,840px 화면에서 한 줄이 3,000px가 되는 것보다
 * 담당자·마감·난이도를 본문 옆에 나란히 두는 편이 회의 중에도 훨씬 쓸모 있다.
 * 좁은 화면에서는 레일이 본문 '위'로 온다(order) — 아래로 밀면 담당자·마감을 보려고 본문 전체를
 * 스크롤해 지나가야 한다. */

function ticketId(t) { return t && t.tid != null ? "GIT-" + t.tid : "티켓"; }

/* 두 열 그리드. xl(1536) 미만에서는 한 열이다 — 1366×768 사내 장비에서 사이드바를 빼면 본문 폭이
 * 1,100px 남짓이라, 78ch 본문 + 레일을 억지로 나란히 두면 둘 다 좁아진다. */
const DETAIL_GRID = {
  display: "grid", gap: 3, alignItems: "start",
  gridTemplateColumns: {
    xs: "1fr",
    xl: `minmax(0, ${PROSE_MAX_WIDTH}) minmax(18rem, 1fr)`,
  },
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
      qc.invalidateQueries({ queryKey: ["tickets"], refetchType: "all" });
      qc.invalidateQueries({ queryKey: ["trash"], refetchType: "all" });
      nav("/my-tickets");
    },
    onError: (e) => toast((e && e.message) || "삭제하지 못했습니다.", "error"),
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
        <Callout tone="danger">{data.error || "티켓을 불러오지 못했습니다."}</Callout>
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
    t.project ? ["프로젝트", t.project] : null,
    (t.assignee_names || []).length ? ["담당자", t.assignee_names.join(", ")] : null,
    t.difficulty ? ["난이도", t.difficulty] : null,
    t.est_wd != null ? ["예상 WD", t.est_wd] : null,
    t.act_wd != null ? ["실제 WD", t.act_wd] : null,
    t.due ? ["마감", t.due] : null,
  ].filter(Boolean);

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="내 업무" area="티켓" title={ticketId(t)} actions={actions} />
      <Box sx={DETAIL_GRID}>
        {/* 본문 열 — 본문과 댓글은 둘 다 산문이라 같은 열에 세로로 쌓고 78ch에서 멈춘다.
            댓글을 레일에 넣으면 좁은 화면에서 order 때문에 본문보다 위로 올라가고(논의가
            대상보다 먼저 나온다), 4K에서는 줄 길이가 2,000px가 된다. */}
        <Box sx={{ minWidth: 0, display: "grid", gap: 2.5, alignContent: "start" }}>
          <Card component="article" sx={{ minWidth: 0 }}>
            <Stack direction="row" gap={1} sx={{ flexWrap: "wrap", alignItems: "center", mb: 1 }}>
              {t.status ? <Badge value={t.status} /> : null}
              {t.priority ? <Badge value={priorityKo(t.priority)} kind={priorityKind(t.priority)} /> : null}
            </Stack>
            <Typography component="h1" variant="h4" sx={{ maxWidth: PROSE_MAX_WIDTH, mb: 2 }}>
              {t.title || "제목 없음"}
            </Typography>
            <TicketBody
              ticketId={id}
              blocks={data.blocks}
              blocksError={data.blocks_error}
              bodyMarkdown={data.body_markdown}
              bodyIsLocal={data.body_is_local}
              bodySyncError={data.body_sync_error}
              originalUrl={original}
              onSaved={() => detail.refetch()}
            />
          </Card>
          {/* 첨부는 본문 **바로 아래**다. 레일에 넣으면 좁은 화면에서 order 때문에 본문보다
              위로 올라가 "무엇에 대한 파일인지"보다 파일이 먼저 나온다(댓글과 같은 이유). */}
          <TicketAttachments
            ticketId={id}
            attachments={data.attachments}
            canEdit={data.can_edit !== false}
            onChanged={() => detail.refetch()}
          />
          <TicketComments ticketId={id} />
        </Box>

        {/* 메타/활동 레일 — 좁은 화면에서는 본문 위로 올린다(order). 아래로 밀면 담당자·마감을
            보려고 본문과 댓글 전체를 스크롤해 지나가야 한다. */}
        <Box sx={{ order: { xs: -1, xl: 0 }, minWidth: 0, display: "grid", gap: 2.5, alignContent: "start" }}>
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
        </Box>
      </Box>
      <TicketEditModal ticket={t} open={editing} onClose={() => { setEditing(false); detail.refetch(); }} />
    </div>
  );
}
