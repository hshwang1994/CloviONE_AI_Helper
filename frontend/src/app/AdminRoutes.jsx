import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Button from "@mui/material/Button";
import { useAuth } from "./auth.jsx";
import { Card, Skeleton, ErrorState, EmptyState } from "../ui/kit.jsx";
import { SCREEN_ROLES, SCREEN_ROLE_HELP } from "./navConfig.js";

/* 관리자 콘솔 라우트
 *
 * App.jsx에서 분리해 별도 청크로 뺐다. 두 콘솔은 서로 다른 사람이 쓴다 — 일반 사용자는
 * 관리자 화면 20여 개를 평생 열지 않고, 관리자도 첫 진입에서 두 벌을 다 받을 이유가 없다.
 * 초기 번들이 예산(gzip 280KB)에 2KB까지 붙어 있었는데, 이 분리로 여유가 생긴다.
 *
 * ## PF7: 화면 컴포넌트와 registry.js 도 전부 지연 로드다
 *
 * 예전에는 이 파일 하나가 화면 컴포넌트 열다섯 개(Dashboard~SchedulerCalendar)와
 * `registry.js`(관리자 화면 스물여덟 개의 설정을 도메인 파일 일곱 개에서 모은 조립체)를
 * 전부 정적으로 물어 왔다. 그 결과 관리자가 `/dashboard` 하나만 열어도 한 번도 안 열
 * 화면 스물몇 개의 코드와 설정을 다 받았다 — 이 파일 자체는 별도 청크였지만, 그 청크
 * 안에서는 다시 전부 한 덩어리였다.
 *
 * 이제 화면 컴포넌트는 각각 `React.lazy()` 로, `registry.js`는 방문한 라우트가 실제로
 * REGISTRY 를 필요로 할 때만 `import()` 로 받는다. 아래 `<React.Suspense>` 는 이 파일이
 * 어디서 렌더되든(App.jsx 의 바깥쪽 Suspense뿐 아니라 테스트가 `<AdminRoutes />` 를 직접
 * 렌더할 때도) 스스로 로딩 상태를 책임지도록 이 파일 안에 둔다.
 */

const Dashboard = React.lazy(() => import("../screens/Dashboard.jsx").then((m) => ({ default: m.Dashboard })));
const Users = React.lazy(() => import("../screens/Users.jsx").then((m) => ({ default: m.Users })));
const Offboarding = React.lazy(() => import("../screens/Offboarding.jsx"));
const Settings = React.lazy(() => import("../screens/Settings.jsx").then((m) => ({ default: m.Settings })));
const Diagnostics = React.lazy(() => import("../screens/Ops.jsx").then((m) => ({ default: m.Diagnostics })));
const Maintenance = React.lazy(() => import("../screens/Ops.jsx").then((m) => ({ default: m.Maintenance })));
const SystemOps = React.lazy(() => import("../screens/SystemOps.jsx"));
const NotionConsole = React.lazy(() => import("../screens/NotionConsole.jsx"));
const LlmConsole = React.lazy(() => import("../screens/LlmConsole.jsx"));
const SetupWizard = React.lazy(() => import("../screens/SetupWizard.jsx"));
const DevReport = React.lazy(() => import("../screens/DevReport.jsx").then((m) => ({ default: m.DevReport })));
const DataScreen = React.lazy(() => import("../screens/DataScreen.jsx").then((m) => ({ default: m.DataScreen })));
const OrgConsole = React.lazy(() => import("../screens/OrgConsole.jsx"));
const Search = React.lazy(() => import("../screens/Search.jsx"));
const SchedulerCalendar = React.lazy(() => import("../screens/SchedulerCalendar.jsx"));

const ROUTES_FALLBACK = <Card><Skeleton lines={6} /></Card>;

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


/* 조직 콘솔이 대신 그리는 화면 키. `REGISTRY` 에는 설정이 그대로 남아 있다 — 콘솔이 그
 * 열·필터·폼 정의를 읽어 쓰기 때문이다(OrgConsole.jsx). 여기서는 **라우트만** 가져간다. */
const ORG_CONSOLE_KEYS = ["organizations", "departments", "org-tree"];

