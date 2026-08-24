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

## 지금 이 성질이 어디에 사는가 (S14)

제품은 Notion 을 읽지 않는다. 그래서 이 규칙을 갖고 있던 `app/projects/notion_source.py`
는 사라졌고, 같은 규칙이 **이관 도구**(`app/migration/transform.py`)에 그대로 남았다.
사고의 조건은 하나도 달라지지 않았다 — 재설치나 두 번째 설치에서 옛 워크스페이스를 한 번
읽어 올 때, 제목 속성 이름을 못 맞히면 프로젝트 21건이 이름 없이 넘어온다. 그 순간에는
고칠 기회조차 없다(원본을 다시 읽어야 한다). 그래서 판정 대상만 옮겨 이 자리에 남긴다.
"""

from __future__ import annotations

import pytest

from app.migration.transform import parse_project, relation_titles

pytestmark = pytest.mark.regression


def _title_prop(name: str) -> dict:
    return {"type": "title", "title": [{"type": "text", "plain_text": name}]}


def _project_page(properties: dict, *, page_id: str = "262c5c5a") -> dict:
    return {"id": page_id, "properties": properties}


def test_the_real_workspace_schema_finds_its_title():
    """운영에서 실제로 읽어 온 스키마 그대로. 이 표본이 곧 사고 그 자체다."""
    row = _project_page({
        "기간": {"type": "date", "date": None},
        "프로젝트 진행률": {"type": "formula", "formula": {}},
        "담당자(정)": {"type": "people", "people": []},
        "요약": {"type": "rich_text", "rich_text": []},
        "진행 상태": {"type": "status", "status": {"name": "진행 중"}},
        "프로젝트": _title_prop("알파 프로젝트"),   # 🔴 이름이 '제목' 이 아니다
    })
    parsed = parse_project(row)
    assert parsed["name"] == "알파 프로젝트", f"제목 속성을 못 찾았다: {parsed['name']!r}"
    # 이름을 찾느라 나머지를 놓치지 않았는지도 함께 본다.
    assert parsed["notion_status"] == "진행 중"


@pytest.mark.parametrize("title_name", ["제목", "이름", "Name", "Project", "프로젝트명", "무슨이름이든"])
def test_any_title_name_works(title_name):
    """이름을 몰라도 맞아야 한다 - 고객마다 다르고 언제든 바뀐다."""
    row = _project_page({
        "요약": {"type": "rich_text", "rich_text": []},
        title_name: _title_prop("베타 프로젝트"),
    })
    assert parse_project(row)["name"] == "베타 프로젝트"


def test_a_schema_without_a_title_leaves_the_name_empty_instead_of_guessing():
    """오탐 방지 - 없으면 없다고 해야 한다. 아무 속성이나 제목으로 쓰면 더 나쁘다."""
    row = _project_page({
        "요약": {"type": "rich_text", "rich_text": [{"type": "text", "plain_text": "설명"}]},
    })
    assert parse_project(row)["name"] == ""


def test_other_fields_still_match_by_name():
    """오탐 방지 - 제목만 타입으로 찾는다. 나머지는 이름 그대로 찾는다."""
    row = _project_page({
        "진행 상태": {"type": "status", "status": {"name": "차질"}},
        "프로젝트": _title_prop("감마"),
        # 이름이 다른 상태 속성은 상태로 읽히면 안 된다.
        "옛 진행 상태": {"type": "status", "status": {"name": "완료"}},
    })
    parsed = parse_project(row)
    assert parsed["notion_status"] == "차질"


def test_relation_titles_read_the_same_way():
    """문서 분류 taxonomy 도 같은 규칙으로 이름을 얻는다 - 한쪽만 고치면 절반이 또 UUID 다."""
    rows = [
        {"id": "t1", "properties": {"유형": _title_prop("계약서")}},
        {"id": "c1", "properties": {"카테고리 이름": _title_prop("영업")}},
        {"id": "x1", "properties": {"메모": {"type": "rich_text", "rich_text": []}}},
    ]
    assert relation_titles(rows) == {"t1": "계약서", "c1": "영업", "x1": ""}
