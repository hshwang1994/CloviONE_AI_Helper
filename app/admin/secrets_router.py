"""비밀 값 관리 API (계획 2.3).

화면이 SMTP 비밀번호와 AI API 키를 **서버에 들어가지 않고** 넣는 길이다. 값은 들어오기만
하고 나가지 않는다 - 응답·감사·로그 어디에도 값이 없다. 화면이 받는 것은 "저장돼 있는가"
와 "언제 바꿨는가" 뿐이다.

권한은 시스템 설정과 같다(`SYSTEM_CONFIGURE`, 범위 없는 system_admin). 이 값들은 조직이 아니라
서버 한 대 전체의 자격이라 부서 범위라는 개념이 없다(`app/sysops/router.py` 머리말과 같다).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.authz.permissions import SYSTEM_CONFIGURE
from app.core.audit import record_audit_from_request
from app.core.deps import get_db, require_csrf, require_permission
from app.core.secret_slots import get_slot, user_slots
from app.core.secret_store import SecretStore

router = APIRouter(
    prefix="/api/admin/secrets",
    tags=["admin-secrets"],
    dependencies=[Depends(require_csrf), Depends(require_permission(SYSTEM_CONFIGURE))],
)

OBJECT_TYPE = "secret"


class SecretWrite(BaseModel):
    value: str


def secret_store(request: Request) -> SecretStore:
    # 앱 상태에 있으면 그것을 쓴다(테스트가 가짜 헬퍼를 꽂는 자리).
    existing = getattr(request.app.state, "secret_store", None)
    if existing is not None:
        return existing
    return SecretStore(
        request.app.state.secret_provider,
        getattr(request.app.state, "sysops_client", None),
    )


def _writable_slot(name: str):
    slot = get_slot(name)
    if not slot.user_writable:
        # 제품이 스스로 만드는 값(ChatGPT 연결 정보)은 사람이 넣지 않는다.
        from app.core.secret_slots import UnknownSecretSlotError

        raise UnknownSecretSlotError()
    return slot


def _view(store: SecretStore, name: str) -> dict:
    slot = get_slot(name)
    return {"slot": slot.name, "label": slot.label, **store.status(slot.name)}


@router.get("")
def list_secrets(request: Request):
    store = secret_store(request)
    return {"items": [_view(store, slot.name) for slot in user_slots()]}


@router.put("/{slot_name}")
def write_secret(slot_name: str, body: SecretWrite, request: Request, db: Session = Depends(get_db)):
    slot = _writable_slot(slot_name)
    store = secret_store(request)
    changed = store.write(slot.name, body.value)
    # 값은 감사에 넣지 않는다. 무엇을 언제 누가 바꿨는가만 남긴다.
    record_audit_from_request(
        request, db, action="secret.write", object_type=OBJECT_TYPE, object_id=slot.name,
        after={"changed": changed},
    )
    db.commit()
    return {**_view(store, slot.name), "changed": changed}


@router.delete("/{slot_name}")
def delete_secret(slot_name: str, request: Request, db: Session = Depends(get_db)):
    slot = _writable_slot(slot_name)
    store = secret_store(request)
    changed = store.delete(slot.name)
    record_audit_from_request(
        request, db, action="secret.delete", object_type=OBJECT_TYPE, object_id=slot.name,
        after={"changed": changed},
    )
    db.commit()
    return {**_view(store, slot.name), "changed": changed}
