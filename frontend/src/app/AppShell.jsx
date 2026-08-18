import React from "react";
import AppBar from "@mui/material/AppBar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { alpha, useTheme } from "@mui/material/styles";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import LightModeRoundedIcon from "@mui/icons-material/LightModeRounded";
import DarkModeRoundedIcon from "@mui/icons-material/DarkModeRounded";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { useAuth } from "./auth.jsx";
import { NotificationBell } from "./NotificationBell.jsx";
import { UserMenu } from "./UserMenu.jsx";
import { CommandPalette, useCommandPaletteHotkey } from "./CommandPalette.jsx";
import { AssistantDrawer, useAssistantHotkey } from "./AssistantDrawer.jsx";
import { ScopeBar } from "./ScopeBar.jsx";
import { Tour } from "./Tour.jsx";
import { activeNavPath, filterGroupsByQuery, groupForPath, NAV_BREAKPOINT_PX } from "./navConfig.js";
import { loginUrl, redirectToLogin } from "../lib/sessionRedirect.js";
import BrandLogo from "../ui/BrandLogo.jsx";
import TopBrand from "./TopBrand.jsx";
import TopSearch from "./TopSearch.jsx";
import { MascotTopButton } from "../ui/Mascot.jsx";
import { useDocumentTitle, brand, setBrand } from "./documentTitle.js";
import { useRouteAnnounce } from "./routeAnnounce.js";
import { recordNavVisit } from "../lib/recentNav.js";
import { navIcon } from "./navIcons.js";
import { Card, CrumbRootProvider, ErrorState, Skeleton } from "../ui/kit.jsx";
import { prefersReducedMotion } from "../ui/motion.js";
import { Banners } from "./Banners.jsx";
import { useStatusNotices } from "./StatusNotices.jsx";
import { NOTI_UNREAD, invalidateNotifications, notiUnreadKey } from "./notification-keys.js";
import { CONTENT_MAX_WIDTH, FONT_SIZE, FONT_WEIGHT, RADIUS } from "../ui/theme.js";
import { useThemeMode } from "../ui/ThemeModeProvider.jsx";
import { applyTheme, storeTheme } from "./theme-store.js";

/* 앱 셸 — 상단바 + 사이드바 + 본문.
 *
 * 사이드바 폭과 상단바 높이는 화면이 커지면 같이 커진다. 4K에서 고정 284px 사이드바는
 * 화면의 7%밖에 안 돼 메뉴가 실처럼 가늘어 보인다.
 */
/* 사이드바 폭 — 지시 13·48. 예전 264/300/340 은 로고 칸이 상단바 폭을 결정하는 구조라
 * Navigation 영역이 시각적으로 무거웠다. 한 단씩 줄여 데이터에 폭을 돌려준다. */
const DRAWER_WIDTH = { xs: 248, xxl: 280, uhd: 320 };
/* 상단바 높이 — 64 는 상시 도구에서 세로를 너무 먹는다. 로고·검색·사용자 영역을 함께
 * 줄여 균형을 맞춘다(지시 13: 이미지 크기만 줄이지 않는다). */
const APPBAR_HEIGHT = { xs: 52, xxl: 60, uhd: 68 };

/* 그룹 접힘 상태는 새로고침에도 유지한다(테마와 같은 이유). 5그룹 20여 항목 트리를 접어
 * 정리한 배치가 새로고침마다 초기화되던 문제. 공용 PC를 위해 계정별로 키를 나눈다. */
const NAV_COLLAPSE_KEY = "clovirone_nav_collapsed";
function navCollapseKey(userId) { return userId ? NAV_COLLAPSE_KEY + ":" + userId : NAV_COLLAPSE_KEY; }
function getStoredCollapsed(userId) {
  try {
    const v = JSON.parse(window.localStorage.getItem(navCollapseKey(userId)) || "{}");
    return v && typeof v === "object" ? v : {};
  } catch (e) { return {}; }
}

/** nav 항목의 badge 키 → 실제 숫자.
 *
 * 폴링을 새로 만들지 않는다. 채팅방 화면이 이미 같은 queryKey로 방 목록을 받고 있고,
 * 서버가 그 응답에 unread_total을 실어 준다(배지 하나 때문에 엔드포인트를 늘리지 않으려고
 * 그렇게 만들었다). react-query가 옵저버들의 간격 중 **가장 짧은 것**을 쓰므로,
 * 채팅방 화면에 있을 때는 5초, 다른 화면에서는 여기 60초로 돈다 — 사이드바 배지 하나
 * 때문에 앱 전체가 5초 폴링을 하지는 않는다.
 */
/* 어느 사이드바 항목이 어떤 알림 유형을 보여 주는가 (사용자 지적 S2).
 *
 * 화면을 열면 그 유형이 읽음 처리된다 — "확인하면 자동으로 없애는 형태로" 가 그 뜻이다.
 * 여기 한 곳에만 두는 이유: 배지를 붙이는 곳과 지우는 곳이 갈리면 **표시는 되는데 안 지워지는**
 * 항목이 생긴다(그 상태를 사용자가 먼저 알아챈다).
 *
 * 채팅은 여기 없다 — 채팅 안읽음은 알림이 아니라 방의 읽음 커서로 세고, 방을 열면 이미 지워진다. */
const BADGE_TYPES = {
  notifUnread: null,                          // 알림 화면은 그 자체가 목록이라 '모두 읽음'이 따로 있다
  jobFailed: ["job_failed"],
  // 위임받았다는 알림도 여기다 — 그 사람이 가야 할 곳이 승인 화면이다(X7).
  approvalPending: ["approval_overdue", "approval_requested", "approval_delegated"],
  // RSTR-03: 백업이 꺼졌거나/실패했거나/오래 정체됐을 때 전부 이 유형 하나로 온다
  // (app/backups/service.py::announce_backup_failure). 알림함·메일은 이미 나가지만
  // 사이드바 배지가 없어 그 화면을 안 열면 계속 안 보였다 — jobFailed/approvalPending과
  // 같은 이유로 여기 추가한다.
  backupFailed: ["backup_failed"],
};

const BADGE_ROUTES = {
  "/jobs": "jobFailed",
  "/approvals": "approvalPending",
  "/backup": "backupFailed",
};

