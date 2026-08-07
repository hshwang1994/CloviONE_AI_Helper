"""프로젝트 이름이 **UUID 로 보이던** 사고 (운영에서 눈으로 확인).

## 무엇이 보였나

프로젝트 목록 22건이 전부 이렇게 떴다:

    (제목 없음) 262c5c5a-5684-8032-b0e1-c9b6467cb3b3

## 왜

이 워크스페이스의 프로젝트 DB 는 제목 속성 이름이 **`프로젝트`** 인데, 별칭표에는
`제목`·`이름`·`Name` 만 있었다. Notion 은 없는 속성을 물어도 **예외를 주지 않는다** -
그냥 없는 것이다. 그래서 조용히 빈 문자열이 됐고 폴백 문구가 UUID 를 화면에 뿌렸다.

## 고친 방향

이름을 더 넣는 것으로는 같은 사고가 또 난다 - 고객마다 이름이 다르고 언제든 바뀐다.
Notion DB 에는 **`type: "title"` 인 속성이 정확히 하나** 있고 그것이 곧 제목이다.
구조로 찾으면 이름이 무엇이든 맞는다.
"""

from __future__ import annotations

import pytest

from app.projects.notion_source import schema_prop

pytestmark = pytest.mark.regression


def test_the_real_workspace_schema_finds_its_title():
    """운영에서 실제로 읽어 온 스키마 그대로. 이 표본이 곧 사고 그 자체다."""
    schema = {
        "기간": {"type": "date"},
        "프로젝트 진행률": {"type": "formula"},
        "담당자(정)": {"type": "people"},
        "요약": {"type": "rich_text"},
        "진행 상태": {"type": "status"},
        "프로젝트": {"type": "title"},      # 🔴 이름이 '제목' 이 아니다
    }
    name, prop = schema_prop(schema, "title")
    assert name == "프로젝트", f"제목 속성을 못 찾았다: {name}"
    assert prop["type"] == "title"


@pytest.mark.parametrize("title_name", ["제목", "이름", "Name", "Project", "프로젝트명", "무슨이름이든"])
def test_any_title_name_works(title_name):
    """이름을 몰라도 맞아야 한다 - 고객마다 다르고 언제든 바뀐다."""
    schema = {"요약": {"type": "rich_text"}, title_name: {"type": "title"}}
    name, _ = schema_prop(schema, "title")
    assert name == title_name


def test_a_schema_without_a_title_returns_none_instead_of_guessing():
    """오탐 방지 - 없으면 없다고 해야 한다. 아무 속성이나 제목으로 쓰면 더 나쁘다."""
    name, prop = schema_prop({"요약": {"type": "rich_text"}}, "title")
    assert name is None and prop is None


def test_other_fields_still_match_by_name():
    """오탐 방지 - 제목만 타입으로 찾는다. 나머지는 이름 별칭 그대로다."""
    schema = {"진행 상태": {"type": "status"}, "프로젝트": {"type": "title"}}
    name, _ = schema_prop(schema, "status")
    assert name == "진행 상태"
