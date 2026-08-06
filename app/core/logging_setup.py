"""로깅 설정 — 웹과 워커가 같은 것을 쓴다.

**왜 이 파일이 생겼나.** 워커는 `worker_main.main()` 에서 `logging.basicConfig` 를 부르는데
**웹 프로세스는 아무것도 부르지 않았다**. uvicorn 의 기본 설정은 `uvicorn`·`uvicorn.error`·
`uvicorn.access` 로거만 잡고 **root 는 건드리지 않는다**. 그래서 `app.*` 의 로그는 핸들러가 없는
root 까지 전파된 뒤 `logging.lastResort` 로 떨어졌다 — 레벨 WARNING, 포맷은 메시지 한 줄뿐.

결과가 컸다:

  * `core/middleware.py` 의 액세스 로그는 `logger.info` 다. **`request_id` 를 담은 유일한 줄인데
    운영에서 한 번도 찍힌 적이 없다.**
  * `health`·`observability`·`search`·`core/scope`·`core/sync_prune` 의 `logger.info` 도 전부 소멸.
  * 살아남은 `logger.exception` 조차 로거명·레벨·시각 없이 맨 문자열로 journald 에 들어갔다.
  * 그런데 `docs/RUNBOOK.md` 는 운영자에게 `journalctl -u …` 로 진단하라고 안내한다 —
    워커에는 맞고 **웹에는 틀린 안내**였다.

`disable_existing_loggers=False` 이고 `uvicorn*` 로거는 재정의하지 않는다. uvicorn 은 자기
로거에 이미 핸들러를 붙이고 `propagate=False` 로 두므로, root 에 핸들러를 더해도 한 줄이 두 번
찍히지 않는다. 여기서 하는 일은 **root 에 핸들러를 붙이는 것 하나**다.
"""

from __future__ import annotations

import logging
import os
from logging.config import dictConfig

# 로거명과 레벨이 있어야 어느 모듈이 무슨 말을 했는지 알 수 있다. 시각이 있어야 journald 밖으로
# 퍼낸 뒤에도 순서를 잡을 수 있다.
DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DEFAULT_LEVEL = "INFO"


def resolve_level(explicit: str | None = None) -> str:
    """레벨 결정. 인자 > `LOG_LEVEL` 환경변수 > INFO."""
    raw = (explicit or os.environ.get("LOG_LEVEL") or DEFAULT_LEVEL).upper()
    return raw if raw in logging._nameToLevel else DEFAULT_LEVEL  # noqa: SLF001


def configure_logging(level: str | None = None) -> None:
    """root 로거에 핸들러를 붙인다. 웹(`create_app`)과 워커(`main`) 양쪽에서 부른다.

    여러 번 불려도 안전하다 — `dictConfig` 가 root 핸들러를 교체하므로 중복되지 않는다.
    """
    dictConfig(
        {
            "version": 1,
            # uvicorn 이 먼저 설정해 둔 로거를 죽이지 않는다. 죽이면 uvicorn 의 기동/오류
            # 로그가 사라져서 "서비스가 왜 안 뜨는지"를 볼 수 없다.
            "disable_existing_loggers": False,
            "formatters": {"standard": {"format": DEFAULT_FORMAT}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    # systemd 가 stderr 를 journald 로 가져간다.
                    "stream": "ext://sys.stderr",
                }
            },
            "root": {"handlers": ["console"], "level": resolve_level(level)},
        }
    )
