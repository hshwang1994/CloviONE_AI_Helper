import React from "react";
import { useQuery } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { keyframes } from "@mui/system";
import { api } from "../lib/api.js";
import { Badge, Button, Card, EmptyState, ErrorState, ScrollArea, SectionTitle, Skeleton, SubGroup, useToast } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, KO_WORD_BREAK, MOTION } from "../ui/theme.js";
import { useAutoHeight } from "../ui/motion.js";
import { BarSeries } from "../ui/charts/BarSeries.jsx";
import { copyText } from "./ops/opsHelpers.js";
import { priorityKind, priorityKo } from "../lib/priority.js";
import { fmtDayKo } from "../lib/format.js";
import { lastDayOf } from "./WorkSummary.jsx";

/* AI 도우미 — 오늘 요약 / 업무 공유 초안 / 이번 주 요약 / 담당자 지정 필요.
 *
 * ## 이 패널이 하는 일은 «숫자를 다시 읽어 주는 것»이 아니다
 *
 * 예전 브리핑 탭은 첫 줄이 「오늘 마감 2건, 지연 12건, 진행 중 14건, 막힘 0건」이었고 그
 * 아래에 「위 숫자는 이 화면 상단 카드와 같은 값입니다」라고 적혀 있었다. 스스로 중복임을
 * 밝히는 영역이 화면 폭 전체를 쓰고 있었던 셈이다. 같은 숫자는 위 판독 줄이 이미 말한다.
 *
 * ## 탭 이름은 «영어 업무 낱말» 이 아니라 하는 일이다
 *
 * 「스탠드업 초안」·「미할당 트리아지」·「주간 업데이트」는 그 낱말을 아는 사람에게만 뜻이
 * 통한다. 트리아지는 응급실 낱말이고, 스탠드업은 특정 회의 관행의 이름이다. 화면은 **그
 * 탭이 무엇을 주는지**를 말한다: 업무 공유 초안 · 담당자 지정 필요 · 이번 주 요약.
 *
 * 그래서 각 탭은 **해석**을 낸다: 지금 무엇이 가장 급한가, 그 이유는 무엇인가, 다음에 무엇을
 * 누르면 되는가. 값은 전부 서버가 준 사실에서 규칙으로 뽑는다(아래 순수 함수들) — 없는
 * 사실을 지어내지 않고, 러너가 죽어 있어도 이 층은 그대로 돈다.
 *
 * ## 네 탭이 공유하는 흐름
 *
 *     요약(한 문장) → 주요 정보 → 세부 정보와 시각화 → 필요한 Action
 *
 * 그릇도 공유한다. 판(Card)은 이 패널 하나뿐이고, 안쪽 묶음은 실선과 여백과 소제목이
 * 가른다 — 판 안에 판을 또 넣지 않는다(`ui/kit.jsx::Surface` 가 깊이 1 이상의 판을
 * 자동으로 눕히지만, 애초에 넣지 않는 것이 이 화면의 계약이다).
 *
 * 의미가 있는 자리에만 상태색을 쓴다: 지연과 막힘은 실제 위험 신호라 색을 갖고, 나머지
 * 정보는 굵기와 잉크 단계로만 위계를 만든다.
 *
 * ## 트리아지는 제안만 한다
 *
 * 서버 계약이 `auto_assign: false` 다(app/assistant/facts.py). 그래서 이 탭에는 배정을
 * 실행하는 컨트롤이 없고, 문장 버튼도 없다 — 「이 티켓은 아무개에게」라는 문장은 결정처럼
 * 읽힌다. 순서와 근거만 준다.
 */

/* `path` 는 서버 계약(`/api/assistant/<path>`)이라 그대로 두고, `label` 만 사람의 말로 바꾼다. */
const TABS = [
  { key: "briefing", path: "briefing", label: "오늘 요약", narratable: true },
  { key: "standup", path: "standup", label: "업무 공유 초안", narratable: true },
  { key: "weekly", path: "weekly-digest", label: "이번 주 요약", narratable: true },
  { key: "triage", path: "triage", label: "담당자 지정 필요", narratable: false },
];

