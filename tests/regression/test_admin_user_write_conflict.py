"""사용자 관리 쓰기 경로가 경합을 **분류해서** 내보낸다 — F-0100 을 닫는다 (S18).

## 이 Finding 이 무엇이었나

W0 이 실사용 중 `POST /api/admin/users/{id}/archive` 10건 중 1건에서 500 을 받았다
(`request_id=940f783ff360927055a94bafa26fa400`). 원인은 SQLite 의 `database is locked` 였고,
`app/users/service.py` 가 그때의 재시도 계약(`is_write_conflict`)을 한 번도 안 쓰는 유일한
쓰기 모듈이라는 것이 진단이었다. 관리자에게는 «Internal server error» 만 보였다 — 다시 하면
되는 일인지 아닌지도 알 수 없는 문장이다.

## 지금 무엇이 달라졌나

전제 두 개가 바뀌었다.

* **SQLite 가 없다** (S2·S14). `database is locked` 라는 상태 자체가 이 제품에 없다.
  PostgreSQL 에서 「다시 하면 되는 실패」는 SQLSTATE `40001`·`40P01`·`55P03` 이고,
  판정은 메시지가 아니라 그 코드로 한다(D-191).
* **분류가 한 곳으로 올라갔다** (D-75 · `app/core/deps.py::get_db`). 요청 끝 커밋이
  직렬화 경합으로 실패하면 원시 500 이 아니라 `WriteUnavailableError`(503)로 나간다.

그래서 F-0100 이 요구한 계약 — *«재시도 뒤 200 이거나, 끝내 실패하면 「잠시 후 다시」로
분류된 오류다. 분류되지 않은 500 은 어느 쪽도 아니다»* — 은 모듈마다 재시도를 손으로
붙여야 성립하는 것이 아니게 됐다.

## 그래서 여기서 무엇을 증명하나

읽어서 «그럴 것이다» 라고 적지 않는다. 사용자 관리의 **쓰기 경로 다섯**을 실제로 불러서
확인한다: 요청 끝 커밋이 경합으로 실패했을 때 ① 상태코드가 503 이고 ② 본문이 재시도할 수
있는 일이라고 **말하고** ③ 경합이 아닌 실패는 503 으로 위장되지 않는다.
세 번째가 반례다 — 그것이 없으면 「전부 503 으로 감싼다」도 이 시험을 통과한다.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as OrmSession

from tests.fakes.pgerrors import io_error, serialization_failure

pytestmark = pytest.mark.integration


def _called_from_get_db() -> bool:
    """지금 커밋을 부른 것이 `get_db` 의 **요청 끝 커밋**인가.

    세션 객체로는 구별할 수 없다 — 로그인·rate limit 도 같은 팩토리의 `Session` 이다.
    dirty 목록으로도 구별할 수 없다: 핸들러가 이미 `db.flush()` 를 부르고 나면 그 행은
    dirty 에서 빠져 있다(첫 시도가 여기서 헛돌았다 — 주입한 고장이 한 번도 안 터졌고
    시험은 «200 이 나왔다» 로 실패했다). 스택을 본다.
    """
    import inspect

    return any(
        frame.filename.replace("\\", "/").endswith("app/core/deps.py")
        and frame.function == "get_db"
        for frame in inspect.stack()[:12]
    )


def _patch_commit(monkeypatch, exc_factory) -> None:
    """요청 **끝** 커밋만 실패시킨다.

    `get_db` 는 핸들러가 성공적으로 반환한 뒤 자기 커밋을 부른다 — 실제 경합이 가장 자주
    나는 자리이고, D-75 가 분류를 넣은 자리도 거기다. 다른 커밋까지 무조건 실패시키면
    주입한 고장이 시험 대상이 아니라 로그인·리미터에서 터진다.
    """
    original = OrmSession.commit

    def flaky(self, *a, **kw):
        if _called_from_get_db():
            raise exc_factory()
        return original(self, *a, **kw)

    monkeypatch.setattr(OrmSession, "commit", flaky)


def _target(client, csrf, make_user):
    victim = make_user(email="archive-target@goodmit.co.kr", role="user")
    return victim.id


# F-0100 이 «전부 같은 경로» 라고 이름으로 지목한 것들이다.
WRITE_PATHS = (
    ("보관", "POST", "/api/admin/users/{id}/archive", {}),
    ("복구", "POST", "/api/admin/users/{id}/unarchive", {}),
    ("비활성화", "POST", "/api/admin/users/{id}/disable", {}),
    ("활성화", "POST", "/api/admin/users/{id}/enable", {}),
    ("잠금 해제", "POST", "/api/admin/users/{id}/unlock", {}),
    ("역할 변경", "PATCH", "/api/admin/users/{id}", {"role": "operator"}),
)


@pytest.mark.parametrize(("label", "method", "path", "body"), WRITE_PATHS)
def test_write_conflict_becomes_a_classified_503(
    client, login_as, make_user, monkeypatch, label, method, path, body
):
    """경합은 «잠시 후 다시» 로 분류돼 나간다 — 원시 500 이 아니다."""
    csrf = login_as("system_admin")
    uid = _target(client, csrf, make_user)

    _patch_commit(monkeypatch, lambda: serialization_failure("UPDATE users SET ..."))
    res = client.request(method, path.format(id=uid), json=body,
                         headers={"X-CSRF-Token": csrf})

    assert res.status_code == 503, "%s: %s %s" % (label, res.status_code, res.text[:400])
    # 상태코드만으로는 부족하다 — 관리자가 읽는 것은 본문이다.
    payload = res.json()
    message = str(payload.get("detail") or payload.get("message") or payload)
    assert "다시" in message, "%s: 재시도할 수 있는 일이라고 말하지 않는다 — %r" % (label, message)


def test_a_non_conflict_failure_is_not_disguised_as_retryable(
    client, login_as, make_user, monkeypatch
):
    """**반례.** 경합이 아닌 실패까지 503 으로 감싸면 이 검사는 아무것도 증명하지 않는다.

    디스크 오류(`58030 io_error`)는 다시 해도 같은 결과다. 「잠시 후 다시」로 포장하면
    관리자는 계속 재시도하고, 진짜 원인은 아무 데도 안 남는다.
    """
    csrf = login_as("system_admin")
    uid = _target(client, csrf, make_user)

    _patch_commit(monkeypatch, lambda: io_error("UPDATE users SET ..."))
    res = client.post("/api/admin/users/%s/archive" % uid, json={},
                      headers={"X-CSRF-Token": csrf})

    assert res.status_code != 503, "경합이 아닌 실패가 «잠시 후 다시» 로 나갔다: %s" % res.text[:400]


def test_the_happy_path_still_archives(client, login_as, make_user):
    """그리고 고장을 안 주입하면 실제로 보관된다 — 위 둘이 «항상 실패» 로 통과하지 않게."""
    csrf = login_as("system_admin")
    uid = _target(client, csrf, make_user)

    res = client.post("/api/admin/users/%s/archive" % uid, json={},
                      headers={"X-CSRF-Token": csrf})
    assert res.status_code == 200, res.text[:400]

    listed = client.get("/api/admin/users")
    assert listed.status_code == 200, listed.text[:200]
    ids = [row["id"] for row in listed.json().get("items", [])]
    assert uid not in ids, "보관했는데 목록에 그대로 있다"


def test_sqlite_is_not_in_this_product_anymore():
    """F-0100 의 전제였던 `database is locked` 는 이 제품에 **있을 수 없다**.

    분류 기준이 SQLSTATE 라는 것을 계약 자체에서 확인한다 — 그래야 「메시지로 판정하던
    옛 코드가 어딘가 남아 있다」가 조용히 성립하지 않는다.
    """
    from app.core import db as core_db

    assert not hasattr(core_db, "is_write_conflict"), (
        "옛 이름이 살아 있다 — D-191 이 둘로 쪼갠 분류가 되돌아왔는지 확인해라")
    assert core_db.is_serialization_conflict(serialization_failure("x"))
    assert not core_db.is_serialization_conflict(io_error("x"))
