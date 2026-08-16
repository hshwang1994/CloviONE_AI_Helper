import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import GavelOutlinedIcon from "@mui/icons-material/GavelOutlined";
import ManageAccountsOutlinedIcon from "@mui/icons-material/ManageAccountsOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
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

export const NAV = [
  // PA-RC-0017: 7그룹 39항목(IA-01이 만든 구조)을 5그룹 35항목으로 다시 짠다. 항목 넷
  // (시스템 설정·Notion 관리·AI 관리·유지보수)이 사라진 건 없어진 게 아니라 /settings의
  // 탭이 됐기 때문이다(SettingsShell.jsx) — 그 네 화면이 남기고 간 자리를 메우려고 다시
  // 채우지 않는다. 나머지 35는 **어느 화면도 새로 만들거나 지우지 않았다** — role·배지·
  // 아이콘도 그대로다, 다섯 묶음 중 어디 속하는가만 바뀐다. 갈 곳을 못 찾는 항목을 기준으로
  // 묶었다: 매일 오늘 상태를 보러 오는가(운영), 사람·조직·권한을 만지는가(사용자·권한),
  // 예약·승인처럼 자동으로 도는 일의 실행/한도인가(자동화), 외부 시스템이나 자동화가 쓰는
  // 재료(러너·워크플로·프롬프트류)인가(연동), 사후 점검·통제·완결성 확인인가(감사). 35/5=7 —
  // 다섯 다 정확히 7항목이라 "5그룹 이하, 그룹당 7항목 이하"(Acceptance Criteria)를
  // 여유 없이 딱 채운다. 이 배치는 완벽한 유일해가 아니라 여러 타당한 분류 중 하나다 —
  // 판단 근거는 DECISIONS.md에 남겼다.
  { group: "운영", icon: DashboardOutlinedIcon, items: [
    { to: "/dashboard", label: "대시보드", icon: "dashboard" },
    { to: "/notifications", label: "알림", badge: "notifUnread", icon: "bell" },
    { to: "/jobs", label: "작업 큐", roles: ["operator", "admin", "system_admin"], badge: "jobFailed", icon: "ticket" },
    { to: "/settings", label: "설정", icon: "settings" },
    { to: "/diagnostics", label: "진단", roles: ["admin", "system_admin"], icon: "diagnostics" },
    { to: "/backup", label: "백업", roles: ["operator", "admin", "system_admin", "auditor"], badge: "backupFailed", icon: "backup" },
    // FN-01: GET /api/admin/mail/status(진단)·POST /test(시험 발송)는 처음부터 있었는데
    // 띄우는 화면이 없어 SMTP 설정 오류(비밀번호 재설정 메일 등이 조용히 안 감)를 아무도
    // 못 봤다 — CONSOLE_READ_ROLES(operator/admin/system_admin/auditor)와 같은 role 집합.
    { to: "/mail", label: "메일 발송", roles: ["operator", "admin", "system_admin", "auditor"], icon: "mail" },
  ] },
  { group: "사용자와 권한", icon: ManageAccountsOutlinedIcon, items: [
    { to: "/users", label: "사용자", roles: ["admin", "system_admin"], icon: "users" },
    // WF1 R4 — "온보딩과 오프보딩"이라고 약속했지만 이 화면(Offboarding.jsx)은 퇴사자 티켓
    // 재배정 마법사뿐이다. 신규 입사자 계정을 만드는 실제 온보딩은 위 "/users"의 "+ 사용자
    // 추가"다 — 이 라벨이 온보딩도 여기서 한다고 오해하게 만들었다.
    { to: "/offboarding", label: "오프보딩", roles: ["admin", "system_admin"], icon: "users" },
    // 조직 관리·부서 관리·조직도는 AdminRoutes.jsx 에서 이미 같은 OrgConsole 로 합쳐졌다
    // (트리는 왼쪽 1/3, 관리 패널은 오른쪽 2/3 — OrgConsole.jsx 참조). 그런데 사이드바
    // 메뉴가 예전처럼 3개로 남아 있으면 클릭할 때마다 '다른 메뉴'가 활성화되며 OrgConsole
    // 이 다시 마운트돼 트리 선택 상태가 리셋된다(사용자 신고: "3개 항목으로 남아있어서
    // 3개 페이지처럼 보임"). 대표 경로 하나로 합친다 — /departments, /org-tree 로의 직접
    // 진입(북마크)은 AdminRoutes.jsx 가 여전히 처리하므로 라우팅은 그대로 둔다.
    { to: "/organizations", label: "조직 관리", roles: ["admin", "system_admin"], icon: "org" },
    { to: "/job-titles", label: "직책 관리", roles: ["admin", "system_admin"], icon: "jobtitle" },
    // 권한 매트릭스는 규칙 표라 읽기 전용 역할(운영자·감사자)에게도 보인다.
    { to: "/rbac", label: "권한 매트릭스", icon: "policy" },
    { to: "/notion-mapping", label: "Notion 사용자 연결", icon: "docs" },
    { to: "/impersonation", label: "대리 보기", roles: ["admin", "system_admin", "auditor"], icon: "impersonate" },
  ] },
  { group: "자동화", icon: AutoAwesomeOutlinedIcon, items: [
    { to: "/schedules", label: "실행 일정(스케줄)", icon: "schedule" },
    { to: "/scheduler-calendar", label: "실행 달력", icon: "sprint" },
    { to: "/documents", label: "문서 자동 생성", icon: "docs" },
    { to: "/approvals", label: "승인", badge: "approvalPending", icon: "check" },
    { to: "/approval-delegations", label: "승인 위임", icon: "check" },
    { to: "/ai-quotas", label: "AI 사용 상한", icon: "quota" },
    { to: "/dev-report", label: "개발자 월간 리포트", roles: ["admin", "system_admin", "auditor"], icon: "report" },
  ] },
  { group: "연동", icon: LinkOutlinedIcon, items: [
    { to: "/integrations", label: "외부 연동", icon: "integration" },
    { to: "/runners", label: "자동화 작업 실행기(러너)", icon: "runner" },
    { to: "/workflows", label: "업무 자동화 흐름(워크플로)", icon: "workflow" },
    // 프롬프트·정책·템플릿은 러너·워크플로가 실행 시 참조하는 재료라 여기 묶인다(자체 화면
    // '콘텐츠' 그룹은 PA-RC-0017에서 없앴다 — 항목 다섯 개만으로 최상위 그룹 하나를 쓰는
    // 것보다, 실제로 누가 쓰는가를 기준으로 기존 그룹에 흡수하는 편이 5그룹 상한과 맞았다).
    { to: "/prompts", label: "프롬프트", icon: "ai" },
    { to: "/policies", label: "정책", icon: "policy" },
    { to: "/templates", label: "템플릿", icon: "template" },
    { to: "/prompt-usage", label: "프롬프트 사용 통계", icon: "report" },
  ] },
  { group: "감사", icon: GavelOutlinedIcon, items: [
    { to: "/audit", label: "감사 로그", roles: ["admin", "system_admin", "auditor"], icon: "audit" },
    { to: "/audit-anomalies", label: "감사 이상 징후", roles: ["admin", "system_admin", "auditor"], icon: "audit" },
    { to: "/feature-flags", label: "기능 플래그", icon: "flag" },
    { to: "/announcements", label: "공지 배너", icon: "announce" },
    { to: "/restore-drills", label: "복구 리허설", icon: "backup" },
    // 최초 실행 셋업(9-3)은 SettingsShell 탭이 아니라(PA-RC-0017 상단 주석 참조) 여전히
    // 독립 화면이다 — "설정이 전부 끝났는가"를 확인하는 체크리스트라 사후 점검 성격의 이
    // 그룹에 둔다. `system_admin` 만인 이유는 SystemOps.jsx / app/setup/router.py와 같다.
    { to: "/setup", label: "초기 설정", roles: ["system_admin"], icon: "settings" },
    // registry/authoring.js에 화면(policy-usage)과 역할 게이트(SCREEN_ROLES 아래)는 있는데
    // 사이드바 항목만 빠져 있었다(IA-01) — 형제 항목 prompt-usage의 headerActions에서만
    // 갈 수 있었고, 직접 주소로만 닿을 수 있었다. 정책이 실제로 지켜지는가의 확인이라 여기 둔다.
    { to: "/policy-usage", label: "정책 사용 통계", icon: "report" },
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
    { to: "/me", label: "홈", icon: "home" },
    { to: "/my-tickets", label: "내 티켓", icon: "ticket" },
    { to: "/unassigned", label: "미할당 티켓", icon: "ticket" },
    { to: "/new-ticket", label: "새 티켓", icon: "plus" },
    /* 알림. 라우트(`/notifications`)는 UserRoutes 에 진작 있었는데 **메뉴 항목이 없었다** —
       그래서 일반 사용자의 왼쪽 사이드바에는 안 읽음 배지가 붙을 자리 자체가 없었다
       (`badge:"notifUnread"` 는 관리자 메뉴에만 선언돼 있었다). 사용자가 "신규 알람 하면
       왼쪽 사이드바에 뜨기로 했는데 왜 안 됨" 이라고 한 것이 이것이다.
       '내 업무' 그룹에 두는 이유: 티켓 배정·업무 인수처럼 **오늘 할 일을 바꾸는** 알림이
       대부분이라, 되돌아보는 자리('내 정보')가 아니라 매일 훑는 자리에 있어야 한다. */
    { to: "/notifications", label: "알림", badge: "notifUnread", icon: "bell" },
  ] },
  /* 기준 파일의 '도우미' 그룹에는 AI 도우미가 항목으로 있다. 예전에 뺐던 이유는 AI 가 탭
     하나가 아니라 어디서든 부르는 전역 도우미가 됐기 때문인데, 그러다 보니 사이드바만 보는
     사용자에게는 AI 로 가는 길이 안 보였다 — 우하단 FAB 과 상단바 버튼은 아이콘이라
     '무엇인지'가 글자로 읽히지 않는다. 기준대로 되살린다. */
  { group: "도우미", icon: EventNoteOutlinedIcon, items: [
    { to: "/chat", label: "AI 도우미", icon: "ai" },
    { to: "/sprint", label: "스프린트 회의", icon: "sprint" },
  ] },
  { group: "문서", icon: DescriptionOutlinedIcon, items: [
    { to: "/team-docs", label: "문서", icon: "docs" },
    { to: "/team-docs/trash", label: "휴지통", icon: "trash" },
  ] },
  { group: "팀 공간", icon: GroupsOutlinedIcon, items: [
    /* 프로젝트는 팀 티켓 **바로 위**에 둔다. 티켓은 그 안의 한 줄이고, 목록에서 프로젝트로
       올라갈 길이 없으면 사용자는 '내 티켓이 어느 계획의 일부인가'를 화면에서 알 수 없다.
       읽기는 역할 게이트가 없다(app/projects/router.py 의 읽기는 인증만 본다) — 프로젝트
       현황은 참여자 전원이 봐야 하는 화면이라 그렇게 만들어 두었다. */
    { to: "/projects", label: "프로젝트", icon: "project" },
    { to: "/team-tickets", label: "팀 티켓", icon: "ticket" },
    // badge는 '어떤 수를 붙일지'만 고르는 키다. 실제 값은 AppShell의 useNavBadges가
    // 정한다 — 여기서 숫자를 알 수는 없고, 그렇다고 셸에 경로를 하드코딩하면
    // 다음 배지를 붙일 때 또 if가 는다.
    { to: "/chat-rooms", label: "채팅방", badge: "chatUnread", icon: "chat" },
    { to: "/games", label: "놀이", icon: "game" },
    { to: "/board", label: "자유게시판", icon: "board" },
    /* 기능 개선 제안(7단계 #1). 게시판과 **같은 표·같은 API**를 종류만 바꿔 쓴다.
       메뉴를 자유게시판 바로 아래 두는 이유: 둘 다 '글을 쓰는 곳'이라 사람이 찾는 자리가
       같다. 문서나 티켓 쪽에 끼워 두면 제안하러 온 사람이 헤맨다. */
    { to: "/ideas", label: "기능 개선 제안", icon: "flag" },
  ] },
  /* 내 정보(계획서 Phase 6 사용자 백로그). '내 업무' 그룹에 섞지 않은 이유: 그쪽은 '오늘 무엇을
   * 할까'를 고르는 곳이고 여기는 '나에 대한 것'을 고치거나 되돌아보는 곳이다. 섞으면 매일 쓰는
   * 네 항목 사이에 가끔 쓰는 세 항목이 끼어 매번 시선이 한 번씩 걸린다. */
  { group: "내 정보", icon: PersonOutlineRoundedIcon, items: [
    { to: "/profile", label: "내 프로필", icon: "profile" },
    { to: "/my-stats", label: "내 업무량", icon: "report" },
    { to: "/activity", label: "내 활동", icon: "activity" },
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

export const NAV_BREAKPOINT_PX = 860;

export const ROLE_KO = {
  user: "사용자", operator: "운영자", auditor: "감사자",
  admin: "관리자", system_admin: "시스템 관리자",
};