/** 이 탭에서 갈 만한 곳. **의미 없는 버튼을 두지 않는다** — 갈 이유가 실제로 있을 때만 낸다.
 *
 * 브리핑은 비어 있다. 바로 위 카드가 이미 「내 티켓 전체」로 나가고 있어서, 같은 목적지를
 * 한 화면에서 두 번 주는 것은 선택지가 아니라 소음이다. */
export function tabLinks(tabKey, data) {
  const d = data || {};
  if (tabKey === "weekly") return [{ href: "#/sprint", label: "스프린트 회의 열기" }];
  if (tabKey === "triage") return d.total ? [{ href: "#/unassigned", label: "미할당 티켓 열기" }] : [];
  return [];
}

function useAssistant(tab, narrate) {
  return useQuery({
    queryKey: ["assistant", tab.path, narrate],
    queryFn: () => api(`/api/assistant/${tab.path}` + (narrate ? "?narrate=true" : "")),
    retry: false,
    staleTime: 60000,
  });
}

/* ── 사실에서 해석을 뽑는 순수 함수들 ─────────────────────────────────────────
 * 렌더 밖에 두는 이유는 시험이 값 자체를 대조할 수 있게 하기 위해서다. */

/** 두 KST 달력일 사이의 날짜 수. 문자열을 UTC 로 읽어 시간대 영향을 없앤다. */
export function daysBetween(fromIso, toIso) {
  if (!fromIso || !toIso) return null;
  const a = Date.parse(String(fromIso) + "T00:00:00Z");
  const b = Date.parse(String(toIso) + "T00:00:00Z");
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.round((b - a) / 86400000);
}

const bucketCount = (tickets, key) => {
  const b = tickets && tickets[key];
  return b && typeof b.count === "number" ? b.count : 0;
};
const bucketItems = (tickets, key) => {
  const b = tickets && tickets[key];
  return b && Array.isArray(b.items) ? b.items : [];
};

/** 오늘 무엇이 가장 급한가. 순서가 곧 판단이다: 지연 → 막힘 → 오늘 마감 → 곧 마감 → 진행 중.
 *
 * `due_today` 키가 아예 없으면 티켓을 못 읽은 것이다(app/home/service.py 는 그 다섯 버킷을
 * 함께 싣거나 함께 뺀다). 그때 0 을 그리면 「모른다」가 「없다」로 바뀐다. */
export function briefingFocus(tickets) {
  const t = tickets || {};
  if (t.due_today === undefined) {
    return { key: "unknown", text: "담당 티켓을 읽지 못해 오늘 요약을 만들 수 없습니다." };
  }
  const n = (k) => bucketCount(t, k);
  if (n("overdue")) return { key: "overdue", text: `마감이 지난 티켓 ${n("overdue")}건이 오늘 가장 급합니다.` };
  if (n("blocked")) return { key: "blocked", text: `막힌 티켓 ${n("blocked")}건이 진행을 멈추고 있습니다.` };
  if (n("due_today")) return { key: "due_today", text: `오늘 마감인 일이 ${n("due_today")}건 있습니다.` };
  if (n("due_soon")) return { key: "due_soon", text: `오늘 마감은 없고 앞으로 7일 안에 ${n("due_soon")}건이 마감입니다.` };
  if (n("in_progress")) return { key: "in_progress", text: `급한 일은 없습니다. 진행 중인 ${n("in_progress")}건을 이어서 하면 됩니다.` };
  return { key: "none", text: "지금 맡고 있는 티켓이 없습니다." };
}

/** 지금 눈으로 확인할 값어치가 있는 티켓 셋. 버킷을 가로질러 급한 순으로 모은다.
 *
 * 위 목록 카드는 사용자가 고른 **한 칸**만 보여 준다. 여기는 그 칸과 무관하게 「지연이든
 * 막힘이든 오늘 마감이든 지금 급한 것」을 섞어서 앞의 셋만 낸다 — 같은 티켓을 두 번 넣지
 * 않는다. */
export function attentionRows(tickets, today) {
  const t = tickets || {};
  const rows = [];
  const seen = new Set();
  const push = (item, reason, kind) => {
    if (!item || rows.length >= 3) return;
    const id = item.id || item.tid;
    if (seen.has(id)) return;
    seen.add(id);
    rows.push({ item, reason, kind });
  };
  bucketItems(t, "overdue").forEach((item) => {
    const late = daysBetween(item.due, today);
    push(item, late && late > 0 ? `지연 ${late}일` : "지연", "danger");
  });
  bucketItems(t, "blocked").forEach((item) => push(item, "막힘", "warn"));
  bucketItems(t, "due_today").forEach((item) => push(item, "오늘 마감", "warn"));
  return rows;
}

