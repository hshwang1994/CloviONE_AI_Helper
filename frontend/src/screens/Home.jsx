import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Fade from "@mui/material/Fade";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtRelative } from "../lib/format.js";
import {
  Badge, Button, Card, DataTable, EmptyState, ErrorState, PageHeader, SectionTitle, Skeleton, StatCard,
} from "../ui/kit.jsx";
import { Donut } from "../ui/charts/Donut.jsx";
import { GRID_GAP } from "../ui/density.js";
import { FONT_WEIGHT } from "../ui/theme.js";
import { ticketColumns, ticketConnState, TicketEditModal } from "./MyTickets.jsx";
import { AssistantPanel } from "./AssistantPanel.jsx";
import { TeamChatWidget } from "./TeamChatWidget.jsx";

/* 홈 '오늘' 커맨드 센터 (계획서 Phase 5).
 *
 * 예전 홈(MyWork)은 /api/tickets/mine 하나만 보고 티켓 카드 네 장을 그렸다. 그래서 안 읽은
 * 알림·채팅, 이번 스프린트에서 내 몫, 최근 문서·게시판 변경은 각각 다른 화면에 흩어져 있었고,
 * "오늘 뭘 해야 하지"를 알려면 화면 네 개를 돌아야 했다. 이제 서버가 그 조합을 한 번에
 * 내려 준다(GET /api/home/today) — 요청 1회, Notion 왕복 0회.
 *
 * 이 화면이 지키는 계약 세 가지:
 *   1) **4K 반응형** — StatCard 행이 <900 1열 → 900~1536 2~3 → 1536~2200 4 → ≥2200 5 → ≥3000 6.
 *      MUI Grid 는 쓰지 않는다(MUI 7 에서 xs={12} 가 조용히 무시된다). Box + display:grid 다.
 *   2) **빈 상태를 구분한다** — '필터를 걸어서 없다'(art="search" + 필터 해제)와 '원래 없다'
 *      (art="tickets"/"docs"/"board")는 다른 화면이다. 같은 그림·같은 문장을 쓰면 사용자는
 *      자기가 건 필터 때문인 줄 모르고 데이터가 사라졌다고 생각한다.
 *   3) **스켈레톤 → 콘텐츠 크로스페이드** — 모션 축소는 테마의 전역 규칙이 처리한다.
 *      화면마다 prefers-reduced-motion 을 다시 쓰지 않는다(그렇게 흩어 놨다가 12곳이 됐었다).
 *
 * px 폰트 크기를 쓰지 않는다 — 4K 대응이 styles/root.css 의 루트 폰트사이즈 레버 하나로
 * 되어 있어서, px 를 쓰면 그 조각만 4K에서 작게 남는다.
 *
 * 이 화면의 **모든 숫자**의 출처표는 docs/DASHBOARD_METRICS.md 3절에 있다(어느 질의 /
 * 어떤 시점 기준 / 범위 / 0과 없음). 특히 '오늘'과 '이번 주'는 서버가 KST 달력일로
 * 정해서 내려 준다 — 화면에서 new Date() 로 다시 판정하면 브라우저 시간대에 따라
 * 서버와 다른 날을 '오늘'이라고 부르게 된다.
 */

/* 통계 카드 줄 — 카드는 **항상 정확히 6장**이다(오늘 마감, 지연, 진행 중, 7일 내 마감,
 * 안 읽은 알림, 그리고 안 읽은 채팅 또는 막힘).
 *
 * 그래서 열 수는 6의 약수여야 한다. 예전 사다리는 xl 에서 4열, xxl 에서 5열이라 마지막
 * 줄에 2장·1장만 남고 오른쪽이 빈 칸이었다. 줄이 하나 더 생기니 이 격자의 높이가 두 배가
 * 되고(사용자 지적: "그리드에 높이가 너무 크지 않아?"), 남은 카드가 왼쪽에 몰려 그 줄만
 * 쏠려 보였다. 기준선 `.grid.kpi` 는 카드 4장을 4열에 넣어 **한 줄**로 끝낸다 — 열 수를
 * 카드 수에 맞추는 것이 그 규칙이고, 검사(density.test.jsx)가 이 성질을 지킨다.
 *
 * 모든 트랙이 minmax(0,...) 다. 그냥 "1fr" 은 minmax(auto,1fr) 이라 **트랙이 내용보다
 * 작아지지 않는다** — 긴 문서 제목 하나가 격자를 통째로 밀어내 페이지에 가로 스크롤이
 * 생겼다(390px 캡처에서 실제로 727px 로 벌어졌다). 격자 폭 문제는 항상 이 한 줄이다. */
