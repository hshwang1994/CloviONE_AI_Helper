"""저장할 수 없는 문자는 요청 경계에서 막는다 (XB-04).

PostgreSQL 의 `text` 는 NUL(`U+0000`)을 담지 못한다. 그 사실을 아무 층도 말해 주지 않으면
요청은 스키마·라우터·서비스를 전부 지나 psycopg 가 `DataError` 를 던지는 자리에서 처음
막히고, 관리자가 받는 것은 「Internal server error」 500 이다 — 무엇이 틀렸는지 모르니
같은 요청을 다시 보낸다. 사람이 손으로 NUL 을 넣지는 않지만 붙여넣기·CSV 가져오기·외부
연동 페이로드로는 실제로 들어온다.

이 파일은 **공용 규칙 자체**(`app/core/text.py::NulFreeModel`)와, 그 규칙을 쓰는 요청
모델이 실제로 422 를 내는지를 함께 센다. 반례도 같은 자리에 둔다 — 한글·이모지·공백은
정상 문자라 그대로 저장돼야 한다. 반례가 없으면 「전부 거절」 구현으로도 초록이 된다.

## 아직 이 규칙을 안 쓰는 요청 모델이 있다

`NulFreeModel` 은 요청 모델이 상속해야 걸린다. 지금 이 저장소에서 상속한 것은 저장소
설정(`app/storage/schemas.py`)과 공지(`app/announcements/router.py`) 둘이다. 부서·직책·
사용자·일정·프롬프트 같은 다른 관리자 쓰기 API 는 아직 예전 그대로라 같은 입력에 500 을
낸다 — 그 채택은 그 파일을 가진 작업의 몫이고, 여기서는 **채택한 곳이 실제로 막는가**만
센다(안 본 것을 봤다고 적지 않는다).

qa-contract-change: 거절 문구가 API 필드 이름(`title`) 대신 화면 이름(「제목」)을 말하도록 계약을 바꿨다 (R6-03)
"""

from __future__ import annotations

import pytest

from app.core.text import NulFreeModel, clean_required_text, has_nul, nul_message
from app.core.errors import ValidationAppError

pytestmark = pytest.mark.security


# ── 공용 규칙 ────────────────────────────────────────────────────────────────


class _Sample(NulFreeModel):
    name: str
    memo: str | None = None
    tags: list[str] = []


def test_the_shared_rule_refuses_a_nul_anywhere_in_the_payload():
    for payload in (
        {"name": "a\x00b"},
        {"name": "정상", "memo": "붙여넣은\x00값"},
        {"name": "정상", "tags": ["ok", "bad\x00"]},
    ):
        with pytest.raises(ValueError):
            _Sample(**payload)


def test_the_shared_rule_lets_normal_unicode_through():
    """반례 — 한글·이모지·공백은 PostgreSQL 이 담는 문자다."""
    row = _Sample(name="정기 점검 🛠", memo="자정부터 두 시간입니다.", tags=["공지", "점검"])
    assert row.name == "정기 점검 🛠"
    assert row.tags == ["공지", "점검"]


def test_the_message_says_which_field_and_what_to_do():
    """CSV·연동처럼 칸이 여럿인 요청에서는 어느 칸이 문제인지 알아야 고칠 수 있다.

    말하는 이름은 **화면의 이름**이다. 이 문장은 토스트로 그대로 나가는데(모듈 docstring),
    그것을 읽는 사람은 `title` 이라는 API 필드 이름을 어디서도 본 적이 없다.
    """
    message = nul_message("title")
    assert message.startswith("제목 칸에"), message
    assert "title" not in message, f"내부 필드 이름이 사용자 문장에 실렸다: {message!r}"
    assert message.endswith("다시 보내 주세요.")


def test_a_field_nobody_named_says_less_rather_than_leaking_the_key():
    """모르는 칸은 **이름 없이** 답한다 — 모르는 키를 그대로 싣느니 한 칸 덜 말한다."""
    message = nul_message("some_internal_key")
    assert message.startswith("입력값에"), message
    assert "some_internal_key" not in message, message


