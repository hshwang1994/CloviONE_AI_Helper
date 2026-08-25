"""S21 이 감사하는 화면과 **그 화면을 여는 주소** (W14).

원장(`ROUTE_COVERAGE.json`)은 `/departments/:id` 처럼 **자리표시자**로 적혀 있다. 브라우저는
그 주소를 못 연다 — 실제 id 가 필요한데 그 값은 씨앗마다 다르다. 그래서 여기서 두 가지를
한 자리에 둔다: 화면 목록과, **그 화면의 id 를 서버에 물어 채우는 규칙**.

id 를 표에 손으로 박지 않는 이유는 S18 이 이미 적어 뒀다 — 표에서 긁으면 화면이 id 를 안
그리는 순간 죽고, 손으로 박으면 씨앗이 바뀌는 순간 거짓이 된다. 서버에 묻는 것이 가장 안
늙는다.
"""

from __future__ import annotations

USER = "/"
ADMIN = "/admin"

# surface → (hash 주소, 셸). `{...}` 는 아래 `RESOLVERS` 가 채운다.
SURFACES: dict[str, tuple[str, str]] = {
    # ── 사용자 콘솔 ────────────────────────────────────────────────────────
    "user_my-tickets": ("/my-tickets", USER),
    "user_unassigned": ("/unassigned", USER),
    "user_team-tickets": ("/team-tickets", USER),
    "user_new-ticket": ("/new-ticket", USER),
    "user_projects-id": ("/projects/{project_id}", USER),
    "user_work-board": ("/work-board", USER),
    "user_knowledge": ("/knowledge", USER),
    "user_knowledge-doc": ("/knowledge/{document_id}", USER),
    "user_team-docs-trash": ("/team-docs/trash", USER),
    "user_legacy-doc-redirect": ("/team-docs/00000000-0000-0000-0000-000000000000", USER),
    "user_board": ("/board", USER),
    "user_ideas": ("/ideas", USER),
    "user_games": ("/games", USER),
    "user_games-id": ("/games/{game_id}", USER),
    "user_chat": ("/chat", USER),
    "user_chat-rooms-id": ("/chat-rooms/{room_id}", USER),
    "user_ai-workspace": ("/ai", USER),
    "user_search": ("/search", USER),
    "user_search-results": ("/search?q=회의", USER),
    "user_search-empty": ("/search?q=존재하지않는검색어zz", USER),
    "user_notifications": ("/notifications", USER),
    "user_my-approvals": ("/my-approvals", USER),
    "user_profile": ("/profile", USER),
    "user_my-stats": ("/my-stats", USER),
    "user_activity": ("/activity", USER),
    "user_my-display": ("/my-display", USER),
    "public_login": ("/login", ""),
    # ── 관리자 콘솔 ────────────────────────────────────────────────────────
    "admin_dashboard": ("/dashboard", ADMIN),
    "admin_search": ("/search", ADMIN),
    "admin_users-id": ("/users/{user_id}", ADMIN),
    "admin_offboarding": ("/offboarding", ADMIN),
    "admin_departments": ("/departments", ADMIN),
    "admin_departments-id": ("/departments/{department_id}", ADMIN),
    "admin_org-tree": ("/org-tree", ADMIN),
    "admin_job-titles": ("/job-titles", ADMIN),
    "admin_rbac": ("/rbac", ADMIN),
    "admin_impersonation": ("/impersonation", ADMIN),
    "admin_admin-notifications": ("/admin-notifications", ADMIN),
    "admin_announcements": ("/announcements", ADMIN),
    "admin_feature-flags": ("/feature-flags", ADMIN),
    "admin_ai-quotas": ("/ai-quotas", ADMIN),
    "admin_prompts": ("/prompts", ADMIN),
    "admin_policies": ("/policies", ADMIN),
    "admin_prompt-usage": ("/prompt-usage", ADMIN),
    "admin_policy-usage": ("/policy-usage", ADMIN),
    "admin_ai-usage__prompt-usage": ("/ai-usage?tab=prompt-usage", ADMIN),
    "admin_ai-usage__policy-usage": ("/ai-usage?tab=policy-usage", ADMIN),
    "admin_integrations": ("/integrations", ADMIN),
    "admin_schedules__schedules": ("/schedules?tab=schedules", ADMIN),
    "admin_schedules__scheduler-calendar": ("/schedules?tab=scheduler-calendar", ADMIN),
    "admin_scheduler-calendar": ("/scheduler-calendar", ADMIN),
    "admin_approvals__approvals": ("/approvals?tab=approvals", ADMIN),
    "admin_approvals__approval-delegations":
        ("/approvals?tab=approval-delegations", ADMIN),
    "admin_approval-delegations": ("/approval-delegations", ADMIN),
    "admin_audit__audit": ("/audit?tab=audit", ADMIN),
    "admin_audit__audit-anomalies": ("/audit?tab=audit-anomalies", ADMIN),
    "admin_audit-anomalies": ("/audit-anomalies", ADMIN),
    "admin_audit-id": ("/audit/{audit_id}", ADMIN),
    "admin_backup__backup": ("/backup?tab=backup", ADMIN),
    "admin_backup__restore-drills": ("/backup?tab=restore-drills", ADMIN),
    "admin_restore-drills": ("/restore-drills", ADMIN),
    "admin_diagnostics": ("/diagnostics", ADMIN),
    "admin_integrity": ("/integrity", ADMIN),
    "admin_dev-report": ("/dev-report", ADMIN),
    "admin_mail": ("/mail", ADMIN),
    "admin_setup": ("/setup", ADMIN),
    "admin_settings__storage": ("/settings?tab=storage", ADMIN),
}

# `{이름}` → 그 값을 어디서 얻는가. `(API 경로, 응답에서 꺼내는 경로)`.
# 응답 경로는 `items.0.id` 처럼 점으로 잇는다.
RESOLVERS: dict[str, tuple[str, str]] = {
    "project_id": ("/api/projects", "items.0.id"),
    "document_id": ("/api/knowledge/documents?page_size=1", "items.0.id"),
    "game_id": ("/api/games/rooms", "items.0.id"),
    "room_id": ("/api/team-chat/rooms", "items.0.id"),
    "user_id": ("/api/admin/users?page_size=1", "items.0.id"),
    "department_id": ("/api/admin/departments?page_size=1", "items.0.id"),
    "audit_id": ("/api/admin/audit?page_size=1", "items.0.id"),
}


def dig(payload, path: str):
    cur = payload
    for part in path.split("."):
        if cur is None:
            return None
        if part.isdigit():
            if not isinstance(cur, list) or len(cur) <= int(part):
                return None
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            # 목록이 곧 응답인 API 도 있다 — `items` 를 요구하지 않는다.
            return None
        else:
            return None
    return cur


def resolve_ids(api_get) -> dict[str, str]:
    """`{이름}` 자리에 넣을 실제 id 를 서버에서 받아 온다."""
    out: dict[str, str] = {}
    for name, (path, pick) in RESOLVERS.items():
        try:
            payload = api_get(path)
        except Exception:  # noqa: BLE001
            payload = None
        value = dig(payload, pick)
        if value is None and isinstance(payload, list) and payload:
            value = (payload[0] or {}).get("id")
        if value is not None:
            out[name] = str(value)
    return out


def hash_for(surface: str, ids: dict[str, str]) -> tuple[str, str] | None:
    entry = SURFACES.get(surface)
    if entry is None:
        return None
    hash_path, shell = entry
    for name, value in ids.items():
        hash_path = hash_path.replace("{%s}" % name, value)
    if "{" in hash_path:
        return None
    return hash_path, shell
