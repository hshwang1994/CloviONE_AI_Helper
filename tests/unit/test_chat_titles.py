"""AI 도우미 대화의 자동 제목 — 첫 질문을 다듬는 규칙 (AI 채팅 개선 회차).

제목은 무엇을 물었는가를 짧게 말한다. 끝의 요청 어미 · 물음표는 떼고, 줄바꿈 · 제어 문자는 공백이 되며, 목록 두 줄(40자)을
넘으면 낱말 경계에서 자르고 말줄임표를 단다(AI-55 — 잘렸다는 표시가 없으면 같은 문장으로 시작하는 대화가 똑같아 보인다).
"""

from __future__ import annotations

import pytest

from app.chat.service import AUTO_TITLE_MAX_CHARS, DEFAULT_TITLE, clean_title


@pytest.mark.parametrize(("question", "title"), [
    ("나에게 할당된 티켓 보여줘", "나에게 할당된 티켓"),
    ("SK하이닉스 프로젝트 진행률이 몇 퍼센트야?", "SK하이닉스 프로젝트 진행률이 몇 퍼센트야"),
    ("내가 만든 문서", "내가 만든 문서"),
    ("회의록 요약해줘", "회의록 요약"),
    ("이번 주 마감 티켓 좀 알려 주세요.", "이번 주 마감 티켓"),
    ("VMware 문서 찾아줘!!", "VMware 문서"),
    ("안녕?", "안녕"),
])
def test_request_endings_and_marks_are_dropped(question, title):
    assert clean_title(question) == title


def test_other_verbs_are_kept():
    # 요청 어미 목록에 없는 말은 그대로 둔다 — 「보내줘」를 「보내」로 자르면 뜻이 이상해진다.
    assert clean_title("회의록 보내줘") == "회의록 보내줘"


def test_control_characters_and_newlines_become_spaces():
    assert clean_title("줄바꿈\n있는\t질문​ 좀 알려줘요") == "줄바꿈 있는 질문"


def test_nothing_left_falls_back_to_the_default_title():
    assert clean_title("?") == DEFAULT_TITLE
    assert clean_title("   ") == DEFAULT_TITLE


def test_long_questions_are_cut_at_a_word_boundary_with_an_ellipsis():
    question = "VMware NSX 네트워크 자동화 구성 관련해서 지금까지 작성된 문서와 티켓을 모두 정리해 주세요"
    title = clean_title(question)
    assert title.endswith("…") and len(title) <= AUTO_TITLE_MAX_CHARS
    assert question.startswith(title[:-1])
    assert question[len(title) - 1] == " "


def test_one_long_word_is_cut_without_a_boundary():
    title = clean_title("가" * 80)
    assert title == "가" * (AUTO_TITLE_MAX_CHARS - 1) + "…"
