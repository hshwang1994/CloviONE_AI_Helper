"""UA-12: 부서·직책 생성/수정의 중복 검사 범위가 실제 유니크 제약과 어긋나 있었다.

`JobTitle.name`은 모델 docstring이 명시하듯 **전역** 유니크다("팀장은 조직이 늘어도
같은 이름을 쓰는 게 자연스럽다"). 그런데 `org/service.py`의 중복 검사(`find_by_name`)는
Department의 `(org_id, name)` 제약에 맞춰 조직 안에서만 봤다 — JobTitle에도 같은 함수를
그대로 썼다. 그래서 다른 조직에 같은 이름의 직책이 있으면 사전검사는 통과하고,
INSERT에서 잡히지 않은 IntegrityError로 500이 났다(생성·이름변경 둘 다).

반대 방향 버그도 있었다: 전역 관리자가 org_id를 안 보내면(스코프도 없다) 저장은
컬럼 기본값(DEFAULT_ORG_ID) 안에서 이뤄지는데, 사전검사는 그 기본값을 모르고
전역으로 봐서 **관계없는 다른 조직**의 같은 이름과 충돌해 잘못된 409가 났다.
"""

from __future__ import annotations

import pytest

from app.core.errors import ConflictError
from app.core.scope import ADMIN_SCOPE_ORG, GLOBAL_SCOPE, Scope
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department, JobTitle
from app.org.service import create_item, update_item

pytestmark = pytest.mark.regression


def _org_scope(org_id: str) -> Scope:
    return Scope(kind=ADMIN_SCOPE_ORG, org_id=org_id)


def test_job_title_same_name_in_a_different_org_is_a_clean_409_not_500(db, two_orgs):
    create_item(db, JobTitle, name="팀장", scope=_org_scope(two_orgs.org_a_id))
    db.commit()

    # JobTitle 이름은 전역 유일이다 — 다른 조직에서 만들어도 진짜 충돌이고, 사전검사가
    # 그걸 못 보면 INSERT의 전역 UNIQUE에서 처리 안 된 IntegrityError로 500이 났다.
    with pytest.raises(ConflictError):
        create_item(db, JobTitle, name="팀장", scope=_org_scope(two_orgs.org_b_id))


def test_renaming_a_job_title_to_a_name_used_in_another_org_is_a_clean_409(db, two_orgs):
    create_item(db, JobTitle, name="팀장", scope=_org_scope(two_orgs.org_a_id))
    other = create_item(db, JobTitle, name="사원", scope=_org_scope(two_orgs.org_b_id))
    db.commit()

    with pytest.raises(ConflictError):
        update_item(db, other, name="팀장", scope=_org_scope(two_orgs.org_b_id))


def test_department_same_name_in_a_different_org_is_allowed(db, two_orgs):
    """Department는 (org_id, name) 유니크다 — 다른 조직이면 이름이 겹쳐도 정상이다.
    JobTitle 수정으로 이 경로가 덩달아 더 엄격해지면 안 된다(회귀 방지)."""
    create_item(db, Department, name="개발팀", scope=_org_scope(two_orgs.org_a_id))
    db.commit()

    # 다른 조직이면 같은 이름이어도 충돌이 아니다 — 실제 DB 제약과 일치해야 한다.
    row = create_item(db, Department, name="개발팀", scope=_org_scope(two_orgs.org_b_id))
    assert row.org_id == two_orgs.org_b_id


def test_global_admin_creating_a_department_does_not_false_conflict_with_another_orgs_department(
    db, two_orgs
):
    """UA-12의 '반대 방향' 버그: org_id도 scope도 없는 전역 관리자가 부서를 만들면
    실제로는 DEFAULT_ORG_ID 안에만 저장되는데, 예전 사전검사는 전역으로 봐서 다른
    조직의 같은 이름과도 충돌해 잘못된 409를 냈다."""
    # org_b 에 미리 같은 이름의 부서를 만들어 둔다 — DEFAULT_ORG_ID 와는 무관한 조직이다.
    create_item(db, Department, name="영업팀", scope=_org_scope(two_orgs.org_b_id))
    db.commit()
    assert two_orgs.org_b_id != DEFAULT_ORG_ID

    # 전역 관리자, org_id 미지정 — 실제로는 DEFAULT_ORG_ID 에 만들어져야 하고, org_b의
    # '영업팀'과는 무관해야 한다.
    row = create_item(db, Department, name="영업팀", scope=GLOBAL_SCOPE)
    assert row.org_id == DEFAULT_ORG_ID
