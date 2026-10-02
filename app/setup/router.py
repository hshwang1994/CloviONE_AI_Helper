"""최초 실행 셋업 체크리스트 API (9-3, P3).

## 왜 `CONSOLE_WRITE_ROLES` 가 아니라 `SYSTEM_ADMIN_ONLY` 인가

`app/sysops/router.py` 가 시스템 설정에 대해 적어 둔 근거가 여기에도 **그대로** 적용된다.
`CONSOLE_WRITE_ROLES` 에는 `admin` 이 들어 있고, 이 제품의 `admin` 은 부서 범위로 좁혀질 수
있다(`admin_scope="dept"`). 부서 관리자는 자기 부서 사람을 관리하는 사람이지 이 서버의
Notion 토큰이 있는지, TLS 인증서가 며칠 남았는지, 러너가 등록됐는지를 다루는 사람이 아니다.
여기 담긴 것은 조직 단위가 아니라 **설치 한 벌 전체**의 상태라 범위라는 개념 자체가 없다.
그래서 범위가 없는 역할만 통과시킨다.

덧붙여 이 응답은 "이 설치에서 무엇이 아직 비어 있는가" 를 한 화면에 모아 준다. 그건 공격
표면 지도이기도 하다 - 읽기 전용이라고 해서 넓게 열 이유가 없다.

## 쓰기는 선택 값 하나뿐이다 (D-534)

이 화면은 무엇이 남았는지 **말할 뿐** 대신 설정해 주지 않는다. 실제 변경은 이미 각자의 자리(조직, 부서, 메일, AI 연결, 연동)에
있고 거기에는 검증과 감사와 되돌리기가 붙어 있다. 여기서 바꾸는 것은 `PUT /choices/{key}` 하나 — 메일 · AI 를 「사용하지 않음」으로
두거나 TLS 를 「외부 프록시가 맡음」으로 두는 선택 값이다. 서버가 그 키 하나를 **행 잠금 안에서** 합치므로 두 관리자가 동시에 다른
키를 바꿔도 하나를 잃지 않는다(예전에는 화면이 객체 전체를 범용 설정 API 로 덮어 앞사람의 선택이 사라질 수 있었다). 감사는
`setting.update` 이고, 응답은 새 체크리스트다 - 화면은 그 값으로 바로 다시 그린다.

"다 봤음" 을 저장하는 버튼은 없다. 한 번 닫으면 다시 못 보는 마법사는 설정을 미룬 사람에게 아무 도움이 안 되고, 남은 항목은 계속
보여야 한다(과제 요구 3).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import SYSTEM_ADMIN_ONLY
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import NotFoundError, ValidationAppError
from app.setup.checklist import CHOICES_KEY, build_setup_checklist, reset_notice_cache
from app.setup.steps import CHOICE_DEFAULTS, CHOICE_VALUES

router = APIRouter(
    prefix="/api/admin/setup",
    tags=["admin-setup"],
    dependencies=[Depends(require_csrf), Depends(require_roles(*SYSTEM_ADMIN_ONLY))],
)


def _checklist(request: Request, db: Session) -> dict:
    # 다른 웹 프로세스가 방금 저장한 선택도 보이게 설정 캐시를 먼저 다시 읽는다(D-532 의 판 번호 확인과 같은 목적).
    cache = request.app.state.settings_cache
    cache.load(db)
    return build_setup_checklist(
        db,
        request.app.state.settings,
        secrets=request.app.state.secret_provider,
        cache=cache,
        gateway=getattr(request.app.state, "ai_gateway", None),
        runtime=getattr(request.app.state, "ai_runtime", None),
        sysops=getattr(request.app.state, "sysops_client", None),
    )


@router.get("/checklist")
def setup_checklist(request: Request, db: Session = Depends(get_db)) -> dict:
    """남은 셋업 항목. 전부 끝나도 200 이고 목록은 그대로 온다."""
    return _checklist(request, db)


class ChoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(max_length=16)


@router.put("/choices/{key}")
def put_choice(key: str, body: ChoiceRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    """선택 값 하나를 바꾼다 — 저장된 객체를 행 잠금 안에서 읽어 그 키만 합친다. 새 체크리스트를 돌려준다."""
    from app.settings.service import apply_setting, lock_for_merge

    if key not in CHOICE_VALUES:
        raise NotFoundError("고를 수 없는 항목입니다.")
    if body.value not in CHOICE_VALUES[key]:
        raise ValidationAppError("이 항목에서 고를 수 없는 값입니다.")
    now = request.app.state.clock.now()
    # 행을 먼저 잠그고(없으면 자리표를 넣어 잠근다) 그 뒤에 읽어 합친다 - 두 관리자가 동시에 다른 키를 바꿔도 둘 다 남는다.
    stored = lock_for_merge(db, key=CHOICES_KEY, updated_by=request.state.user.id, now=now)
    current = ({k: v for k, v in stored.items() if k in CHOICE_VALUES and v in CHOICE_VALUES[k]}
               if isinstance(stored, dict) else {})
    merged = {**CHOICE_DEFAULTS, **current, key: body.value}
    result = apply_setting(
        db, request.app.state.settings_cache, key=CHOICES_KEY, value=merged,
        updated_by=request.state.user.id, now=now,
    )
    # 범용 설정 저장과 같은 감사 모양이다(`app/settings/router.py`) - 감사 화면이 같은 방식으로 읽는다.
    record_audit_from_request(
        request, db, action="setting.update", object_type="app_setting", object_id=CHOICES_KEY,
        before={"value": result["before"]}, after={"value": result["after"]},
    )
    reset_notice_cache(getattr(request.app.state, "setup_notice_cache", None))
    return _checklist(request, db)


__all__ = ["router"]
