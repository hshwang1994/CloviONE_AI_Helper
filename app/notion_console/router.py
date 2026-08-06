"""Notion 관리 API (9-4).

## 왜 `SYSTEM_ADMIN_ONLY` 인가

`app/setup/router.py` 와 `app/sysops/router.py` 가 적어 둔 근거가 여기에도 그대로 적용된다.
`CONSOLE_WRITE_ROLES` 에는 `admin` 이 들어 있고 이 제품의 `admin` 은 부서 범위로 좁혀질 수
있다(`admin_scope="dept"`). 부서 관리자는 자기 부서 사람을 관리하는 사람이지, **이 설치
전체가 어느 노션 워크스페이스를 보는지**를 정하는 사람이 아니다. 여기서 바뀌는 것은 조직
단위가 아니라 설치 한 벌 전체라 범위라는 개념 자체가 없다.

## 왜 데이터베이스 id 를 여기서 저장하지 않는가

id 는 설정 레지스트리를 지난다(`PUT /api/admin/settings/{key}`). 거기에는 검증, 감사,
버전 이력, 되돌리기가 이미 붙어 있다. 여기에 두 번째 쓰기 경로를 내면 그 넷이 없는 길이
생기고, 언젠가 그 길로만 값이 바뀐다. 이 라우터가 저장하는 것은 **레지스트리로 표현할 수
없는 것 둘**뿐이다: 시크릿 파일(토큰)과 노션에 실제로 데이터베이스를 만드는 동작.

## 토큰은 응답에도 감사에도 남지 않는다

받은 값은 파일로만 간다. 응답은 설정됨 여부만 말하고, 감사 기록의 before/after 에도
`{"configured": true}` 만 넣는다. 값이 한 번이라도 봉투에 실리면 그 봉투는 되돌려 읽을 수
있는 자리(감사 로그, 진단 번들)로 흘러간다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import SYSTEM_ADMIN_ONLY
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import ValidationAppError
from app.notion_console import service
from app.notion_console.service import OBJECT_TYPE_DATABASE, OBJECT_TYPE_TOKEN

router = APIRouter(
    prefix="/api/admin/notion",
    tags=["admin-notion"],
    dependencies=[Depends(require_csrf), Depends(require_roles(*SYSTEM_ADMIN_ONLY))],
)

# 토큰 길이 상한. 노션 통합 토큰은 60자 안팎이다. 상한을 두는 이유는 크기가 아니라
# **잘못 붙여 넣은 것을 저장하지 않기 위해서**다 - 페이지를 통째로 복사해 넣는 일이 있다.
MAX_TOKEN_LENGTH = 500


def _effective(request: Request, db: Session) -> dict:
    from app.settings.service import effective_settings

    return effective_settings(db, request.app.state.settings_cache)


@router.get("")
def notion_overview(request: Request, db: Session = Depends(get_db)) -> dict:
    """화면 한 판. **외부 호출을 하지 않는다.**

    화면을 여는 것만으로 노션을 부르면, 관리자가 이 탭을 열어 둔 채 회의를 하는 동안
    몇 분마다 요청이 나간다(폴링). 노션은 초당 3요청으로 제한한다 - 진단이 정작 동기화를
    밀어낸다. 실제 호출은 사람이 누르는 연결 테스트에서만 나간다.
    """
    return service.overview(
        request.app.state.settings,
        request.app.state.secret_provider,
        _effective(request, db),
    )


@router.post("/test")
def notion_connection_test(request: Request, db: Session = Depends(get_db)) -> dict:
    """토큰과 데이터베이스를 실제로 한 번씩 부른다.

    쓰기가 아니지만 POST 인 이유: 부작용이 없다고 해서 GET 으로 두면 브라우저와 프록시가
    캐시하고, 그러면 사람이 다시 눌러도 **옛 결과**를 본다. 진단에서 그건 최악이다.
    감사에도 남긴다 - "그때 눌러 봤더니 이랬다" 는 나중에 원인을 재구성할 유일한 단서다.
    """
    result = service.run_connection_test(
        request.app.state.outbound_client,
        request.app.state.settings,
        request.app.state.secret_provider,
    )
    record_audit_from_request(
        request,
        db,
        action="notion.connection.test",
        object_type=OBJECT_TYPE_TOKEN,
        object_id="notion",
        # 결과 어휘만 남긴다. 토큰도, 노션이 준 원문도 남기지 않는다.
        after={
            "ok": result["ok"],
            "tokens": {t["field"]: t["result"] for t in result["tokens"]},
            "databases": {d["key"]: d["result"] for d in result["databases"]},
        },
    )
    return result


class TokenBody(BaseModel):
    field: str
    value: str = Field(min_length=1, max_length=MAX_TOKEN_LENGTH)


@router.post("/token")
def update_notion_token(
    request: Request, payload: TokenBody, db: Session = Depends(get_db)
) -> dict:
    """토큰 파일 하나를 놓는다. 쓸 수 없는 서버면 **그렇다고 말한다.**

    운영 설치에서 못 쓰는 것이 정상이다(systemd `ProtectSystem=strict`). 그 경우
    `secret_dir_not_writable` 로 409 를 주고, 화면은 그 대신 무엇을 해야 하는지 말한다
    (`GET /api/admin/notion` 의 `token.manual_instruction`).
    """
    settings = request.app.state.settings
    known = {field for field, _label in service.TOKEN_REFS}
    if payload.field not in known:
        raise ValidationAppError("알 수 없는 토큰 항목입니다.")
    ref = getattr(settings, payload.field, "") or ""
    if not ref:
        raise ValidationAppError("이 서버에는 토큰 참조 이름이 설정돼 있지 않습니다.")

    secrets = request.app.state.secret_provider
    # 예외(SecretDirNotWritableError / InvalidSecretRefError)는 그대로 올린다. 둘 다
    # AppError 라 봉투가 알아서 만들어지고, 값은 어디에도 안 실린다.
    secrets.write(ref, payload.value)

    record_audit_from_request(
        request,
        db,
        action="notion.token.update",
        object_type=OBJECT_TYPE_TOKEN,
        object_id=ref,
        # 🔴 값이 아니라 사실만. 여기 값을 넣으면 감사 로그가 토큰 보관소가 된다.
        after={"configured": True},
    )
    return {"field": payload.field, "ref": ref, "configured": True}


class CreateDatabaseBody(BaseModel):
    key: str
    parent_page_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=100)
    confirm: bool = False


@router.post("/databases")
def create_notion_database(
    request: Request, payload: CreateDatabaseBody, db: Session = Depends(get_db)
) -> dict:
    """빈 워크스페이스에 데이터베이스를 만든다. **되돌리기 어렵다.**

    그래서 셋을 먼저 본다: 만들 수 있는 종류인가, 확인을 받았는가, 이미 있지는 않은가
    (`service.guard_create`). 만든 뒤에는 설정 레지스트리를 통해 id 를 저장한다 - 여기서
    직접 행을 쓰면 검증과 버전 이력을 건너뛴다.
    """
    from app.notion_console import probe_notion as probe
    from app.settings.service import apply_setting

    settings = request.app.state.settings
    spec = service.guard_create(
        payload.key, settings, _effective(request, db), confirm=payload.confirm
    )
    token_ref = getattr(settings, spec.token_ref_field, "") or ""
    result = probe.create_database(
        request.app.state.outbound_client,
        settings,
        parent_page_id=payload.parent_page_id.strip(),
        title=payload.title.strip(),
        kind=spec.kind,
        token_ref=token_ref,
    )
    record_audit_from_request(
        request,
        db,
        action="notion_database.create",
        object_type=OBJECT_TYPE_DATABASE,
        object_id=result.get("database_id") or payload.key,
        after={"key": payload.key, "result": result["result"]},
    )
    if result["result"] != probe.RESULT_OK:
        return {"created": False, **result}

    # 만들었으면 그 id 를 곧바로 설정에 넣는다. 안 넣으면 데이터베이스는 생겼는데 포털은
    # 여전히 못 보고, 운영자는 id 를 손으로 옮겨 적어야 한다 - 그 한 단계에서 오타가 난다.
    applied = apply_setting(
        db,
        request.app.state.settings_cache,
        key=spec.key,
        value=result["database_id"],
        updated_by=request.state.user.id,
        now=request.app.state.clock.now(),
    )
    record_audit_from_request(
        request,
        db,
        action="setting.update",
        object_type="app_setting",
        object_id=spec.key,
        before={"value": applied["before"]},
        after={"value": applied["after"]},
    )
    return {"created": True, **result, "apply_note": service.APPLY_NOTE}


__all__ = ["router"]