/** 스탠드업에서 그대로 읽거나 붙여 넣을 수 있는 초안. 복사 버튼이 이 문자열을 낸다. */
export function standupDraft(data) {
  const d = data || {};
  const section = (label, block) => {
    const items = (block && block.items) || [];
    if (!items.length) return `${label}: 없음`;
    const lines = items.map((t) => `- ${t.title || "제목 없음"}${t.due ? ` (마감 ${t.due})` : ""}`);
    return [`${label}:`, ...lines].join("\n");
  };
  const head = `${d.today || ""} 업무 공유`.trim();
  return [
    head,
    section("최근 끝낸 일", d.recently_done),
    section("오늘 할 일", d.today_plan),
    section("막힌 일", d.blocked),
  ].join("\n\n");
}

/* ── 공용 그릇 ──────────────────────────────────────────────────────────────
 * 네 탭이 같은 모양으로 읽히게 하는 최소 부품 셋. */

/** 탭의 첫 줄. 이 한 문장이 그 탭의 결론이다. */
function Lede({ children }) {
  return (
    <Typography
      sx={{ fontSize: FONT_SIZE.title, fontWeight: FONT_WEIGHT.semibold, lineHeight: 1.35, ...KO_WORD_BREAK }}
    >
      {children}
    </Typography>
  );
}

/** 탭 마지막 줄의 행동. 할 것이 없으면 아무것도 그리지 않는다. */
function Actions({ children }) {
  const list = React.Children.toArray(children).filter(Boolean);
  if (!list.length) return null;
  return (
    <Box sx={{ mt: 2.5, pt: 2, borderTop: 1, borderColor: "divider", display: "flex", gap: 1.5, flexWrap: "wrap", alignItems: "center" }}>
      {list}
    </Box>
  );
}

/* 티켓 한 줄 — 제목은 딥링크, 오른쪽은 상태와 마감. 표를 쓰기엔 항목이 짧다. */
function TicketRow({ ticket, lead, leadKind }) {
  return (
    <Box component="li" sx={{ display: "flex", gap: 1, alignItems: "baseline", minWidth: 0, py: 0.25 }}>
      {lead ? <Badge value={lead} kind={leadKind} /> : null}
      <Link
        href={"#/tickets/" + ticket.id}
        underline="hover"
        title={ticket.title || "제목 없음"}
        sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
      >
        {ticket.title || "제목 없음"}
      </Link>
      {ticket.status ? <Badge value={ticket.status} /> : null}
      <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap", flexShrink: 0 }}>
        {ticket.due || "마감 없음"}
      </Typography>
    </Box>
  );
}

function TicketList({ children, ariaLabel, scrollAfter, maxHeight = "18rem" }) {
  const rows = React.Children.toArray(children).filter(Boolean);
  const list = (
    <Stack component="ul" gap={0.25} sx={{ listStyle: "none", m: 0, p: 0, minWidth: 0 }}>
      {rows}
    </Stack>
  );
  /* 스크롤 칸은 **실제로 길어질 수 있는 목록에만** 준다. 서버가 다섯 건까지만 주는 목록에
     상자를 씌우면 굴릴 것이 없는 스크롤 칸이 하나 더 생길 뿐이다. */
  if (!scrollAfter || rows.length <= scrollAfter) return list;
  return <ScrollArea maxHeight={maxHeight} ariaLabel={ariaLabel}>{list}</ScrollArea>;
}

/* 잘라서 보여 주는 목록은 **잘랐다고 말한다.**
 *
 * 서버가 다섯 건까지만 싣는다(app/assistant/facts.py 의 `DIGEST_LIMIT`). 개수만 크게
 * 적어 두고 다섯 줄만 그리면 읽는 사람은 나머지가 어디 갔는지 모른다 — 「없다」로 읽거나
 * 「목록이 고장 났다」로 읽는다. 안쪽 스크롤을 만들지 않는 대신 한 줄로 사실을 적는다. */
