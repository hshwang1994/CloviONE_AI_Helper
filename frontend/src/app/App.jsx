import React, { useEffect, useState } from "react";
import { HashRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth.jsx";
import { Dashboard } from "../screens/Dashboard.jsx";
import { Users } from "../screens/Users.jsx";
import { Settings } from "../screens/Settings.jsx";
import { Diagnostics, Maintenance } from "../screens/Ops.jsx";
import { MyWork, MyTickets, Unassigned, NewTicket } from "../screens/MyTickets.jsx";
import { Board } from "../screens/Board.jsx";
import { BoardPost } from "../screens/BoardPost.jsx";
import { TeamDocs } from "../screens/TeamDocs.jsx";
import { TeamDoc } from "../screens/TeamDoc.jsx";
import { Trash } from "../screens/Trash.jsx";
import { Ticket } from "../screens/Ticket.jsx";
import { TeamTickets } from "../screens/TeamTickets.jsx";
import { Sprint } from "../screens/Sprint.jsx";
import { Games } from "../screens/Games.jsx";
import { ChatRooms } from "../screens/ChatRooms.jsx";
import { ChatRoom } from "../screens/ChatRoom.jsx";
import { DataScreen } from "../screens/DataScreen.jsx";
import { REGISTRY } from "../screens/registry.js";
import { Card, Skeleton, ErrorState, EmptyState } from "../ui/kit.jsx";
import { AppShell, ShellErrorFallback } from "./AppShell.jsx";
import { NAV, SCREEN_ROLES, SCREEN_ROLE_HELP, USER_NAV, inUserSegment } from "./navConfig.js";
import { applyBootTheme } from "./theme-store.js";
import Button from "@mui/material/Button";

/* 라우트 표와 셸 조립. 셸 자체(상단바·사이드바·팔레트·마스코트)는 AppShell.jsx,
 * 사이트맵과 권한 표는 navConfig.js에 있다.
 *
 * 라우트 경로는 재설계에서도 한 글자도 바꾸지 않았다 — 북마크·알림 딥링크·초기 진입 로직이
 * 전부 이 해시 경로에 걸려 있다. */

/* 첫 페인트 전에 테마를 적용해 다크 사용자의 화이트 플래시(FOUC)를 없앤다.
 * CSP가 인라인 <script>를 막으므로 부팅 인라인 스크립트 대신 모듈 스코프에서 동기 적용한다
 * (이 모듈은 createRoot보다 먼저 평가된다). */
applyBootTheme();

/* 무거운 화면은 라우트 진입 시점에 따로 받는다.
 * 셋 다 화면 하나가 수백~천 줄이고(채팅 1,205줄, 게임방 821줄) 대부분의 사용자는 한 세션에
 * 들르지 않는다. 첫 진입에서 같이 받으면 사내 LAN이라도 초기 로딩만 무거워진다.
 * 나머지 화면은 지연 로딩할 만큼 크지 않아 그대로 둔다 — 청크가 잘게 쪼개지면 화면 전환마다
 * 요청이 늘어 오히려 느려진다. */
const Chat = React.lazy(() => import("../screens/Chat.jsx").then((m) => ({ default: m.Chat })));
const GameRoom = React.lazy(() => import("../screens/GameRoom.jsx").then((m) => ({ default: m.GameRoom })));
const DevReport = React.lazy(() => import("../screens/DevReport.jsx").then((m) => ({ default: m.DevReport })));

/* 지연 로딩 화면은 받아오는 동안 스켈레톤을 보여준다 — 빈 화면이면 '눌렀는데 아무 일도
 * 안 일어난다'로 보인다. */
function Lazy({ children }) {
  return <React.Suspense fallback={<Card><Skeleton lines={6} /></Card>}>{children}</React.Suspense>;
}

/* 역할 가드 — 나브 항목만 숨기면 해시 URL 직접 진입 시 죽은 껍데기(수집 버튼 없는 진단 등)가
 * 그려진다. 라우트 자체를 역할로 감싸 권한 없는 사용자에겐 명확한 안내를 보인다. */
function RequireRole({ roles, children, help }) {
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  if (auth.isLoading) return <Card><Skeleton /></Card>;
  // 세션 만료(401)는 '권한 없음'과 다르다 — 재로그인하면 바로 풀리는 문제다. 권한 없음처럼
  // 영구적으로 보이는 EmptyState 대신 로그인 링크가 있는 ErrorState를 보여준다.
  if (auth.isError) return <ErrorState error={auth.error} onRetry={() => auth.refetch()} />;
  if (!role || !roles.includes(role)) {
    return (
      <EmptyState
        title="권한이 없습니다"
        help={help || "이 화면은 관리자, 시스템 관리자만 사용할 수 있습니다."}
        art="noPermission"
        action={<Button variant="contained" href="#/">대시보드로 이동</Button>}
      />
    );
  }
  return children;
}

/* 에러 경계 — 화면 렌더 중 예외가 나도 전체 SPA가 흰 화면으로 죽지 않게 한다.
 * 라우트별로 key를 주어 경로가 바뀌면 리셋된다. */
class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  // 예전엔 캐치는 됐지만 아무 데도 기록되지 않아(console.error조차 없이) 원인 스택이 조용히
  // 삼켜졌다. 이 경계가 앱의 유일한 크래시 포착 지점이다.
  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info && info.componentStack);
  }
  render() {
    if (this.state.err) return <ShellErrorFallback />;
    return this.props.children;
  }
}