function useNavBadges() {
  const rooms = useQuery({
    queryKey: ["team-chat-rooms"],
    queryFn: () => api("/api/team-chat/rooms"),
    /* 60초다(예전 30초). 이 폴링은 **모든 화면에서** 돌고, 서버쪽에서 방 목록은 가장 비싼
       조회 축에 속한다(H4). 그런데 이것이 채우는 것은 사이드바 숫자 하나뿐이고, 바로 옆
       알림 배지는 이미 60초로 돈다 — 두 배지가 서로 다른 속도로 갱신될 이유가 없다.
       채팅을 실제로 하는 중이면 채팅방 화면이 같은 키를 5초로 관찰하고, react-query 는
       옵저버들 중 **가장 짧은 간격**을 쓴다. 즉 이 값은 '채팅을 안 보고 있을 때'의 속도다. */
    refetchInterval: 60000,
    // 배지는 없어도 되는 정보다. 실패하면 조용히 0으로 두고 재시도로 소란 피우지 않는다.
    retry: false,
    staleTime: 10000,
  });
  // 알림 배지 상태는 **벨이 이미 폴링한다**(NotificationBell 의 `NOTI_UNREAD`).
  // 같은 키·같은 엔드포인트를 써서 react-query 가 하나로 합치게 한다 — 폴링을 하나 더
  // 만들면 사이드바가 있다는 이유만으로 요청이 두 배가 된다(PF1 이 지적한 그 부류다).
  // 두 콘솔의 알림 배지는 **다른 숫자**다(0060) — 사용자 사이드바의 '알림'은 개인 알림,
  // 관리자 사이드바의 '관리 알림'은 관리 조치가 필요한 사건이다. 벨이 지금 콘솔의 것을
  // 이미 폴링하므로 같은 키를 써서 react-query 가 합치게 하고(요청이 두 배가 되지 않게),
  // 반대편 숫자만 하나 더 관찰한다.
  const notif = useQuery({
    queryKey: notiUnreadKey("user"),
    queryFn: () => api("/api/notifications/unread-count?audience=user"),
    refetchInterval: 60000,
    retry: false,
    staleTime: 20000,
  });
  const adminNotif = useQuery({
    queryKey: notiUnreadKey("admin"),
    queryFn: () => api("/api/notifications/unread-count?audience=admin"),
    refetchInterval: 60000,
    retry: false,
    staleTime: 20000,
  });
  const myApprovals = useQuery({
    queryKey: ["my-approvals", "todo", "badge"],
    queryFn: () => api("/api/approvals/mine?box=todo&page_size=1"),
    refetchInterval: 60000,
    retry: false,
    staleTime: 20000,
  });
  const byType = (notif.data && notif.data.by_type) || {};
  const sum = (types) => (types || []).reduce((n, t) => n + (byType[t] || 0), 0);

  const adminByType = (adminNotif.data && adminNotif.data.by_type) || {};
  const adminSum = (types) => (types || []).reduce((n, t) => n + (adminByType[t] || 0), 0);

  return {
    chatUnread: (rooms.data && rooms.data.unread_total) || 0,
    notifUnread: (notif.data && notif.data.badge) || 0,
    adminNotifUnread: (adminNotif.data && adminNotif.data.badge) || 0,
    // 관리 콘솔 배지는 관리자 알림 쪽에서 센다 — 사용자 알림에 같은 유형이 섞여 들어와도
    // 관리 큐 숫자가 부풀지 않아야 한다.
    jobFailed: adminSum(BADGE_TYPES.jobFailed) || sum(BADGE_TYPES.jobFailed),
    approvalPending: adminSum(BADGE_TYPES.approvalPending) || sum(BADGE_TYPES.approvalPending),
    backupFailed: adminSum(BADGE_TYPES.backupFailed) || sum(BADGE_TYPES.backupFailed),
    // 개인 결재함은 **알림이 아니라 목록 자체**를 센다 — 알림은 읽으면 사라지지만 결재할
    // 건은 처리해야 사라진다. 알림 수로 세면 "읽었으니 0" 이 되어 할 일이 숨는다.
    myApprovalPending: (myApprovals.data && myApprovals.data.total) || 0,
  };
}

/* 화면에 들어오면 그 화면이 보여 주는 알림 유형을 읽음 처리한다 (S2 뒷절반).
 *
 * **폴링이 아니라 진입 이벤트**다 — 폴링으로 지우면 열지도 않은 알림이 사라진다.
 * 실패는 조용히 넘긴다: 배지가 한 번 더 보이는 것이 최악의 결과이고, 여기서 오류 토스트를
 * 띄우면 "화면을 열었더니 오류가 났다" 로 읽힌다. */
function useClearBadgeOnEntry(pathname, ready) {
  const qc = useQueryClient();
  React.useEffect(() => {
    // CSRF 토큰은 `/api/me` 응답과 함께 들어온다. 그 전에 POST 하면 403 이고, 배지는
    // 안 지워진 채로 남는다(실제로 그랬다). 인증이 준비된 뒤에만 부른다.
    if (!ready) return;
    const key = BADGE_ROUTES[pathname];
    const types = key && BADGE_TYPES[key];
    if (!types || !types.length) return;
    let cancelled = false;
    api("/api/notifications/read-types", { method: "POST", body: { types } })
      .then((res) => {
        if (cancelled || !res || !res.read) return;
        // 알림 캐시는 한 뿌리다 — 한 번이면 벨·팝오버 목록·전체 화면이 다 갱신된다 (PF9).
        invalidateNotifications(qc);
      })
      .catch(() => { /* 배지가 한 번 더 보일 뿐이다 */ });
    return () => { cancelled = true; };
  }, [pathname, ready, qc]);
}

/** 배지 숫자. 99를 넘으면 폭이 튀어 항목 이름이 밀리므로 99+로 자른다. */
function NavBadge({ count }) {
  if (!count) return null;
  return (
    <Box
      component="span"
      aria-label={`안 읽음 ${count}건`}
      sx={{
        ml: 1, px: 0.75, minWidth: "1.25rem", height: "1.25rem",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        borderRadius: "0.625rem", flexShrink: 0,
        fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.extrabold, lineHeight: 1,
        // PA-RC-0021: 흰 글자를 고정해 뒀었다 — 다크 모드의 error.main(#FF8B9B, 밝은 분홍)
        // 위에서 2.23:1(기준 4.5)로 실측 실패했다. error.contrastText는 MUI가 각 모드의
        // error.main 명도로 자동 계산한 값이라(명시적 override 없음, theme.js:256) 라이트에서는
        // 여전히 흰 글자, 다크에서는 검은 글자로 갈라져 두 모드 다 통과한다.
        bgcolor: "error.main", color: "error.contrastText",
      }}
    >
      {count > 99 ? "99+" : count}
    </Box>
  );
}