function MoreNote({ count, shown }) {
  if (!(count > shown)) return null;
  return (
    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
      {shown}건만 표시했습니다.
    </Typography>
  );
}

/* 티켓 목록 한 토막(스탠드업 세 단). 소제목은 h3 — 패널 제목이 h2 라 그 아래는 h3 다. */
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
        <>
          <TicketList ariaLabel={label}>
            {items.map((t) => <TicketRow key={t.id || t.tid} ticket={t} />)}
          </TicketList>
          <MoreNote count={count} shown={items.length} />
        </>
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

/* ── 탭 넷 ──────────────────────────────────────────────────────────────── */

/** 오늘 브리핑 — 결론 한 줄, 지금 볼 티켓 셋, 그리고 문장 요약. */
function Briefing({ data }) {
  const tickets = data.tickets || {};
  const focus = briefingFocus(tickets);
  const rows = attentionRows(tickets, data.today);
  const sprint = data.sprint;
  return (
    <>
      <Lede>{focus.text}</Lede>
      {sprint ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, ...KO_WORD_BREAK }}>
          이번 주 맡은 {sprint.assigned}건 가운데 {sprint.done}건을 끝냈고 {sprint.remaining ?? Math.max(0, sprint.assigned - sprint.done)}건이 남았습니다.
        </Typography>
      ) : (
        /* 스프린트 카드가 같은 화면에서 이미 원인을 문장으로 설명한다. 여기서 그 문장을
           다시 쓰면 같은 화면에 같은 경고가 두 번 뜬다. 짧게 참조만 한다. */
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
          「이번 주」 카드와 같은 이유로 이번 주 진척도 계산할 수 없습니다.
        </Typography>
      )}

      <SubGroup title="지금 볼 것">
        {rows.length ? (
          <TicketList ariaLabel="지금 볼 티켓">
            {rows.map((r) => (
              <TicketRow key={r.item.id || r.item.tid} ticket={r.item} lead={r.reason} leadKind={r.kind} />
            ))}
          </TicketList>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {focus.key === "unknown"
              ? "티켓을 다시 읽을 수 있게 되면 여기에 급한 순서로 표시됩니다."
              : "지금 따로 챙길 티켓이 없습니다."}
          </Typography>
        )}
      </SubGroup>
    </>
  );
}

/** 스탠드업 초안 — 세 단으로 나눈 목록과, 그대로 복사할 수 있는 초안. */
function Standup({ data }) {
  const count = (block) => (block && typeof block.count === "number" ? block.count : 0);
  const done = count(data.recently_done);
  const plan = count(data.today_plan);
  const stuck = count(data.blocked);
  return (
    <>
      <Lede>
        {plan || stuck || done
          ? `끝낸 일 ${done}건과 오늘 할 일 ${plan}건, 막힌 일 ${stuck}건을 공유합니다.`
          : "이번 주에 공유할 일이 아직 없습니다."}
      </Lede>
      <SubGroup title="공유할 내용">
        <Box sx={SECTION_GRID}>
          <TicketLines label="최근 끝낸 일" block={data.recently_done} empty="이번 주에 완료한 티켓이 없습니다." />
          <TicketLines label="오늘 할 일" block={data.today_plan} empty="오늘 마감이거나 지연된 티켓이 없습니다." />
          <TicketLines label="막힌 일" block={data.blocked} empty="상태가 이슈인 티켓이 없습니다." />
        </Box>
      </SubGroup>
    </>
  );
}

