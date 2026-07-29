import React, { useEffect, useState, useRef } from "react";
import { HashRouter, Routes, Route, NavLink, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth.jsx";
import { api } from "../lib/api.js";
import { Chat } from "../screens/Chat.jsx";
import { Dashboard } from "../screens/Dashboard.jsx";
import { Users } from "../screens/Users.jsx";
import { Settings } from "../screens/Settings.jsx";
import { Diagnostics, Maintenance } from "../screens/Ops.jsx";
import { DevReport } from "../screens/DevReport.jsx";
import { MyWork, MyTickets, Unassigned, NewTicket } from "../screens/MyTickets.jsx";
import { Board } from "../screens/Board.jsx";
import { BoardPost } from "../screens/BoardPost.jsx";
import { TeamDocs } from "../screens/TeamDocs.jsx";
import { TeamDoc } from "../screens/TeamDoc.jsx";
import { Games } from "../screens/Games.jsx";
import { GameRoom } from "../screens/GameRoom.jsx";
import { DataScreen } from "../screens/DataScreen.jsx";
import { REGISTRY } from "../screens/registry.js";
import { NotificationBell } from "./NotificationBell.jsx";
import { Card, Skeleton, ErrorState, EmptyState, Modal, Badge } from "../ui/kit.jsx";
import { fmtDateTime } from "../lib/format.js";

/* 역할 가드 — 나브 항목만 숨기면 해시 URL 직접 진입 시 죽은 껍데기(수집 버튼 없는 진단 등)가
 * 그려진다. 라우트 자체를 역할로 감싸 권한 없는 사용자에겐 명확한 '권한 없음' 안내를 보인다. */
function RequireRole({ roles, children, help }) {
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  if (auth.isLoading) return <Card><Skeleton /></Card>;
  // 세션 만료(401)는 '권한 없음'과 다르다, /api/me가 401이면 auth.data는 비어 있고 role도
  // 없어 아래 권한 분기와 겹쳐 보이지만, 실제로는 재로그인하면 바로 풀리는 문제다. 권한
  // 없음처럼 영구적인 것으로 보이는 EmptyState 대신 로그인 링크가 있는 ErrorState를 보여준다.
  if (auth.isError) {
    // ErrorState의 401 분기는 onRetry가 있어도 항상 로그인 링크를 우선 보인다(내부 isAuth
    // 체크). 그 밖의 상태(네트워크 오류, 5xx 등, .status가 아예 없는 경우 포함)는 onRetry가
    // 없으면 어떤 버튼도 없는 진짜 막다른 화면이 된다, /api/me 재조회로 복구 경로를 준다.
    // Card로 감싸지 않는다, 같은 세션-오류류를 보여주는 바로 아래 EmptyState 분기(권한 없음)와
    // DataScreen.jsx가 쓰는 전 화면 ErrorState/EmptyState는 전부 카드 없이 맨몸으로 그린다.
    return <ErrorState error={auth.error} onRetry={() => auth.refetch()} />;
  }
  if (!role || !roles.includes(role)) {
    return <EmptyState icon={null} title="권한이 없습니다" help={help || "이 화면은 관리자, 시스템 관리자만 사용할 수 있습니다."} action={<a className="k-btn k-btn--primary" href="#/">대시보드로 이동</a>} />;
  }
  return children;
}

/* 화면(REGISTRY 및 커스텀)의 라우트 역할 게이트 — 나브만 숨기면 해시 직접 진입 시 껍데기가
 * 그려지고 API가 raw 403을 뱉는다(RequireRole 패턴이 막으려던 바로 그 막다른 길). config.roles가
 * 있으면 그걸 쓰고, 없으면 이 표로 라우트를 감싼다. 백엔드 라우터 레벨 권한과 정확히 맞춘다:
 *  - users: GET까지 admin+ (users/router.py). 커스텀 라우트라 AdminBody에서 직접 감싼다.
 *  - jobs: operator/admin/system_admin (jobs/router.py, auditor 제외).
 *  - departments/job-titles: GET까지 admin+.
 *  - backup: GET은 READ_ROLES(operator/admin/system_admin/auditor) 허용 — 쓰기 액션만
 *    registry에서 system_admin으로 막으므로 라우트는 읽기 역할까지 연다(예전 system_admin 전용
 *    게이트는 대시보드의 '백업 관리' 버튼·경고가 닿는 유일한 경로를 403 막다른 길로 만들었다). */
const SCREEN_ROLES = {
  users: ["admin", "system_admin"],
  jobs: ["operator", "admin", "system_admin"],
  departments: ["admin", "system_admin"],
  "job-titles": ["admin", "system_admin"],
  backup: ["operator", "admin", "system_admin", "auditor"],
  // audit: GET은 admin/system_admin/auditor만(audit/router.py, operator 제외). registry.audit엔
  // roles가 없어 라우트가 무방비였고, operator가 나브에서 '감사 로그'를 눌러 raw 403 막다른 길에
  // 빠졌다. 나브 항목(아래)과 이 라우트 게이트를 백엔드 READ_ROLES에 정확히 맞춘다.
  audit: ["admin", "system_admin", "auditor"],
};
// 화면별 403 안내 — RequireRole의 기본 문구("관리자, 시스템 관리자만")는 실제 허용 역할 집합이
// 더 넓은 화면(예: jobs도 operator 허용, audit/backup도 auditor 허용)에서 누가 접근 가능한지를
// 실제보다 좁게 말해 헷갈리게 한다. SCREEN_ROLES/하드코딩 라우트의 실제 역할 집합과 맞춘 문구.
const SCREEN_ROLE_HELP = {
  jobs: "이 화면은 운영자, 관리자, 시스템 관리자만 사용할 수 있습니다.",
  audit: "이 화면은 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다.",
  backup: "이 화면은 운영자, 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다.",
};

/* 에러 경계 — 화면 렌더 중 예외가 나도 전체 SPA가 흰 화면으로 죽지 않게 공통 오류 화면을 보여준다.
 * `bare` — AdminBody 안(라우트별 경계)처럼 이미 실제 .c-app>.c-body>.c-main>.c-content 셸
 * 안에 중첩돼 있을 때 쓴다. bare가 없으면(최상위 경계, Layout을 감싸는 용도) 그 셸 자체가
 * 아직 없으므로 껍데기를 통째로 다시 그린다, 안 그러면 사이드바, 상단바 바깥에 오류가 떠
 * 레이아웃이 깨진다. 예전엔 두 용도가 항상 같은(전체 셸) 마크업을 썼다. */
class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  // 캐치는 됐지만 아무 데도 기록되지 않았다, console.error조차 없었다. 이 경계가 앱의 유일한
  // 크래시 포착 지점(루트+라우트별)인데, 원인 스택이 전부 조용히 삼켜져 있었다
  // (product-quality-audit AREA=D). 최소한 콘솔에는 남겨 개발자 도구/향후 오류 수집기가 볼 수 있게 한다.
  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info && info.componentStack);
  }
  render() {
    if (this.state.err) {
      const body = <ErrorState error={{ message: "화면을 표시하는 중 문제가 발생했습니다. 새로고침해 주세요." }} onRetry={() => window.location.reload()} />;
      if (this.props.bare) return body;
      // 정상 셸과 같은 중첩(c-body>c-main>c-content)으로 그려 여백, 정렬이 어긋나지 않게 한다.
      // Topbar는 여기서 그리지 않는다, 크래시가 Topbar/컨텍스트에서 났다면 다시 크래시해 무한 루프가 된다.
      return (
        <div className="c-app"><div className="c-body"><main className="c-main"><div className="c-content">
          {body}
        </div></main></div></div>
      );
    }
    return this.props.children;
  }
}

