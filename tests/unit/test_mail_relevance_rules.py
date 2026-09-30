"""알림 메일의 판정 표가 빠진 칸 없이 서 있는가 (계획 3.4, D-514).

새 유형을 메일로 보낼 수 있게 더하면서 그 유형의 「보내기 직전 판정」을 빠뜨리면, 장애 뒤에 의미를 잃은 메일이
그대로 나간다. 까닭을 적어 놓고 그 문장을 빠뜨리면 발송 기록 화면에 「보내지 않았습니다」만 남는다.
"""

from __future__ import annotations

import pytest

from app.mail import relevance
from app.notifications import mail as notification_mail
from app.profiles.prefs import DEFAULT_MAIL_NOTIFICATION_TYPES, MAILABLE_TYPES, NOTIFICATION_TYPES

pytestmark = pytest.mark.unit


def test_every_mailable_type_has_a_relevance_rule():
    assert set(relevance.NOTIFICATION_RULES) == set(MAILABLE_TYPES)


def test_every_mailable_type_is_a_known_notification_type():
    """화면 목록과 이름이 이 표(`NOTIFICATION_TYPES`)에서 나온다 - 없으면 설정 화면에 영문 키가 보인다."""
    assert set(MAILABLE_TYPES) <= set(NOTIFICATION_TYPES)
    assert set(DEFAULT_MAIL_NOTIFICATION_TYPES) <= set(MAILABLE_TYPES)


def _reason_values(module, prefix: str = "REASON_") -> set[str]:
    return {v for k, v in vars(module).items() if k.startswith(prefix) and isinstance(v, str)}


def test_every_reason_has_a_sentence():
    reasons = _reason_values(relevance) | _reason_values(notification_mail)
    missing = sorted(reasons - set(relevance.REASON_LABELS))
    assert missing == [], f"문장이 없는 까닭: {missing}"


@pytest.mark.parametrize("sentence", sorted(set(relevance.REASON_LABELS.values())))
def test_reason_sentences_are_complete_sentences(sentence):
    assert sentence.endswith("다.") and "·" not in sentence and "—" not in sentence, sentence


def test_the_default_allow_list_matches_the_setting_default():
    from app.settings.registry import REGISTRY

    assert REGISTRY["mail_notification_types"].default == list(DEFAULT_MAIL_NOTIFICATION_TYPES)