/** 주간 업데이트 — 내 몫과 팀의 이번 주, 그 주에 바뀐 것. */
function WeeklyDigest({ data }) {
  const mine = data.mine;
  const team = data.team;
  const docs = data.documents_changed || {};
  const board = data.board || {};
  const contributors = Array.isArray(data.top_contributors) ? data.top_contributors : [];
  const win = data.window || {};
  const teamKey = team ? `weekly-team:${team.done}:${team.in_progress}:${team.verify}:${team.overdue}:${team.total}` : null;
  return (
    <>
      <Lede>
        {mine
          ? `이번 주 맡은 ${mine.assigned}건 가운데 ${mine.done}건을 끝냈습니다.`
          : "이번 주 내 몫을 계산할 수 없습니다. 관리자에게 문의하세요."}
      </Lede>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, ...KO_WORD_BREAK }}>
        {/* 끝은 **포함되는 마지막 날**로 적는다. 계약값(end_exclusive)을 그대로 보이면 그
            날이 포함인지 매번 다시 생각해야 하고 반쯤은 틀리게 읽는다(오른쪽 레일과 같은
            규칙 — `WorkSummary.jsx::lastDayOf` 하나를 쓴다). */}
        {win.start ? `${fmtDayKo(win.start)}부터 ${fmtDayKo(lastDayOf(win.end_exclusive))}까지 마감인 일을 셉니다.` : null}
        {mine && mine.overdue ? ` 지연 ${mine.overdue}건이 남아 있습니다.` : null}
      </Typography>

      <SubGroup title="팀은 이번 주에 무엇을 했나">
        {team ? (
          <Box sx={{ display: "grid", gap: 2.5, alignItems: "start", gridTemplateColumns: { xs: "minmax(0,1fr)", lg: "minmax(0,1.4fr) minmax(0,1fr)" } }}>
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
              revealKey={teamKey}
            />
            <Box sx={{ minWidth: 0 }}>
              <Typography component="h4" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 0.75 }}>
                많이 끝낸 사람
              </Typography>
              {contributors.length ? (
                <Stack component="ul" gap={0.5} sx={{ listStyle: "none", m: 0, p: 0, minWidth: 0 }}>
                  {contributors.map((c) => (
                    <Box component="li" key={c.user_id || c.name} sx={{ display: "flex", gap: 1, alignItems: "baseline", minWidth: 0 }}>
                      <Typography variant="body2" sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {c.name}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
                        {c.done} / {c.assigned}건
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">이번 주에 완료한 사람이 아직 없습니다.</Typography>
              )}
            </Box>
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary">
            팀 합계를 읽을 수 없습니다. 관리자에게 문의하세요.
          </Typography>
        )}
      </SubGroup>

      <SubGroup title={`이번 주에 바뀐 것 (문서 ${docs.count || 0}건, 새 글 ${board.count || 0}건)`}>
        {(docs.items || []).length || (board.items || []).length ? (
          <Box sx={SECTION_GRID}>
            <Box sx={{ minWidth: 0 }}>
              <Typography component="h4" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 0.75 }}>문서</Typography>
              {(docs.items || []).length ? (
                <Stack component="ul" gap={0.25} sx={{ listStyle: "none", m: 0, p: 0, minWidth: 0 }}>
                  {(docs.items || []).map((d) => (
                    <Box component="li" key={d.id} sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {/* 정본 문서 id 다 (S14 · C2). 옛 미러의 page id 로 보내면 그 자리에서
                          「찾지 못했습니다」가 뜬다. */}
                      <Link href={"#/knowledge/" + d.id} underline="hover" title={d.title}>{d.title}</Link>
                    </Box>
                  ))}
                  <MoreNote count={docs.count || 0} shown={(docs.items || []).length} />
                </Stack>
              ) : <Typography variant="body2" color="text.secondary">바뀐 문서가 없습니다.</Typography>}
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography component="h4" variant="body2" sx={{ fontWeight: FONT_WEIGHT.bold, mb: 0.75 }}>게시글</Typography>
              {(board.items || []).length ? (
                <Stack component="ul" gap={0.25} sx={{ listStyle: "none", m: 0, p: 0, minWidth: 0 }}>
                  {(board.items || []).map((p) => (
                    <Box component="li" key={p.id} sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      <Link href={"#/board/" + p.id} underline="hover" title={p.title}>{p.title}</Link>
                    </Box>
                  ))}
                  <MoreNote count={board.count || 0} shown={(board.items || []).length} />
                </Stack>
              ) : <Typography variant="body2" color="text.secondary">새로 올라온 글이 없습니다.</Typography>}
            </Box>
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary">이번 주에 바뀐 문서와 새 글이 없습니다.</Typography>
        )}
      </SubGroup>
    </>
  );
}

/** 어휘 표에 없는 등급의 색 — 서버가 매긴 순위로만 정한다(`app/home/aggregate.py::priority_rank`). */
const rankKind = (rank) => (rank === 0 ? "danger" : rank === 1 ? "warn" : "neutral");