function AdminRoutes() {
  return (
    <Routes>
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/users" element={<RequireRole roles={SCREEN_ROLES.users}><Users /></RequireRole>} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/diagnostics" element={<RequireRole roles={["admin", "system_admin"]}><Diagnostics /></RequireRole>} />
      <Route path="/maintenance" element={<RequireRole roles={["operator", "admin", "system_admin", "auditor"]} help="이 화면은 운영자, 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다."><Maintenance /></RequireRole>} />
      <Route path="/dev-report" element={<RequireRole roles={["admin", "system_admin", "auditor"]} help="이 화면은 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다."><Lazy><DevReport /></Lazy></RequireRole>} />
      {Object.keys(REGISTRY).map((key) => {
        const cfg = REGISTRY[key];
        const roles = cfg.roles || SCREEN_ROLES[key];
        const screen = <DataScreen config={cfg} />;
        return (
          <Route key={key} path={"/" + key}
            element={roles ? <RequireRole roles={roles} help={SCREEN_ROLE_HELP[key]}>{screen}</RequireRole> : screen} />
        );
      })}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

/* 사용자 콘솔 — 내 업무/내 티켓/미할당 + 팀 공간 + 문서 + AI 도우미(/chat).
 * 알림은 공용 DataScreen이라 기본 '관리자' 빵부스러기가 뜨므로 그 라우트만 감싼다. */
function UserRoutes() {
  return (
    <Routes>
      <Route path="/me" element={<MyWork />} />
      <Route path="/my-tickets" element={<MyTickets />} />
      <Route path="/unassigned" element={<Unassigned />} />
      <Route path="/new-ticket" element={<NewTicket />} />
      <Route path="/tickets/:id" element={<Ticket />} />
      <Route path="/team-tickets" element={<TeamTickets />} />
      <Route path="/sprint" element={<Sprint />} />
      <Route path="/chat" element={<div className="c-chat-embed"><Lazy><Chat /></Lazy></div>} />
      <Route path="/chat-rooms" element={<ChatRooms />} />
      <Route path="/chat-rooms/:id" element={<ChatRoom />} />
      <Route path="/board" element={<Board />} />
      <Route path="/board/:id" element={<BoardPost />} />
      <Route path="/team-docs" element={<TeamDocs />} />
      {/* /team-docs/trash 는 /team-docs/:id 보다 먼저 — id 로 잡히지 않게 */}
      <Route path="/team-docs/trash" element={<Trash />} />
      <Route path="/team-docs/:id" element={<TeamDoc />} />
      <Route path="/games" element={<Games />} />
      <Route path="/games/:id" element={<Lazy><GameRoom /></Lazy>} />
      <Route path="/notifications" element={<div className="c-body--user-noti"><DataScreen config={REGISTRY.notifications} /></div>} />
      <Route path="*" element={<Navigate to="/me" replace />} />
    </Routes>
  );
}

function Layout() {
  const loc = useLocation();
  const nav = useNavigate();
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  const isUser = role === "user";
  const [navOpen, setNavOpen] = useState(false);

  // 경로가 바뀌면 모바일 드로어를 닫는다(항목 선택 후 자동 닫힘).
  useEffect(() => { setNavOpen(false); }, [loc.pathname]);

  // 최초 진입: 해시가 없으면 실제 경로로 기본 화면을 정한다(/admin→대시보드, 그 외→내 업무 홈).
  useEffect(() => {
    const h = window.location.hash.replace("#", "");
    if (!h) nav(window.location.pathname === "/admin" ? "/dashboard" : "/me", { replace: true });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // must_change_password가 켜진 계정은 /api/me 이외 거의 모든 API가 403으로 막힌다 —
  // 그대로 두면 화면마다 막다른 403만 보인다. login.js가 로그인 직후 하는 것과 같은
  // 리다이렉트를 SPA 진입 시점에도 한다(/change-password는 이 SPA 밖의 별도 페이지).
  useEffect(() => {
    if (auth.data && auth.data.must_change_password) window.location.href = "/change-password";
  }, [auth.data]);

  // 사용자 세그먼트 여부(관리자군이 상단 '사용자' 탭에 있는지). role=user 는 항상 사용자 콘솔.
  const userSeg = inUserSegment(loc.pathname);
  const showMenu = !auth.isError && !auth.isLoading;
  const useUserConsole = isUser || userSeg;

  return (
    <AppShell
      nav={useUserConsole ? USER_NAV : NAV}
      ariaLabel={useUserConsole ? "사용자 메뉴" : "관리 메뉴"}
      navOpen={navOpen}
      onCloseNav={() => setNavOpen(false)}
      onToggleNav={() => setNavOpen((v) => !v)}
      isUser={isUser}
      userSeg={userSeg}
      minimal={auth.isError}
      showMenu={showMenu}
    >
      {/* 오류 경계를 본문에만 두고 경로별로 리셋한다 — 한 화면이 크래시해도 사이드바·상단바는
          살아 이동 가능하다. */}
      <ErrorBoundary key={loc.pathname}>
        {useUserConsole ? <UserRoutes /> : <AdminRoutes />}
      </ErrorBoundary>
    </AppShell>
  );
}

export function App() {
  // 저장된 테마를 부팅 때 적용(없으면 OS 선호 → 라이트).
  useEffect(() => { applyBootTheme(); }, []);
  return (
    <AuthProvider>
      <HashRouter>
        <ErrorBoundary>
          <Layout />
        </ErrorBoundary>
      </HashRouter>
    </AuthProvider>
  );
}
