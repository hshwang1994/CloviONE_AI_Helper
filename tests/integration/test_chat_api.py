import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_TEST_PASSWORD, PROJECT_ROOT

pytestmark = pytest.mark.integration

CLIENT_MSG_ID = "m0123456789abcdef0123456789abcdef"


@pytest.fixture()
def user_csrf(login_as):
    return login_as("user")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _new_conversation(client, csrf):
    r = client.post("/api/conversations", json={}, headers=_headers(csrf))
    assert r.status_code == 201
    return r.json()["conversation"]


def test_create_and_list_conversations(client, user_csrf):
    conv = _new_conversation(client, user_csrf)
    assert conv["title"] == "새 대화"
    r = client.get("/api/conversations")
    assert r.status_code == 200
    assert any(c["id"] == conv["id"] for c in r.json()["items"])


def test_list_conversations_q_searches_title_and_body(client, user_csrf):
    """AI-38: 제목 검색만으로는 "내가 만든 티켓 보여줘" 같은 흔한 제목 아래 묻힌 대화를
    못 찾는다 — 사용자 메시지 본문도 함께 본다."""
    named = _new_conversation(client, user_csrf)
    client.patch(
        f"/api/conversations/{named['id']}", json={"title": "분기 마감 정리"}, headers=_headers(user_csrf)
    )
    body_only = _new_conversation(client, user_csrf)
    client.post(
        f"/api/conversations/{body_only['id']}/messages",
        json={"content": "포스코DX 프로젝트 진행률 알려줘", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    unrelated = _new_conversation(client, user_csrf)

    by_title = client.get("/api/conversations", params={"q": "마감"}).json()["items"]
    assert {c["id"] for c in by_title} == {named["id"]}

    by_body = client.get("/api/conversations", params={"q": "포스코DX"}).json()["items"]
    assert {c["id"] for c in by_body} == {body_only["id"]}

    no_match = client.get("/api/conversations", params={"q": "존재하지않는검색어"}).json()["items"]
    assert no_match == []

    assert unrelated["id"] not in {c["id"] for c in by_title} | {c["id"] for c in by_body}


def test_list_conversations_q_does_not_leak_other_users_messages(client, login_as, make_user):
    """대화 소유권 필터(user_id) 밑에서 서브쿼리로 본문을 보므로, 다른 사용자의 메시지
    내용이 검색어와 맞아도 이 사용자의 목록엔 나오면 안 된다(IDOR)."""
    other = make_user("other@goodmit.co.kr")
    other_csrf = login_as("user", email="other@goodmit.co.kr")
    other_conv = _new_conversation(client, other_csrf)
    client.post(
        f"/api/conversations/{other_conv['id']}/messages",
        json={"content": "비밀 프로젝트 알파 진행 상황", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(other_csrf),
    )

    my_csrf = login_as("user", email="user@goodmit.co.kr")
    result = client.get("/api/conversations", params={"q": "비밀 프로젝트"}).json()["items"]
    assert result == []


def test_list_conversations_reports_total_and_respects_limit(client, user_csrf):
    """AI-18: 대화 목록이 100개로 고정 상한이었고 그 이상은 total도 offset도 없어 화면에서
    영영 볼 방법이 없었다. limit이 실제로 자르고, total이 (limit과 무관하게) 실제 전체
    개수를 알려줘야 화면이 "더 보기"를 보여줄지 판단할 수 있다."""
    ids = [_new_conversation(client, user_csrf)["id"] for _ in range(3)]

    capped = client.get("/api/conversations", params={"limit": 2}).json()
    assert len(capped["items"]) == 2
    assert capped["total"] == 3

    full = client.get("/api/conversations", params={"limit": 100}).json()
    assert {c["id"] for c in full["items"]} == set(ids)
    assert full["total"] == 3

    # 서버가 정한 상한(MAX_CONVERSATION_LIST_LIMIT)을 넘는 요청은 그대로 받지 않는다 —
    # 클라이언트가 임의로 큰 값을 넣어 한 번에 전체 테이블을 긁어가지 못하게 막는다.
    too_big = client.get("/api/conversations", params={"limit": 5000})
    assert too_big.status_code == 422


def test_rename_and_delete_conversation(client, user_csrf):
    conv = _new_conversation(client, user_csrf)
    # rename
    r = client.patch(f"/api/conversations/{conv['id']}", json={"title": "포스코 프로젝트 문의"},
                     headers=_headers(user_csrf))
    assert r.status_code == 200 and r.json()["conversation"]["title"] == "포스코 프로젝트 문의"
    # archive hides it from the default list
    client.patch(f"/api/conversations/{conv['id']}", json={"archived": True}, headers=_headers(user_csrf))
    assert all(c["id"] != conv["id"] for c in client.get("/api/conversations").json()["items"])
    # delete removes it entirely
    r = client.delete(f"/api/conversations/{conv['id']}", headers=_headers(user_csrf))
    assert r.status_code == 200
    assert client.get(f"/api/conversations/{conv['id']}/messages").status_code == 404


def test_conversation_delete_rename_idor_blocked(client, login_as, make_user):
    owner_csrf = login_as("user", email="owner@goodmit.co.kr")
    conv = _new_conversation(client, owner_csrf)
    # A different user must not rename or delete someone else's conversation.
    make_user("intruder@goodmit.co.kr")
    other_csrf = login_as("user", email="intruder@goodmit.co.kr")
    assert client.patch(f"/api/conversations/{conv['id']}", json={"title": "x"},
                        headers=_headers(other_csrf)).status_code == 403
    assert client.delete(f"/api/conversations/{conv['id']}",
                         headers=_headers(other_csrf)).status_code == 403


def test_post_message_returns_202_and_enqueues_job(client, user_csrf, db):
    conv = _new_conversation(client, user_csrf)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "내 할당 티켓 보여줘", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    assert r.status_code == 202
    body = r.json()
    assert body["message"]["processing_status"] == "pending"
    assert body["job_id"]

    from app.jobs.models import Job

    job = db.get(Job, body["job_id"])
    payload = json.loads(job.payload_json)
    assert payload["requester"]["email"] == "user@goodmit.co.kr"
    assert payload["content"] == "내 할당 티켓 보여줘"
    assert job.idempotency_key == f"chatmsg:{CLIENT_MSG_ID}"


def test_duplicate_client_message_id_not_duplicated(client, user_csrf, db):
    conv = _new_conversation(client, user_csrf)
    for _ in range(2):
        r = client.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": "중복 전송 테스트", "client_message_id": CLIENT_MSG_ID},
            headers=_headers(user_csrf),
        )
        assert r.status_code == 202

    messages = client.get(f"/api/conversations/{conv['id']}/messages").json()["items"]
    assert len(messages) == 1

    from app.jobs.models import Job

    assert db.query(Job).count() == 1


def test_client_message_id_reuse_across_conversations_is_not_a_conflict(
    client, user_csrf, login_as, make_user
):
    """UB-23: message_id는 예전엔 전역 UNIQUE였다(migration 0054 전) — 다른 사용자의
    대화에 이미 그 client_message_id가 쓰였으면 409("이미 다른 대화에서 사용된 메시지
    ID입니다")가 났다. 이건 소유자 필터 없는 존재-확인 오라클이었다: 아무 사용자나 임의의
    id로 찔러 보면 201/409로 그 문자열이 시스템 어딘가(다른 사용자의 대화 포함)에 이미
    있는지 알 수 있었다. 유일성이 이제 (conversation_id, message_id) 복합키라 다른
    사용자·다른 대화에서의 재사용은 그냥 새 메시지다."""
    other = make_user("other-msgid@goodmit.co.kr")
    other_csrf = login_as("user", email="other-msgid@goodmit.co.kr")
    other_conv = _new_conversation(client, other_csrf)
    r = client.post(
        f"/api/conversations/{other_conv['id']}/messages",
        json={"content": "다른 사람 메시지", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(other_csrf),
    )
    assert r.status_code == 202

    my_csrf = login_as("user", email="user@goodmit.co.kr")
    my_conv = _new_conversation(client, my_csrf)
    r2 = client.post(
        f"/api/conversations/{my_conv['id']}/messages",
        json={"content": "내 메시지, 같은 id", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(my_csrf),
    )
    assert r2.status_code == 202, r2.text
    assert r2.json()["message"]["content"] == "내 메시지, 같은 id"


def test_first_message_sets_conversation_title(client, user_csrf):
    conv = _new_conversation(client, user_csrf)
    client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "이번 주 마감 티켓 알려줘", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    data = client.get(f"/api/conversations/{conv['id']}/messages").json()
    assert data["conversation"]["title"] == "이번 주 마감 티켓 알려줘"


def test_long_first_message_title_is_truncated_with_an_ellipsis(client, user_csrf):
    """AI-55: 예전엔 60자에서 잘리기만 하고 표시가 없어, 같은 문장으로 시작하는 대화
    여러 개가 목록에서 글자 하나 안 틀리고 똑같아 보였다."""
    long_msg = "이 메시지는 예순 글자를 넘겨서 자동 제목이 잘리는지 확인하기 위한 아주 긴 문장입니다 " * 2
    conv = _new_conversation(client, user_csrf)
    client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": long_msg, "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    data = client.get(f"/api/conversations/{conv['id']}/messages").json()
    title = data["conversation"]["title"]
    assert title.endswith("…")
    assert len(title) <= 60
    assert title[:-1] == long_msg[:59].rstrip()
    assert title[:-1] == long_msg[: len(title) - 1]


def test_message_too_long_rejected_with_input_preserved_semantics(client, user_csrf, settings):
    conv = _new_conversation(client, user_csrf)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={
            "content": "가" * (settings.max_message_length + 1),
            "client_message_id": CLIENT_MSG_ID,
        },
        headers=_headers(user_csrf),
    )
    assert r.status_code == 422
    # Nothing persisted → the browser restores the draft.
    assert client.get(f"/api/conversations/{conv['id']}/messages").json()["items"] == []


def test_empty_message_rejected(client, user_csrf):
    conv = _new_conversation(client, user_csrf)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "   ", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    assert r.status_code == 422


def test_bad_client_message_id_rejected(client, user_csrf):
    conv = _new_conversation(client, user_csrf)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "hello", "client_message_id": "short"},
        headers=_headers(user_csrf),
    )
    assert r.status_code == 422


def test_messages_after_cursor(client, user_csrf):
    conv = _new_conversation(client, user_csrf)
    client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "첫 메시지", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    first = client.get(f"/api/conversations/{conv['id']}/messages").json()["items"][0]
    r = client.get(
        f"/api/conversations/{conv['id']}/messages", params={"after": first["id"]}
    )
    assert r.json()["items"] == []


def test_messages_unknown_after_cursor_returns_empty(client, user_csrf):
    # Regression: an unknown 'after' id used to return the FULL list (client would
    # then duplicate every message). It must return empty instead.
    conv = _new_conversation(client, user_csrf)
    client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "첫 메시지", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    r = client.get(
        f"/api/conversations/{conv['id']}/messages", params={"after": "nonexistent-id"}
    )
    assert r.json()["items"] == []


def test_chat_send_rate_limited_per_user(client, user_csrf, fake_clock):
    # 사용자당 전송 폭주 차단(버스트 용량 20 초과 시 429). 잡 큐·다운스트림 보호.
    conv = _new_conversation(client, user_csrf)
    codes = [
        client.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": f"메시지 {i}", "client_message_id": f"mrate{i:027d}"},
            headers=_headers(user_csrf),
        ).status_code
        for i in range(22)
    ]
    assert 202 in codes  # 초반 버스트는 통과
    assert codes[-1] == 429  # 용량 초과분은 거부
    # 429는 rate_limited 코드로 응답한다.
    last = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "one more", "client_message_id": "mrateoverflow0000000000000000000"},
        headers=_headers(user_csrf),
    )
    assert last.status_code == 429 and last.json()["error"]["code"] == "rate_limited"


