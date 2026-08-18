"""Request/response schemas for admin user management (spec §11, §23.3)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 이 프로젝트는 argon2-cffi 외 바이너리 의존성을 두지 않는다(CLAUDE.md §1) — pydantic의
# EmailStr은 선택 패키지 email-validator를 추가로 요구하므로 쓰지 않는다. 대신 이미
# 클라이언트(login.js EMAIL_SHAPE, Users.jsx)가 쓰는 것과 같은 최소 형태(정확히 하나의
# '@', 공백 없음)만 스키마 층에서도 거른다 — 도메인에 점을 강제하지는 않는다(사내망은
# 점 없는 내부 주소(user@host)도 유효할 수 있어서, login.js의 기존 관례와 동일하게 둔다).
# 도메인 허용 목록 검사(validate_company_email, app/users/service.py)는 마지막 '@' 기준
# 으로 도메인만 보므로 "a@b@company.com" 같은 값도 "company.com" 도메인으로 통과시킨다
# — 정확히 하나의 '@'만 요구하는 이 형태 검사가 그 틈을 막는다.
_EMAIL_SHAPE_RE = re.compile(r"^[^\s@]+@[^\s@]+$")


def _validate_email_shape(value: str) -> str:
    if not _EMAIL_SHAPE_RE.match(value.strip()):
        raise ValueError("이메일 형식이 올바르지 않습니다.")
    return value


class _StrictRequest(BaseModel):
    """모르는 필드는 거절한다.

    부서·직책이 자유 문자열({"department": "영업팀"})에서 명부 참조({"department_id": ...})로
    바뀌었다. 기본값(extra 무시)이면 옛 방식으로 보낸 요청이 200을 받고도 부서가 안
    바뀐다 — 부르는 쪽은 성공했다고 믿는다. 조용히 무시하는 대신 422로 말해 준다.
    """

    model_config = ConfigDict(extra="forbid")


class UserCreateRequest(_StrictRequest):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=120)
    role: str = "user"
    active: bool = True
    must_change_password: bool = True
    # 부서·직책은 이름이 아니라 명부(app/org)의 id로 받는다. 자유 문자열을 계속 받으면
    # 'ClovirONE팀'과 'ClovirOne팀'이 다시 갈라지고 명부를 둔 의미가 없어진다.
    department_id: str | None = Field(default=None, max_length=36)
    title_id: str | None = Field(default=None, max_length=36)
    # 소속 종류(0060) — 부서가 없을 때만 뜻이 있다. `organization`(조직 직속) 또는
    # `unassigned`(아직 미정). 부서를 주면 서버가 `department` 로 맞추므로 보낼 필요가 없다.
    membership_kind: str | None = Field(default=None, max_length=16)
    # Optional admin-chosen initial password; omitted → crypto-random temp password.
    password: str | None = Field(default=None, max_length=128)

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        return _validate_email_shape(v)


class UserUpdateRequest(_StrictRequest):
    display_name: str | None = Field(default=None, max_length=120)
    department_id: str | None = Field(default=None, max_length=36)
    title_id: str | None = Field(default=None, max_length=36)
    # 소속 종류(0060) — 부서가 없을 때만 뜻이 있다. `organization`(조직 직속) 또는
    # `unassigned`(아직 미정). 부서를 주면 서버가 `department` 로 맞추므로 보낼 필요가 없다.
    membership_kind: str | None = Field(default=None, max_length=16)
    role: str | None = None
    must_change_password: bool | None = None
    # ── 관리 범위(F2) ────────────────────────────────────────────────────────
    # 모델과 `app/core/scope.py`(읽는 쪽)는 0024 부터 있었는데 **넣는 길이 없었다** —
    # 스키마·라우터·화면 어디에도 없어서 부서 관리자를 만들 방법이 제품에 존재하지 않았다.
    # 그런데 범위 IDOR 테스트 넷은 `user.admin_scope = scope` 를 손으로 대입해 초록이었다:
    # 읽기 쪽을 훌륭하게 증명하면서 쓰기 쪽의 부재를 그 한 줄로 가리고 있었다(T3).
    admin_scope: str | None = Field(default=None, max_length=16)
    scope_org_id: str | None = Field(default=None, max_length=36)
    scope_dept_id: str | None = Field(default=None, max_length=36)


class ResetPasswordRequest(_StrictRequest):
    password: str | None = Field(default=None, max_length=128)


class BulkUserActionRequest(_StrictRequest):
    """대량 작업 요청. 상한은 서비스(app/users/bulk.py MAX_BULK_USERS)와 같은 값이어야 한다 —
    스키마가 더 느슨하면 서비스가 던지는 오류로만 걸러져 메시지가 두 벌이 된다."""

    user_ids: list[str] = Field(min_length=1, max_length=200)
    action: str = Field(max_length=32)
    # set_department / set_title 의 대상 id. 빈 값이면 '지정 해제'다.
    value: str | None = Field(default=None, max_length=36)


class ImportUsersRequest(_StrictRequest):
    """CSV 본문을 문자열로 받는다(멀티파트 업로드 아님).

    이유: 이 앱의 프런트는 파일을 읽어 텍스트로 다루고 있고, 멀티파트를 새로 도입하면
    CSRF·크기 제한·인코딩 판정이 전부 별도 경로가 된다. 텍스트로 받으면 기존 JSON 경로의
    검증이 그대로 적용된다. 200행 상한(MAX_IMPORT_ROWS)이 크기의 실질 상한이다.
    """

    csv_text: str = Field(min_length=1, max_length=200_000)
    # 기본이 미리보기다. 미리보기 없이 100명이 생기는 버튼은 아무도 못 누른다.
    dry_run: bool = True
