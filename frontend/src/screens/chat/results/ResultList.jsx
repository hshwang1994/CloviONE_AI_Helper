import React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import ConfirmationNumberOutlinedIcon from "@mui/icons-material/ConfirmationNumberOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import HistoryRoundedIcon from "@mui/icons-material/HistoryRounded";
import NotificationsNoneRoundedIcon from "@mui/icons-material/NotificationsNoneRounded";
import { Badge, Button, Callout, Segmented, Surface } from "../../../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT, ICON, KO_WORD_BREAK, remPx } from "../../../ui/theme.js";
import { fmtDateTime, fmtListStamp } from "../../../lib/format.js";
import { api } from "../../../lib/api.js";
import { safeListRoute, safeSourceRoute } from "../../chat-helpers.js";
import { ProjectSummaryCard } from "./ProjectSummaryCard.jsx";

/* 결과 블록 — 도우미가 보여 주기로 한 목록(`structured.results[].shown`)을 서버가 준 칸 그대로 그린다(AI 채팅 개선 회차).
 *
 * 예전에는 모델이 쓴 「- [제목](route) 작성자, 수정일」 줄을 다시 읽어 그렸다 — 같은 작성자 · 날짜가 줄마다 되풀이됐고, 제목에
 * 대괄호가 든 문서는 링크가 깨졌으며, 열 건 뒤로는 이어 볼 길이 없었다. 지금은
 *   - 머리: 무엇의 목록인지 · 「361건 중 10건」 · 정렬(그 도구가 받을 때) · 「전체 목록 열기」(서버가 만든 화면 경로),
 *   - 줄: 종류마다 같은 부품(`ResultRow`) — 문서 · 티켓 · 프로젝트 · 결재 · 알림 · 활동,
 *   - 발: 「10건 더 보기」 — 모델을 부르지 않고 저장된 조건으로 다음 쪽을 받는다(`GET /api/messages/{id}/results/{rid}`).
 * 프로젝트 현황은 카드 하나다(`ProjectSummaryCard`). 전체 화면과 클로비 패널이 같은 부품이다(`compact` 면 줄을 줄인다). */

const TOOL_LABELS = {
  my_documents: "내 문서",
  search_documents: "문서 검색 결과",
  my_work: "내 티켓",
  search_tickets: "티켓",
  search_projects: "프로젝트",
  my_approvals: "승인 요청",
  my_notifications: "알림",
  my_activity: "내 최근 활동",
};

const SORT_LABELS = {
  recent: "최근 수정", created: "만든 날", title: "제목",
  due: "마감", updated: "최근 바뀜", completed: "최근 끝남",
};

const KIND_ICONS = {
  document: DescriptionOutlinedIcon,
  ticket: ConfirmationNumberOutlinedIcon,
  project: FolderOutlinedIcon,
  approval: FactCheckOutlinedIcon,
  notification: NotificationsNoneRoundedIcon,
  activity: HistoryRoundedIcon,
};

function rowRoute(item) {
  return safeSourceRoute(item && item.route) || null;
}

function Meta({ parts }) {
  const list = parts.filter((p) => p != null && p !== "" && p !== false);
  if (!list.length) return null;
  return (
    <Box component="span" sx={{ display: "flex", flexWrap: "wrap", columnGap: 1, rowGap: 0, fontSize: FONT_SIZE.caption,
                                color: "text.secondary", minWidth: 0, ...KO_WORD_BREAK }}>
      {list.map((p, i) => <Box key={i} component="span" sx={{ minWidth: 0 }}>{p}</Box>)}
    </Box>
  );
}

function Stamp({ value, prefix }) {
  if (!value) return null;
  return (
    <Box component="time" dateTime={value} title={fmtDateTime(value)} sx={{ whiteSpace: "nowrap", fontVariantNumeric: "tabular-nums" }}>
      {prefix ? `${prefix} ` : ""}{fmtListStamp(value)}
    </Box>
  );
}

