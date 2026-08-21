"""llm_connection_test 잡 핸들러 - AI 연결을 워커에서 한 번 확인한다 (9-5).

## 왜 웹이 직접 부르지 않는가

명령줄 도구 호출은 **수십 초**가 걸릴 수 있다. 이 저장소의 핸들러는 전부 sync 라
(불변 §2-1) 그동안 요청 처리 스레드 한 칸이 통째로 묶인다. 워커가 하나뿐인 배포에서
그 칸이 잠기면 다른 사람의 화면이
같이 느려진다. 관리자가 진단 버튼을 누른 대가를 전 직원이 치르는 모양이다.

그래서 **둘 다** 한다.

  * **잡 큐** - 기다림을 워커로 옮긴다. 재시도, 좀비 회수, 취소가 이미 그 큐에 있다.
  * **짧은 상한** - 큐에 맡겨도 무한은 아니다. `TEST_TIMEOUT_SECONDS`(60초)로 끊는다.
    설정된 타임아웃이 600초여도 테스트는 60초에서 끝난다. 통하면 몇 초 안에 오고,
    안 통하면 오래 기다려도 답은 같기 때문이다.

## 결과를 어디에 담는가

성공이면 잡이 성공한다. 실패면 `PermanentJobError` 로 **재시도 없이** 끝내고, 그 메시지에
`provider.STATUS_*` 어휘 **한 단어만** 담는다(`job.last_error`). 화면은 그 단어를 한국어
문장으로 옮긴다(`app/llm_console/service.py::test_message`).

  * 왜 재시도하지 않는가: 로그인 안 됨, 실행 파일 없음, 설정 꺼짐은 5초 뒤에 다시 해도
    같은 답이다. 재시도는 워커 시간을 태우고 큐 화면에 같은 실패를 세 줄 남긴다.
  * 왜 어휘 한 단어인가: 도구가 준 원문에는 경로와 계정 이름이 섞여 있고, 실제로 이
    저장소가 화면에서 쓰지 않기로 한 글자도 들어 있다(`app/llm/provider.py` 참조).
    우리가 쓴 문장만 화면으로 나간다.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from sqlalchemy.orm import Session

from app.jobs.exceptions import PermanentJobError
from app.jobs.models import Job
from app.jobs.worker import WorkerContext, parse_payload
from app.llm import provider
from app.llm.service import LlmService
from app.llm_console.service import TEST_BODY, TEST_TIMEOUT_SECONDS

logger = logging.getLogger("app.handlers.llm_connection_test")


def build_test_service(settings, *, backend=None, outbound=None) -> LlmService:
    """테스트 전용 서비스. 설정과 **다른 것은 타임아웃 하나**다.

    동시성은 설정 그대로 쓴다. 테스트가 슬롯을 우회하면 진짜 요약이 도는 중에 테스트가
    끼어들어 구독 한도를 함께 태운다 - 그것이 슬롯을 둔 이유다. 슬롯이 전부 차 있으면
    `busy` 가 나오고, 화면은 그것을 '지금은 확인할 수 없다' 로 말한다.
    """
    config = provider.resolve_config(settings)
    capped = min(config.timeout_seconds, TEST_TIMEOUT_SECONDS)
    return LlmService(
        replace(config, timeout_seconds=capped),
        data_dir=getattr(settings, "data_dir", "var"),
        backend=backend,
        outbound=outbound,
        max_concurrency=getattr(settings, "llm_max_concurrency", 1) or 1,
    )


def handle_llm_connection_test(db: Session, job: Job, ctx: WorkerContext) -> None:
    # payload 는 항상 {} 다. 읽어 쓰는 필드는 없지만 손상된 payload 를 여기서 조기에 잡는다.
    parse_payload(job)
    # 워커는 60초 간격으로 설정 캐시를 다시 읽고(worker_main.py::settings_cache_tick), 그
    # load 가 관리 콘솔에서 바꾼 값을 `settings` 에 얹는다(tenant_config.py::apply_overrides).
    # 여기서 다시 읽을 것은 없다.
    service = build_test_service(
        ctx.settings, backend=ctx.extras.get("llm_backend"), outbound=ctx.outbound_client
    )
    result = service.summarize(body=TEST_BODY)
    if result.ok:
        logger.info("LLM 연결 테스트 성공 (backend=%s)", result.backend)
        return
    logger.warning("LLM 연결 테스트 실패: %s", result.status)
    # 🔴 어휘 한 단어만. 도구가 준 원문은 여기에 담지 않는다.
    raise PermanentJobError(result.status)


__all__ = ["build_test_service", "handle_llm_connection_test"]
