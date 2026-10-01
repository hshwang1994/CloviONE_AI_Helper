"""ChatGPT 계정 로그인 흐름 — 화면이 그리는 모양(`flow`)과 서버가 하는 일을 나눈다 (D-540).

## 흐름은 두 모양이다

- ``paste``(지금 쓰는 것): 관리자가 「Continue with ChatGPT」를 누르면 같은 클릭 안에서 새 창이 열려 ChatGPT 승인으로 간다.
  승인이 끝나면 브라우저가 ``http://127.0.0.1:<포트>/auth/callback?...`` 에서 멈춘다(그 주소에는 아무것도 듣고 있지 않다).
  관리자가 그 주소를 붙여 넣으면 서버가 제 PKCE verifier 와 호스트 id 로 인가 코드를 토큰으로 바꾼다. 코드만으로는
  쓸모가 없으므로 주소를 붙여 넣는 일이 토큰을 넘기는 일이 아니다. 설치할 것도, 실행할 명령도 없다.
- ``redirect``(공식 지원이 생기면): 같은 창에서 승인으로 가고 서버의 https 콜백이 ``/ai-connection?connected=1`` 로
  돌려보낸다. **공식 지원 전에는 열지 않는다** — 비공식 우회를 하지 않는다. 지원이 생기면 서버에 콜백 경로 하나를 더하고
  ``CHATGPT_LOGIN_FLOW`` 를 바꾼다. 화면(`ChatGptLogin.jsx`)은 응답의 ``flow`` 로 갈래를 고르므로 다시 만들지 않는다.

## 왜 순수 웹 왕복이 지금은 안 되는가 (2026-10-01 공식 문서 조사)

「Sign in with ChatGPT」의 요금제 사용은 오픈 소스 · 로컬 호스팅 앱 문서가 다루고, 콜백은 ``http://127.0.0.1:<포트>/<고정
경로>`` 만 된다(``localhost`` 금지, 포트만 바뀔 수 있고 같은 시도 안에서 인가와 교환이 같은 주소). ``https://`` 콜백은 선택된
상업 파트너의 제한된 시험이고 그 안내는 신원 로그인 전용이다. 자체 호스팅 VM 안내는 「127.0.0.1 콜백은 브라우저를 실행한
컴퓨터에 닿지 원격 VM 에 닿지 않는다」고 적는다. 그래서 원격 ClovirAssist 서버가 콜백을 직접 받는 흐름은 지금 공식적으로
불가능하고, 설치 없이 되는 가장 단순한 공식 흐름이 붙여 넣기다.

예전에는 관리자 PC 에서 돌리는 연결 도우미(PowerShell · Python)가 콜백을 받아 넘겼다. 그 도우미와 쿠키 없는
``/api/connect/*`` 문은 걷었고 다시 들이지 않는다(D-540, `tests/regression/test_no_connect_helper.py`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.ai.credentials import oauth

FLOW_PASTE = "paste"
FLOW_REDIRECT = "redirect"
#: 지금 쓰는 흐름. 공식 지원 없이 `redirect` 로 바꾸지 않는다(머리말).
CHATGPT_LOGIN_FLOW = FLOW_PASTE
OPEN_FLOWS = frozenset({FLOW_PASTE})


class LoginFlow(Protocol):
    """로그인 흐름 하나가 지켜야 하는 것. 화면은 `start` 응답의 `flow` 로만 그린다."""

    key: str

    def start(self, db: Session, *, admin_user_id: str, session_id: str | None, session_secret: str,
              now: datetime) -> dict: ...

    def complete(self, db: Session, *, transaction_id: str, admin_user_id: str, session_id: str | None,
                 callback_url, context: "oauth.CompleteContext") -> dict: ...


class PasteLoopbackFlow:
    """새 창에서 승인 → 멈춘 127.0.0.1 주소를 붙여 넣기. 시도마다 포트를 새로 고른다(`oauth.start`)."""

    key = FLOW_PASTE

    def start(self, db: Session, *, admin_user_id: str, session_id: str | None, session_secret: str,
              now: datetime) -> dict:
        row, authorize_url = oauth.start(db, admin_user_id=admin_user_id, session_id=session_id,
                                         session_secret=session_secret, now=now)
        return {
            **oauth.view(row),
            "flow": self.key,
            "authorize_url": authorize_url,
            "redirect_uri": oauth.redirect_for(row),
        }

    def complete(self, db: Session, *, transaction_id: str, admin_user_id: str, session_id: str | None,
                 callback_url, context: "oauth.CompleteContext") -> dict:
        return oauth.complete_manual(db, transaction_id=transaction_id, admin_user_id=admin_user_id,
                                     session_id=session_id, callback_url=callback_url, context=context)


def chatgpt_flow(key: str = CHATGPT_LOGIN_FLOW) -> LoginFlow:
    """지금 흐름. 열지 않은 흐름을 달라고 하면 예외다 — 설정 한 줄로 비공식 경로가 열리지 않게 한다."""
    if key == FLOW_PASTE:
        return PasteLoopbackFlow()
    raise ValueError(f"열지 않은 로그인 흐름입니다: {key}")


def complete_context(request, now: datetime) -> "oauth.CompleteContext":
    """끝내기에 필요한 바깥 것들을 요청에서 모은다(라우터 전용)."""
    from app.ai.runtime import runtime_for_app

    runtime = runtime_for_app(request.app)
    cache = getattr(request.app.state, "settings_cache", None)
    return oauth.CompleteContext(
        now=now, outbound=request.app.state.outbound_client, tokens=runtime.chatgpt_tokens(),
        session_secret=str(getattr(request.app.state.settings, "session_secret", "") or ""),
        settings_values=cache.current() if cache is not None else {},
    )
