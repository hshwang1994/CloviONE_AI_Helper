"""설정 설명은 완전한 문장이다 (D-587, r23 #95).

설정 화면의 「시스템 정책」 표와 편집 창은 `app/settings/registry.py` 의 설명을 그대로 보여 준다. 예전에는 설명이
「대화 보존 기간(일). 이 기간이 …」처럼 라벨 조각으로 시작하거나(표가 라벨이 같을 때만 앞부분을 벗겨 냈다), 「AI 퀴즈
만들기: …」처럼 화면 라벨과 다른 이름을 콜론으로 붙였고, 마침표 없이 끝나기도 했다. 화면 라벨이 다른 줄(「AI 도우미」 ·
「게임 퀴즈 AI」 · 「홈 문장 요약」)은 그 접두가 그대로 표에 섰다 — 「채팅: 비활성화하면 …」.

이 시험은 설명 하나하나가 「…다.」로 끝나는 문장들로만 되어 있는지, 라벨을 콜론으로 붙이지 않았는지, 화면 문구에서 쓰지
않는 글리프(가운뎃점 · 줄표)가 없는지를 본다.
"""

from __future__ import annotations

import re

import pytest

from app.settings.registry import REGISTRY

pytestmark = pytest.mark.unit

_SENTENCE_BREAK = re.compile(r"(?<=\.)\s+")


@pytest.mark.parametrize("key", sorted(REGISTRY))
def test_description_is_complete_sentences(key):
    text = REGISTRY[key].description.strip()
    sentences = [s for s in _SENTENCE_BREAK.split(text) if s]
    assert sentences, key
    for sentence in sentences:
        assert sentence.endswith("다."), (key, sentence)


@pytest.mark.parametrize("key", sorted(REGISTRY))
def test_description_has_no_label_prefix_or_banned_glyphs(key):
    text = REGISTRY[key].description
    # 「비밀번호 정책: …」 같은 라벨 접두 — 화면은 라벨을 따로 그린다.
    assert ": " not in text, (key, text)
    assert "·" not in text and "—" not in text, (key, text)


def test_counterexample_the_check_catches_the_old_fragment_forms():
    """반례 — 예전 모양이 이 검사에 걸리는지 확인한다(검사기가 늘 통과만 하지 않는다)."""
    for old in (
        "대화 보존 기간(일). 이 기간이 지난 대화는 자동으로 삭제됩니다.",
        "유지보수 모드 (일반 사용자 신규 요청 차단)",
        "메일로도 보낼 수 있는 알림 유형입니다. 사용자는 이 안에서 메일로 받을 알림을 고릅니다",
    ):
        sentences = [s for s in _SENTENCE_BREAK.split(old.strip()) if s]
        assert not all(s.endswith("다.") for s in sentences), old
    assert ": " in "AI 퀴즈 만들기: 활성화하면 놀이 화면에서 AI가 퀴즈 초안을 만듭니다."
