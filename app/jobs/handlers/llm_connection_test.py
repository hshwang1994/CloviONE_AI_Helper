"""llm_connection_test 잡 핸들러 - AI 연결을 워커에서 한 번 확인한다 (9-5 · 계획 3.14, D-515).

잡 이름은 예전 그대로다(큐 화면과 대화형 레인이 이 이름을 안다). 하는 일이 바뀌었다: 서버에 로그인된 명령줄 도구가
아니라 AI 런타임(`app/ai/runtime.py::AiRuntime.verify`)으로 제공자에게 아주 짧은 답을 한 번 받고, 결과를 연결 상태에
적는다. 실제 생성이 도는 경로를 그대로 지나는 것이 목적이다.

## 왜 웹이 직접 부르지 않는가

제공자 호출은 수십 초가 걸릴 수 있다. 이 저장소의 핸들러는 전부 sync 라(불변 §2-1) 그동안 요청 처리 칸 하나가
통째로 묶인다. 잡 큐가 기다림을 워커로 옮긴다.

## 결과를 어디에 담는가

성공이면 잡이 성공한다. 실패면 `PermanentJobError` 로 **재시도 없이** 끝내고, 그 메시지에 **우리가 쓴 한 문장**만
담는다(`job.last_error`). 제공자가 준 원문은 담지 않는다 - 키 이름이나 내부 주소가 섞일 수 있다.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload

logger = logging.getLogger("app.handlers.llm_connection_test")


def handle_llm_connection_test(db: Session, job: Job, ctx: WorkerContext) -> None:
    # payload 는 항상 {} 다. 손상된 payload 를 여기서 조기에 잡는다.
    parse_payload(job)
    from app.ai.runtime import runtime_for_worker

    outcome = runtime_for_worker(ctx).verify(db)
    if outcome["ok"]:
        logger.info("AI 연결 확인 성공")
        return
    logger.warning("AI 연결 확인 실패: %s", outcome["status"])
    raise PermanentJobError(outcome["message"])


__all__ = ["handle_llm_connection_test"]
