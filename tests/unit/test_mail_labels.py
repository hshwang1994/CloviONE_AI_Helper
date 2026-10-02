"""메일 상태 낱말 — 확인한 단계까지만 말한다 (계획 M2, D-555).

못박는 것:
  * 저장 상태와 보내는 방식 · 바깥 전달 결과가 낱말 하나로 간다(외부 SMTP 접수 · 로컬 릴레이 접수 · 수신측 전달 · 상위 SMTP 접수 ·
    재시도 · 거부 · 만료).
  * 어떤 낱말도 「도착」 · 「받았습니다」라고 말하지 않는다 - 받은 편지함 확인은 사람의 증거다.
  * 대기 중인 메일의 잡이 돌고 있으면 「보내는 중」이다(새 저장 상태를 만들지 않는다).
"""

from __future__ import annotations

import pytest

from app.mail import labels

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("status, kwargs, word", [
    ("queued", {}, "보낼 차례"),
    ("queued", {"sending": True}, "보내는 중"),
    ("retrying", {}, "다시 보낼 차례"),
    ("unconfigured", {}, "설정이 끝나지 않아 보내지 못함"),
    ("sent", {"mode": "external"}, "메일 서버가 접수함"),
    ("sent", {"mode": "local_relay"}, "로컬 릴레이가 접수함"),
    ("sent", {"mode": "local_relay", "remote_status": "queued"}, "로컬 릴레이가 접수함"),
    ("sent", {"mode": "local_relay", "remote_status": "delivered", "relay_delivery": "direct"}, "수신측 메일 서버로 전달함"),
    ("sent", {"mode": "local_relay", "remote_status": "delivered", "relay_delivery": "smarthost"}, "상위 SMTP 서버가 접수함"),
    ("sent", {"mode": "local_relay", "remote_status": "deferred"}, "전달 재시도 중"),
    ("sent", {"mode": "local_relay", "remote_status": "bounced"}, "수신측이 거부함"),
    ("sent", {"mode": "local_relay", "remote_status": "expired"}, "전달 시간이 지남"),
    ("failed", {}, "보내지 못함"),
    ("cancelled", {}, "취소됨"),
    ("superseded", {}, "보내지 않음(의미가 없어짐)"),
])
def test_each_stage_has_its_word(status, kwargs, word):
    assert labels.delivery_word(status, **kwargs) == word


def test_no_word_claims_the_mail_arrived():
    words = list(labels.STATUS_WORDS.values()) + list(labels.REMOTE_WORDS.values()) + list(labels.REMOTE_GENERIC.values())
    words += [labels.SENDING_WORD, labels.ACCEPTED_EXTERNAL, labels.ACCEPTED_RELAY]
    words += list(labels.STATUS_FILTER_WORDS.values())
    words += [labels.test_result_sentence("external"), labels.test_result_sentence("local_relay")]
    for word in words:
        assert "도착" not in word and "받았습니다" not in word, word


def test_the_test_sentences_say_accepted():
    assert labels.test_result_sentence("external").startswith("메일 서버가 시험 메일을 접수했습니다.")
    assert labels.test_result_sentence("local_relay").startswith("로컬 릴레이가 시험 메일을 접수했습니다.")
