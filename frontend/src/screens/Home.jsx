import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import Fade from "@mui/material/Fade";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { fmtDayKo, fmtRelative } from "../lib/format.js";
import {
  Badge, Button, Callout, Card, DataTable, EmptyState, ErrorState, MetricStrip, PageHeader,
  ScrollArea, SectionTitle, Skeleton, SubGroup,
} from "../ui/kit.jsx";
import { Donut } from "../ui/charts/Donut.jsx";
import { BUDGET_BODY, BUDGET_SCROLL, GRID_GAP, plateBudget } from "../ui/density.js";
import { KO_WORD_BREAK } from "../ui/theme.js";
import { ticketColumns, ticketConnState, TicketEditModal, useInlineStatusEdit } from "./MyTickets.jsx";
import { useTicketSignals } from "../lib/ticketSignals.js";
import { AssistantPanel, mostUrgentBucket, URGENCY_ORDER } from "./AssistantPanel.jsx";
import { lastDayOf, WorkSection } from "./WorkSummary.jsx";

/* 홈 '오늘' 커맨드 센터.
 *
 * 서버가 한 번에 조합해 준다(GET /api/home/today) — 요청 1회, 바깥 왕복 0회.
 *
 * ## 정보 우선순위 넷
 *
 *   1. 오늘 당장 처리해야 할 일   판독 줄(필터) + 그 칸의 티켓 표
 *   2. 이번 주 업무 상태          오른쪽 레일 첫 카드(진척 · 프로젝트 · 주마다 끝낸 일)
 *   3. 최근 문서                  오른쪽 레일 둘째 카드
 *   4. AI 가 해석해 주는 업무     본문 아래 AI 도우미
 *
 * **같은 KPI 를 두 자리에서 말하지 않는다.** 실측(2026-08-26)에서 「지연 12」가 판독 줄과
 * 「내 업무」 줄에 나란히 있었고, AI 브리핑이 그 둘을 문장으로 한 번 더 읽었다 — 한 화면에
 * 같은 수가 세 번 있었다. 티켓 축의 수는 판독 줄이 유일하게 말하고, 레일은 프로젝트와
 * 마일스톤(다른 축)을, AI 도우미는 해석을 맡는다.
 *
 * ## 두 열은 서로의 높이에 매이지 않는다
 *
 * 🔴 예전에는 본문 격자가 **한 줄**이었고 그 아래에 「내 업무」와 AI 도우미가 전체 폭으로
 * 이어졌다. 격자 한 줄의 높이는 두 칸 중 큰 쪽이 정하므로, 오른쪽 레일이 왼쪽 티켓 카드보다
 * 길면 **왼쪽 카드 아래에 레일 높이만큼의 빈 판**이 생겼다. 티켓이 두 건인 계정에서 그
 * 공백이 화면 절반이었다.
 *
 * 간격을 줄여서 될 일이 아니다 — 원인은 여백이 아니라 **한 줄짜리 격자**다. 지금은 격자가
 * 두 개의 독립된 세로 흐름을 담는다. 각 열은 자기 카드를 자기 순서로 쌓고, 한쪽이 길어져도
 * 반대쪽 다음 카드는 따라 내려가지 않는다. 격자 **뒤에 오는 것을 두지 않는 것**도 같은
 * 규칙의 일부다: 격자 뒤에 무엇이든 두면 그것이 다시 두 열 중 큰 쪽을 기다린다.
 *
 * 카드에 억지로 같은 높이를 주지도 않는다. 높이를 맞추려고 짧은 카드를 늘리면 그 안이
 * 비고, 비어 있는 이유를 아무도 설명할 수 없다.
 *
 * ## 그 밖에 이 화면이 지키는 것
 *
 *   * **빈 상태를 구분한다** — '필터를 걸어서 없다'(art="search")와 '원래 없다'는 다른
 *     화면이다. 같은 문장을 쓰면 사용자는 데이터가 사라졌다고 생각한다.
 *   * **px 폰트 크기를 쓰지 않는다** — 4K 대응이 styles/root.css 의 루트 폰트사이즈 레버
 *     하나로 되어 있어서, px 를 쓰면 그 조각만 4K 에서 작게 남는다.
 *   * **모든 격자 트랙이 minmax(0,...)** — 그냥 "1fr" 은 트랙이 내용보다 작아지지 않게 해서
 *     긴 문서 제목 하나가 페이지에 가로 스크롤을 만든다.
 *
 * 이 화면의 **모든 숫자**의 출처표는 docs/DASHBOARD_METRICS.md 3절에 있다. '오늘'과
 * '이번 주'는 서버가 KST 달력일로 정해서 내려 준다 — 화면에서 new Date() 로 다시 판정하면
 * 브라우저 시간대에 따라 서버와 다른 날을 '오늘'이라고 부르게 된다.
 */

