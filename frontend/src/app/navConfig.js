import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import ManageAccountsOutlinedIcon from "@mui/icons-material/ManageAccountsOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import WorkOutlineRoundedIcon from "@mui/icons-material/WorkOutlineRounded";
import EventNoteOutlinedIcon from "@mui/icons-material/EventNoteOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import GroupsOutlinedIcon from "@mui/icons-material/GroupsOutlined";
import PersonOutlineRoundedIcon from "@mui/icons-material/PersonOutlineRounded";

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
export const SCREEN_ROLES = {
  users: ["admin", "system_admin"],
  jobs: ["operator", "admin", "system_admin"],
  departments: ["admin", "system_admin"],
  "job-titles": ["admin", "system_admin"],
  "org-tree": ["admin", "system_admin"],
  offboarding: ["admin", "system_admin"],
  backup: ["operator", "admin", "system_admin", "auditor"],
  audit: ["admin", "system_admin", "auditor"],
  // 권한 매트릭스는 규칙 표 그 자체라 사용자 데이터가 없다 — 운영자·감사자도 '내가 무엇을
  // 할 수 있는가'를 볼 수 있어야 한다(백엔드 CONSOLE_READ_ROLES와 같은 집합).
  rbac: ["operator", "admin", "system_admin", "auditor"],
};

/* 화면별 403 안내 — 기본 문구("관리자, 시스템 관리자만")는 실제 허용 역할이 더 넓은 화면에서
 * 누가 접근 가능한지를 실제보다 좁게 말해 헷갈리게 한다. */
export const SCREEN_ROLE_HELP = {
  jobs: "이 화면은 운영자, 관리자, 시스템 관리자만 사용할 수 있습니다.",
  audit: "이 화면은 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다.",
  backup: "이 화면은 운영자, 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다.",
  rbac: "이 화면은 운영자, 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다.",
};

export const NAV = [
  { group: "운영", icon: DashboardOutlinedIcon, items: [
    { to: "/dashboard", label: "대시보드" },
    { to: "/notifications", label: "알림" },
    { to: "/jobs", label: "작업 큐", roles: ["operator", "admin", "system_admin"] },
    { to: "/settings", label: "설정" },
    { to: "/audit", label: "감사 로그", roles: ["admin", "system_admin", "auditor"] },
    { to: "/backup", label: "백업", roles: ["operator", "admin", "system_admin", "auditor"] },
    { to: "/diagnostics", label: "진단", roles: ["admin", "system_admin"] },
    // GET /api/admin/settings(유지보수 모드가 담긴 응답)는 READ_ROLES까지 허용하는데 이 화면만
    // admin/system_admin으로 막혀 있었다 — 쓰기는 Ops.jsx의 canWrite가 따로 가드한다.
    { to: "/maintenance", label: "유지보수", roles: ["operator", "admin", "system_admin", "auditor"] },
  ] },
  { group: "사용자", icon: ManageAccountsOutlinedIcon, items: [
    { to: "/users", label: "사용자", roles: ["admin", "system_admin"] },
    { to: "/offboarding", label: "온보딩 · 오프보딩", roles: ["admin", "system_admin"] },
    { to: "/departments", label: "부서 관리", roles: ["admin", "system_admin"] },
    { to: "/org-tree", label: "조직도", roles: ["admin", "system_admin"] },
    { to: "/job-titles", label: "직책 관리", roles: ["admin", "system_admin"] },
    // 권한 매트릭스는 규칙 표라 읽기 전용 역할(운영자·감사자)에게도 보인다.
    { to: "/rbac", label: "권한 매트릭스" },
    { to: "/notion-mapping", label: "Notion 사용자 연결" },
  ] },
  { group: "연동", icon: LinkOutlinedIcon, items: [
    { to: "/integrations", label: "외부 연동" },
    { to: "/runners", label: "자동화 작업 실행기(러너)" },
    { to: "/workflows", label: "업무 자동화 흐름(워크플로)" },
  ] },
  { group: "콘텐츠", icon: ArticleOutlinedIcon, items: [
    { to: "/prompts", label: "프롬프트" },
    { to: "/policies", label: "정책" },
    { to: "/templates", label: "템플릿" },
  ] },
  { group: "자동화", icon: AutoAwesomeOutlinedIcon, items: [
    { to: "/schedules", label: "실행 일정(스케줄)" },
    { to: "/documents", label: "문서 자동 생성" },
    { to: "/dev-report", label: "개발자 월간 리포트", roles: ["admin", "system_admin", "auditor"] },
    { to: "/approvals", label: "승인" },
  ] },
];

