import React from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { api } from "../lib/api.js";
import { Badge, Button, Card, EmptyState, ErrorState, SectionTitle, Skeleton } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import { BarSeries } from "../ui/charts/BarSeries.jsx";

/* AI 도우미 — 오늘 브리핑 / 스탠드업 초안 / 주간 다이제스트 / 미할당 트리아지.
 *
 * 계획서 Phase 5 의 순서를 화면에서도 지킨다: **숫자가 먼저, 문장은 나중.**
 * 네 탭 모두 결정적 집계 엔드포인트(/api/assistant/*)를 그대로 그리고, 문장은 사용자가
 * '문장 요약 만들기'를 누를 때만 요청한다(?narrate=true). 러너가 죽어 있거나 기능이 꺼져
 * 있으면 서버가 그 이유를 narrative.error 로 돌려주고 **숫자는 그대로 남는다** — 화면은
 * 그 사실을 있는 그대로 보여준다(동작하는 척하지 않는다).
 *
 * 트리아지에는 문장 버튼이 없다. '이 티켓은 아무개에게'라는 문장은 결정처럼 읽히는데,
 * 이 기능의 계약은 제안(auto_assign=false)이다. 순서와 근거(현재 담당 건수)만 준다.
 */

const TABS = [
  { key: "briefing", path: "briefing", label: "오늘 브리핑", narratable: true },
  { key: "standup", path: "standup", label: "스탠드업 초안", narratable: true },
  { key: "weekly", path: "weekly-digest", label: "주간 다이제스트", narratable: true },
  { key: "triage", path: "triage", label: "미할당 트리아지", narratable: false },
];

function useAssistant(tab, narrate) {
  return useQuery({
    queryKey: ["assistant", tab.path, narrate],
    queryFn: () => api(`/api/assistant/${tab.path}` + (narrate ? "?narrate=true" : "")),
    retry: false,
    staleTime: 60000,
  });
}

/* 티켓 목록 한 토막 — 제목은 상세 딥링크, 옆에 상태·마감. 표를 쓰기엔 항목이 짧다. */
function TicketLines({ label, block, empty }) {
  const items = (block && block.items) || [];
  const count = (block && block.count) || 0;
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography component="h3" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 0.75 }}>
        {label} <Box component="span" sx={{ color: "text.secondary", fontWeight: FONT_WEIGHT.medium }}>{count}건</Box>
      </Typography>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">{empty}</Typography>
      ) : (
        <Stack component="ul" gap={0.5} sx={{ listStyle: "none", m: 0, p: 0 }}>
          {items.map((t) => (
            <Box component="li" key={t.id || t.tid} sx={{ display: "flex", gap: 1, alignItems: "baseline", minWidth: 0 }}>
              <Link
                href={"#/tickets/" + t.id}
                underline="hover"
                title={t.title || "제목 없음"}
                sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {t.title || "제목 없음"}
              </Link>
              {t.status ? <Badge value={t.status} /> : null}
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>{t.due || "마감 없음"}</Typography>
            </Box>
          ))}
        </Stack>
      )}
    </Box>
  );
}

/* 모든 트랙이 minmax(0,...) 다 — "1fr" 은 트랙이 내용보다 작아지지 못하게 해서 긴 티켓
 * 제목 하나가 좁은 화면에서 격자를 밀어낸다. */
const SECTION_GRID = {
  display: "grid", gap: 2.5, alignItems: "start",
  gridTemplateColumns: { xs: "minmax(0,1fr)", md: "repeat(2, minmax(0,1fr))", xxl: "repeat(3, minmax(0,1fr))" },
};

/* 오늘 브리핑 — **목록을 다시 그리지 않는다.** 같은 화면 위쪽이 이미 오늘 마감·지연 티켓을
 * 표로 보여주고 있어서, 여기서 또 나열하면 같은 티켓이 한 화면에 두 번 나온다. 여기서는
 * 한 줄 요약(숫자)만 내고, 이 탭의 존재 이유인 '문장'을 아래 Narrative 가 채운다. */
