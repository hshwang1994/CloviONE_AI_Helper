"""판이 본 판과 지금 티켓이 다르면 409 이고, 그 문장은 남 탓을 하지 않는다.

같은 사람의 다른 탭 · 늦게 온 둘째 요청(더블클릭)도 이 확인에 걸린다. 예전 문장 「다른 사람이 먼저 이 티켓을
옮겼습니다」는 그 사람에게 자기 클릭을 남의 경합으로 읽게 했다(배정 잠금 문장과 같은 결함, D-498).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.errors import ConflictError
from app.work.service import TICKET_MOVED_MEANWHILE, _ensure_version


def test_a_stale_base_version_is_a_conflict_that_does_not_blame_someone_else():
    with pytest.raises(ConflictError) as caught:
        _ensure_version(SimpleNamespace(version=4), 3)
    message = str(caught.value.message if hasattr(caught.value, "message") else caught.value)
    assert message == TICKET_MOVED_MEANWHILE
    assert "다른 사람" not in message


def test_the_same_or_missing_base_version_passes():
    _ensure_version(SimpleNamespace(version=4), 4)
    _ensure_version(SimpleNamespace(version=4), None)