/* 본문 두 열 — 왼쪽은 본문 흐름, 오른쪽은 레일. 좁으면 한 줄로 쌓인다.
 *
 * ## 레일 폭은 «정보 밀도» 로 정한다
 *
 * 실측(2026-08-26): 상한이 22rem 이라 1366 과 1920 에서 레일이 **똑같이 352px** 였다.
 * 그 폭에서 「2026-08-24 부터 2026-08-30 까지, 예상 WD 3 / 10.5」가 두 줄로 꺾이고,
 * 주별 막대는 110px 로 쪼그라들었다. 1920 은 본문에 1,232px 를 주면서 레일에는 1366 과
 * 같은 폭을 준 셈이다 — 남는 폭을 한쪽만 가져갔다.
 *
 * 그래서 상한을 **비율과 절대값 가운데 작은 쪽**으로 준다. 좁은 데스크톱에서는 비율이
 * 이겨 레일이 본문을 잡아먹지 않고, 넓어지면 절대값이 이겨 레일이 끝없이 자라지 않는다.
 * 하한(20rem)은 도넛과 범례가 나란히 서지 못하고 접히는 폭이다. 실측:
 *
 *   1200 레일 320 · 본문 544     1366 레일 358 · 본문 672
 *   1920 레일 448 · 본문 1,136   2560 레일 504 · 본문 1,680  (2200 이상은 루트 18px)
 *
 * 중단점을 하나만 쓰는 것도 이유가 있다 — 폭이 계단으로 튀면 그 경계에서 줄바꿈이 통째로
 * 바뀐다. 두 값 다 rem 이라 4K 루트 폰트사이즈 레버를 함께 탄다. */
const BODY_GRID = {
  display: "grid", gap: GRID_GAP, alignItems: "start",
  gridTemplateColumns: {
    xs: "minmax(0, 1fr)",
    lg: "minmax(0, 1fr) minmax(20rem, min(28rem, 34%))",
  },
};

/* 업무 판의 **높이 계약**. 값과 근거는 `ui/density.js::PLATE_BUDGET.today` 한 곳에 있다.
 *
 * 아래 `VIEWS` 다섯은 판 다섯이 아니라 **한 판의 다섯 칸**이다. 그래서 이 판은 예산
 * (범위)이 아니라 계약(하나의 높이)을 갖는다 — 데스크톱에서 어떤 칸을 누르든, 그 칸에
 * 0건이 있든 30건이 있든 판의 바깥 높이가 같다. 판이 칸마다 다른 높이로 서면 바로 아래에
 * 있는 AI 도우미가 누를 때마다 위아래로 뛴다(실측: 같은 판이 164~512px 사이를 오갔다).
 *
 * 안에서는 셋이 각자 자기 일을 한다:
 *   머리   제목과 「내 티켓 전체」 — 계약 높이 안에 고정이라 굴려도 안 사라진다
 *   몸     남는 높이를 받는 칸(`BUDGET_BODY`). 목록만 그 안에서 굴린다(`BUDGET_SCROLL`)
 *   꼬리   「N건만 표시했습니다」 — 몸 밖이라 언제나 보인다
 *
 * 0건은 몸 전체를 채우는 가운데 구성(`EmptyState layout="card"`)이라, 계약 높이가 곧
 * 클로비가 서는 자리가 된다. 소량일 때 목록 아래가 남는 것은 이 판이 받아들이는 값이다 —
 * 「칸마다 같은 높이」와 「빈 자리 없음」은 한 판에서 동시에 참일 수 없고, 사용자가 이
 * 판에서는 앞을 골랐다(D-348). 좁은 화면에는 계약이 없다 — 세로로 자연스럽게 흐른다. */
