import pytest

# 이 파일은 `create_app(settings, …)` 을 **직접** 부른다 — 시험 하네스의 바인드를
# 안 받으므로 `settings.database_url` 로 자기 엔진을 만들고 **진짜로 커밋한다**.
# 공유 DB 계층에서는 그 커밋이 되감기 밖에 있어 다음 시험으로 샌다(실제로 같은
# 이메일로 두 번째 `create_user` 가 유니크 위반으로 죽었다). 그래서 전용 DB 를 받는다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]


def test_healthz(client):
    # 여기서 기다리는 값은 **제품이 배포되는 기본값**이다 — S14 부터 티켓 정본은 자체 DB
    # (`native`) 이고, 이 한 줄이 배포된 기본 소스를 밖에서 읽을 수 있는 유일한 자리다.
    # 시험 세계만 옛 값을 적어 두면 되돌리기 창을 닫는 날 아무도 그 사실을 모른다.
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "ticket_source": "native"}


def test_healthz_names_the_repository_that_is_actually_wired(client):
    """`/healthz` 가 말하는 이름이 **실제로 배선된 저장소**와 같은가.

    예전에는 이 값이 설정에서 왔고, 그래서 이 자리의 시험은 "기본값이 아닌 값을 주입해도
    따라오는가" 였다. 그 스위치는 사라졌다 — 구현이 하나뿐이라 고를 것이 없다. 그래도
    문자열 하나를 손으로 적어 두면 배선을 바꾸는 날 이 응답만 옛 이름으로 남고, 밖에서
    이 키를 지켜보는 감시 도구는 아무 일도 없다고 말한다. 그래서 응답이 배선기의 상수와
    같은지, 그리고 그 배선기가 실제로 자체 DB 구현을 만드는지 함께 본다.
    """
    from app.core.source_registry import SOURCE_NATIVE
    from app.tickets.repository_native import NativeTicketRepository

    reported = client.get("/healthz").json()["ticket_source"]
    assert reported == SOURCE_NATIVE, f"응답과 배선기의 이름이 갈렸다: {reported}"
    wired = client.app.state.repositories.tickets
    assert type(wired) is NativeTicketRepository, (
        f"이름은 native 라고 말하는데 배선된 구현은 다른 것이다: {type(wired).__name__}"
    )


def test_readyz_with_working_db(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


# OPS-03: uploads 디렉터리가 쓰기 불가(소유권/권한 드리프트, OPS-01 실사고와 같은 유형)여도
# 예전엔 이를 관측할 방법이 전혀 없었다 — 디스크 용량 확인(_disk_usage)만으로는 안 보인다.
def test_readyz_reports_unready_when_uploads_not_writable(client, monkeypatch):
    from pathlib import Path

    def _boom(self, *a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", _boom)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "unready", "reason": "uploads_not_writable"}


def test_dashboard_reports_uploads_writable(client, login_as):
    csrf = login_as("system_admin")
    r = client.get("/api/admin/dashboard", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["uploads_writable"] is True


def test_dashboard_reports_uploads_not_writable(client, login_as, monkeypatch):
    from pathlib import Path

    csrf = login_as("system_admin")

    def _boom(self, *a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", _boom)
    r = client.get("/api/admin/dashboard", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["uploads_writable"] is False


def test_readyz_reports_unready_when_db_is_broken(settings):
    from fastapi.testclient import TestClient

    from app.core.db import EngineOptions, make_engine, make_session_factory
    from app.main import create_app

    app = create_app(settings)
    # 붙을 수 없는 DB 를 가리킨다. **주소 자체는 유효해야 한다** — `make_engine` 이
    # PostgreSQL 이 아닌 주소를 아예 거부하므로(D-187), 예전처럼 `sqlite:///Z:/…` 를 쓰면
    # 「DB 가 고장났다」가 아니라 「설정이 틀렸다」를 시험하게 된다. 그 둘은 다른 사고다.
    #
    # 포트 1은 특권 포트라 아무도 안 듣는다 — 연결이 즉시 거부된다.
    broken = make_engine(
        "postgresql://nobody@127.0.0.1:1/definitely_missing",
        EngineOptions(pool_pre_ping=False),
    )
    app.state.session_factory = make_session_factory(broken)

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "unready"}