/** 결과 한 줄 — 종류 아이콘 · 제목(두 줄까지, 전체는 `title`) · 종류별 짧은 사실. 제목이 앱 안 경로로 가는 링크다. */
export function ResultRow({ kind, item, hideAuthor = false }) {
  const Icon = KIND_ICONS[kind] || DescriptionOutlinedIcon;
  const route = rowRoute(item);
  const title = item.title || item.name || "(제목 없음)";
  const project = item.project && typeof item.project === "object" ? (item.project.code || item.project.name) : item.project;
  let meta = [];
  if (kind === "document") {
    meta = [item.space || item.where, project, hideAuthor ? null : (item.author || item.legacy_author), <Stamp key="u" value={item.updated_at} prefix="수정" />];
  } else if (kind === "ticket") {
    meta = [item.key, item.status ? <Badge key="s" value={item.status} /> : null,
            (item.assignees || []).length ? `담당 ${item.assignees.join(", ")}` : null,
            item.due ? `마감 ${item.due}` : null, item.completed_at ? <Stamp key="c" value={item.completed_at} prefix="끝남" /> : null,
            item.blocked ? "막힘" : null];
  } else if (kind === "project") {
    meta = [item.code, item.status, typeof item.progress_pct === "number" ? `진행률 ${Math.round(item.progress_pct)}%` : null,
            typeof item.health_score === "number" ? `건강 ${item.health_score}` : null, item.my_role];
  } else if (kind === "approval") {
    meta = [item.requester ? `요청 ${item.requester}` : null, item.status, <Stamp key="c" value={item.created_at} />,
            item.overdue ? "기한 지남" : null];
  } else if (kind === "notification") {
    meta = [item.read ? "읽음" : "안 읽음", <Stamp key="c" value={item.created_at} />];
  } else if (kind === "activity") {
    meta = [item.action, item.key, <Stamp key="a" value={item.at} />];
  }
  return (
    <Box component="li" sx={{ display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", columnGap: 1, alignItems: "start",
                              py: 0.875, minWidth: 0, "& + &": { borderTop: 1, borderColor: "rule" } }}>
      <Icon aria-hidden="true" sx={{ fontSize: remPx(ICON.mark), color: "text.secondary", mt: "0.1875rem" }} />
      <Box sx={{ minWidth: 0, display: "grid", gap: 0.25 }}>
        {route ? (
          <Box component="a" href={"#" + route} title={title}
            sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, color: "text.primary", textDecoration: "none",
                  display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden", ...KO_WORD_BREAK,
                  "&:hover": { color: "primary.main", textDecoration: "underline" } }}>
            {title}
          </Box>
        ) : (
          <Box component="span" title={title} sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.semibold, ...KO_WORD_BREAK }}>{title}</Box>
        )}
        <Meta parts={meta} />
      </Box>
    </Box>
  );
}

/** 블록의 쪽들 — 처음은 답에 실린 쪽, 「더 보기」는 다음 쪽을 덧붙이고, 정렬을 바꾸면 처음부터 다시 받는다. */
export function useResultPages(block, messageId) {
  const [state, setState] = React.useState(() => ({
    items: block.items || [], total: block.total, next: (block.offset || 0) + (block.returned || 0),
    truncated: !!block.truncated, sort: block.sort || null, loading: false, error: "",
  }));
  const load = React.useCallback(async ({ offset, sort, replace }) => {
    if (!messageId) return;
    setState((s) => ({ ...s, loading: true, error: "" }));
    const query = new URLSearchParams({ offset: String(offset) });
    if (sort) query.set("sort", sort);
    try {
      const res = await api(`/api/messages/${messageId}/results/${block.id}?${query}`);
      const page = (res && res.block) || {};
      setState((s) => ({
        items: replace ? (page.items || []) : [...s.items, ...(page.items || [])],
        total: page.total, next: (page.offset || 0) + (page.returned || 0), truncated: !!page.truncated,
        sort: page.sort || sort || s.sort, loading: false, error: "",
      }));
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: (e && e.message) || "목록을 더 받지 못했습니다. 잠시 후 다시 시도해 주세요." }));
    }
  }, [block.id, messageId]);
  return {
    ...state,
    more: () => load({ offset: state.next, sort: state.sort, replace: false }),
    resort: (sort) => load({ offset: 0, sort, replace: true }),
  };
}