def test_chat_page_renders_shell(client, user_csrf):
    # 홈(채팅)은 React 셸이 서빙한다. UI(새 대화·입력창)는 React가 그리므로 HTML엔 없다 —
    # 셸(root 컨테이너 + 외부 번들)이 왔는지만 확인한다.
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="root"' in r.text
    assert "/static/react/assets/" in r.text


# --- image attachments (#34 Phase 2) ----------------------------------------
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_post_message_with_attachment(client, user_csrf, db):
    conv = _new_conversation(client, user_csrf)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={
            "content": "이 스크린샷 보고 티켓 만들어줘",
            "client_message_id": "matt0123456789abcdef0123456789ab",
            "attachments": [
                {"filename": "error.png", "media_type": "image/png", "data": PNG_B64}
            ],
        },
        headers=_headers(user_csrf),
    )
    assert r.status_code == 202
    msg = r.json()["message"]
    # Stored message exposes names only — never the bytes.
    assert msg["structured"]["attachments"] == [
        {"filename": "error.png", "media_type": "image/png"}
    ]
    # The transient job payload DOES carry the data (needed by n8n/runner).
    from app.jobs.models import Job

    job = db.get(Job, r.json()["job_id"])
    payload = json.loads(job.payload_json)
    assert payload["attachments"][0]["data"] == PNG_B64


