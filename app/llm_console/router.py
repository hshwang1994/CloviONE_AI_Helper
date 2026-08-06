"""LLM 관리 API (9-5).

## 왜 `SYSTEM_ADMIN_ONLY` 인가

`app/notion_console/router.py` 와 같은 근거다. 여기서 정하는 것은 **이 서버가 어떤 프로그램을
어떤 인자로 띄우는가**(실행 파일 경로, 모델, 제한 시간)이고, 그것은 조직 단위가 아니라 설치
한 벌 전체의 성질이다. `admin` 은 부서 범위로 좁혀질 수 있는 역할이라 여기 들이지 않는다.

실행 파일 경로가 특히 그렇다. 그 값은 그대로 `argv[0]` 이 된다
(`app/llm/cli_backend.py::build_argv`). `shell=False` 라 명령 주입은 안 되지만, 이 서버가
무엇을 띄울지 정하는 권한은 서버 전체를 다루는 사람의 것이다.

## 왜 설정을 여기서 저장하지 않는가

Notion 쪽과 같다. 값은 `PUT /api/admin/settings/{key}` 를 지난다 - 검증, 감사, 버전 이력,
되돌리기가 이미 거기 붙어 있다. 이 라우터는 **읽기와 연결 테스트**만 한다.

## 연결 테스트는 잡 큐로 보낸다

이유는 `app/jobs/handlers/llm_connection_test.py` 맨 위에 적어 뒀다. 요약하면 둘 다 한다:
기다림은 워커로 옮기고(잡 큐), 워커에서도 60초에서 끊는다(짧은 상한).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.audit import record_audit_from_request
from app.core.authz import SYSTEM_ADMIN_ONLY
from app.core.deps import get_db, require_csrf, require_roles
from app.core.errors import NotFoundError
from app.jobs.models import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    Job,
)
from app.jobs.repository import enqueue
from app.llm import provider
from app.llm_console import service

router = APIRouter(
    prefix="/api/admin/llm",
    tags=["admin-llm"],
    dependencies=[Depends(require_csrf), Depends(require_roles(*SYSTEM_ADMIN_ONLY))],
)


@router.get("")
def llm_overview(request: Request, db: Session = Depends(get_db)) -> dict:
    from app.settings.service import effective_settings

    return service.overview(
        request.app.state.settings,
        effective_settings(db, request.app.state.settings_cache),
    )


@router.post("/test")
def start_connection_test(request: Request, db: Session = Depends(get_db)) -> dict:
    """테스트를 큐에 넣고 **곧바로** 잡 id 를 돌려준다. 여기서 기다리지 않는다."""
    now = request.app.state.clock.now()
    job = enqueue(
        db,
        job_type=service.JOB_TYPE_TEST,
        payload={},
        now=now,
        user_id=request.state.user.id,
        # 실패해도 다시 시도하지 않는다. 로그인 안 됨, 실행 파일 없음, 꺼짐은 5초 뒤에도
        # 같은 답이라 재시도가 워커 시간만 태우고 큐 화면에 같은 실패를 세 줄 남긴다.
        max_attempts=1,
    )
    record_audit_from_request(
        request,
        db,
        action="llm.connection.test",
        object_type=service.OBJECT_TYPE,
        object_id=job.id,
        after={"queued": True},
    )
    return {
        "job_id": job.id,
        "status": job.status,
        "note": service.TEST_MODE_NOTE,
        "timeout_seconds": service.TEST_TIMEOUT_SECONDS,
    }


@router.get("/test/{job_id}")
def connection_test_result(
    request: Request, job_id: str, db: Session = Depends(get_db)
) -> dict:
    """잡 하나의 결과. 아직 안 끝났으면 **끝난 척하지 않는다.**

    큐에 있거나 도는 중이면 `result` 는 null 이다. 여기서 '아직 실패는 아니니 성공' 처럼
    보이는 값을 주면 화면이 초록불을 그리고, 그 초록불은 아무것도 확인하지 않은 것이다.
    """
    job = db.get(Job, job_id)
    if job is None or job.job_type != service.JOB_TYPE_TEST:
        raise NotFoundError("연결 테스트 기록을 찾을 수 없습니다.")

    result = None
    if job.status == STATUS_SUCCEEDED:
        result = {
            "status": provider.STATUS_OK,
            "message": service.test_message(provider.STATUS_OK),
        }
    elif job.status == STATUS_FAILED:
        # 핸들러가 담아 둔 것은 어휘 한 단어다. 모르는 단어가 와도 화면이 비지 않게
        # test_message 가 기본 문장으로 접는다.
        code = (job.last_error or "").strip() or provider.STATUS_FAILED
        result = {"status": code, "message": service.test_message(code)}
    elif job.status == STATUS_CANCELLED:
        result = {
            "status": provider.STATUS_FAILED,
            "message": "연결 테스트가 취소됐습니다.",
        }

    return {
        "job_id": job.id,
        "status": job.status,
        "pending": job.status in (STATUS_QUEUED, STATUS_RUNNING),
        "result": result,
    }


__all__ = ["router"]
