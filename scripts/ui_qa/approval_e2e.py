"""승인 파이프라인을 **처음부터 끝까지** 한 번 돌린다 (`approvals` 0행, `USE-01`).

이 설치에서 승인은 **한 번도 발생한 적이 없다** — 화면 2개(`/approvals`·`/approval-delegations`),
알림 5종(`approval_requested`·`approval_decided`·`approval_delegated`·`approval_expired`·
`approval_overdue`), SLA(`due_at`), 위임 규칙이 전부 미검증 상태다.

**어떻게 만드나**: `admin`(비 system_admin)이 사용자의 역할을 바꾸면 즉시 적용되지 않고
`user.role_change` 승인이 접수된다(`app/users/router.py:452`). 그 경로를 쓴다.

**되돌린다**: 대상은 QA 계정(`qa-user`)뿐이고, 끝나면 역할을 `user` 로 복구한다.
"""

from __future__ import annotations

import json
import ssl
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import Viewport, new_context  # noqa: E402

BASE = "https://clovirone-ai.gooddi.lab"
OUT = Path("dist/approval-e2e")
TARGET_EMAIL = "qa-user@goodmit.co.kr"


def session_for(browser, out_dir: Path):
    return ensure_session(browser, BASE, out_dir, insecure=True, log=print)


def ctx_for(browser, sess):
    return new_context(browser, storage_state=sess.storage_state, user_id=sess.user_id,
                       theme="light", viewport=Viewport("1600x1000", 1600, 1000),
                       insecure=True)


def me(ctx) -> dict:
    return ctx.request.get(BASE + "/api/me", timeout=30_000).json()


def call(ctx, method: str, path: str, csrf: str, body=None):
    fn = getattr(ctx.request, method)
    kw = {"timeout": 60_000,
          "headers": {"X-CSRF-Token": csrf, "Content-Type": "application/json"}}
    if body is not None:
        kw["data"] = body
    r = fn(BASE + path, **kw)
    try:
        return r.status, r.json()
    except Exception:  # noqa: BLE001
        return r.status, (r.text() or "")[:300]


def find_user(ctx, email: str):
    st, body = call(ctx, "get", "/api/admin/users?page=1&q=" + email, "")
    items = (body or {}).get("items", []) if isinstance(body, dict) else []
    for u in items:
        if u.get("email") == email:
            return u
    return None


def main() -> int:
    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    log: dict = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)

        # ── 1. admin 으로 역할 변경을 시도한다 → 승인이 접수돼야 한다 ──────────
        admin = session_for(b, Path("dist/ui-qa-admin-2"))
        actx = ctx_for(b, admin)
        acsrf = me(actx).get("csrf_token", "")
        log["actor"] = {"email": admin.email, "role": admin.role, "csrf": bool(acsrf)}

        target = find_user(actx, TARGET_EMAIL)
        log["target_before"] = target and {"id": target["id"], "role": target.get("role")}
        if not target:
            print("대상 사용자를 찾지 못했습니다"); return 1

        st, body = call(actx, "patch", f"/api/admin/users/{target['id']}", acsrf,
                        {"role": "admin"})
        log["role_change_request"] = {"status": st, "body": str(body)[:300]}

        after = find_user(actx, TARGET_EMAIL)
        log["target_role_right_after"] = after and after.get("role")

        st, body = call(actx, "get", "/api/admin/approvals", acsrf)
        items = (body or {}).get("items", []) if isinstance(body, dict) else []
        log["approvals_seen_by_admin"] = {
            "status": st, "n": len(items),
            "tail": [{k: v for k, v in i.items()
                      if k in ("id", "request_type", "status", "due_at", "requested_by_name")}
                     for i in items[:3]]}
        approval_id = items[0]["id"] if items else None

        # ── 2. 요청자 본인이 자기 요청을 승인할 수 있는가 (있으면 결함) ────────
        if approval_id:
            st, body = call(actx, "post", f"/api/admin/approvals/{approval_id}/approve",
                            acsrf, {})
            log["self_approve_attempt"] = {"status": st, "body": str(body)[:200]}
        actx.close()

        # ── 3. system_admin 이 승인한다 ────────────────────────────────────
        sa = session_for(b, Path("dist/ai-e2e"))          # hshwang@ (system_admin)
        sctx = ctx_for(b, sa)
        scsrf = me(sctx).get("csrf_token", "")
        log["approver"] = {"email": sa.email, "role": sa.role}

        st, body = call(sctx, "get", "/api/admin/approvals", scsrf)
        items = (body or {}).get("items", []) if isinstance(body, dict) else []
        approval_id = approval_id or (items[0]["id"] if items else None)
        log["approvals_seen_by_sysadmin"] = {"status": st, "n": len(items)}

        if approval_id:
            st, body = call(sctx, "post", f"/api/admin/approvals/{approval_id}/approve",
                            scsrf, {"comment": "QA 조사 — 승인 파이프라인 검증"})
            log["approve"] = {"status": st, "body": str(body)[:300]}

        final = find_user(sctx, TARGET_EMAIL)
        log["target_role_after_approve"] = final and final.get("role")

        # ── 4. 알림이 실제로 갔는가 ────────────────────────────────────────
        st, body = call(sctx, "get", "/api/notifications", scsrf)
        notis = (body or {}).get("items", []) if isinstance(body, dict) else []
        log["approval_notifications"] = [
            {"type": n.get("type"), "title": (n.get("title") or "")[:60],
             "route": n.get("related_route")}
            for n in notis if str(n.get("type", "")).startswith("approval")][:5]

        # ── 5. 되돌린다 ───────────────────────────────────────────────────
        if final:
            st, body = call(sctx, "patch", f"/api/admin/users/{final['id']}", scsrf,
                            {"role": "user"})
            log["revert"] = {"status": st, "role_now": (find_user(sctx, TARGET_EMAIL) or {}).get("role")}
        sctx.close()
        b.close()

    (OUT / "approval_e2e.json").write_text(json.dumps(log, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