/** 담당자 지정 필요 — 순서와 근거만 준다. 배정은 사람이 다른 화면에서 누른다. */
function Triage({ data }) {
  if (data.ok === false) {
    return (
      <EmptyState art="tickets" title="미할당 티켓을 불러오지 못했습니다"
        help={data.message || data.error || "잠시 뒤에 다시 시도하거나 관리자에게 문의하세요."} />
    );
  }
  if (!data.total) {
    return (
      <EmptyState art="tickets" title="담당자를 지정할 티켓이 없습니다"
        help="새로 들어온 티켓에 담당자가 비어 있으면 여기에 급한 순서로 표시됩니다." />
    );
  }
  const items = Array.isArray(data.items) ? data.items : [];
  const late = items.filter((t) => t.overdue).length;
  const candidates = Array.isArray(data.candidates) ? data.candidates : [];
  const candidateKey = candidates.length
    ? "triage-load:" + candidates.map((c) => `${c.user_id}:${c.active_tickets}`).join(",")
    : null;
  return (
    <>
      <Lede>
        담당자 없는 티켓이 {data.total}건 있습니다{late ? `. 그중 ${late}건은 이미 지연입니다` : ""}.
      </Lede>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75, ...KO_WORD_BREAK }}>
        아래는 제안이고 이 화면은 아무것도 배정하지 않습니다. 배정은 미할당 티켓 화면에서 직접 확인하고 누릅니다.
      </Typography>

      <SubGroup title={data.total > items.length ? `급한 순서 (앞의 ${items.length}건)` : "급한 순서"}>
        <TicketList ariaLabel="미할당 티켓 순서" scrollAfter={6} maxHeight="17rem">
          {items.map((t) => (
            <TicketRow
              key={t.id || t.tid}
              ticket={t}
              /* 🔴 우선순위를 **원문 그대로** 찍고 있었다 — 실측에서 이 자리에 「Low」가 떴다.
                 같은 값이 티켓 표에서는 「낮음」이다. 한 제품이 한 낱말을 두 가지로 말하지
                 않는다: 어휘는 `lib/priority.js` 한 곳에서 온다. 그 표에 없는 등급이면
                 서버가 매긴 순위로 색만 정한다. */
              lead={t.overdue ? "지연" : (t.priority ? priorityKo(t.priority) : null)}
              leadKind={t.overdue ? "danger" : (priorityKind(t.priority) || rankKind(t.priority_rank))}
            />
          ))}
        </TicketList>
      </SubGroup>

      <SubGroup title="지금 손이 비어 있는 사람">
        {candidates.length ? (
          <BarSeries
            question="맡고 있는 티켓이 적은 순입니다. 누가 무엇을 잘하는지는 판단하지 않습니다."
            items={candidates.map((c) => ({ label: c.display_name, value: c.active_tickets }))}
            unit="건"
            emptyLabel="후보 없음"
            revealKey={candidateKey}
          />
        ) : (
          <Typography variant="body2" color="text.secondary">
            배정할 수 있는 사람이 없습니다. 활성 사용자가 있는지 확인하세요.
          </Typography>
        )}
      </SubGroup>
    </>
  );
}

const RENDERERS = { briefing: Briefing, standup: Standup, weekly: WeeklyDigest, triage: Triage };

/* 문장 블록 — 성공하면 문단, 실패하면 왜 없는지. 어느 쪽이든 위의 숫자는 그대로다.
 *
 * 예전에는 성공이 초록 Alert 였다. 문장이 생겼다는 것은 「성공」이라는 상태가 아니라 그냥
 * 결과물이라, 의미 없는 상태색이었다. 옅은 함몰면과 소제목으로 구분한다. */
function Narrative({ narrative }) {
  if (!narrative) return null;
  if (narrative.text) {
    return (
      <SubGroup title="문장 요약">
        <Box sx={{ bgcolor: "background.inset", borderRadius: 1, p: 2, minWidth: 0 }}>
          <Typography variant="body2" sx={{ whiteSpace: "pre-line", ...KO_WORD_BREAK }}>{narrative.text}</Typography>
        </Box>
      </SubGroup>
    );
  }
  return (
    <SubGroup title="문장 요약">
      <Typography variant="body2" color="text.secondary" role="status" sx={{ ...KO_WORD_BREAK }}>
        {narrative.error || "요약 문장을 만들지 못했습니다. 다시 시도해 주세요."}
      </Typography>
    </SubGroup>
  );
}