const WORK_PANEL = plateBudget("today");
const WORK_PANEL_BODY = BUDGET_BODY;

const VIEWS = [
  { key: "due_today", label: "오늘 마감", kind: "warn" },
  { key: "overdue", label: "지연", kind: "danger" },
  { key: "in_progress", label: "진행 중" },
  { key: "due_soon", label: "7일 내 마감" },
  // 「막힘(이슈)」였다. 괄호 안이 티켓 상태값 그대로라, 그 값을 모르는 사람에게는 설명이
  // 아니라 암호였다. 상태값은 아래 목록의 배지가 이미 보여 준다.
  { key: "blocked", label: "막힌 일", kind: "danger" },
];

/* 처음 열 칸을 정하는 순서.
 *
 * 🔴 예전에는 언제나 `"due_today"` 였다. 그래서 오늘 마감이 0 이고 지연이 14 인 계정에서
 * 이 화면의 **가장 큰 판**이 「오늘 마감에 해당하는 티켓이 없습니다」로 비어 있었고, 바로
 * 그 아래 AI 도우미는 같은 데이터를 읽고 「마감이 지난 티켓 14건이 오늘 가장 급합니다」라고
 * 말했다(실측 2026-09-01). 한 화면이 서로 반대되는 말을 둘 하고 있었고, 그 사이에 정작
 * 급한 티켓 열넷은 한 번 더 눌러야 나왔다.
 *
 * **「오늘 마감」이 먼저인 것은 그대로 둔다** — 이 화면의 이름이 「오늘」이고, 판독 줄의
 * 지배값도 그 칸이다. 바꾸는 것은 **그 칸이 비었을 때**뿐이고, 그때 무엇을 여는지는
 * AI 도우미와 **같은 급한 순**(`URGENCY_ORDER`)이 정한다. 순서를 여기 다시 적지 않는
 * 이유는 그것이 갈라진 결과가 바로 위에 적은 그 화면이기 때문이다.
 *
 * 사용자가 칸을 한 번 누르면 그 선택이 이긴다(아래 `focus`) — 30초마다 오는 갱신이 개수를
 * 바꿨다고 보고 있던 칸이 발밑에서 옮겨 가면 안 된다. */
const DEFAULT_FOCUS_ORDER = ["due_today", ...URGENCY_ORDER.filter((k) => k !== "due_today")];
const defaultFocus = (tickets) => mostUrgentBucket(tickets, DEFAULT_FOCUS_ORDER) || "due_today";

