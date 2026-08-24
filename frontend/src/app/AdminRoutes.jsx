import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Button from "@mui/material/Button";
import { useAuth } from "./auth.jsx";
import { Card, Skeleton, ErrorState, EmptyState } from "../ui/kit.jsx";
import { SCREEN_ROLES, SCREEN_ROLE_HELP } from "./navConfig.js";
import { TabShell } from "../ui/TabShell.jsx";

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
// PA-RC-0017: 시스템 설정·유지보수·AI 관리는 더 이상 각자의 라우트가 그리지 않는다 — 전부
// SettingsShell.jsx의 탭이 됐다(그 파일이 이 세 컴포넌트를 직접 import한다). 아래
// /system·/maintenance·/llm-console 라우트는 옛 주소가 죽은 링크가 되지 않도록
// /settings?tab=* 로 보내는 리다이렉트만 남는다.
const Settings = React.lazy(() => import("../screens/Settings.jsx").then((m) => ({ default: m.SettingsShell })));
const Diagnostics = React.lazy(() => import("../screens/Ops.jsx").then((m) => ({ default: m.Diagnostics })));
const MailStatus = React.lazy(() => import("../screens/MailStatus.jsx"));
const SetupWizard = React.lazy(() => import("../screens/SetupWizard.jsx"));
const DevReport = React.lazy(() => import("../screens/DevReport.jsx").then((m) => ({ default: m.DevReport })));
const DataScreen = React.lazy(() => import("../screens/DataScreen.jsx").then((m) => ({ default: m.DataScreen })));
const OrgConsole = React.lazy(() => import("../screens/OrgConsole.jsx"));
const Search = React.lazy(() => import("../screens/Search.jsx"));
const SchedulerCalendar = React.lazy(() => import("../screens/SchedulerCalendar.jsx"));
const Integrity = React.lazy(() => import("../screens/Integrity.jsx").then((m) => ({ default: m.Integrity })));

// 라우트 청크가 통째로 아직 없다 — `UserRoutes.jsx::Lazy` 와 같은 이유로 화면 모양을 그린다.
const ROUTES_FALLBACK = <Skeleton kind="page" lines={4} />;

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

/* PA-RC-0024: 모르는 관리자 경로(오타 URL, 지워진 상세 id 등)가 설명 없이 대시보드로
 * 조용히 튕겨 나갔다 — 잘못 온 것인지 뭔가 없어진 것인지 사용자가 알 방법이 없었다.
 * 새 컴포넌트를 만들지 않는다(Handoff 명시) — 사용자 콘솔의 :id 라우트 6개가 이미
 * 쓰는 ErrorState(kit.jsx)를 그대로 재사용한다. status:404를 주면 "찾을 수 없습니다"
 * 문구·홈으로 버튼까지 전부 그 컴포넌트가 책임진다. */
function RouteNotFound() {
  return <ErrorState error={{ status: 404 }} />;
}

/* 조직 콘솔이 대신 그리는 화면 키. `REGISTRY` 에는 설정이 그대로 남아 있다 — 콘솔이 그
 * 열·필터·폼 정의를 읽어 쓰기 때문이다(OrgConsole.jsx). 여기서는 **라우트만** 가져간다. */

/* 탭으로 합친 관리자 화면 (지시 30 · 41 · 51).
 *
 * ## 합치는 기준
 *
 * "이름이 비슷해서"가 아니라 **같은 질문에 답하는가**다. 네 짝 모두 역할 집합이 정확히
 * 같아서(아래 `sameRoles` 가 조립 시점에 확인한다) 탭으로 합쳐도 RBAC 가 부서지지 않는다 —
 * SettingsShell 이 '초기 설정'과 '유지보수'를 탭으로 안 묶은 것과 같은 기준이다(그쪽은
 * 역할이 달랐다).
 *
 * ## 주소
 *
 * 대표 주소 하나(`path`)가 그릇이고 탭은 `?tab=` 이다. 합쳐진 화면의 **옛 주소는 전부
 * 살린다** — 즐겨찾기와 다른 화면의 딥링크가 조용히 끊기면 안 된다(조직 콘솔이 세 주소를
 * 남긴 것과 같은 이유). 옛 주소는 리다이렉트가 아니라 **그 자리에서 해당 탭으로 연다**:
 * 리다이렉트는 해시 쿼리를 버려서, 저장된 뷰 링크(`#/restore-drills?status=failed`)를 열면
 * 필터가 사라진 화면이 뜬다.
 */