/* 사이드바 구조 — 라우트로 이동. 메뉴명은 사용자 관점 한국어(§12). 각 항목의 `to`는 해시 라우트.
 * `roles`가 있으면 그 역할만 항목을 본다(백엔드 권한과 맞춰 '403 막다른 길'을 없앤다).
 * 부서·직책 관리는 백엔드 라우터가 GET을 포함해 전부 admin/system_admin만 허용하므로 여기서도 가린다. */
const NAV = [
  { group: "운영", items: [
    { to: "/dashboard", label: "대시보드" },
    { to: "/notifications", label: "알림" },
    { to: "/jobs", label: "작업 큐", roles: ["operator", "admin", "system_admin"] },
    { to: "/settings", label: "설정" },
    { to: "/audit", label: "감사 로그", roles: ["admin", "system_admin", "auditor"] },
    { to: "/backup", label: "백업", roles: ["operator", "admin", "system_admin", "auditor"] },
    { to: "/diagnostics", label: "진단", roles: ["admin", "system_admin"] },
    // GET /api/admin/settings(유지보수 모드가 담긴 바로 그 응답)는 READ_ROLES=operator/admin/
    // system_admin/auditor까지 허용하는데, 이 화면만 admin/system_admin으로 막혀 있었다 —
    // 쓰기는 Ops.jsx의 canWrite가 이미 역할별로 따로 가드하므로(비활성 버튼+안내문) 읽기
    // 역할까지 넓혀도 안전하다.
    { to: "/maintenance", label: "유지보수", roles: ["operator", "admin", "system_admin", "auditor"] },
  ] },
  { group: "사용자", items: [
    { to: "/users", label: "사용자", roles: ["admin", "system_admin"] },
    { to: "/departments", label: "부서 관리", roles: ["admin", "system_admin"] },
    { to: "/job-titles", label: "직책 관리", roles: ["admin", "system_admin"] },
    { to: "/notion-mapping", label: "Notion 사용자 연결" },
  ] },
  { group: "연동", items: [
    { to: "/integrations", label: "외부 연동" },
    { to: "/runners", label: "자동화 작업 실행기(러너)" },
    { to: "/workflows", label: "업무 자동화 흐름(워크플로)" },
  ] },
  { group: "콘텐츠", items: [
    { to: "/prompts", label: "프롬프트" },
    { to: "/policies", label: "정책" },
    { to: "/templates", label: "템플릿" },
  ] },
  { group: "자동화", items: [
    { to: "/schedules", label: "실행 일정(스케줄)" },
    { to: "/documents", label: "문서 자동 생성" },
    { to: "/dev-report", label: "개발자 월간 리포트", roles: ["admin", "system_admin", "auditor"] },
    { to: "/approvals", label: "승인" },
  ] },
];

/* 사용자(role=user) 콘솔 네비 — 관리자 셸과 같은 Sidebar 규격을 공유한다(위 NAV와 동일 구조).
 * 채팅은 여기 한 섹션이 되고, 내 업무·내 티켓·미할당은 /api/tickets/* 로 본인 것만 본다. */
const USER_NAV = [
  { group: "내 업무", items: [
    { to: "/me", label: "홈" },
    { to: "/my-tickets", label: "내 티켓" },
    { to: "/unassigned", label: "미할당 티켓" },
    { to: "/new-ticket", label: "새 티켓" },
  ] },
  { group: "도우미", items: [
    { to: "/chat", label: "AI 도우미" },
  ] },
  { group: "문서", items: [
    { to: "/team-docs", label: "문서" },
  ] },
  { group: "팀 공간", items: [
    { to: "/games", label: "놀이" },
    { to: "/board", label: "자유게시판" },
  ] },
];