/* 목록 한 줄(문서 공용). 제목은 링크, 오른쪽은 메타.
 *
 * 잘림(ellipsis)이 실제로 동작하려면 **줄여야 하는 모든 flex 조상**에 minWidth:0 이 있어야
 * 한다. 기본값 min-width:auto 는 "내용보다 작아지지 마라"는 뜻이라, 하나라도 빠지면 긴 제목이
 * 줄지 않고 부모를 밀어낸다. */
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
      <Typography variant="body2" color="text.secondary" sx={KO_WORD_BREAK}>
        티켓 소스를 읽지 못해 이번 주 진척을 계산할 수 없습니다. 관리자에게 문의하세요.
      </Typography>
    );
  }
  if (!sprint.assigned) {
    return (
      <EmptyState
        art="tickets"
        title="이번 주에 맡은 일이 없습니다"
        help={`${fmtDayKo(sprint.window.start)}부터 한 주 동안 마감인 내 티켓이 없습니다.`}
      />
    );
  }
  const rate = sprint.completion_rate;
  const lastDay = lastDayOf(sprint.window.end_exclusive);
  const wdTotal = sprint.est_wd_total;
  return (
    <Box sx={{ display: "grid", gap: 1.5, justifyItems: { xs: "start", sm: "start", lg: "center" } }}>
      {/* 「남음」은 **Brand 시리즈 슬롯**을 받는다(색을 안 준다). 예전 값 `"primary"` 는
          사용자 Accent 라, 청록을 고른 사람의 화면에서는 이 도넛이 청록이었다.
          「완료」·「취소」는 색이 곧 상태라 상태색을 유지한다. `total` 을 명시해 링의 모수가
          «그려진 조각의 합»이 아니라 **내 티켓 전체**가 되게 한다. */}
      <Donut
        question="이번 주에 맡은 일 가운데 얼마나 끝냈는지 봅니다."
        segments={[
          { label: "완료", value: sprint.done, color: "success" },
          { label: "남음", value: sprint.remaining },
          { label: "취소", value: sprint.cancelled, color: "warning" },
        ]}
        total={sprint.assigned}
        unit="건"
        centerLabel={rate == null ? "-" : rate + "%"}
        emptyLabel="이번 주 티켓 없음"
        revealKey={`home-sprint:${sprint.window.start}:${sprint.done}:${sprint.remaining}:${sprint.cancelled}:${sprint.assigned}`}
      />
      <Box sx={{ display: "grid", gap: 0.5, justifyItems: { xs: "start", lg: "center" }, textAlign: { xs: "left", lg: "center" } }}>
        <Typography variant="body2" sx={KO_WORD_BREAK}>
          내 티켓 {sprint.assigned}건 중 {sprint.done}건 완료
          {sprint.overdue ? `, 지연 ${sprint.overdue}건` : ""}
        </Typography>
        {/* 「이번 주」가 어느 주인지 화면이 스스로 말한다. 끝을 **포함되는 날**로 적는다 —
            계약값(end_exclusive)을 그대로 보이면 그 날이 포함인지 매번 다시 생각해야 한다.
            예전에는 이 자리가 「2026-08-24 부터 2026-08-30 까지, 예상 WD 3 / 10.5」였다.
            날짜는 매번 연·월·일로 다시 분해해야 했고 「WD」는 내부 낱말이다. 둘을 갈라
            각각 완전한 문장으로 적는다. */}
        <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>
          {fmtDayKo(sprint.window.start)}부터 {fmtDayKo(lastDay)}까지 마감인 일입니다.
        </Typography>
        {wdTotal > 0 ? (
          <Typography variant="caption" color="text.secondary" sx={KO_WORD_BREAK}>
            예상 작업량 {wdTotal}일 가운데 {sprint.est_wd_done}일치를 끝냈습니다.
          </Typography>
        ) : null}
      </Box>
    </Box>
  );
}

function RecentDocuments({ items }) {
  if (!items.length) {
    return (
      <EmptyState art="docs" title="최근 바뀐 문서가 없습니다"
        help="팀 문서가 바뀌면 여기에 최신 순으로 표시됩니다." />
    );
  }
  return (
    /* 문서는 계속 늘어나는 보조 목록이다 — 판의 예산이 남긴 높이만 쓰고 넘치면 굴린다.
       짧으면 스크롤바가 안 생기고, 그때는 초점도 안 받는다(`ScrollArea`). 제목과
       「문서 전체」는 이 칸 밖에 있어 언제나 보인다. */
    <ScrollArea sx={BUDGET_SCROLL} ariaLabel="최근 문서 목록">
      <Stack component="ul" gap={1} sx={{ listStyle: "none", m: 0, p: 0 }}>
        {items.map((d) => (
          <RowLink
            key={d.id}
            /* 서버가 주는 id 는 정본 문서(`documents.id`)다 — 옛 미러의 page id 가 아니다
               (S14 · C2, `app/home/readers.py`). 그래서 목적지도 정본 문서 화면이다. */
            href={"#/knowledge/" + d.id}
            title={d.title}
            badge={d.document_type ? <Badge value={d.document_type} kind="info" /> : null}
            meta={fmtRelative(d.last_edited)}
          />
        ))}
      </Stack>
    </ScrollArea>
  );
}

/* 오른쪽 레일 — 이번 주 상태와 최근 문서.
 *
 * 여기 있는 것은 전부 **훑는 정보**다. 누르면 자기 화면으로 나가고, 이 자리에서 무엇을
 * 고치지는 않는다. 팀 채팅·게시판 위젯은 여기 없다 — 둘 다 사이드바에 자기 목적지가
 * 이미 있다(navConfig.js). `/me` 는 "오늘 내가 할 일"에 좁힌다. */