/* 탭 내용이 바뀔 때의 짧은 등장. 6px 만 올라오고 끝나며, 동작 최소화를 켜면 전역 규칙이
   길이를 0 으로 만든다(theme.js 의 prefers-reduced-motion 블록). */
const enterPanel = keyframes`
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
`;

export function AssistantPanel() {
  const [index, setIndex] = React.useState(0);
  const [narrate, setNarrate] = React.useState(false);
  const toast = useToast();
  const tab = TABS[index];
  const q = useAssistant(tab, narrate && tab.narratable);
  const Renderer = RENDERERS[tab.key];
  const auto = useAutoHeight();

  // 탭을 옮기면 문장 요청은 초기화한다 — 다른 탭의 요약 요청을 자동으로 이어받지 않는다.
  const select = (i) => { setIndex(i); setNarrate(false); };

  const copy = (text) => {
    copyText(text).then((ok) => toast(ok ? "클립보드에 복사했습니다." : "복사를 지원하지 않는 환경입니다.", ok ? "success" : "info"));
  };

  const narrative = q.data && q.data.narrative;
  const body = q.isLoading ? <Skeleton kind="chart" height="8rem" />
    : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
      : (
        <>
          <Renderer data={q.data || {}} />
          <Narrative narrative={narrative} />
          {/* 행동은 탭마다 다르지만 **자리는 하나**다. 목적지 링크와 복사와 문장 요청이
              각자 자기 줄을 만들면 탭 아래가 버튼 세 줄이 된다. */}
          <Actions>
            {tabLinks(tab.key, q.data).map((a) => (
              <Button key={a.href} size="sm" href={a.href}>{a.label}</Button>
            ))}
            {tab.key === "standup" ? (
              <Button size="sm" onClick={() => copy(standupDraft(q.data || {}))}>초안 복사</Button>
            ) : null}
            {narrative && narrative.text ? (
              <Button size="sm" variant="ghost" onClick={() => copy(narrative.text)}>문장 복사</Button>
            ) : null}
            {tab.narratable ? (
              <Button size="sm" disabled={q.isFetching} onClick={() => setNarrate(true)}>
                {narrate && q.isFetching ? "요약 만드는 중…" : "문장 요약 만들기"}
              </Button>
            ) : null}
          </Actions>
        </>
      );

  return (
    <Card>
      {/* SEM-02: 이 컴포넌트는 항상 Home.jsx(/me) 안에 박혀 있다(단독 라우트 없음). 그
          화면의 다른 최상위 구역과 같은 무게라 h2 이고, 그 아래 소제목은 h3 다. */}
      <SectionTitle
        component="h2"
        title="AI 도우미"
        help="지금 급한 일과 다음에 할 일을 정리합니다."
        sx={{ mb: 1 }}
      />
      <Tabs
        value={index}
        onChange={(_e, v) => select(v)}
        variant="scrollable"
        scrollButtons="auto"
        allowScrollButtonsMobile
        aria-label="AI 도우미 보기 선택"
        sx={{
          mb: 2, minHeight: 0,
          "& .MuiTab-root": { minHeight: 0, py: 1.25 },
          /* 밑줄이 다음 탭으로 미끄러진다. MUI 기본 전환을 이 제품의 길이와 곡선으로 맞춘다. */
          "& .MuiTabs-indicator": { transition: `left ${MOTION.base} ${MOTION.ease}, width ${MOTION.base} ${MOTION.ease}` },
        }}
      >
        {TABS.map((t) => <Tab key={t.key} label={t.label} />)}
      </Tabs>
      {/* 바깥 상자가 높이를 잇고, 안쪽 상자가 실제 높이를 잰다. 탭이 바뀌면 key 가 바뀌어
          내용이 짧게 올라오며 나타난다. */}
      <Box sx={auto.sx}>
        <Box ref={auto.ref}>
          <Box key={tab.key} sx={{ animation: `${enterPanel} ${MOTION.base} ${MOTION.ease} both` }}>
            {body}
          </Box>
        </Box>
      </Box>
    </Card>
  );
}