/* W0: `registry-surface-parity.test.js` 가 이 표를 import 해 ROUTE_COVERAGE 와 대조한다.
   Python 정규식으로는 계산된 경로를 못 읽어 28개 중 1개를 조용히 놓쳤다 — JS 진실은 JS 가 증명한다. */
export const TAB_GROUPS = [
  {
    path: "/backup", area: "운영", title: "백업",
    tabs: [
      { key: "backup", label: "백업" },
      { key: "restore-drills", label: "복구 리허설" },
    ],
  },
  {
    path: "/approvals", area: "사용자와 권한", title: "승인",
    tabs: [
      { key: "approvals", label: "승인 요청" },
      { key: "approval-delegations", label: "승인 위임" },
    ],
  },
  {
    path: "/audit", area: "감사", title: "감사 로그",
    tabs: [
      { key: "audit", label: "감사 로그" },
      { key: "audit-anomalies", label: "이상 징후" },
    ],
  },
  {
    path: "/ai-usage", area: "AI", title: "AI 사용 통계",
    tabs: [
      { key: "policy-usage", label: "정책" },
      { key: "prompt-usage", label: "프롬프트" },
    ],
  },
  {
    /* 실행 일정 ↔ 실행 달력은 **같은 데이터의 두 표현**이다 — "무엇이 등록돼 있나"(표)와
       "언제 도나"(달력). 달력은 DataScreen 계약으로는 답이 안 되는 질문이라 별도 화면으로
       남아 있었는데(SchedulerCalendar.jsx 헤더 주석), 그렇다고 사이드바 항목 두 개일 이유는
       없었다 — 둘 중 무엇을 고를지는 '어떻게 볼지'의 문제다. */
    path: "/schedules", area: "자동화와 연동", title: "실행 일정",
    tabs: [
      { key: "schedules", label: "목록" },
      { key: "scheduler-calendar", label: "달력", render: () => <SchedulerCalendar embedded /> },
    ],
  },
];

/** 탭이 대신 그리는 registry 키 — 아래 일괄 라우트 등록에서 뺀다(같은 경로 이중 등록 금지). */
const TAB_GROUP_KEYS = TAB_GROUPS.flatMap((g) => g.tabs.map((t) => t.key));

/** 한 그릇 안의 탭들이 같은 역할 집합인가. 다르면 합치는 순간 RBAC 가 넓어지거나 좁아진다. */
function sameRoles(tabs) {
  const sets = tabs.map((t) => JSON.stringify([...(SCREEN_ROLES[t.key] || [])].sort()));
  return sets.every((x) => x === sets[0]);
}