/* role이 없는 항목(`roles` 미지정)은 전 역할 공개, 있으면 그 목록에 현재 role이 있어야 본다.
 * SidebarNav의 현재 콘솔 메뉴와 CommandPalette의(잠재적으로 더 넓은) 검색 대상 메뉴가
 * 이 규칙을 공유한다 — 규칙이 두 벌이 되면 한쪽만 고쳐지는 날이 온다. */
function filterNavByRole(nav, role) {
  return (nav || [])
    .map((g) => ({ ...g, items: g.items.filter((it) => !it.roles || (role && it.roles.includes(role))) }))
    .filter((g) => g.items.length);
}

/* PA-RC-0017 acceptance_criteria 7: 레일 상단 내비 필터. `showFilter`가 없으면(사용자 콘솔
 * 호출부) 입력 자체를 그리지 않는다 — Handoff의 constraints가 "사용자 콘솔 내비는 건드리지
 * 않는다(이미 정상이다)"라고 명시했다. 관리자 39개 중 지금 role이 보는 목적지 안에서만
 * 좁힌다(groups는 이미 filterNavByRole을 거친 뒤라 role 밖 항목은 애초에 여기 없다). */
function SidebarNav({ groups, activePath, onNavigate, userId, showFilter }) {
  const badges = useNavBadges();
  const [collapsed, setCollapsed] = React.useState(() => getStoredCollapsed(userId));
  const [filterQuery, setFilterQuery] = React.useState("");
  const filtering = showFilter && filterQuery.trim().length > 0;
  const visibleGroups = filtering ? filterGroupsByQuery(groups, filterQuery) : groups;
  // PA-RC-0017: `isOpen`(아래)의 "기록 없음 = 접힘" 기본값과 짝을 맞춘다 — 지금 열려
  // 있다는 뜻은 `c[name] === false`(명시적으로 편 적이 있음)일 때뿐이므로, 그 반대를
  // 다음 값으로 적는다. 예전 `!c[name]`은 "기록 없음 = 펼침"이던 옛 기본값 시절 공식이라,
  // 지금 기본값(접힘)에서 그대로 두면 처음 눌러도 `true`(접힘)를 또 적어 아무 반응이 없었다.
  const toggle = (name) => setCollapsed((c) => {
    const next = { ...c, [name]: c[name] === false };
    try { window.localStorage.setItem(navCollapseKey(userId), JSON.stringify(next)); } catch (e) { /* ignore */ }
    return next;
  });

  /* 활성 라우트가 든 그룹은 접혀 있었어도 강제로 펼쳐 보인다(아래 isOpen). 그런데 그
   * "펼쳐 보임"을 실제로 펼친 것으로 기록해 두지 않으면, 다른 화면으로 넘어가는 순간 예전에
   * 저장된 collapsed:true로 조용히 되돌아간다 — 사용자는 그 그룹을 접은 적이 없는데 다른
   * 곳을 클릭했더니 저절로 접힌 것처럼 보인다(사용자 지적). 사용자가 실제로 편 것처럼
   * collapsed 상태 자체를 false로 갱신해 둔다. */
  const activeGroup = groups.find((g) => g.items.some((it) => it.to === activePath));
  React.useEffect(() => {
    if (!activeGroup || !collapsed[activeGroup.group]) return;
    setCollapsed((c) => {
      if (!c[activeGroup.group]) return c;
      const next = { ...c, [activeGroup.group]: false };
      try { window.localStorage.setItem(navCollapseKey(userId), JSON.stringify(next)); } catch (e) { /* ignore */ }
      return next;
    });
  }, [activeGroup, collapsed, userId]);

  /* VIS-113: 35항목 5그룹이 1080 높이에 다 안 들어가 목록 자체가 스크롤된다. 활성 그룹은
   * 강제로 펼치지만(위 effect), 펼친 뒤 그 활성 항목이 스크롤 영역 밖에 있으면(예: /restore-drills·
   * /policy-usage처럼 아래쪽 그룹) "내가 어디 있는지"를 보여주는 아무 표시도 화면에 없다 —
   * 하이라이트 자체는 이미 있는데(selected/aria-current) 스크롤이 안 따라가 안 보일 뿐이다.
   * 경로가 바뀔 때마다 활성 항목을 목록 안으로 스크롤한다(포커스는 옮기지 않는다 — 라우트
   * 전환 포커스는 이미 route-change-focus가 본문으로 보낸다, 여기서 또 가져가면 그것과 싸운다).
   * block:"nearest"라 이미 보이는 항목은 건드리지 않는다(불필요한 점프 방지). */
  const activeItemRef = React.useRef(null);
  React.useEffect(() => {
    const el = activeItemRef.current;
    if (!el) return;
    try {
      el.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    } catch (e) { /* ignore */ }
  }, [activePath]);

  /* VIS-104: 이 목록이 VIS-113처럼 스크롤되는데(35항목 5그룹은 1080 높이에 다 안 들어간다),
   * 바로 아래 항상 보이는 마스코트 카드가 붙어 있어 "메뉴가 여기서 끝난다"로 착시된다 —
   * 실제로는 스크롤하면 항목이 더 있다(1920×1080 실측: `내 업무량`·`내 활동`이 이렇게
   * 가려졌다, 1305 높이에서는 셋 다 보임). 스크롤 가능 여부를 재서 아래쪽 경계에 그림자를
   * 얹어 "더 있다"는 신호를 준다. ResizeObserver는 안 쓴다 — jsdom(테스트 환경)에 없어
   * 이 컴포넌트를 렌더하는 다른 테스트들이 전부 깨진다. 뷰포트 높이 차(1080 vs 1305)는
   * window resize로도 잡힌다. */
  const listRef = React.useRef(null);
  const [hasMoreBelow, setHasMoreBelow] = React.useState(false);
  React.useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const update = () => {
      // 1px 여유 — scrollHeight/clientHeight/scrollTop 반올림 오차로 스크롤 끝에서도
      // 차이가 0이 아니라 0.x로 남아 그림자가 안 사라지는 경우를 막는다.
      setHasMoreBelow(el.scrollHeight - el.clientHeight - el.scrollTop > 1);
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      el.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [visibleGroups, collapsed]);

  return (
    <>
      {showFilter ? (
        <Box sx={{ px: 1.5, pt: 1 }}>
          <TextField
            size="small"
            fullWidth
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            placeholder="메뉴 찾기"
            inputProps={{ "aria-label": "메뉴 찾기" }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchRoundedIcon fontSize="small" sx={{ color: "sidebar.muted" }} />
                </InputAdornment>
              ),
              sx: {
                color: "text.primary", bgcolor: "background.plate", borderRadius: RADIUS.sm / 8,
                "& fieldset": { borderColor: "divider" },
                "&:hover fieldset": { borderColor: "dividerStrong" },
              },
            }}
          />
        </Box>
      ) : null}
      {filtering && visibleGroups.length === 0 ? (
        <Typography variant="body2" sx={{ px: 3, py: 2, color: "sidebar.muted" }}>
          '{filterQuery}'와 맞는 메뉴가 없습니다.
        </Typography>
      ) : null}
      <List
        component="nav"
        ref={listRef}
        sx={{
          px: 1.5, py: 1, flex: 1, overflowY: "auto",
          boxShadow: hasMoreBelow ? "inset 0 -14px 10px -12px rgba(16,20,28,.18)" : "none",
          transition: "box-shadow .15s",
        }}
      >
      {visibleGroups.map((g) => {
        const groupActive = g.items.some((it) => it.to === activePath);
        // 현재 위치가 든 그룹은 사용자가 접어 뒀어도 항상 펼친다 — 알림 딥링크나 직접 해시로
        // 접힌 그룹 안의 경로에 도착했을 때 '여기 있음' 항목이 숨으면 길을 잃는다.
        // 필터링 중에는 무조건 편다 — 검색으로 찾은 항목이 접힌 그룹 안에 숨어 있으면 필터
        // 자체가 무용해진다.
        //
        // PA-RC-0017: `collapsed[g.group]`에 **아무 기록이 없을 때**(첫 방문, 또는 이번
        // 재편으로 그룹 이름이 바뀌어 예전 기록이 새 이름과 안 맞게 된 경우) 예전엔
        // `!collapsed[g.group]`(undefined → true)로 펼침이 기본값이었다 — 그룹 5개 전부가
        // 한꺼번에 펼쳐져 관리자 레일이 실측 scrollHeight 1716 / clientHeight 794로 정확히
        // "5개 이하·스크롤 없이 전부 보인다"(acceptance_criteria 1)를 깨뜨렸다(실브라우저
        // 재측정으로 확인). 바로 위 주석의 원래 의도("접혀 있었어도 강제로 펼친다")도 애초에
        // "평소엔 접혀 있다"를 전제한다 — 코드의 실제 기본값이 그 전제와 어긋나 있었다.
        // `collapsed[g.group] === false`(사용자가 실제로 편 적이 있어 명시적으로 기록됨)일
        // 때만 접힘 기록 없이도 펼치고, 그 외(기록 없음 포함)엔 접힘이 기본값이다 — 활성
        // 그룹은 `groupActive`가 여전히 강제로 편다.
        const isOpen = filtering || groupActive || collapsed[g.group] === false;
        const GroupIcon = g.icon;
        const itemsId = "nav-group-" + g.group;
        return (
          <Box key={g.group} sx={{ mb: 0.5 }}>
            <ListItemButton
              onClick={() => toggle(g.group)}
              aria-expanded={isOpen}
              aria-controls={itemsId}
              sx={{ borderRadius: RADIUS.sm / 8, py: 0.75, color: "sidebar.muted" }}
            >
              {GroupIcon ? (
                <ListItemIcon sx={{ minWidth: 32, color: "inherit" }}><GroupIcon fontSize="small" /></ListItemIcon>
              ) : null}
              <ListItemText
                primary={g.group}
                primaryTypographyProps={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.extrabold, letterSpacing: ".04em" }}
              />
              <ExpandMoreRoundedIcon
                fontSize="small"
                aria-hidden="true"
                sx={{ transform: isOpen ? "none" : "rotate(-90deg)", transition: "transform .18s" }}
              />
            </ListItemButton>
            {/* 접혔을 때 통째로 언마운트하면 aria-controls가 없는 노드를 가리키는 무효 참조가
                된다(ARIA disclosure 패턴 위반) — 항상 마운트해 두고 감추기만 한다. */}
            <Collapse in={isOpen} id={itemsId} unmountOnExit={false}>
              <List disablePadding sx={{ pl: 1 }}>
                {g.items.map((it) => {
                  const active = it.to === activePath;
                  const ItemIcon = navIcon(it.icon);
                  return (
                    <ListItemButton
                      key={it.to}
                      ref={active ? activeItemRef : undefined}
                      component={Link}
                      to={it.to}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      selected={active}
                      sx={{
                        position: "relative",
                        borderRadius: RADIUS.sm / 8,
                        minHeight: 34,
                        py: 0.25,
                        pl: 1.75,
                        color: active ? "text.primary" : "sidebar.muted",
                        /* 선택 표현은 제품 전체에서 **하나**다(D-141 RAISE, console-atmosphere):
                           앞머리 2px 레일 + 글자 굵기 + 글자색. 예전의 큰 알약 그라데이션
                           배경은 쓰지 않는다 — 펼침 상태와 선택 상태가 헷갈렸고(지시 48),
                           chrome 이 데이터보다 눈에 띄었다. */
                        "&::before": {
                          content: '""',
                          position: "absolute",
                          insetBlock: 4,
                          insetInlineStart: 0,
                          width: 2,
                          borderRadius: 1,
                          bgcolor: active ? "sidebar.activeRail" : "transparent",
                        },
                        "&.Mui-selected": { bgcolor: "transparent" },
                        "&.Mui-selected:hover": { bgcolor: "sidebar.hover" },
                        "&:hover": { bgcolor: "sidebar.hover" },
                      }}
                    >
                      {/* 기준 파일은 메뉴 항목마다 아이콘을 둔다(§2). 예전에는 그룹에만 있어서
                          펼친 목록이 글자만 늘어선 벽이었다. 아이콘은 장식이 아니라 훑을 때
                          위치를 기억하게 하는 표지라, 항목 쪽에 있어야 한다. */}
                      {ItemIcon ? (
                        <ListItemIcon sx={{ minWidth: 30, color: "inherit", opacity: active ? 1 : 0.82 }}>
                          <ItemIcon size={18} strokeWidth={1.8} aria-hidden="true" />
                        </ListItemIcon>
                      ) : null}
                      <ListItemText
                        primary={it.label}
                        primaryTypographyProps={{ fontSize: FONT_SIZE.body, fontWeight: active ? FONT_WEIGHT.bold : FONT_WEIGHT.semibold }}
                      />
                      {it.badge ? <NavBadge count={badges[it.badge]} /> : null}
                    </ListItemButton>
                  );
                })}
              </List>
            </Collapse>
          </Box>
        );
      })}
      </List>
    </>
  );
}

