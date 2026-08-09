"""팀 공간 > 문서 API 통합 테스트 (§17 + 분류 개편).

목록·상세·즐겨찾기·최근·필터(문서 종류/업무 분야/프로젝트/기술 태그)·생성·동기화 게이트
+ 인증/CSRF/기능플래그 + 장애 격리.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.models_base import utcnow
from app.team_docs.models import DocumentCache, join_names
from tests.conftest import DEFAULT_TEST_PASSWORD, PROJECT_ROOT, TEST_DOCS_DB

pytestmark = pytest.mark.integration

_NAME_FIELDS = ("project_names", "author_names", "tech_tags", "type_names", "category_names")


def _add_doc(db, pid, title, **over):
    for f in _NAME_FIELDS:
        if over.get(f) is not None:
            v = over[f]
            over[f] = join_names(v if isinstance(v, list) else [v])
    row = DocumentCache(notion_page_id=pid, title=title, synced_at=utcnow(), **over)
    db.add(row)
    db.commit()
    return row


def test_requires_auth(client):
    assert client.get("/api/team-docs").status_code == 401


def test_list_search_filter_sort(client, login_as, db):
    login_as("user", email="docs@goodmit.co.kr")
    _add_doc(db, "d1", "계약서 A", document_type="보고서", work_field="보안",
             tech_tags=["Docker"], project_names=["포스코DX"], last_edited="2026-07-02T00:00:00.000Z")
    _add_doc(db, "d2", "제안서 B", document_type="회의록", work_field="개발",
             last_edited="2026-07-05T00:00:00.000Z")
    _add_doc(db, "d3", "보관 문서", archived=True)

    listing = client.get("/api/team-docs").json()
    assert listing["total"] == 2
    assert listing["items"][0]["id"] == "d2"  # 최근 수정순

    assert client.get("/api/team-docs?q=계약").json()["total"] == 1
    assert client.get("/api/team-docs?doc_type=회의록").json()["total"] == 1
    assert client.get("/api/team-docs?work_field=보안").json()["total"] == 1
    assert client.get("/api/team-docs?tech=Docker").json()["total"] == 1
    assert client.get("/api/team-docs?project=포스코DX").json()["total"] == 1
    titles = [i["title"] for i in client.get("/api/team-docs?sort=title").json()["items"]]
    assert titles == sorted(titles)


def test_tech_filter_is_exact_token(client, login_as, db):
    login_as("user", email="tok@goodmit.co.kr")
    _add_doc(db, "r1", "A", tech_tags=["Docker"])
    _add_doc(db, "r2", "B", tech_tags=["Kubernetes"])
    res = client.get("/api/team-docs?tech=Docker").json()
    assert res["total"] == 1 and res["items"][0]["id"] == "r1"


def test_view_exposes_new_taxonomy(client, login_as, db):
    login_as("user", email="view@goodmit.co.kr")
    _add_doc(db, "v1", "문서", document_type="회의록", work_field="개발", tech_tags=["Docker", "Linux"])
    item = client.get("/api/team-docs").json()["items"][0]
    assert item["document_type"] == "회의록" and item["work_field"] == "개발"
    assert set(item["tech_tags"]) == {"Docker", "Linux"}


def test_favorite_toggle_and_favorites_only(client, login_as, db):
    csrf = login_as("user", email="fav@goodmit.co.kr")
    _add_doc(db, "f1", "문서")
    r = client.post("/api/team-docs/f1/favorite?on=true", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["is_favorite"] is True
    assert client.get("/api/team-docs?favorites=true").json()["total"] == 1
    client.post("/api/team-docs/f1/favorite?on=false", headers={"X-CSRF-Token": csrf})
    assert client.get("/api/team-docs?favorites=true").json()["total"] == 0


def test_favorite_requires_csrf(client, login_as, db):
    login_as("user", email="csrfd@goodmit.co.kr")
    _add_doc(db, "c1", "문서")
    assert client.post("/api/team-docs/c1/favorite?on=true").status_code == 403


def test_detail_blocks_and_records_recent(client, login_as, db, settings, fake_http):
    (settings.secrets_dir / "notion_docs_token").write_text("faketoken", encoding="utf-8")
    fake_http.on(
        "https://api.notion.com/v1/blocks/x1/children",
        json_body={"results": [
            {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "머리말"}]}},
            {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "본문 내용"}]}},
            {"type": "image", "image": {}},
        ], "has_more": False},
    )
    login_as("user", email="det@goodmit.co.kr")
    _add_doc(db, "x1", "문서 상세", original_url="https://orig")
    r = client.get("/api/team-docs/x1").json()
    assert r["document"]["title"] == "문서 상세"
    assert [b["kind"] for b in r["blocks"]] == ["heading_1", "paragraph", "unsupported"]
    assert r["blocks_error"] is None
    assert any(d["id"] == "x1" for d in client.get("/api/team-docs/filters").json()["recent"])


def test_detail_missing_returns_404(client, login_as):
    login_as("user", email="miss@goodmit.co.kr")
    assert client.get("/api/team-docs/nope").status_code == 404


def test_trashed_document_detail_is_not_found(client, login_as, db):
    """휴지통 문서는 상세로도 없는 것으로 취급한다 (H2, 티켓과 같은 규칙 —
    app/tickets/service.py::ensure_not_trashed 주석 참고).

    이 판정이 없으면 지운 문서가 계속 상세로 열리고(제목·본문 그대로), 그 상태에서 계속
    편집·댓글·즐겨찾기가 되는데 보관기간이 끝나면 그 문서와 함께 조용히 사라진다."""
    csrf = login_as("operator", email="trashdet@goodmit.co.kr")
    _add_doc(db, "td1", "지울 문서")
    r = client.post("/api/team-docs/td1/trash", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text

    detail = client.get("/api/team-docs/td1")
    assert detail.status_code == 404, f"휴지통 문서가 상세로 열린다: {detail.status_code} {detail.text}"


def test_trashed_document_comments_are_not_found(client, login_as, db):
    """댓글 목록·작성도 상세와 같은 판정을 지나야 한다 — 안 그러면 지운 문서의 논의가
    보관기간 동안 계속된다(상세는 막혀도 딥링크로 댓글만 열리는 구멍)."""
    csrf = login_as("operator", email="trashcom@goodmit.co.kr")
    _add_doc(db, "td2", "지울 문서 2")
    r = client.post("/api/team-docs/td2/trash", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text

    listing = client.get("/api/team-docs/td2/comments")
    assert listing.status_code == 404, f"휴지통 문서의 댓글 목록이 열린다: {listing.status_code} {listing.text}"

    created = client.post("/api/team-docs/td2/comments", json={"body": "댓글"},
                          headers={"X-CSRF-Token": csrf})
    assert created.status_code == 404, f"휴지통 문서에 댓글을 달 수 있다: {created.status_code} {created.text}"


def test_filters_endpoint_returns_fixed_lists_and_projects(client, login_as, db):
    login_as("user", email="filt@goodmit.co.kr")
    _add_doc(db, "a", "A", project_names=["포스코DX"])
    _add_doc(db, "b", "B", project_names=["하이닉스"])
    f = client.get("/api/team-docs/filters").json()
    assert "회의록" in f["doc_types"] and "보안" in f["work_fields"] and "Docker" in f["tech_tags"]
    assert set(f["projects"]) == {"포스코DX", "하이닉스"}


def _notion_write_fakes(fake_http):
    fake_http.on(
        # 문서 DB id 는 설치처 고유값이라 소스 기본값이 없다 - 테스트 설정이 쓰는 값을 그대로 쓴다.
        f"https://api.notion.com/v1/databases/{TEST_DOCS_DB}",
        json_body={"properties": {"프로젝트": {"type": "relation", "relation": {"database_id": "projdb"}}}},
    )
    fake_http.on(
        "https://api.notion.com/v1/databases/projdb/query",
        json_body={"results": [{"id": "pj1", "properties": {"Name": {"type": "title", "title": [{"plain_text": "포스코DX"}]}}}], "has_more": False},
    )


def test_create_document(client, login_as, db, settings, fake_http):
    (settings.secrets_dir / "notion_docs_token").write_text("faketoken", encoding="utf-8")
    _notion_write_fakes(fake_http)
    fake_http.on(
        "https://api.notion.com/v1/pages",
        json_body={"id": "newdoc", "url": "https://notion/newdoc",
                   "created_time": "2026-07-28T00:00:00.000Z", "last_edited_time": "2026-07-28T00:00:00.000Z"},
    )
    csrf = login_as("user", email="mk@goodmit.co.kr")
    r = client.post(
        "/api/team-docs",
        json={"title": "회의 문서", "document_type": "회의록", "work_field": "개발",
              "tech_tags": ["Docker"], "project": "포스코DX", "status": "초안", "body": "첫 줄\n둘째 줄"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    doc = r.json()["document"]
    assert doc["title"] == "회의 문서" and doc["document_type"] == "회의록"
    assert doc["work_field"] == "개발" and doc["tech_tags"] == ["Docker"]
    assert doc["projects"] == ["포스코DX"]
    # 작성자 자동 채움: 만든 사람 이름이 채워진다(매핑 없어도 앱 캐시엔 표시).
    assert doc["author_names"] == ["테스트 사용자"]
    assert any(d["id"] == "newdoc" for d in client.get("/api/team-docs").json()["items"])


def test_create_document_requires_csrf(client, login_as):
    login_as("user", email="mkcsrf@goodmit.co.kr")
    assert client.post("/api/team-docs", json={"title": "x"}).status_code == 403


def test_create_document_rejects_bad_taxonomy(client, login_as):
    csrf = login_as("user", email="mkbad@goodmit.co.kr")
    assert client.post("/api/team-docs", json={"title": "문서", "document_type": "이상함"},
                       headers={"X-CSRF-Token": csrf}).status_code == 422
    assert client.post("/api/team-docs", json={"title": "문서", "tech_tags": ["없는태그"]},
                       headers={"X-CSRF-Token": csrf}).status_code == 422


def test_create_document_maps_write_forbidden(client, login_as, db, settings, fake_http):
    (settings.secrets_dir / "notion_docs_token").write_text("faketoken", encoding="utf-8")
    _notion_write_fakes(fake_http)
    fake_http.on("https://api.notion.com/v1/pages", status=403, json_body={"message": "no write"})
    csrf = login_as("user", email="mkforbid@goodmit.co.kr")
    r = client.post(
        "/api/team-docs",
        json={"title": "권한없음 문서", "document_type": "회의록", "work_field": "개발"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "notion_docs_write_forbidden"


def test_projects_endpoint_falls_back_to_cache_without_notion(client, login_as, db):
    # Notion 토큰 미설정 → 전체 프로젝트 조회 실패 → 캐시(문서 보유) 프로젝트로 폴백(§17.4 격리).
    login_as("user", email="projfb@goodmit.co.kr")
    _add_doc(db, "pj1", "문서", project_names=["프로젝트X"])
    r = client.get("/api/team-docs/projects")
    assert r.status_code == 200
    assert "프로젝트X" in r.json()["projects"]


def test_sync_requires_operator(client, login_as):
    csrf = login_as("user", email="synguser@goodmit.co.kr")
    assert client.post("/api/team-docs/sync", headers={"X-CSRF-Token": csrf}).status_code == 403


def test_operator_sync_faults_gracefully_without_notion(client, login_as):
    csrf = login_as("operator", email="op@goodmit.co.kr")
    r = client.post("/api/team-docs/sync", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert r.json()["sync"]["status"] == "error"


def test_feature_flag_off_hides_team_docs(db_path, tmp_path, fake_clock, fake_http):
    import shutil

    from app.core.config import Settings
    from app.main import create_app
    from app.users.service import create_user

    cfg = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg)
    (cfg / "feature-flags.json").write_text(json.dumps({"team_docs_enabled": False}), encoding="utf-8")
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    settings = Settings(
        _env_file=None, app_env="test", database_url=f"sqlite:///{db_path.as_posix()}",
        session_secret="test-session-secret", cookie_secure=False,
        config_dir=cfg, secrets_dir=secrets_dir, data_dir=tmp_path,
    )
    app = create_app(settings, clock=fake_clock, outbound_transport=fake_http.transport())
    with app.state.session_factory() as s:
        create_user(s, email="ff@goodmit.co.kr", display_name="FF", password=DEFAULT_TEST_PASSWORD,
                    settings=settings, actor_role="system_admin", role="user", active=True,
                    must_change_password=False)
        s.commit()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "ff@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        assert c.get("/api/team-docs").status_code == 404
