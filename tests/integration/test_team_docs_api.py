"""팀 공간 > 문서 API 통합 테스트 (§17 + 분류 개편).

목록·상세·즐겨찾기·최근·필터(문서 종류/업무 분야/프로젝트/기술 태그)·생성·동기화 게이트
+ 인증/CSRF/기능플래그 + 장애 격리.

qa-contract-change: 세 시험이 문서 미러 동기화 라우트(POST /api/team-docs/sync)와 노션 쓰기 403 매핑을 확인했고 S14 가 그 라우트와 그 구현체를 함께 지웠다(D-284) — 거부할 상대도 부를 라우트도 없으므로, 권한 단언 둘을 «라우트가 돌아오지 않는다» 하나로 바꾸고 쓰기 거부 매핑 시험은 걷었다.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.models_base import utcnow
from app.team_docs.models import DocumentCache, join_names
from tests.conftest import DEFAULT_TEST_PASSWORD, PROJECT_ROOT, TEST_DOCS_DB

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]

_NAME_FIELDS = ("project_names", "author_names", "tech_tags", "type_names", "category_names")


def _add_doc(db, pid, title, **over):
    for f in _NAME_FIELDS:
        if over.get(f) is not None:
            v = over[f]
            over[f] = join_names(v if isinstance(v, list) else [v])
    # 소속(0060)은 문서 자신이 든다. 이 파일이 검사하는 것은 소속 게이트가 아니라
    # 편집·목록 동작이므로 조직 공통으로 둔다 — 소속을 안 주면 전역 관리자만 보인다.
    over.setdefault("owner_kind", "organization")
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


# 즐겨찾기 시험은 여기 없다 (S14 · C2) — 그 축은 정본 문서로 옮겼고
# `tests/integration/test_knowledge_favorites.py` 가 고정한다.


def test_detail_unpacks_the_saved_body_into_blocks(client, login_as, db):
    """상세는 저장된 본문을 화면 블록으로 풀어 준다.

    본문을 가짜 Notion 서버가 아니라 **문서 행에 직접 심는다** (S14). 자체 DB 가 정본이 된
    뒤에는 상세가 저장된 마크다운만 읽으므로, 페이크만 두면 블록이 빈 목록으로 와서 이
    시험이 아무것도 증명하지 못한다.

    옛 기대값에 있던 `unsupported` 는 미러에만 있는 종류였다 — 편집기가 표현할 수 없는
    Notion 블록(이미지·표·컬럼)을 그 자리표시자로 바꾸는 것이
    `app/team_docs/notion_docs.py` 이고, 마크다운 본문에는 그런 블록이 아예 없다. 그
    자리표시자 자체의 규칙은 `tests/unit/test_notion_blocks_roundtrip.py` 가 따로 고정한다.
    """
    login_as("user", email="det@goodmit.co.kr")
    _add_doc(db, "x1", "문서 상세", original_url="https://orig",
             body_markdown="# 머리말\n본문 내용")
    r = client.get("/api/team-docs/x1").json()
    assert r["document"]["title"] == "문서 상세"
    assert [b["kind"] for b in r["blocks"]] == ["heading_1", "paragraph"]
    assert [b["text"] for b in r["blocks"]] == ["머리말", "본문 내용"]
    assert r["blocks_error"] is None


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


# 휴지통 문서의 댓글 시험도 여기 없다 (S14 · C2). 댓글은 정본 문서에 붙었고, 그쪽의
# 「범위 밖은 404」는 `tests/integration/test_knowledge_comments.py` 가 네 경로 전부에서
# 고정한다.


def test_filters_endpoint_returns_fixed_lists_and_projects(client, login_as, db):
    login_as("user", email="filt@goodmit.co.kr")
    _add_doc(db, "a", "A", project_names=["포스코DX"])
    _add_doc(db, "b", "B", project_names=["하이닉스"])
    f = client.get("/api/team-docs/filters").json()
    assert "회의록" in f["doc_types"] and "보안" in f["work_fields"] and "Docker" in f["tech_tags"]
    assert set(f["projects"]) == {"포스코DX", "하이닉스"}


def test_create_document(client, login_as, db):
    """새 문서가 만들어지고, 분류·프로젝트·작성자가 채워진 채 목록에 바로 나온다.

    가짜 Notion 서버를 **일부러 안 깐다** (S14). 자체 DB 소스의 생성은 나가는 호출이 없어야
    하고, 페이크를 깔아 두면 몰래 나가는 왕복이 하나 생겨도 이 시험이 그대로 통과한다.
    등록하지 않은 주소로 나가면 `fake_http` 가 실패로 답하므로, 안 까는 것 자체가 검사다.

    page id 도 이제 **우리가 짓는다**(`app/team_docs/repository_native.py::create` 의 UUID).
    응답이 준 그 id 로 목록에서 찾는다 — 시험이 미리 정한 문자열로 찾으면 소스가 정하던
    시절의 값을 고정하게 되고, 그건 지금 아무도 지키지 않는 계약이다.
    """
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
    assert doc["id"], "만든 문서의 딥링크 키가 없으면 화면이 상세로 갈 수 없다"
    assert any(d["id"] == doc["id"] for d in client.get("/api/team-docs").json()["items"])


def test_create_document_requires_csrf(client, login_as):
    login_as("user", email="mkcsrf@goodmit.co.kr")
    assert client.post("/api/team-docs", json={"title": "x"}).status_code == 403


def test_create_document_rejects_bad_taxonomy(client, login_as):
    csrf = login_as("user", email="mkbad@goodmit.co.kr")
    assert client.post("/api/team-docs", json={"title": "문서", "document_type": "이상함"},
                       headers={"X-CSRF-Token": csrf}).status_code == 422
    assert client.post("/api/team-docs", json={"title": "문서", "tech_tags": ["없는태그"]},
                       headers={"X-CSRF-Token": csrf}).status_code == 422


# 여기 있던 `test_create_document_maps_write_forbidden` 을 걷었다. 문서 생성이 소스의
# 403 을 `notion_docs_write_forbidden` 으로 옮겨 담는지 보던 시험인데, S14 뒤로 생성은
# **우리 표에 행을 하나 넣는 일**이라 거부할 상대가 없다(D-284). 권한 자체는 위
# `test_create_document` 와 아래 범위 시험들이 본다.


def test_projects_endpoint_falls_back_to_cache_without_notion(client, login_as, db):
    # 고를 프로젝트가 한 건도 안 나오면 **문서가 이미 쓰고 있는** 프로젝트 이름으로 폴백한다
    # (§17.4 격리). 미러 시절에는 그 「안 나온다」가 Notion 조회 실패였고, 자체 DB 소스에서는
    # 프로젝트 표가 비어 있는 경우다 — 어느 쪽이든 작성 폼이 빈 선택지로 열리면 안 된다는
    # 것이 이 시험이 지키는 계약이고, 그 폴백은 `app/team_docs/router.py::all_projects` 에
    # 한 곳으로 있다.
    login_as("user", email="projfb@goodmit.co.kr")
    _add_doc(db, "pj1", "문서", project_names=["프로젝트X"])
    r = client.get("/api/team-docs/projects")
    assert r.status_code == 200
    assert "프로젝트X" in r.json()["projects"]


def test_the_sync_endpoint_is_gone_for_everyone(client, login_as):
    """🔴 `POST /api/team-docs/sync` 가 **없다** (S14 · D-284).

    예전에는 이 자리에 둘이 있었다: 「운영자만 부를 수 있다」와 「노션이 없으면 곱게
    실패한다」. 문서 미러 동기화가 사라지면서 라우트째 없어졌으므로 그 둘은 지킬 대상이
    없다 — 대신 **되살아나지 않는 것**을 본다.

    권한으로 확인하지 않고 **없음**으로 확인하는 이유: 라우트가 돌아오면 그 순간 제품이
    정본 표에 외부 소스를 덮어쓰는 경로를 다시 갖는다. 그때 403 을 단언하는 시험은
    「막혀 있다」로 초록을 내며 그 사실을 감춘다.
    """
    for role, email in (("user", "synguser@goodmit.co.kr"), ("operator", "op@goodmit.co.kr")):
        csrf = login_as(role, email=email)
        r = client.post("/api/team-docs/sync", headers={"X-CSRF-Token": csrf})
        assert r.status_code == 405, (
            f"{role} 에게 문서 동기화 라우트가 살아 있다: {r.status_code} {r.text[:200]}"
        )


def test_feature_flag_off_hides_team_docs(db_url, tmp_path, fake_clock, fake_http):
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
        _env_file=None, app_env="test", database_url=db_url,
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
