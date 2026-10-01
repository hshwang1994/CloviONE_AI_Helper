import React, { useEffect, useState } from "react";
import { HashRouter, Routes, Route, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth.jsx";
import { Skeleton } from "../ui/kit.jsx";
import { AppShell, ShellErrorFallback } from "./AppShell.jsx";
import { LoginHandoff } from "./LoginHandoff.jsx";
import { useImpersonation } from "./Banners.jsx";
import { NavEntryProvider, screenKeyOf, useNavEntry } from "./navEntry.jsx";

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

/* 해시가 없는 최초 진입에서 기본 화면을 정한다.
 *
 * **사람은 누구나 먼저 사용자다** (0060 §3). 역할과 무관하게 개인 업무 홈으로 착지한다 —
 * 관리자도 자기 티켓과 승인이 있고, 관리 기능은 필요할 때 상단 전환으로 들어간다.
 * 예전에는 role !== "user" 이면 곧장 관리자 대시보드로 보냈는데, 그래서 관리자 12명은
 * 로그인할 때마다 운영 지표부터 보고 자기 업무는 찾아 들어가야 했다.
 *
 * `/admin` 물리 경로로 직접 들어온 경우만 예외다 — 그 주소 자체가 관리 콘솔 진입 의도이고,
 * 서버가 이미 그 경로를 관리 콘솔 역할로 게이팅한다(app/admin/router.py::admin_console).
 */
export function initialLandingPath(pathname, _role) {
  return pathname === "/admin" ? "/dashboard" : "/me";
}

/** 이 해시가 **갈 곳을 말하고 있나**. 아니면 착지 규칙이 대신 정한다.
 *
 * 🔴 `"/"` 도 갈 곳이 아니다. `#/` 는 `hash.replace("#","")` 를 지나면 truthy 한 `"/"` 가
 * 되어 예전 조건(`!h`)을 그냥 통과했는데, **두 라우트 표 어디에도 `path="/"` 가 없다** —
 * 그래서 `href="#/"` 로 보내던 세 자리(`kit.jsx` 의 ErrorState, 관리 콘솔·설정의 권한 벽)가
 * 전부 「찾을 수 없습니다」로 갔다. 막다른 길에서 막다른 길로 보낸 것이다.
 *
 * 라우트 표에 `path="/"` 를 넣는 쪽으로는 안 고친다 — 그 자리는 **역할을 모른다.** 인증
 * 조회가 끝나기 전에 그 리다이렉트가 먼저 돌면 일반 사용자가 관리자 대시보드 주소로
 * 밀려가고, 그 뒤에는 해시가 비어 있지 않아 이 규칙이 다시 안 돈다. */
export function hasDestination(hash) {
  const h = String(hash || "").replace("#", "");
  return !!h && h !== "/";
}

/** 지금 이 브라우저를 SPA 밖 `/change-password` 로 밀어야 하는가 (users-07).
 *
 * 세 값이 다 필요하다:
 *   * `mustChange` — `/api/me` 가 말한 값. 대리 보기 중이면 **대상의** 값이다.
 *   * `impersonationKnown` — 대리 보기 여부를 아직 물어보는 중이면 밀지 않고 기다린다.
 *     먼저 밀면 그 답이 도착할 자리가 없어진다. 조회가 실패해도 «안다» 로 친다(그때는
 *     대리 보기가 아닌 것으로 보고 예전과 똑같이 민다).
 *   * `impersonating` — 대리 보기 중이면 안 민다. 갓 만든 계정은 전부
 *     `must_change_password` 라(기본값), 그 사람을 대리 보기로 열면 관리자가 SPA 밖
 *     비밀번호 변경 화면에 갇혔다 — 그 페이지에는 대리 보기 띠도 「대리 보기 종료」도
 *     없어서 화면 안에서 되돌아올 길이 로그아웃뿐이었다.
 */
export function shouldForcePasswordChange({ mustChange, impersonationKnown, impersonating }) {
  return !!mustChange && !!impersonationKnown && !impersonating;
}

/* 첫 페인트 전에 테마를 적용해 다크 사용자의 화이트 플래시(FOUC)를 없앤다.
 * CSP가 인라인 <script>를 막으므로 부팅 인라인 스크립트 대신 모듈 스코프에서 동기 적용한다
 * (이 모듈은 createRoot보다 먼저 평가된다). */
applyBootTheme();

/* 에러 경계 — 화면 렌더 중 예외가 나도 전체 SPA가 흰 화면으로 죽지 않게 한다.
 * 본문 경계의 key 는 `경로:진입 번호` 다 — 다른 경로로 가거나 **같은 메뉴를 다시 누르면**
 * 리셋된다(`navEntry.jsx`). 폴백의 「다시 시도」는 경계를 되감아 같은 화면을 다시 그린다. */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { err: null, componentStack: null };
    this.reset = this.reset.bind(this);
  }
  static getDerivedStateFromError(err) { return { err }; }
  // 예전엔 캐치는 됐지만 아무 데도 기록되지 않아(console.error조차 없이) 원인 스택이 조용히
  // 삼켜졌다. 이 경계가 앱의 유일한 크래시 포착 지점이다. 부품 경로는 폴백의 기술 정보에도 싣는다 —
  // 사용자가 옮겨 적어 줄 수 있어야 다음 발생에서 원인을 짚는다.
  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info && info.componentStack);
    this.setState({ componentStack: (info && info.componentStack) || null });
  }
  reset() { this.setState({ err: null, componentStack: null }); }
  render() {
    if (this.state.err) {
      return (
        <ShellErrorFallback
          error={this.state.err}
          componentStack={this.state.componentStack}
          onReset={this.props.resettable ? this.reset : null}
        />
      );
    }
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

  // 최초 진입: 해시가 없으면 initialLandingPath()로 기본 화면을 정한다. role은 인증 조회가
  // 끝나야 안다 — 로딩 중엔 메뉴 자체가 없어(showMenu) 그 사이 해시가 바뀔 수 없으므로
  // (누를 것이 없다) 안전하게 기다린다.
  useEffect(() => {
    if (auth.isLoading) return;
    if (!hasDestination(window.location.hash)) {
      nav(initialLandingPath(window.location.pathname, role), { replace: true });
    }
    // 🔴 `loc.pathname` 이 의존성에 **있어야 한다**. 없으면 이 규칙이 부팅 때 한 번만 돌아,
    // SPA 안에서 `#/` 로 이동하는 경우(`hasDestination` 주석의 세 단추)를 못 받는다.
    // 여기는 `auth.isLoading` 을 기다리므로 역할을 알고 나서 정한다.
  }, [auth.isLoading, loc.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  /* must_change_password가 켜진 계정은 /api/me 이외 거의 모든 API가 403으로 막힌다 —
   * 그대로 두면 화면마다 막다른 403만 보인다. login.js가 로그인 직후 하는 것과 같은
   * 리다이렉트를 SPA 진입 시점에도 한다(/change-password는 이 SPA 밖의 별도 페이지).
   *
   * 🔴 **대리 보기 중에는 안 민다.** 그 세션의 `must_change_password` 는 지금 보고 있는
   * 대상의 것이지 이 브라우저 주인의 것이 아니다. 갓 만든 계정은 전부 그 상태라(기본값),
   * 그 사람을 대리 보기로 열면 관리자가 SPA 밖 비밀번호 변경 화면에 갇혔다 — 그 페이지에는
   * 대리 보기 띠도 「대리 보기 종료」도 없어서 되돌아오는 길이 로그아웃뿐이었다(users-07).
   * 서버는 이미 그렇게 판단해 뒀다(`app/core/deps.py::get_current_user` — 대리 보기 세션은
   * 읽기만 되므로 그 게이트를 안 건다). 그리고 대리 보기 세션은 비밀번호를 바꿀 수도 없다.
   *
   * 판단 자체는 위 `shouldForcePasswordChange` 에 있다 — 세 값의 조합을 화면 없이 시험한다. */
  const impersonation = useImpersonation();
  const impersonating = !!(impersonation.data && impersonation.data.impersonating);
  const impersonationKnown = impersonation.isFetched;
  const mustChange = !!(auth.data && auth.data.must_change_password);
  useEffect(() => {
    if (shouldForcePasswordChange({ mustChange, impersonationKnown, impersonating })) {
      window.location.href = "/change-password";
    }
  }, [mustChange, impersonationKnown, impersonating]);

  // 같은 메뉴를 다시 누르면 올라가는 번호 — 본문 경계의 키에 들어가 화면이 새로 마운트된다.
  const entry = useNavEntry();

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
        nav={navWithFeatures(useUserConsole ? USER_NAV : NAV, auth.data && auth.data.features, auth.data && auth.data.capabilities)}
        // SRCH-01: 명령 팔레트(Ctrl+K)는 "어디서든 어디로든"이 존재 이유라 현재 콘솔 하나로
        // 좁히면 안 된다 — 두 콘솔 전체를 검색 대상으로 주고, role 필터(AppShell 안에서)가
        // 지금 역할이 못 보는 화면은 그대로 걸러 낸다.
        paletteNav={navWithFeatures([...NAV, ...USER_NAV], auth.data && auth.data.features, auth.data && auth.data.capabilities)}
        ariaLabel={useUserConsole ? "사용자 메뉴" : "관리 메뉴"}
        navOpen={navOpen}
        onCloseNav={() => setNavOpen(false)}
        onToggleNav={() => setNavOpen((v) => !v)}
        isUser={isUser}
        userSeg={userSeg}
        minimal={auth.isError}
        showMenu={showMenu}
      >
        {/* 오류 경계를 본문에만 두고 화면별로 리셋한다 — 한 화면이 크래시해도 사이드바·상단바는
            살아 이동 가능하다. 키는 경로가 아니라 **화면**이다(`navEntry.jsx::screenKeyOf`) — 목록과 상세를 한
            화면에 둔 곳(조직 관리 · 사용자 · 채팅방)은 고를 때마다 다시 마운트되지 않는다. 키에 진입 번호가
            들어간다: 같은 메뉴를 다시 누르면 화면이 새로 마운트되어, 두 번 누른 끝 상태가 한 번 누른 끝 상태와 같다. */}
        <ErrorBoundary key={`${screenKeyOf(loc.pathname)}:${entry}`} resettable>
          <React.Suspense fallback={<Skeleton kind="page" lines={4} />}>
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
          <NavEntryProvider>
            <Layout />
          </NavEntryProvider>
        </ErrorBoundary>
      </HashRouter>
    </AuthProvider>
  );
}