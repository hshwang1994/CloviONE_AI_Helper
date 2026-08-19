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
import { Card, CrumbRootProvider, ErrorState, Skeleton } from "../ui/kit.jsx";
import { prefersReducedMotion } from "../ui/motion.js";
import { Banners } from "./Banners.jsx";
import { useStatusNotices } from "./StatusNotices.jsx";
import { NOTI_UNREAD, invalidateNotifications, notiUnreadKey } from "./notification-keys.js";
import { BREAKPOINTS, CONTENT_MAX_WIDTH, CONTROL, FONT_SIZE, FONT_WEIGHT, ICON,
  NAV_ANATOMY, RADIUS, remPx } from "../ui/theme.js";
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

/* 사이드바 한 줄의 **공통 해부구조** (PLAN «Icon System» 라벨 시작선 계약).
 *
 * 그룹 헤더와 자식 항목이 같은 상자를 쓴다 — 다르면 두 격자가 생긴다. 값은 전부
 * `NAV_ANATOMY`/`CONTROL`/`ICON` 에서 오고 여기에 리터럴을 적지 않는다.
 *
 *   · `px` 는 MUI spacing 단위다. spacing(1) = 0.5rem = @16 8px 이므로 `px / 8` 이 rem 으로
 *     가는 환산이다 — 4K 레버(`styles/root.css`)가 루트 폰트사이즈를 올리면 여백·글리프·
 *     라벨 시작선이 **함께** 자란다. 여기서 px 로 굳히면 3840 에서 틀만 커지고 칸이 안 커져
 *     글리프가 라벨과 맞붙는다(F-W2R-02 실측).
 *   · 행은 하우징 **가장자리까지** 간다(바깥 List 의 좌우 여백 0). 활성 레일이 목록 안쪽
 *     20px 에 떠 있는 조각이 아니라 하우징을 따라 흐르는 선이 되려면 그래야 한다.
 *   · 알약 모서리를 쓰지 않는다 — 선택 상태를 배경 알약으로 말하면 그룹 펼침과 헷갈린다(지시 48).
 *   · 포커스 링은 안쪽으로 그린다. 전역 `:focus-visible` 규칙은 `outline-offset: 2` 라
 *     가장자리 행에서 링이 하우징 밖으로 새어 나간다. */