function Briefing({ data }) {
  const t = data.tickets || {};
  const s = data.sprint;
  const n = (b) => (b && typeof b.count === "number" ? b.count : 0);
  // PA-RC-0027: 소스를 못 읽었거나 매핑이 없으면 백엔드가 버킷 자체를 안 싣는다 —
  // due_today가 그 다섯 버킷을 대표하는 존재 여부 신호다(전부 함께 실리거나 함께
  // 빠진다). 여기서 n()으로 그냥 0을 내면 "오늘 마감 0건"이 "모른다"를 "없다"로
  // 오독시킨다 — 위 스프린트 문장과 같은 원칙으로 짧게 참조만 한다.
  const ticketsUsable = t.due_today !== undefined;
  return (
    <Stack gap={1}>
      <Typography variant="body2">
        {ticketsUsable
          ? `오늘 마감 ${n(t.due_today)}건, 지연 ${n(t.overdue)}건, 진행 중 ${n(t.in_progress)}건, 막힘 ${n(t.blocked)}건`
          : "담당 티켓을 판단할 수 없어 오늘 요약을 계산할 수 없습니다."}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {s ? `이번 주 내 몫 ${s.assigned}건 중 ${s.done}건 완료${s.completion_rate == null ? "" : ` (${s.completion_rate}%)`}`
           /* VIS-34: 위 스프린트 카드(SprintProgress, Home.jsx)가 같은 원인으로 이미 전체
              문장("티켓 소스를 읽지 못해...")을 설명한다 — 여기서 그대로 반복하면 같은
              화면에 같은 경고가 두 번 뜬다. 짧게 참조만 한다. */
           : "위 스프린트 카드와 같은 이유로 이번 주 진척도 계산할 수 없습니다."}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {/* VIS-34: 이 숫자들은 이 화면 상단 카드(오늘 마감·지연·진행 중·막힘)와 같은 값이다
            — 서로 다른 집계로 오해하지 않도록 그 관계를 밝힌다(VIS-25가 관리자 대시보드에서
            쓴 것과 같은 "요약 vs 상세" 신호). PA-RC-0027: ticketsUsable이 아니면 위 줄에
            숫자 자체가 없으므로 "위 숫자는..." 문장을 빼고 두 번째 절만 남긴다. */}
        {ticketsUsable ? "위 숫자는 이 화면 상단 카드와 같은 값입니다. " : ""}
        ‘문장 요약 만들기’를 누르면 문장으로 옮겨 줍니다.
      </Typography>
    </Stack>
  );
}

function Standup({ data }) {
  return (
    <Box sx={SECTION_GRID}>
      <TicketLines label="최근 끝낸 일" block={data.recently_done} empty="이번 주 창에서 완료한 티켓이 없습니다." />
      <TicketLines label="오늘 할 일" block={data.today_plan} empty="오늘 마감이거나 지연된 티켓이 없습니다." />
      <TicketLines label="막힌 것" block={data.blocked} empty="상태가 ‘이슈’인 티켓이 없습니다." />
    </Box>
  );
}

