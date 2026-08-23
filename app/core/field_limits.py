"""관리자 폼 maxLength의 단일 출처 (PA-RC-0005).

`app/*/schemas.py`·라우터 안 요청 스키마의 `Field(max_length=)`가 정본이다. 여기서는 그 값을
두 번째로 손으로 적지 않는다 — Pydantic의 `model_json_schema()`에서 그대로 읽는다.
`scripts/generate_field_limits.py`가 이 모듈을 불러 `frontend/src/generated/fieldLimits.json`
으로 내보내고, `scripts/check_field_limits_fresh.py`가 그 파일이 지금 스키마와 맞는지
(static_checks.sh 경유) 검사한다 — 프런트 번들 신선도 검사(check_bundle_fresh.py)와 같은 관용이다.

## 무엇을 매핑하는가, 무엇을 매핑하지 않는가

`FORM_SCHEMAS`의 키는 화면 이름표일 뿐이다 — 소비하는 쪽이 둘 있다. (1) `kit.jsx`의
`FormModal`이 `screenKey`/`formKind` prop으로 `maxLengthFor()`를 호출하는 경로
(`frontend/src/screens/registry/*.js`의 DataScreen 화면이 대다수지만, `Users.jsx`처럼
registry 밖의 손으로 쓴 화면도 그 상세/생성/수정 폼이 이미 `FormModal`을 그대로 쓰면
`screenKey="users"`만 넘겨 재사용할 수 있다 — PA-RC-0014, 새 경로를 만들지 않았다).
(2) `FormModal`조차 안 쓰는 완전 수제 화면(`Offboarding.jsx`)이 자기 `<TextField>`에서
`maxLengthFor()`를 직접 불러 쓰는 경로 — 이 경우 `formKind`는 "create"/"edit"이 아니어도
된다(예: `"offboarding": {"run": ...}`, 아래 `FORM_SCHEMAS` 주석 참고). 두 경로 다
`app/*/schemas.py`가 정본이라는 점은 같다.

## Pydantic max_length가 없는 필드는 결과에 없다

`prompt_id`처럼 `Field(max_length=)`가 없는 필드(DB 컬럼엔 `String(36)`이 있어도)는 결과에
아예 나오지 않는다. 백엔드가 실제로 길이 때문에 422를 내는 필드만 프런트에 약속한다 — DB
컬럼 길이만 있고 API 계층 검증이 없는 필드까지 넣으면, 서버가 실제로는 안 막는 상한을 화면이
거짓으로 강제하게 된다(constraints: 서버 검증을 정본으로 삼는다).
"""

from __future__ import annotations

from pydantic import BaseModel

from app.announcements.router import AnnouncementPatch, AnnouncementRequest
from app.approvals.router import DelegationRequest
from app.integrations.schemas import IntegrationConfig, IntegrationUpdateRequest
from app.offboarding.schemas import OffboardingRunRequest
from app.org.schemas import (
    DepartmentCreateRequest,
    DepartmentUpdateRequest,
    OrganizationCreateRequest,
    OrganizationUpdateRequest,
    OrgItemCreateRequest,
    OrgItemUpdateRequest,
)
from app.prompts.router import (
    PolicyContentUpdateRequest,
    PolicyCreateRequest,
    PromptContentUpdateRequest,
    PromptCreateRequest,
)
from app.quotas.router import QuotaPatch, QuotaRequest
from app.schedules.router import ScheduleRequest
from app.users.schemas import UserCreateRequest, UserUpdateRequest


def _extract_max_length(prop: dict) -> int | None:
    if "maxLength" in prop:
        return prop["maxLength"]
    for branch in prop.get("anyOf", ()):
        if "maxLength" in branch:
            return branch["maxLength"]
    return None


def schema_max_lengths(model: type[BaseModel]) -> dict[str, int]:
    """`model`이 선언한 필드별 `max_length`(선언한 필드만, 손으로 옮기지 않고 그대로 읽는다)."""
    props = model.model_json_schema().get("properties", {})
    out: dict[str, int] = {}
    for name, prop in props.items():
        limit = _extract_max_length(prop)
        if limit is not None:
            out[name] = limit
    return out


# screen key(frontend registry/*.js의 config.key) → {"create"/"edit": 그 폼이 실제로 제출하는
# 요청 스키마}. 새 화면을 여기 연결하려면 이 표에 한 줄만 추가하면 된다 — 프런트는 고칠 필요
# 없다(FormModal이 config.key로 fieldLimits.json을 자동 조회한다).
#
# edit 스키마는 그 화면의 실제 PATCH/PUT 바디와 일치해야 한다 — 라우터가 다른 스키마를 쓰면
# (예: create.fields에는 있는데 edit 스키마엔 없는 필드) 여기서 자동으로 걸러진다(그 필드는
# 결과에 없는 채로 남는다). schedules처럼 create/edit이 같은 스키마를 쓰는 화면도 있다.
FORM_SCHEMAS: dict[str, dict[str, type[BaseModel]]] = {
    "prompts": {"create": PromptCreateRequest, "edit": PromptContentUpdateRequest},
    "policies": {"create": PolicyCreateRequest, "edit": PolicyContentUpdateRequest},
    "departments": {"create": DepartmentCreateRequest, "edit": DepartmentUpdateRequest},
    "job-titles": {"create": OrgItemCreateRequest, "edit": OrgItemUpdateRequest},
    "organizations": {"create": OrganizationCreateRequest, "edit": OrganizationUpdateRequest},
    "schedules": {"create": ScheduleRequest, "edit": ScheduleRequest},
    # 위임(delegation)은 생성 후 편집 폼이 없다(회수만 가능 — governance.js) — "edit" 키 자체가 없다.
    "approval-delegations": {"create": DelegationRequest},
    "integrations": {"create": IntegrationConfig, "edit": IntegrationUpdateRequest},
    "announcements": {"create": AnnouncementRequest, "edit": AnnouncementPatch},
    "ai-quotas": {"create": QuotaRequest, "edit": QuotaPatch},
    "users": {"create": UserCreateRequest, "edit": UserUpdateRequest},
    # 오프보딩 실행 폼은 create/edit이 아니라 1회성 실행이다 — formKind를 "run"으로 둔다
    # (maxLengthFor는 formKind 문자열 자체엔 의미를 두지 않고 그대로 조회만 한다).
    "offboarding": {"run": OffboardingRunRequest},
}


def all_field_limits() -> dict[str, dict[str, dict[str, int]]]:
    """`{screen: {"create"|"edit": {field_name: max_length}}}` — 전부 실시간 introspection."""
    return {
        screen: {form: schema_max_lengths(model) for form, model in forms.items()}
        for screen, forms in FORM_SCHEMAS.items()
    }
