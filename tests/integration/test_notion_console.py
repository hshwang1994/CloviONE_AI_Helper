"""Notion 관리 화면 (9-4).

## 이 파일이 지키려는 것

1. **토큰이 응답에도 감사에도 안 남는다.** 토큰은 시크릿 파일 참조다. 한 번이라도 봉투에
   실리면 그 봉투는 되돌려 읽을 수 있는 자리(감사 로그, 진단 번들)로 흘러간다.
2. **연결 테스트가 원인을 구분한다.** "실패" 한 마디는 아무것도 알려 주지 않는다. 토큰 무효,
   데이터베이스 없음, 권한 없음은 운영자가 할 일이 전부 다르다.
3. **못 하는 것을 되는 척하지 않는다.** 운영 설치의 웹 프로세스는 시크릿 디렉터리에 쓸 수
   없다(systemd 하드닝). 그때 200 을 돌려주면 운영자는 토큰을 바꿨다고 믿는다.

⚠️ 판정이 상수가 아닌지 보려고 **값이 실제로 달라지는 표본**을 쓴다. 같은 엔드포인트를
서로 다른 세계에서 두 번 이상 부르고 응답이 따라 바뀌는지 본다 - 한 번만 부르고 원하는
문자열을 찾는 테스트는 구현이 상수를 돌려줘도 초록불이다.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from app.notion_console import probe_notion as probe

NOTION = "https://api.notion.com"
USERS_ME = f"{NOTION}/v1/users/me"
DATABASES = f"{NOTION}/v1/databases"


def _notion_error(code: str, status: int) -> dict:
    """노션이 실제로 주는 오류 봉투 모양."""
    return {"object": "error", "status": status, "code": code, "message": "irrelevant"}


@pytest.fixture()
def tokens_present(settings):
    for ref in (settings.notion_report_token_ref, settings.notion_docs_token_ref):
        (settings.secrets_dir / ref).write_text("secret-notion-token", encoding="utf-8")
    return settings


# ── 1. 권한 ──────────────────────────────────────────────────────────────────


def test_console_is_system_admin_only(client, login_as):
    """부서 범위로 좁혀질 수 있는 `admin` 은 못 들어온다.

    여기서 바뀌는 것은 **이 설치 전체가 어느 워크스페이스를 보는가**라 범위라는 개념이 없다.
    """
    login_as("admin")
    assert client.get("/api/admin/notion").status_code == 403

    login_as("system_admin")
    assert client.get("/api/admin/notion").status_code == 200


def test_database_id_setting_rejects_non_system_admin(client, login_as):
    """설정 API 로 우회해도 같은 게이트를 지난다.

    화면만 막고 API 를 열어 두면 게이트가 아니라 장식이다.
    """
    csrf = login_as("admin")
    denied = client.put(
        "/api/admin/settings/notion_tasks_database_id",
        json={"value": "a" * 32},
        headers={"X-CSRF-Token": csrf},
    )
    assert denied.status_code == 403

    csrf = login_as("system_admin")
    allowed = client.put(
        "/api/admin/settings/notion_tasks_database_id",
        json={"value": "a" * 32},
        headers={"X-CSRF-Token": csrf},
    )
    assert allowed.status_code == 200, allowed.text


# ── 2. 데이터베이스 id 를 화면에서 바꾼다 ────────────────────────────────────


def test_saving_database_id_changes_what_the_app_actually_queries(client, login_as):
    """저장한 값이 **실제 조회에 쓰인다.**

    화면에만 반영되고 조회는 옛 값으로 나가는 것이 이 저장소가 가장 싫어하는 거짓말이다
    ("설정했다는데 안 된다"). 그래서 화면 응답이 아니라 `Settings` 의 실제 필드를 본다 -
    그 필드를 모든 노션 조회 경로가 읽는다.
    """
    csrf = login_as("system_admin")
    live = client.app.state.settings
    before = live.notion_tasks_database_id
    new_id = "b" * 32

    assert before != new_id  # 표본이 실제로 달라지는지부터 확인한다

    saved = client.put(
        "/api/admin/settings/notion_tasks_database_id",
        json={"value": new_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert saved.status_code == 200, saved.text
    assert live.notion_tasks_database_id == new_id

    overview = client.get("/api/admin/notion").json()
    tasks = next(d for d in overview["databases"] if d["key"] == "notion_tasks_database_id")
    assert tasks["value"] == new_id
    assert tasks["source"] == "settings"
    # 언제 반영되는지 화면이 말해야 한다.
    assert overview["apply_note"].strip()


def test_clearing_database_id_falls_back_to_the_server_env_value(client, login_as, settings):
    """비우기 = 지우기가 아니라 **환경변수로 되돌리기**다.

    빈 값까지 덮으면 env 로 설정해 둔 기존 설치가 업그레이드하는 순간 통째로 미설정이 된다.
    """
    csrf = login_as("system_admin")
    env_value = settings.notion_tasks_database_id
    assert env_value

    client.put(
        "/api/admin/settings/notion_tasks_database_id",
        json={"value": "c" * 32},
        headers={"X-CSRF-Token": csrf},
    )
    assert client.app.state.settings.notion_tasks_database_id == "c" * 32

    client.put(
        "/api/admin/settings/notion_tasks_database_id",
        json={"value": ""},
        headers={"X-CSRF-Token": csrf},
    )
    overview = client.get("/api/admin/notion").json()
    tasks = next(d for d in overview["databases"] if d["key"] == "notion_tasks_database_id")
    assert tasks["source"] == "env"
    assert tasks["value"] == env_value


def test_database_id_rejects_a_pasted_url(client, login_as):
    """사람들이 붙여 넣는 것은 대개 주소창 링크 통째다.

    그대로 저장하면 조회 URL 이 망가지고 노션은 400 을 준다 - 화면은 '조회 실패' 로 그리고
    운영자는 토큰을 의심한다. 저장 시점에 끊는다.
    """
    csrf = login_as("system_admin")
    bad = client.put(
        "/api/admin/settings/notion_tasks_database_id",
        json={"value": "https://www.notion.so/team/" + "d" * 32 + "?v=abc"},
        headers={"X-CSRF-Token": csrf},
    )
    assert bad.status_code == 422


# ── 3. 토큰 ──────────────────────────────────────────────────────────────────


def test_token_is_never_echoed_back_or_written_to_the_audit_log(
    client, login_as, db, settings
):
    """토큰은 응답에도 감사에도 남지 않는다."""
    from app.audit.models import AuditLog

    csrf = login_as("system_admin")
    token = "ntn_super-secret-value-0123456789"
    saved = client.post(
        "/api/admin/notion/token",
        json={"field": "notion_report_token_ref", "value": token},
        headers={"X-CSRF-Token": csrf},
    )
    assert saved.status_code == 200, saved.text
    assert token not in saved.text

    # 파일에는 실제로 들어갔다(되는 척이 아니다).
    stored = (settings.secrets_dir / settings.notion_report_token_ref).read_text(
        encoding="utf-8"
    )
    assert stored == token

    # 그런데 화면은 다시 읽어 보여 주지 않는다.
    overview = client.get("/api/admin/notion")
    assert token not in overview.text
    report = next(
        t for t in overview.json()["token"]["items"] if t["field"] == "notion_report_token_ref"
    )
    assert report["configured"] is True
    assert "value" not in report

    rows = db.query(AuditLog).all()
    blob = json.dumps(
        [(r.action, r.object_type, r.before_json, r.after_json) for r in rows],
        ensure_ascii=False,
    )
    assert token not in blob
    assert "notion.token.update" in blob


def test_secret_provider_really_detects_a_directory_it_cannot_write(tmp_path):
    """`writable()` 자체가 정직한지 본다. **가짜를 꽂지 않고** 진짜 구현을 부른다.

    ⚠️ 이 테스트가 없었을 때 아래 화면 테스트만 있었고, 그 테스트는 `writable` 을 통째로
    가짜로 바꿔 놓고 돌았다. 그래서 `writable()` 첫 줄에 `return True` 를 넣어도 초록불이
    나왔다 - 즉 "못 쓰는 서버를 알아본다" 는 성질을 아무도 확인하지 않고 있었다.
    """
    from app.core.secret_refs import FileSecretReferenceProvider, SecretDirNotWritableError

    assert FileSecretReferenceProvider(tmp_path).writable() is True

    missing = FileSecretReferenceProvider(tmp_path / "no-such-dir")
    assert missing.writable() is False
    with pytest.raises(SecretDirNotWritableError):
        missing.write("notion_report_token", "value")

    # 경로가 디렉터리가 아니라 파일인 설치도 실제로 있다(설치 스크립트를 반만 돌린 경우).
    as_file = tmp_path / "secrets-is-a-file"
    as_file.write_text("", encoding="utf-8")
    assert FileSecretReferenceProvider(as_file).writable() is False


def test_secret_write_replaces_atomically_and_leaves_no_leftovers(tmp_path):
    """덮어쓰는 도중에 읽는 쪽이 **잘린 토큰**을 보면 안 된다(그 조회는 401 이 된다).

    임시 파일 -> `os.replace` 관용을 쓴 결과로, 쓰기가 끝난 뒤 디렉터리에는 토큰 파일
    하나만 남아야 한다. 임시 파일이 남으면 다음 사람이 그것을 secret 으로 착각한다.
    """
    from app.core.secret_refs import FileSecretReferenceProvider

    provider = FileSecretReferenceProvider(tmp_path)
    provider.write("notion_report_token", "first-token")
    provider.write("notion_report_token", "second-token")

    assert provider.get("notion_report_token").reveal() == "second-token"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["notion_report_token"]


def test_token_screen_says_so_when_the_server_cannot_write(client, login_as, monkeypatch):
    """쓸 수 없는 서버에서 **되는 척하지 않는다.**

    운영 설치에서 못 쓰는 것이 정상이다(systemd `ProtectSystem=strict`). 그때 화면은
    (a) 못 쓴다고 말하고 (b) 대신 무엇을 할지 알려 주고 (c) 저장 요청은 409 로 거절한다.
    """
    csrf = login_as("system_admin")
    secrets = client.app.state.secret_provider

    # 쓸 수 있는 세계
    writable = client.get("/api/admin/notion").json()["token"]
    assert writable["writable"] is True
    assert writable["manual_instruction"] is None

    # 쓸 수 없는 세계 — 응답이 따라 바뀌어야 한다
    monkeypatch.setattr(type(secrets), "writable", lambda self: False)

    def _refuse(self, name, value):
        from app.core.secret_refs import SecretDirNotWritableError

        raise SecretDirNotWritableError()

    monkeypatch.setattr(type(secrets), "write", _refuse)

    blocked = client.get("/api/admin/notion").json()["token"]
    assert blocked["writable"] is False
    assert blocked["manual_instruction"]
    # 무엇을 해야 하는지 말해야 한다 - 경로가 안내에 들어 있어야 실행 가능한 지시가 된다.
    assert str(secrets.directory) in blocked["manual_instruction"]

    refused = client.post(
        "/api/admin/notion/token",
        json={"field": "notion_report_token_ref", "value": "x" * 20},
        headers={"X-CSRF-Token": csrf},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "secret_dir_not_writable"


# ── 4. 연결 테스트가 원인을 구분한다 ─────────────────────────────────────────


def test_connection_test_reports_missing_token_without_calling_notion(
    client, login_as, fake_http
):
    """토큰 파일이 없으면 **부르지 않는다.** 부르면 그 실패가 네트워크 문제로 보인다."""
    csrf = login_as("system_admin")
    result = client.post("/api/admin/notion/test", headers={"X-CSRF-Token": csrf}).json()

    assert result["ok"] is False
    assert {t["result"] for t in result["tokens"]} == {probe.RESULT_TOKEN_MISSING}
    assert not [r for r in fake_http.requests if str(r.url).startswith(NOTION)]


def test_connection_test_distinguishes_invalid_token_from_missing_database(
    client, login_as, fake_http, tokens_present
):
    """세 원인이 서로 다른 어휘로 나온다. 같은 엔드포인트를 세 세계에서 부른다."""
    csrf = login_as("system_admin")

    def run() -> dict:
        return client.post("/api/admin/notion/test", headers={"X-CSRF-Token": csrf}).json()

    def tasks_of(result: dict) -> dict:
        return next(d for d in result["databases"] if d["key"] == "notion_tasks_database_id")

    # (a) 토큰이 무효다 — 데이터베이스는 아예 확인하지 않는다.
    fake_http.on(USERS_ME, status=401, json_body=_notion_error("unauthorized", 401))
    fake_http.on(DATABASES, status=200, json_body={"id": "x", "title": []})
    invalid = run()
    assert invalid["ok"] is False
    assert {t["result"] for t in invalid["tokens"]} == {probe.RESULT_TOKEN_INVALID}
    assert tasks_of(invalid)["result"] == probe.RESULT_TOKEN_INVALID

    # (b) 토큰은 통하는데 데이터베이스를 못 찾는다(id 오타 또는 통합에 미공유).
    fake_http.on(USERS_ME, status=200, json_body={"object": "user", "name": "포털 통합"})
    fake_http.on(DATABASES, status=404, json_body=_notion_error("object_not_found", 404))
    missing = run()
    assert missing["ok"] is False
    assert {t["result"] for t in missing["tokens"]} == {probe.RESULT_OK}
    assert tasks_of(missing)["result"] == probe.RESULT_NOT_FOUND
    # 두 원인을 다 적어 준다 - 노션이 둘을 같은 404 로 답하므로 아는 척하지 않는다.
    assert "공유" in tasks_of(missing)["message"]

    # (c) 권한이 없다.
    fake_http.on(DATABASES, status=403, json_body=_notion_error("restricted_resource", 403))
    forbidden = run()
    assert tasks_of(forbidden)["result"] == probe.RESULT_NO_PERMISSION

    # (d) 전부 정상.
    fake_http.on(
        DATABASES,
        status=200,
        json_body={"id": "ok", "title": [{"plain_text": "작업"}], "properties": {"제목": {}}},
    )
    good = run()
    assert good["ok"] is True
    assert tasks_of(good)["result"] == probe.RESULT_OK
    assert tasks_of(good)["title"] == "작업"

    # 네 판정이 실제로 서로 달랐다(상수를 돌려준 것이 아니다).
    assert len(
        {
            tasks_of(invalid)["result"],
            tasks_of(missing)["result"],
            tasks_of(forbidden)["result"],
            tasks_of(good)["result"],
        }
    ) == 4


def test_connection_test_survives_a_dead_network(client, login_as, fake_http, tokens_present):
    """노션에 못 닿아도 500 이 아니다. 500 은 '일시적 오류' 로 읽혀 재시도만 반복하게 만든다."""
    csrf = login_as("system_admin")
    fake_http.on_connect_error(USERS_ME)
    response = client.post("/api/admin/notion/test", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert {t["result"] for t in response.json()["tokens"]} == {probe.RESULT_UNREACHABLE}


def test_connection_test_does_not_record_the_token_in_the_audit_log(
    client, login_as, db, fake_http, tokens_present
):
    from app.audit.models import AuditLog

    csrf = login_as("system_admin")
    fake_http.on(USERS_ME, status=200, json_body={"object": "user", "name": "포털 통합"})
    fake_http.on(DATABASES, status=200, json_body={"id": "ok", "title": []})
    client.post("/api/admin/notion/test", headers={"X-CSRF-Token": csrf})

    rows = [r for r in db.query(AuditLog).all() if r.action == "notion.connection.test"]
    assert rows
    blob = json.dumps([r.after_json for r in rows], ensure_ascii=False)
    assert "secret-notion-token" not in blob


# ── 5. 스프린트 DB 미공유 진단 ───────────────────────────────────────────────


def test_sprint_diagnosis_says_the_two_sprints_are_different_things(client, login_as):
    """포털의 '이번 주' 와 팀의 노션 스프린트가 어긋나 있음을 화면이 말해야 한다.

    포털은 작업 DB 의 마감일로 이번 주를 계산하고, 팀은 별도의 노션 스프린트 DB 를 쓴다.
    어느 쪽도 고장 나지 않아서 아무 화면도 아무 말을 하지 않았다.
    """
    csrf = login_as("system_admin")
    unlinked = client.get("/api/admin/notion").json()["sprint"]
    assert unlinked["linked"] is False
    assert "마감일" in unlinked["portal_window"]
    assert unlinked["finding"].strip()
    assert unlinked["next_step"].strip()

    # 값을 넣으면 진단이 **따라 바뀐다**(상수가 아니다).
    client.put(
        "/api/admin/settings/notion_sprint_database_id",
        json={"value": "e" * 32},
        headers={"X-CSRF-Token": csrf},
    )
    linked = client.get("/api/admin/notion").json()["sprint"]
    assert linked["linked"] is True
    assert linked["sprint_database_id"] == "e" * 32
    assert linked["finding"] != unlinked["finding"]


def test_sprint_database_shows_as_not_shared_when_notion_answers_404(
    client, login_as, fake_http, tokens_present
):
    """계획서 §0-B 가 확인한 그 상태(조회 404)를 진단이 그대로 말한다."""
    csrf = login_as("system_admin")
    client.put(
        "/api/admin/settings/notion_sprint_database_id",
        json={"value": "f" * 32},
        headers={"X-CSRF-Token": csrf},
    )
    fake_http.on(USERS_ME, status=200, json_body={"object": "user", "name": "포털 통합"})

    def _by_id(request):
        if str(request.url).endswith("f" * 32):
            return (404, _notion_error("object_not_found", 404))
        return {"id": "ok", "title": []}

    fake_http.on_handler(DATABASES, _by_id)

    result = client.post("/api/admin/notion/test", headers={"X-CSRF-Token": csrf}).json()
    sprint = next(d for d in result["databases"] if d["key"] == "notion_sprint_database_id")
    assert sprint["result"] == probe.RESULT_NOT_FOUND
    assert "공유" in sprint["message"]
    # 작업 DB 는 멀쩡하다 — 스프린트만 어긋난 상태를 구분해 보여 준다.
    tasks = next(d for d in result["databases"] if d["key"] == "notion_tasks_database_id")
    assert tasks["result"] == probe.RESULT_OK


# ── 6. 빈 워크스페이스에 데이터베이스 만들기 ─────────────────────────────────


def test_create_database_needs_confirmation_and_refuses_when_one_already_exists(
    client, login_as, fake_http, tokens_present
):
    """되돌리기 어려운 동작이라 문 앞에서 막는다."""
    csrf = login_as("system_admin")
    body = {
        "key": "notion_tasks_database_id",
        "parent_page_id": "parent-page",
        "title": "작업",
        "confirm": False,
    }
    unconfirmed = client.post(
        "/api/admin/notion/databases", json=body, headers={"X-CSRF-Token": csrf}
    )
    assert unconfirmed.status_code == 422

    # 픽스처는 작업 DB id 를 이미 채워 둔다 — 확인을 눌러도 만들지 않는다.
    already = client.post(
        "/api/admin/notion/databases",
        json={**body, "confirm": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert already.status_code == 409
    assert not [
        r for r in fake_http.requests if r.method == "POST" and str(r.url) == DATABASES
    ]


def test_create_database_saves_the_new_id_into_the_settings(
    client, login_as, fake_http, tokens_present
):
    """만들었으면 id 를 곧바로 설정에 넣는다. 손으로 옮겨 적게 하면 거기서 오타가 난다."""
    csrf = login_as("system_admin")
    client.put(
        "/api/admin/settings/notion_documents_database_id",
        json={"value": ""},
        headers={"X-CSRF-Token": csrf},
    )
    client.app.state.settings.notion_documents_database_id = ""

    created_id = "9" * 32
    fake_http.on_handler(
        DATABASES,
        lambda request: {"id": created_id, "title": [{"plain_text": "문서"}]}
        if request.method == "POST"
        else None,
    )

    response = client.post(
        "/api/admin/notion/databases",
        json={
            "key": "notion_documents_database_id",
            "parent_page_id": "parent-page",
            "title": "문서",
            "confirm": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["created"] is True
    assert payload["database_id"] == created_id
    assert client.app.state.settings.notion_documents_database_id == created_id


def test_create_database_reports_notion_failure_instead_of_claiming_success(
    client, login_as, fake_http, tokens_present
):
    """노션이 거절하면 만들었다고 말하지 않는다."""
    csrf = login_as("system_admin")
    client.app.state.settings.notion_documents_database_id = ""
    fake_http.on_handler(
        DATABASES,
        lambda request: (403, _notion_error("restricted_resource", 403))
        if request.method == "POST"
        else None,
    )
    response = client.post(
        "/api/admin/notion/databases",
        json={
            "key": "notion_documents_database_id",
            "parent_page_id": "parent-page",
            "title": "문서",
            "confirm": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["created"] is False
    assert payload["result"] == probe.RESULT_NO_PERMISSION
    assert client.app.state.settings.notion_documents_database_id == ""


def test_concurrent_create_requests_do_not_create_two_databases(
    client, login_as, fake_http, tokens_present
):
    """두 요청이 거의 동시에 눌려도 노션에 데이터베이스가 하나만 생겨야 한다.

    `guard_create`의 '이미 있으면 안 만든다' 검사와 실제 노션 호출 + 설정 저장 사이에는
    시간이 걸리는 진짜 외부 호출이 끼어 있다. 그 틈에 두 번째 요청이 들어오면 둘 다 같은
    '아직 없음'을 보고 통과해 노션에 데이터베이스가 두 개 생기고, 하나는 설정에 못 들어간
    채 워크스페이스에 고아로 남는다 - 그래서 노션의 실제 생성 호출이 **한 번만** 나가야
    한다(그 자체가, 두 번째 요청이 아예 노션까지 못 갔다는 증거다).
    """
    csrf = login_as("system_admin")
    client.app.state.settings.notion_documents_database_id = ""

    def _create_handler(request):
        if request.method != "POST":
            return None
        # 레이스가 벌어질 시간을 넉넉히 준다 - 잠금이 없으면 그 사이 두 번째 요청도
        # guard_create를 통과해 이 핸들러를 또 부른다.
        time.sleep(0.2)
        return {"id": "9" * 32, "title": [{"plain_text": "문서"}]}

    fake_http.on_handler(DATABASES, _create_handler)

    body = {
        "key": "notion_documents_database_id",
        "parent_page_id": "parent-page",
        "title": "문서",
        "confirm": True,
    }
    results: list = []

    def _fire():
        results.append(
            client.post(
                "/api/admin/notion/databases", json=body, headers={"X-CSRF-Token": csrf}
            )
        )

    threads = [threading.Thread(target=_fire) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert len(results) == 2
    # 하나는 만들고(200, created=True), 다른 하나는 그 사이 값이 채워진 것을 보고
    # '이미 있다'(409)로 막혀야 한다 - 둘 다 200으로 만들어지면 중복 생성이다.
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409], [
        (r.status_code, r.text) for r in results
    ]

    created_true = [r for r in results if r.status_code == 200 and r.json().get("created") is True]
    assert len(created_true) == 1, [r.json() for r in results]

    post_calls = [
        r for r in fake_http.requests if r.method == "POST" and str(r.url) == DATABASES
    ]
    assert len(post_calls) == 1, (
        f"노션 데이터베이스 생성 호출이 {len(post_calls)}번 나갔다 - 중복 생성"
    )
