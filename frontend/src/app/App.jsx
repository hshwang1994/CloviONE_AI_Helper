import React, { useEffect, useState } from "react";
import { HashRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth.jsx";
import { Card, Skeleton } from "../ui/kit.jsx";
import { AppShell, ShellErrorFallback } from "./AppShell.jsx";
import { LoginHandoff } from "./LoginHandoff.jsx";

/* 두 콘솔은 각각 별도 청크다. 사용자 콘솔만 쓰는 사람은 관리자 화면 20여 개를 받지 않는다. */
const AdminRoutes = React.lazy(() => import("./AdminRoutes.jsx"));
const UserRoutes = React.lazy(() => import("./UserRoutes.jsx"));
import { NAV, USER_NAV, inUserSegment, navWithFeatures } from "./navConfig.js";
import { applyBootTheme } from "./theme-store.js";

/* 라우트 표와 셸 조립. 셸 자체(상단바·사이드바·팔레트·마스코트)는 AppShell.jsx,
 * 사이트맵과 권한 표는 navConfig.js에 있다.
 *
 * 라우트 경로는 재설계에서도 한 글자도 바꾸지 않았다 — 북마크·알림 딥링크·초기 진입 로직이
 * 전부 이 해시 경로에 걸려 있다. */

/* 첫 페인트 전에 테마를 적용해 다크 사용자의 화이트 플래시(FOUC)를 없앤다.
 * CSP가 인라인 <script>를 막으므로 부팅 인라인 스크립트 대신 모듈 스코프에서 동기 적용한다
 * (이 모듈은 createRoot보다 먼저 평가된다). */
applyBootTheme();

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
    <>
      {/* 로그인 화면에서 시작된 연출을 여기서 이어받아 끝낸다. 로그인 직후가 아니면
          아무것도 그리지 않는다(실패·만료·평상시 새로고침에서는 표식 자체가 없다).
          인증 조회가 끝나야 첫 화면이 실제로 그려지므로 그 시점을 준비 신호로 준다. */}
      <LoginHandoff ready={!auth.isLoading} />
      <AppShell
        nav={navWithFeatures(useUserConsole ? USER_NAV : NAV, auth.data && auth.data.features)}
        // SRCH-01: 명령 팔레트(Ctrl+K)는 "어디서든 어디로든"이 존재 이유라 현재 콘솔 하나로
        // 좁히면 안 된다 — 두 콘솔 전체를 검색 대상으로 주고, role 필터(AppShell 안에서)가
        // 지금 역할이 못 보는 화면은 그대로 걸러 낸다.
        paletteNav={navWithFeatures([...NAV, ...USER_NAV], auth.data && auth.data.features)}
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
          <React.Suspense fallback={<Card><Skeleton lines={6} /></Card>}>
            {useUserConsole ? <UserRoutes /> : <AdminRoutes />}
          </React.Suspense>
        </ErrorBoundary>
      </AppShell>
    </>
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