"""팀 채팅 입력 상한은 **자르지 않고 거부한다** (Z3).

예전에는 `v[:2000]`(메시지) · `v[:200]`(방 이름) · `out[:50]`(멤버 목록)로 조용히 자르고
200 을 돌려줬다. 사용자가 겪는 일:

  * 2,400자를 붙여넣으면 2,000자만 저장되는데 **화면은 보냈다고 말한다.**
  * 60명을 초대하면 **50명만 초대되고 성공이라 말한다.**

바로 옆 `app/board/schemas.py` 는 같은 종류의 입력을 "본문은 20000자 이하여야 합니다." 로
거부한다. 계약이 두 벌일 이유가 없고, **사용자 글자를 말없이 먹는 쪽이 틀렸다.**

경계값(정확히 상한)은 통과해야 한다 — 상한을 한 칸 잘못 잡으면 "2000자까지"라고 안내하고
2000자를 거부하는 화면이 된다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.team_chat.schemas import (
    MAX_BODY,
    MAX_MEMBERS,
    MAX_TITLE,
    GroupCreate,
    MembersInput,
    MessageCreate,
    RenameInput,
)

pytestmark = pytest.mark.unit


def _msg(err: ValidationError) -> str:
    return err.errors()[0]["msg"]


def test_message_over_limit_is_rejected_not_truncated():
    with pytest.raises(ValidationError) as e:
        MessageCreate(body="가" * (MAX_BODY + 1))
    assert str(MAX_BODY) in _msg(e.value)


def test_message_at_limit_is_kept_whole():
    assert len(MessageCreate(body="가" * MAX_BODY).body) == MAX_BODY


def test_room_title_over_limit_is_rejected():
    with pytest.raises(ValidationError):
        GroupCreate(title="나" * (MAX_TITLE + 1))
    with pytest.raises(ValidationError):
        RenameInput(title="나" * (MAX_TITLE + 1))
    # 만들 때와 바꿀 때의 규칙이 같아야 한다 — 다르면 만들 수 없는 이름으로 바꿀 수 있다.
    assert len(RenameInput(title="나" * MAX_TITLE).title) == MAX_TITLE


def test_too_many_members_is_rejected_not_silently_dropped():
    """50명만 초대하고 '성공'이라 말하던 자리."""
    with pytest.raises(ValidationError) as e:
        MembersInput(user_ids=[f"u{i}" for i in range(MAX_MEMBERS + 1)])
    assert str(MAX_MEMBERS) in _msg(e.value)

    ok = MembersInput(user_ids=[f"u{i}" for i in range(MAX_MEMBERS)])
    assert len(ok.user_ids) == MAX_MEMBERS


def test_group_create_member_list_also_rejects():
    with pytest.raises(ValidationError):
        GroupCreate(title="방", member_user_ids=[f"u{i}" for i in range(MAX_MEMBERS + 1)])


def test_dedup_still_happens_before_the_limit():
    """중복 제거는 상한보다 먼저다 — 같은 사람을 두 번 골랐다고 거부하면 안 된다."""
    ids = [f"u{i}" for i in range(MAX_MEMBERS)] + [f"u{i}" for i in range(MAX_MEMBERS)]
    assert len(MembersInput(user_ids=ids).user_ids) == MAX_MEMBERS


def test_empty_input_still_rejected():
    with pytest.raises(ValidationError):
        MessageCreate(body="   ")
    with pytest.raises(ValidationError):
        GroupCreate(title="  ")
    with pytest.raises(ValidationError):
        MembersInput(user_ids=[])