/* registry.js 를 정적으로 물어 오지 않는다(PF7) — 대신 이 파일이 마운트된 뒤 한 번
 * `import()` 로 받는다. `REGISTRY` 는 컴포넌트가 아니라 설정 객체라 `React.lazy()` 로는
 * 못 감싸지만, 같은 효과(별도 청크·지연 로드)는 이 `useState`+`useEffect` 로 낸다.
 * 로딩 중에는 REGISTRY 기반 라우트가 아직 없으므로 catch-all이 대시보드로 튕기지 않고
 * 로딩 상태를 보여준다 — 안 그러면 새로고침으로 `/schedules` 같은 주소에 막 들어온
 * 관리자가 REGISTRY 를 받기도 전에 대시보드로 튕기는 깜빡임이 생긴다. */
function useRegistry() {
  const [registry, setRegistry] = React.useState(null);
  React.useEffect(() => {
    let alive = true;
    import("../screens/registry.js").then((mod) => {
      if (alive) setRegistry(mod.REGISTRY);
    });
    return () => { alive = false; };
  }, []);
  return registry;
}

function AdminRoutes() {
  const registry = useRegistry();
  return (
    <React.Suspense fallback={ROUTES_FALLBACK}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        {/* 통합 검색 결과(계획서 Phase 5) — 사용자 콘솔과 **같은 경로**로 양쪽에 둔다.
            관리자가 Ctrl+K 로 검색했는데 세그먼트가 사용자 쪽으로 튀면 사이드바가 통째로 바뀐다.
            역할 게이트는 걸지 않는다: 결과 자체가 역할·범위로 걸러져 나온다(app/search/service.py). */}
        <Route path="/search" element={<Search />} />
        <Route path="/users" element={<RequireRole roles={SCREEN_ROLES.users}><Users /></RequireRole>} />
        {/* 온보딩·오프보딩은 목록이 아니라 마법사라 DataScreen 계약으로는 '미리 보여 주고
            확인받는' 단계를 표현할 수 없다(Offboarding.jsx 헤더 주석). */}
        <Route path="/offboarding" element={<RequireRole roles={SCREEN_ROLES.offboarding}><Offboarding /></RequireRole>} />
        <Route path="/settings" element={<Settings />} />
        {/* 최초 실행 셋업(9-3). Settings 와 같이 `RequireRole` 로 감싸지 않는다 — 이 화면은
            역할 게이트를 스스로 들고 있고(SetupWizard.jsx), 그래야 권한 없는 역할에게 목록
            요청 자체를 보내지 않는다. 서버 게이트는 app/setup/router.py 가 따로 건다. */}
        <Route path="/setup" element={<SetupWizard />} />
        {/* 시스템 설정(§S). `system_admin` 만이다 - `admin` 은 부서 범위로 좁혀질 수 있는
            역할인데, 여기서 바뀌는 것은 조직이 아니라 **서버 한 대 전체**라 범위라는 개념이
            없다. 서버 게이트는 app/sysops/router.py 가 같은 근거로 따로 건다. */}
        <Route path="/system" element={<RequireRole roles={["system_admin"]} help="이 화면은 시스템 관리자만 사용할 수 있습니다."><SystemOps /></RequireRole>} />
        {/* Notion 관리(9-4)와 AI 관리(9-5). 시스템 설정과 같은 근거로 `system_admin` 만이다 -
            여기서 바뀌는 것은 **설치 한 벌 전체**가 어느 워크스페이스를 보고 어떤 실행 파일을
            띄우는가라 '부서 범위' 라는 개념이 없다. 서버 게이트는 각 라우터가 따로 건다. */}
        <Route path="/notion-console" element={<RequireRole roles={["system_admin"]} help="이 화면은 시스템 관리자만 사용할 수 있습니다."><NotionConsole /></RequireRole>} />
        <Route path="/llm-console" element={<RequireRole roles={["system_admin"]} help="이 화면은 시스템 관리자만 사용할 수 있습니다."><LlmConsole /></RequireRole>} />
        <Route path="/diagnostics" element={<RequireRole roles={["admin", "system_admin"]}><Diagnostics /></RequireRole>} />
        <Route path="/maintenance" element={<RequireRole roles={["operator", "admin", "system_admin", "auditor"]} help="이 화면은 운영자, 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다."><Maintenance /></RequireRole>} />
        <Route path="/dev-report" element={<RequireRole roles={["admin", "system_admin", "auditor"]} help="이 화면은 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다."><DevReport /></RequireRole>} />
        {/* 스케줄러 캘린더(PLAN Phase 6) — "언제 도는가"는 표로 답이 안 되는 유일한 질문이라
            DataScreen 계약을 쓰지 않는다(SchedulerCalendar.jsx 헤더 주석). 같은 백로그의 다른
            화면 여덟 개는 전부 registry.js 설정으로 끝냈다. */}
        <Route
          path="/scheduler-calendar"
          element={
            <RequireRole roles={SCREEN_ROLES["scheduler-calendar"]} help={SCREEN_ROLE_HELP["scheduler-calendar"]}>
              <SchedulerCalendar />
            </RequireRole>
          }
        />
        {/* 조직 콘솔(OrgConsole.jsx) — 조직 관리, 부서 관리, 조직도가 한 화면이다.
         *
         * **세 주소를 모두 남긴다.** 사라진 주소로 들어온 사람은 대시보드로 튕기고(아래
         * catch-all 라우트), 즐겨찾기와 다른 화면의 딥링크(registry/org.js 의 '조직도에서 보기',
         * '부서 관리에서 열기')가 조용히 끊긴다.
         *
         * 리다이렉트 대신 **그 자리에서 열되 오른쪽 패널을 그 종류로 맞춘다.** 리다이렉트는
         * 해시 쿼리를 버린다 — `#/departments?active=false` 나 저장된 뷰 링크를 열면 필터가
         * 사라진 다른 화면이 뜨고, 사용자는 링크가 고장 났다고 읽는다. 여기서는 주소가 그대로
         * 남아 DataScreen 이 그 쿼리를 예전과 똑같이 읽는다(datascreen-view.js 의 parseView 는
         * 그 화면이 아는 필터 키만 취한다).
         *
         * `/org-tree` 의 기본값이 조직인 이유는 OrgConsole.jsx 헤더 주석 참조. */}
        <Route path="/org-tree" element={<RequireRole roles={SCREEN_ROLES["org-tree"]} help={SCREEN_ROLE_HELP["org-tree"]}><OrgConsole /></RequireRole>} />
        <Route path="/organizations" element={<RequireRole roles={SCREEN_ROLES.organizations} help={SCREEN_ROLE_HELP.organizations}><OrgConsole defaultKind="organizations" /></RequireRole>} />
        <Route path="/departments" element={<RequireRole roles={SCREEN_ROLES.departments} help={SCREEN_ROLE_HELP.departments}><OrgConsole defaultKind="departments" /></RequireRole>} />
        {/* 위 세 화면은 설정만으로 그려지지 않는다(트리 + 관리 패널) — 아래 일괄 등록에서 뺀다.
            같은 경로를 두 번 등록하면 어느 쪽이 이기는지가 라우터의 정렬 규칙에 달리게 된다.
            `registry` 가 아직 로드되기 전(null)에는 REGISTRY 기반 라우트가 하나도 없다 —
            그 사이에는 아래 catch-all 이 대시보드로 튕기는 대신 로딩 화면을 보인다. */}
        {registry && Object.keys(registry).filter((key) => !ORG_CONSOLE_KEYS.includes(key)).map((key) => {
          const cfg = registry[key];
          const roles = cfg.roles || SCREEN_ROLES[key];
          const screen = <DataScreen config={cfg} />;
          return (
            <Route key={key} path={"/" + key}
              element={roles ? <RequireRole roles={roles} help={SCREEN_ROLE_HELP[key]}>{screen}</RequireRole> : screen} />
          );
        })}
        <Route path="*" element={registry ? <Navigate to="/dashboard" replace /> : ROUTES_FALLBACK} />
      </Routes>
    </React.Suspense>
  );
}


export default AdminRoutes;
