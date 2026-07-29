"""불변 규칙 §2.1 (sync 일관성): 라우트 핸들러는 async def 여서는 안 된다.

FastAPI는 sync `def` 핸들러를 threadpool에서 실행하고, `async def` 핸들러는
이벤트 루프에서 직접 실행한다. 이 저장소는 SQLAlchemy·핸들러 모두 sync다
(§2 불변 규칙 1). async def 핸들러 안에서 Argon2·동기 SQLAlchemy를 돌리면
그 블로킹 작업이 이벤트 루프를 통째로 막는다 — 로그인 한 번이 전체 요청을 세운다.
가용성 문제이자 sync 결정론 테스트(worker/scheduler)를 깨뜨리는 원인이다.

예외로 async여야 하는 것들(예외 핸들러, 미들웨어 dispatch/ASGI __call__,
본문을 await 하는 헬퍼 의존성)은 app.routes 에 라우트 핸들러로 등록되지 않으므로
이 검사에 걸리지 않는다 — 여기서는 등록된 라우트의 endpoint 만 본다.
"""

import inspect

import pytest
from fastapi.routing import APIRoute

pytestmark = pytest.mark.security


def _async_route_handlers(app):
    offenders = []
    for route in app.routes:
        if isinstance(route, APIRoute) and inspect.iscoroutinefunction(route.endpoint):
            methods = ",".join(sorted(route.methods or []))
            offenders.append(f"{methods} {route.path} -> {route.endpoint.__qualname__}")
    return offenders


def test_no_async_route_handlers(app):
    offenders = _async_route_handlers(app)
    assert not offenders, (
        "async def 라우트 핸들러가 이벤트 루프를 막는다 (§2 불변 규칙 1 위반). "
        "sync `def` 로 바꿔라:\n  " + "\n  ".join(offenders)
    )
