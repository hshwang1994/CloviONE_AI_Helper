import pytest
from fastapi.testclient import TestClient

from app.core.errors import NotFoundError
from app.main import create_app

pytestmark = pytest.mark.integration


def test_unhandled_exception_returns_opaque_envelope(settings):
    app = create_app(settings)

    @app.get("/boom")
    def boom():
        raise RuntimeError("sensitive internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    assert "sensitive internal detail" not in r.text
    assert "Traceback" not in r.text


def test_app_error_renders_envelope(settings):
    app = create_app(settings)

    @app.get("/missing")
    def missing():
        raise NotFoundError("Ticket not found")

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/missing")
    assert r.status_code == 404
    assert r.json()["error"] == {
        "code": "not_found",
        "message": "Ticket not found",
        "request_id": r.headers["X-Request-ID"],
    }


def test_validation_error_does_not_echo_input(settings):
    from pydantic import BaseModel

    app = create_app(settings)

    class Payload(BaseModel):
        count: int

    @app.post("/typed")
    def typed(payload: Payload):
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/typed", json={"count": "secret-string-value"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert "secret-string-value" not in r.text


# PA-RC-0014: 검증 실패 문구가 Pydantic 영문 그대로("Invalid request data",
# "String should have at most …") 나가던 결함의 revert-to-verify. err["msg"]를 파싱하지 않고
# err["type"]+ctx로 만든 한국어 문구인지, 그리고 그 문구가 어느 필드(loc)를 가리키는지를 고정한다.
def test_validation_error_message_is_korean_for_string_too_long(settings):
    from pydantic import BaseModel, Field

    app = create_app(settings)

    class Payload(BaseModel):
        name: str = Field(max_length=5)

    @app.post("/pa-rc-0014-str")
    def typed_str(payload: Payload):
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/pa-rc-0014-str", json={"name": "너무너무너무 긴 이름입니다"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["message"] == "입력값을 확인해 주세요."
    detail = body["error"]["details"][0]
    assert detail["loc"][-1] == "name"
    assert detail["msg"] == "최대 5자까지 입력할 수 있습니다."
    assert "String should have at most" not in r.text
    assert "Invalid request data" not in r.text
    # 제출값을 응답에 되돌려주지 않는다(errors.py의 "never echo submitted values back" 유지).
    assert "너무너무너무 긴 이름입니다" not in r.text


def test_validation_error_message_is_korean_for_missing_field(settings):
    from pydantic import BaseModel

    app = create_app(settings)

    class Payload(BaseModel):
        required_field: str

    @app.post("/pa-rc-0014-missing")
    def typed_missing(payload: Payload):
        return {"ok": True}

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/pa-rc-0014-missing", json={})
    assert r.status_code == 422
    body = r.json()
    detail = body["error"]["details"][0]
    assert detail["loc"][-1] == "required_field"
    assert detail["msg"] == "필수 항목입니다."
    assert "Field required" not in r.text