// 사용자 세그먼트에 속하는 경로 — 관리자군이 상단 '사용자' 탭을 눌렀을 때 이 경로들에서 UserBody
// (개인 업무 콘솔)를 렌더한다. /notifications 는 관리자 세그먼트 소유라 여기 넣지 않는다(알림은
// 상단 벨로 접근). role=user 는 세그먼트와 무관하게 항상 UserBody 다.
const USER_SEG_PATHS = ["/me", "/my-tickets", "/unassigned", "/new-ticket", "/chat", "/board", "/team-docs", "/games"];
function inUserSegment(pathname) {
  return USER_SEG_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

// 그룹 아이콘(Feather 스타일 인라인 SVG, currentColor). 그룹명과 함께 계층을 시각화.
const NAV_ICONS = {
  "운영": "M3 3h18v4H3z M3 10h11v11H3z M17 10h4v11h-4z",
  "사용자": "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  "연동": "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1",
  "콘텐츠": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 13h8 M8 17h8",
  "자동화": "M13 2 3 14h9l-1 8 10-12h-9z",
  "내 업무": "M9 11l3 3 8-8 M20 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
  "도우미": "M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 0 1-.9-3.8A8.38 8.38 0 0 1 12.5 3a8.38 8.38 0 0 1 8.5 8.5z",
  "문서": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M8 13h8 M8 17h8",
  "팀 공간": "M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z",
};
function NavIcon({ group }) {
  return (
    <svg className="c-nav-ico" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={NAV_ICONS[group] || ""} /></svg>
  );
}

// 그룹 접힘 상태는 새로고침에도 유지한다(테마와 동일하게 localStorage). 5그룹, 20여 항목 트리를
// 접어 정리한 배치가 새로고침마다 초기화되던 문제.
// 공용/키오스크 PC에서는 계정별로 키를 나눈다, 예전엔 브라우저 하나에 값 하나뿐이라 한 사람의
// 사이드바 배치, 테마가 같은 기기에서 로그인한 다음 사람에게 그대로 넘어갔다
// (product-quality-audit AREA=D). userId를 모르면(부팅 초기 등) 계정 구분 없는 키로 폴백한다.
const NAV_COLLAPSE_KEY = "clovirone_nav_collapsed";
function navCollapseKey(userId) { return userId ? NAV_COLLAPSE_KEY + ":" + userId : NAV_COLLAPSE_KEY; }
function getStoredCollapsed(userId) {
  try { const v = JSON.parse(localStorage.getItem(navCollapseKey(userId)) || "{}"); return v && typeof v === "object" ? v : {}; }
  catch (e) { return {}; }
}

/* 재사용 탐색 컴포넌트, 관리자 셸과 (향후) 사용자 셸이 같은 규격(행 높이, 좌우 여백, 글꼴, 아이콘
 *, 선택 상태)을 공유하도록 항목/그룹 마크업을 한 곳으로 모은다. 그동안 그룹, 항목 마크업이
 * Sidebar 안에 인라인으로 흩어져 있어 두 셸이 서로 다른 규격으로 벌어질 위험이 있었다.
 * 선택 상태는 좌측 강조선(§6가 거부한 Claude식 바) 없이 '행 전체 배경 틴트 + 글자/아이콘 색'으로만
 * 표현한다(스타일은 global.css .c-nav-item.is-active). */
function NavigationItem({ to, label, onNavigate }) {
  return (
    <NavLink to={to} onClick={onNavigate}
      className={({ isActive }) => "c-nav-item" + (isActive ? " is-active" : "")}>
      <span className="c-nav-label">{label}</span>
    </NavLink>
  );
}

function NavigationGroup({ group, items, active, collapsed, onToggle, onNavigate }) {
  // 모바일 햄버거(.c-hamburger)는 aria-controls로 자신이 여는 사이드바(#admin-sidebar)와
  // 이미 연결돼 있다. 이 그룹 토글도 같은 펼침/접힘 패턴(aria-expanded+회전 화살표)을 쓰면서
  // 자신이 여는 항목 목록과는 연결돼 있지 않았다, id를 주고 aria-controls로 묶는다.
  const itemsId = "nav-group-" + group;
  return (
    <div className={"c-nav-group" + (active ? " has-active" : "")}>
      <button type="button" className="c-nav-group-title" aria-expanded={!collapsed} aria-controls={itemsId} onClick={onToggle}>
        <NavIcon group={group} />
        <span className="c-nav-group-name">{group}</span>
        <svg className={"c-nav-chev" + (collapsed ? " is-collapsed" : "")} width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {/* 접혔을 때 이 컨테이너를 통째로 언마운트하면(예전 방식) aria-controls={itemsId}가
          가리키는 노드가 DOM에 없어진다, 접힘이 기본/영구 상태인 사용자가 대다수라
          평소엔 aria-controls가 존재하지 않는 요소를 가리키는 무효 참조였다(ARIA disclosure
          위젯 패턴 위반). 항상 마운트해 두고 hidden 속성으로만 감춘다(product-quality-audit AREA=D). */}
      <div className="c-nav-items" id={itemsId} hidden={collapsed}>
        {items.map((it) => (
          <NavigationItem key={it.to} to={it.to} label={it.label} onNavigate={onNavigate} />
        ))}
      </div>
    </div>
  );
}

function Sidebar({ nav = NAV, ariaLabel = "관리 메뉴", onNavigate }) {
  const loc = useLocation();
  const auth = useAuth();
  const role = auth.data && auth.data.role;
  const userId = auth.data && auth.data.id;
  const [collapsed, setCollapsed] = useState(() => getStoredCollapsed(userId));
  // 권한 없는 메뉴는 숨긴다(예: 진단·유지보수는 admin/system_admin만).
  const groups = nav.map((g) => ({ ...g, items: g.items.filter((it) => !it.roles || (role && it.roles.includes(role))) }))
    .filter((g) => g.items.length);
  const toggle = (name) => setCollapsed((c) => {
    const next = { ...c, [name]: !c[name] };
    try { localStorage.setItem(navCollapseKey(userId), JSON.stringify(next)); } catch (e) { /* ignore */ }
    return next;
  });
  return (
    <nav className="c-nav" aria-label={ariaLabel}>
      {groups.map((g) => {
        const groupActive = g.items.some((it) => loc.pathname === it.to);
        // 현재 위치가 든 그룹은 사용자가 접어 뒀어도 항상 펼쳐 '여기 있음' 항목이 숨지 않게 한다
        // (알림 딥링크, 세그먼트, 직접 해시로 접힌 그룹 안 경로에 도착할 때).
        const isCollapsed = !!collapsed[g.group] && !groupActive;
        return (
          <NavigationGroup key={g.group} group={g.group} items={g.items} active={groupActive}
            collapsed={isCollapsed} onToggle={() => toggle(g.group)} onNavigate={onNavigate} />
        );
      })}
    </nav>
  );
}

// 테마, [data-theme]로만 다크가 켜진다(prefers-color-scheme 아님). 저장값을 부팅 때 적용.
// 계정별 키(themeKey)는 UserMenu가 로그인 사용자를 알게 된 뒤에만 쓴다, 부팅 시점(모듈 로드,
// 아직 인증 전)엔 계정 구분 없는 키로만 읽고 쓴다(위 navCollapseKey와 같은 이유).
const THEME_KEY = "clovirone_theme";
function themeKey(userId) { return userId ? THEME_KEY + ":" + userId : THEME_KEY; }
function applyTheme(t) {
  if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
}
function getStoredTheme() { try { return localStorage.getItem(THEME_KEY) || ""; } catch (e) { return ""; } }
// 저장된 선호가 없으면 OS의 prefers-color-scheme를 따른다(다크 OS 사용자가 매번 라이트로 시작하던 문제).
function prefersDark() {
  try { return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches); }
  catch (e) { return false; }
}
function initialTheme() { return getStoredTheme() || (prefersDark() ? "dark" : "light"); }
// 첫 페인트 전(모듈 로드 시점, createRoot 이전)에 테마를 적용해 다크 사용자의 화이트 플래시(FOUC)를 없앤다.
// CSP가 인라인 <script>를 막으므로 부팅 인라인 스크립트 대신 여기 모듈 스코프에서 동기 적용한다.
applyTheme(initialTheme());