/** 결과 블록 하나. 프로젝트 현황이면 카드, 아니면 목록이다. */
export function ResultBlock({ block, messageId, compact = false, hideAuthor }) {
  if (block.kind === "project_summary") {
    const card = (block.items || [])[0];
    return card ? <ProjectSummaryCard project={card} compact={compact} /> : null;
  }
  return <ResultList block={block} messageId={messageId} compact={compact} hideAuthor={hideAuthor} />;
}

function ResultList({ block, messageId, compact, hideAuthor }) {
  const pages = useResultPages(block, messageId);
  const label = TOOL_LABELS[block.tool] || "결과";
  const total = typeof pages.total === "number" ? pages.total : null;
  const shown = pages.items.length;
  /* 이어 묻기(「다음 10개」)의 블록은 처음부터가 아니다 — 머리는 몇 번째부터인지 말하고, 남은 수는 받은 끝(`next`)에서 센다. */
  const start = block.offset || 0;
  const end = Math.max(pages.next || 0, start + shown);
  const count = total == null ? `${shown}건`
    : start > 0 ? `전체 ${total}건 중 ${start + 1}~${end}번째`
    : total > shown ? `전체 ${total}건 중 ${shown}건 표시` : `전체 ${total}건`;
  const remaining = total == null ? null : Math.max(0, total - end);
  // 한 쪽의 크기는 도구마다 다르다(문서 검색 8 · 나머지 10) — 처음 받은 쪽의 크기를 쓴다.
  const pageSize = block.returned || 10;
  const listRoute = safeListRoute(block.list_route);
  const sortOptions = !compact && Array.isArray(block.sort_options)
    ? block.sort_options.filter((v) => SORT_LABELS[v]).map((v) => ({ value: v, label: SORT_LABELS[v] })) : [];
  /* 내 문서는 작성자가 언제나 묻는 사람이라 줄마다 이름을 되풀이하지 않는다(답 글의 「황형섭, 2026-09-04」 반복이 사라진 자리). */
  const omitAuthor = hideAuthor != null ? hideAuthor : block.tool === "my_documents";
  return (
    <Surface tone="inset" component="section" aria-label={`${label} ${count}`}
      data-result-block={block.id} data-result-tool={block.tool}
      sx={{ p: compact ? 1.25 : 1.5, display: "grid", gap: 0.75, minWidth: 0 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
        <Typography component="h4" sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold }}>{label}</Typography>
        <Typography component="span" sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
          {count}
        </Typography>
        <Box sx={{ flex: 1 }} />
        {sortOptions.length > 1 ? (
          <Segmented value={pages.sort || sortOptions[0].value} onChange={(v) => pages.resort(v)} options={sortOptions}
            ariaLabel={`${label} 정렬`} />
        ) : null}
        {/* 정렬 칸(34)과 같은 줄이면 단추도 같은 높이다 — 한 줄의 컨트롤은 높이와 윗선이 같다(조합 계약 control_row). */}
        {listRoute ? (
          <Button size={sortOptions.length > 1 ? undefined : "sm"} variant="ghost" href={"#" + listRoute}>전체 목록 열기</Button>
        ) : null}
      </Box>
      {shown ? (
        <Box component="ul" role="list" sx={{ listStyle: "none", m: 0, p: 0, minWidth: 0, opacity: pages.loading && pages.items === block.items ? 0.6 : 1 }}>
          {pages.items.map((item, i) => (
            <ResultRow key={`${item.ref || item.title || ""}:${i}`} kind={block.kind} item={item} hideAuthor={omitAuthor} />
          ))}
        </Box>
      ) : (
        <Typography sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>검색 조건에 맞는 항목이 없습니다.</Typography>
      )}
      {pages.error ? <Callout tone="danger" compact>{pages.error}</Callout> : null}
      {(pages.truncated || (remaining && remaining > 0)) && messageId ? (
        <Box sx={{ display: "flex", justifyContent: "center" }}>
          <Button size="sm" variant="ghost" loading={pages.loading} onClick={pages.more}>
            {remaining ? `${Math.min(pageSize, remaining)}건 더 보기` : "더 보기"}
          </Button>
        </Box>
      ) : null}
    </Surface>
  );
}
