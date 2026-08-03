"""Route inventory for the SPA — DERIVED, not guessed.

Sources (re-derive from these if the app's routing changes):

  frontend/src/app/App.jsx
    * ``UserBody()``  — the ``<Route>`` elements of the user console
      (/me, /my-tickets, /unassigned, /new-ticket, /tickets/:id, /team-tickets,
      /sprint, /chat, /chat-rooms, /chat-rooms/:id, /board, /board/:id,
      /team-docs, /team-docs/trash, /team-docs/:id, /games, /games/:id,
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
    * ``REGISTRY`` — 16 keys, each rendered by ``AdminBody`` at ``"/" + key``:
      integrations, runners, workflows, prompts, policies, templates, schedules,
      documents, approvals, departments, job-titles, notion-mapping, jobs,
      audit, notifications, backup.  None of them declare their own
      ``roles:``, so ``SCREEN_ROLES`` alone gates them.

  app/admin/router.py  — ``GET /admin`` redirects ``role == "user"`` to ``/``,
      which is why every admin-console route needs at least ``operator``.
  app/chat/router.py   — ``GET /``  serves the same React shell for the user
      console.

Routing is HashRouter: a URL is ``<base_url><shell>#<hash_path>``, e.g.
``http://127.0.0.1:8080/#/my-tickets`` and ``http://127.0.0.1:8080/admin#/dashboard``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# 5-role RBAC (app/users/models.py ALL_ROLES). The set is NOT a strict
# hierarchy — `operator` and `auditor` are siblings with different read scopes —
# but a single "minimum role" column has to order them somehow, so we rank by
# how much of the console each role can reach. Consult ``allowed_roles`` when
# the exact set matters.
ROLE_RANK = {"user": 0, "operator": 1, "auditor": 2, "admin": 3, "system_admin": 4}

USER_SHELL = "/"
ADMIN_SHELL = "/admin"


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

    @property
    def is_detail(self) -> bool:
        return bool(self.hash_template)

    @property
    def shell(self) -> str:
        return USER_SHELL if self.console == "user" else ADMIN_SHELL

    def url(self, base_url: str, hash_path: str | None = None) -> str:
        return f"{base_url.rstrip('/')}{self.shell}#{hash_path or self.hash_path}"


def _u(rid, path, label, **kw) -> Route:
    return Route(id=rid, hash_path=path, console="user", label=label, min_role="user", **kw)


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
)

# --- admin console (App.jsx AdminBody) --------------------------------------
# The six hard-coded routes first, then the 16 REGISTRY-driven DataScreen routes.
ADMIN_ROUTES: tuple[Route, ...] = (
    _a("admin_dashboard", "/dashboard", "대시보드"),
    _a("admin_users", "/users", "사용자", "admin", ("admin", "system_admin")),
    _a("admin_settings", "/settings", "설정"),
    _a("admin_diagnostics", "/diagnostics", "진단", "admin", ("admin", "system_admin")),
    _a("admin_maintenance", "/maintenance", "유지보수", "operator",
       ("operator", "admin", "system_admin", "auditor")),
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
    _a("admin_departments", "/departments", "부서 관리", "admin", ("admin", "system_admin")),
    _a("admin_job-titles", "/job-titles", "직책 관리", "admin", ("admin", "system_admin")),
    _a("admin_notion-mapping", "/notion-mapping", "Notion 사용자 연결"),
    _a("admin_jobs", "/jobs", "작업 큐", "operator", ("operator", "admin", "system_admin")),
    _a("admin_audit", "/audit", "감사 로그", "auditor", ("admin", "system_admin", "auditor")),
    _a("admin_notifications", "/notifications", "알림"),
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
)

ALL_ROUTES: tuple[Route, ...] = USER_ROUTES + ADMIN_ROUTES
BY_ID = {r.id: r for r in ALL_ROUTES}

# A small, cheap smoke set: one user-console screen, one DataScreen-driven admin
# screen, one detail view. Used by ``run.py --routes smoke``.
SMOKE_IDS = ("user_my-tickets", "admin_audit", "admin_integration-detail")


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
        }
        for r in ALL_ROUTES
    ]


if __name__ == "__main__":  # quick sanity dump: python -m scripts.ui_qa.routes
    for r in ALL_ROUTES:
        print(f"{r.id:<26} {r.console:<5} {(r.hash_template or r.hash_path):<22} "
              f"{r.min_role:<12} {r.label}")
    print(f"총 {len(ALL_ROUTES)}개 (user={len(USER_ROUTES)}, admin={len(ADMIN_ROUTES)})")
