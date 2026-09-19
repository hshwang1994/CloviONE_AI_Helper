import React, { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Box from "@mui/material/Box";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import ReportProblemRoundedIcon from "@mui/icons-material/ReportProblemRounded";
import { api } from "../lib/api.js";
import { fmtDateTime } from "../lib/format.js";
import { Button as KitButton, Callout, CountChip, EmptyState } from "../ui/kit.jsx";
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
// 동기화 정지류 병합 문구에 쓰는, 심각도별 서술어 — app/observability/router.py의
// LEVEL_WARNING/LEVEL_CRITICAL 판정과 같은 두 단어를 그대로 재사용한다(문구가 갈라지면
// "같은 사실을 다르게 말한다"는 새 혼란이 생긴다).
const SYNC_LEVEL_WORD = { warning: "늦어지고 있습니다", critical: "멈춰 있습니다" };

/* 사용자 알림함에 넣을 자격이 있는 것만 고른다 (지시 1·67).
 *
 * 지시 1: "정상적인 동기화 시작·완료·주기 등의 내부 처리 정보는 일반 사용자에게 노출하지
 * 않는다. 동기화 실패로 실제 기능에 영향이 있거나 사용자의 조치가 필요한 경우에만 알림
 * 대상으로 처리한다."
 *
 * 그래서 두 갈래를 다르게 다룬다:
 *   · `kind === "sync"` — 내부 처리 정보다. **주의·장애일 때만** 보낸다. 정상 동기화는
 *     사용자가 알 필요가 없다.
 *   · 공지(announcement) — 사람이 사용자에게 하려고 쓴 말이다. 심각도와 무관하게 보낸다.
 *
 * 지시 67: 이것은 **사용자 알림함**의 규칙일 뿐이다. 관리자·운영자용 시스템 상태
 * (`/api/system/status` 의 `components[]`, 서비스 Health, 조치 필요 항목)는 여기서 거르지
 * 않는다 — 그쪽은 관리 화면이 계속 보여 준다(관리자 대시보드·진단).
 */
export function userFacingNotices(notices) {
  const all = (notices && notices.visible) || [];
  return all.filter((n) => (n.kind === "sync" ? n.level !== "info" : true));
}

const DISMISS_STORAGE_KEY = "clovirassist_dismissed_status_notices_v1";

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

/* 알림함의 심각도 셋을 메시지 박스의 톤으로 옮긴다. 예전에는 제목 앞에 「안내·주의·장애」 낱말을
   붙였는데, 핸드오프 D-11 이 메시지 박스의 톤 이름 줄을 걷었다 — 심각도는 아이콘의 모양과 그 접근
   이름이 말하고, 제목은 서버가 준 문장 그대로다. */
const NOTICE_TONE = { info: "info", warning: "warn", critical: "danger" };

export function NoticeRow({ notice, onDismiss }) {
  const dismissible = notice.kind === "sync" || notice.dismissible;
  return (
    /* 공용 메시지 박스로 그린다 — 이 줄은 오래 자기 마크업이었고, 그래서 같은 목적의
       상자가 화면마다 다른 무게로 나타나던 자리의 하나였다. 목록 안이라 `listitem` 을
       그대로 두고(그래야 목록이 안 깨진다) 모서리와 좌우 선을 없애 줄들이 한 기둥으로
       이어지게 한다. 닫기는 상자의 오른쪽 동작 칸에 선다 — 심각도와 별개로 이 알림이
       닫을 수 있는 것인지는 서버가 정한다. */
    /* 제목 앞의 톤 낱말(「안내:」 「주의:」 「장애:」)을 걷었다(핸드오프 D-11 — 톤 이름 줄 금지).
       상태는 아이콘의 모양과 그 접근 이름이 말한다. 줄들이 한 기둥으로 이어지는 띠라 `bleed` 갈래다. */
    /* 상자의 동작(닫기 · 자세히 보기)은 30 보조다 — 글자 단추는 목록 안 부수 동작의 자리다(핸드오프 RULES §3 · 조합 계약 C-4). */
    <Callout
      role="listitem"
      tone={NOTICE_TONE[notice.level] || "info"}
      variant="bleed"
      title={notice.message}
      action={dismissible ? (
        <KitButton size="sm" onClick={() => onDismiss(notice)}>닫기</KitButton>
      ) : null}
    >
      <Box sx={{ display: "grid", gap: 0.5 }}>
        {notice.body ? <Box component="span">{notice.body}</Box> : null}
        {notice.since ? (
          <Box component="span" sx={{ fontSize: FONT_SIZE.caption }}>
            마지막 정상: {fmtDateTime(notice.since)}
          </Box>
        ) : null}
        {notice.href ? (
          <Box>
            <KitButton size="sm" href={notice.href}>
              {notice.hrefLabel || "자세히 보기"}
            </KitButton>
          </Box>
        ) : null}
      </Box>
    </Callout>
  );
}

/** 헤더 우측의 작은 상태 단추. 심각도별 개수만 보이고, 누르면 전체 목록 패널이 열린다.
 *
 * 이름이 `StatusChip` 이었다 — 목록을 상태로 좁히는 상태 칩(`ui/StatusKpi.jsx::StatusChip`)과 이름이 같아
 * 둘이 같은 부품으로 읽혔다. 누르면 패널이 열리는 단추라 이름도 단추다. */
export function StatusNoticeButton({ notices }) {
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
  const tone = counts.critical ? "error" : counts.warning ? "warning" : "info";

  return (
    <Box sx={{ display: "inline-flex" }}>
      {/* 누르는 것은 30 단추이고, 합계는 단추 안의 건수 미니 칩이 말한다(핸드오프 RULES §2 · §3). 심각도는
          낱말(「장애 1」)이 말하고 아이콘 색이 거든다 — 색만으로 말하지 않는다. */}
      <KitButton
        ref={anchorRef}
        size="sm"
        startIcon={<ReportProblemRoundedIcon fontSize="small" color={tone} />}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="status-notices-pop"
      >
        {label}
        <CountChip value={total > 9 ? "9+" : total} sx={{ ml: 0.75 }} />
      </KitButton>
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
  /* 전폭 한 줄 띠는 메시지 박스의 `bleed` 갈래다 — 붉게 칠한 손 띠 대신 다른 알림 줄과 같은 1a 얼굴로 서고,
     장애라는 사실은 오류 아이콘과 그 접근 이름이 말한다. */
  return (
    <Callout
      tone="danger"
      compact
      variant="bleed"
      role="status"
      action={first.kind === "sync" ? (
        <KitButton size="sm" onClick={() => dismiss(first)}>닫기</KitButton>
      ) : null}
    >
      {first.message}{extra > 0 ? ` (그 외 장애 ${extra}건, 우측 상단 칩에서 확인)` : ""}
    </Callout>
  );
}
