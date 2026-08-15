"""UB-21 — 프롬프트/정책 **생성**·**새 버전** 이 경합할 때 500이 아니라 깨끗한 결과를 준다.

`transition()`(발행 경합, UB-04)은 이미 `begin_nested()` + `is_write_conflict()` 로
보호돼 있었다(0053, migration `ux_{prompts,policies}_published_dedup`). 그런데
같은 파일의 두 이웃 - `router.py`의 `create()`(존재 확인~삽입)와 `service.py`의
`new_version_from()`(버전 번호 계산~삽입) - 은 똑같은 확인-후-삽입(check-then-insert)
모양인데 아무 보호가 없었다. 커밋은 요청 끝에 한 번뿐이라(get_db) 그 사이 창이 요청
하나만큼 넓다 - 더블클릭·폼 재제출이면 실제로 겹친다.

두 경우는 "맞는 결과"가 다르다:
  * `create()`: 같은 이름으로 두 번 생성하면 진 쪽은 **정말로 이름이 이미 있다** -
    재시도해도 같은 결론이라 깨끗한 409만 주면 된다.
  * `new_version_from()`: 같은 이름의 "새 버전"을 두 번 요청하면 진 쪽이 원하는 건
    여전히 "새 버전 하나" - 버전 번호만 다시 계산해 재시도하면 **실제로 성공**할 수
    있다. 사용자에게 409를 보여줄 이유가 없다(approvals.create_approval과 같은 관용).

두 테스트 모두 고치기 전 원본 코드에서 재현된다: 확인함(2026-08-11) - `create()`의
`db.add(row); db.flush()`와 `new_version_from()`의 동일 코드로 되돌리면 두 번째
스레드가 uq_{prompts,policies}_name_version 위반으로 **처리되지 않은 IntegrityError**
를 던져 500이 난다(`raise_server_exceptions=False`로 잡아 상태 코드로 확인).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

THREADS = 8
ADMIN_EMAIL = "admin@goodmit.co.kr"


def test_concurrent_create_same_name_never_500s(app, login_as):
    """8-way 순수 타이밍 경주로는 이 레이스가 안정적으로 안 잡혔다 - 확인함(2026-08-11):
    로그인 자체가 같은 admin 행을 두고 경합해(자체 재시도+지터, `app/auth/router.py`)
    스레드마다 완료 시각이 흩어지고, 그 결과 각 스레드의 "이름 존재 확인" SELECT 가
    서로 겹치지 않고 순차로 벌어지기 쉬웠다 - `new_version_from` 쪽 레이스(아래 테스트)는
    같은 8-way 타이밍으로도 재현됐지만, 이쪽은 8/8 모두 성공(1개 201 + 7개 409)으로
    끝나 버그를 놓쳤다(위양성 - UB-08 테스트를 처음 썼을 때와 같은 실수, 그때처럼
    바로잡는다). 결정적으로 겹치게 만들려고 `before_cursor_execute` 로 "존재 확인" SELECT
    두 개를 `threading.Barrier(2)` 에 세운다 - 둘 다 "없음"을 본 다음에야 동시에
    INSERT 로 넘어가게 강제한다.
    """
    import threading

    from sqlalchemy import event

    login_as("admin")  # 관리자 계정을 미리 만들어 둔다 — 로그인 자체의 생성 경합은 테스트 대상이 아니다.
    engine = app.state.engine
    barrier = threading.Barrier(2)
    hits = 0
    hits_lock = threading.Lock()

    def _pause_before_insert_races(conn, cursor, statement, parameters, context, executemany):
        nonlocal hits
        if "FROM prompts" not in statement or "race-create-prompt" not in str(parameters):
            return
        with hits_lock:
            hits += 1
            should_wait = hits <= 2
        if should_wait:
            barrier.wait(timeout=5)

    def attempt(_i: int) -> int:
        with TestClient(app, raise_server_exceptions=False) as c:
            # 관리자 한 명이 같은 세션에서 연타한 것처럼 같은 admin 계정으로 로그인한다 -
            # login_as가 이미 만든 세션과는 별개 쿠키(별도 TestClient)라 실제 요청처럼
            # 서로 다른 세션 토큰으로 동시에 들어간다.
            r = c.post(
                "/login", json={"email": ADMIN_EMAIL, "password": DEFAULT_TEST_PASSWORD}
            )
            assert r.status_code == 200, r.text
            token = r.json()["csrf_token"]
            resp = c.post(
                "/api/admin/prompts",
                json={"name": "race-create-prompt", "content": "v1"},
                headers={"X-CSRF-Token": token},
            )
            return resp.status_code

    event.listen(engine, "before_cursor_execute", _pause_before_insert_races)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(attempt, range(2)))
    finally:
        event.remove(engine, "before_cursor_execute", _pause_before_insert_races)

    assert codes.count(201) == 1, f"정확히 하나만 성공해야 한다: {codes}"
    assert all(c in (201, 409) for c in codes), f"500이 섞였다(처리 안 된 경합): {codes}"

    # 경합 뒤에도 그 이름으로 다시 만들려 하면 평범한 409(순차 경로) — 크래시 안 남는다.
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post(
            "/login", json={"email": ADMIN_EMAIL, "password": DEFAULT_TEST_PASSWORD}
        )
        token = r.json()["csrf_token"]
        again = c.post(
            "/api/admin/prompts",
            json={"name": "race-create-prompt", "content": "v2"},
            headers={"X-CSRF-Token": token},
        )
        assert again.status_code == 409


def test_concurrent_new_version_all_succeed_with_distinct_versions(app, login_as, db):
    from app.prompts.models import STATUS_DRAFT, Prompt

    login_as("admin")  # 관리자 계정을 미리 만들어 둔다 — 로그인 자체의 생성 경합은 테스트 대상이 아니다.
    base = Prompt(name="race-new-version-prompt", version=1, content="v1", status=STATUS_DRAFT)
    db.add(base)
    db.commit()
    row_id = base.id

    def attempt(_i: int) -> tuple[int, int | None]:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/login", json={"email": ADMIN_EMAIL, "password": DEFAULT_TEST_PASSWORD}
            )
            assert r.status_code == 200, r.text
            token = r.json()["csrf_token"]
            resp = c.post(
                f"/api/admin/prompts/{row_id}/new-version",
                headers={"X-CSRF-Token": token},
            )
            version = resp.json()["item"]["version"] if resp.status_code == 200 else None
            return resp.status_code, version

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(attempt, range(THREADS)))

    codes = [c for c, _v in results]
    versions = [v for _c, v in results if v is not None]
    # UB-21의 핵심 주장: "새 버전"은 재시도로 실제로 풀리는 경합이라 전부 성공해야 한다
    # (409로 물러나는 게 아니라) — 그리고 새로 만든 버전 번호는 서로 겹치지 않아야 한다.
    assert all(c == 200 for c in codes), f"500/409 없이 전부 성공해야 한다: {codes}"
    assert len(set(versions)) == len(versions), f"버전 번호가 겹쳤다: {versions}"


def test_new_version_from_gives_up_cleanly_after_exhausting_retries(db, monkeypatch):
    """PA-RC-0008 — 예산을 다 쓰면 raw 500(처리 안 된 IntegrityError)이 아니라 깨끗한
    409여야 한다. 실 스레드 타이밍 경주 대신 `next_version()`이 항상 이미 있는 버전
    번호(1)를 돌려주게 고정해 **매 시도**가 `uq_prompts_name_version`과 결정적으로
    부딪히게 만든다 — 8-way 타이밍 경주보다 재현이 확실하다(예전엔 예산 5·지터 없이
    이 경로가 처리 안 된 `IntegrityError`를 그대로 500으로 흘렸다).
    """
    from app.core.errors import ConflictError
    from app.prompts import service as svc
    from app.prompts.models import STATUS_DRAFT, Prompt

    base = Prompt(name="exhaust-prompt", version=1, content="v1", status=STATUS_DRAFT)
    db.add(base)
    db.commit()

    attempts = []

    def _always_colliding_version(_db, _model, _name):
        attempts.append(1)
        return 1

    monkeypatch.setattr(svc, "next_version", _always_colliding_version)
    monkeypatch.setattr(svc.time, "sleep", lambda _seconds: None)  # 재시도 횟수/결과만 본다 — 실제로 자면 느려진다

    with pytest.raises(ConflictError):
        svc.new_version_from(db, base, created_by=None)
    assert len(attempts) == svc._NEW_VERSION_RETRIES, f"정확히 예산만큼 시도해야 한다: {attempts}"


def test_new_version_from_retry_budget_is_the_shared_default():
    """PA-RC-0008 — 새 공용 기본값(10, auth.py 로그인 실측)을 실제로 쓰는지 못박는다
    (예전엔 지터 없이 5회뿐이라 8-way 경합에서 40% 확률로 500이 났다)."""
    from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES
    from app.prompts import service as svc

    assert svc._NEW_VERSION_RETRIES == DEFAULT_WRITE_CONFLICT_RETRIES == 10