function WeeklyDigest({ data }) {
  const mine = data.mine;
  const team = data.team;
  const docs = data.documents_changed || {};
  const board = data.board || {};
  return (
    <Stack gap={2.5}>
      <Typography variant="body2" color="text.secondary">
        {data.window ? `${data.window.start} ~ ${data.window.end_exclusive} 이전 (마감일 기준)` : null}
      </Typography>
      <Box sx={SECTION_GRID}>
        <Box>
          <Typography component="h3" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 0.75 }}>내 몫</Typography>
          {mine ? (
            <Typography variant="body2" color="text.secondary">
              담당 {mine.assigned}건, 완료 {mine.done}건, 남음 {mine.remaining}건
              {mine.overdue ? `, 지연 ${mine.overdue}건` : ""}
            </Typography>
          ) : <Typography variant="body2" color="text.secondary">계산할 수 없습니다. 관리자에게 문의하세요.</Typography>}
        </Box>
        <Box>
          <Typography component="h3" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 0.75 }}>팀 전체</Typography>
          {team ? (
            <BarSeries
              question="이번 주 팀의 일이 어디에 몰려 있는지 봅니다."
              items={[
                { label: "완료", value: team.done, color: "success" },
                { label: "진행", value: team.in_progress },
                { label: "검증", value: team.verify },
                { label: "지연", value: team.overdue, color: "error" },
              ]}
              unit="건"
              max={team.total || undefined}
              emptyLabel="이번 주 티켓 없음"
            />
          ) : <Typography variant="body2" color="text.secondary">연동이 설정되지 않았습니다. 관리자에게 문의하세요.</Typography>}
        </Box>
        <Box>
          <Typography component="h3" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 0.75 }}>바뀐 것</Typography>
          <Typography variant="body2" color="text.secondary">
            문서 {docs.count || 0}건, 새 글 {board.count || 0}건
          </Typography>
          <Stack component="ul" gap={0.25} sx={{ listStyle: "none", m: 0, mt: 0.75, p: 0 }}>
            {(docs.items || []).map((d) => (
              <Box component="li" key={d.id} sx={{ minWidth: 0 }}>
                {/* 정본 문서 id 다 (S14 · C2) — 옛 미러의 page id 가 아니라서 옛 주소로
                    보내면 그 자리에서 「찾지 못했습니다」가 뜬다. */}
                <Link href={"#/knowledge/" + d.id} underline="hover" sx={{ fontSize: FONT_SIZE.body }}>{d.title}</Link>
              </Box>
            ))}
          </Stack>
        </Box>
      </Box>
      {(team && team.total === 0) ? (
        <EmptyState art="tickets" title="이번 주에 마감인 티켓이 없습니다"
          help="스프린트 창은 이번 주 월요일부터 다음 주 월요일 전날까지입니다." />
      ) : null}
    </Stack>
  );
}

function Triage({ data }) {
  if (data.ok === false) {
    return (
      <EmptyState art="tickets" title="미할당 티켓을 불러오지 못했습니다. 관리자에게 문의하세요."
        help={data.message || data.error} />
    );
  }
  if (!data.total) {
    return (
      <EmptyState art="tickets" title="담당자 없는 티켓이 없습니다"
        help="새로 들어온 티켓 중 담당자가 비어 있으면 여기에 급한 순서로 표시됩니다." />
    );
  }
  return (
    <Stack gap={2}>
      <Alert severity="info" icon={false} sx={{ alignItems: "flex-start" }}>
        <Box component="span" sx={{ fontWeight: FONT_WEIGHT.extrabold, mr: 1.5 }}>안내</Box>
        아래는 <b>제안</b>입니다. 이 화면은 아무것도 배정하지 않습니다. 배정은
        {" "}<Link href="#/unassigned" underline="hover">미할당 티켓</Link> 화면에서 사람이 확인하고 누릅니다.
      </Alert>
      <Box sx={{ display: "grid", gap: 2.5, gridTemplateColumns: { xs: "minmax(0,1fr)", lg: "minmax(0,2fr) minmax(0,1fr)" }, alignItems: "start" }}>
        <Stack component="ol" gap={0.75} sx={{ m: 0, pl: 3 }}>
          {data.items.map((t) => (
            <Box component="li" key={t.id || t.tid} sx={{ minWidth: 0 }}>
              <Box sx={{ display: "flex", gap: 1, alignItems: "baseline", flexWrap: "wrap", minWidth: 0 }}>
                <Link href={"#/tickets/" + t.id} underline="hover">{t.title || "제목 없음"}</Link>
                {t.overdue ? <Badge value="지연" kind="danger" /> : null}
                {t.priority ? <Badge value={t.priority} kind={t.priority_rank === 0 ? "danger" : t.priority_rank === 1 ? "warn" : "neutral"} /> : null}
                <Typography variant="caption" color="text.secondary">{t.due || "마감 없음"}</Typography>
              </Box>
            </Box>
          ))}
        </Stack>
        <Box>
          <Typography component="h3" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 0.75 }}>여유 있는 담당자</Typography>
          {(data.candidates || []).length === 0 ? (
            <Typography variant="body2" color="text.secondary">배정할 수 있는 사람이 없습니다. 활성 사용자가 있는지 확인하세요.</Typography>
          ) : (
            <BarSeries
              question="지금 손이 비어 있는 사람이 누구인지 봅니다. 담당 중인 활성 티켓이 적은 순이고, 누가 무엇을 잘하는지는 판단하지 않습니다."
              items={data.candidates.map((c) => ({ label: c.display_name, value: c.active_tickets }))}
              unit="건"
              emptyLabel="후보 없음"
            />
          )}
        </Box>
      </Box>
    </Stack>
  );
}