/* 사용자(role=user) 콘솔 네비 — 관리자 셸과 같은 규격을 공유한다.
 *
 * '도우미' 그룹에서 'AI 도우미'가 빠졌다. AI는 이제 탭 하나가 아니라 어느 화면에서든 부르는
 * 전역 도우미이고(우하단 마스코트 버튼, 좁은 화면에서는 상단바 버튼), 이 그룹에는 스프린트
 * 회의만 남는다 — 저장된 계획(IDEAS_BACKLOG 부록 A)의 확정 방향이다.
 * 그룹 아이콘도 대화 말풍선에서 일정 아이콘으로 바꿨다. */
export const USER_NAV = [
  { group: "내 업무", icon: WorkOutlineRoundedIcon, items: [
    { to: "/me", label: "홈" },
    { to: "/my-tickets", label: "내 티켓" },
    { to: "/unassigned", label: "미할당 티켓" },
    { to: "/new-ticket", label: "새 티켓" },
  ] },
  { group: "도우미", icon: EventNoteOutlinedIcon, items: [
    { to: "/sprint", label: "스프린트 회의" },
  ] },
  { group: "문서", icon: DescriptionOutlinedIcon, items: [
    { to: "/team-docs", label: "문서" },
    { to: "/team-docs/trash", label: "휴지통" },
  ] },
  { group: "팀 공간", icon: GroupsOutlinedIcon, items: [
    { to: "/team-tickets", label: "팀 티켓" },
    // badge는 '어떤 수를 붙일지'만 고르는 키다. 실제 값은 AppShell의 useNavBadges가
    // 정한다 — 여기서 숫자를 알 수는 없고, 그렇다고 셸에 경로를 하드코딩하면
    // 다음 배지를 붙일 때 또 if가 는다.
    { to: "/chat-rooms", label: "채팅방", badge: "chatUnread" },
    { to: "/games", label: "놀이" },
    { to: "/board", label: "자유게시판" },
  ] },
  /* 내 정보(계획서 Phase 6 사용자 백로그). '내 업무' 그룹에 섞지 않은 이유: 그쪽은 '오늘 무엇을
   * 할까'를 고르는 곳이고 여기는 '나에 대한 것'을 고치거나 되돌아보는 곳이다. 섞으면 매일 쓰는
   * 네 항목 사이에 가끔 쓰는 세 항목이 끼어 매번 시선이 한 번씩 걸린다. */
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
  "/chat", "/chat-rooms", "/sprint", "/board", "/team-docs", "/games",
  // 프로필·업무량·활동은 '나에 대한 것'이라 역할과 무관하게 사용자 콘솔에 산다 —
  // 관리자가 자기 프로필을 열면 사용자 세그먼트로 넘어가고, 상단 세그먼트 탭이 그걸 보여 준다.
  "/profile", "/my-stats", "/activity",
];

export function inUserSegment(pathname) {
  return USER_SEG_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
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

/* 사이드바가 서랍으로 바뀌는 폭. 디자인 사양서와 기존 앱이 모두 860px이다. */
export const NAV_BREAKPOINT_PX = 860;

export const ROLE_KO = {
  user: "사용자", operator: "운영자", auditor: "감사자",
  admin: "관리자", system_admin: "시스템 관리자",
};