// 내 프로필 모달 — GET /api/profile(부서·직책·마지막 로그인·활성 세션 수·Notion 연결 상태)을
// 보여준다. 백엔드는 이미 이 엔드포인트를 완성해 뒀지만 어떤 화면도 부르지 않아, 사용자가
// 자기 부서/직책을 볼 방법도, 보안상 중요한 '지금 활성 세션이 몇 개인지'를 볼 방법도 전혀
// 없었다(product-quality-audit AREA=D).
// 역할 라벨 — 5역할 RBAC가 나브·액션 노출을 바꾸는데도 셸 어디에도 '내 역할'이 안 보였다
// (사용자·operator·auditor가 왜 버튼이 없는지 알 길이 없었다). ProfileModal에 표시한다
// (product-quality-audit AREA=D). Users.jsx의 ROLE_KO와 같은 어휘지만 그 파일을 import하면
// 순환/결합이 생겨 여기 로컬로 둔다.
const ROLE_KO = { user: "사용자", operator: "운영자", auditor: "감사자", admin: "관리자", system_admin: "시스템 관리자" };

function ProfileModal({ open, onClose }) {
  const auth = useAuth();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  // reloadTick으로 onRetry를 구현한다 — 이 모달은 react-query가 아니라 수동 fetch라
  // auth.refetch() 같은 기성 재조회 함수가 없다. 네트워크 순단·일시적 5xx로 실패했을 때
  // onRetry가 없으면 버튼 하나 없는 진짜 막다른 화면이 된다(RequireRole 주석과 같은 문제,
  // product-quality-audit AREA=D).
  const [reloadTick, setReloadTick] = useState(0);
  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setLoading(true); setErr(null); setData(null);
    api("/api/profile")
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setErr(e); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, reloadTick]);
  const row = (label, value) => (
    <div className="k-profile-row"><span className="k-profile-label">{label}</span><span className="k-profile-value">{value}</span></div>
  );
  return (
    <Modal open={open} onClose={onClose} title="내 프로필">
      {loading ? <Skeleton /> : err ? <ErrorState error={err} onRetry={() => setReloadTick((n) => n + 1)} /> : data ? (
        <div>
          {row("역할", (() => { const r = data.role || (auth.data && auth.data.role); return r ? (ROLE_KO[r] || r) : "-"; })())}
          {row("부서", data.department || "-")}
          {row("직책", data.title || "-")}
          {row("마지막 로그인", data.last_login_at ? fmtDateTime(data.last_login_at) : "-")}
          {row("현재 활성 세션", data.active_session_count != null ? data.active_session_count + "개" : "-")}
          {/* 세션 수가 예상보다 많으면 계정 침해 신호일 수 있다 — 하지만 본인 계정용 세션
              해제 자기서비스가 아직 없다(Users.jsx의 '세션 해제'는 admin이 남을 대상으로만
              쓸 수 있다). 최소한 무엇을 해야 하는지는 알려준다(product-quality-audit AREA=D). */}
          {data.active_session_count != null && data.active_session_count > 1 ? (
            // 안내가 실제 통제로 이어지지 않아 있으나 마나였다, UserMenu에 '비밀번호 변경'
            // 항목이 이미 바로 옆(한 클릭)에 있는데도 이 문구는 평문이라, 여기서 닫고 메뉴를
            // 다시 열어 다시 눌러야 했다. 같은 링크를 여기 직접 심는다(product-quality-audit AREA=D).
            <div className="k-profile-help">숫자가 예상보다 많다면 <a href="/change-password">비밀번호를 변경</a>하거나 관리자에게 문의하세요.</div>
          ) : null}
          {row("Notion 연결 상태", data.notion_mapping_status ? <Badge value={data.notion_mapping_status} /> : "-")}
        </div>
      ) : null}
    </Modal>
  );
}

