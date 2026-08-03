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
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import { NotificationBell } from "./NotificationBell.jsx";
import { UserMenu } from "./UserMenu.jsx";
import { CommandPalette, useCommandPaletteHotkey } from "./CommandPalette.jsx";
import { bestNavMatch, NAV_BREAKPOINT_PX } from "./navConfig.js";
import BrandLogo from "../ui/BrandLogo.jsx";
import { MascotButton, MascotSidebarCard } from "../ui/Mascot.jsx";
import { Card, ErrorState, Skeleton } from "../ui/kit.jsx";
import { CONTENT_MAX_WIDTH } from "../ui/theme.js";

/* 앱 셸 — 상단바 + 사이드바 + 본문.
 *
 * 사이드바 폭과 상단바 높이는 화면이 커지면 같이 커진다. 4K에서 고정 284px 사이드바는
 * 화면의 7%밖에 안 돼 메뉴가 실처럼 가늘어 보인다.
 */
const DRAWER_WIDTH = { xs: 284, xxl: 320, uhd: 360 };
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

function SidebarNav({ groups, activePath, onNavigate, userId }) {
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
                  return (
                    <ListItemButton
                      key={it.to}
                      component={Link}
                      to={it.to}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      selected={active}
                      sx={{
                        borderRadius: 2, minHeight: 40, py: 0.5, pl: 2.5,
                        color: active ? "common.white" : "rgba(237,240,255,.78)",
                        "&.Mui-selected": { bgcolor: "rgba(255,255,255,.14)" },
                        "&.Mui-selected:hover": { bgcolor: "rgba(255,255,255,.2)" },
                        "&:hover": { bgcolor: "rgba(255,255,255,.08)" },
                      }}
                    >
                      <ListItemText
                        primary={it.label}
                        primaryTypographyProps={{ fontSize: "0.875rem", fontWeight: active ? 750 : 600 }}
                      />
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
  const role = auth.data && auth.data.role;
  const userId = auth.data && auth.data.id;
  const name = (auth.data && auth.data.display_name) || "";
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
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#1B2447", color: "common.white" }}>
      <Toolbar sx={{ minHeight: APPBAR_HEIGHT, px: 2.5, gap: 1.5 }}>
        <BrandLogo markOnly width={30} />
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: "0.9375rem", fontWeight: 800, lineHeight: 1.1 }}>ClovirONE</Typography>
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
          background: `linear-gradient(105deg, ${theme.palette.primary.dark}, #327C98 62%, #765FC7)`,
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
              ClovirONE
            </Box>
          </Button>

          <Box sx={{ flex: 1 }} />

          {!minimal ? (
            <>
              {/* 라벨이 '메뉴 검색'인 이유는 v1이 실제로 메뉴만 찾기 때문이다.
                  티켓·문서·사람을 가로지르는 통합 검색은 백엔드 인덱스가 준비된 뒤 같은 자리에 붙는다. */}
              <Tooltip title="메뉴 검색 (Ctrl+K)">
                <IconButton onClick={() => setPaletteOpen(true)} aria-label="메뉴 검색 열기" color="inherit">
                  <SearchRoundedIcon />
                </IconButton>
              </Tooltip>
              {/* 좁은 화면에서는 우하단 마스코트 버튼이 본문을 가려서 숨긴다 —
                  AI 도우미로 가는 길이 사라지지 않게 상단바에 같은 목적지를 둔다. */}
              <Tooltip title="AI 도우미">
                <IconButton
                  onClick={() => navigate("/chat")}
                  aria-label="AI 도우미 열기"
                  color="inherit"
                  sx={{ display: { xs: "inline-flex", md: "none" } }}
                >
                  <SmartToyOutlinedIcon />
                </IconButton>
              </Tooltip>
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
          {!minimal ? <UserMenu name={name} userId={userId} /> : null}
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

      {/* 우하단 플로팅 마스코트 — AI 도우미로 가는 상시 입구. 실제 대화 패널은 /chat 화면이다. */}
      {!minimal ? (
        <Box sx={{ position: "fixed", right: 24, bottom: 24, zIndex: (t) => t.zIndex.speedDial }}>
          <MascotButton onClick={() => navigate("/chat")} mode="listening" />
        </Box>
      ) : null}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} groups={groups} />
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