export const STAT_GRID = {
  display: "grid", gap: GRID_GAP, mb: 2.5,
  gridTemplateColumns: {
    xs: "minmax(0, 1fr)",
    sm: "repeat(2, minmax(0,1fr))",
    md: "repeat(3, minmax(0,1fr))",
    xl: "repeat(6, minmax(0,1fr))",
  },
};

/* 본문 2단 — 좁으면 한 줄로 쌓이고, 넓어지면 오른쪽에 '레일'(진척·최근 변경)이 붙는다.
 * 남는 폭을 줄 길이로 쓰지 않고 두 번째 열로 보내는 것이 이 앱의 4K 규칙이다. */
const BODY_GRID = {
  display: "grid", gap: 2.5, alignItems: "start",
  gridTemplateColumns: {
    xs: "minmax(0, 1fr)",
    lg: "minmax(0, 2fr) minmax(0, 1fr)",
    xxl: "minmax(0, 3fr) minmax(0, 1fr)",
  },
};

const VIEWS = [
  { key: "due_today", label: "오늘 마감", kind: "warn" },
  { key: "overdue", label: "지연", kind: "danger" },
  { key: "in_progress", label: "진행 중" },
  { key: "due_soon", label: "7일 내 마감" },
  { key: "blocked", label: "막힘(이슈)", kind: "danger" },
];

/* SectionTitle(ui/kit.jsx)로 옮겨졌다 — 이 화면·MyStats·Profile·AssistantPanel이
 * 각자 갖고 있던 같은 모양의 컴포넌트를 하나로 합쳤다(DS-07). */

/* 목록 한 줄(문서·게시글 공용). 제목은 링크, 오른쪽은 메타.
 *
 * 잘림(ellipsis)이 실제로 동작하려면 **줄여야 하는 모든 flex 조상**에 minWidth:0 이 있어야
 * 한다. 기본값 min-width:auto 는 "내용보다 작아지지 마라"는 뜻이라, 하나라도 빠지면 긴 제목이
 * 줄지 않고 부모를 밀어낸다(그게 390px 화면이 727px 이 된 원인 중 하나였다). */
function RowLink({ href, title, meta, badge }) {
  return (
    <Box
      component="li"
      sx={{
        display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 2,
        py: 0.75, minWidth: 0,
        borderBottom: 1, borderColor: "divider", "&:last-of-type": { borderBottom: 0 },
      }}
    >
      <Link
        href={href}
        underline="hover"
        title={title}
        sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1, minWidth: 0, overflow: "hidden", color: "text.primary" }}
      >
        {badge}
        <Box component="span" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</Box>
      </Link>
      {meta ? (
        <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap", flexShrink: 0 }}>{meta}</Typography>
      ) : null}
    </Box>
  );
}

/* 이번 스프린트에서 **내 몫**의 진척. 도넛은 구성비를 보여주고, 옆의 숫자가 같은 값을
 * 글자로 말한다(그림을 못 보는 사람도 정보량이 같다 — charts/base.jsx 의 규칙). */
function SprintProgress({ sprint }) {
  if (!sprint) {
    return (
      <Typography variant="body2" color="text.secondary">
        티켓 소스를 읽지 못해 이번 주 진척을 계산할 수 없습니다. 관리자에게 문의하세요.
      </Typography>
    );
  }
  if (!sprint.assigned) {
    return (
      <EmptyState
        art="tickets"
        title="이번 주 내 몫이 없습니다"
        help={`${sprint.window.start} 주에 마감인 내 티켓이 없습니다.`}
      />
    );
  }
  const rate = sprint.completion_rate;
  return (
    <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "minmax(0,1fr)", sm: "auto minmax(0,1fr)", lg: "minmax(0,1fr)" }, alignItems: "center", justifyItems: "center" }}>
      <Donut
        segments={[
          { label: "완료", value: sprint.done, color: "success" },
          { label: "남음", value: sprint.remaining, color: "primary" },
          { label: "취소", value: sprint.cancelled, color: "warning" },
        ]}
        unit="건"
        centerLabel={rate == null ? "-" : rate + "%"}
        emptyLabel="이번 주 티켓 없음"
      />
      <Box sx={{ display: "grid", gap: 0.5, justifyItems: { xs: "center", sm: "start", lg: "center" } }}>
        <Typography variant="body2" color="text.secondary">
          {sprint.window.start} ~ {sprint.window.end_exclusive} 이전
        </Typography>
        <Typography variant="body2">
          내 티켓 {sprint.assigned}건 중 {sprint.done}건 완료
          {sprint.overdue ? `, 지연 ${sprint.overdue}건` : ""}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          예상 WD {sprint.est_wd_done} / {sprint.est_wd_total}
        </Typography>
      </Box>
    </Box>
  );
}

