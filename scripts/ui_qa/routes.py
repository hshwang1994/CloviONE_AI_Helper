"""Route inventory for the SPA — DERIVED, not guessed.

Sources (re-derive from these if the app's routing changes):

  frontend/src/app/App.jsx
    * ``UserBody()``  — the ``<Route>`` elements of the user console
      (/me, /my-tickets, /unassigned, /new-ticket, /tickets/:id, /team-tickets,
      /work-board, /sprint, /chat, /chat-rooms, /chat-rooms/:id, /board, /board/:id,
      /team-docs, /team-docs/trash, /team-docs/:id, /knowledge, /knowledge/:id,
      /games, /games/:id,
      /notifications).
    * ``AdminBody()`` — the hard-coded admin ``<Route>`` elements
      (/dashboard, /users, /settings, /diagnostics, /maintenance, /dev-report)
      plus ``Object.keys(REGISTRY).map(key => <Route path={"/" + key} .../>)``.
    * ``SCREEN_ROLES`` + the explicit ``<RequireRole roles={...}>`` wrappers —
      the minimum role each screen needs.
    * ``USER_SEG_PATHS`` — which pathnames make ``Layout`` render ``UserBody``.
      Note ``/notifications`` is deliberately NOT in that list ("알림은 관리자
      세그먼트 소유"), so it is catalogued here as an admin-console route.

  frontend/src/screens/registry.js
    * ``REGISTRY`` — **28** keys (not 16; the count in this docstring was stale
      for a long while), assembled from 7 domain files under
      ``frontend/src/screens/registry/`` and each rendered by ``AdminRoutes`` at
      ``"/" + key``:
        integrations.js  integrations runners workflows
        authoring.js     prompts policies templates prompt-usage policy-usage
        automation.js    schedules documents jobs
        org.js           organizations departments job-titles org-tree notion-mapping
        governance.js    approvals approval-delegations audit audit-anomalies rbac impersonation
        platform.js      backup restore-drills announcements ai-quotas feature-flags
        notifications.js notifications
      None of them declare their own ``roles:``, so ``SCREEN_ROLES`` alone gates
      them.  ``organizations``/``departments``/``org-tree`` are excluded from the
      auto-registration (``ORG_CONSOLE_KEYS``) and served by ``OrgConsole``, but
      their configs stay in ``REGISTRY`` because ``OrgConsole`` reads columns and
      forms from them.

  app/admin/router.py  — ``GET /admin`` redirects ``role == "user"`` to ``/``,
      which is why every admin-console route needs at least ``operator``.
  app/chat/router.py   — ``GET /``  serves the same React shell for the user
      console.

Routing is HashRouter: a URL is ``<base_url><shell>#<hash_path>``, e.g.
``http://127.0.0.1:8080/#/my-tickets`` and ``http://127.0.0.1:8080/admin#/dashboard``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

# 5-role RBAC (app/users/models.py ALL_ROLES). The set is NOT a strict
# hierarchy — `operator` and `auditor` are siblings with different read scopes —
# but a single "minimum role" column has to order them somehow, so we rank by
# how much of the console each role can reach. Consult ``allowed_roles`` when
# the exact set matters.
ROLE_RANK = {"user": 0, "operator": 1, "auditor": 2, "admin": 3, "system_admin": 4}

USER_SHELL = "/"
ADMIN_SHELL = "/admin"
# 로그인·비밀번호 변경은 SPA 가 아니라 서버가 그리는 Jinja 화면이다 — 해시가 없다.
PUBLIC_SHELL = ""


@dataclass(frozen=True)
class Route:
    """One capturable SPA screen."""

    id: str  # filename-safe identifier, used for dist/ui-qa/<theme>/<vp>/<id>.png
    hash_path: str  # the HashRouter path, e.g. "/my-tickets"
    console: str  # "user" | "admin"
    label: str  # short Korean label (matches the sidebar wording where one exists)
    min_role: str  # least-privileged role that renders real content
    allowed_roles: tuple[str, ...] = ()  # empty == "any role that reaches the shell"
    # Detail screens need a real object id. ``discover`` is an authenticated GET
    # whose first item's ``id`` is substituted into ``hash_template``.
    hash_template: str = ""
    discover: tuple[str, ...] = field(default_factory=tuple)
    # ROUTE_COVERAGE.json 의 surface id. 하네스 id 와 표기가 달라서(harness
    # ``admin_users-detail`` vs coverage ``admin_users-id``) Gate 가 경로로 짐작해
    # 맞춰 왔는데, 짐작은 한 쪽이 바뀌는 날 조용히 어긋난다. 명시한다.
    surface_id: str = ""
    # 소스가 `<Navigate>` 로 바꾼 옛 주소. 값이 있으면 **화면이 아니라 별칭**이다.
    alias_of: str = ""

    @property
    def is_alias(self) -> bool:
        return bool(self.alias_of)

    @property
    def is_detail(self) -> bool:
        return bool(self.hash_template)

    @property
    def is_public(self) -> bool:
        """세션 없이 찍는 화면(로그인). storage_state 를 실으면 홈으로 튕겨 못 찍는다."""
        return self.console == "public"

    @property
    def shell(self) -> str:
        if self.console == "public":
            return PUBLIC_SHELL
        return USER_SHELL if self.console == "user" else ADMIN_SHELL

    def visible_to(self, role: str) -> bool:
        """이 역할이 **실제 내용**을 볼 수 있는가.

        🔴 이것이 없으면 라우트 커버리지가 허수가 된다. `system_admin` 전용 4화면을
        `admin` 계정으로 찍으면 **권한 거부 배너**가 찍히는데, 21개 검사는 그 배너를
        기준으로 전부 통과하고 요약에는 `ok` 로 올라간다 — 화면이 아니라 배너를 검사한 것이다
        (BACKLOG `QA-12`). 볼 수 없는 라우트는 `ok` 가 아니라 **미검사**로 세야 한다.
        """
        if self.is_public or not role:
            return True
        if self.allowed_roles:
            return role in self.allowed_roles
        if not self.min_role:
            return True
        return ROLE_RANK.get(role, -1) >= ROLE_RANK.get(self.min_role, 0)

    def url(self, base_url: str, hash_path: str | None = None) -> str:
        path = hash_path or self.hash_path
        if self.console == "public":   # 해시 라우터가 아니라 진짜 경로다
            return f"{base_url.rstrip('/')}{path}"
        return f"{base_url.rstrip('/')}{self.shell}#{path}"


def _p(rid, path, label, **kw) -> Route:
    return Route(id=rid, hash_path=path, console="public", label=label, min_role="", **kw)


def _u(rid, path, label, **kw) -> Route:
    return Route(id=rid, hash_path=path, console="user", label=label, min_role="user", **kw)


def _alias(rid, path, target, label, min_role="operator", allowed=()) -> Route:
    """옛 주소. `AdminRoutes.jsx` 가 `<Navigate>` 로 바꿔 **자기 화면이 없다**.

    화면으로 세면 PNG 는 도착지 화면인데 검사는 전부 통과하고 커버리지는 한 화면을 둘로
    센다 — 실제로 `/system`·`/notion-console`·`/llm-console`·`/maintenance` 네 개가
    그렇게 세어지고 있었다. `ALL_ROUTES` 에서 빼고 리다이렉트 계약 검증에만 쓴다.
    """
    return Route(
        id=rid, hash_path=path, console="admin", label=label,
        min_role=min_role, allowed_roles=tuple(allowed), alias_of=target,
    )


def _a(rid, path, label, min_role="operator", allowed=(), **kw) -> Route:
    return Route(
        id=rid, hash_path=path, console="admin", label=label,
        min_role=min_role, allowed_roles=tuple(allowed), **kw,
    )


# --- user console (App.jsx UserBody) ----------------------------------------
USER_ROUTES: tuple[Route, ...] = (
    # 홈은 '오늘' 커맨드 센터(screens/Home.jsx)로 바뀌었다 — 해시 경로는 그대로 /me 다.
    _u("user_me", "/me", "홈 — 오늘"),
    _u("user_my-tickets", "/my-tickets", "내 티켓"),
    _u("user_unassigned", "/unassigned", "미할당 티켓"),
    _u("user_new-ticket", "/new-ticket", "새 티켓"),
    # ``/api/tickets/mine`` is empty unless the QA account is mapped to a Notion
    # user, and it never is (the CLI creates a plain account). ``/api/tickets``
    # is not a route at all — it answers 405. So the detail screen was skipped on
    # every run. ``/api/tickets/team`` needs no mapping and lists the whole board,
    # which is exactly what a screenshot needs.
    _u("user_ticket-detail", "/my-tickets", "티켓 상세",
       hash_template="/tickets/{id}",
       discover=("/api/tickets/mine", "/api/tickets/team?active=false")),
    _u("user_team-tickets", "/team-tickets", "팀 티켓"),
    # 작업 보드(S6) — 칸반과 백로그 두 탭. 캡처는 기본 탭(칸반)을 찍는다.
    _u("user_work-board", "/work-board", "작업 보드"),
    _u("user_sprint", "/sprint", "스프린트 회의"),
    _u("user_chat", "/chat", "AI 도우미"),
    _u("user_chat-rooms", "/chat-rooms", "채팅방"),
    _u("user_chat-room-detail", "/chat-rooms", "채팅방 상세",
       hash_template="/chat-rooms/{id}", discover=("/api/team-chat/rooms",)),
    _u("user_board", "/board", "자유게시판"),
    _u("user_board-post", "/board", "게시글 상세",
       hash_template="/board/{id}", discover=("/api/board/posts",)),
    _u("user_team-docs", "/team-docs", "문서"),
    _u("user_team-docs-trash", "/team-docs/trash", "문서 휴지통"),
    _u("user_team-doc-detail", "/team-docs", "문서 상세",
       hash_template="/team-docs/{id}", discover=("/api/team-docs",)),
    # 지식 공간(S7). **사이드바 항목이 없다** — 사용자 서랍 한 그룹이 여섯 항목을 넘지
    # 않는다는 계약 때문이고, 입구는 「문서」 화면에 있다(navConfig.js ROUTE_OWNER 주석).
    # 캡처 대상이 아닌 것은 아니다: 화면은 있고 주소로 도달한다.
    _u("user_knowledge", "/knowledge", "지식 공간"),
    _u("user_knowledge-doc", "/knowledge", "지식 문서 상세",
       hash_template="/knowledge/{id}", discover=("/api/knowledge/documents",)),
    # 통합 검색(0030). 두 콘솔 양쪽에 같은 경로로 등록돼 있지만 같은 컴포넌트라 한 번만 찍는다.
    # **빈 상태와 결과 상태를 둘 다** 찍는다 — 검색 화면의 회귀는 "결과가 그려지는가"보다
    # "아직 안 쳤다 / 쳤는데 없다"의 얼굴에서 더 자주 난다.
    _u("user_search", "/search", "통합 검색"),
    _u("user_search-results", "/search?q=회의", "통합 검색 — 결과"),
    # '검색 결과 없음'(art="search")은 '데이터 없음'과 **다른 얼굴이어야 한다**는 것이
    # 계획서의 명시 요구다. 그 구분은 캡처로만 확인된다.
    _u("user_search-empty", "/search?q=존재하지않는검색어zz", "통합 검색 — 결과 없음"),
    _u("user_games", "/games", "놀이"),
    _u("user_game-room", "/games", "놀이방",
       hash_template="/games/{id}", discover=("/api/games/rooms",)),
    # 내 정보(계획서 Phase 6 사용자 백로그) — 프로필 셀프서비스·업무량 통계·활동 피드.
    # 셋 다 `USER_SEG_PATHS` 에 들어 있어 사용자 셸에서 열린다(navConfig.js).
    _u("user_profile", "/profile", "내 프로필"),
    _u("user_my-stats", "/my-stats", "내 업무량 · 완료 통계"),
    _u("user_activity", "/activity", "내 활동"),
    # ── 목록에서 빠져 있던 화면들 (2026-08-08) ────────────────────────────────
    # 이 세 개는 `UserRoutes.jsx` 에 라우트가 있는데도 여기 없어서 **한 번도 캡처된 적이 없다**.
    # 하네스가 "전 화면을 돈다"고 말하면서 실제로는 돌지 않은 구간이 있었다는 뜻이다.
    # (`Projects.jsx` 306 + `Project.jsx` 382 + 하위 4개 + `Board.jsx` 의 아이디어 모드)
    _u("user_projects", "/projects", "프로젝트"),
    _u("user_project-detail", "/projects", "프로젝트 상세",
       hash_template="/projects/{id}", discover=("/api/projects",)),
    # 기능 개선 제안 — 게시판과 같은 API 를 종류만 바꿔 쓴다(navConfig.js). 화면은 Board.jsx 다.
    _u("user_ideas", "/ideas", "기능 개선 제안"),
    # ── 사용자 콘솔에는 완전성 테스트 자체가 없었다 (2026-08-19, W0) ─────────────
    # `UserRoutes.jsx` 에 라우트가 있는데 이 목록에 **0건**이라 한 번도 캡처된 적이 없다.
    # 관리자 쪽에서 세 번 반복된 결함(system_admin 4화면 · admin_mail · /audit/:id)과
    # 같은 부류다. 이번에 등록하면서 완전성 테스트를 사용자 콘솔까지 확장한다.
    # `/notifications` 는 0060 에서 **사용자 콘솔 소유**가 됐다(navConfig.js::USER_SEG_PATHS).
    # 하네스는 이걸 관리자 라우트로 갖고 있었는데 `AdminRoutes.jsx` 에는 그 경로가 없다 —
    # `/admin#/notifications` 는 catch-all 의 RouteNotFound 다. 그 404 화면을 찍어 놓고
    # 21개 검사가 전부 통과해 왔다. 관리자 알림은 아래 `/admin-notifications` 다.
    _u("user_notifications", "/notifications", "알림"),
    _u("user_my-approvals", "/my-approvals", "내 승인 요청"),
    _u("user_my-display", "/my-display", "화면 표시 설정"),
)

# --- admin console (App.jsx AdminBody) --------------------------------------
# The six hard-coded routes first, then the 16 REGISTRY-driven DataScreen routes.
ADMIN_ROUTES: tuple[Route, ...] = (
    _a("admin_dashboard", "/dashboard", "대시보드"),
    # 통합 검색은 두 콘솔에 같은 경로로 등록돼 있다. 같은 컴포넌트라 한 번만 찍어 왔는데,
    # 이번 리뉴얼의 작업 대상이 Header·Sidebar 라 **셸이 다르면 다른 화면**이다.
    _a("admin_search", "/search", "통합 검색 (관리자 셸)"),
    _a("admin_users", "/users", "사용자", "admin", ("admin", "system_admin")),
    # PA-RC-0024가 신설한 상세 딥링크(직접 진입·새로고침·뒤로가기 보존) — QAH-06과 같은
    # 함정을 세 번째로 반복하지 않으려고 새 라우트를 추가하면서 바로 등록한다
    # (test_ui_qa_route_registry_completeness.py가 이제 이 누락을 회귀로 잡는다).
    # hash_path는 AdminRoutes.jsx의 `<Route path="/users/:id">` 리터럴과 정확히 같아야
    # 완전성 검사를 통과한다 — 실제 캡처용 대체값은 hash_template(`{id}` 자리표시자)이 쓴다.
    _a("admin_users-detail", "/users/:id", "사용자 상세", "admin", ("admin", "system_admin"),
       hash_template="/users/{id}", discover=("/api/admin/users",)),
    # 온보딩·오프보딩(Phase 6)은 마법사라 REGISTRY 가 아니라 전용 화면이다
    # (미리 보여 주고 확인받는 단계를 DataScreen 계약으로는 표현할 수 없다 — Offboarding.jsx).
    _a("admin_offboarding", "/offboarding", "온보딩 · 오프보딩", "admin",
       ("admin", "system_admin")),
    _a("admin_settings", "/settings", "설정"),
    _a("admin_diagnostics", "/diagnostics", "진단", "admin", ("admin", "system_admin")),
    # 데이터 정합성(0060) — 소속 미지정 계정·프로젝트 없는 티켓·Ownership 미지정 문서처럼
    # **조용히 안 보이게 되는 상태**를 모아 보여 주고 일괄로 고친다. `/diagnostics`(시스템
    # 점검)와 이름이 비슷하지만 다루는 대상이 다르다 — 저쪽은 연결·설정, 이쪽은 데이터다.
    _a("admin_integrity", "/integrity", "데이터 정합성", "admin", ("admin", "system_admin")),
    _a("admin_dev-report", "/dev-report", "개발자 월간 리포트", "auditor",
       ("admin", "system_admin", "auditor")),
    # REGISTRY keys — "/" + key, gated by SCREEN_ROLES when listed there.
    _a("admin_integrations", "/integrations", "외부 연동"),
    _a("admin_runners", "/runners", "자동화 작업 실행기(러너)"),
    _a("admin_workflows", "/workflows", "업무 자동화 흐름(워크플로)"),
    _a("admin_prompts", "/prompts", "프롬프트"),
    _a("admin_policies", "/policies", "정책"),
    _a("admin_templates", "/templates", "템플릿"),
    _a("admin_schedules", "/schedules", "실행 일정(스케줄)"),
    _a("admin_documents", "/documents", "문서 자동 생성"),
    _a("admin_approvals", "/approvals", "승인"),
    _a("admin_organizations", "/organizations", "조직 관리", "admin", ("admin", "system_admin")),
    _a("admin_departments", "/departments", "부서 관리", "admin", ("admin", "system_admin")),
    # admin_users-detail과 같은 이유(PA-RC-0024, QAH-06 재발 방지) — AdminRoutes.jsx의
    # `<Route path="/departments/:id">` 리터럴과 hash_path가 정확히 같아야 한다.
    _a("admin_departments-detail", "/departments/:id", "부서 상세", "admin", ("admin", "system_admin"),
       hash_template="/departments/{id}", discover=("/api/admin/departments",)),
    # 조직도(Phase 6) — 0024 의 Department.parent_id 를 평탄화해 표 하나로 그린다.
    _a("admin_org-tree", "/org-tree", "조직도", "admin", ("admin", "system_admin")),
    _a("admin_job-titles", "/job-titles", "직책 관리", "admin", ("admin", "system_admin")),
    # 권한 매트릭스(Phase 6) — 규칙 표라 읽기 전용 역할도 본다(백엔드 CONSOLE_READ_ROLES).
    _a("admin_rbac", "/rbac", "권한 매트릭스", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    _a("admin_notion-mapping", "/notion-mapping", "Notion 사용자 연결"),
    # REGISTRY 28키 중 하나(`screens/registry/notifications.js::admin-notifications`).
    # 하네스에도 커버리지에도 없어서 한 번도 캡처된 적이 없다 — Python 정규식이 계산된
    # 경로(`path={"/" + key}`)를 못 읽어 조용히 놓친 바로 그 한 개다
    # (`frontend/src/screens/registry-surface-parity.test.js` 가 JS 로 잡았다).
    _a("admin_admin-notifications", "/admin-notifications", "관리 알림"),
    _a("admin_jobs", "/jobs", "작업 큐", "operator", ("operator", "admin", "system_admin")),
    _a("admin_audit", "/audit", "감사 로그", "auditor", ("admin", "system_admin", "auditor")),
    _a("admin_backup", "/backup", "백업", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    # Detail views inside the admin console are drawers opened by a query string
    # on the same hash route — registry.js declares them as
    # ``onQuery: (p) => p.id ? { open: "select", id: p.id } : null`` and
    # ``OBJ_ID_PARAM`` names the parameter per object type (id / job_id / user_id).
    _a("admin_integration-detail", "/integrations", "외부 연동 상세",
       hash_template="/integrations?id={id}", discover=("/api/admin/integrations",)),
    _a("admin_runner-detail", "/runners", "러너 상세",
       hash_template="/runners?id={id}", discover=("/api/admin/runners",)),
    _a("admin_job-detail", "/jobs", "작업 상세", "operator",
       ("operator", "admin", "system_admin"),
       hash_template="/jobs?job_id={id}", discover=("/api/admin/jobs",)),
    # ── 관리자 백로그 잔여(PLAN Phase 6, 마이그레이션 0033) ────────────────────
    # 여덟 개는 REGISTRY 키라 "/" + key 로 라우팅되고, 실행 달력만 AdminRoutes.jsx 의
    # 전용 라우트다(표로 표현할 수 없는 유일한 화면 — SchedulerCalendar.jsx).
    _a("admin_impersonation", "/impersonation", "임퍼소네이션(대리 보기)", "auditor",
       ("admin", "system_admin", "auditor")),
    _a("admin_approval-delegations", "/approval-delegations", "승인 위임", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    _a("admin_announcements", "/announcements", "공지 배너", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    _a("admin_ai-quotas", "/ai-quotas", "AI 사용 상한", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    _a("admin_feature-flags", "/feature-flags", "기능 플래그", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    _a("admin_audit-anomalies", "/audit-anomalies", "감사 이상 징후", "auditor",
       ("admin", "system_admin", "auditor")),
    _a("admin_restore-drills", "/restore-drills", "복구 리허설", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    # QAH-06(2026-08-11): AdminRoutes.jsx의 실제 라우트(MailStatus.jsx)인데 이 목록에 없어서
    # 68라우트 QAH 하네스 1회차를 포함해 한 번도 캡처된 적이 없었다 — 아래 system_admin 전용
    # 4화면과 같은 부류의 결함(등록 누락). role 집합은 AdminRoutes.jsx:117의 RequireRole과 동일.
    _a("admin_mail", "/mail", "메일 발송 현황", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    _a("admin_scheduler-calendar", "/scheduler-calendar", "실행 달력", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    _a("admin_prompt-usage", "/prompt-usage", "프롬프트 사용 통계", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    _a("admin_policy-usage", "/policy-usage", "정책 사용 통계", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    # 초기 설정만 여전히 자기 화면이다(SetupWizard.jsx). 나머지 셋과 유지보수는
    # `/settings` 탭이 됐고 옛 주소는 `<Navigate>` 다 — 아래 ALIAS_ROUTES 로 옮겼다.
    _a("admin_setup", "/setup", "초기 설정", "system_admin", ("system_admin",)),
    # ── /settings 탭 본문 (2026-08-19, W0) ────────────────────────────────────
    # `SettingsShell.jsx::TAB_DEFS` 의 네 탭 중 `policy` 만 `/settings` 로 찍혀 왔다.
    # 나머지 셋이 그리는 SystemOps(389) · NotionConsole(433) · LlmConsole(394) 는
    # **직접 캡처된 적이 없다** — 1,216줄이 시각 검사 밖에 있었다.
    _a("admin_settings-os", "/settings?tab=os", "설정 — OS와 서비스 동작",
       "system_admin", ("system_admin",)),
    _a("admin_settings-integration", "/settings?tab=integration", "설정 — 연동",
       "system_admin", ("system_admin",)),
    _a("admin_settings-ai", "/settings?tab=ai", "설정 — AI",
       "system_admin", ("system_admin",)),
    # ── 탭 그릇의 두 번째 탭 (2026-08-19, W0) ─────────────────────────────────
    # `AdminRoutes.jsx::TAB_GROUPS` 의 `/ai-usage` 그릇은 옛 주소 두 개(/policy-usage,
    # /prompt-usage)로만 하네스에 있었다. 대표 주소와 탭 상태는 별개 Surface 다.
    _a("admin_ai-usage", "/ai-usage", "AI 사용 통계 — 정책", "operator",
       ("operator", "admin", "system_admin", "auditor")),
    _a("admin_ai-usage-prompt", "/ai-usage?tab=prompt-usage", "AI 사용 통계 — 프롬프트",
       "operator", ("operator", "admin", "system_admin", "auditor")),
    # 탭 그릇의 두 번째 탭을 **대표 주소 + 탭 상태**로도 찍는다. 옛 주소(`/restore-drills`
    # 등)는 이미 위에 있지만 그건 다른 주소다 — 둘 다 살아 있어야 한다는 것이
    # `AdminRoutes.jsx` 의 설계다(리다이렉트를 안 쓴 이유가 그 주석에 있다).
    _a("admin_backup-restore-drills-tab", "/backup?tab=restore-drills", "백업 — 복구 리허설 탭",
       "operator", ("operator", "admin", "system_admin", "auditor")),
    _a("admin_approvals-delegations-tab", "/approvals?tab=approval-delegations",
       "승인 — 승인 위임 탭", "operator", ("operator", "admin", "system_admin", "auditor")),
    _a("admin_audit-anomalies-tab", "/audit?tab=audit-anomalies", "감사 로그 — 이상 징후 탭",
       "auditor", ("admin", "system_admin", "auditor")),
    _a("admin_schedules-calendar-tab", "/schedules?tab=scheduler-calendar",
       "실행 일정 — 달력 탭", "operator", ("operator", "admin", "system_admin", "auditor")),
    # 감사 로그 상세(PA-RC-0024)는 `AdminRoutes.jsx:277` 이 탭 그릇 안에서 등록하는데
    # 정규식 완전성 테스트가 `<Route key=... path=` 형태를 못 읽어 조용히 빠져 있었다.
    _a("admin_audit-detail", "/audit/:id", "감사 로그 상세", "auditor",
       ("admin", "system_admin", "auditor"),
       hash_template="/audit/{id}", discover=("/api/admin/audit",)),
)

# --- 옛 주소(리다이렉트) -------------------------------------------------------
# `AdminRoutes.jsx:216-219` 가 `<Navigate to="/settings?tab=…" replace />` 로 바꿨다.
# **화면이 아니다.** 캡처하면 도착지 화면의 PNG 가 네 장 더 생기고 그 위에서 21개 검사가
# 전부 통과한다 — 커버리지가 한 화면을 둘로 세는 정확히 그 함정이다(PLAN C1b).
# 여기 남겨 두는 이유는 리다이렉트 계약을 검증하기 위해서다
# (`frontend/src/app/settings-route-redirects.test.jsx` 가 그 계약의 정본이고,
#  `--routes alias` 로 실제 브라우저에서도 도착지를 확인할 수 있다).
ALIAS_ROUTES: tuple[Route, ...] = (
    _alias("admin_system", "/system", "/settings?tab=os", "시스템 설정(옛 주소)",
           "system_admin", ("system_admin",)),
    _alias("admin_notion-console", "/notion-console", "/settings?tab=integration",
           "Notion 관리(옛 주소)", "system_admin", ("system_admin",)),
    _alias("admin_llm-console", "/llm-console", "/settings?tab=ai",
           "AI 관리(옛 주소)", "system_admin", ("system_admin",)),
    _alias("admin_maintenance", "/maintenance", "/settings?tab=policy",
           "유지보수(옛 주소)", "operator",
           ("operator", "admin", "system_admin", "auditor")),
)

# --- 로그인 전 화면 -----------------------------------------------------------
# 하네스가 로그인된 세션으로 시작하는 바람에 **로그인 화면을 한 번도 안 찍었다**.
# 지시서 §1 이 통째로 검사 밖에 있었다는 뜻이라 세션 없는 컨텍스트로 따로 찍는다.
PUBLIC_ROUTES: tuple[Route, ...] = (
    _p("public_login", "/login", "로그인"),
)

# 별칭은 **화면이 아니라서** ALL_ROUTES 에 들어가지 않는다. `--routes alias` 로만 부른다.
# --- 하네스 id ↔ ROUTE_COVERAGE Surface id ------------------------------------
# 두 이름이 다른 자리. Gate 와 `scripts/collect_evidence.py` 가 경로로 짐작해 맞추던 것을
# 표로 고정한다 — 짐작은 한쪽이 바뀌는 날 조용히 어긋나고, 그러면 증거가 엉뚱한 Surface 에
# 붙는다. 여기 없는 Route 는 id 가 그대로 Surface id 다.
SURFACE_ID_OVERRIDES: dict[str, str] = {
    "admin_ai-usage": "admin_ai-usage__policy-usage",
    "admin_ai-usage-prompt": "admin_ai-usage__prompt-usage",
    "admin_approvals": "admin_approvals__approvals",
    "admin_approvals-delegations-tab": "admin_approvals__approval-delegations",
    "admin_audit": "admin_audit__audit",
    "admin_audit-anomalies-tab": "admin_audit__audit-anomalies",
    "admin_audit-detail": "admin_audit-id",
    "admin_backup": "admin_backup__backup",
    "admin_backup-restore-drills-tab": "admin_backup__restore-drills",
    "admin_departments-detail": "admin_departments-id",
    "admin_schedules": "admin_schedules__schedules",
    "admin_schedules-calendar-tab": "admin_schedules__scheduler-calendar",
    "admin_settings-ai": "admin_settings__ai",
    "admin_settings-integration": "admin_settings__integration",
    "admin_settings-os": "admin_settings__os",
    "admin_users-detail": "admin_users-id",
    "user_board-post": "user_board-id",
    "user_chat-room-detail": "user_chat-rooms-id",
    "user_game-room": "user_games-id",
    "user_project-detail": "user_projects-id",
    "user_team-doc-detail": "user_team-docs-id",
    "user_ticket-detail": "user_tickets-id",
}


def _stamp(routes: tuple[Route, ...]) -> tuple[Route, ...]:
    return tuple(
        replace(r, surface_id=SURFACE_ID_OVERRIDES.get(r.id, r.id)) for r in routes
    )


PUBLIC_ROUTES = _stamp(PUBLIC_ROUTES)
USER_ROUTES = _stamp(USER_ROUTES)
ADMIN_ROUTES = _stamp(ADMIN_ROUTES)
ALIAS_ROUTES = _stamp(ALIAS_ROUTES)

ALL_ROUTES: tuple[Route, ...] = PUBLIC_ROUTES + USER_ROUTES + ADMIN_ROUTES
BY_ID = {r.id: r for r in ALL_ROUTES + ALIAS_ROUTES}

# A small, cheap smoke set: one user-console screen, one DataScreen-driven admin
# screen, one detail view. Used by ``run.py --routes smoke``.
SMOKE_IDS = ("public_login", "user_my-tickets", "admin_audit", "admin_integration-detail")


def resolve(selectors: Iterable[str] | None) -> list[Route]:
    """Turn CLI ``--routes`` values into Route objects.

    Accepts route ids, hash paths, the aliases ``all`` / ``smoke`` / ``user`` /
    ``admin``, and the ``detail`` alias (every detail screen).
    """
    if not selectors:
        return list(ALL_ROUTES)
    out: list[Route] = []
    seen: set[str] = set()

    def add(routes: Iterable[Route]) -> None:
        for r in routes:
            if r.id not in seen:
                seen.add(r.id)
                out.append(r)

    for raw in selectors:
        token = raw.strip()
        if not token:
            continue
        low = token.lower()
        if low == "all":
            add(ALL_ROUTES)
        elif low == "smoke":
            add(BY_ID[i] for i in SMOKE_IDS)
        elif low == "user":
            add(USER_ROUTES)
        elif low == "admin":
            add(ADMIN_ROUTES)
        elif low == "public":
            add(PUBLIC_ROUTES)
        elif low == "alias":
            add(ALIAS_ROUTES)
        elif low == "detail":
            add(r for r in ALL_ROUTES if r.is_detail)
        elif token in BY_ID:
            add([BY_ID[token]])
        else:
            wanted = token if token.startswith("/") else "/" + token
            matches = [r for r in ALL_ROUTES if r.hash_path == wanted or r.hash_template == wanted]
            if not matches:
                raise SystemExit(
                    f"알 수 없는 라우트: {raw}\n"
                    f"사용 가능한 id: {', '.join(sorted(BY_ID))}"
                )
            add(matches)
    return out


def inventory() -> list[dict]:
    """Serializable inventory (goes into results.json so a POST run can diff it)."""
    return [
        {
            "id": r.id, "hash_path": r.hash_template or r.hash_path, "console": r.console,
            "label": r.label, "min_role": r.min_role,
            "allowed_roles": list(r.allowed_roles), "is_detail": r.is_detail,
            "is_public": r.is_public,
            "surface_id": r.surface_id or r.id,
            "alias_of": r.alias_of,
        }
        for r in ALL_ROUTES + ALIAS_ROUTES
    ]


if __name__ == "__main__":  # quick sanity dump: python -m scripts.ui_qa.routes
    for r in ALL_ROUTES:
        print(f"{r.id:<26} {r.console:<5} {(r.hash_template or r.hash_path):<22} "
              f"{r.min_role:<12} {r.label}")
    print(f"총 {len(ALL_ROUTES)}개 (public={len(PUBLIC_ROUTES)}, "
          f"user={len(USER_ROUTES)}, admin={len(ADMIN_ROUTES)}) "
          f"+ 별칭 {len(ALIAS_ROUTES)}개(화면 아님)")
