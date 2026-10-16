import { inUserSegment } from "./navConfig.js";

/* 서버가 실어 주는 딥링크(알림의 `related_route` · 내 활동의 `route`)를 이 사람이 실제로 열 수 있는가 (r23 #68).
 *
 * 서버의 경로 표(`app/notifications/destinations.py`)는 「경로는 권한과 무관하다」가 원칙이고, 역할 게이트는 프런트가 건다.
 * 두 가지를 본다.
 *   ① 일반 사용자는 언제나 사용자 콘솔이다(`App.jsx` 의 `useUserConsole`). 관리자 콘솔 경로(`/users` · `/jobs` …)는 그 사람에게
 *      「권한이 없습니다」 화면이다 — 사용자 콘솔 경로(`USER_SEG_PATHS`)만 열 수 있다.
 *   ② 관리자군도 그 화면이 부르는 API 의 읽기 역할이 더 좁으면 그 자리에서 403 이다 — `ROUTE_ROLES` 가 백엔드 라우터
 *      기준으로 그 역할을 적는다(`/approvals` · `/schedules` · `/jobs` 의 읽기는 `app/core/authz.py` 의 CONSOLE_READ_ROLES).
 * 예전에는 알림 종만 ②를 걸었고 내 활동은 아무것도 걸지 않아, 일반 사용자의 「로그인했습니다」 줄에 관리자 화면으로 가는
 * 「열기」가 섰다. 누르면 「권한이 없습니다」였다. */
export const ROUTE_ROLES = {
  "/users": ["admin", "system_admin"],
  "/jobs": ["operator", "admin", "system_admin", "auditor"],
  "/approvals": ["operator", "admin", "system_admin", "auditor"],
  "/schedules": ["operator", "admin", "system_admin", "auditor"],
};

/** 앱 안 경로만 받는다(`/…`, `//` 로 시작하는 바깥 주소는 아니다). 경로 부분(`?` · `#` 앞)을 돌려준다. */
export function routePath(route) {
  if (typeof route !== "string" || !route.startsWith("/") || route.startsWith("//")) return null;
  return route.split(/[?#]/)[0];
}

/** 이 역할이 `route` 를 열면 그 화면이 실제로 서는가. 역할을 아직 모르면 열 수 없다고 본다(누르면 막히는 단추를 먼저 세우지 않는다). */
export function routeReachable(route, role) {
  const path = routePath(route);
  if (!path || !role) return false;
  if (role === "user") return inUserSegment(path);
  const roles = ROUTE_ROLES[path];
  return !roles || roles.includes(role);
}