function RecentDocuments({ items }) {
  if (!items.length) {
    return (
      <EmptyState art="docs" title="최근 바뀐 문서가 없습니다"
        help="팀 문서가 수정되면 여기에 최신 순으로 표시됩니다." />
    );
  }
  return (
    <Stack component="ul" gap={1} sx={{ listStyle: "none", m: 0, p: 0 }}>
      {items.map((d) => (
        <RowLink
          key={d.id}
          href={"#/team-docs/" + d.id}
          title={d.title}
          badge={d.document_type ? <Badge value={d.document_type} kind="info" /> : null}
          meta={fmtRelative(d.last_edited)}
        />
      ))}
    </Stack>
  );
}

/* 내 게시판 활동 요약(내 글·받은 댓글·조회). 게시판이 꺼져 있거나(404) 로딩 중이면 조용히
 * 숨긴다 — 예전 홈에 있던 위젯을 그대로 옮겨 왔다(기능을 잃지 않는다). 최근 글 목록과 같은
 * 카드에 두어 카드 수를 늘리지 않는다. */
function MyBoardStats() {
  const q = useQuery({ queryKey: ["board-mine"], queryFn: () => api("/api/board/mine"), retry: false });
  if (q.isError || !q.data) return null;
  const s = q.data.summary || { post_count: 0, comment_count_received: 0, view_count_total: 0 };
  const stat = (num, label) => (
    <Box sx={{ display: "grid", gap: 0.25 }}>
      <Typography component="span" sx={{ fontSize: "1.125rem", fontWeight: FONT_WEIGHT.extrabold, lineHeight: 1.1 }}>{num}</Typography>
      <Typography component="span" variant="caption" color="text.secondary">{label}</Typography>
    </Box>
  );
  return (
    <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(3, minmax(0,1fr))", mb: 2 }}>
      {stat(s.post_count, "내 글")}
      {stat(s.comment_count_received, "받은 댓글")}
      {stat(s.view_count_total, "조회")}
    </Box>
  );
}

function RecentBoard({ items }) {
  if (!items.length) {
    return (
      <EmptyState art="board" title="아직 올라온 글이 없습니다"
        help="자유게시판에 글이 올라오면 여기에 표시됩니다."
        action={<Button variant="primary" size="sm" href="#/board">자유게시판 열기</Button>} />
    );
  }
  return (
    <Stack component="ul" gap={1} sx={{ listStyle: "none", m: 0, p: 0 }}>
      {items.map((p) => (
        <RowLink
          key={p.id}
          href={"#/board/" + p.id}
          title={p.title}
          badge={p.is_pinned ? <Badge value="고정" kind="info" /> : null}
          meta={`${p.author_name || "-"}, 댓글 ${p.comment_count}`}
        />
      ))}
    </Stack>
  );
}

/* 오른쪽 레일 — 진척과 최근 변경. ≥lg 에서만 옆으로 붙고 그 아래에서는 본문 뒤에 쌓인다. */
function SideRail({ data }) {
  const recent = data.recent || {};
  return (
    <Stack gap={2.5}>
      <Card>
        <SectionTitle component="h2" title="이번 주 내 진척" action={<Link href="#/sprint" underline="hover">스프린트 회의</Link>} />
        <SprintProgress sprint={data.sprint} />
      </Card>
      <Card>
        <SectionTitle component="h2" title="최근 문서" action={<Link href="#/team-docs" underline="hover">문서 전체</Link>} />
        <RecentDocuments items={recent.documents || []} />
      </Card>
      <Card>
        <SectionTitle component="h2" title="게시판" action={<Link href="#/board" underline="hover">자유게시판</Link>} />
        <MyBoardStats />
        <RecentBoard items={recent.board || []} />
      </Card>
    </Stack>
  );
}