const USERMENU_FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';
/* 사용자 메뉴 — 이름/아바타를 누르면 테마 전환·내 프로필·비밀번호 변경·로그아웃. 로그아웃이
 * 없던 것이 큰 공백이었다(공용 PC 보안). 로그아웃은 서버 세션을 지우고 로그인 화면으로 보낸다. */
function UserMenu({ name, userId }) {
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState(initialTheme());
  const [busy, setBusy] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const ref = useRef(null);
  const menuRef = useRef(null);
  const btnRef = useRef(null);
  // '내 프로필' 클릭은 같은 커밋에서 setOpen(false) 다음 setProfileOpen(true)를 부른다 —
  // 아래 정리 이펙트가 무조건 btnRef에 포커스를 되돌리면, 그 직후 열리는 ProfileModal이
  // 다시 자기 안으로 포커스를 옮기며 두 컴포넌트가 포커스를 뺏고 뺏기는 경쟁이 생겼다.
  // NotificationBell.jsx의 navClosingRef와 같은 패턴으로 이 경우만 건너뛴다(product-quality-audit AREA=D).
  const openingProfileRef = useRef(false);
  useEffect(() => {
    if (!userId) return undefined;
    // 이 계정 전용으로 저장된 테마가 있으면(공용 PC에서 이전 사용자와 선택이 다를 수 있다)
    // 부팅 시 적용된 계정 구분 없는 테마 대신 그 값을 따른다.
    try {
      const saved = localStorage.getItem(themeKey(userId));
      if (saved) {
        if (saved !== theme) { setTheme(saved); applyTheme(saved); }
        // 계정 구분 없는 기본 키에도 미러링한다 — 부팅 시점(모듈 로드, 인증 전) initialTheme()은
        // 이 기본 키만 읽는데 예전엔 계정별 키만 쓰여 이 값이 영영 비어 있어, 선택한 테마가
        // OS 설정과 다르면 새로고침마다 매번 잘못된 테마 플래시(FOUC)가 났다(product-quality-audit AREA=D).
        localStorage.setItem(THEME_KEY, saved);
      }
    } catch (e) { /* ignore */ }
    // theme은 매 렌더 최신값을 읽되 이 효과 자체는 계정이 바뀔 때만 다시 돈다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);
  // NotificationBell의 팝오버와 같은 포커스 트랩 패턴 — 예전엔 열릴 때 포커스를 메뉴 안으로
  // 옮기지 않고 닫힐 때도 트리거 버튼으로 되돌리지 않아, Tab이 메뉴를 지나 배경 페이지로
  // 새어 나갔다(product-quality-audit AREA=D).
  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => {
      if (e.key === "Escape") { setOpen(false); return; }
      if (e.key === "Tab" && menuRef.current) {
        const els = Array.prototype.filter.call(menuRef.current.querySelectorAll(USERMENU_FOCUSABLE), (el) => el.offsetParent !== null);
        if (!els.length) return;
        const first = els[0], last = els[els.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("mousedown", onDoc); document.addEventListener("keydown", onKey);
    const t = window.setTimeout(() => {
      const node = menuRef.current; if (!node) return;
      const first = node.querySelector(USERMENU_FOCUSABLE);
      (first || node).focus();
    }, 0);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey);
      if (!openingProfileRef.current && btnRef.current && typeof btnRef.current.focus === "function") {
        try { btnRef.current.focus(); } catch (e) { /* ignore */ }
      }
      openingProfileRef.current = false;
    };
  }, [open]);
  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      localStorage.setItem(themeKey(userId), next);
      // 부팅 FOUC 방지용 기본 키에도 최신 선택을 미러링한다(위 로드 이펙트 주석 참고).
      localStorage.setItem(THEME_KEY, next);
    } catch (e) { /* ignore */ }
    applyTheme(next);
  }
  async function logout() {
    setBusy(true);
    // 기본(계정 구분 없는) 테마 키는 로그아웃 때 지운다, 공용/키오스크 PC에서 다음 사용자가
    // 로그인 화면부터 이전 사용자의 테마를 물려받지 않게 한다. 계정별 키(themeKey)는 남겨 둬
    // 본인이 다시 로그인하면 자기 선택이 복원된다(product-quality-audit AREA=D).
    try { localStorage.removeItem(THEME_KEY); } catch (e) { /* ignore */ }
    try { await api("/logout", { method: "POST", body: {} }); } catch (e) { /* 세션이 이미 없어도 로그인으로 */ }
    window.location.href = "/login";
  }
  return (
    <div className="c-user" ref={ref}>
      {/* aria-label을 버튼 자체에 명시한다, global.css가 ≤860px에서 .c-user-name(유일한 텍스트
          자식)을 숨기고 .c-avatar는 이미 aria-hidden이라, 모바일 폭(햄버거 메뉴가 뜨는 바로 그
          구간)에서만 접근 가능한 이름이 통째로 사라졌었다. */}
      <button ref={btnRef} type="button" className="c-user-btn" aria-haspopup="menu" aria-expanded={open}
        aria-label={(name || "관리자") + " 메뉴"} onClick={() => setOpen((v) => !v)}>
        <span className="c-user-name" aria-hidden="true">{name || "관리자"}</span>
        <span className="c-avatar" aria-hidden="true">{name ? name[0] : "?"}</span>
      </button>
      {open ? (
        <div className="c-usermenu" role="menu" ref={menuRef}>
          <button type="button" className="c-usermenu-item" role="menuitem" onClick={toggleTheme}>{theme === "dark" ? "라이트 모드" : "다크 모드"}</button>
          <button type="button" className="c-usermenu-item" role="menuitem" onClick={() => { openingProfileRef.current = true; setOpen(false); setProfileOpen(true); }}>내 프로필</button>
          <a className="c-usermenu-item" role="menuitem" href="/change-password">비밀번호 변경</a>
          <button type="button" className="c-usermenu-item c-usermenu-danger" role="menuitem" disabled={busy} onClick={logout}>{busy ? "로그아웃 중…" : "로그아웃"}</button>
        </div>
      ) : null}
      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
    </div>
  );
}

