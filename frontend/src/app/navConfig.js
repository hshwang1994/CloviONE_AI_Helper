import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import GavelOutlinedIcon from "@mui/icons-material/GavelOutlined";
import ManageAccountsOutlinedIcon from "@mui/icons-material/ManageAccountsOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import WorkOutlineRoundedIcon from "@mui/icons-material/WorkOutlineRounded";
import TopicOutlinedIcon from "@mui/icons-material/TopicOutlined";
import GroupsOutlinedIcon from "@mui/icons-material/GroupsOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PersonOutlineRoundedIcon from "@mui/icons-material/PersonOutlineRounded";
import { NAV_BREAKPOINT } from "../ui/theme.js";
import { CONSOLE_WRITE_ROLES } from "../lib/roles.js";

/* 사이드바 구조와 라우트 권한 표.
 *
 * App.jsx에서 분리했다 — 셸 마크업과 '사이트맵'이 한 파일에 섞여 있으면, 메뉴 하나 고치려고
 * 700줄짜리 파일을 열어야 한다. 여기가 이 앱의 사이트맵이다.
 *
 * 각 항목의 `to`는 해시 라우트다. `roles`가 있으면 그 역할만 항목을 본다 —
 * 백엔드 라우터 권한과 정확히 맞춰 '눌렀더니 403' 막다른 길을 없앤다.
 */

/* 화면(REGISTRY 및 커스텀)의 라우트 역할 게이트 — 나브만 숨기면 해시 직접 진입 시 껍데기가
 * 그려지고 API가 raw 403을 뱉는다. config.roles가 있으면 그걸 쓰고, 없으면 이 표로 감싼다.
 * 백엔드 라우터 레벨 권한과 정확히 맞춘다:
 *  - users: GET까지 admin+ (users/router.py)
 *  - jobs: operator/admin/system_admin (jobs/router.py, auditor 제외)
 *  - departments/job-titles: GET까지 admin+
 *  - backup: GET은 READ_ROLES 허용 — 쓰기만 registry에서 system_admin으로 막는다
 *  - audit: GET은 admin/system_admin/auditor만(operator 제외) */
const CONSOLE_READ = ["operator", "admin", "system_admin", "auditor"];
const CONSOLE_OPS = ["operator", "admin", "system_admin"];
// 값의 정본은 서버(app/core/authz.py)이고, 화면 쪽 사본은 lib/roles.js 한 곳이다(지시 21).
const CONSOLE_WRITE = CONSOLE_WRITE_ROLES;
const SENSITIVE_READ = ["admin", "system_admin", "auditor"];

export const SCREEN_ROLES = {
  // 관리자 화면은 **빠짐없이** 여기 있어야 한다. 이 표가 곧 사이드바 항목의 role 이 되고
  // (아래 `NAV`), 라우트 게이트가 되고(AdminRoutes.jsx), 명령 팔레트 필터가 된다.
  // 예전에는 nav 항목의 `roles` 와 이 표가 따로 있었고 35개 중 22개가 nav 쪽에 비어 있어,
  // 일반 사용자가 Ctrl+K 로 관리자 화면 22개를 발견할 수 있었다.
  dashboard: CONSOLE_READ,
  "admin-notifications": CONSOLE_READ,
  settings: CONSOLE_READ,          // 탭 단위 게이트는 SettingsShell.jsx 가 따로 건다
  diagnostics: CONSOLE_OPS,
  mail: CONSOLE_READ,
  schedules: CONSOLE_READ,
  documents: CONSOLE_READ,
  approvals: CONSOLE_READ,
  integrations: CONSOLE_READ,
  runners: CONSOLE_READ,
  workflows: CONSOLE_READ,
  prompts: CONSOLE_READ,
  policies: CONSOLE_READ,
  templates: CONSOLE_READ,
  integrity: CONSOLE_READ,
  "notion-mapping": CONSOLE_READ,
  "dev-report": SENSITIVE_READ,
  setup: ["system_admin"],
  users: CONSOLE_WRITE,
  jobs: ["operator", "admin", "system_admin"],
  organizations: ["admin", "system_admin"],
  departments: ["admin", "system_admin"],
  "job-titles": ["admin", "system_admin"],
  "org-tree": ["admin", "system_admin"],
  offboarding: ["admin", "system_admin"],
  backup: ["operator", "admin", "system_admin", "auditor"],
  audit: ["admin", "system_admin", "auditor"],
  // 권한 매트릭스는 규칙 표 그 자체라 사용자 데이터가 없다 — 운영자·감사자도 '내가 무엇을
  // 할 수 있는가'를 볼 수 있어야 한다(백엔드 CONSOLE_READ_ROLES와 같은 집합).
  rbac: ["operator", "admin", "system_admin", "auditor"],
  // ── 관리자 백로그 잔여(0033, PLAN Phase 6) ───────────────────────────────
  // 백엔드 게이트와 정확히 같은 집합으로 맞춘다 — 넓게 두면 '눌렀더니 403' 막다른 길이 되고,
  // 좁게 두면 권한이 있는 사람이 화면을 못 찾는다.
  impersonation: ["admin", "system_admin", "auditor"],   // 기록 조회 = SENSITIVE_READ_ROLES
  "audit-anomalies": ["admin", "system_admin", "auditor"],
  announcements: ["operator", "admin", "system_admin", "auditor"],
  "ai-quotas": ["operator", "admin", "system_admin", "auditor"],
  "feature-flags": ["operator", "admin", "system_admin", "auditor"],
  "approval-delegations": ["operator", "admin", "system_admin", "auditor"],
  "restore-drills": ["operator", "admin", "system_admin", "auditor"],
  "scheduler-calendar": ["operator", "admin", "system_admin", "auditor"],
  "prompt-usage": ["operator", "admin", "system_admin", "auditor"],
  "policy-usage": ["operator", "admin", "system_admin", "auditor"],
  // 탭 그릇의 대표 경로 — 안에 든 두 탭(policy-usage·prompt-usage)과 같은 집합이어야
  // 한다(AdminRoutes.jsx 의 sameRoles 가 조립 시점에 확인한다).
  "ai-usage": ["operator", "admin", "system_admin", "auditor"],
};

