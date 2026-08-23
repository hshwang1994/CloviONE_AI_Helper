"""app/core/field_limits.py — 관리자 폼 maxLength가 실제 Pydantic 스키마에서 옳게 나오는가
(PA-RC-0005).

핀 고정 값은 각 스키마 파일을 직접 읽어 손으로 확인한 값이다(app/prompts/router.py,
app/org/schemas.py, app/templates/router.py) — 스키마가 바뀌면 이 테스트가 먼저 깨져야
`FORM_SCHEMAS`가 엉뚱한 클래스를 가리키게 된 것을 놓치지 않는다.
"""

from __future__ import annotations

"""qa-contract-change: 폼 필드 상한을 스키마에서 그대로 읽는다는 계약의 화면이 셋 줄었다(runners·workflows·templates). 남은 연동 쪽 단언은 그대로이고, 그 자리에 **반대 방향 단언**을 넣었다 — 사라진 세 화면이 결과에 되살아나면 실패한다. 화면 없는 상한이 생기는 것을 그것이 막는다."""

import pytest
from pydantic import BaseModel, Field

from app.core.field_limits import all_field_limits, schema_max_lengths

pytestmark = pytest.mark.unit


def test_optional_and_required_fields_both_surface_their_max_length():
    """Optional[str]은 JSON schema에서 anyOf 아래 묻힌다 — 둘 다 잡아야 한다."""

    class Sample(BaseModel):
        required_field: str = Field(max_length=10)
        optional_field: str | None = Field(default=None, max_length=20)
        no_limit_field: str | None = None
        untyped_number: int = 5

    assert schema_max_lengths(Sample) == {"required_field": 10, "optional_field": 20}


def test_prompts_and_policies_limits_match_the_schema_declarations():
    limits = all_field_limits()
    assert limits["prompts"]["create"] == {"name": 120, "purpose": 2000, "content": 100000}
    assert limits["prompts"]["edit"] == {"content": 100000, "purpose": 2000}
    assert limits["policies"]["create"] == {"name": 120, "purpose": 2000, "content": 100000}
    assert limits["policies"]["edit"] == {"content": 100000, "purpose": 2000}


def test_org_screens_limits_match_the_schema_declarations():
    limits = all_field_limits()
    assert limits["departments"]["create"] == {"name": 120, "parent_id": 36, "org_id": 36}
    assert limits["departments"]["edit"] == {"name": 120, "parent_id": 36}
    assert limits["job-titles"]["create"] == {"name": 120}
    assert limits["job-titles"]["edit"] == {"name": 120}
    assert limits["organizations"]["create"] == {"name": 200, "slug": 80}
    assert limits["organizations"]["edit"] == {"name": 200, "status": 16}


def test_runner_id_has_no_pydantic_limit_and_is_correctly_absent():
    """PA-RC-0005 scope note: DB엔 String(36)이 있어도 PromptCreateRequest.runner_id는
    Field(max_length=)가 없다 — 서버가 실제로 길이로 거절하지 않으므로 결과에도 없어야 한다
    (없는데 있다고 하면 화면이 서버가 안 지키는 약속을 강제하게 된다)."""
    limits = all_field_limits()
    assert "runner_id" not in limits["prompts"]["create"]


def test_schedules_limits_match_the_schema_declaration():
    """create/edit이 같은 스키마(ScheduleRequest)를 쓴다 — templates와 동일 패턴."""
    limits = all_field_limits()
    expected = {"name": 120, "description": 2000, "cron_expression": 120, "target_ref": 64}
    assert limits["schedules"]["create"] == expected
    assert limits["schedules"]["edit"] == expected


def test_approval_delegations_has_create_only_no_edit_key():
    """위임은 회수만 가능하고 편집 폼이 없다(governance.js) — "edit" 키 자체가 없어야 한다
    (있는데 빈 dict인 것과 아예 없는 것은 다르다 — FORM_SCHEMAS에 실수로 넣지 않았는지 못박는다)."""
    limits = all_field_limits()
    assert limits["approval-delegations"]["create"] == {
        "delegator_user_id": 36, "delegate_user_id": 36, "reason": 500,
    }
    assert "edit" not in limits["approval-delegations"]


def test_integrations_limits_match_the_schema_declarations():
    """create/edit 스키마 이름이 다르다(Config/UpdateRequest). 연동은 우연히 대칭이라
    두 벌이 같은 값이어야 한다 — 한쪽만 고치면 여기서 걸린다.

    S11 이전에는 러너·워크플로도 함께 봤고, 그 둘은 **비대칭**이었다(edit 스키마에
    `Field(max_length=)` 가 없는 필드가 있었다). 두 화면과 함께 사라졌다."""
    limits = all_field_limits()
    assert limits["integrations"]["create"] == {
        "name": 120, "description": 2000, "base_url": 500, "health_url": 500, "secret_ref": 128,
    }
    assert limits["integrations"]["edit"] == limits["integrations"]["create"]

    # 사라진 세 화면이 결과에 되살아나면 안 된다 — FORM_SCHEMAS 에 다시 얹히는 순간
    # 화면 없는 상한이 생긴다.
    for gone in ("runners", "workflows", "templates"):
        assert gone not in limits, f"{gone} 화면이 없는데 필드 상한이 남아 있다"


def test_announcements_and_ai_quotas_limits_match_the_schema_declarations():
    limits = all_field_limits()
    expected_announce = {
        "title": 200, "body": 4000, "level": 16, "audience": 16,
        "link_url": 500, "link_label": 80,
    }
    assert limits["announcements"]["create"] == expected_announce
    assert limits["announcements"]["edit"] == expected_announce

    assert limits["ai-quotas"]["create"] == {
        "scope_type": 16, "user_id": 36, "period": 16, "note": 200,
    }
    assert limits["ai-quotas"]["edit"] == {"note": 200}


def test_users_limits_match_the_schema_declarations():
    """PA-RC-0014 — Users.jsx는 registry 화면은 아니지만 FormModal을 그대로 쓰므로 다른
    screenKey와 똑같이 FORM_SCHEMAS에 연결한다(field_limits.py 모듈 docstring 참고)."""
    limits = all_field_limits()
    assert limits["users"]["create"] == {
        "email": 255, "display_name": 120, "password": 128, "department_id": 36, "title_id": 36,
        # 소속 종류(0060) — 만들 때부터 정할 수 있어야 한다. 기본값은 '미지정'(fail-closed).
        "membership_kind": 16,
    }
    assert limits["users"]["edit"] == {
        "display_name": 120, "department_id": 36, "title_id": 36,
        "admin_scope": 16, "scope_org_id": 36, "scope_dept_id": 36,
        # 소속 종류(0060). 부서/조직 직속/미지정을 가르는 값이라 폼에서 고칠 수 있어야 하고,
        # 폼에 있으면 다른 필드와 같이 길이 계약에 잡혀야 한다.
        "membership_kind": 16,
    }


def test_offboarding_limits_match_the_schema_declaration():
    """오프보딩 실행 폼(메모)도 같은 처리를 받는다(PA-RC-0014 acceptance_criteria 4) — formKind는
    create/edit이 아니라 "run"(1회성 실행)이다."""
    limits = all_field_limits()
    assert limits["offboarding"]["run"] == {"successor_user_id": 36, "note": 1000}
