"""AI 정책의 규칙, 적용 대상, 가리기 (계획 3.9, D-519).

못박는 성질:
1. 종류마다 규칙 칸이 정해져 있다. 모르는 칸은 거절하고 빠진 칸은 기본값으로 채운다. 출력 글자 수는 코드 상한 안이다.
2. 적용 대상은 액션 키 목록이거나 `*` 다. 쓰기 승인은 결과가 저장되는 액션에만 붙고, 연결 확인에는 어떤 정책도 안 붙는다.
3. 가리기: 휴대전화, 유선, 대표 번호, 주민등록번호, 이메일을 고정 토큰으로 바꾼다. 날짜나 금액 같은 숫자는 건드리지 않는다.
4. 제품 밖 링크는 앞머리를 떼어 누를 수 없게 하고, 제품 호스트로 가는 링크는 그대로 둔다.
5. 응답 제한의 글자 수는 액션의 코드 상한보다 커지지 않는다.
"""

from __future__ import annotations

import pytest

from app.ai.policy import masking
from app.ai.policy.engine import PolicySet, ResolvedPolicy
from app.ai.policy.schemas import normalize_applies_to, normalize_rules
from app.core.errors import ValidationAppError


def test_rules_fill_defaults_and_refuse_unknown_fields():
    assert normalize_rules("data_protection", {}) == {
        "mask_emails": False, "mask_phone_numbers": True, "mask_resident_registration_numbers": True,
    }
    with pytest.raises(ValidationAppError, match="없는 규칙"):
        normalize_rules("content", {"allowed_languages": ["ko"]})
    with pytest.raises(ValidationAppError):
        normalize_rules("content", {"max_output_chars": 5})
    with pytest.raises(ValidationAppError):
        normalize_rules("approval", {"auto_approve_roles": ["god"]})
    with pytest.raises(ValidationAppError):
        normalize_rules("legacy", {})


def test_targets_are_actions_or_everything():
    assert normalize_applies_to("content", "*") == ["*"]
    assert normalize_applies_to("content", ["workspace.ask", "*"]) == ["*"]
    assert normalize_applies_to("content", ["workspace.ask", "chat.answer"]) == ["chat.answer", "workspace.ask"]
    assert normalize_applies_to("approval", "workspace.draft") == ["workspace.draft"]
    for kind, bad in (("approval", "chat.answer"), ("content", "system.connection_test"), ("content", "nope")):
        with pytest.raises(ValidationAppError):
            normalize_applies_to(kind, bad)
    with pytest.raises(ValidationAppError):
        normalize_applies_to("content", [])


@pytest.mark.parametrize("text, expected", [
    ("연락처 010-1234-5678 로 주세요", "연락처 [전화번호] 로 주세요"),
    ("휴대폰 01012345678", "휴대폰 [전화번호]"),
    ("본사 02-123-4567, 지사 031 1234 5678", "본사 [전화번호], 지사 [전화번호]"),
    ("대표 1588-1234", "대표 [전화번호]"),
    ("주민번호 900101-1234567 입니다", "주민번호 [주민등록번호] 입니다"),
    ("메일 kim.minsu@goodmit.co.kr 로", "메일 [이메일] 로"),
])
def test_personal_data_is_masked(text, expected):
    masked, count = masking.mask(text, emails=True, phones=True, rrns=True)
    assert masked == expected and count >= 1


@pytest.mark.parametrize("text", [
    "2026-09-30 회의", "예산 1,500,000원", "티켓 PRJ-0123", "버전 1.2.3", "10:30 에 시작",
])
def test_ordinary_numbers_are_left_alone(text):
    assert masking.mask(text, emails=True, phones=True, rrns=True) == (text, 0)


def test_masking_follows_each_switch():
    text = "010-1234-5678 kim@goodmit.co.kr"
    assert masking.mask(text, emails=False, phones=True, rrns=True)[0] == "[전화번호] kim@goodmit.co.kr"
    assert masking.mask(text, emails=True, phones=False, rrns=False)[0] == "010-1234-5678 [이메일]"


def test_links_outside_the_product_lose_their_scheme():
    text = "안내는 https://evil.example.com/x?y=1 와 https://clovirassist.gooddi.lab/knowledge/1 에 있습니다."
    neutral, count = masking.neutralize_links(text, allowed_hosts={"clovirassist.gooddi.lab"})
    assert count == 1
    assert "evil.example.com/x?y=1" in neutral and "https://evil" not in neutral
    assert "https://clovirassist.gooddi.lab/knowledge/1" in neutral


def test_the_output_cap_never_exceeds_the_action_cap():
    tight = PolicySet(content=ResolvedPolicy(id="p", name="n", version=1, kind="content",
                                             rules={"max_output_chars": 300, "block_external_links": False}))
    loose = PolicySet(content=ResolvedPolicy(id="p", name="n", version=1, kind="content",
                                             rules={"max_output_chars": 9000, "block_external_links": False}))
    assert tight.output_cap(4000) == 300
    assert loose.output_cap(4000) == 4000
    assert PolicySet().output_cap(4000) == 4000