/* 미러 신선도 — '지금 보는 숫자가 언제 것인가'. 정상이면 조용히 한 줄, 문제가 있으면 눈에 띄게. */
function Freshness({ sync }) {
  if (!sync) return null;
  const stale = sync.status !== "ok" || sync.truncated;
  return (
    <Typography
      variant="caption"
      // warning.main은 badge/tint 배경 위 전용이다 — 이 텍스트는 page background.default
      // 위에 바로 얹혀 4.48:1로 WCAG AA 4.5 미달이었다(Chrome E2E contrast 실측).
      // warning.strong이 이미 이 정확한 경계 문제(theme.js QAH-03)를 위해 만들어져 있었다.
      color={stale ? "warning.strong" : "text.secondary"}
      sx={{ display: "block", mb: 1.5 }}
    >
      티켓 동기화 {sync.status === "ok" ? "정상" : "확인 필요"}, 마지막 성공 {fmtRelative(sync.last_success_at)}
      {sync.truncated ? ", 일부만 동기화됨(관리자 확인 필요)" : ""}
    </Typography>
  );
}

function useToday() {
  return useQuery({
    queryKey: ["home", "today"],
    queryFn: () => api("/api/home/today"),
    retry: false,
    // 홈은 탭을 열어 둔 채로 오래 머문다 — 30초면 알림·채팅 배지가 충분히 따라온다.
    // VIS-160: staleTime만으로는 재조회가 안 일어난다(다음 mount/refetchOnWindowFocus를
    // 기다려야 한다) — 화면이 떠 있는 동안 실제로 30초마다 갱신하려면 refetchInterval이
    // 따로 필요하다(Dashboard.jsx의 같은 패턴). 숨은 탭에서는 react-query
    // 기본값(refetchIntervalInBackground=false)이 저절로 멈춘다(polling-visibility.test.js).
    staleTime: 30000,
    refetchInterval: 30000,
  });
}

export function Home() {
  const q = useToday();
  const nav = useNavigate();
  const [focus, setFocus] = React.useState("due_today");
  const [editing, setEditing] = React.useState(null);

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="" title="오늘" spot="mywork" />
      {q.isLoading ? (
        <>
          {/* 스켈레톤은 실제 배치와 같은 격자를 쓴다 — 로딩이 끝나는 순간 요소가 뛰지 않는다. */}
          <Box sx={STAT_GRID}>
            {Array.from({ length: 6 }).map((_, i) => (
              <Paper key={i} variant="outlined" sx={{ p: 3 }}><Skeleton lines={2} /></Paper>
            ))}
          </Box>
          <Box sx={BODY_GRID}>
            <Card><Skeleton lines={6} /></Card>
            <Card><Skeleton lines={4} /></Card>
          </Box>
        </>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        <Fade in timeout={220}>
          {/* Fade 는 자식 하나에 ref 를 걸어야 한다 — div 로 감싼다. */}
          <div>
            <HomeBody
              data={q.data || {}}
              focus={focus}
              onFocus={setFocus}
              onEdit={setEditing}
              onOpen={(t) => nav("/tickets/" + t.id, { state: { from: "/me" } })}
            />
          </div>
        </Fade>
      )}
      <TicketEditModal ticket={editing} open={!!editing} onClose={() => setEditing(null)} />
    </div>
  );
}

