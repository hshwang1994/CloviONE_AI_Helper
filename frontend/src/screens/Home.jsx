import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Fade from "@mui/material/Fade";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtRelative } from "../lib/format.js";
import {
  Badge, Button, Card, DataTable, EmptyState, ErrorState, MetricStrip, PageHeader, SectionTitle, Skeleton,
} from "../ui/kit.jsx";
import { Donut } from "../ui/charts/Donut.jsx";
import { MirrorNotice } from "../ui/MirrorNotice.jsx";
import { GRID_GAP } from "../ui/density.js";
import { FONT_WEIGHT } from "../ui/theme.js";
import { ticketColumns, ticketConnState, TicketEditModal } from "./MyTickets.jsx";
import { AssistantPanel } from "./AssistantPanel.jsx";
import { WorkSection } from "./WorkSummary.jsx";

/* 홈 '오늘' 커맨드 센터 (계획서 Phase 5).
 *
 * 예전 홈(MyWork)은 /api/tickets/mine 하나만 보고 티켓 카드 네 장을 그렸다. 그래서 안 읽은
 * 알림·채팅, 이번 스프린트에서 내 몫, 최근 문서·게시판 변경은 각각 다른 화면에 흩어져 있었고,
 * "오늘 뭘 해야 하지"를 알려면 화면 네 개를 돌아야 했다. 이제 서버가 그 조합을 한 번에
 * 내려 준다(GET /api/home/today) — 요청 1회, Notion 왕복 0회.
 *
 * 이 화면이 지키는 계약 세 가지:
 *   1) **4K 반응형** — 지표는 판독 줄(MetricStrip)이라 폭에 따라 스스로 접힌다. 본문 격자는
 *      MUI Grid 를 쓰지 않는다(MUI 7 에서 xs={12} 가 조용히 무시된다). Box + display:grid 다.
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
      {/* 「남음」은 **Brand 시리즈 슬롯**을 받는다(색을 안 준다). 예전 값 `"primary"` 는
          사용자 Accent 라, 청록을 고른 사람의 화면에서는 이 도넛이 청록이었다 —
          제품 정체성이 개인 설정을 따라가던 자리다(PLAN §Data Visualization 이 이 줄을
          이름으로 지목했다). 「완료」·「취소」는 색이 곧 상태라 상태색을 유지한다.
          `total` 을 명시해 링의 모수가 «그려진 조각의 합»이 아니라 **내 티켓 전체**가 되게
          한다 — 안 주면 값 0 인 상태가 조용히 빠져 도넛이 전체를 설명한다고 착각하게 된다. */}
      <Donut
        segments={[
          { label: "완료", value: sprint.done, color: "success" },
          { label: "남음", value: sprint.remaining },
          { label: "취소", value: sprint.cancelled, color: "warning" },
        ]}
        total={sprint.assigned}
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