const NAV_GLYPH_SLOT = remPx(NAV_ANATOMY.glyph + NAV_ANATOMY.gap);
const NAV_ROW = {
  position: "relative",
  minHeight: remPx(CONTROL.navItem),
  px: NAV_ANATOMY.padInline / 8,
  py: 0.25,
  borderRadius: 0,
  "&:hover": { bgcolor: "sidebar.hover", color: "sidebar.text" },
  /* 두 선택자를 **함께** 적는다. MUI 는 자기 키보드 판정으로 `.Mui-focusVisible` 를 붙이고,
     브라우저는 자기 판정으로 `:focus-visible` 를 건다 — 둘이 항상 같이 걸리지는 않는다.
     한쪽만 적으면 나머지 경우에 전역 규칙(`outline-offset: 2`)이 이겨서 링이 하우징 **밖**으로
     새어 나간다. 실브라우저 프로브가 정확히 그 상태를 8/8 조합에서 잡았다(offset 2px). */
  "&.Mui-focusVisible, &:focus-visible": {
    outline: (t) => `2px solid ${t.palette.sidebar.focusRing}`,
    outlineOffset: "-2px",
  },
};

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
function SidebarNav({ groups, activePath, onNavigate, userId, showFilter, groupsOpenByDefault }) {
  const badges = useNavBadges();
  const [collapsed, setCollapsed] = React.useState(() => getStoredCollapsed(userId));

  /* `userId` 가 **마운트 뒤에 바뀌면** 그 계정의 접힘 기록을 다시 읽는다.
   *
   * 접힘 키는 계정별이다(`clovirone_nav_collapsed:<userId>`) — 공용 PC 에서 남의 배치가
   * 넘어오지 않게 나눠 둔 것이다. 그런데 `useState` 초기화 함수는 **한 번만** 돌기 때문에,
   * 이 컴포넌트가 마운트된 채로 신원이 바뀌는 경로(대리 보기 시작·종료, 재로그인 handoff)
   * 에서는 앞 계정의 상태가 그대로 남는다. 더 나쁜 것은 그 다음 `toggle` 이 **새 계정의
   * 키에 앞 계정의 상태를 쓴다**는 것이다 — 키를 나눈 이유가 그 자리에서 무너진다.
   *
   * 평상시 새로고침은 이 경로를 타지 않는다. 셸이 `auth.isLoading` 동안 사이드바 대신
   * 스켈레톤을 그리므로 `SidebarNav` 는 이미 userId 가 있는 상태로 마운트되고, 실브라우저
   * 실측도 그렇게 나온다(접고 → 새로고침 → 접힌 채 그대로). 여기서 막는 것은 **신원 교체**
   * 하나다. */
  const hydratedFor = React.useRef(userId);
  React.useEffect(() => {
    if (hydratedFor.current === userId) return;
    hydratedFor.current = userId;
    setCollapsed(getStoredCollapsed(userId));
  }, [userId]);
  const [filterQuery, setFilterQuery] = React.useState("");
  const filtering = showFilter && filterQuery.trim().length > 0;
  const visibleGroups = filtering ? filterGroupsByQuery(groups, filterQuery) : groups;
  /* 기록이 없을 때의 기본값은 **콘솔마다 다르다** (PLAN «Chrome 설계»: "사용자 vs 관리자 —
   * Shell·항목 해부구조·상태 계약·아이콘 규칙 완전 동일. 차이는 깊이 표현뿐이다").
   *   · 사용자 콘솔 4그룹 20항목 — 다 펼쳐도 한 화면에 들어간다. 펼침이 기본이라 목록이
   *     곧 지도다.
   *   · 관리자 콘솔 6그룹 31항목 — PA-RC-0017 실측에서 전부 펼치면 scrollHeight 1716 /
   *     clientHeight 794 로 "스크롤 없이 전부 보인다"가 깨졌다. 접힘이 기본이고, 대신
   *     메뉴 필터가 목적지를 좁힌다.
   * `collapsed[name]` 에 기록이 있으면 그 사람이 실제로 누른 것이므로 언제나 그것이 이긴다.
   * 예전 공식(`c[name] === false` 만 펼침)은 기본값이 한 벌이던 시절 것이라, 기본값이
   * 둘이 된 지금 그대로 두면 사용자 콘솔에서 처음 눌러도 아무 반응이 없다. */
  /* 펼침이 기본인 것은 **목록이 곧 지도일 수 있을 때**뿐이다.
   *
   * 1920 에서는 사용자 rail 4그룹 18항목이 다 펼쳐져도 들어간다. 1366x768 에서는 안 들어간다 —
   * 독립 검수가 배포본 픽셀로 실측했다: 22행 중 17행만 보이고 «내 정보» 랜드마크가 **통째로**
   * 스크롤 아래로 사라졌다(Before·W2 에서는 접힘 기본이라 4개 그룹 헤더가 전부 보였다).
   * 그 자리를 알리는 유일한 신호는 명도차 2.4% 짜리 그림자이고, 사용자 콘솔에는 대체 수단인
   * 메뉴 필터도 없다. 랜드마크가 있다는 사실 자체를 알 수 없는 상태다.
   *
   * 그래서 뷰포트 상수를 박지 않고 **잰다.** 한 행의 실제 높이 · 그룹 경계 간격 · 목록 여백을
   * 렌더된 DOM 에서 읽어 "전부 펼친 높이"를 계산하고, 목록이 실제로 쓸 수 있는 높이와 비교한다.
   * 접힌 뒤에도 다시 잴 수 있다(접힘 상태의 scrollHeight 를 쓰지 않는다) — 창을 키우면 다시
   * 펼쳐진다. 4K rem 레버·역할별 크롬 높이(관리자는 콘솔 스위치와 필터가 목록 위에 하나 더
   * 있다)·글꼴 확대까지 전부 실측이 흡수한다.
   *
   * `useLayoutEffect` 다 — 브라우저가 그리기 **전에** 판정이 끝나야 펼쳤다 접히는 깜빡임이
   * 없다. 판정 결과는 localStorage 에 쓰지 않는다: 이건 사용자의 선택이 아니라 화면의 형편이고,
   * 기록해 두면 큰 화면으로 옮겨도 접힌 채로 남는다. */
  // 두 측정(펼침 적합성 · 스크롤 그림자)이 같은 목록 요소를 본다.
  const listRef = React.useRef(null);
  const [fitsExpanded, setFitsExpanded] = React.useState(true);
  React.useLayoutEffect(() => {
    const el = listRef.current;
    if (!el || !groupsOpenByDefault) return undefined;
    const measure = () => {
      const row = el.querySelector(".MuiListItemButton-root");
      if (!row) return;
      const rowH = row.getBoundingClientRect().height;
      if (!rowH) return;
      const block = el.firstElementChild;
      const gap = block ? parseFloat(getComputedStyle(block).marginBottom) || 0 : 0;
      const listStyle = getComputedStyle(el);
      const padY = (parseFloat(listStyle.paddingTop) || 0) + (parseFloat(listStyle.paddingBottom) || 0);
      const groupCount = visibleGroups.length;
      const itemCount = visibleGroups.reduce((n, g) => n + g.items.length, 0);
      const needed = (groupCount + itemCount) * rowH + groupCount * gap + padY;
      setFitsExpanded(needed <= el.clientHeight);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [groupsOpenByDefault, visibleGroups]);

  const openByDefault = groupsOpenByDefault && fitsExpanded;
  const isCollapsed = React.useCallback(
    (name) => (collapsed[name] === undefined ? !openByDefault : collapsed[name] === true),
    [collapsed, openByDefault],
  );
  const toggle = (name) => setCollapsed((c) => {
    const wasCollapsed = c[name] === undefined ? !openByDefault : c[name] === true;
    const next = { ...c, [name]: !wasCollapsed };
    try { window.localStorage.setItem(navCollapseKey(userId), JSON.stringify(next)); } catch (e) { /* ignore */ }
    return next;
  });

  /* 활성 라우트가 든 그룹은 접혀 있었어도 강제로 펼쳐 보인다(아래 isOpen). 그런데 그
   * "펼쳐 보임"을 실제로 펼친 것으로 기록해 두지 않으면, 다른 화면으로 넘어가는 순간 예전에
   * 저장된 collapsed:true로 조용히 되돌아간다 — 사용자는 그 그룹을 접은 적이 없는데 다른
   * 곳을 클릭했더니 저절로 접힌 것처럼 보인다(사용자 지적). 사용자가 실제로 편 것처럼
   * collapsed 상태 자체를 false로 갱신해 둔다. */
  /* 조건은 **명시 기록**이다 — `isCollapsed()` 가 아니다.
   *
   * `isCollapsed()` 는 "기록 없음 + 화면이 좁아 자동으로 접힘" 에도 true 를 준다. 그것으로
   * 조건을 걸면 셸의 **화면 형편** 판정이 여기서 사용자 선택(false)으로 저장되고, 저장된
   * 기록은 자동 판정을 영원히 이긴다. 1366x768 에서 네 그룹을 한 번씩만 방문해도
   * `{"내 업무":false,"팀 업무":false,"팀 공간":false,"내 정보":false}` 가 쌓여 자동 접힘이
   * 무력화되고 «랜드마크가 폴드 아래로 사라진다» 가 새로고침에도 살아남는 형태로 되돌아온다
   * (독립 재검증이 배포본에서 그 경로를 실제로 밟았다). 자동으로 접힌 그룹은 활성일 때
   * `groupActive` 가 렌더 시점에 이미 펼쳐 주므로 저장할 것이 애초에 없다. */
  const activeGroup = groups.find((g) => g.items.some((it) => it.to === activePath));
  React.useEffect(() => {
    if (!activeGroup || collapsed[activeGroup.group] !== true) return;
    setCollapsed((c) => {
      if (c[activeGroup.group] !== true) return c;
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
              /* 인디고 하우징 **안**의 입력이다 — 캔버스 토큰(`background.plate`)을 쓰면
                 라이트에서 셸에서 가장 밝은 면이 되고(실측 14.13:1) 다크에서는 셸에 묻힌다
                 (1.12:1). 상단바 검색과 **같은 이유로 같은 토큰**을 쓴다(F-W1R-01·13·32).
                 placeholder 는 MUI 기본 opacity 0.42 를 걷어내고 토큰 잉크를 그대로 쓴다 —
                 알파를 두 번 곱하면 실측해 둔 대비(4.90~6.51)가 무너진다. */
              sx: (t) => ({
                color: t.palette.chrome.onShell, bgcolor: t.palette.chrome.track,
                borderRadius: RADIUS.sm / 8,
                "& fieldset": { borderColor: t.palette.chrome.edge },
                "&:hover fieldset": { borderColor: t.palette.chrome.edge },
                "&.Mui-focused fieldset": { borderColor: t.palette.chrome.focusRing },
                "& input::placeholder": { color: t.palette.chrome.onShellMuted, opacity: 1 },
              }),
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
          /* 좌우 여백 0 — 행이 하우징 **가장자리까지** 간다. 여백을 여기 두면 활성 레일이
             목록 안쪽 12px 에 떠 있는 조각이 되고, 행 채움도 하우징과 사이에 틈을 남긴다.
             안쪽 여백은 행이 `NAV_ROW.px` 로 직접 갖는다. */
          px: 0, py: 1, flex: 1, overflowY: "auto",
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
        const isOpen = filtering || groupActive || !isCollapsed(g.group);
        const GroupIcon = g.icon;
        const itemsId = "nav-group-" + g.group;
        return (
          /* 랜드마크 경계의 공기. 자식 글리프를 걷어내면서 들여쓰기도 함께 사라졌으므로,
             그룹을 가르는 일이 **간격 하나**에 남았다. 4px(행 간격의 10%)로는 22줄이 한
             덩어리 벽으로 읽힌다는 것이 독립 검수 픽셀 실측에서 나왔다(항목↔항목 잉크 간격
             25~27px vs 그룹 경계 29~30px — 차이 12%). 12px 은 경계가 경계로 읽히는 최소치다. */
          <Box key={g.group} sx={{ mb: 1.5 }}>
            <ListItemButton
              onClick={() => toggle(g.group)}
              aria-expanded={isOpen}
              aria-controls={itemsId}
              sx={{ ...NAV_ROW, color: "sidebar.muted" }}
            >
              {GroupIcon ? (
                <ListItemIcon sx={{ minWidth: NAV_GLYPH_SLOT, color: "inherit" }}>
                  <GroupIcon aria-hidden="true" sx={{ fontSize: remPx(ICON.nav) }} />
                </ListItemIcon>
              ) : null}
              <ListItemText
                primary={g.group}
                primaryTypographyProps={{ fontSize: FONT_SIZE.caption, fontWeight: FONT_WEIGHT.semibold, letterSpacing: ".04em" }}
              />
              {/* 펼침 화살표는 **상태**를 말하는 표지다 — 랜드마크 글리프(20)보다 한 단 작은
                  inline(18) 슬롯을 쓴다. 두 그림이 같은 크기면 어느 쪽이 그룹의 정체인지
                  읽히지 않는다. */}
              <ExpandMoreRoundedIcon
                aria-hidden="true"
                sx={{
                  fontSize: remPx(ICON.inline), flexShrink: 0,
                  transform: isOpen ? "none" : "rotate(-90deg)", transition: "transform .18s",
                }}
              />
            </ListItemButton>
            {/* 접혔을 때 통째로 언마운트하면 aria-controls가 없는 노드를 가리키는 무효 참조가
                된다(ARIA disclosure 패턴 위반) — 항상 마운트해 두고 감추기만 한다. */}
            <Collapse in={isOpen} id={itemsId} unmountOnExit={false}>
              {/* 자식 목록에 들여쓰기를 주지 않는다. 깊이는 **그룹의 접힘 상태**가 이미
                  말하고 있고, 들여쓰기로 한 번 더 말하면 라벨이 두 열에서 시작한다
                  (실측 그룹 60px / 자식 64px — F-W1R-18). */}
              <List disablePadding>
                {g.items.map((it) => {
                  const active = it.to === activePath;
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
                        ...NAV_ROW,
                        /* 자식은 글리프를 갖지 않는다(그룹이 가졌다 — PLAN «Icon System»).
                           그 자리를 padding 으로 채워 라벨이 그룹 라벨과 **같은 42px 열**에서
                           시작하게 한다. 값의 정본은 `NAV_ANATOMY` 하나다. */
                        pl: NAV_ANATOMY.labelStart / 8,
                        color: active ? "sidebar.text" : "sidebar.muted",
                        /* 활성 신호는 **정확히 둘**이다 (PLAN «Navigation 상태», 지시 79):
                           위치 = 하우징 가장자리에 붙는 3px 레일, 색 = 행 채움 + 잉크.
                           예전에는 넷이 겹쳤다 — 2px 레일 + `fontWeight 700 vs 600` + 색 +
                           `icon opacity 1 vs .82`. 한글에서 semibold→bold 전환은 글자 폭을
                           실제로 바꿔 항목을 움직이고(레이아웃 흔들림), 흐린 글리프를 더
                           흐리게 하는 것은 가벼워지는 게 아니라 탁해지는 것이다(F-W1R-05).
                           굵기·배경 알약·아이콘 fill 교체는 금지다. */
                        "&::before": {
                          content: '""',
                          position: "absolute",
                          insetBlock: 0,
                          insetInlineStart: 0,
                          width: remPx(NAV_ANATOMY.rail),
                          bgcolor: active ? "sidebar.activeRail" : "transparent",
                        },
                        "&.Mui-selected": { bgcolor: "sidebar.selected" },
                        /* 선택된 행에 hover 를 얹으면 `selected`(.10/.12)보다 옅은
                           `hover`(.06/.08)가 덮어써서 **지금 있는 자리가 흐려진다.** 그대로 둔다. */
                        "&.Mui-selected:hover": { bgcolor: "sidebar.selected" },
                      }}
                    >
                      <ListItemText
                        primary={it.label}
                        primaryTypographyProps={{ fontSize: FONT_SIZE.body, fontWeight: FONT_WEIGHT.medium }}
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
        bgcolor: "sidebar.track", borderRadius: RADIUS.sm / 8,
      }}
    >
      {[{ label: "사용자", on: userSeg, to: "/me" }, { label: "관리자", on: !userSeg, to: "/dashboard" }].map((seg) => (
        <Button
          key={seg.label}
          size="small"
          onClick={() => onNavigate(seg.to)}
          aria-current={seg.on ? "page" : undefined}
          sx={{
            /* rem — 셸의 틀과 같은 배율로 자란다(4K 레버, TopSearch 와 같은 이유). */
            flex: 1, minHeight: "1.75rem", borderRadius: RADIUS.sm / 8, textTransform: "none",
            fontWeight: seg.on ? FONT_WEIGHT.semibold : FONT_WEIGHT.regular,
            /* Shell 이 인디고라 선택 표시를 **반전**으로 만든다. 예전에는 흰 판이 떠올랐는데,
               인디고 하우징 안에서 흰 알약은 화면에서 가장 밝은 면이 되어 데이터보다 먼저
               눈에 띈다. 지금은 트랙보다 밝은 흰빛 알파 + 한 줄 하이라이트다.
               잉크도 함께 뒤집힌다 — 선택은 `onShell`, 비선택은 `onShellMuted`.
               실측 AA: 비선택 4.90~6.51, 선택 6.20~8.10(그라디언트 세 stop 전부). */
            color: seg.on ? "sidebar.text" : "sidebar.muted",
            bgcolor: seg.on ? "sidebar.trackSelected" : "transparent",
            boxShadow: seg.on ? (t) => `inset 0 0 0 1px ${t.palette.sidebar.edge}` : "none",
            "&:hover": { bgcolor: seg.on ? "sidebar.trackSelected" : "sidebar.hover" },
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
    /* chrome 은 **Brand 하우징**이다 — D-179 가 D-141 의 "캔버스 계열 단색" 조항을 대체했다.
       이 파일이 두 번 겪은 실패는 같은 종류다: chrome 의 밝기가 바뀌었는데 그 위 잉크가
       안 따라왔다. 처음에는 딥 인디고 -> 밝은 회색으로 갈 때 흰 글자가 남아 제품명이 1.21 로
       사라졌고, 이번에는 반대 방향에서 Canvas 용 워드마크 잉크가 2.32 로 무너졌다(독립
       리뷰어가 배포본 픽셀에서 잡았다). 그래서 잉크는 전부 `sidebar.*`(= `chrome.*`) 에서
       오고, 면에 종속된 값(포커스 링·워드마크)은 이 컨테이너가 CSS 변수로 덮어 상속시킨다.
       색은 팔레트에서 온다. tokens.css 는 같은 theme.js 에서 생성되므로 두 소스가 갈라지지
       않는다(scripts/generate_design_tokens.mjs). */
    <Box
      sx={{
        display: "flex", flexDirection: "column", height: "100%",
        /* 단색은 **바닥**이다(폰트·이미지가 늦게 와도 셸이 흰 채로 번쩍이지 않는다).
           그 위에 `chrome.shellImage` 를 얹어 레일을 하나의 물체로 만든다 — 아래로 갈수록
           어두워져 하단(보조 항목)이 상단 주요 항목과 채도로 경쟁하지 않는다(PLAN
           «Gradient 정책»). W1 은 토큰만 만들고 소비처가 0이라 셸이 평평했다(F-W1R-39).
           Gradient 리터럴을 여기 적지 않는 이유: `check_brand_tokens.py` 가 `app/**` 의 raw
           gradient 를 금지한다 — 색이 테마 밖에 있으면 대비 시험이 그 색을 아예 모른다. */
        bgcolor: "sidebar.bg", color: "sidebar.text",
        backgroundImage: (t) => t.palette.chrome.shellImage,
        /* 하우징의 **바깥 모서리**다. 상단바 아래 가로 이음매와 같은 재료·같은 색이어야
           L 이 한 물체로 마감된다.
           `borderInlineEnd: 1` 로는 **안 그려진다** — MUI 의 border 스타일 함수
           (`@mui/system` borders.js)가 펴 주는 이름은 `border`/`borderTop|Right|Bottom|Left`
           뿐이라 논리 속성 shorthand 는 그대로 통과하고, `border-inline-end: 1` 은 style 이
           없어 무효 CSS 다. 배포본 실측으로 확인했다: 1920 light y=400 에서 x=247 (34,43,96)
           → x=248 (238,240,247) 로 **선 없이** 캔버스로 넘어간다. 같은 함정을 팔레트 선택
           레일에서도 밟았다(CommandPalette.jsx). 그래서 세 속성을 따로 적는다. */
        borderInlineEndStyle: "solid",
        borderInlineEndWidth: "1px",
        borderInlineEndColor: (t) => t.palette.chrome.line,
        /* AppBar 와 같은 이유 — Shell 안의 포커스 링과 워드마크는 Shell 용이다. */
        "--clovir-focus-ring": (t) => t.palette.chrome.focusRing,
        "--clovir-wordmark": (t) => t.palette.chrome.wordmark,
      }}
    >
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
          {/* 두 축 모두 **지금 어느 콘솔인가**로 정한다. `isUser`(역할)로 정하면 관리자가
              사용자 세그먼트에 들어갔을 때 20항목짜리 사용자 트리 위에 관리자용 메뉴 필터가
              뜬다 — 같은 축 혼동을 알림 종에서 이미 한 번 겪었다(F-W2E-01).
              `homeUser = isUser || userSeg` 가 바로 위 `nav` 를 고른 그 값이다. */}
          <SidebarNav
            groups={groups}
            activePath={activePath}
            onNavigate={onCloseNav}
            userId={userId}
            showFilter={!homeUser}
            groupsOpenByDefault={Boolean(homeUser)}
          />
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
            /* 이 링크는 포커스됐을 때 상단바(인디고) 위에 뜬다 — 링도 Shell 용이어야 한다.
               MUI 컴포넌트가 아니라 `component="a"` 라 예전에는 UA 기본 외곽선(#101010)을
               썼다. 이제 `:focus-visible` 전역 규칙이 이 변수를 읽는다. */
            "--clovir-focus-ring": (t) => t.palette.chrome.focusRing,
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
          /* 상단바와 사이드바는 **같은 재료**다(D-179). 옛 결정("chrome 은 발광하지 않는다",
             D-141)은 chrome 을 캔버스 계열 무채색으로 두었고, 그 상태가 Before 측정에서
             `brand_presence` 1,494장 중 1,452장 실패로 나타났다 — 통과한 42장은 전부 로그인
             화면이었다.
             W1 은 여기를 flat `chrome.shell`(#1E2758)로 두었는데, 바로 아래 사이드바는
             Gradient 의 **첫 stop `chrome.shellTop`(#28336F)** 에서 시작한다. 즉 W1 상태는
             두 층이 만나는 모서리에서 한 stop 어긋나 있었고, Gradient 3종은 소비처가 0이라
             셸이 통째로 평평했다(F-W1R-39). PLAN «Chrome 설계» 의 문장이 이유를 그대로
             말한다 — "만나는 모서리가 같은 색인 이유는 Top bar 의 채움이 Sidebar Gradient 의
             첫 stop 이기 때문이다". `theme-contract.test.js` 가 그 항등식을 이미 단언하고
             있고(stopsOf(shellImage)[0] === shellTop), 이제 제품이 그 토큰을 실제로 읽는다. */
          background: t.palette.chrome.shellTop,
          color: t.palette.chrome.onShell,
          /* Shell 위에서는 포커스 링도 Shell 용이다. Canvas 용 링은 인디고 위에서 light 기준
             1.38~1.83:1 로 사실상 보이지 않는다(실측) — 상속되는 변수 하나로 이 안의 모든
             후손이 `chrome.focusRing`(9.15:1)을 쓴다. 워드마크도 같다 — Canvas 용 잉크는
             인디고 위에서 2.32:1 이다. */
          "--clovir-focus-ring": t.palette.chrome.focusRing,
          "--clovir-wordmark": t.palette.chrome.wordmark,
          /* 아래 실선은 **chrome 과 캔버스의 경계**다. 그런데 상단바는 전폭이라 예전
             `borderBottom` 은 사이드바 열 위에도 그어졌다 — 그 구간의 아래는 캔버스가 아니라
             chrome 이므로, 그 선이 하우징을 한가운데서 잘라 L 이 두 조각으로 보였다
             (w1-after light/user_me.png y=52 에 전폭 실선. 사이드바가 열로 서 있을 때만
             해당하므로 서랍(좁은 화면)과 셸 없는 화면에서는 전폭 그대로 긋는다). */
          borderBottom: 0,
        })}
      >
        {/* disableGutters — MUI Toolbar 기본 좌우 패딩(24px)이 남으면 로고 칸이
            사이드바 폭에서 그만큼 밀려 두 층의 경계가 어긋난다. `pl:0` 으로는
            안 되고(gutters 가 브레이크포인트별로 다시 넣는다) 아예 꺼야 한다.
            왼쪽 여백은 로고 칸이 자기 안에서 주고, 오른쪽만 여기서 준다. */}
        {/* 좁은 화면에는 사이드바 열 자체가 없으므로 왼쪽 여백을 여기서 준다 — `disableGutters`
            는 **로고 칸을 사이드바 폭에 맞추기 위한** 것이고, 그 열이 없는 폭에서는 목적이
            사라진다. 그 상태로 두면 햄버거가 화면 왼쪽 끝(x=0)에 잘려 붙는다(390 실측:
            잉크가 x=0 부터 시작해 왼쪽 둥근 끝이 사각으로 잘린다). */}
        <Toolbar disableGutters sx={{ minHeight: APPBAR_HEIGHT, gap: 1, pr: 0, pl: isNarrow ? 1 : 0 }}>
          {showMenu && isNarrow ? (
            <IconButton
              onClick={onToggleNav}
              aria-label={navOpen ? "메뉴 닫기" : "메뉴 열기"}
              aria-expanded={navOpen}
              aria-controls="app-sidebar"
              color="inherit"
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

          {/* 검색은 브랜드 칸과 AI 앵커 **사이의 가운데**에 놓는다 (지시 13 «Global Search 와
              사용자 영역과의 균형»). 예전에는 브랜드 바로 뒤에 붙고 오른쪽이 통째로 비어
              (실측: 1920 에서 573px, 2560 에서 1,062px, 3840 에서 2,188px), 상단바가 왼쪽으로
              쏠린 채 남는 폭을 아무도 회수하지 않았다. 양쪽 신축 스페이서가 그 폭을 반씩
              나눠 가지면 검색이 실제 사용 폭의 가운데에 서고, 오른쪽 컨트롤은 여전히 화면
              끝에 붙는다(사용자 지적 Q3 유지). */}
          <Box sx={{ flex: 1 }} />
          {!minimal ? <TopSearch onOpen={() => setPaletteOpen(true)} /> : null}
          <Box sx={{ flex: 1 }} />

          {!minimal ? (
            /* ── AI 앵커 ────────────────────────────────────────────────────────
               chrome 에서 **보라가 나타나는 유일한 자리**다. PLAN «Chrome 설계» 가 이 자리를
               `chrome.aiWash` 로 규정하고 그 안에 사는 것을 "Clovi·종·아바타" 로 명시한다.

               상단바 **전체**에 깔지 않는 이유는 취향이 아니라 숫자다: AI Wash 를 합성하면
               `onShellMuted` 가 dark 에서 4.36:1 로 AA 아래로 내려간다(theme.js §CHROME 실측).
               워시를 전폭으로 깔면 검색 inset 의 muted 잉크가 그 영역 안으로 들어간다.
               그래서 워시는 **경계가 있는 요소**로 두고, 그 안의 잉크는 전부 `onShell` 로
               고정한다(D-179 «Wash 위 잉크 하드 룰»). 라디얼(`120% 200% at 100% 0%`)은 상자
               폭의 72% 지점에서 이미 transparent 라 왼쪽 모서리에 경계가 보이지 않는다.

               오른쪽 여백을 Toolbar 대신 여기서 주는 이유: 워시의 앵커가 `at 100% 0%` 라
               상자가 화면 오른쪽 끝까지 닿아야 앵커가 화면 모서리에 앉는다. */
            <Box
              data-shell-region="ai"
              sx={(t) => ({
                display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 1,
                alignSelf: "stretch", pl: 2.5, pr: 2.5,
                /* 워시의 기하가 **상자 폭에 종속**이다: `120% 200% at 100% 0%` 는 오른쪽
                   끝에서 상자 폭의 72% 지점까지만 살아 있고 나머지 28% 는 완전히 투명하다.
                   컨트롤 묶음만 감싸면(실측 313px) 그 죽은 구간이 정확히 **클로비 알약 위**에
                   떨어져서(1625~1705), 보라가 AI 가 아니라 계정을 칠했다 — 독립 검수자가
                   ΔE=0 으로 잡았다. 그래서 상자에 최소 폭을 줘 워시가 묶음 전체를 덮게 한다.
                   26rem 은 임의값이 아니라 계산값이다: 1920 에서 26rem=416px → 워시가
                   x=1920−0.72×416=1620 까지 닿아 알약(1627~)을 덮고, 검색 오른쪽 끝(1286)
                   에는 닿지 않아 D-181 의 잉크 규칙이 유지된다. rem 이라 4K 에서 함께 자란다.
                   좁은 화면에서는 상자가 뷰포트를 넘으므로 최소 폭을 풀어 준다. */
                minWidth: { xs: 0, md: "26rem" },
                color: t.palette.chrome.onShell,
                backgroundImage: t.palette.chrome.aiWash,
              })}
            >
              {/* 넓은 화면에서는 위 검색 막대가 그 일을 하므로 아이콘은 좁은 화면에만 둔다.
                  경계는 **셸 자신의 것**(`isNarrow` = NAV_BREAKPOINT)이다 — 예전에는 여기가
                  md(900), 검색 막대가 720 이라 그 사이 폭에서 같은 기능이 두 번 보였다. */}
              {isNarrow ? (
                <Tooltip title="통합 검색 (Ctrl+K)">
                  <IconButton onClick={() => setPaletteOpen(true)} aria-label="통합 검색 열기"
                    color="inherit">
                    <SearchRoundedIcon />
                  </IconButton>
                </Tooltip>
              ) : null}
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

              {/* 사용자/관리자 전환은 **사이드바 최상단**으로 옮겼다(P2). 여기 두 벌을 두면
                  같은 스위치가 화면에 두 번 나온다. 좁은 화면에서는 사이드바가 서랍으로 접히지만,
                  그때는 메뉴를 여는 것이 곧 트리를 보는 것이라 스위치도 함께 나온다. */}

              {/* 지시 1: 사용자 알림의 단일 진입점은 이 종 하나다. 예전에는 헤더 상태 칩과
                  본문 위 CRITICAL 띠가 따로 있었다. 지시 67 에 따라 정보를 없앤 것이 아니라
                  옮긴 것이다 — 운영자용 서비스 Health 는 관리자 대시보드·진단이 계속 보여 준다. */}
              <NotificationBell isUser={isUser} notices={statusNotices} />
              <UserMenu
                name={name} userId={userId} avatarUrl={avatarUrl}
                // 내 소속·관리 범위(0060 §5) — 셸이 이미 들고 있는 값을 넘긴다.
                me={auth.data && (auth.data.user || auth.data)}
              />
            </Box>
          ) : null}
        </Toolbar>

        {/* chrome 과 캔버스의 경계선. 위 주석대로 사이드바 열 **다음**에서 시작한다.
            의사요소가 아니라 실제 요소인 이유는 폭이 반응형 객체(DRAWER_WIDTH)이기
            때문이다 — sx 의 중첩 선택자 안에서 브레이크포인트 객체가 해석되는지에
            의존하지 않는다. 장식이라 낭독 대상이 아니고 포인터도 통과시킨다. */}
        <Box
          aria-hidden="true"
          data-testid="shell-seam"
          sx={{
            position: "absolute", bottom: 0, insetInlineEnd: 0, height: "1px",
            insetInlineStart: showMenu && !isNarrow ? DRAWER_WIDTH : 0,
            bgcolor: "chrome.line", pointerEvents: "none",
          }}
        />
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
          /* 상단바가 `position:fixed` 라 본문은 그 높이만큼 스스로 내려와야 한다. 값을
             **px 로** 준다 — 예전에는 `pt: APPBAR_HEIGHT.xs / 8`(spacing 단위)이었는데,
             이 저장소의 spacing 은 rem 이고(theme.js) 루트 폰트사이즈는 2200/3000 에서
             16→18→20 으로 커진다. 반면 Toolbar 의 `minHeight` 는 px 다. 두 축이 서로 다른
             단위를 타면서 **넓은 화면에서만 어긋났다**: 실측 2560 에서 7.5px, 3840 에서
             17px 의 죽은 띠가 상단바 바로 아래에 생긴다(52 는 우연히 맞았다 — 루트가
             16px 라 3.25rem = 52px). R-6 이 말하는 "해상도 변화에 따라 화면이 어긋난다"의
             교과서적 사례라 여기서 단위를 하나로 통일한다. */
          pt: `${APPBAR_HEIGHT.xs}px`, outline: "none",
          /* 경계값도 리터럴로 적지 않는다 — `styles/root.css` 의 4K 레버와 이 오프셋이 서로
             다른 숫자를 들고 있으면 한쪽만 바뀔 때 D-182 가 방금 고친 어긋남이 되돌아온다.
             (`root-scale-lever.test.js` 가 root.css 의 두 경계도 같은 값인지 단언한다.) */
          [`@media (min-width:${BREAKPOINTS.xxl}px)`]: { pt: `${APPBAR_HEIGHT.xxl}px` },
          [`@media (min-width:${BREAKPOINTS.uhd}px)`]: { pt: `${APPBAR_HEIGHT.uhd}px` },
        }}
      >
        {/* 배너는 본문 폭 캡 밖에 있어야 한다 — 안쪽에 두면 4K 에서 화면 가운데만 띠가 뜨고
            양옆이 비어, "전역 공지"가 한 열짜리 카드처럼 보인다. 세션 만료(minimal) 상태에는
            띄우지 않는다: 그때 필요한 유일한 행동은 재로그인이고, 배너 API 도 401 이다. */}
        {!minimal ? <Banners /> : null}
        {/* 스코프 바 — 배너 **아래**, 본문 폭 캡 **안**이다. 배너는 전역 공지라 화면 폭
            전체를 쓰지만 이건 "이 목록이 왜 이만큼인가" 를 설명하는 줄이라 목록과 같은
            폭이어야 붙어 읽힌다. 전체 범위인 사람에게는 아무것도 그리지 않는다. */}
        {/* 본문 열. `c-content` 는 장식용 class 가 아니라 **측정 지점**이다 — `narrow_main`
            프로브(scripts/ui_qa/assertions.py)가 `#main-content` 안에서 이 이름을 찾아
            "사용자가 읽는 열" 의 폭을 잰다. 이름이 없던 동안에는 그 프로브가 열을 못 찾고
            보이는 상자들의 합집합으로 되짚었다(그 주석이 "the MUI shell caps a class-less
            <Box>" 라고 적어 둔 상태가 이것이다). 폭 캡을 소유한 층이 자기 이름을 대는 것이
            측정 가능한 계약이다. */}
        <Box
          className="c-content"
          sx={{
            width: "100%", maxWidth: CONTENT_MAX_WIDTH, mx: "auto",
            px: { xs: 2, sm: 3, xl: 4 }, py: { xs: 2.5, sm: 3.5 },
            // PA-RC-0020: 우하단 FAB을 없애 본문 위에 뜬 컨트롤이 더는 없다 — FAB
            // 자리를 비워 두던 큰 하단 여백(md:14)도 함께 걷어낸다.
            pb: { xs: 3, md: 4 },
          }}
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