/* 본문 — 로딩·오류가 아닌 정상 상태만 그린다(위 컴포넌트가 분기를 이미 끝냈다). */
function HomeBody({ data, focus, onFocus, onEdit, onOpen }) {
  const tickets = data.tickets || {};
  const inbox = data.inbox || {};
  const conn = ticketConnState(tickets);
  const view = VIEWS.find((v) => v.key === focus) || VIEWS[0];
  const rows = (tickets[view.key] && tickets[view.key].items) || [];
  const total = (tickets[view.key] && tickets[view.key].count) || 0;
  const anyTicket = VIEWS.some((v) => tickets[v.key] && tickets[v.key].count > 0);
  // 채팅이 꺼진 설치에서는 chat_unread 가 null 이다(0 과 다른 뜻) — 카드 자리를 '막힘'이 채운다.
  const chatOff = inbox.chat_unread == null;

  return (
    <>
      <Freshness sync={data.sync} />
      <Box sx={STAT_GRID}>
        <StatCard value={tickets.due_today ? tickets.due_today.count : null} label="오늘 마감"
          kind={tickets.due_today && tickets.due_today.count ? "warn" : undefined}
          active={focus === "due_today"} onClick={() => onFocus("due_today")} />
        <StatCard value={tickets.overdue ? tickets.overdue.count : null} label="지연"
          kind={tickets.overdue && tickets.overdue.count ? "danger" : undefined}
          active={focus === "overdue"} onClick={() => onFocus("overdue")} />
        <StatCard value={tickets.in_progress ? tickets.in_progress.count : null} label="진행 중"
          active={focus === "in_progress"} onClick={() => onFocus("in_progress")} />
        <StatCard value={tickets.due_soon ? tickets.due_soon.count : null} label="7일 내 마감"
          active={focus === "due_soon"} onClick={() => onFocus("due_soon")} />
        <StatCard value={inbox.notifications_unread} label="안 읽은 알림"
          kind={inbox.notifications_unread ? "info" : undefined}
          onClick={() => { window.location.hash = "#/notifications"; }} />
        {chatOff ? (
          <StatCard value={tickets.blocked ? tickets.blocked.count : null} label="막힘(이슈)"
            kind={tickets.blocked && tickets.blocked.count ? "danger" : undefined}
            active={focus === "blocked"} onClick={() => onFocus("blocked")} />
        ) : (
          <StatCard value={inbox.chat_unread} label="안 읽은 채팅"
            kind={inbox.chat_unread ? "info" : undefined}
            onClick={() => { window.location.hash = "#/chat-rooms"; }} />
        )}
      </Box>

      <Box sx={BODY_GRID}>
        <Stack gap={2.5} sx={{ minWidth: 0 }}>
          <Card>
            {/* SEM-02: /me는 h1(PageHeader "오늘") 하나 아래 h3 다섯 개(이 카드+AssistantPanel의
                "AI 도우미"+TeamChatWidget의 "팀 채팅"+SideRail 셋)가 직결돼 h2가 아예 없었다.
                SectionTitle 기본값(h3)은 그대로 두고(다른 소비처가 이미 올바르게 h2 아래 h3로
                쓴다 — kit.jsx 주석 참고) 여기서만 명시적으로 h2를 준다. */}
            <SectionTitle
              component="h2"
              title={`${view.label} (${total}건)`}
              action={<Link href="#/my-tickets" underline="hover">내 티켓 전체</Link>}
            />
            {conn ? conn : rows.length ? (
              <>
                <DataTable
                  /* compact: 홈의 왼쪽 열은 2단 배치라 좁다 — 계획서 4K 계약의 '표(핵심열)'을
                     그대로 따른다(난이도·예상 WD 는 빼고, 편집은 아이콘). 전체 열을 넣으면
                     1366 화면에서 마감·편집이 잘려 가로로 긁어야 보였다. */
                  columns={ticketColumns({ onEdit, onOpen, compact: true })}
                  rows={rows}
                  rowKey={(t) => t.id}
                />
                {total > rows.length ? (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
                    {rows.length}건만 표시했습니다.{" "}
                    <Link href="#/my-tickets" underline="hover">내 티켓에서 {total}건 모두 보기</Link>
                  </Typography>
                ) : null}
              </>
            ) : anyTicket ? (
              /* 다른 칸에는 티켓이 있는데 이 칸만 비었다 — '검색 결과 없음'과 같은 상황이다.
                 그림도 문장도 '데이터 없음'과 달라야 사용자가 자기가 고른 칸 때문임을 안다. */
              <EmptyState
                art="search"
                title={`${view.label}에 해당하는 티켓이 없습니다`}
                help="다른 칸을 눌러 보거나 전체 목록에서 확인하세요."
                action={<Button size="sm" onClick={() => onFocus("in_progress")}>진행 중 전체 보기</Button>}
              />
            ) : (
              /* 내 티켓 자체가 하나도 없다 — 진짜 '데이터 없음'. */
              <EmptyState
                art="tickets"
                title="담당한 티켓이 없습니다"
                situation="지금 나에게 배정된 티켓이 없습니다."
                steps={["미할당 티켓에서 가져오거나", "새 티켓을 직접 만들 수 있습니다."]}
                action={<Button variant="primary" size="sm" href="#/unassigned">미할당 티켓 보기</Button>}
              />
            )}
          </Card>
          <AssistantPanel />
          <TeamChatWidget />
        </Stack>
        <SideRail data={data} />
      </Box>
    </>
  );
}
