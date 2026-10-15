"""AI 검색의 동의어 표 (D-568).

질문의 낱말이 표의 묶음에 들면 그 묶음의 다른 낱말을 절반 가중으로 함께 찾는다(`app/ai/retrieval/query.py`). 여기서 지키는 것:

* 묶음의 짝은 그 낱말 자신 · 질문에 이미 있는 낱말을 빼고, 상한(`MAX_EXPANSIONS`) 안에서 **낱말마다 돌아가며** 고른다.
* 한 낱말이 두 묶음에 들면 두 묶음의 짝을 합친다(첫 묶음만 보면 다른 묶음의 짝을 잃는다).
* 표의 낱말은 `search_text.keywords()` 와 같은 꼴(소문자 · `[0-9a-z가-힣]`)이다 — LIKE 가지와 FTS 질의 문자열이 그대로 받는다.
"""
import re

from app.core import search_synonyms
from app.core.search_text import keywords


def test_every_word_in_the_table_has_the_keyword_shape():
    for group in search_synonyms.GROUPS:
        assert len(group) == len(set(group)), group
        for word in group:
            assert re.fullmatch(r"[0-9a-z가-힣]{2,}", word), word
            assert keywords(word, split_mixed=False) == (word,), f"{word} 가 낱말 뽑기에서 다른 꼴이 된다"


def test_expansions_skip_the_given_words_and_respect_the_limit():
    out = search_synonyms.expand(("vmware",))
    assert out == ("vsphere", "esxi", "vcenter", "vcf")
    assert "vmware" not in out
    # 두 낱말이 같은 짝을 가지면 한 번만 선다. 이미 질문에 있는 낱말(서로의 짝)은 건너뛴다.
    assert search_synonyms.expand(("vmware", "vsphere")) == ("esxi", "vcenter", "vcf", "가상화")
    assert len(search_synonyms.expand(("vmware", "네트워크", "자동화", "스토리지"), limit=2)) == 2
    assert search_synonyms.expand(("연차",)) == ()
    assert search_synonyms.expand(()) == ()


def test_each_question_word_gets_a_turn_before_any_word_gets_a_second_partner():
    """「VMware 네트워크 자동화」 — vmware 의 짝 넷이 상한을 다 채우면 「nsx」를 잃는다. 한 바퀴에 하나씩 고른다."""
    out = search_synonyms.expand(("vmware", "네트워크", "자동화"))
    assert out[:3] == ("vsphere", "nsx", "automation")
    assert len(out) == search_synonyms.MAX_EXPANSIONS


def test_a_word_in_two_groups_gets_both_groups_partners():
    partners = search_synonyms.partners_of("vsphere")
    assert "vmware" in partners and "가상화" in partners
    assert search_synonyms.partners_of("없는낱말") == ()


def test_the_hynix_group_answers_the_mixed_token_parts():
    words = keywords("SK하이닉스 프로젝트")
    assert "하이닉스" in words
    assert "hynix" in search_synonyms.expand(words)