export const ORG_CONSOLE_KEYS = ["organizations", "departments", "org-tree"];

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
  const usersElement = <RequireRole roles={SCREEN_ROLES.users}><Users /></RequireRole>;
  const departmentsElement = (
    <RequireRole roles={SCREEN_ROLES.departments} help={SCREEN_ROLE_HELP.departments}>
      <OrgConsole defaultKind="departments" />
    </RequireRole>
  );
  return (
    <React.Suspense fallback={ROUTES_FALLBACK}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        {/* 조직 정합성 진단(0060) — fail-closed 규칙이 닫아 버린 대상을 보여 주고 일괄로
            지정한다. 규칙과 같은 배포에 있어야 복구가 몇 분짜리 일이 된다. */}
        <Route
          path="/integrity"
          element={<RequireRole roles={SCREEN_ROLES.integrity}><Integrity /></RequireRole>}
        />
        {/* 통합 검색 결과(계획서 Phase 5) — 사용자 콘솔과 **같은 경로**로 양쪽에 둔다.
            관리자가 Ctrl+K 로 검색했는데 세그먼트가 사용자 쪽으로 튀면 사이드바가 통째로 바뀐다.
            역할 게이트는 걸지 않는다: 결과 자체가 역할·범위로 걸러져 나온다(app/search/service.py). */}
        <Route path="/search" element={<Search />} />
        {/* PA-RC-0024: /users/:id는 /users와 완전히 같은 element(같은 컴포넌트
            레퍼런스)다 — 목록 위 모달이라는 표현은 그대로 두고 주소만 상세 상태를 실어
            딥링크·새로고침·뒤로가기가 성립하게 한다. 두 Route가 같은 컴포넌트를 가리키면
            둘 사이를 navigate()로 오갈 때 컴포넌트 인스턴스가 유지된다(리액트 라우터
            v7 실측 확인 — 목록이 다시 마운트되며 스크롤/필터/데이터를 잃지 않는다).
            Users.jsx 안에서 useParams().id를 기존 ?id= 딥링크 소비 경로와 함께 읽는다. */}
        <Route path="/users" element={usersElement} />
        <Route path="/users/:id" element={usersElement} />
        {/* 온보딩·오프보딩은 목록이 아니라 마법사라 DataScreen 계약으로는 '미리 보여 주고
            확인받는' 단계를 표현할 수 없다(Offboarding.jsx 헤더 주석). */}
        <Route path="/offboarding" element={<RequireRole roles={SCREEN_ROLES.offboarding}><Offboarding /></RequireRole>} />
        <Route path="/settings" element={<Settings />} />
        {/* 최초 실행 셋업(9-3). Settings 와 같이 `RequireRole` 로 감싸지 않는다 — 이 화면은
            역할 게이트를 스스로 들고 있고(SetupWizard.jsx), 그래야 권한 없는 역할에게 목록
            요청 자체를 보내지 않는다. 서버 게이트는 app/setup/router.py 가 따로 건다. */}
        <Route path="/setup" element={<SetupWizard />} />
        {/* PA-RC-0017: 시스템 설정·AI 관리·유지보수는 화면이 아니라 /settings의 탭이
            됐다(SettingsShell.jsx) — role 게이트도 그 안에서 탭 단위로 건다(옛 RequireRole과
            같은 role 집합을 SettingsShell의 TAB_DEFS가 그대로 물려받았다). 여기 남는 것은 옛
            주소 세 개가 죽은 링크나 대시보드로 튕기지 않고 정확한 탭으로 가게 하는
            리다이렉트뿐이다 — 권한 없는 역할이 옛 주소로 와도 SettingsShell이 그 탭을
            안 보여주고 첫 탭(시스템 정책)으로 떨어지므로 여기서 또 막을 필요가 없다.

            넷째 주소 `/notion-console`은 리다이렉트도 남기지 않고 지웠다. 리다이렉트가
            뜻이 있으려면 도착지가 있어야 하는데 그 도착지였던 '연동' 탭이 통째로 없어졌기
            때문이다. 없는 탭으로 보내면 SettingsShell이 주소를 정정해 '시스템 정책'을
            그리고, 사용자는 자기가 찾던 화면 대신 엉뚱한 화면을 보면서 왜 그런지 듣지
            못한다. 지금은 아래 catch-all이 「이 주소는 없습니다」를 정직하게 말한다. */}
        <Route path="/system" element={<Navigate to="/settings?tab=os" replace />} />
        <Route path="/llm-console" element={<Navigate to="/settings?tab=ai" replace />} />
        <Route path="/maintenance" element={<Navigate to="/settings?tab=policy" replace />} />
        {/* FN-01: GET /status는 CONSOLE_READ_ROLES(operator/admin/system_admin/auditor) —
            navConfig.js의 /mail 항목과 같은 role 집합. */}
        <Route path="/mail" element={<RequireRole roles={["operator", "admin", "system_admin", "auditor"]} help="이 화면은 운영자 이상만 사용할 수 있습니다."><MailStatus /></RequireRole>} />
        {/* PA-RC-0026: GET /api/admin/diagnostics/bundle은 CONSOLE_OPS_ROLES(operator/admin/
            system_admin) — /jobs와 같은 role 집합("헬스체크"는 authz.py의 console.ops가
            명시한다). 예전엔 CONSOLE_WRITE_ROLES(admin+)라 발표된 권한표보다 더 좁았다. */}
        <Route path="/diagnostics" element={<RequireRole roles={["operator", "admin", "system_admin"]} help="이 화면은 운영자, 관리자, 시스템 관리자만 사용할 수 있습니다."><Diagnostics /></RequireRole>} />
        <Route path="/dev-report" element={<RequireRole roles={["admin", "system_admin", "auditor"]} help="이 화면은 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다."><DevReport /></RequireRole>} />
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
        <Route path="/departments" element={departmentsElement} />
        {/* PA-RC-0024: 부서 상세도 같은 원리(같은 element, 인스턴스 유지) — OrgConsole은
            트리+DataScreen을 같이 그리므로 :id가 있으면 DataScreen 쪽 상세만 자동으로
            열리게 하는 배선은 registry/org.js의 departments onQuery에 있다. */}
        <Route path="/departments/:id" element={departmentsElement} />
        {/* 위 세 화면은 설정만으로 그려지지 않는다(트리 + 관리 패널) — 아래 일괄 등록에서 뺀다.
            같은 경로를 두 번 등록하면 어느 쪽이 이기는지가 라우터의 정렬 규칙에 달리게 된다.
            `registry` 가 아직 로드되기 전(null)에는 REGISTRY 기반 라우트가 하나도 없다 —
            그 사이에는 아래 catch-all 이 대시보드로 튕기는 대신 로딩 화면을 보인다. */}
        {/* 탭으로 합친 묶음 — 대표 주소와 옛 주소가 **같은 그릇**을 그리고, 옛 주소는 그
            자리에서 해당 탭이 열린다(리다이렉트가 아니라 기본 탭을 바꿔 준다 — 해시 쿼리를
            버리지 않기 위해서다). */}
        {registry && TAB_GROUPS.flatMap((g) => {
          const roles = SCREEN_ROLES[g.tabs[0].key];
          if (!sameRoles(g.tabs)) return [];   // 조립 실수를 화면에 내보내지 않는다
          const shellFor = (firstKey) => {
            const ordered = [...g.tabs].sort((a, b) => (a.key === firstKey ? -1 : b.key === firstKey ? 1 : 0));
            return (
              <RequireRole roles={roles} help={SCREEN_ROLE_HELP[g.tabs[0].key]}>
                <TabShell
                  area={g.area} title={g.title} idPrefix={g.path.slice(1)}
                  tabs={ordered.map((t) => ({
                    key: t.key,
                    label: t.label,
                    // 대부분은 설정 주도 목록이지만, 표로 답이 안 되는 탭은 자기 화면을 준다.
                    render: t.render || (() => <DataScreen config={registry[t.key]} embedded />),
                  }))}
                />
              </RequireRole>
            );
          };
          const routes = [<Route key={g.path} path={g.path} element={shellFor(g.tabs[0].key)} />];
          // 감사 로그는 상세 :id 라우트를 함께 쓴다(PA-RC-0024) — 그릇 안에서도 그대로다.
          if (g.path === "/audit") {
            routes.push(<Route key="/audit/:id" path="/audit/:id" element={shellFor("audit")} />);
          }
          g.tabs.forEach((t) => {
            const old = "/" + t.key;
            if (old === g.path) return;
            routes.push(<Route key={old} path={old} element={shellFor(t.key)} />);
          });
          return routes;
        })}
        {registry && Object.keys(registry).filter((key) => !ORG_CONSOLE_KEYS.includes(key) && !TAB_GROUP_KEYS.includes(key)).flatMap((key) => {
          const cfg = registry[key];
          const roles = cfg.roles || SCREEN_ROLES[key];
          const screen = <DataScreen config={cfg} />;
          const element = roles ? <RequireRole roles={roles} help={SCREEN_ROLE_HELP[key]}>{screen}</RequireRole> : screen;
          // 감사 로그의 :id 상세 라우트(PA-RC-0024)는 위 탭 묶음이 담당한다 — 여기 남은
          // 화면들은 목록 라우트 하나씩이다.
          return [<Route key={key} path={"/" + key} element={element} />];
        })}
        <Route path="*" element={registry ? <RouteNotFound /> : ROUTES_FALLBACK} />
      </Routes>
    </React.Suspense>
  );
}


export default AdminRoutes;