def test_post_image_only_message_gets_marker_content(client, user_csrf):
    conv = _new_conversation(client, user_csrf)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={
            "content": "",
            "client_message_id": "mimg0123456789abcdef0123456789ab",
            "attachments": [
                {"filename": "shot.png", "media_type": "image/png", "data": PNG_B64}
            ],
        },
        headers=_headers(user_csrf),
    )
    assert r.status_code == 202
    assert r.json()["message"]["content"] == "(이미지 첨부)"


def test_post_message_rejects_fake_image(client, user_csrf):
    import base64 as _b64

    conv = _new_conversation(client, user_csrf)
    html = _b64.b64encode(b"<html>not an image</html>").decode()
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={
            "content": "x",
            "client_message_id": "mbad0123456789abcdef0123456789ab",
            "attachments": [
                {"filename": "x.png", "media_type": "image/png", "data": html}
            ],
        },
        headers=_headers(user_csrf),
    )
    assert r.status_code in (400, 422)


def test_empty_message_without_attachment_still_rejected(client, user_csrf):
    conv = _new_conversation(client, user_csrf)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "  ", "client_message_id": "memp0123456789abcdef0123456789ab"},
        headers=_headers(user_csrf),
    )
    assert r.status_code in (400, 422)


# --- retry endpoint error handling (app/chat/router.py:retry) -----------------
def test_retry_rate_limited_returns_429(client, user_csrf):
    # The retry endpoint shares the per-user chat_ratelimiter (capacity 20) so a
    # user can't bypass the send-rate limit by hammering '다시 시도'. With the
    # clock frozen (no token refill), the bucket drains and later calls get 429.
    codes = [
        client.post(
            "/api/messages/no-such-message/retry", headers=_headers(user_csrf)
        ).status_code
        for _ in range(25)
    ]
    assert 429 in codes  # the burst capacity is exceeded within 25 calls
    last = client.post(
        "/api/messages/no-such-message/retry", headers=_headers(user_csrf)
    )
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "rate_limited"