/* 오른쪽 레일 — 진척과 최근 변경. ≥lg 에서만 옆으로 붙고 그 아래에서는 본문 뒤에 쌓인다.
 *
 * PA-RC-0018 direction 6: 팀 채팅·게시판 카드는 여기서 뺐다 — 둘 다 사이드바에 이미 자기
 * 목적지가 있다(navConfig.js "채팅방" "/chat-rooms", "자유게시판" "/board"). `/me`는
 * "오늘 내가 할 일"에 좁힌다: 티켓(본문)과 그 티켓의 이번 주 진척·최근 문서 변경(둘 다
 * 업무와 바로 이어지는 맥락)만 남긴다. */
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
    </Stack>
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
          {/* 스켈레톤은 실제 배치와 같은 모양을 쓴다 — 로딩이 끝나는 순간 요소가 뛰지 않는다.
              이제 지표는 격자 여섯 칸이 아니라 판독 줄 둘이다. */}
          <Box sx={{ display: "grid", gap: 1.5, mb: 2.5 }}>
            <Card sx={{ py: 1.5 }}><Skeleton lines={2} /></Card>
            <Card sx={{ py: 1.5 }}><Skeleton lines={2} /></Card>
          </Box>
          <Box sx={BODY_GRID}>
            <Card><Skeleton lines={6} /></Card>
            <Card><Skeleton lines={4} /></Card>
          </Box>
          {/* VIS-35로 AssistantPanel이 격자 밖 전체 폭으로 내려왔다 — 스켈레톤도 같은 3번째
              구역을 둬야 로딩이 끝나는 순간 이 블록만큼 페이지가 아래로 밀리지 않는다. */}
          <Box sx={{ mt: 2.5 }}><Card><Skeleton lines={3} /></Card></Box>
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
  const conn = ticketConnState(tickets);
  const view = VIEWS.find((v) => v.key === focus) || VIEWS[0];
  const rows = (tickets[view.key] && tickets[view.key].items) || [];
  const total = (tickets[view.key] && tickets[view.key].count) || 0;
  const anyTicket = VIEWS.some((v) => tickets[v.key] && tickets[v.key].count > 0);

  return (
    <>
      {/* 정상 동기화 상태는 사용자에게 알리지 않는다 (지시 1 · 29). 실패했거나 한 번도
          성공 못 했을 때만 말한다 — 그 판정은 공용 `MirrorNotice` 한 곳에 있다. 예전에는
          이 화면이 자기 `Freshness` 로 "티켓 동기화 정상, 마지막 성공 …"을 상시로 띄웠다. */}
      <MirrorNotice sync={data.sync} unit="티켓" />
      {/* 지표 줄 (지시 2).
        *
        * 예전에는 흰 카드 여섯 장이 한 격자에 깔렸고, 여섯이라는 개수 자체가 격자 산수에서
        * 나온 값이었다 — 그래서 채팅이 켜져 있으면 '막힘(이슈)'이 자리가 없다는 이유만으로
        * 사라졌다. 판독 줄에는 그 산수가 없으므로 막힘은 항상 있다.
        *
        * 여기 있던 '안 읽은 알림'·'안 읽은 채팅' 두 칸은 뺐다. 같은 숫자를 상단 종
        * (알림의 단일 진입점, 지시 1)과 사이드바 배지(navConfig `notifUnread`/`chatUnread`)가
        * 이미 말하고 있어서 한 화면에 세 번 나왔고, 무엇보다 이 줄의 나머지 칸은 아래 목록을
        * 거르는 **필터**인데 그 둘만 다른 화면으로 나가는 링크라 누를 때 무슨 일이
        * 일어나는지가 칸마다 달랐다(지시 62: 행동으로 이어지지 않는 지표는 두지 않는다). */}
      <Box sx={{ mb: 2.5 }}>
        <MetricStrip
          ariaLabel="내 티켓"
          items={VIEWS.map((v) => ({
            key: v.key,
            value: tickets[v.key] ? tickets[v.key].count : null,
            label: v.label,
            // 색은 셀 값이 있을 때만 — 0건인 '지연'을 빨갛게 칠하면 없는 문제를 만든다.
            kind: v.kind && tickets[v.key] && tickets[v.key].count ? v.kind : undefined,
            primary: v.key === "due_today",
            active: focus === v.key,
            onClick: () => onFocus(v.key),
          }))}
        />
      </Box>

      {/* VIS-35: AssistantPanel은 예전엔 왼쪽 열 안에서 티켓 카드 아래로 쌓여 있었다 — 티켓
          행 수만큼 커지는 카드 하나(왼쪽)와 담당자 배지가 없는 고정형 카드 둘(오른쪽 SideRail)이
          같은 열에서 경쟁하면 실데이터가 있는 계정일수록 왼쪽이 오른쪽보다 훨씬 길어져 오른쪽
          아래에 큰 흰 여백이 남았다(VIS-36/37이 SideRail에서 팀채팅·게시판 위젯을 뺀 뒤로 격차가
          더 벌어졌다). 두 열의 높이를 억지로 맞추는 대신(내용 없는 카드를 늘리면 그 자체가
          더 어색하다), 행 수와 무관하게 항상 일정한 AssistantPanel을 격자 **밖**, 전체 폭으로
          내려 격차의 원인이 되는 조합 자체를 없앤다 — 4개 탭(브리핑/스탠드업/다이제스트/트리아지)도
          좁은 2fr 칸보다 전체 폭에서 더 잘 읽힌다. */}
      <Box data-testid="home-body-grid" sx={BODY_GRID}>
        <Stack gap={2.5} sx={{ minWidth: 0 }}>
          <Card>
            {/* SEM-02: /me는 h1(PageHeader "오늘") 하나 아래 SectionTitle 여러 개(이 카드+
                AssistantPanel의 "AI 도우미"+SideRail 셋)가 전부 기본값(h3)으로 직결돼 h2가
                아예 없었다 — 이 화면에서만 SectionTitle 호출마다 명시적으로 h2를 준다(다른
                소비처는 이미 h2 아래 h3로 올바르게 쓴다 — kit.jsx 주석 참고). PA-RC-0018
                전에는 TeamChatWidget "팀 채팅"·SideRail의 "게시판"도 같은 층에 있었으나
                direction 6으로 카드에서 빠지고 사이드바 "채팅방"/"자유게시판"으로 돌아갔다. */}
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
        </Stack>
        <SideRail data={data} />
      </Box>
      {/* 내 업무 요약 — 예전에는 **관리자 대시보드**에 있었다(0060 §3).
          "내 미완료·이번 주 마감·지연 티켓" 과 "차질 프로젝트·지연 마일스톤" 은 관리자에게도
          개인 업무이고, 관리자 콘솔(Control Plane)이 아니라 여기가 그 자리다. 프로젝트
          숫자는 이미 조회 범위로 걸러진 값이라(app/home/work.py) 조직·부서 관리자에게는
          자기 범위 요약이 된다. */}
      <Box sx={{ mt: 2.5 }}>
        <WorkSection />
      </Box>
      <Box sx={{ mt: 2.5 }}>
        <AssistantPanel />
      </Box>
    </>
  );
}
