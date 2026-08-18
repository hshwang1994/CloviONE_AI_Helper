/* 역할 묶음 — **화면이 무엇을 보여 줄지** 판단할 때 쓰는 한 벌 (지시 21).
 *
 * ## 왜 한 곳에 모으는가
 *
 * 같은 목록(`["admin", "system_admin"]`)이 이름만 달리해 다섯 파일에 따로 살아 있었다:
 * `MailStatus.jsx::WRITE_ROLES`, `ops/opsHelpers.js::WRITE_ROLES`,
 * `registry/shared.js::WRITE_ROLES`, `settings/settingsRegistry.js::WRITE_ROLES`,
 * `navConfig.js::CONSOLE_WRITE`. 다섯이 같은 값이라 지금은 아무 문제가 없다 — 문제는
 * **하나가 바뀌는 날**이다. 그날 화면 넷은 새 규칙을, 하나는 옛 규칙을 말한다.
 *
 * ## 이것은 권한이 **아니다**
 *
 * 권한 판단의 정본은 서버다(`app/core/authz.py`). 여기 있는 값은 "이 버튼을 보여 줄까"
 * 라는 **표시 판단**일 뿐이고, 프런트에서 숨긴다고 막히는 것은 없다 — 서버가 같은 요청을
 * 403 으로 거절해야 막힌 것이다(지시 55). 그래서 이 파일의 이름과 값은 서버의 것과 **같은
 * 어휘를 쓴다**. 갈라지면 `role-sets-match-backend.test.js` 가 실패한다.
 */

export const ROLE_USER = "user";
export const ROLE_OPERATOR = "operator";
export const ROLE_AUDITOR = "auditor";
export const ROLE_ADMIN = "admin";
export const ROLE_SYSTEM_ADMIN = "system_admin";

/** 관리 콘솔 읽기 — 운영자군 전부 + 감사자. */
export const CONSOLE_READ_ROLES = [ROLE_OPERATOR, ROLE_ADMIN, ROLE_SYSTEM_ADMIN, ROLE_AUDITOR];

/** 관리 콘솔 설정 변경 — admin 이상. auditor 는 읽기 전용 가지라 절대 포함되지 않는다. */
export const CONSOLE_WRITE_ROLES = [ROLE_ADMIN, ROLE_SYSTEM_ADMIN];

/** 관리 콘솔 운영 동작 — 실행·재시도·헬스체크처럼 설정은 안 바꾸지만 부수효과가 있는 것. */
export const CONSOLE_OPS_ROLES = [ROLE_OPERATOR, ROLE_ADMIN, ROLE_SYSTEM_ADMIN];

/** 민감 집계 읽기 — 감사 로그, 개발자 월간 리포트. 사람에 대한 평가가 담겨 operator 를 뺀다. */
export const SENSITIVE_READ_ROLES = [ROLE_ADMIN, ROLE_SYSTEM_ADMIN, ROLE_AUDITOR];

/** 백업 생성·검증·복구, 시스템 설정. */
export const SYSTEM_ADMIN_ONLY = [ROLE_SYSTEM_ADMIN];

/** 사용자 콘텐츠 중재 — 집합으로 보면 CONSOLE_OPS_ROLES 와 같다(서버도 그렇다). */
export const MODERATOR_ROLES = [ROLE_OPERATOR, ROLE_ADMIN, ROLE_SYSTEM_ADMIN];

/** 그 역할이 이 묶음에 드는가. `roles.includes(role)` 을 화면마다 다시 쓰지 않게 한다. */
export function hasRole(roles, role) {
  return Array.isArray(roles) && roles.includes(role);
}
