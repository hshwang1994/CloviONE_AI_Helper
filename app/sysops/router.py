"""운영 콘솔의 시스템 설정 API (§S, 9-6).

## 왜 `CONSOLE_WRITE_ROLES` 가 아니라 `ROLE_SYSTEM_ADMIN` 인가

`CONSOLE_WRITE_ROLES` 에는 `admin` 이 들어 있고, 이 제품의 `admin` 은 **부서 범위로 좁혀질 수
있다**(`admin_scope="dept"`). 부서 관리자는 자기 부서 사람을 관리하는 사람이지 서버의 DNS·
호스트 이름·TLS 인증서를 바꾸는 사람이 아니다. 여기서 바뀌는 것은 조직 단위가 아니라
**서버 한 대 전체**라 범위라는 개념 자체가 없다. 그래서 범위가 없는 역할만 통과시킨다.

## 여기서도 검증하지만, **믿는 검증은 헬퍼 쪽이다**

이 라우터의 검증은 사용자에게 빠르고 친절한 오류를 주기 위한 것이다. 진짜 경계는 헬퍼
안에 있다(`app/sysops/actions.py`). 웹이 뚫렸다는 가정에서도 헬퍼가 버텨야 하므로,
웹에서 한 검증을 헬퍼가 다시 한다 - 중복이 아니라 **다른 목적**이다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import SYSTEM_ADMIN_ONLY
from app.core.deps import get_db, require_csrf, require_roles
from app.sysops.actions import list_actions
from app.sysops.client import STATUS_OK, SysopsClient

router = APIRouter(
    prefix="/api/admin/system",
    tags=["admin-system"],
    dependencies=[Depends(require_csrf), Depends(require_roles(*SYSTEM_ADMIN_ONLY))],
)

OBJECT_TYPE = "system_setting"


class ActionRequest(BaseModel):
    params: dict = {}


def _client(request: Request) -> SysopsClient:
    # 앱 상태에 있으면 그것을 쓴다(테스트가 가짜를 꽂는 자리). 없으면 기본 경로.
    existing = getattr(request.app.state, "sysops_client", None)
    return existing or SysopsClient()


@router.get("")
def system_overview(request: Request):
    """시스템 정보 + **도우미를 쓸 수 있는지**.

    도우미가 없어도 200 이다. 없다는 것은 오류가 아니라 이 서버의 상태이고, 화면은 그
    사실을 그대로 말해야 한다. 500 을 주면 화면이 "일시적 오류" 로 읽고 재시도만 반복한다.
    """
    reply = _client(request).probe()
    return {
        "available": reply.available,
        "status": reply.status,
        "detail": reply.detail,
        "info": reply.data if reply.available and reply.ok else {},
        "actions": list_actions(),
    }


@router.post("/{action_name}")
def run_action(
    action_name: str,
    body: ActionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """시스템 동작 하나를 실행한다.

    성공·실패·되돌림을 **전부 감사에 남긴다.** 실패도 남기는 이유: 인증서 교체 실패처럼
    되돌아간 시도는 나중에 "그때 무슨 일이 있었나" 를 재구성할 유일한 단서다.
    ⚠️ `body.params` 는 감사에 넣지 않는다 - 인증서 개인키가 들어 있다.
    """
    reply = _client(request).call(action_name, body.params)

    record_audit_from_request(
        request, db,
        action="system_action",
        object_type=OBJECT_TYPE,
        object_id=action_name,
        after={
            "available": reply.available,
            "ok": reply.ok,
            "changed": reply.changed,
            "rolled_back": reply.rolled_back,
            "detail": reply.detail,
        },
        result="success" if reply.ok else "failure",
    )
    db.commit()

    return {
        "available": reply.available,
        "status": reply.status,
        "ok": reply.ok,
        "changed": reply.changed,
        "rolled_back": reply.rolled_back,
        "detail": reply.detail,
        "data": reply.data if reply.status == STATUS_OK else {},
    }