/* 화면별 403 안내 — 기본 문구("관리자, 시스템 관리자만")는 실제 허용 역할이 더 넓은 화면에서
 * 누가 접근 가능한지를 실제보다 좁게 말해 헷갈리게 한다. */
export const SCREEN_ROLE_HELP = {
  jobs: "이 화면은 운영자, 관리자, 시스템 관리자만 사용할 수 있습니다.",
  audit: "이 화면은 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다.",
  backup: "이 화면은 운영자, 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다.",
  rbac: "이 화면은 운영자, 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다.",
  impersonation: "이 화면은 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다. 대리 보기 시작은 관리자, 시스템 관리자만 할 수 있습니다.",
  "audit-anomalies": "이 화면은 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다.",
};

/* 화면 키(경로에서 슬래시를 뗀 것) → 이 항목을 볼 수 있는 역할.
 *
 * nav 항목에 `roles` 를 직접 적지 않는다. 두 벌을 두면 하나만 고쳐지고, 그때 증상은
 * "메뉴에는 보이는데 눌렀더니 403"(또는 그 반대)이라 눈에 잘 안 띈다.
 * `navRoles()` 가 이 표에서 읽어 붙인다 — 표에 없는 경로는 시험이 잡는다(nav-features.test.js).
 */
export function navRoles(to) {
  return SCREEN_ROLES[to.replace(/^\//, "")] || null;
}

/** 이 역할이 이 경로에 **도달할 수 있는가**. 링크를 살릴지 죽일지 정하는 자리다.
 *
 * 표에 없는 경로는 통과시킨다 — 사용자 콘솔 경로처럼 역할 게이트가 없는 화면이 그렇다.
 * 표에 있으면 그 목록이 전부다(라우트 게이트·사이드바·명령 팔레트와 같은 표).
 *
 * 쿼리·해시는 떼고 본다: `/settings?tab=policy` 는 `/settings` 와 같은 화면이고, 탭 단위
 * 게이트는 그 화면이 따로 건다(SettingsShell.jsx).
 *
 * ⚠️ 프런트의 판단은 **표시**를 위한 것이다. 권한의 정본은 서버다(불변규칙 §5) — 여기서
 * 통과한다고 API 가 열리지 않고, 여기서 막는다고 보안이 되는 것도 아니다. 목적은 '눌렀더니
 * 403' 막다른 길과 '권한이 있는데 링크가 죽어 있음'을 둘 다 없애는 것이다. */
export function canReach(path, role) {
  const clean = String(path || "").split(/[?#]/)[0];
  const allowed = navRoles(clean);
  return !allowed || (role != null && allowed.includes(role));
}

/** nav 정의에 role 을 붙여 돌려준다. 정의(무엇이 어느 묶음인가)와 권한(누가 보는가)을
 *  따로 적되 **합치는 자리는 하나**로 둔다. */
function withRoles(groups) {
  return groups.map((g) => ({
    ...g,
    items: g.items.map((it) => {
      const roles = navRoles(it.to);
      return roles ? { ...it, roles } : it;
    }),
  }));
}

export const NAV = withRoles([
  /* 관리자 사이드바 — 36항목·5그룹에서 31항목·6그룹으로 (지시 30 · 51 · 60).
   *
   * ## 무엇이 문제였나
   *
   * 항목이 많은 것 자체가 아니라 **묶음이 질문에 답하지 않았다.**
   *
   *   · `운영` 열한 개가 장애 대응(대시보드·작업 큐·진단), 설정(설정·초기 설정·기능 플래그),
   *     데이터 보호(백업·복구 리허설), 메일, 정합성 진단을 한 통에 담았다.
   *   · `자동화` 아홉 개가 실행 일정과 AI 재료(프롬프트·정책·템플릿)와 승인과 공지를 섞었다.
   *   · `감사` 다섯 개 중 셋이 감사가 아니라 **사용 통계 리포트**였다.
   *
   * ## 판단 기준 (지시 51)
   *
   * 기존 코드 구조가 IA 를 정하지 않는다. "이 일을 하려면 어디를 보겠는가"로 정하고, 같은
   * 질문에 답하는 화면끼리 묶었다. 짝을 이루는 다섯은 탭으로 합쳤다(AdminRoutes.jsx
   * TAB_GROUPS) — 백업↔복구 리허설, 승인↔승인 위임, 감사 로그↔이상 징후,
   * 정책 사용↔프롬프트 사용, 실행 일정↔실행 달력. 다섯 짝 모두 역할 집합이 같아서 합쳐도
   * RBAC 가 부서지지 않는다.
   *
   * **합치지 않은 것도 근거가 있다.**
   *   · `조직 관리`(OrgConsole)는 이미 조직·부서·조직도를 내부 전환으로 담고 있다. 거기에
   *     `직책 관리`를 바깥 탭으로 또 씌우면 탭이 두 겹이 된다 — 지시 60 이 경고하는 "복잡도가
   *     탭으로 이동"이 정확히 그 모양이다. 형제 항목으로 둔다.
   *   · `오프보딩`은 목록이 아니라 마법사다(SettingsShell 이 '초기 설정'을 탭으로 안 묶은
   *     것과 같은 이유). 사용자 상세의 넘침 메뉴에서도 닿지만, 사이드바에서 지우면 그 기능이
   *     있다는 사실 자체를 모르게 된다.
   *
   * ## 옮긴 것
   *   · 설정·초기 설정·기능 플래그·공지 배너 → 새 `설정` 묶음. 공지 배너는 자동화가 아니라
   *     "무엇을 사용자에게 보여 줄지" 설정이다.
   *   · 프롬프트·정책·템플릿·AI 사용 상한·AI 사용 통계 → 새 `AI` 묶음. 흩어져 있던 AI 재료가
   *     한 자리에 모인다(지시 30 이 예로 든 재배치).
   *   · 자동화와 연동을 한 묶음으로. 실행 일정·문서 자동 생성이 타고 흐르는 배관이 외부 연동·
   *     러너·워크플로다 — 둘을 갈라 두면 "왜 안 돌지"를 두 묶음에서 찾아야 한다.
   *   · 조직 정합성·백업·메일 발송은 운영에 남는다(장애·데이터 보호·전달 상태).
   */
  { group: "운영", icon: DashboardOutlinedIcon, items: [
    { to: "/dashboard", label: "대시보드" },
    // 관리자 알림은 **사용자 알림과 다른 경로**다(0060). 같은 canonical path 를 두 콘솔이
    // 공유하면 어느 쪽에서 눌러도 상대 콘솔로 튕긴다 — 경로가 콘솔을 정하기 때문이다.
    { to: "/admin-notifications", label: "관리 알림", badge: "adminNotifUnread" },
    { to: "/jobs", label: "작업 큐", badge: "jobFailed" },
    { to: "/diagnostics", label: "진단" },
    { to: "/integrity", label: "조직 정합성" },
    // 백업 화면은 '복구 리허설' 탭을 함께 갖는다 — 백업이 있는가와 그것이 실제로 복구되는가는
    // 한 질문의 앞뒤다.
    { to: "/backup", label: "백업", badge: "backupFailed" },
    { to: "/mail", label: "메일 발송" },
  ] },
  { group: "설정", icon: SettingsOutlinedIcon, items: [
    { to: "/settings", label: "설정" },
    { to: "/setup", label: "초기 설정" },
    { to: "/feature-flags", label: "기능 플래그" },
    { to: "/announcements", label: "공지 배너" },
  ] },
  { group: "사용자와 권한", icon: ManageAccountsOutlinedIcon, items: [
    { to: "/users", label: "사용자" },
    // WF1 R4 — "온보딩과 오프보딩"이라고 약속했지만 이 화면(Offboarding.jsx)은 퇴사자 티켓
    // 재배정 마법사뿐이다. 신규 입사자 계정을 만드는 실제 온보딩은 위 "/users"의 "사용자
    // 추가"다 — 이 라벨이 온보딩도 여기서 한다고 오해하게 만들었다.
    { to: "/offboarding", label: "오프보딩" },
    // 조직 관리·부서 관리·조직도는 AdminRoutes.jsx 에서 이미 같은 OrgConsole 로 합쳐졌다.
    // 대표 경로 하나만 메뉴에 둔다 — /departments, /org-tree 직접 진입(북마크)은 여전히 산다.
    { to: "/organizations", label: "조직 관리" },
    { to: "/job-titles", label: "직책 관리" },
    { to: "/rbac", label: "권한 매트릭스" },
    // 승인 화면은 '승인 위임' 탭을 함께 갖는다 — 누가 승인하는가와 그 권한을 누구에게
    // 넘겼는가는 같은 질문이다.
    { to: "/approvals", label: "승인", badge: "approvalPending" },
    { to: "/notion-mapping", label: "Notion 사용자 연결" },
    { to: "/impersonation", label: "대리 보기" },
  ] },
  { group: "자동화와 연동", icon: AutoAwesomeOutlinedIcon, items: [
    // 실행 일정 화면은 '달력' 탭을 함께 갖는다 — 같은 데이터의 두 표현이다.
    { to: "/schedules", label: "실행 일정" },
    { to: "/documents", label: "문서 자동 생성" },
    { to: "/integrations", label: "외부 연동" },
    { to: "/runners", label: "자동화 작업 실행기" },
    { to: "/workflows", label: "업무 자동화 흐름" },
  ] },
  { group: "AI", icon: SmartToyOutlinedIcon, items: [
    { to: "/prompts", label: "프롬프트" },
    { to: "/policies", label: "정책" },
    { to: "/templates", label: "템플릿" },
    { to: "/ai-quotas", label: "사용 상한" },
    // 정책 사용 통계와 프롬프트 사용 통계는 같은 모양의 리포트 둘이었다 — 한 화면의 탭이다.
    { to: "/ai-usage", label: "사용 통계" },
  ] },
  { group: "감사", icon: GavelOutlinedIcon, items: [
    // 감사 로그 화면은 '이상 징후' 탭을 함께 갖는다 — 이상 징후는 감사 로그 위의 파생 뷰다.
    { to: "/audit", label: "감사 로그" },
    { to: "/dev-report", label: "개발자 월간 리포트" },
  ] },
]);

/* 사용자(role=user) 콘솔 네비 — 관리자 셸과 같은 규격을 공유한다.
 *
 * '도우미' 그룹에서 'AI 도우미'가 빠졌다. AI는 이제 탭 하나가 아니라 어느 화면에서든 부르는
 * 전역 도우미이고(우하단 마스코트 버튼, 좁은 화면에서는 상단바 버튼), 이 그룹에는 스프린트
 * 회의만 남는다 — 저장된 계획(IDEAS_BACKLOG 부록 A)의 확정 방향이다.
 * 그룹 아이콘도 대화 말풍선에서 일정 아이콘으로 바꿨다. */
export const USER_NAV = [
  // 0060 §4: '내 업무'는 **나에게 직접 관련된 일**만 둔다. 미할당 티켓은 아직 내 일이 아니라
  // 팀이 함께 나눠 갖는 일이므로 '팀 공간'으로 옮긴다. 개인 결재함(/my-approvals)은 새로
  // 생겼다 — 승인은 위임받은 일반 사용자에게도 오는 개인 업무인데, 예전에는 관리자 콘솔에만
  // 화면이 있어서 그 사람은 알림만 받고 들어갈 곳이 없었다.
  /* 지시 58 재검토(2026-08-19, D-166). 바꾼 것 셋과 그 근거:
   *
   * ① `알림` 은 **그대로 둔다.** 지시 1 의 "단일 진입점은 종"을 이 항목까지 지우라는 뜻으로
   *    읽을 뻔했는데, 이 항목은 사용자가 직접 요구해서 생긴 것이다("신규 알람 하면 왼쪽
   *    사이드바나 알림창에 뜨기로 했는데 왜 안 됨??" — `user-nav-notifications.test.jsx`).
   *    지시 1 이 없앤 것은 **전 라우트 상단의 장애 띠와 헤더 칩**이고, 알림 전체 목록으로
   *    가는 길은 다른 것이다. 종은 "왔다"를 알리고 이 항목은 "전부 보기"로 간다.
   * ② `도우미` 그룹을 해체했다. `AI 도우미` 와 `스프린트 회의` 는 같은 부류가 아니다 —
   *    하나는 내가 쓰는 도구, 하나는 팀이 함께 보는 회의 화면이다. 그룹 이름이 둘 중
   *    하나도 설명하지 못했고, 그룹 아이콘(달력)은 스프린트만 가리켰다.
   * ③ `팀 공간` 8항목을 성격으로 갈랐다. 업무(프로젝트·티켓·문서·회의)와 소통·놀이가
   *    한 서랍에 있으면, 일하러 온 사람도 놀러 온 사람도 목록 전체를 훑어야 한다.
   */
  { group: "내 업무", icon: WorkOutlineRoundedIcon, items: [
    { to: "/me", label: "홈" },
    { to: "/my-tickets", label: "내 티켓" },
    { to: "/new-ticket", label: "새 티켓" },
    { to: "/my-approvals", label: "승인", badge: "myApprovalPending" },
    { to: "/notifications", label: "알림", badge: "notifUnread" },
    // AI 도우미는 내 업무를 돕는 도구다 — 팀 회의 화면과 묶이는 것보다 여기가 정확하다.
    { to: "/chat", label: "AI 도우미" },
  ] },
  { group: "팀 업무", icon: TopicOutlinedIcon, items: [
    { to: "/projects", label: "프로젝트" },
    { to: "/team-tickets", label: "팀 티켓" },
    // 미할당은 "우리 팀이 함께 나눠 가질 일" 이다 — 개인 업무가 아니라 팀의 일이고,
    // 0060 부터 실제로도 팀(프로젝트) 범위로 좁혀진다.
    { to: "/unassigned", label: "미할당 티켓" },
    { to: "/sprint", label: "스프린트 회의" },
    { to: "/team-docs", label: "문서" },
  ] },
  { group: "팀 공간", icon: GroupsOutlinedIcon, items: [
    { to: "/chat-rooms", label: "채팅방", badge: "chatUnread" },
    { to: "/board", label: "자유게시판" },
    { to: "/ideas", label: "기능 개선 제안" },
    { to: "/games", label: "놀이" },
  ] },
  /* 내 정보. '내 업무' 그룹에 섞지 않은 이유: 그쪽은 '오늘 무엇을 할까'를 고르는 곳이고
   * 여기는 '나에 대한 것'을 고치거나 되돌아보는 곳이다. */
  { group: "내 정보", icon: PersonOutlineRoundedIcon, items: [
    { to: "/profile", label: "내 프로필" },
    { to: "/my-stats", label: "내 업무량" },
    { to: "/activity", label: "내 활동" },
  ] },
];

/* 사용자 세그먼트에 속하는 경로 — 관리자군이 상단 '사용자' 탭을 눌렀을 때 이 경로들에서
 * UserBody(개인 업무 콘솔)를 렌더한다. /notifications 는 관리자 세그먼트 소유(알림은 상단 벨).
 * role=user 는 세그먼트와 무관하게 항상 UserBody. */
export const USER_SEG_PATHS = [
  "/me", "/my-tickets", "/unassigned", "/new-ticket", "/tickets", "/team-tickets",
  "/chat", "/chat-rooms", "/sprint", "/board", "/ideas", "/team-docs", "/games",
  // 프로젝트는 사용자 콘솔 소유다. 관리자 세그먼트에 두면 관리자군이 프로젝트를 열 때
  // 사이드바가 관리자 메뉴로 통째로 바뀌고, 그 메뉴에는 프로젝트 항목이 없어 선택이 사라진다.
  "/projects",
  // 프로필·업무량·활동은 '나에 대한 것'이라 역할과 무관하게 사용자 콘솔에 산다 —
  // 관리자가 자기 프로필을 열면 사용자 세그먼트로 넘어가고, 상단 세그먼트 탭이 그걸 보여 준다.
  // 화면 강조색(PA-RC-0022, /my-display)도 같은 부류다 — 브라우저 로컬 저장이라 역할이
  // 아예 무관하다.
  "/profile", "/my-stats", "/activity", "/my-display",
  // 통합 검색(VIS-72) — ROUTE_OWNER는 이미 "/search": "/me"로 사용자 콘솔 소유라 선언하는데
  // 여기 목록엔 빠져 있었다. 관리자군이 Ctrl+K로 검색을 열면 상단 세그먼트가 관리자로
  // 튕기고 사이드바가 통째로 관리자 메뉴로 바뀌었다 — 위 /projects와 같은 부류의 결함
  // (그건 이미 한 번 고쳐졌는데 /search는 안 고쳐져 있었다).
  "/search",
  // 알림(0060). `USER_NAV` 에 항목이 있는데 이 목록에 없어서, 관리자군이 사용자 탭에서
  // 알림을 누르면 **사이드바가 통째로 관리자 메뉴로 바뀌었다** — `/projects`·`/search` 와
  // 정확히 같은 부류의 결함인데 이것만 안 고쳐져 있었다. 관리자 알림은 이제 다른 경로
  // (`/admin-notifications`)라 두 콘솔이 같은 canonical path 를 공유하지 않는다.
  "/notifications",
  // 개인 결재함 — 승인은 위임받은 일반 사용자에게도 오는 개인 업무다.
  "/my-approvals",
];

export function inUserSegment(pathname) {
  return USER_SEG_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

/* 관리 범위(부서/조직)가 **실제로 걸리는** 경로 (ScopeBar).
 *
 * `ScopeBar` 는 라우트를 안 가리고 모든 화면에 "이 범위 밖의 항목은 목록에 나오지
 * 않습니다"를 단언했다. 그런데 서버가 실제로 범위를 거는 곳은 백엔드 서비스 계층에서
 * `app/core/scope.py::build_scope`/`apply_user_scope` 를 부르는 모듈뿐이다 - 게시판·놀이·
 * 알림은 부서 범위를 안 건다(`app/board/repository.py` 가 "사내 공지판이다 … 부서로 좁히지는
 * 않는다"고 명시한다). 부서가 배정된 일반 사용자에게는 `/board` 를 열 때마다 그 자리에서
 * 거짓말이 됐다.
 *
 * 이 목록은 범위를 거는 백엔드 모듈과 1:1 이다 - 새로 범위를 걸기 시작하면 여기도 넣어야
 * ScopeBar 가 그 화면에서도 경고를 띄운다:
 *   tickets    → build_scope   → /my-tickets, /unassigned, /new-ticket, /team-tickets, /tickets/:id
 *   team_docs  → build_scope   → /team-docs
 *   trash      → build_scope   → /team-docs/trash
 *   sprints    → build_scope   → /sprint
 *   users      → apply_user_scope → /users
 *   org        → apply_user_scope → /organizations, /departments, /org-tree
 *   offboarding→ build_scope   → /offboarding
 */
export const SCOPE_ENFORCED_PATHS = [
  "/my-tickets", "/unassigned", "/new-ticket", "/team-tickets", "/tickets",
  "/team-docs",
  "/sprint",
  // 0060: 프로젝트는 처음부터 범위가 걸렸는데 이 목록에 없어서 안내가 안 떴다. 반대로
  // `/unassigned` 는 목록에 있는데 서버가 아무것도 안 걸러 그 자리에서 거짓말이었다 —
  // 이제 둘 다 실제 동작과 맞는다.
  "/projects",
  "/users", "/offboarding", "/organizations", "/departments", "/org-tree",
];

export function isScopeEnforcedRoute(pathname) {
  return SCOPE_ENFORCED_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

/* 현재 경로에 '가장 길게 맞는' 항목만 활성으로 본다.
 * 접두 매칭이면 /team-docs 가 /team-docs/trash 에서도 활성이라 '문서'와 '휴지통'이 동시에
 * 켜졌다(실제 사용자 신고 버그). 가장 구체적인 항목 하나만 활성이 되게 한다. */
export function bestNavMatch(pathname, paths) {
  let best = null;
  for (const p of paths) {
    if (pathname === p || pathname.startsWith(p + "/")) {
      if (!best || p.length > best.length) best = p;
    }
  }
  return best;
}

/* 메뉴에 **자기 항목이 없는** 화면이 어느 메뉴에 속하는가 (사용자 지적 #14).
 *
 * `bestNavMatch` 는 nav 항목 경로의 접두사만 본다. 그런데 상세 화면들은 목록과 **다른
 * 접두사**를 쓴다 — 목록은 `/my-tickets`·`/unassigned`·`/team-tickets` 인데 상세는
 * `/tickets/:id` 다. 그래서 티켓을 열면 어느 메뉴에도 안 걸려 **선택 표시가 통째로 사라졌다.**
 * `/search`·`/profile` 도 같다(사이드바 항목이 없다).
 *
 * 여기 한 곳에 모으는 이유: 라우트를 새로 만들 때마다 사이드바 코드를 고치게 하면 반드시
 * 잊는다 — 그리고 그때 증상은 "어떤 화면에서만 메뉴가 꺼진다" 라 눈에 잘 안 띈다.
 *
 * ⚠️ 이건 **폴백**이다. 목록에서 들어온 경우에는 `location.state.from` 이 이긴다 —
 * '미할당' 에서 연 티켓은 '미할당' 이 켜져 있어야 사용자가 어디서 왔는지 안다.
 */
export const ROUTE_OWNER = {
  "/tickets": "/my-tickets",       // 티켓 상세 — 기본 소속은 '내 티켓'
  "/search": "/me",                // 통합 검색은 자기 메뉴가 없다 — 홈에 딸린 기능이다
  /* 프로젝트 상세(`/projects/:id`)의 소속을 **적어 둔다.**
   *
   * 지금은 목록 항목(`/projects`)이 접두사로도 맞아떨어져서 `bestNavMatch` 만으로도 켜진다.
   * 그래도 여기 적는 이유는 그 우연이 조용히 깨지기 때문이다 — 목록 경로를 언젠가
   * `/my-projects` 같은 것으로 옮기면 상세에서 선택 표시가 소리 없이 사라진다. 여기 적어
   * 두면 그때 위의 "목적지는 실제로 존재하는 메뉴다" 검사가 **먼저 실패한다**(nav-active.test.js). */
  "/projects": "/projects",
  /* 조직 관리·부서 관리·조직도가 사이드바 항목 하나(`/organizations`)로 합쳐진 뒤(사이드바
   * 조직 메뉴 통합, nav-org-menu.test.js) `/departments`·`/org-tree`는 **자기 메뉴 항목이
   * 없는 화면**이 됐다 — `/tickets/:id`·`/search`와 같은 부류다. 그런데 이 둘은 라우팅만
   * 유지됐을 뿐 여기(ROUTE_OWNER)에 등록되지 않아, `location.state.from` 없이 도달하면
   * (registry/org.js의 "조직도에서 보기"/"부서 관리로 이동" 액션은 `window.location.hash`
   * 직접 대입이라 state가 없다, Users.jsx의 부서 안내 링크는 새 탭이라 애초에 history state가
   * 없다, 북마크·주소창 직접 입력도 마찬가지) 사이드바 선택 표시가 통째로 사라졌다. */
  "/departments": "/organizations",
  "/org-tree": "/organizations",
};
// (`/profile`·`/my-stats`·`/activity` 는 **자기 메뉴 항목이 있다** — 여기 넣으면 안 된다.
//  넣으면 그 화면에서 자기 메뉴 대신 홈이 켜진다. `nav-active.test.js` 가 그걸 못박는다.)

/* 지금 켜져야 할 메뉴 경로. `paths` 는 실제로 그려진 항목들이다.
 *
 * `from` 은 목록 화면이 상세로 넘길 때 실어 주는 출처(`location.state.from`)다. 그것이
 * 실제 메뉴 항목이면 그대로 쓴다 — 그게 사용자가 방금 누른 그 메뉴이기 때문이다.
 */
export function activeNavPath(pathname, paths, from) {
  const direct = bestNavMatch(pathname, paths);
  if (direct) return direct;
  if (from && paths.includes(from)) return from;
  const owner = ROUTE_OWNER[bestNavMatch(pathname, Object.keys(ROUTE_OWNER)) || ""];
  return owner && paths.includes(owner) ? owner : null;
}

/* PA-RC-0039: 지금 경로가 속한 사이드바 그룹 이름 — kit.jsx의 PageHeader가 crumbRoot를
 * 유도할 때 쓴다(사이드바 하이라이트와 같은 activeNavPath를 재사용하므로 "지금 켜진 메뉴"와
 * "breadcrumb 뿌리"가 서로 다른 답을 낼 수 없다 — 같은 함수라 어긋날 방법이 없다). 상세
 * 화면(`/team-docs/trash` 등 자기 메뉴 항목이 없는 경로)도 activeNavPath의 ROUTE_OWNER/
 * prefix 폴백을 그대로 물려받는다. */
export function groupForPath(nav, pathname, from) {
  const paths = nav.flatMap((g) => (g.items || []).map((it) => it.to));
  const active = activeNavPath(pathname, paths, from);
  if (!active) return null;
  const owner = nav.find((g) => (g.items || []).some((it) => it.to === active));
  return owner ? owner.group : null;
}

/* 사이드바가 서랍으로 바뀌는 폭. 디자인 사양서와 기존 앱이 모두 860px이다. */
/* 기능 플래그 → 메뉴 (X4).
 *
 * 예전에는 플래그가 **서버만** 껐다. 껐다고 믿은 메뉴가 사이드바에 그대로 남고, 눌리고,
 * 404 를 뱉었다 — 운영자는 "껐는데 왜 보이지" 를, 사용자는 "눌렀는데 없다" 를 겪는다.
 * 올바른 패턴이 `home/readers.py` 에 이미 있었는데 **한 화면에만** 적용돼 있었다.
 *
 * 화면에서 감추는 것은 **편의일 뿐 통제가 아니다** — 라우터가 여전히 각자 막는다.
 * 여기서 감추는 이유는 '눌러 봐야 거절당하는 메뉴' 를 안 그리기 위해서다.
 */
export const NAV_FEATURE_FLAG = {
  "/chat": "chat_enabled",
  "/team-docs": "team_docs_enabled",
  "/team-docs/trash": "team_docs_enabled",
  "/chat-rooms": "team_chat_enabled",
  "/games": "games_enabled",
  "/board": "board_enabled",
  // 같은 라우터(/api/board)를 쓰므로 플래그도 같다 — 게시판을 끄면 제안 게시판도 404 다.
  // 여기에 안 적으면 꺼진 기능의 메뉴가 남아 '눌러 봐야 거절당하는' 항목이 된다.
  "/ideas": "board_enabled",
};

/** 플래그로 꺼진 항목을 뺀 메뉴. `features` 가 없으면(로딩 전·구버전) 그대로 둔다 —
 *  값을 모를 때 감추면 새로고침마다 메뉴가 깜빡인다. */
export function navWithFeatures(nav, features) {
  if (!features) return nav;
  const on = (to) => {
    const flag = NAV_FEATURE_FLAG[to];
    return !flag || features[flag] !== false;
  };
  return nav
    .map((group) => (group.items ? { ...group, items: group.items.filter((i) => on(i.to)) } : group))
    // 항목이 하나도 안 남은 묶음은 제목만 남아 빈 자리가 된다.
    .filter((group) => !group.items || group.items.length > 0);
}

/* PA-RC-0017: 레일 상단 내비 필터(acceptance_criteria 7 — "두 글자를 입력하면 목적지가
 * 좁혀진다"). navWithFeatures와 같은 모양(map으로 items 거르고 빈 그룹은 filter로 뺀다) —
 * 필터도 "메뉴를 좁힌다"는 점에서 같은 종류의 변환이라 새 자료구조를 만들지 않는다.
 * 그룹 이름 자체가 질의와 맞으면(예: "감사") 그 그룹의 항목은 다 남긴다 — 사람이 그룹명을
 * 치면 "그 묶음을 보여줘"라는 뜻이지 그룹명이 항목 라벨에 포함된 것을 찾는 게 아니다. */
export function filterGroupsByQuery(nav, query) {
  const q = (query || "").trim().toLowerCase();
  if (!q) return nav;
  return nav
    .map((group) => {
      const groupMatches = group.group.toLowerCase().includes(q);
      const items = groupMatches
        ? group.items
        : (group.items || []).filter((i) => i.label.toLowerCase().includes(q));
      return { ...group, items };
    })
    .filter((group) => group.items.length > 0);
}

export const NAV_BREAKPOINT_PX = NAV_BREAKPOINT;

export const ROLE_KO = {
  user: "사용자", operator: "운영자", auditor: "감사자",
  admin: "관리자", system_admin: "시스템 관리자",
};