function SideRail({ data }) {
  const recent = data.recent || {};
  return (
    <Stack gap={GRID_GAP} sx={{ minWidth: 0 }}>
      <Card sx={plateBudget("week")}>
        <SectionTitle
          component="h2"
          title="이번 주"
          action={<Link href="#/sprint" underline="hover">스프린트 회의</Link>}
        />
        {/* **핵심 요약은 굴리지 않는다** (사용자 지시 §3). 이 주에 얼마나 끝냈는가는 이
            판의 결론이라 언제나 같은 자리에 있어야 한다. 첫 묶음이므로 위에 가를 것이 없다. */}
        <SubGroup first>
          <SprintProgress sprint={data.sprint} />
        </SubGroup>
        {/* 세부(프로젝트 · 최근 완료 추이)만 예산 안에서 굴린다. 실선은 이 **고정된**
            상자가 갖는다 — `WorkSection` 안에 두면 굴릴 때 머리와 몸의 경계가 사라진다. */}
        <Box sx={{ ...BUDGET_BODY, mt: 2.5, pt: 2.5, borderTop: 1, borderColor: "divider" }}>
          <ScrollArea sx={BUDGET_SCROLL} ariaLabel="이번 주 세부 목록">
            <WorkSection />
          </ScrollArea>
        </Box>
      </Card>
      <Card sx={plateBudget("docs")}>
        <SectionTitle component="h2" title="최근 문서" action={<Link href="#/knowledge" underline="hover">문서 전체</Link>} />
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
  // `null` 은 「사용자가 아직 안 골랐다」다 — 그동안은 데이터가 칸을 정한다(`defaultFocus`).
  // 한 번 누르면 키가 들어오고, 그 뒤로는 갱신이 와도 그 칸이 유지된다.
  const [focus, setFocus] = React.useState(null);
  const [editing, setEditing] = React.useState(null);
  /* 🔴 **배경 갱신 한 번이 실패했다고 화면을 지우지 않는다.** 이 화면은 30초마다 스스로
     다시 읽고(`useToday`) 재시도를 안 한다 — 예전에는 `q.isError` 하나만 보고 오류 화면을
     그려서, 순간 끊김 한 번이면 이미 손에 들고 있던 오늘 티켓·이번 주·최근 문서가 통째로
     사라졌다. 마지막으로 성공한 값을 계속 보여 주고, **낡았다는 사실만** 배너로 말한다
     (관리자 대시보드가 같은 상황을 이미 그렇게 다룬다 — `Dashboard.jsx::staleAfterError`). */
  const staleAfterError = q.isError && !!q.data;

  return (
    <div className="c-screen">
      <PageHeader crumbRoot="" title="오늘" />
      {staleAfterError ? (
        <Box sx={{ mb: 2.5 }} role="status" aria-live="polite">
          <Callout tone="warn">실시간 갱신이 실패했습니다. 표시된 값이 최신이 아닐 수 있습니다. 새로고침해 주세요.</Callout>
        </Box>
      ) : null}
      {!q.data && q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        /* 스켈레톤은 **실제 배치와 같은 모양**을 쓴다 — 로딩이 끝나는 순간 요소가 뛰지
           않는다. 판독 줄은 판이 아니므로 카드로 감싸지 않는다. */
        <>
          <Box sx={{ mb: 2.5 }}><Skeleton lines={2} /></Box>
          <Box sx={BODY_GRID}>
            <Stack gap={GRID_GAP}>
              {/* 업무 판의 계약 높이를 스켈레톤에도 그대로 준다 — 이것이 없으면 로딩이
                  끝나는 순간 아래 AI 도우미가 한 판 높이만큼 아래로 밀린다. */}
              <Card sx={WORK_PANEL}><Skeleton lines={6} /></Card>
              <Card><Skeleton lines={5} /></Card>
            </Stack>
            <Stack gap={GRID_GAP}>
              <Card><Skeleton kind="chart" height="9rem" /></Card>
              <Card><Skeleton lines={5} /></Card>
            </Stack>
          </Box>
        </>
      ) : (
        <Fade in timeout={220}>
          {/* Fade 는 자식 하나에 ref 를 걸어야 한다 — div 로 감싼다. */}
          <div>
            <HomeBody
              data={q.data}
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
  const signalsOf = useTicketSignals();
  const statusEdit = useInlineStatusEdit();
  const tickets = data.tickets || {};
  const conn = ticketConnState(tickets);
  // 고른 칸이 없으면 데이터가 정한다(위 `defaultFocus`). 고른 뒤에는 그 선택이 이긴다.
  const focusKey = focus || defaultFocus(tickets);
  const view = VIEWS.find((v) => v.key === focusKey) || VIEWS[0];
  const rows = (tickets[view.key] && tickets[view.key].items) || [];
  const total = (tickets[view.key] && tickets[view.key].count) || 0;
  const anyTicket = VIEWS.some((v) => tickets[v.key] && tickets[v.key].count > 0);

  return (
    <>
      {/* 판독 줄 — 이 화면에서 **티켓 수를 말하는 유일한 자리**이고, 동시에 아래 목록을
        * 거르는 필터다. 칸마다 같은 일이 일어난다(누르면 아래가 바뀐다) — 예전에 여기 있던
        * '안 읽은 알림'·'안 읽은 채팅' 두 칸만 다른 화면으로 나가는 링크라 칸마다 결과가
        * 달랐고, 그 두 수는 상단 종과 사이드바 배지가 이미 말하고 있었다. */}
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
            active: view.key === v.key,
            onClick: () => onFocus(v.key),
          }))}
        />
      </Box>

      <Box data-testid="home-body-grid" sx={BODY_GRID}>
        {/* 본문 열 — 오늘 할 일과 그 해석. 두 카드 다 데이터 양에 따라 길이가 변한다. */}
        <Stack gap={GRID_GAP} sx={{ minWidth: 0 }}>
          {/* 업무 판 — 판독 줄에서 고른 칸의 내용이 여기 들어온다. 바깥 높이는 계약이다. */}
          <Card sx={WORK_PANEL}>
            {/* SEM-02: 이 화면은 h1(PageHeader "오늘") 아래 최상위 구역이 넷이고 전부 h2 다.
                제목과 「내 티켓 전체」는 목록 칸 밖에 있어 목록을 굴려도 안 사라진다. */}
            <SectionTitle
              component="h2"
              title={`${view.label} ${total}건`}
              action={<Link href="#/my-tickets" underline="hover">내 티켓 전체</Link>}
            />
            <Box sx={WORK_PANEL_BODY}>
              {conn ? conn : rows.length ? (
                <>
                  {/* 목록 칸만 굴린다 — 티켓이 늘어도 판은 계약 높이에 그대로 선다.
                      짧으면 스크롤바도 초점도 없고 목록이 위에서부터 그려진다(`ScrollArea`). */}
                  <ScrollArea sx={BUDGET_SCROLL} ariaLabel={`${view.label} 티켓 목록`}>
                    <DataTable
                      /* compact: 본문 열은 2단 배치라 좁다 — 4K 계약의 '표(핵심열)'을 그대로
                         따른다(난이도·예상 WD 는 빼고, 편집은 아이콘). 전체 열을 넣으면 1366
                         화면에서 마감·편집이 잘려 가로로 긁어야 보였다. */
                      columns={ticketColumns({ onEdit, onOpen, compact: true, signalsOf, statusEdit })}
                      rows={rows}
                      rowKey={(t) => t.id}
                      /* 굴려도 열 이름이 안 사라진다. 이 표를 감싼 것이 스크롤 컨테이너라
                         (`ScrollArea`) 붙는 자리가 그 칸의 위쪽이다. */
                      stickyHeader
                    />
                  </ScrollArea>
                  {/* 잘라서 보여 준 목록은 잘랐다고 말한다. `count` 는 언제나 진짜 총계라
                      (`app/home/aggregate.py::bucket`) 이 두 수가 어긋날 일이 없다. */}
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
                  layout="card"
                  art="search"
                  title={`${view.label}에 해당하는 티켓이 없습니다`}
                  help="다른 칸을 눌러 보거나 전체 목록에서 확인하세요."
                  action={<Button size="sm" onClick={() => onFocus("in_progress")}>진행 중 전체 보기</Button>}
                />
              ) : (
                /* 내 티켓 자체가 하나도 없다 — 진짜 '데이터 없음'. */
                <EmptyState
                  layout="card"
                  art="tickets"
                  title="담당한 티켓이 없습니다"
                  help="미할당 티켓에서 가져오거나 새 티켓을 직접 만들 수 있습니다."
                  action={<Button variant="primary" size="sm" href="#/unassigned">미할당 티켓 보기</Button>}
                />
              )}
            </Box>
          </Card>
          <AssistantPanel />
        </Stack>
        <SideRail data={data} />
      </Box>
    </>
  );
}
