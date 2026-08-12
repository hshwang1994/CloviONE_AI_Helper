"""휴지통 실제 왕복 실행 (`USE-01` 마지막 남은 항목 — 문서 trash → list → restore).

기존 `trash_e2e.py`는 빈 상태와 폴링만 확인했지 실제로 문서를 넣고 빼 본 적이 없었다.
막고 있던 이유는 "실제 문서를 trash에 넣으려면 새 문서 생성(Notion 쓰기, D-21) 또는 기존
실문서를 잠시 건드려야 한다"였는데, 둘 다 필요 없다 — `app/trash/service.py`를 직접 읽으면
`move_to_trash`/`restore`는 **Notion을 전혀 건드리지 않는다**("노션은 손대지 않는다", 코드
docstring). Notion 호출은 `purge`(영구삭제)에만 있고 이 스크립트는 그 경로를 부르지 않는다.

그래서 이번엔 **완전히 합성된 문서 한 건**(`notion_page_id="qa-trash-axis-e2e-doc-1"`)을
`document_cache`에 직접 심는다 — 실제 동기화를 거치지 않은 가짜 행이라 실고객 Notion
워크스페이스와 무관하고, 로컬 dev 서버(이 저장소 자신의 `var/web.sqlite3`)에만 존재해
다른 사람 화면에도 영향이 없다. 왕복이 끝나면 그 행을 지운다(원상복구).

확인 순서: 상세 200(존재) → POST trash → 상세 404(휴지통은 "없음"과 같은 취급, H2) →
GET /api/trash 목록에 등장 → POST restore → 상세 200(복귀) → 목록에서 사라짐 → 감사 로그
(`team_docs.trash`, `trash.restore`) 둘 다 이 문서의 object_id로 실제로 남았는지 확인.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ui_qa.auth import ensure_session  # noqa: E402

BASE = os.environ.get("TRASH_AXIS_BASE_URL", "http://127.0.0.1:8099")
OUT = Path("dist/trash-axis-e2e")
DOC_PAGE_ID = "qa-trash-axis-e2e-doc-1"
DOC_TITLE = "[QA 조사용] USE-01 휴지통 왕복 확인용 합성 문서 — 실제 Notion 문서 아님"


def seed_document() -> None:
    """document_cache 에 완전히 합성된 문서 한 행을 심는다(Notion 미접촉)."""
    import app.models_registry  # noqa: F401 — Base.metadata에 전 모델 등록(FK 해석용, alembic/env.py와 동일)
    from app.core.config import Settings
    from app.core.db import make_engine, make_session_factory
    from app.team_docs.models import DocumentCache

    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as db:
        existing = db.query(DocumentCache).filter_by(notion_page_id=DOC_PAGE_ID).one_or_none()
        if existing is not None:
            db.delete(existing)
            db.flush()
        db.add(DocumentCache(notion_page_id=DOC_PAGE_ID, title=DOC_TITLE,
                             document_type="etc", owner="QA E2E"))
        db.commit()


def cleanup_document() -> None:
    import app.models_registry  # noqa: F401
    from app.core.config import Settings
    from app.core.db import make_engine, make_session_factory
    from app.team_docs.models import DocumentCache
    from app.trash.models import TrashItem

    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    with factory() as db:
        db.query(TrashItem).filter_by(notion_page_id=DOC_PAGE_ID).delete()
        db.query(DocumentCache).filter_by(notion_page_id=DOC_PAGE_ID).delete()
        db.commit()


def call(ctx, method: str, path: str, csrf: str, body=None):
    fn = getattr(ctx.request, method)
    kw = {"timeout": 60_000, "headers": {"X-CSRF-Token": csrf, "Content-Type": "application/json"}}
    if body is not None:
        kw["data"] = body
    r = fn(BASE + path, **kw)
    try:
        return r.status, r.json()
    except Exception:  # noqa: BLE001
        return r.status, (r.text() or "")[:300]


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    log: dict = {}
    seed_document()
    log["seeded"] = DOC_PAGE_ID
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            sess = ensure_session(b, BASE, Path("dist/trash-axis-e2e-session"), log=print)
            ctx = b.new_context(storage_state=sess.storage_state)
            csrf = ctx.request.get(BASE + "/api/me", timeout=30_000).json().get("csrf_token", "")
            log["csrf"] = bool(csrf)

            st, before = call(ctx, "get", f"/api/team-docs/{DOC_PAGE_ID}", csrf)
            log["detail_before_trash"] = {"status": st, "title": (before or {}).get("document", {}).get("title")}

            st, trashed = call(ctx, "post", f"/api/team-docs/{DOC_PAGE_ID}/trash", csrf)
            log["trash_call"] = {"status": st, "body": trashed}

            st, gone = call(ctx, "get", f"/api/team-docs/{DOC_PAGE_ID}", csrf)
            log["detail_after_trash"] = {"status": st}

            st, trash_list = call(ctx, "get", "/api/trash", csrf)
            items = trash_list.get("items", []) if isinstance(trash_list, dict) else []
            row = next((it for it in items if it.get("notion_page_id") == DOC_PAGE_ID), None)
            log["appears_in_trash_list"] = {"status": st, "found": row is not None,
                                            "type_label": (row or {}).get("type_label")}
            trash_id = (row or {}).get("id")

            if trash_id:
                st, restored = call(ctx, "post", f"/api/trash/{trash_id}/restore", csrf)
                log["restore_call"] = {"status": st, "body": restored}

                st, back = call(ctx, "get", f"/api/team-docs/{DOC_PAGE_ID}", csrf)
                log["detail_after_restore"] = {"status": st, "title": (back or {}).get("document", {}).get("title")}

                st, trash_list_after = call(ctx, "get", "/api/trash", csrf)
                items_after = trash_list_after.get("items", []) if isinstance(trash_list_after, dict) else []
                still_there = any(it.get("notion_page_id") == DOC_PAGE_ID for it in items_after)
                log["gone_from_trash_after_restore"] = {"status": st, "still_there": still_there}

            for action in ("team_docs.trash", "trash.restore"):
                st, audit = call(ctx, "get", f"/api/admin/audit?page=1&page_size=20&action={action}", csrf)
                audit_items = audit.get("items", []) if isinstance(audit, dict) else []
                hit = any(it.get("object_id") == DOC_PAGE_ID for it in audit_items)
                log[f"audit_{action}"] = {"status": st, "found_for_this_doc": hit}

            ctx.close()
            b.close()
    finally:
        cleanup_document()
        log["cleaned_up"] = True

    (OUT / "trash_axis.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    # ensure_ascii=True for the console print — Windows cp949 콘솔은 이모지·em-dash 같은
    # 문자를 못 뱉는다(디스크 파일은 위에서 이미 utf-8로 정확히 썼다, 이건 표시 전용).
    print(json.dumps(log, ensure_ascii=True, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
