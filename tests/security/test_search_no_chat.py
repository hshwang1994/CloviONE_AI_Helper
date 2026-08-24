"""**채팅은 통합 검색에 절대 들어가지 않는다** (0030, PLAN Phase 5 v1 범위).

이건 성능이나 범위 조정 문제가 아니라 유출 경계다:
  * 채팅 접근 권한은 **방 멤버십**으로 정해진다. 인덱스 안에 그 ACL 을 복제하는 순간,
    멤버가 바뀌었는데 인덱스가 안 따라온 그 몇 분이 그대로 열람 창이 된다.
  * 1:1 DM 은 두 사람만 볼 수 있다. 그것을 공용 인덱스에 넣는 것은, 그 인덱스를 잘못 읽는
    코드 한 줄이 곧바로 사적 대화 유출이 된다는 뜻이다.

검색은 '조금 덜 찾아 주는' 실패는 견딘다. '남의 DM 을 보여 주는' 실패는 못 견딘다.
그래서 이 파일은 **데이터 층(인덱싱해도 안 들어간다)과 코드 층(부를 방법이 없다)** 을
둘 다 못박는다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.search.indexer import reindex_all
from app.search.models import SEARCH_KINDS, SearchDocument
from app.team_chat.models import ChatMessage, ChatRoom, ChatRoomMember

pytestmark = pytest.mark.security

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 3, 9, 0, 0)

# 채팅에만 있고 다른 어디에도 없는 문자열. 검색 결과에 이게 나오면 채팅이 샌 것이다.
SECRET = "비밀디엠문구입니다"
PASSWORD = "Str0ng-Passw0rd!"


@pytest.fixture()
def chat_with_secret(db, make_user):
    """1:1 DM 방 하나 + 그 안의 비밀 메시지."""
    alice = make_user(email="chat-a@goodmit.co.kr", display_name="채팅앨리스")
    bob = make_user(email="chat-b@goodmit.co.kr", display_name="채팅밥")
    db.commit()

    room = ChatRoom(id="room-secret-01", kind="dm", title="비밀 대화",
                    created_by_user_id=alice.id, dm_key=f"{alice.id}:{bob.id}",
                    event_seq=1, created_at=NOW, updated_at=NOW)
    db.add(room)
    db.flush()
    for user in (alice, bob):
        db.add(ChatRoomMember(room_id=room.id, user_id=user.id, joined_at=NOW))
    db.add(ChatMessage(room_id=room.id, seq=1, sender_user_id=alice.id, kind="text",
                       body=SECRET, created_at=NOW))
    db.commit()
    return {"alice": alice.email, "bob": bob.email, "room": room.id}


# ── 데이터 층 ────────────────────────────────────────────────────────────────


def test_chat_is_not_an_indexable_kind():
    assert "chat" not in SEARCH_KINDS
    assert set(SEARCH_KINDS) == {"ticket", "document", "board", "user"}


def test_reindex_never_writes_a_chat_row(db, app, chat_with_secret):
    # 티켓 소스(Notion)는 이 테스트에서 미설정이라 그 유형만 error 로 기록된다 —
    # 그래도 나머지 유형은 인덱싱되고 예외는 밖으로 나오지 않는다(장애 격리).
    reindex_all(
        db, tickets=app.state.repositories.tickets, now=NOW,
    )
    db.commit()

    rows = db.execute(select(SearchDocument)).scalars().all()
    assert all(row.kind != "chat" for row in rows)
    leaked = [row for row in rows if SECRET in (row.title or "") + (row.body or "")]
    assert not leaked, f"채팅 본문이 검색 인덱스에 들어갔다: {[r.ref_id for r in leaked]}"


def test_a_dm_participant_cannot_find_their_own_dm_through_search(
    client, db, app, chat_with_secret
):
    """**대화 당사자조차** 검색으로는 못 찾는다.

    '본인 것이니 괜찮다'로 예외를 하나 열면 그 예외가 인덱스 안 ACL 의 시작이 된다.
    v1 은 채팅을 아예 인덱싱하지 않는다 — 예외 없음이 가장 확인하기 쉬운 규칙이다.
    """
    reindex_all(
        db, tickets=app.state.repositories.tickets, now=NOW,
    )
    db.commit()

    response = client.post(
        "/login", json={"email": chat_with_secret["alice"], "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = client.get("/api/search", params={"q": SECRET}).json()
    assert body["total"] == 0, f"채팅 메시지가 검색 결과에 나왔다: {body}"


# ── 코드 층 ──────────────────────────────────────────────────────────────────


def test_the_indexer_does_not_import_chat_modules():
    """인덱서가 채팅 모듈을 import 하면 실패한다.

    import 를 보는 이유는 usage_events 검사와 같다 — 호출을 문법으로 쫓으면 별칭·간접
    호출로 새어 나가지만, import 가 없으면 부를 방법 자체가 없다(지연 import 도 같은
    문자열이라 함께 걸린다).
    """
    source = (PROJECT_ROOT / "app/search/indexer.py").read_text(encoding="utf-8")
    for banned in ("team_chat", "ChatMessage", "chat_messages"):
        assert banned not in source, (
            f"app/search/indexer.py 가 '{banned}' 를 참조한다. 채팅은 v1 검색 범위 밖이고, "
            "방별 ACL 을 인덱스 안에 넣는 순간 DM 이 공용 인덱스에 실린다."
        )


def test_the_guard_above_is_not_vacuous():
    """검사 문자열이 판별력을 가진다는 증명 — 실제로 채팅을 다루는 파일에서는 보인다."""
    wired = (PROJECT_ROOT / "app/team_chat/service.py").read_text(encoding="utf-8")
    assert "ChatMessage" in wired
