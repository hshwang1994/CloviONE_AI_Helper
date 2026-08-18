"""공지 배너·AI 쿼터를 처음부터 끝까지 한 번씩 돌린다 (`announcements`/`ai_quotas`
0행, `USE-01` 나머지 항목).

둘 다 **외부 쓰기가 없다** — Notion을 건드리는 문서/티켓/오프보딩(D-21이 실고객
워크스페이스 위험을 이유로 실서버 재현을 보류시킨 것과 같은 부류)과 달리, 이 둘은
이 앱 자신의 DB에만 쓴다. 그래서 이번 조사에서 안전하게 실행 가능한 후보로 골랐다.

**공지는 `active=False` 로만 만든다** — 생성 즉시 지우지만, 그 짧은 순간이라도 다른
실제 로그인 사용자에게 배너가 실제로 뜨는 것은 피한다("Publishing... visible to
others"에 해당할 수 있는 행동). 목적은 "배너가 보이는가"가 아니라 "쓰기 경로가
실제로 동작하는가(테이블 행 생성·감사 로그 기록·삭제)"이므로 `active=False` 로도
같은 것을 확인할 수 있다.

**AI 쿼터는 QA 테스트 계정(`qa-user`) 범위로만 만든다** — 전역(`scope_type=global`)
쿼터는 회사 전체 실사용자의 AI를 멈출 수 있어 대상에서 제외했다.

둘 다 **되돌린다** — 만든 행을 세션 끝에 지운다.
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

import os

# 원격 승인된 TEST SERVER(clovirone-ai.gooddi.lab)의 QA 캐시 세션이 전부 만료돼 있었고
# (session_idle_timeout 초과 또는 그 사이 재배포), 저장된 비밀번호도 더는 안 먹혀
# 재로그인이 안 됐다 — 원격 계정 재발급은 SSH가 필요한데(auth.py의 명시적 경고), 이
# 조사 하나 때문에 SSH 자격증명을 꺼내는 것은 범위 밖이다. 로컬 dev 서버(이 저장소
# 자신의 SQLite, `var/web.sqlite3`)로 전환 — `user_cli`가 로컬에서는 자유롭게 계정을
# 만들 수 있고, 이 조사가 실제로 확인하려는 것("코드 경로가 실제로 동작하는가")은
# 로컬 실행으로도 똑같이 증명된다(FN-05/FN-03b가 이미 쓴 방식과 동일).
BASE = os.environ.get("USE_AXIS_BASE_URL", "http://127.0.0.1:8080")
OUT = Path("dist/use-axis-e2e")
# 비우면 서버가 422("사용자 쿼터에는 user_id 가 필요합니다")로 정확히 거절한다 — 그건
# 제품이 옳게 동작한 것이고, 쿼터 축은 **한 번도 안 돌아 본 것**이 된다(2026-08-19 실측).
# 안 주면 로그인한 그 계정 자신에게 건다: 스스로에게 거는 쿼터는 남의 사용에 영향이 없고,
# 이 스크립트가 곧바로 지운다.
QA_USER_ID = os.environ.get("USE_AXIS_TARGET_USER_ID", "")


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


def main() -> int:
    ssl._create_default_https_context = ssl._create_unverified_context
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    log: dict = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        # 로컬 dev 서버 전용 QA 계정(system_admin, 이 파일 상단 주석 참고) — user_cli로
        # 새로 만들었으니 credentials.json 없이도 UI_QA_EMAIL/UI_QA_PASSWORD로 첫 로그인.
        # 승인된 TEST SERVER 는 자체 서명 인증서를 쓴다(`USE_AXIS_BASE_URL` 로 겨눌 때).
        # 그 사실을 안 넘기면 로그인 자체가 ERR_CERT_AUTHORITY_INVALID 로 죽는다 —
        # 이 파일이 로컬 http 만 상정하고 쓰였기 때문이다(2026-08-19 실측).
        insecure = BASE.startswith("https://")
        sess = ensure_session(b, BASE, Path("dist/use-axis-e2e-session"), log=print,
                              insecure=insecure)
        ctx = new_context(b, storage_state=sess.storage_state, user_id=sess.user_id,
                          theme="light", viewport=Viewport("1600x1000", 1600, 1000),
                          insecure=insecure)
        me = ctx.request.get(BASE + "/api/me", timeout=30_000).json()
        csrf = me.get("csrf_token", "")
        log["csrf"] = bool(csrf)
        target_user_id = QA_USER_ID or (me.get("user") or {}).get("id") or me.get("id") or sess.user_id
        log["quota_target_user_id"] = bool(target_user_id)

        # ── 1. 공지 배너 — active=False 로 생성, 목록 확인, 삭제 ──────────────
        st, before = call(ctx, "get", "/api/admin/announcements?page=1", csrf)
        log["announcements_before"] = {"status": st, "n": len(before.get("items", []))
                                       if isinstance(before, dict) else None}

        st, created = call(ctx, "post", "/api/admin/announcements", csrf, body={
            "title": "[QA 조사용] U축 실행 이력 확인 — 실사용자에게 노출되지 않음",
            "body": "USE-01 실환경 실행 이력 조사(2026-08-12). active=False로 생성 직후 삭제.",
            "level": "info", "audience": "admin", "active": False, "dismissible": True,
        })
        log["announcement_create"] = {"status": st, "body": created}
        ann_id = (created or {}).get("id") if st == 201 else None

        if ann_id:
            st, listed = call(ctx, "get", "/api/admin/announcements?page=1", csrf)
            found = any((it.get("id") == ann_id) for it in listed.get("items", []))
            log["announcement_appears_in_list"] = {"status": st, "found": found}

            st, deleted = call(ctx, "delete", f"/api/admin/announcements/{ann_id}", csrf)
            log["announcement_delete"] = {"status": st, "body": deleted}

            st, after = call(ctx, "get", "/api/admin/announcements?page=1", csrf)
            still_there = any((it.get("id") == ann_id) for it in after.get("items", []))
            log["announcement_gone_after_delete"] = {"status": st, "still_there": still_there}

        # ── 2. AI 쿼터 — qa-user 범위로 생성, 목록/사용량 확인, 삭제 ──────────
        st, before_q = call(ctx, "get", "/api/admin/ai-quotas", csrf)
        log["quotas_before"] = {"status": st, "n": len(before_q.get("items", []))
                                if isinstance(before_q, dict) else None}

        st, created_q = call(ctx, "post", "/api/admin/ai-quotas", csrf, body={
            "scope_type": "user", "user_id": target_user_id, "period": "day",
            "max_calls": 500, "note": "[QA 조사용] U축 실행 이력 확인 — 2026-08-12",
        })
        log["quota_create"] = {"status": st, "body": created_q}
        quota_id = (created_q or {}).get("id") if st == 201 else None

        if quota_id:
            st, listed_q = call(ctx, "get", "/api/admin/ai-quotas", csrf)
            row = next((it for it in listed_q.get("items", []) if it.get("id") == quota_id), None)
            log["quota_appears_in_list"] = {"status": st, "found": row is not None,
                                            "used_field_present": row is not None and "used" in row}

            st, usage = call(ctx, "get", "/api/admin/ai-quotas/usage", csrf)
            log["quota_usage_endpoint"] = {"status": st,
                                           "keys": list(usage)[:8] if isinstance(usage, dict) else None}

            st, deleted_q = call(ctx, "delete", f"/api/admin/ai-quotas/{quota_id}", csrf)
            log["quota_delete"] = {"status": st, "body": deleted_q}

            st, after_q = call(ctx, "get", "/api/admin/ai-quotas", csrf)
            still_there_q = any((it.get("id") == quota_id) for it in after_q.get("items", []))
            log["quota_gone_after_delete"] = {"status": st, "still_there": still_there_q}

        # ── 3. 오프보딩 — 전용 QA 대상/후임 계정, ticket_page_ids=[] (Notion 쓰기 0건) ──
        # D-21과 같은 이유로 실제 Notion 워크스페이스에 쓰지 않는다 — `_move_tickets`는
        # `ticket_page_ids`에 있는 건만 옮기므로(offboarding/schemas.py: "서버가 고르지
        # 않는다"), 빈 목록을 보내면 그 루프가 아예 안 돈다. 계정 비활성화·후임 알림·
        # `offboarding_runs` 행 생성은 전부 이 앱 자신의 DB만 건드린다.
        target_id = os.environ.get("USE_AXIS_OFFB_TARGET_ID", "")
        successor_id = os.environ.get("USE_AXIS_OFFB_SUCCESSOR_ID", "")
        if target_id:
            st, before_run = call(ctx, "get", "/api/admin/offboarding?page=1", csrf)
            log["offboarding_before"] = {"status": st,
                                         "n": len(before_run.get("items", [])) if isinstance(before_run, dict) else None}

            st, target_before = call(ctx, "get", f"/api/admin/users/{target_id}", csrf)
            log["offboarding_target_active_before"] = {"status": st,
                                                        "active": (target_before or {}).get("active")}

            st, run_result = call(ctx, "post", f"/api/admin/offboarding/run/{target_id}", csrf, body={
                "ticket_page_ids": [], "successor_user_id": successor_id or None,
                "deactivate": True, "archive": False,
                "note": "[QA 조사용] U축 실행 이력 확인 — 2026-08-12, ticket_page_ids=[]",
            })
            log["offboarding_run"] = {"status": st, "body": run_result}
            run_id = (run_result or {}).get("run", {}).get("id") if st == 200 else None

            st, target_after = call(ctx, "get", f"/api/admin/users/{target_id}", csrf)
            log["offboarding_target_active_after"] = {"status": st,
                                                       "active": (target_after or {}).get("active")}

            if run_id:
                st, listed_r = call(ctx, "get", "/api/admin/offboarding?page=1", csrf)
                found_r = any((it.get("id") == run_id) for it in listed_r.get("items", []))
                log["offboarding_appears_in_list"] = {"status": st, "found": found_r}

                st, undo_result = call(ctx, "post", f"/api/admin/offboarding/{run_id}/undo", csrf)
                log["offboarding_undo"] = {"status": st, "body": undo_result}

                st, target_undone = call(ctx, "get", f"/api/admin/users/{target_id}", csrf)
                log["offboarding_target_active_after_undo"] = {"status": st,
                                                                "active": (target_undone or {}).get("active")}

        # ── 4. 감사 로그에 세 액션이 실제로 남았는지 확인 ─────────────────────
        for action in ("announcement.create", "ai_quota.create",
                       "offboarding.run", "offboarding.undo"):
            st, audit = call(ctx, "get",
                             f"/api/admin/audit?page=1&page_size=10&action={action}", csrf)
            log[f"audit_{action}"] = {"status": st,
                                      "n": len(audit.get("items", [])) if isinstance(audit, dict) else None}

        ctx.close()
        b.close()

    (OUT / "use_axis.json").write_text(json.dumps(log, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