/* 상단바 다크/라이트 토글 — 사용자 지적 Q3("다크/화이트 버튼이 오른쪽 상단에 있어야 한다").
 *
 * 예전에는 이 스위치가 **사용자 메뉴를 열어야** 나왔다. 하루에도 여러 번 쓰는 것이
 * 두 번 클릭 뒤에 숨어 있었다. 사용자 메뉴 쪽 항목은 그대로 둔다 — 좁은 화면에서는
 * 상단바 아이콘이 접히므로 두 경로가 다 필요하다.
 *
 * 상태는 `<html data-theme>` 이 정본이고 ThemeModeProvider 가 MutationObserver 로 따라온다.
 * 그래서 여기서는 applyTheme 만 부르면 되고 별도 상태를 들 필요가 없다. */
/* 사용자/관리자 전환 — 사용자 지적 P2("사용자 관리자 버전의 위치를 왼쪽 트리 상단으로 옮겨라").
 *
 * 예전에는 상단바 오른쪽, 알림 벨과 아바타 사이에 있었다. 그런데 이건 **어느 메뉴 트리를
 * 볼 것인가**를 고르는 스위치라 알림·계정 같은 전역 컨트롤이 아니라 그 트리 위에 있어야
 * 맥락이 맞는다. 사이드바가 어두운 판이라 배경/글자색만 그쪽에 맞춘다.
 *
 * 관리자 권한이 없는 사용자에게는 애초에 렌더되지 않는다(호출측 `!isUser` 조건). */