def test_retry_non_failed_message_returns_409(client, user_csrf):
    # A freshly posted message is 'pending', not 'failed' — only failed user
    # messages can be retried (app/chat/service.py:retry_message).
    conv = _new_conversation(client, user_csrf)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "진행 중 메시지", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    assert r.status_code == 202
    msg_id = r.json()["message"]["id"]
    retry = client.post(f"/api/messages/{msg_id}/retry", headers=_headers(user_csrf))
    assert retry.status_code == 409


def test_retry_unknown_message_returns_404(client, user_csrf):
    r = client.post(
        "/api/messages/does-not-exist/retry", headers=_headers(user_csrf)
    )
    assert r.status_code == 404


def test_feature_flag_off_hides_chat_api_but_not_the_app_shell(db_path, tmp_path, fake_clock, fake_http):
    """AI-45: chat_enabled=False로 채팅 API는 막히지만, "/"(React 앱 전체의 진입점)는
    채팅 전용 경로가 아니므로 계속 살아 있어야 한다 — 껐다고 앱 전체가 깨지면 안 된다."""
    import shutil

    from app.core.config import Settings
    from app.main import create_app
    from app.users.service import create_user

    cfg = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg)
    (cfg / "feature-flags.json").write_text(
        json.dumps({"chat_enabled": False}), encoding="utf-8"
    )
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_secret="test-session-secret",
        cookie_secure=False,
        config_dir=cfg,
        secrets_dir=secrets_dir,
        data_dir=tmp_path,
    )
    app = create_app(settings, clock=fake_clock, outbound_transport=fake_http.transport())
    with app.state.session_factory() as s:
        create_user(
            s,
            email="ff-chat@goodmit.co.kr",
            display_name="FF",
            password=DEFAULT_TEST_PASSWORD,
            settings=settings,
            actor_role="system_admin",
            role="user",
            active=True,
            must_change_password=False,
        )
        s.commit()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "ff-chat@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        assert c.get("/api/conversations").status_code == 404
        assert c.get("/api/me/ai-quota").status_code == 404
        assert c.get("/").status_code == 200, "채팅을 껐다고 앱 셸(/) 전체가 깨지면 안 된다"