const RENDERERS = { briefing: Briefing, standup: Standup, weekly: WeeklyDigest, triage: Triage };

/* 문장 블록 — 성공하면 문단, 실패하면 '왜 없는지'. 어느 쪽이든 위의 숫자는 그대로다. */
function Narrative({ narrative }) {
  if (!narrative) return null;
  if (narrative.text) {
    return (
      <Alert severity="success" icon={false} sx={{ mt: 2, alignItems: "flex-start" }}>
        <Box component="span" sx={{ fontWeight: FONT_WEIGHT.extrabold, mr: 1.5 }}>요약</Box>
        <Box component="span" sx={{ whiteSpace: "pre-line" }}>{narrative.text}</Box>
      </Alert>
    );
  }
  return (
    <Alert severity="info" icon={false} sx={{ mt: 2 }} role="status">
      {narrative.error || "요약 문장을 만들지 못했습니다. 다시 시도해 주세요."}
    </Alert>
  );
}

export function AssistantPanel() {
  const [index, setIndex] = React.useState(0);
  const [narrate, setNarrate] = React.useState(false);
  const tab = TABS[index];
  const q = useAssistant(tab, narrate && tab.narratable);
  const Renderer = RENDERERS[tab.key];

  // 탭을 옮기면 문장 요청은 초기화한다 — 다른 탭의 '요약 만들기'를 자동으로 이어받지 않는다.
  const select = (i) => { setIndex(i); setNarrate(false); };

  return (
    <Card>
      {/* SEM-02: 이 컴포넌트는 항상 Home.jsx(/me) 안에 박혀 있다(단독 라우트 없음) — 그
          화면의 다른 최상위 구역(내 티켓·이번 주 내 진척 등)과 같은 무게라 h2를 준다.
          그러면 이 아래 소제목(TicketLines 등, h4)이 h2→h4로 건너뛰므로 h3로 함께 낮췄다. */}
      <SectionTitle
        component="h2"
        title="AI 도우미"
        sx={{ mb: 1 }}
        action={tab.narratable ? (
          <Button size="sm" disabled={q.isFetching} onClick={() => setNarrate(true)}>
            {narrate && q.isFetching ? "요약 만드는 중…" : "문장 요약 만들기"}
          </Button>
        ) : null}
      />
      <Tabs
        value={index}
        onChange={(_e, v) => select(v)}
        variant="scrollable"
        scrollButtons="auto"
        allowScrollButtonsMobile
        aria-label="AI 도우미 보기 선택"
        sx={{ mb: 2, minHeight: 0, "& .MuiTab-root": { minHeight: 0, py: 1.25 } }}
      >
        {TABS.map((t) => <Tab key={t.key} label={t.label} />)}
      </Tabs>
      {q.isLoading ? <Skeleton kind="chart" height="6rem" />
        : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : (
          <>
            <Renderer data={q.data || {}} />
            <Narrative narrative={q.data && q.data.narrative} />
          </>
        )}
    </Card>
  );
}
