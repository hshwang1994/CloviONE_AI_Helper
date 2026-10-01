"""ChatGPT 로그인 흐름 계약 (D-540).

못박는 성질:
1. 지금 흐름은 `paste` 하나다. `redirect` 는 공식 지원 전이라 열리지 않는다 - 달라고 하면 예외다(설정 한 줄로 비공식 경로가
   열리지 않는다).
2. 흐름은 `start` · `complete` 두 동작을 갖고, `start` 응답이 화면이 고를 `flow` 를 싣는다.
3. 루프백 포트는 동적 · 사설 범위(49152 ~ 65535)에서 고른다.
"""

from __future__ import annotations

import pytest

from app.ai.credentials import login_flow, oauth


def test_the_current_flow_is_paste_and_redirect_is_not_open():
    assert login_flow.CHATGPT_LOGIN_FLOW == login_flow.FLOW_PASTE
    assert login_flow.OPEN_FLOWS == {login_flow.FLOW_PASTE}
    assert login_flow.chatgpt_flow().key == login_flow.FLOW_PASTE
    with pytest.raises(ValueError):
        login_flow.chatgpt_flow(login_flow.FLOW_REDIRECT)


def test_a_flow_has_start_and_complete():
    flow = login_flow.chatgpt_flow()
    assert callable(flow.start) and callable(flow.complete)


def test_the_start_reply_names_its_flow(monkeypatch):
    class Row:
        id = "tx-1"
        phase = oauth.PHASE_BROWSER
        error_code = None
        account_label = None
        redirect_port = 50123

        class expires_at:  # noqa: N801 - isoformat 만 쓰는 흉내
            @staticmethod
            def isoformat():
                return "2026-10-02T00:10:00"

    monkeypatch.setattr(oauth, "start", lambda db, **kw: (Row, "https://auth.openai.com/oauth/authorize?x=1"))
    reply = login_flow.PasteLoopbackFlow().start(None, admin_user_id="a", session_id="s", session_secret="x" * 32,
                                                 now=None)
    assert reply["flow"] == "paste"
    assert reply["authorize_url"].startswith("https://auth.openai.com/")
    assert reply["redirect_uri"] == "http://127.0.0.1:50123/auth/callback"
    assert reply["transaction_id"] == "tx-1"


def test_ports_stay_in_the_dynamic_range():
    assert (oauth.PORT_MIN, oauth.PORT_MAX) == (49152, 65535)
    for _ in range(200):
        assert oauth.PORT_MIN <= oauth.pick_port() <= oauth.PORT_MAX
