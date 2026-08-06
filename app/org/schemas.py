"""부서·직책 요청 스키마.

이름 검증은 서비스의 normalize_name이 한다(공백 정리 + 빈 이름 거부). 여기서 min_length로
한 번 더 막으면 '   '처럼 공백만 있는 이름이 통과해 두 곳의 규칙이 갈라진다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _StrictOrgRequest(BaseModel):
    """모르는 필드는 거절한다(users/schemas.py `_StrictRequest` 와 같은 이유).

    부서만 트리이므로 직책 요청에 `parent_id` 를 보내면 **조용히 무시**된다 — 화면은 저장됐다고
    하고 값은 아무 데도 안 남는다. 조용한 무시 대신 422 로 말해 준다.
    """

    model_config = ConfigDict(extra="forbid")


class OrgItemCreateRequest(_StrictOrgRequest):
    name: str = Field(max_length=120)


class OrgItemUpdateRequest(_StrictOrgRequest):
    name: str | None = Field(default=None, max_length=120)
    active: bool | None = None


# 부서만 트리다(0024 `Department.parent_id`). 직책 스키마에도 parent_id 를 넣어 두면 그 필드를
# 보낸 요청이 **조용히 무시**된다 — 화면은 저장됐다고 하고 값은 아무 데도 안 남는다.
# 그래서 모델별로 스키마를 나누고, 라우터 팩토리가 어느 쪽을 쓸지 인자로 받는다.
class DepartmentCreateRequest(OrgItemCreateRequest):
    parent_id: str | None = Field(default=None, max_length=36)
    # 어느 조직의 부서인가. 예전에는 이 필드가 **아예 없어서**, 조직 관리 화면이 만든 조직에
    # 부서를 넣을 방법이 없었다(사용자 지적 P5 "부서 추가하면 부서랑 조직을 연결하는 것이 없음").
    # 비우면 요청한 관리자의 조직에 만든다 — 조직이 하나뿐인 지금은 그것이 늘 맞는 답이고,
    # 조직이 늘어나도 "내 조직" 이 가장 흔한 의도다.
    org_id: str | None = Field(default=None, max_length=36)


class DepartmentUpdateRequest(OrgItemUpdateRequest):
    # 안 보냄(=그대로 둔다)과 null/""(=최상위로 올린다)을 구분해야 하므로 라우터가
    # `model_dump(exclude_unset=True)` 로 걸러 넘긴다(name/active 와 같은 규약).
    parent_id: str | None = Field(default=None, max_length=36)


# ── 조직 ──────────────────────────────────────────────────────────────────────
#
# 부서·직책과 스키마를 공유하지 않는다. 조직은 `active` 대신 `status`(active/suspended)를
# 쓰고 `slug` 를 갖는다 — 억지로 한 스키마에 넣으면 조직에 없는 필드를 보낸 요청이
# 조용히 무시된다(위 parent_id 와 같은 함정).

class OrganizationCreateRequest(_StrictOrgRequest):
    name: str = Field(max_length=200)
    # slug 는 사람이 쓰는 안정적인 키다(URL·설정·운영 스크립트에서 UUID 대신 쓴다).
    slug: str = Field(max_length=80, pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")


class OrganizationUpdateRequest(_StrictOrgRequest):
    name: str | None = Field(default=None, max_length=200)
    # slug 는 바꾸지 못한다. 다른 곳에서 이 값을 키로 참조하고 있을 수 있고, 바꾸면
    # 그 참조가 조용히 끊긴다 — 이름만 바꾸면 되는 일에 그 위험을 붙이지 않는다.
    status: str | None = Field(default=None, max_length=16)
