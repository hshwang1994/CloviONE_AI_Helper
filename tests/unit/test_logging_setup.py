"""웹 프로세스의 로그가 실제로 나오는가 (Z7).

이 파일이 지키는 것은 포맷 취향이 아니라 **운영자가 새벽 3시에 볼 것이 있는가** 다.

예전에는 `app/main.py` 가 로깅을 아예 설정하지 않았다. uvicorn 의 기본 설정은 `uvicorn*`
로거만 잡고 root 는 건드리지 않으므로, `app.*` 의 `logger.info` 는 핸들러 없는 root 까지
전파된 뒤 `logging.lastResort`(레벨 WARNING) 에서 버려졌다. 그 결과 **`request_id` 를 담은
유일한 줄인 액세스 로그가 운영에서 한 번도 찍히지 않았다.**

`docs/RUNBOOK.md` 는 운영자에게 `journalctl -u …` 로 진단하라고 안내한다. 워커에는 맞고
웹에는 틀린 안내였다 — 그 비대칭을 여기서 못박는다.
"""

from __future__ import annotations

import logging

import pytest

from app.core.logging_setup import DEFAULT_FORMAT, configure_logging, resolve_level

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _restore_root():
    """root 로거를 건드리는 테스트라 원상복구한다 — 안 하면 뒤 테스트의 로그 캡처가 흔들린다."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    yield
    root.handlers, root.level = saved


def test_app_logger_is_dropped_without_configuration():
    """설정이 없으면 info 가 버려진다 — 이게 우리가 겪던 상태다.

    이 테스트가 없으면 아래 테스트가 '원래부터 잘 됐던 것'을 확인하는 셈이 된다.
    """
    root = logging.getLogger()
    root.handlers = []
    root.setLevel(logging.WARNING)  # lastResort 의 레벨

    assert not logging.getLogger("app.core.middleware").isEnabledFor(logging.INFO)


def test_configure_logging_lets_app_info_through():
    configure_logging("INFO")

    root = logging.getLogger()
    assert root.handlers, "root 에 핸들러가 붙어야 app.* 로그가 나온다"
    assert logging.getLogger("app.core.middleware").isEnabledFor(logging.INFO)


def test_access_log_line_carries_request_id(capsys):
    """액세스 로그가 request_id 를 싣고 **실제 stderr 로** 나가는가.

    middleware 가 쓰는 것과 같은 모양으로 찍어 본다 — 그 줄이 나오지 않으면
    "이 사용자의 이 요청" 을 추적할 방법이 사라진다.

    caplog 이 아니라 stderr 를 보는 이유: `dictConfig` 가 root 핸들러를 교체하므로 caplog 의
    핸들러가 떨어져 나간다. 우리가 확인하려는 것은 pytest 가 잡았는가가 아니라
    **systemd 가 가져갈 stream 에 나왔는가** 이므로 이쪽이 진짜에 가깝다.
    """
    configure_logging("INFO")  # capsys 가 sys.stderr 를 바꾼 뒤에 바인딩되도록 안에서 부른다
    logging.getLogger("app.core.middleware").info(
        "%s %s %s %.1fms request_id=%s", "GET", "/api/me", 200, 12.3, "abc123"
    )

    err = capsys.readouterr().err
    assert "request_id=abc123" in err
    assert "app.core.middleware" in err   # 어느 모듈인지
    assert "INFO" in err                  # 어느 레벨인지


def test_format_carries_logger_name_level_and_time():
    """journald 로 나간 뒤에도 어느 모듈이 무슨 말을 했는지 알 수 있어야 한다."""
    for token in ("%(asctime)s", "%(levelname)s", "%(name)s", "%(message)s"):
        assert token in DEFAULT_FORMAT


def test_level_comes_from_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert resolve_level() == "DEBUG"

    monkeypatch.setenv("LOG_LEVEL", "잘못된값")
    assert resolve_level() == "INFO"  # 오타로 로그가 꺼지면 안 된다

    monkeypatch.delenv("LOG_LEVEL")
    assert resolve_level("WARNING") == "WARNING"  # 인자가 환경변수를 이긴다


def test_configure_is_idempotent():
    """여러 번 불려도 핸들러가 쌓이지 않는다(웹·워커가 각각 부른다)."""
    configure_logging("INFO")
    first = len(logging.getLogger().handlers)
    configure_logging("INFO")
    assert len(logging.getLogger().handlers) == first