/* minimal, 세션 만료 등 인증이 끊긴 화면용. 세그먼트 전환, 알림 벨, 사용자 메뉴를 감춘다.
 * 이들은 죽은 컨트롤이거나(전환해도 화면이 안 바뀜) 401을 쏴 빨간 오류 표식, 팝오버를 낳는다. */
function Topbar({ isUser, userSeg, showMenu, navOpen, onMenu, minimal }) {
  const auth = useAuth();
  const name = (auth.data && auth.data.display_name) || "";
  const userId = auth.data && auth.data.id;
  const nav = useNavigate();
  const homeUser = isUser || userSeg;  // 현재 사용자 세그먼트면 홈은 /me, 아니면 관리자 /dashboard
  return (
    <header className="c-topbar">
      {showMenu ? (
        // 벨, 아바타와 같은 열림/닫힘 신호를 준다(aria-expanded/aria-controls), 이 버튼만 상태
        // 없이 static했다. 두 번째 탭도 no-op이 아니게 토글로 바꾸고, 아이콘도 열림 상태를
        // 반영한다(햄버거 ↔ ✕), 아이콘이 항상 같으면 눌러서 뭐가 바뀌었는지 알 수 없었다.
        <button type="button" className="c-hamburger" onClick={onMenu}
          aria-label={navOpen ? "메뉴 닫기" : "메뉴 열기"} aria-expanded={navOpen} aria-controls="app-sidebar">
          {navOpen ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 12h18 M3 6h18 M3 18h18" /></svg>
          )}
        </button>
      ) : null}
      {/* minimal(세션 만료) 화면에선 라우팅이 401 상태에 갇혀 해시만 바뀌고 화면은 그대로다 -
          홈 대신 유일한 실제 CTA인 로그인으로 보낸다(죽은 컨트롤 방지). */}
      <button type="button" className="c-brand"
        onClick={() => { if (minimal) { window.location.href = "/login"; } else { nav(homeUser ? "/me" : "/dashboard"); } }}
        aria-label={minimal ? "로그인 화면으로" : "홈으로"}>
        <svg className="c-brand-mark" viewBox="0 0 22 22" width="22" height="22" aria-hidden="true">
          <rect x="0" y="0" width="10" height="10" rx="2" fill="#536CD6" />
          <rect x="12" y="0" width="10" height="10" rx="2" fill="#758AE1" />
          <rect x="0" y="12" width="10" height="10" rx="2" fill="#8E75E1" />
          <rect x="12" y="12" width="10" height="10" rx="2" fill="#435CBE" />
        </svg>
        <span className="c-brand-name">ClovirONE</span>
        <span className="c-brand-sub">업무 도우미</span>
      </button>
      <div className="c-topbar-spacer" />
      {!isUser && !minimal ? (
        <div className="c-seg" role="group" aria-label="화면 전환">
          <button type="button" className={"c-seg-item" + (userSeg ? " is-on" : "")} aria-current={userSeg ? "page" : undefined} onClick={() => nav("/me")}>사용자</button>
          <button type="button" className={"c-seg-item" + (!userSeg ? " is-on" : "")} aria-current={!userSeg ? "page" : undefined} onClick={() => nav("/dashboard")}>관리자</button>
        </div>
      ) : null}
      {!minimal ? <NotificationBell isUser={isUser} /> : null}
      {!minimal ? <UserMenu name={name} userId={userId} /> : null}
    </header>
  );
}

/* 콘솔 셸, 좌측 네비(Sidebar) + 본문(라우트). 관리자, 사용자 셸이 공유한다(모바일 드로어, 포커스
 * 트랩, inert, 스켈레톤, 라우트별 오류경계 포함). nav/ariaLabel 로 어느 네비를, children 으로 어느
 * 라우트를 그릴지 주입한다. flush(=채팅 경로)면 .c-content 패딩, 폭 캡 없이 본문을 꽉 채운다
 * (채팅은 자체 2단 레이아웃이 높이를 관리하므로). */
