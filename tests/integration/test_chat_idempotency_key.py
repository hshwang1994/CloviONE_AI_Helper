"""러너로 나가는 idempotency_key 가 두 종류의 재시도를 옳게 갈라야 한다.

문제의 모양: n8n 으로 보내는 POST 에는 자체 멱등성 수단이 없다. n8n 이 티켓 생성 같은
**쓰기를 마쳤는데 HTTP 응답이 유실**되면 우리 워커는 실패로 보고 다시 POST 한다.
n8n 이 중복을 걸러내지 못하면 티켓이 두 장 생긴다.

그렇다고 message_id 로 키를 만들면 반대쪽이 깨진다. 사용자가 실패를 보고 '다시 시도'를
눌렀을 때도 값이 같아서, n8n 이 엄격히 중복 제거하면 **옛 답변을 그대로 돌려준다.**
사용자는 다시 시도했는데 아무것도 안 바뀐 화면을 본다. 두 경우가 같은 문자열을 쓰는 한
n8n 이 무엇을 하든 한쪽은 틀린다.

그래서 job 행의 키를 그대로 내보낸다. chat/service.py 가 이미 둘을 다르게 만든다:
  최초 전송      chatmsg:{message_id}
  사용자 재시도  chatmsg:{message_id}:retry:{시각}   (새 job 행을 만든다)
그리고 한 job 행 안에서는 값이 변하지 않으므로 워커 재시도는 같은 값을 낸다.

여기서 고정하는 것은 두 문장이다:
  1) 워커가 같은 job 을 다시 처리하면 **같은** 키가 나간다.
  2) 사용자가 다시 시도하면 **다른** 키가 나간다.
n8n 은 이 문자열 하나로 중복 제거만 하면 되고, 판단 로직이 필요 없다.
자세한 인계 내용은 docs/RUNNER_HANDOFF.md.
"""

import json

import pytest

pytestmark = pytest.mark.integration

N8N_URL = "http://127.0.0.1:5678/webhook/clovirone-work-assistant"
MSG_ID = "i0123456789abcdef0123456789abcdef"


# test_chat_handler.py 와 같은 셋업이다. 그쪽 fixture 를 import 하지 않고 여기 두는 이유:
# 파일 사이 fixture 를 끌어 쓰면 한쪽을 고칠 때 다른 쪽이 조용히 깨진다.
@pytest.fixture()
def chat_worker(app, settings, fake_clock):
    from app.jobs.handlers.chat_message import handle_chat_message
    from app.jobs.worker import Worker, WorkerContext

    ctx = WorkerContext(settings=settings, clock=fake_clock,
                        outbound_client=app.state.outbound_client)
    return Worker(app.state.session_factory, fake_clock,
                  {"chat_message": handle_chat_message}, ctx, poll_interval=0.01)


@pytest.fixture()
def posted_message(client, login_as, make_user, db):
    # 1인칭 문장이라 Notion 매핑이 확인된 사용자여야 러너까지 간다(아니면 안전 차단).
    from datetime import datetime

    from app.notion_mapping.service import manual_map

    user = make_user("idem@goodmit.co.kr")
    manual_map(db, user, notion_user_id="idem1234", notion_email="i@x",
               now=datetime(2026, 7, 14))
    db.commit()
    csrf = login_as("user", email="idem@goodmit.co.kr")
    conv = client.post("/api/conversations", json={},
                       headers={"X-CSRF-Token": csrf}).json()["conversation"]
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "내 할당 티켓 보여줘", "client_message_id": MSG_ID},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 202
    return {"conversation_id": conv["id"], "csrf": csrf}


def _sent_keys(fake_http) -> list[str]:
    """페이크가 받은 러너 요청 본문에서 idempotency_key 만 순서대로 뽑는다."""
    keys = []
    for req in fake_http.requests:
        if not str(req.url).startswith(N8N_URL):
            continue
        try:
            body = json.loads(req.content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if "idempotency_key" in body:
            keys.append(body["idempotency_key"])
    return keys


def test_worker_retry_sends_the_same_key(
    client, chat_worker, fake_http, fake_clock, posted_message
):
    """응답 유실 쪽: 같은 job 을 워커가 다시 집으면 키가 같아야 n8n 이 중복을 막을 수 있다."""
    fake_http.on(N8N_URL, status=500, json_body={"error": "boom"})
    chat_worker.run_once()
    fake_clock.advance(60)
    chat_worker.run_once()          # 같은 job 의 두 번째 시도

    keys = _sent_keys(fake_http)
    assert len(keys) >= 2, f"러너 호출이 2회 이상이어야 한다: {keys}"
    assert keys[0] == keys[1], (
        "워커 재시도인데 키가 달라졌다 — n8n 이 중복을 걸러낼 수 없어,\n"
        "쓰기는 성공했는데 응답만 유실된 경우 티켓이 두 장 생긴다:\n"
        f"  {keys[:2]}"
    )


def test_user_retry_sends_a_different_key(
    client, chat_worker, fake_http, fake_clock, posted_message
):
    """사용자 재시도 쪽: 키가 달라야 n8n 이 새 요청으로 보고 다시 답한다."""
    fake_http.on(N8N_URL, status=400, json_body={})
    chat_worker.run_once()
    failed = client.get(
        f"/api/conversations/{posted_message['conversation_id']}/messages"
    ).json()["items"][0]
    assert failed["processing_status"] == "failed"
    first_key = _sent_keys(fake_http)[0]

    fake_http.on(N8N_URL, json_body={"reply": "재시도 성공"})
    r = client.post(
        f"/api/messages/{failed['id']}/retry",
        headers={"X-CSRF-Token": posted_message["csrf"]},
    )
    assert r.status_code == 200
    fake_clock.advance(1)
    chat_worker.run_once()

    keys = _sent_keys(fake_http)
    assert len(keys) >= 2, f"재시도 후 러너 호출이 2회 이상이어야 한다: {keys}"
    assert keys[-1] != first_key, (
        "사용자가 일부러 다시 시도했는데 키가 같다 — n8n 이 중복으로 보고 옛 답변을\n"
        "돌려주면, 사용자는 다시 시도했는데 아무것도 안 바뀐 화면을 본다:\n"
        f"  최초={first_key}  재시도={keys[-1]}"
    )
    # 규약은 유지한다 — 같은 메시지의 재시도임을 n8n 로그에서 알아볼 수 있어야 한다.
    assert keys[-1].startswith(first_key), (
        f"재시도 키가 최초 키를 접두사로 갖지 않는다: {first_key} vs {keys[-1]}"
    )


def test_key_is_always_present(client, chat_worker, fake_http, posted_message):
    """키가 아예 빠지면 n8n 은 중복 제거를 시작조차 할 수 없다."""
    fake_http.on(N8N_URL, json_body={"reply": "네"})
    chat_worker.run_once()

    keys = _sent_keys(fake_http)
    assert keys, "러너 요청에 idempotency_key 가 없다"
    assert keys[0].startswith("chatmsg:"), keys[0]