function ConsoleSwitch({ userSeg, onNavigate }) {
  return (
    <Box
      role="group"
      aria-label="화면 전환"
      sx={{
        display: "flex", mx: 1.5, mt: 1.5, mb: 0.5, p: 0.5,
        bgcolor: "background.inset", borderRadius: RADIUS.sm / 8,
      }}
    >
      {[{ label: "사용자", on: userSeg, to: "/me" }, { label: "관리자", on: !userSeg, to: "/dashboard" }].map((seg) => (
        <Button
          key={seg.label}
          size="small"
          onClick={() => onNavigate(seg.to)}
          aria-current={seg.on ? "page" : undefined}
          sx={{
            flex: 1, minHeight: 28, borderRadius: RADIUS.sm / 8, textTransform: "none",
            fontWeight: seg.on ? FONT_WEIGHT.semibold : FONT_WEIGHT.regular,
            /* 선택된 쪽이 판(plate)으로 떠오르고 나머지는 오목면에 남는다 — 트랙이 inset 이라
               두 면이 서로 다른 값이어야 눌린 쪽이 보인다. 예전에는 배경이 두 모드 모두
               리터럴 흰색이었는데(CTR-02), chrome 이 밝아지면서 선택 표시가 사라졌다. */
            color: seg.on ? "text.primary" : "sidebar.muted",
            bgcolor: seg.on ? "background.plate" : "transparent",
            boxShadow: seg.on ? (t) => `inset 0 0 0 1px ${t.palette.divider}` : "none",
            "&:hover": { bgcolor: seg.on ? "background.plate" : "sidebar.hover" },
          }}
        >
          {seg.label}
        </Button>
      ))}
    </Box>
  );
}

function ThemeToggle({ userId }) {
  const { mode } = useThemeMode();
  const dark = mode === "dark";
  const next = dark ? "light" : "dark";
  return (
    <Tooltip title={dark ? "라이트 모드로" : "다크 모드로"}>
      <IconButton
        onClick={() => { storeTheme(next, userId); applyTheme(next); }}
        aria-label={dark ? "라이트 모드로 전환" : "다크 모드로 전환"}
        color="inherit"
      >
        {dark ? <LightModeRoundedIcon /> : <DarkModeRoundedIcon />}
      </IconButton>
    </Tooltip>
  );
}