function ConsoleShell({ nav, ariaLabel, navOpen, onCloseNav, children }) {
  const auth = useAuth();
  const loc = useLocation();
  const [isMobile, setIsMobile] = useState(false);
  const asideRef = useRef(null);
  const flush = loc.pathname.startsWith("/chat");
  // 모바일 폭(<=860px) 감지 — 닫힌 사이드바는 화면 밖으로 밀려 있을 뿐 DOM에 남아 키보드/SR이 도달한다
  // (채팅 드로어와 동일한 처리). 모바일이고 닫혀 있으면 aside를 inert로 만든다.
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 860px)");
    const on = () => setIsMobile(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  // 모바일 드로어: Esc로 닫고, 열릴 때 포커스를 사이드바 안 첫 항목으로 옮긴다. 모바일에서는
  // Modal/UserMenu/NotificationBell과 같은 Tab 트랩(사이드바 안에서만 순환)과 닫힐 때 트리거
  // (햄버거 버튼)로 포커스 복귀도 더한다 — 예전엔 이 드로어만 그 셋과 달리 Tab이 배경(백드롭에
  // 덮인, 시각적으로 도달 불가능한 본문)으로 새어 나가고 닫아도 포커스가 어디로도 안 돌아갔다
  // (product-quality-audit AREA=D).
  useEffect(() => {
    if (!navOpen) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") { onCloseNav(); return; }
      if (isMobile && e.key === "Tab" && asideRef.current) {
        const els = Array.prototype.filter.call(asideRef.current.querySelectorAll('a[href], button:not([disabled])'), (el) => el.offsetParent !== null);
        if (!els.length) return;
        const first = els[0], last = els[els.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", onKey);
    let t;
    if (isMobile) {
      t = window.setTimeout(() => {
        const node = asideRef.current; if (!node) return;
        const first = node.querySelector('a[href], button:not([disabled])');
        if (first) first.focus();
      }, 0);
    }
    return () => {
      if (t) window.clearTimeout(t);
      document.removeEventListener("keydown", onKey);
      // 항목 선택으로 닫힌 경우도 포함해 항상 햄버거로 되돌린다, 새 화면의 본문(#main-content)이
      // 이미 라우트 전환으로 포커스를 받을 수 있지만, 받지 않는 경우(예: 같은 라우트를 다시 누름)
      // 포커스가 사라진(unmount된 사이드바 링크) 채로 남는 것보다 안전하다.
      if (isMobile) {
        const hb = document.querySelector(".c-hamburger");
        if (hb && typeof hb.focus === "function") { try { hb.focus(); } catch (e) { /* ignore */ } }
      }
    };
    // onCloseNav는 매 렌더 새 함수라 deps에 넣으면 드로어가 열린 채 재렌더 시 포커스를 반복 탈취한다.
    // navOpen이 true로 바뀌는 순간의 클로저면 충분하다(항상 setNavOpen(false)만 호출).
  }, [navOpen, isMobile]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="c-body">
      <aside id="app-sidebar" ref={asideRef} className={"c-sidebar" + (navOpen ? " is-open" : "")}
        {...(isMobile && !navOpen ? { inert: "", "aria-hidden": "true" } : {})}>
        {/* auth가 로딩 중이면 role이 아직 없어 역할 게이트 항목이 전부 숨는다, 3개짜리
            나브가 그려졌다가 인증이 끝나는 순간 최대 8개로 튀는 레이아웃 점프를 막기 위해
            본문과 같은 스켈레톤으로 대기한다(위 :330의 콘텐츠 스켈레톤과 짝을 맞춤). */}
        {/* 세션 만료(auth.isError)면 role이 없어 Sidebar가 역할 게이트 없는 나브 항목을 전부
            클릭 가능하게 그린다, 누르는 족족 401 '로그인 필요' 화면으로 가는 죽은 링크 더미다.
            상단바를 minimal로 접는 것과 같은 정신으로 사이드바도 재로그인 안내 한 칸으로 접는다
            (product-quality-audit AREA=D). */}
        {auth.isLoading ? <div className="c-nav"><Skeleton lines={6} /></div>
          : auth.isError ? (
            <div className="c-nav c-nav-expired">
              <p>세션이 만료되었습니다.</p>
              <a className="k-btn k-btn--primary" href="/login">다시 로그인</a>
            </div>
          )
          : <Sidebar nav={nav} ariaLabel={ariaLabel} onNavigate={onCloseNav} />}
      </aside>
      {navOpen ? <div className="c-sidebar-backdrop" onClick={onCloseNav} aria-hidden="true" /> : null}
      {/* 모바일 드로어가 열려 있는 동안 본문은 반투명 백드롭에 덮여 시각적으로 도달 불가능한데도
          포커스 트랩이 없어 Tab이 그대로 본문 컨트롤로 새어 나갔다(닫힌 aside를 inert로 만드는
          위 처리와 짝이 맞지 않았다). aside와 같은 방식으로 본문을 inert 처리해 막는다. */}
      <main className={"c-main" + (flush ? " c-main--flush" : "")} id="main-content" tabIndex={-1}
        {...(isMobile && navOpen ? { inert: "", "aria-hidden": "true" } : {})}>
        {/* 오류 경계를 '본문'에만 두고 경로별로 리셋한다, 한 화면이 크래시해도 사이드바, 상단바는 살아 이동 가능.
            채팅(flush)은 .c-content 래핑 없이 꽉 채운다(자체 레이아웃이 높이, 스크롤 관리). */}
        {auth.isLoading ? <div className="c-content"><Card><Skeleton /></Card></div> : (
          <ErrorBoundary key={loc.pathname} bare>
            {flush ? children : <div className="c-content">{children}</div>}
          </ErrorBoundary>
        )}
      </main>
    </div>
  );
}

function AdminBody({ navOpen, onCloseNav }) {
  return (
    <ConsoleShell nav={NAV} ariaLabel="관리 메뉴" navOpen={navOpen} onCloseNav={onCloseNav}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/users" element={<RequireRole roles={SCREEN_ROLES.users}><Users /></RequireRole>} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/diagnostics" element={<RequireRole roles={["admin", "system_admin"]}><Diagnostics /></RequireRole>} />
        <Route path="/maintenance" element={<RequireRole roles={["operator", "admin", "system_admin", "auditor"]} help="이 화면은 운영자, 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다."><Maintenance /></RequireRole>} />
        <Route path="/dev-report" element={<RequireRole roles={["admin", "system_admin", "auditor"]} help="이 화면은 관리자, 시스템 관리자, 감사자만 사용할 수 있습니다."><DevReport /></RequireRole>} />
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
    </ConsoleShell>
  );
}

/* 사용자 콘솔 본문, 내 업무/내 티켓/미할당(조회) + 채팅(/chat, 자체 대화목록 2차 패널) + 알림.
 * 알림은 공용 DataScreen 이라 기본 '관리자' 빵부스러기가 뜨므로 그 라우트만 c-body--user-noti 로 감춘다. */
function UserBody({ navOpen, onCloseNav }) {
  return (
    <ConsoleShell nav={USER_NAV} ariaLabel="사용자 메뉴" navOpen={navOpen} onCloseNav={onCloseNav}>
      <Routes>
        <Route path="/me" element={<MyWork />} />
        <Route path="/my-tickets" element={<MyTickets />} />
        <Route path="/unassigned" element={<Unassigned />} />
        <Route path="/new-ticket" element={<NewTicket />} />
        <Route path="/chat" element={<div className="c-chat-embed"><Chat /></div>} />
        <Route path="/board" element={<Board />} />
        <Route path="/board/:id" element={<BoardPost />} />
        <Route path="/team-docs" element={<TeamDocs />} />
        <Route path="/team-docs/:id" element={<TeamDoc />} />
        <Route path="/games" element={<Games />} />
        <Route path="/games/:id" element={<GameRoom />} />
        <Route path="/notifications" element={<div className="c-body--user-noti"><DataScreen config={REGISTRY.notifications} /></div>} />
        <Route path="*" element={<Navigate to="/me" replace />} />
      </Routes>
    </ConsoleShell>
  );
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
  // 세션 만료(401)여도 셸(사이드바·상단바)은 정상 렌더하고, 각 데이터 화면이 ErrorState(로그인 링크 포함)를
  // 보여 준다. 전체 화면을 세션만료 카드로 덮지 않아 무로그인 상태에서도 UI 검증이 가능하다.
  // 최초 진입: 해시가 없으면 실제 경로로 기본 화면 결정(/admin→대시보드, 그 외→채팅).
  useEffect(() => {
    const h = window.location.hash.replace("#", "");
    if (!h) nav(window.location.pathname === "/admin" ? "/dashboard" : "/me", { replace: true });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // 사용자 세그먼트 여부(관리자군이 상단 '사용자' 탭에 있는지). role=user 는 항상 사용자 콘솔.
  const userSeg = inUserSegment(loc.pathname);
  // must_change_password가 켜진 계정은 /api/me 이외 거의 모든 API가 403 password_change_required로
  // 막힌다(app/core/deps.py get_current_user) — 관리자가 사용자 폼에서 '비밀번호 변경 요구'를 켜면
  // 도달 가능한, 실제로 살아있는 상태다. login.js가 로그인 직후 하는 것과 같은 리다이렉트를 SPA
  // 진입 시점에도 한다(그대로 두면 화면마다 막다른 403만 보였다). /change-password는 이 SPA 밖의
  // 별도 페이지라 실제 페이지 이동으로 나간다.
  useEffect(() => {
    if (auth.data && auth.data.must_change_password) window.location.href = "/change-password";
  }, [auth.data]);
  // 셸 선택, 로딩: 스켈레톤. role=user: 항상 UserBody. 관리자군: 상단 '사용자' 세그먼트에 있으면
  // UserBody(개인 업무 콘솔 전체, 내 업무/내 티켓/미할당/새 티켓 + 도우미), '관리자' 세그먼트면
  // AdminBody. (예전엔 관리자의 '사용자'가 /chat 전폭 채팅뿐이라 사용자 콘솔을 못 봤다.)
  // 두 콘솔 모두 좌측 사이드바가 있어 햄버거(메뉴)는 인증된 동안 항상 노출한다.
  const showMenu = !auth.isError && !auth.isLoading;
  let body;
  if (auth.isLoading) {
    body = <div className="c-body"><main className="c-main" id="main-content" tabIndex={-1}><div className="c-content"><Card><Skeleton /></Card></div></main></div>;
  } else if (isUser || userSeg) {
    body = <UserBody navOpen={navOpen} onCloseNav={() => setNavOpen(false)} />;
  } else {
    body = <AdminBody navOpen={navOpen} onCloseNav={() => setNavOpen(false)} />;
  }
  return (
    <div className="c-app">
      {/* HashRouter에서 href='#main-content'는 해시를 라우트로 파싱하므로 앵커 대신 <main>(tabIndex=-1)에 포커스를 준다. */}
      {!auth.isError ? <a className="c-skip-link" href="#main-content"
        onClick={(e) => { e.preventDefault(); const m = document.getElementById("main-content"); if (m) m.focus(); }}>본문으로 건너뛰기</a> : null}
      <Topbar isUser={isUser} userSeg={userSeg} showMenu={showMenu} navOpen={navOpen} onMenu={() => setNavOpen((v) => !v)} minimal={auth.isError} />
      {body}
    </div>
  );
}

export function App() {
  // 저장된 테마를 부팅 때 적용(없으면 OS 선호 → 라이트). 모듈 스코프에서 이미 한 번 적용했으나
  // 안전하게 재적용한다(테스트 환경 등에서 모듈 스코프 호출이 없었던 경우 대비).
  useEffect(() => { applyTheme(initialTheme()); }, []);
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
