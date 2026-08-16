import React, { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Popover from "@mui/material/Popover";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import ReportProblemRoundedIcon from "@mui/icons-material/ReportProblemRounded";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { EmptyState } from "../ui/kit.jsx";
import { FONT_SIZE, FONT_WEIGHT } from "../ui/theme.js";
import { safeExternal } from "../lib/safeUrl.js";

/* PA-RC-0016: 시스템 상태 + 공지 배너 스택을 헤더 칩 하나로 접는다.
 *
 * **왜 여기 있는가.** 예전엔 Banners.jsx가 셋(임퍼소네이션·시스템 상태와 공지)을 전부 세로로
 * 쌓아 전 라우트에서 첫 화면의 20~31%를 상시 점유했다(PA-RC-0016 실측). 임퍼소네이션은
 * "지금 남의 눈으로 본다"는 사실이라 닫을 수 없고 항상 눈에 보여야 하므로 Banners.jsx에
 * 그대로 남긴다. 이 파일은 나머지 둘(시스템 상태와 공지) — 원래도 언젠가는 풀리거나 닫을 수
 * 있는 것들 — 만 다룬다.
 *
 * **판정 조건은 하나도 안 건드린다.** WARNING/CRITICAL 임계, 공지 노출 대상, 응답 구조
 * (GET /api/system/status·/api/announcements)는 예전 Banners.jsx가 쓰던 것과 완전히 같다.
 * 바뀌는 것은 "같은 정보를 화면 어디에 얼마나 크게 놓는가"뿐이다.
 */

const LEVEL_SEVERITY = { info: "info", warning: "warning", critical: "error" };
const LEVEL_LABEL = { info: "안내", warning: "주의", critical: "장애" };
// 동기화 정지류 병합 문구에 쓰는, 심각도별 서술어 — app/observability/router.py의
// LEVEL_WARNING/LEVEL_CRITICAL 판정과 같은 두 단어를 그대로 재사용한다(문구가 갈라지면
// "같은 사실을 다르게 말한다"는 새 혼란이 생긴다).
const SYNC_LEVEL_WORD = { warning: "늦어지고 있습니다", critical: "멈춰 있습니다" };

const DISMISS_STORAGE_KEY = "clovirone_dismissed_status_notices_v1";

function loadDismissed() {
  try {
    const raw = window.localStorage.getItem(DISMISS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

// 시스템 상태 알림은 서버에 닫음 상태를 저장할 자리가 없다(관측 엔드포인트는 매 폴링마다
// 현재 상태를 다시 계산해 돌려줄 뿐, 알림이라는 '행'이 DB에 없다) — 공지처럼 서버가 대상을
// 판정해 영구히 남기는 것과 다르다. 그래서 이 브라우저에서만 기억한다(localStorage). 기기를
// 바꾸면 다시 보이는 정도의 비용은, 새 서버 저장소 하나를 위해 감수하기엔 과하다고 판단했다
// (D-91 참고) — 계정 자체가 아니라 "이미 이 사고를 이 화면에서 봤다"는 사실만 기억하면 된다.
function saveDismissed(map) {
  try {
    window.localStorage.setItem(DISMISS_STORAGE_KEY, JSON.stringify(map));
  } catch {
    // 사생활 보호 모드 등으로 저장이 안 되어도 기능 자체는 그대로 동작한다 — 새로고침하면
    // 다시 보일 뿐이다.
  }
}

// 닫음 상태의 키에 **레벨을 포함한다** — 같은 id라도 심각도가 올라가면(예: warning→critical)
// 다른 키가 되어 자동으로 다시 나타난다("심각도 상승 시 재노출" 요구를 새 판정 로직 없이
// 만족시킨다).
function dismissKey(id, level) {
  return `${id}::${level}`;
}

function useSystemStatus(enabled) {
  const [interval_, setInterval_] = React.useState(120000);
  const query = useQuery({
    queryKey: ["system-status"],
    queryFn: () => api("/api/system/status"),
    refetchInterval: enabled ? interval_ : false,
    enabled,
    retry: false,
    staleTime: 30000,
  });
  React.useEffect(() => {
    const seconds = query.data && query.data.poll_seconds;
    if (seconds && seconds * 1000 !== interval_) setInterval_(seconds * 1000);
  }, [query.data, interval_]);
  return query;
}

function useAnnouncements(enabled) {
  return useQuery({
    queryKey: ["announcements-active"],
    queryFn: () => api("/api/announcements"),
    refetchInterval: enabled ? 300000 : false,
    enabled,
    retry: false,
    staleTime: 120000,
  });
}

// 같은 접두어("sync.")를 쓰는 알림을 같은 심각도끼리 하나로 합친다(예: 티켓 동기화 정지 +
// 문서 동기화 정지 → "동기화 지연/정지 2건"). **합치는 기준은 문구가 아니라 id 접두어다**
// (app/observability/router.py::_notice_for가 매기는 `sync.{component}` 식별자) — 문구
// 매칭으로 하면 서버가 나중에 단어 하나만 바꿔도 조용히 안 합쳐진다.
function mergeSyncNotices(notices) {
  const byLevel = new Map();
  const rest = [];
  for (const n of notices) {
    if (typeof n.id === "string" && n.id.startsWith("sync.")) {
      const arr = byLevel.get(n.level) || [];
      arr.push(n);
      byLevel.set(n.level, arr);
    } else {
      rest.push(n);
    }
  }
  const merged = [];
  for (const [level, group] of byLevel) {
    if (group.length === 1) {
      merged.push(group[0]);
      continue;
    }
    const since = group.reduce((oldest, n) => {
      if (!n.since) return oldest;
      return !oldest || n.since < oldest ? n.since : oldest;
    }, null);
    const word = SYNC_LEVEL_WORD[level] || "지연되고 있습니다";
    merged.push({
      id: `sync.merged.${level}`,
      level,
      message: `지금 ${group.length}개 항목의 동기화가 ${word} 최근 변경이 아직 안 보일 수 있습니다.`,
      since,
      kind: "sync",
      _mergedCount: group.length,
    });
  }
  return [...merged, ...rest];
}

function normalizeNotices(systemData, announcementData) {
  const sync = ((systemData && systemData.notices) || []).map((n) => ({ ...n, kind: "sync" }));
  const merged = mergeSyncNotices(sync);
  const announcements = ((announcementData && announcementData.items) || []).map((a) => ({
    id: `announcement.${a.id}`,
    level: a.level,
    message: a.title,
    body: a.body,
    href: safeExternal(a.link_url),
    hrefLabel: a.link_label || "자세히 보기",
    kind: "announcement",
    announcementId: a.id,
    dismissible: !!a.dismissible,
  }));
  // 위험한 것이 위 — 기존 Banners.jsx의 순서 규약(임퍼소네이션 → 시스템 상태 → 공지)과
  // 같은 정신이다. 심각도 자체로도 한 번 더 정렬해, 병합으로 순서가 흔들려도 critical이
  // 항상 먼저 보인다.
  const order = { critical: 0, warning: 1, info: 2 };
  return [...merged, ...announcements].sort((a, b) => (order[a.level] ?? 9) - (order[b.level] ?? 9));
}

async function dismissAnnouncement(qc, id) {
  await api(`/api/announcements/${encodeURIComponent(id)}/dismiss`, { method: "POST", body: {} });
  qc.invalidateQueries({ queryKey: ["announcements-active"] });
}

/** 공용 훅 — 칩과 상시 노출 CRITICAL 한 줄이 같은 목록(닫힘 반영 후)을 봐야 서로 다른
 * 개수를 말하는 모순이 안 생긴다. */
export function useStatusNotices({ enabled = true } = {}) {
  const status = useSystemStatus(enabled);
  const announcements = useAnnouncements(enabled);
  const qc = useQueryClient();
  const [dismissed, setDismissed] = useState(loadDismissed);

  const all = useMemo(
    () => normalizeNotices(status.data, announcements.data),
    [status.data, announcements.data]
  );
  const visible = useMemo(
    () => all.filter((n) => !dismissed[dismissKey(n.id, n.level)]),
    [all, dismissed]
  );
  const counts = useMemo(() => {
    const c = { critical: 0, warning: 0, info: 0 };
    for (const n of visible) c[n.level] = (c[n.level] || 0) + 1;
    return c;
  }, [visible]);

  function dismiss(notice) {
    if (notice.kind === "announcement") {
      if (!notice.dismissible) return;
      dismissAnnouncement(qc, notice.announcementId);
      return; // 서버가 다음 조회부터 목록에서 뺀다 — 로컬 dismissed에 넣지 않는다(중복 관리 방지).
    }
    setDismissed((prev) => {
      const next = { ...prev, [dismissKey(notice.id, notice.level)]: true };
      saveDismissed(next);
      return next;
    });
  }

  return {
    isLoading: status.isPending || announcements.isPending,
    isError: status.isError && announcements.isError, // 하나만 실패해도 나머지는 보여준다.
    all,
    visible,
    counts,
    dismiss,
  };
}

function NoticeRow({ notice, onDismiss }) {
  return (
    <Box
      role="listitem"
      sx={{
        display: "grid", gap: 0.5, px: 2, py: 1.25,
        borderBottom: 1, borderColor: "divider",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1 }}>
        <Typography sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold }}>
          {LEVEL_LABEL[notice.level] || "안내"}: {notice.message}
        </Typography>
        {notice.kind === "sync" || notice.dismissible ? (
          <Button size="small" onClick={() => onDismiss(notice)} sx={{ minWidth: "auto", px: 1, flexShrink: 0 }}>
            닫기
          </Button>
        ) : null}
      </Box>
      {notice.body ? (
        <Typography sx={{ fontSize: FONT_SIZE.bodySm, color: "text.secondary" }}>{notice.body}</Typography>
      ) : null}
      {notice.since ? (
        <Typography sx={{ fontSize: FONT_SIZE.caption, color: "text.secondary" }}>
          마지막 정상: {fmtDateTime(notice.since)}
        </Typography>
      ) : null}
      {notice.href ? (
        <Box>
          <Button size="small" href={notice.href} sx={{ px: 0, fontWeight: FONT_WEIGHT.bold }}>
            {notice.hrefLabel || "자세히 보기"}
          </Button>
        </Box>
      ) : null}
    </Box>
  );
}

/** 헤더 우측의 작은 상태 칩. 심각도별 개수만 보이고, 누르면 전체 목록 패널이 열린다. */
export function StatusChip({ notices }) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef(null);
  const { visible, counts, dismiss, isLoading } = notices;
  const total = counts.critical + counts.warning + counts.info;

  if (isLoading || total === 0) return null;

  const label = [
    counts.critical ? `장애 ${counts.critical}` : null,
    counts.warning ? `주의 ${counts.warning}` : null,
    counts.info ? `안내 ${counts.info}` : null,
  ].filter(Boolean).join(", ");
  const chipColor = counts.critical ? "error" : counts.warning ? "warning" : "info";

  return (
    <Box sx={{ display: "inline-flex" }}>
      <Badge
        badgeContent={total > 9 ? "9+" : total}
        color={chipColor}
        overlap="circular"
        sx={{ "& .MuiBadge-badge": { pointerEvents: "none" } }}
      >
        <Chip
          ref={anchorRef}
          icon={<ReportProblemRoundedIcon fontSize="small" />}
          label={label}
          color={chipColor}
          variant="outlined"
          size="small"
          onClick={() => setOpen((v) => !v)}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls="status-notices-pop"
          sx={{ color: "inherit", borderColor: "rgba(255,255,255,0.5)", fontWeight: FONT_WEIGHT.bold }}
        />
      </Badge>
      <Popover
        open={open}
        anchorEl={anchorRef.current}
        onClose={() => setOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{
          paper: {
            id: "status-notices-pop", role: "dialog", "aria-label": "시스템 상태와 공지",
            sx: { mt: 1, width: "min(28rem, calc(100vw - 2rem))", maxHeight: "min(30rem, 80vh)", overflow: "hidden", display: "flex", flexDirection: "column" },
          },
        }}
      >
        <Box sx={{ px: 2, py: 1.25, borderBottom: 1, borderColor: "divider", flexShrink: 0 }}>
          <Typography sx={{ fontWeight: FONT_WEIGHT.bold, fontSize: FONT_SIZE.body }}>시스템 상태와 공지</Typography>
        </Box>
        <Box role="list" sx={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
          {visible.length === 0 ? (
            <EmptyState size="compact" title="표시할 항목이 없습니다" />
          ) : (
            visible.map((n) => <NoticeRow key={n.id} notice={n} onDismiss={dismiss} />)
          )}
        </Box>
      </Popover>
    </Box>
  );
}

/** 헤더 바로 아래, 심각도 CRITICAL 항목이 있을 때만 뜨는 얇은 한 줄(≤40px). 나머지는 전부
 * 칩 안으로 접힌다 — 이 한 줄이 유일하게 "항상 눈에 보이는" 시스템 상태 표시다. */
export function CriticalStatusLine({ notices }) {
  const { visible, dismiss } = notices;
  const critical = visible.filter((n) => n.level === "critical");
  if (critical.length === 0) return null;
  // 여럿이어도 한 줄만 — 첫 항목을 대표로 보이고 개수만 덧붙인다(칩을 열면 전부 보인다).
  const first = critical[0];
  const extra = critical.length - 1;
  return (
    <Box
      role="status"
      sx={{
        display: "flex", alignItems: "center", gap: 1.5, minHeight: 40,
        px: 2, py: 0.75, bgcolor: "error.main", color: "error.contrastText",
      }}
    >
      <ReportProblemRoundedIcon fontSize="small" aria-hidden="true" />
      <Typography sx={{ fontSize: FONT_SIZE.bodySm, fontWeight: FONT_WEIGHT.bold, flex: 1 }}>
        {first.message}{extra > 0 ? ` (그 외 장애 ${extra}건, 우측 상단 칩에서 확인)` : ""}
      </Typography>
      {first.kind === "sync" ? (
        <Button size="small" color="inherit" onClick={() => dismiss(first)} sx={{ flexShrink: 0, textDecorationLine: "underline" }}>
          닫기
        </Button>
      ) : null}
    </Box>
  );
}