export function AppShell({
  nav, paletteNav, ariaLabel, navOpen, onCloseNav, onToggleNav,
  isUser, userSeg, minimal, showMenu, children,
}) {
  const theme = useTheme();
  const auth = useAuth();
  const loc = useLocation();
  const navigate = useNavigate();
  // 탭 제목을 화면마다 다르게 — 정적 <title> 하나뿐이라 어느 탭이 무엇인지 구분이 안 됐다.
  useDocumentTitle(loc.pathname);
  /* 화면이 바뀌면 포커스를 본문으로 옮기고 그 사실을 한 줄 알린다 (Z14).
     무엇을 언제 알릴지와 그 이유는 routeAnnounce.js 에 적어 뒀다. */
  const routeMessage = useRouteAnnounce(loc.pathname);
  // SRCH-04 — 팔레트(Ctrl+K)의 빈 질의 상태가 최근 방문을 보여주려면 어디를 다녀갔는지
  // 알아야 한다. 서버 왕복 없이 즉시 반응해야 하는 자리라 localStorage에만 남긴다.
  React.useEffect(() => { recordNavVisit(loc.pathname); }, [loc.pathname]);
  const role = auth.data && auth.data.role;
  const userId = auth.data && auth.data.id;
  const name = (auth.data && auth.data.display_name) || "";
  // 프로필 사진은 /api/me 가 함께 준다 — 상단바 아바타 하나 때문에 별도 요청을 하지 않는다.
  const avatarUrl = (auth.data && auth.data.avatar_url) || null;
  const isNarrow = useMediaQuery(`(max-width:${NAV_BREAKPOINT_PX}px)`);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  // 클로비 AI 드로어(Q2) — 세 진입점이 모두 이걸 연다. 예전에는 셋 다
  // `navigate("/chat")` 이라 물어보려고 누르면 보던 화면이 사라졌다.
  const [assistantOpen, setAssistantOpen] = React.useState(false);
  // 이 화면이 보여 주는 알림 유형을 진입 시 읽음 처리한다(S2 "확인하면 자동으로 없애는 형태로").
  useClearBadgeOnEntry(loc.pathname, !!(auth.data && auth.data.id));
  useCommandPaletteHotkey(setPaletteOpen);
  useAssistantHotkey(setAssistantOpen);

  // 권한 없는 메뉴는 숨긴다 — 검색 결과로 403에 빠지면 안 된다.
  const groups = React.useMemo(() => filterNavByRole(nav, role), [nav, role]);
  // SRCH-01: 팔레트는 예전에 사이드바와 같은 `nav`(현재 콘솔 하나만)를 썼다 — 그래서
  // system_admin이 사용자 콘솔(`/me`)에 있는 동안엔 Ctrl+K로 "사용자"·"백업" 같은 관리자
  // 화면을 찾을 방법이 아예 없었다(메뉴 결과 0건, 사이드바가 바로 옆에 있는데도). 팔레트의
  // 존재 이유가 "어디서든 어디로든"이므로, `paletteNav`(두 콘솔 전체, App.jsx가 넘겨줌)가
  // 있으면 그걸 쓴다 — role 필터는 그대로라 지금 역할이 못 보는 화면은 여전히 안 뜬다.
  // `paletteNav`를 안 넘기는 기존 호출부(테스트 등)는 예전처럼 `nav`만 검색한다.
  const paletteGroups = React.useMemo(
    () => filterNavByRole(paletteNav || nav, role),
    [paletteNav, nav, role]
  );
  /* 상세 화면에는 자기 메뉴 항목이 없다(`/tickets/:id`·`/search`·`/profile`) — 예전에는
     그런 화면에서 **선택 표시가 통째로 사라졌다**(사용자 지적 #14). 어디서 왔는지가
     있으면 그 메뉴를, 없으면 `ROUTE_OWNER` 의 기본 소속을 켠다. */
  const activePath = activeNavPath(
    loc.pathname,
    groups.flatMap((g) => g.items.map((it) => it.to)),
    loc.state && loc.state.from,
  );

  // AI 도우미(/chat)는 우하단 마스코트 버튼만 감춘다 — 그 버튼이 하는 일이 "/chat 으로 가기"
  // 뿐이라 그 화면에서는 아무 일도 하지 않으면서 입력창을 가린다.
  //
  // 예전에는 이 화면만 **폭 캡과 패딩까지 없앴다**("자체 2단 레이아웃이라"). 그 결과 앱에서
  // 유일하게 제목도 여백도 없이 맨바닥에 붙는 화면이 됐고, 사용자가 "너무 안이쁘다" 고 한
  // 이유가 그것이었다(S3). 지금은 다른 화면과 같은 `c-screen` + PageHeader + 카드 위에
  // 있으므로 예외를 둘 이유가 없다.
  const onAssistant = loc.pathname === "/chat";
  const homeUser = isUser || userSeg;
  // PA-RC-0039: 관리자 콘솔의 breadcrumb 뿌리는 계속 리터럴 "관리자"다(화면마다 손으로
  // 넘기는 area가 그 아래 단계를 맡는다) — 사용자 콘솔만 지금 경로가 속한 groups(=USER_NAV,
  // role로 이미 걸러진 값)의 그룹 이름으로 유도한다. activePath와 같은 인자로 같은
  // activeNavPath를 타므로 사이드바 강조와 항상 같은 답을 낸다.
  const crumbRoot = homeUser
    ? (groupForPath(groups, loc.pathname, loc.state && loc.state.from) || "")
    : "관리자";

  // 시스템 상태·공지는 이제 종(NotificationBell) 안에서만 보인다(지시 1). 훅은 셸이 한 번
  // 부르고 벨에 내려준다 — 벨이 직접 부르면 같은 데이터를 두 번 조회한다.
  // minimal(세션 만료) 상태에선 이 API 도 401 이므로 아예 조회하지 않는다.
  const statusNotices = useStatusNotices({ enabled: !minimal });

  const drawerContent = (
    /* chrome 은 캔버스 계열 단색이다(D-141). 예전에는 위에서 아래로 어두워지는 딥 인디고
       그라데이션이었고, 글자색이 `common.white` 로 고정돼 있었다 — 사이드바가 밝아진 뒤에도
       그 흰 글자가 남아 제품명이 대비 1.21 로 사라졌다(하네스가 잡았다).
       색은 팔레트에서 온다. tokens.css 는 같은 theme.js 에서 생성되므로 두 소스가 갈라지지
       않는다(scripts/generate_design_tokens.mjs). */
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "sidebar.bg", color: "sidebar.text", borderInlineEnd: 1, borderColor: "sidebar.line" }}>
      {/* 로고+브랜드명 묶음은 사이드바 폭 안에서 가운데 정렬한다(사용자 지적). justifyContent
          만으로는 좁은 화면에서 닫기 버튼이 로고 옆에 그대로 남아 묶음이 광학적으로 오른쪽에
          치우쳐 보이므로, 그 버튼은 절대 위치로 오른쪽 끝에 고정해 가운데 정렬을 방해하지
          않게 한다. */}
      <Toolbar sx={{ minHeight: APPBAR_HEIGHT, px: 2.5, gap: 1.5, justifyContent: "center", position: "relative" }}>
        <BrandLogo markOnly width={30} />
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: "0.9375rem", fontWeight: FONT_WEIGHT.extrabold, lineHeight: 1.1 }}>{brand()}</Typography>
          <Typography sx={{ fontSize: FONT_SIZE.caption, color: "sidebar.muted" }}>Smart Workspace Assistant</Typography>
        </Box>
        {isNarrow ? (
          <IconButton
            onClick={onCloseNav}
            aria-label="메뉴 닫기"
            sx={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", color: "inherit" }}
          >
            <CloseRoundedIcon />
          </IconButton>
        ) : null}
      </Toolbar>

      {auth.isLoading ? (
        <Box sx={{ p: 3 }}><Skeleton lines={6} /></Box>
      ) : auth.isError ? (
        /* 세션이 만료되면 역할이 없어 역할 게이트 없는 항목이 전부 클릭 가능하게 그려진다 —
           누르는 족족 401로 가는 죽은 링크 더미다. 상단바를 minimal로 접는 것과 같은 정신으로
           사이드바도 재로그인 안내 한 칸으로 접는다. */
        <Box sx={{ p: 3, display: "grid", gap: 2 }}>
          <Typography variant="body2" sx={{ color: "sidebar.muted" }}>세션이 만료되었습니다.</Typography>
          <Button variant="contained" href={loginUrl()}>다시 로그인</Button>
        </Box>
      ) : (
        <>
          {/* 트리 위에 둔다 — 이 스위치가 고르는 것이 바로 아래 트리다(P2). */}
          {!isUser && !minimal ? (
            <ConsoleSwitch userSeg={userSeg} onNavigate={(to) => { onCloseNav(); navigate(to); }} />
          ) : null}
          <SidebarNav groups={groups} activePath={activePath} onNavigate={onCloseNav} userId={userId} showFilter={!isUser} />
        </>
      )}
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100dvh", bgcolor: "background.default" }}>
      {/* 화면 전환 알림 (Z14). 비어 있어도 **항상** 떠 있어야 한다 — 라이브 영역이 내용과
          같은 순간에 생기면 그 변화를 낭독하지 않는 스크린리더가 있다. 눈에는 보이지 않고
          (sr-only) 레이아웃도 차지하지 않는다. */}
      <Box className="sr-only" role="status" aria-live="polite" aria-atomic="true">{routeMessage}</Box>

      {/* HashRouter에서 href='#main-content'는 해시를 라우트로 파싱하므로 앵커 대신
          <main>(tabIndex=-1)에 직접 포커스를 준다. 첫 Tab에 나와야 한다. */}
      {!minimal ? (
        <Box
          component="a"
          href="#main-content"
          onClick={(e) => { e.preventDefault(); const m = document.getElementById("main-content"); if (m) m.focus(); }}
          sx={{
            position: "fixed", top: 8, left: 8, zIndex: (t) => t.zIndex.tooltip + 1,
            px: 2, py: 1, borderRadius: 2, bgcolor: "primary.main", color: "primary.contrastText",
            fontWeight: FONT_WEIGHT.bold, textDecoration: "none",
            transform: "translateY(-200%)", transition: "transform .15s",
            "&:focus": { transform: "none" },
          }}
        >
          본문 바로가기
        </Box>
      ) : null}

      <AppBar
        position="fixed"
        elevation={0}
        sx={(t) => ({
          zIndex: t.zIndex.drawer + 1,
          /* chrome 은 발광하지 않는다(D-141). 예전에는 보라 빛무리 + 3정지점 그라데이션이
             화면에서 가장 채도 높은 면이었다 — 정작 데이터는 무채색인데 상단바가 시선을
             가져갔다. 이제 캔버스 계열 단색에 실선 하나다. 채도는 조치가 필요한 상태·
             현재 선택·주요 행동 세 자리에만 쓴다. */
          background: t.palette.sidebar.bg,
          color: t.palette.text.primary,
          borderBottom: `1px solid ${t.palette.sidebar.line}`,
        })}
      >
        {/* disableGutters — MUI Toolbar 기본 좌우 패딩(24px)이 남으면 로고 칸이
            사이드바 폭에서 그만큼 밀려 두 층의 경계가 어긋난다. `pl:0` 으로는
            안 되고(gutters 가 브레이크포인트별로 다시 넣는다) 아예 꺼야 한다.
            왼쪽 여백은 로고 칸이 자기 안에서 주고, 오른쪽만 여기서 준다. */}
        <Toolbar disableGutters sx={{ minHeight: APPBAR_HEIGHT, gap: 1, pr: 2.5 }}>
          {showMenu && isNarrow ? (
            <IconButton
              onClick={onToggleNav}
              aria-label={navOpen ? "메뉴 닫기" : "메뉴 열기"}
              aria-expanded={navOpen}
              aria-controls="app-sidebar"
              color="inherit"
              edge="start"
            >
              {navOpen ? <CloseRoundedIcon /> : <MenuRoundedIcon />}
            </IconButton>
          ) : null}

          {/* minimal(세션 만료) 화면에선 라우팅이 401에 갇혀 해시만 바뀌고 화면은 그대로다 —
              홈 대신 유일한 실제 CTA인 로그인으로 보낸다(죽은 컨트롤 방지).

              로고 칸은 **사이드바 열과 정확히 같은 폭**이다 (사용자 지적). 상단바는 한 줄로
              보이지만 실제로는 두 구역이다: 왼쪽은 사이드바 위, 오른쪽은 본문 위. 그 경계가
              아래 사이드바 경계와 어긋나면 두 층이 서로 다른 격자를 쓰는 것처럼 보인다.
              그래서 검색 막대는 이 칸 **다음**에서 시작한다. 좁은 화면(사이드바가 서랍으로
              접힘)에서는 그 열 자체가 없으므로 폭을 풀어 준다. */}
          <TopBrand
            onClick={() => { if (minimal) { redirectToLogin(); } else { navigate(homeUser ? "/me" : "/dashboard"); } }}
            label={minimal ? "로그인 화면으로" : "홈으로"}
            width={isNarrow ? undefined : DRAWER_WIDTH}
          />

          {!minimal ? <TopSearch onOpen={() => setPaletteOpen(true)} /> : null}

          {/* 오른쪽 컨트롤을 화면 끝으로 민다 — 사용자 지적 Q3.
              예전에는 이 스페이서가 `minimal` 일 때만 늘어나서, 일반 화면에서는 검색 막대
              (maxWidth 45rem) 바로 뒤에 컨트롤이 붙고 오른쪽이 통째로 비었다.
              실측: 1920px 에서 573px, 2560px 에서 1,062px, 3840px 에서 2,188px 가 빈 채였다. */}
          <Box sx={{ flex: 1 }} />

          {!minimal ? (
            <>
              {/* 넓은 화면에서는 위 검색 막대가 그 일을 하므로 아이콘은 좁은 화면에만 둔다. */}
              <Tooltip title="통합 검색 (Ctrl+K)">
                <IconButton onClick={() => setPaletteOpen(true)} aria-label="통합 검색 열기"
                  color="inherit" sx={{ display: { xs: "inline-flex", md: "none" } }}>
                  <SearchRoundedIcon />
                </IconButton>
              </Tooltip>
              {/* 상단바 우측 클로비(기준 파일의 .top-clovi-btn). 사용자가 "오른쪽 상단의 웃는
                  클로비를 유지"라고 했는데 그 자리에는 실제로 MUI 의 일반 로봇 아이콘이 있었다.
                  좁은 화면에서만 보이던 것도 항상 보이게 바꾼다 — 우하단 FAB 은 md 미만에서
                  숨는데, 그 아래 폭에서 AI 도우미로 가는 길이 아이콘 하나뿐이었다.
                  AI-57: /chat 에서는 이 버튼도 우하단 FAB(§661)과 같은 이유로 안 띄운다 —
                  이미 전체화면 채팅이 열려 있는데 누르면 그 위에 같은 대화를 다시 보여주는
                  드로어가 겹쳐 뜬다. "동작하지 않는(=의미 없는) 컨트롤을 띄워 두지 않는다"는
                  이 저장소 원칙과 같은 방향. */}
              {!onAssistant ? <MascotTopButton onClick={() => setAssistantOpen(true)} /> : null}
              <ThemeToggle userId={userId} />
            </>
          ) : null}

          {/* 사용자/관리자 전환은 **사이드바 최상단**으로 옮겼다(P2). 여기 두 벌을 두면
              같은 스위치가 화면에 두 번 나온다. 좁은 화면에서는 사이드바가 서랍으로 접히지만,
              그때는 메뉴를 여는 것이 곧 트리를 보는 것이라 스위치도 함께 나온다. */}

          {/* 지시 1: 사용자 알림의 단일 진입점은 이 종 하나다. 예전에는 헤더 상태 칩과
              본문 위 CRITICAL 띠가 따로 있었다. 지시 67 에 따라 정보를 없앤 것이 아니라
              옮긴 것이다 — 운영자용 서비스 Health 는 관리자 대시보드·진단이 계속 보여 준다. */}
          {!minimal ? <NotificationBell isUser={isUser} notices={statusNotices} /> : null}
          {!minimal ? (
            <UserMenu
              name={name} userId={userId} avatarUrl={avatarUrl}
              // 내 소속·관리 범위(0060 §5) — 셸이 이미 들고 있는 값을 넘긴다.
              me={auth.data && (auth.data.user || auth.data)}
            />
          ) : null}
        </Toolbar>
      </AppBar>

      {showMenu ? (
        /* 이 <aside>는 '자리를 차지하는' 역할이다. MUI Drawer(permanent)는 position:fixed라
           흐름에서 빠지므로, 같은 폭의 자리를 여기서 잡아 주지 않으면 본문이 사이드바 밑으로
           깔려 왼쪽이 잘린다. 좁은 화면에서는 서랍이 오버레이라 자리를 잡으면 안 된다.
           (폭을 sx={{ width: { md: DRAWER_WIDTH } }}처럼 반응형 객체를 중첩해 쓰면 조용히
            무시된다 — 실제로 그렇게 썼다가 본문이 통째로 가려졌다.) */
        <Box component="aside" id="app-sidebar" sx={{ width: isNarrow ? 0 : DRAWER_WIDTH, flexShrink: 0 }}>
          <Drawer
            variant={isNarrow ? "temporary" : "permanent"}
            open={isNarrow ? navOpen : true}
            onClose={onCloseNav}
            ModalProps={{ keepMounted: true }}
            aria-label={ariaLabel}
            sx={{
              "& .MuiDrawer-paper": {
                width: DRAWER_WIDTH, boxSizing: "border-box", border: 0,
                bgcolor: "sidebar.bg",
              },
            }}
          >
            {drawerContent}
          </Drawer>
        </Box>
      ) : null}

      <Box
        component="main"
        id="main-content"
        tabIndex={-1}
        sx={{
          flex: 1, minWidth: 0, display: "flex", flexDirection: "column",
          pt: APPBAR_HEIGHT.xs / 8, outline: "none",
          "@media (min-width:2200px)": { pt: APPBAR_HEIGHT.xxl / 8 },
          "@media (min-width:3000px)": { pt: APPBAR_HEIGHT.uhd / 8 },
        }}
      >
        {/* 배너는 본문 폭 캡 밖에 있어야 한다 — 안쪽에 두면 4K 에서 화면 가운데만 띠가 뜨고
            양옆이 비어, "전역 공지"가 한 열짜리 카드처럼 보인다. 세션 만료(minimal) 상태에는
            띄우지 않는다: 그때 필요한 유일한 행동은 재로그인이고, 배너 API 도 401 이다. */}
        {!minimal ? <Banners /> : null}
        {/* 스코프 바 — 배너 **아래**, 본문 폭 캡 **안**이다. 배너는 전역 공지라 화면 폭
            전체를 쓰지만 이건 "이 목록이 왜 이만큼인가" 를 설명하는 줄이라 목록과 같은
            폭이어야 붙어 읽힌다. 전체 범위인 사람에게는 아무것도 그리지 않는다. */}
        <Box
          sx={
            {
                  width: "100%", maxWidth: CONTENT_MAX_WIDTH, mx: "auto",
                  px: { xs: 2, sm: 3, xl: 4 }, py: { xs: 2.5, sm: 3.5 },
                  // PA-RC-0020: 우하단 FAB을 없애 본문 위에 뜬 컨트롤이 더는 없다 — FAB
                  // 자리를 비워 두던 큰 하단 여백(md:14)도 함께 걷어낸다.
                  pb: { xs: 3, md: 4 },
            }
          }
        >
          {!minimal ? <ScopeBar /> : null}
          <CrumbRootProvider value={crumbRoot}>
            {auth.isLoading ? <Card><Skeleton /></Card> : children}
          </CrumbRootProvider>
        </Box>
      </Box>

      {/* PA-RC-0019/0020: 우하단 FAB과 사이드바 카드를 없앴다 — 셋이던 진입점(FAB·사이드바
          카드·상단 칩)이 헤더 칩 하나 + 전역 단축키(Ctrl/Cmd+/, useAssistantHotkey)로
          모인다. FAB은 늘 본문 위에 떠 있어 표 화면 마지막 행(그리고 「상세」 버튼 열이
          사라진 뒤로는 행 자체)을 실제로 가려 클릭을 가로챘다(elementFromPoint 히트테스트로
          확인, `PA-RC-0019`) — z-index만 낮추거나 자리를 옮기는 대신 진입점 자체를 하나로
          줄여 겹칠 대상을 없앴다. */}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} groups={paletteGroups} />

      {/* 클로비 AI 드로어(Q2) — 클로비를 누르면 보던 화면 위로 열린다. 예전에는 세 진입점이
          모두 `/chat` 으로 이동해서, 물어볼 대상이 화면에 있는데 그 화면을 떠나야 했다.
          세션 만료(minimal) 상태에서는 띄우지 않는다 — 대화 API 도 401 이다. */}
      {!minimal ? (
        <AssistantDrawer open={assistantOpen} onClose={() => setAssistantOpen(false)} />
      ) : null}

      {/* 첫 로그인 둘러보기 — 홈(/me)에서만 스스로 열리고, 건너뛰면 서버에 기록돼 다시 안 뜬다.
          세션 만료(minimal) 상태에서는 띄우지 않는다: 그때 필요한 유일한 행동은 재로그인이다. */}
      {!minimal ? <Tour /> : null}
    </Box>
  );
}

/* 셸 안에서 쓰는 오류 표시 — 라우트가 크래시해도 사이드바·상단바는 살아 이동할 수 있게 한다. */
export function ShellErrorFallback() {
  return (
    <ErrorState
      error={{ message: "화면을 표시하는 중 문제가 발생했습니다. 새로고침해 주세요." }}
      onRetry={() => window.location.reload()}
    />
  );
}
