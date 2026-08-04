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
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { alpha, useTheme } from "@mui/material/styles";
import MenuRoundedIcon from "@mui/icons-material/MenuRounded";
import CloseRoundedIcon from "@mui/icons-material/CloseRounded";
import SearchRoundedIcon from "@mui/icons-material/SearchRounded";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api.js";
import { useAuth } from "./auth.jsx";
import { NotificationBell } from "./NotificationBell.jsx";
import { UserMenu } from "./UserMenu.jsx";
import { CommandPalette, useCommandPaletteHotkey } from "./CommandPalette.jsx";
import { Tour } from "./Tour.jsx";
import { bestNavMatch, NAV_BREAKPOINT_PX } from "./navConfig.js";
import BrandLogo from "../ui/BrandLogo.jsx";
import { MascotButton, MascotSidebarCard, MascotTopButton } from "../ui/Mascot.jsx";
import { useDocumentTitle } from "./documentTitle.js";
import { navIcon } from "./navIcons.js";
import { Card, ErrorState, Skeleton } from "../ui/kit.jsx";
import { Banners } from "./Banners.jsx";
import { CONTENT_MAX_WIDTH } from "../ui/theme.js";

/* 앱 셸 — 상단바 + 사이드바 + 본문.
 *
 * 사이드바 폭과 상단바 높이는 화면이 커지면 같이 커진다. 4K에서 고정 284px 사이드바는
 * 화면의 7%밖에 안 돼 메뉴가 실처럼 가늘어 보인다.
 */
/* 기준 파일의 --sidebar-w 는 264px 다(예전 값 284는 초안 단계에서 온 것). */
const DRAWER_WIDTH = { xs: 264, xxl: 300, uhd: 340 };
const APPBAR_HEIGHT = { xs: 64, xxl: 72, uhd: 80 };

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
 * 채팅방 화면에 있을 때는 5초, 다른 화면에서는 여기 30초로 돈다 — 사이드바 배지 하나
 * 때문에 앱 전체가 5초 폴링을 하지는 않는다.
 */
function useNavBadges() {
  const q = useQuery({
    queryKey: ["team-chat-rooms"],
    queryFn: () => api("/api/team-chat/rooms"),
    refetchInterval: 30000,
    // 배지는 없어도 되는 정보다. 실패하면 조용히 0으로 두고 재시도로 소란 피우지 않는다.
    retry: false,
    staleTime: 10000,
  });
  return { chatUnread: (q.data && q.data.unread_total) || 0 };
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
        fontSize: "0.6875rem", fontWeight: 800, lineHeight: 1,
        bgcolor: "error.main", color: "common.white",
      }}
    >
      {count > 99 ? "99+" : count}
    </Box>
  );
}

