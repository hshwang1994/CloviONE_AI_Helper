"""확정표 적용이 **실제로 Key 를 잡고, 못 찾은 것은 안 만지는가** (U11 · D-197 · D-243).

문서와 코드가 같은지는 `tests/unit/test_project_keys_confirmed.py` 가 본다. 여기서 보는
것은 그 표가 **행에 닿는지**다 — 표가 맞아도 적용이 안 돌면 S13 은 Key 없는 프로젝트를
받고, 그 프로젝트의 티켓은 전부 번호를 못 받는다.

## 여기서 가장 중요한 단정

**표에 없는 프로젝트를 건드리지 않는다.** 「이 프로젝트에도 뭔가 붙여 주자」가 정확히
U11 이 금지한 임의 배정이고, 잘못 붙인 Key 는 영구다(D-196).
"""

from __future__ import annotations

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.work import keys as keys_mod
from app.work import project_keys
from app.work.models import KEY_ACTIVE, ProjectKeyRegistry

pytestmark = pytest.mark.integration


def _project(db, name, *, code=None):
    row = Project(name=name, code=code, org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.flush()
    return row


def test_it_claims_the_confirmed_key_for_a_matching_project(db):
    key, name = project_keys.CONFIRMED[0]
    project = _project(db, name)

    report = project_keys.apply_confirmed(db)
    db.refresh(project)

    assert project.code == key, f"«{name}» 에 «{key}» 가 안 붙었다: {project.code}"
    assert [e["key"] for e in report[project_keys.APPLIED]] == [key]

    row = db.get(ProjectKeyRegistry, key)
    assert row is not None and row.state == KEY_ACTIVE and row.project_id == project.id, (
        "대장에 안 올라갔다 — 다른 조직이 같은 이름을 가져갈 수 있다"
    )


def test_it_never_touches_a_project_that_is_not_in_the_table(db):
    """**이 시험이 U11 이다.** 표에 없는 이름은 Key 를 받지 않는다."""
    stranger = _project(db, "표에 없는 프로젝트")

    project_keys.apply_confirmed(db)
    db.refresh(stranger)

    assert stranger.code is None, f"표에 없는 프로젝트에 Key 가 붙었다: {stranger.code}"


def test_missing_projects_are_reported_not_invented(db):
    """PostgreSQL 의 `projects` 가 비어 있는 지금 상태가 바로 이것이다.

    20건 전부 «못 찾음» 이고 **그것이 정상**이다 — 적재는 S13 이다.
    """
    report = project_keys.apply_confirmed(db)

    assert len(report[project_keys.NOT_FOUND]) == len(project_keys.CONFIRMED)
    assert report[project_keys.APPLIED] == []
    assert db.query(ProjectKeyRegistry).filter(
        ProjectKeyRegistry.state == KEY_ACTIVE
    ).count() == 0, "못 찾았는데 대장에 뭔가 올라갔다"


def test_running_it_twice_changes_nothing(db):
    """재실행 안전. S13 이 적재를 나눠 돌려도 같은 결과여야 한다."""
    key, name = project_keys.CONFIRMED[1]
    project = _project(db, name)

    first = project_keys.apply_confirmed(db)
    second = project_keys.apply_confirmed(db)
    db.refresh(project)

    assert [e["key"] for e in first[project_keys.APPLIED]] == [key]
    assert second[project_keys.APPLIED] == [], "두 번째 실행이 또 잡았다"
    assert [e["key"] for e in second[project_keys.ALREADY]] == [key]
    assert project.code == key


def test_a_project_that_already_has_another_key_is_left_alone(db):
    """Key 를 **바꾸는 것**은 옛 canonical 을 별칭으로 남겨야 하는 별도 동작이다(D-195).

    여기서 조용히 갈아 끼우면 그 프로젝트의 옛 링크가 전부 죽는다.
    """
    key, name = project_keys.CONFIRMED[2]
    project = _project(db, name)
    keys_mod.claim(db, project_id=project.id, key="OLDKEY")
    db.flush()

    report = project_keys.apply_confirmed(db)
    db.refresh(project)

    assert project.code == "OLDKEY", "확정표가 옛 Key 를 조용히 갈아 끼웠다"
    assert [e["key"] for e in report[project_keys.OTHER_KEY]] == [key]


def test_two_projects_with_the_same_name_are_reported_not_guessed(db):
    """같은 이름이 둘이면 어느 쪽인지 사람만 안다. 골라 주지 않는다."""
    key, name = project_keys.CONFIRMED[3]
    _project(db, name)
    _project(db, name)

    report = project_keys.apply_confirmed(db)

    assert [e["key"] for e in report[project_keys.AMBIGUOUS]] == [key]
    assert report[project_keys.APPLIED] == []
    assert db.get(ProjectKeyRegistry, key) is None, "모호한데 대장에 올라갔다"


def test_whitespace_differences_still_match(db):
    """소스가 겹공백이나 끝 공백을 주는 일은 흔하다. 그것 때문에 못 찾으면 안 된다."""
    key, name = project_keys.CONFIRMED[4]
    project = _project(db, f"  {name.replace(' ', '  ')} ")

    project_keys.apply_confirmed(db)
    db.refresh(project)

    assert project.code == key


def test_numbering_works_right_after_applying(db):
    """적용이 **채번까지 이어지는가** — 그것이 이 표가 존재하는 이유다.

    Key 가 붙는 순간부터 그 프로젝트의 티켓은 `<KEY>-<SEQ>` 를 받는다.
    """
    from app.work import numbering

    key, name = project_keys.CONFIRMED[5]
    project = _project(db, name)
    project_keys.apply_confirmed(db)
    db.flush()

    assert numbering.allocate(db, project.id) == 1


def test_the_summary_says_what_happened(db):
    """숫자만 주면 「무엇이 안 됐나」를 다시 물어야 한다."""
    _project(db, project_keys.CONFIRMED[6][1])
    report = project_keys.apply_confirmed(db)
    line = project_keys.summarize(report)

    assert "applied 1" in line and f"not_found {len(project_keys.CONFIRMED) - 1}" in line
