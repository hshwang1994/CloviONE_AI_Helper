"""처리 안 된 예외가 500 으로 새지 않는 두 자리 — 본문 형식 오류와 유니크 경합.

운영 로그(2026-09-16)의 500 다섯 건은 전부 새 티켓 **만들기**에서 붙여 넣은 그림의 주소가
`cid:` 인 본문이었다. 본문 저장 경로는 `BlockError` 를 손으로 422 로 옮기고 있었는데 만들기
경로가 그 한 줄을 빠뜨렸다. 이제 `BlockError` 자체가 422 오류 계층이다.

같은 요청이 두 번 들어와 둘째가 유니크 제약에 부딪힌 것도 서버 오류가 아니라 「이미 있다」다.
단, FK · NOT NULL 같은 데이터 버그는 계속 500 이어야 한다 — 그것까지 409 로 접으면 버그가
경합처럼 보인다.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.errors import DUPLICATE_WRITE_MESSAGE, AppError, ValidationAppError, register_error_handlers
from app.knowledge import blocks


class _Orig(Exception):
    """psycopg 예외의 흉내 — `sqlstate` 와 `diag.constraint_name` 만 있으면 분류된다."""

    def __init__(self, sqlstate: str, constraint: str | None = None) -> None:
        super().__init__(f"sqlstate {sqlstate}")
        self.sqlstate = sqlstate
        self.diag = type("Diag", (), {"constraint_name": constraint, "sqlstate": sqlstate})()


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/block-error")
    def block_error():
        raise blocks.BlockError("이미지 주소가 없거나 허용하지 않는 스킴입니다.")

    @app.get("/block-error-default")
    def block_error_default():
        raise blocks.BlockError()

    @app.get("/unique")
    def unique():
        raise IntegrityError("INSERT …", {}, _Orig("23505", "uq_sprints_name"))

    @app.get("/foreign-key")
    def foreign_key():
        raise IntegrityError("INSERT …", {}, _Orig("23503", "fk_x"))

    return app


def _client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


def test_block_error_is_a_validation_app_error_and_still_a_value_error():
    err = blocks.BlockError("x")
    assert isinstance(err, ValidationAppError)
    assert isinstance(err, AppError)
    # 옛 자리가 `ValueError` 로 잡는다 — 그 이름도 계속 참이어야 한다.
    assert isinstance(err, ValueError)
    assert err.status_code == 422


def test_block_error_becomes_422_with_the_korean_sentence():
    res = _client().get("/block-error")
    assert res.status_code == 422
    body = res.json()["error"]
    assert body["code"] == "validation_error"
    assert body["message"] == "이미지 주소가 없거나 허용하지 않는 스킴입니다."


def test_block_error_without_a_message_still_speaks_korean():
    res = _client().get("/block-error-default")
    assert res.status_code == 422
    message = res.json()["error"]["message"]
    assert message == blocks.BlockError.default_message
    assert "Invalid" not in message


def test_unique_violation_at_the_boundary_is_409_not_500():
    res = _client().get("/unique")
    assert res.status_code == 409
    body = res.json()["error"]
    assert body["code"] == "conflict"
    assert body["message"] == DUPLICATE_WRITE_MESSAGE


def test_other_integrity_errors_stay_500():
    res = _client().get("/foreign-key")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "internal_error"