function SidebarNav({ groups, activePath, onNavigate, userId }) {
  const badges = useNavBadges();
  const [collapsed, setCollapsed] = React.useState(() => getStoredCollapsed(userId));
  const toggle = (name) => setCollapsed((c) => {
    const next = { ...c, [name]: !c[name] };
    try { window.localStorage.setItem(navCollapseKey(userId), JSON.stringify(next)); } catch (e) { /* ignore */ }
    return next;
  });

  return (
    <List component="nav" sx={{ px: 1.5, py: 1, flex: 1, overflowY: "auto" }}>
      {groups.map((g) => {
        const groupActive = g.items.some((it) => it.to === activePath);
        // 현재 위치가 든 그룹은 사용자가 접어 뒀어도 항상 펼친다 — 알림 딥링크나 직접 해시로
        // 접힌 그룹 안의 경로에 도착했을 때 '여기 있음' 항목이 숨으면 길을 잃는다.
        const isOpen = !collapsed[g.group] || groupActive;
        const GroupIcon = g.icon;
        const itemsId = "nav-group-" + g.group;
        return (
          <Box key={g.group} sx={{ mb: 0.5 }}>
            <ListItemButton
              onClick={() => toggle(g.group)}
              aria-expanded={isOpen}
              aria-controls={itemsId}
              sx={{ borderRadius: 2, py: 1, color: "rgba(237,240,255,.72)" }}
            >
              {GroupIcon ? (
                <ListItemIcon sx={{ minWidth: 32, color: "inherit" }}><GroupIcon fontSize="small" /></ListItemIcon>
              ) : null}
              <ListItemText
                primary={g.group}
                primaryTypographyProps={{ fontSize: "0.75rem", fontWeight: 800, letterSpacing: ".04em" }}
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
                      component={Link}
                      to={it.to}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      selected={active}
                      sx={{
                        borderRadius: 2, minHeight: 42, py: 0.5, pl: 1.5,
                        color: active ? "common.white" : "rgba(237,240,255,.78)",
                        /* 활성 항목은 기준 파일의 .nav-item.is-active 와 같은 처리 —
                           단색 배경이 아니라 왼쪽에서 흐르는 그라데이션 + 안쪽 링이다. */
                        "&.Mui-selected": {
                          background: "linear-gradient(90deg, rgba(117,138,225,.34), rgba(142,117,225,.14))",
                          boxShadow: "inset 0 0 0 1px rgba(173,185,255,.2)",
                        },
                        "&.Mui-selected:hover": {
                          background: "linear-gradient(90deg, rgba(117,138,225,.44), rgba(142,117,225,.2))",
                        },
                        "&:hover": { bgcolor: "rgba(255,255,255,.08)" },
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
                        primaryTypographyProps={{ fontSize: "0.875rem", fontWeight: active ? 750 : 600 }}
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
  );
}

export function AppShell({
  nav, ariaLabel, navOpen, onCloseNav, onToggleNav,
  isUser, userSeg, minimal, showMenu, children,
}) {
  const theme = useTheme();
  const auth = useAuth();
  const loc = useLocation();
  const navigate = useNavigate();
  // 탭 제목을 화면마다 다르게 — 정적 <title> 하나뿐이라 어느 탭이 무엇인지 구분이 안 됐다.
  useDocumentTitle(loc.pathname);
  const role = auth.data && auth.data.role;
  const userId = auth.data && auth.data.id;
  const name = (auth.data && auth.data.display_name) || "";
  // 프로필 사진은 /api/me 가 함께 준다 — 상단바 아바타 하나 때문에 별도 요청을 하지 않는다.
  const avatarUrl = (auth.data && auth.data.avatar_url) || null;
  const isNarrow = useMediaQuery(`(max-width:${NAV_BREAKPOINT_PX}px)`);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  useCommandPaletteHotkey(setPaletteOpen);

  // 권한 없는 메뉴는 숨긴다. 팔레트도 같은 목록을 쓴다 — 검색 결과로 403에 빠지면 안 된다.
  const groups = React.useMemo(
    () => (nav || [])
      .map((g) => ({ ...g, items: g.items.filter((it) => !it.roles || (role && it.roles.includes(role))) }))
      .filter((g) => g.items.length),
    [nav, role]
  );
  const activePath = bestNavMatch(loc.pathname, groups.flatMap((g) => g.items.map((it) => it.to)));

  // AI 도우미(/chat)만 자체 2단 레이아웃이라 폭 캡·패딩을 없앤다.
  // /chat-rooms(팀 채팅방)는 일반 레이아웃이므로 정확히 /chat 일 때만.
  const flush = loc.pathname === "/chat";
  const homeUser = isUser || userSeg;

  const drawerContent = (
    /* 기준 파일의 .sidebar 는 단색이 아니라 위에서 아래로 어두워지는 그라데이션이다 —
       상단바(딥 인디고)와 이어지고 아래로 갈수록 가라앉아 목록이 길어도 답답하지 않다. */
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", background: "linear-gradient(180deg, #111936 0%, #0A1026 100%)", color: "common.white" }}>
      <Toolbar sx={{ minHeight: APPBAR_HEIGHT, px: 2.5, gap: 1.5 }}>
        <BrandLogo markOnly width={30} />
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: "0.9375rem", fontWeight: 800, lineHeight: 1.1 }}>ClovirAssist</Typography>
          <Typography sx={{ fontSize: "0.75rem", color: "rgba(237,240,255,.62)" }}>Smart Workspace Assistant</Typography>
        </Box>
        {isNarrow ? (
          <IconButton onClick={onCloseNav} aria-label="메뉴 닫기" sx={{ ml: "auto", color: "inherit" }}>
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
          <Typography variant="body2" sx={{ color: "rgba(237,240,255,.8)" }}>세션이 만료되었습니다.</Typography>
          <Button variant="contained" href="/login">다시 로그인</Button>
        </Box>
      ) : (
        <>
          <SidebarNav groups={groups} activePath={activePath} onNavigate={onCloseNav} userId={userId} />
          <Box sx={{ pb: 3 }}>
            <MascotSidebarCard onClick={() => { onCloseNav(); navigate("/chat"); }} />
          </Box>
        </>
      )}
    </Box>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100dvh", bgcolor: "background.default" }}>
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
            fontWeight: 700, textDecoration: "none",
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
        sx={{
          zIndex: (t) => t.zIndex.drawer + 1,
          /* 기준 파일의 최종 상단바. 예전 값(105deg, primary.dark → #327C98 → #765FC7)은
             초안 단계의 것이라 전체적으로 밝고 청록이 강했다. 최종안은 딥 인디고에서
             브랜드 파랑으로 흐르고, 오른쪽 위 바깥에서 보라 빛무리가 내려앉는다. */
          background:
            "radial-gradient(circle at 78% -120%, rgba(142,117,225,.74), transparent 44%)," +
            " linear-gradient(112deg, #17204D 0%, #293B8D 48%, #536CD6 100%)",
        }}
      >
        <Toolbar sx={{ minHeight: APPBAR_HEIGHT, gap: 1 }}>
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
              홈 대신 유일한 실제 CTA인 로그인으로 보낸다(죽은 컨트롤 방지). */}
          <Button
            onClick={() => { if (minimal) { window.location.href = "/login"; } else { navigate(homeUser ? "/me" : "/dashboard"); } }}
            aria-label={minimal ? "로그인 화면으로" : "홈으로"}
            color="inherit"
            sx={{ gap: 1.5, textTransform: "none", px: 1 }}
          >
            <Box sx={{ bgcolor: "common.white", borderRadius: 1.5, p: 0.25, display: "grid", placeItems: "center" }}>
              <BrandLogo markOnly width={26} />
            </Box>
            <Box component="span" sx={{ display: { xs: "none", sm: "inline" }, fontWeight: 800, fontSize: "0.9375rem" }}>
              ClovirAssist
            </Box>
          </Button>

          {/* 기준 파일의 상단바 검색(.top-search) — flex:1, max-width 720. 아이콘 버튼 하나만
              두면 '검색이 있다'는 사실 자체가 안 보인다(§2 "검색 영역도 기준에 맞게").
              누르면 Ctrl+K 팔레트를 연다 — 입력을 여기서 직접 받지 않는 이유는, 결과 목록이
              뜰 자리가 상단바에는 없고 팔레트가 이미 그 일(키보드 이동, 그룹, 최근 항목)을
              하기 때문이다. 되는 척하는 컨트롤이 아니라 **같은 기능의 더 큰 표적**이다.
              좁은 화면에서는 자리를 차지하지 않게 돋보기 아이콘으로 접힌다. */}
          {!minimal ? (
            <Box
              component="button"
              type="button"
              onClick={() => setPaletteOpen(true)}
              aria-label="통합 검색 열기"
              sx={{
                display: { xs: "none", md: "flex" }, alignItems: "center", gap: 1.25,
                flex: 1, maxWidth: "45rem", mx: 2, height: 40, px: 1.75,
                border: 1, borderColor: "rgba(255,255,255,.26)", borderRadius: "12px",
                background: "rgba(10,18,42,.22)", color: "rgba(255,255,255,.86)",
                cursor: "text", textAlign: "left", font: "inherit",
                "&:hover": { borderColor: "rgba(255,255,255,.45)" },
                "&:focus-visible": { outline: "2px solid #fff", outlineOffset: 2 },
              }}
            >
              <SearchRoundedIcon fontSize="small" aria-hidden="true" />
              <Box component="span" sx={{ flex: 1, fontSize: "0.875rem", minWidth: 0 }}>
                티켓, 문서, 게시판, 사용자 검색
              </Box>
              <Box component="kbd" sx={{
                flexShrink: 0, fontSize: "0.6875rem", fontWeight: 700, letterSpacing: ".02em",
                border: 1, borderColor: "rgba(255,255,255,.3)", borderRadius: 1,
                px: 0.75, py: 0.125, fontFamily: "inherit",
              }}>Ctrl K</Box>
            </Box>
          ) : null}

          <Box sx={{ flex: minimal ? 1 : "0 0 auto" }} />

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
                  숨는데, 그 아래 폭에서 AI 도우미로 가는 길이 아이콘 하나뿐이었다. */}
              <MascotTopButton onClick={() => navigate("/chat")} />
            </>
          ) : null}

          {!isUser && !minimal ? (
            <Box role="group" aria-label="화면 전환" sx={{ display: "flex", bgcolor: "rgba(255,255,255,.16)", borderRadius: 999, p: 0.5, mx: 1 }}>
              {[{ label: "사용자", on: userSeg, to: "/me" }, { label: "관리자", on: !userSeg, to: "/dashboard" }].map((s) => (
                <Button
                  key={s.label}
                  size="small"
                  onClick={() => navigate(s.to)}
                  aria-current={s.on ? "page" : undefined}
                  sx={{
                    minHeight: 30, px: 2, borderRadius: 999, textTransform: "none", fontWeight: 750,
                    color: s.on ? "primary.dark" : "common.white",
                    bgcolor: s.on ? "common.white" : "transparent",
                    "&:hover": { bgcolor: s.on ? "common.white" : "rgba(255,255,255,.12)" },
                  }}
                >
                  {s.label}
                </Button>
              ))}
            </Box>
          ) : null}

          {!minimal ? <NotificationBell isUser={isUser} /> : null}
          {!minimal ? <UserMenu name={name} userId={userId} avatarUrl={avatarUrl} /> : null}
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
                bgcolor: "#1B2447",
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
        <Box
          sx={
            flush
              ? { flex: 1, minHeight: 0, display: "flex" }
              : {
                  width: "100%", maxWidth: CONTENT_MAX_WIDTH, mx: "auto",
                  px: { xs: 2, sm: 3, xl: 4 }, py: { xs: 2.5, sm: 3.5 },
                  /* 우하단 마스코트 버튼이 본문 위에 떠 있다(70px + 여백 24px ≈ 94px).
                     아래 여백이 그보다 작으면 화면 맨 아래에 붙는 컨트롤을 가린다 —
                     실제로 놀이방의 '보내기' 버튼을 덮었다. 버튼이 보이는 md 이상에서만 넉넉히. */
                  pb: { xs: 5, md: 14 },
                }
          }
        >
          {auth.isLoading ? <Card><Skeleton /></Card> : children}
        </Box>
      </Box>

      {/* 우하단 플로팅 마스코트 — AI 도우미로 가는 상시 입구. 실제 대화 패널은 /chat 화면이다.
          pointerEvents:none — 이 래퍼는 **자리를 잡을 뿐 눌리는 물건이 아니다.** 안쪽 FAB은
          borderRadius가 커서 네 모서리가 시각적으로 비어 있는데, 사각형인 이 래퍼는 그 빈
          모서리에서도 클릭을 가로챈다. 실제로 권한 매트릭스 표 맨 아랫줄의 '상세' 버튼이
          아무것도 안 그려진 지점(1837,987)에서 눌리지 않았다(QA fab_overlap 검사가 잡았다).
          받는 쪽은 MascotButton 안의 Fab이 pointerEvents:auto로 되돌린다. */}
      {/* /chat 에서는 띄우지 않는다(flush 가 곧 '지금 /chat'이다). 이 버튼이 하는 일은
          /chat 으로 가는 것뿐이라, 그 화면에서는 아무 일도 하지 않으면서 입력창 오른쪽의
          '전송'을 덮는다 — QA fab_overlap 검사가 1920 라이트·다크에서 잡았고, 실제로
          스크롤로도 비켜낼 수 없다(입력창이 화면 아래에 고정돼 있다).
          동작하지 않는 컨트롤을 띄워 두지 않는다는 저장소 원칙과도 같은 방향이다. */}
      {!minimal && !flush ? (
        <Box sx={{ position: "fixed", right: 24, bottom: 24, pointerEvents: "none",
                   zIndex: (t) => t.zIndex.speedDial }}>
          <MascotButton onClick={() => navigate("/chat")} mode="listening" />
        </Box>
      ) : null}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} groups={groups} />

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
