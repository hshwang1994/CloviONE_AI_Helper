"""app/core/field_limits.py — 관리자 폼 maxLength가 실제 Pydantic 스키마에서 옳게 나오는가
(PA-RC-0005).

핀 고정 값은 각 스키마 파일을 직접 읽어 손으로 확인한 값이다(app/prompts/router.py,
app/org/schemas.py, app/templates/router.py) — 스키마가 바뀌면 이 테스트가 먼저 깨져야
`FORM_SCHEMAS`가 엉뚱한 클래스를 가리키게 된 것을 놓치지 않는다.
"""

from __future__ import annotations

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


def test_templates_limits_match_the_schema_declaration():
    limits = all_field_limits()
    expected = {"name": 120, "description": 2000, "target_ref": 64}
    assert limits["templates"]["create"] == expected
    assert limits["templates"]["edit"] == expected


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