def test_a_model_can_name_its_own_fields():
    """같은 키를 화면마다 다르게 부르는 경우가 있다 — 모델이 공용 표를 덮을 수 있다."""

    class _Named(NulFreeModel):
        nul_field_labels = {"options": "연동 옵션"}
        options: str

    with pytest.raises(ValueError) as caught:
        _Named(options="rw\x00")
    assert "연동 옵션 칸에" in str(caught.value), str(caught.value)


def test_the_storage_provider_message_names_the_field_the_screen_names():
    """저장소 설정 폼의 「경로」 칸은 서버 문장에서도 「경로」다(StorageProviders.jsx)."""
    message = nul_message("base_path")
    assert message.startswith("경로 칸에"), message
    assert "base_path" not in message, message


def test_has_nul_looks_inside_lists_and_dicts():
    assert has_nul({"a": ["x", {"b": "y\x00"}]}) is True
    assert has_nul({"a": ["x", {"b": "y"}]}) is False
    assert has_nul(7) is False


def test_a_required_text_of_only_spaces_is_a_validation_error():
    """`Field(min_length=1)` 은 strip 전 길이를 본다 — 정규화와 검증이 같은 자리에 있어야
    검증한 문자열과 저장되는 문자열이 갈라지지 않는다."""
    with pytest.raises(ValidationAppError):
        clean_required_text("   ", subject="제목")
    assert clean_required_text("  제목  ", subject="제목") == "제목"


def test_the_required_text_message_picks_the_particle_instead_of_writing_both():
    """「을(를)」 같은 괄호 표기는 완전한 한 문장이 아니다(CLAUDE.md §10) — 받침을 보고 고른다."""
    with pytest.raises(ValidationAppError) as with_batchim:
        clean_required_text("", subject="저장소 이름")
    assert str(with_batchim.value) == "저장소 이름을 입력해야 합니다."

    with pytest.raises(ValidationAppError) as without_batchim:
        clean_required_text("", subject="메모")
    assert str(without_batchim.value) == "메모를 입력해야 합니다."

    for message in (str(with_batchim.value), str(without_batchim.value)):
        assert "(" not in message, f"괄호 조사가 남아 있다: {message!r}"


# ── 규칙을 쓰는 쓰기 API ─────────────────────────────────────────────────────


def test_a_nul_in_a_storage_provider_name_is_422(client, login_as, db, settings):
    from app.storage import service

    service.ensure_default_provider(db, settings)
    db.commit()

    csrf = login_as("system_admin")
    response = client.post(
        "/api/storage/providers",
        json={
            "name": "a\x00b", "kind": "LOCAL", "role": "BACKUP",
            "base_path": "/srv/clovir/nul", "enabled": False,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text


def test_a_nul_in_a_storage_option_is_422(client, login_as, db, settings):
    """이름만 막으면 나머지 칸이 그대로 남는다 — 모델 진입에서 한 번에 본다."""
    from app.storage import service

    provider = service.ensure_default_provider(db, settings)
    db.commit()

    csrf = login_as("system_admin")
    response = client.patch(
        f"/api/storage/providers/{provider.id}",
        json={"options": "rw\x00"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text


def test_a_nul_in_an_announcement_title_is_422(client, login_as):
    csrf = login_as("system_admin")
    response = client.post(
        "/api/admin/announcements",
        json={"title": "점검\x00안내", "body": "본문"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text


def test_the_same_endpoints_still_accept_normal_text(client, login_as, db, settings):
    """반례 — 위 셋이 422 인 이유가 «이 API 가 막혔다» 가 아님을 같은 자리에서 보인다."""
    from app.storage import service

    service.ensure_default_provider(db, settings)
    db.commit()

    csrf = login_as("system_admin")
    created = client.post(
        "/api/storage/providers",
        json={
            "name": "백업 저장소 🗄", "kind": "LOCAL", "role": "BACKUP",
            "base_path": "/srv/clovir/ok", "enabled": False,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "백업 저장소 🗄"

    announced = client.post(
        "/api/admin/announcements",
        json={"title": "점검 안내 🛠", "body": "본문"},
        headers={"X-CSRF-Token": csrf},
    )
    assert announced.status_code == 201, announced.text
