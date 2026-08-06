import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Button from "@mui/material/Button";
import { useAuth } from "./auth.jsx";
import { Dashboard } from "../screens/Dashboard.jsx";
import { Users } from "../screens/Users.jsx";
import { Offboarding } from "../screens/Offboarding.jsx";
import { Settings } from "../screens/Settings.jsx";
import { Diagnostics, Maintenance } from "../screens/Ops.jsx";
import { SystemOps } from "../screens/SystemOps.jsx";
import { NotionConsole } from "../screens/NotionConsole.jsx";
import { LlmConsole } from "../screens/LlmConsole.jsx";
import { SetupWizard } from "../screens/SetupWizard.jsx";
import { DevReport } from "../screens/DevReport.jsx";
import { DataScreen } from "../screens/DataScreen.jsx";
import { Search } from "../screens/Search.jsx";
import { SchedulerCalendar } from "../screens/SchedulerCalendar.jsx";
import { REGISTRY } from "../screens/registry.js";
import { Card, Skeleton, ErrorState, EmptyState } from "../ui/kit.jsx";
import { SCREEN_ROLES, SCREEN_ROLE_HELP } from "./navConfig.js";

/* 관리자 콘솔 라우트
 *
 * App.jsx에서 분리해 별도 청크로 뺐다. 두 콘솔은 서로 다른 사람이 쓴다 — 일반 사용자는
 * 관리자 화면 20여 개를 평생 열지 않고, 관리자도 첫 진입에서 두 벌을 다 받을 이유가 없다.
 * 초기 번들이 예산(gzip 280KB)에 2KB까지 붙어 있었는데, 이 분리로 여유가 생긴다.
 */

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


function AdminRoutes() {
  return (
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


export default AdminRoutes;
