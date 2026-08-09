"""워커 싱글턴 락 (PLAN Phase 4 — 스케일 심).

막으려는 것은 "워커가 둘 도는 상태"다. 그러면 잡이 두 번 실행되고(워크플로가 두 번 호출된다),
스케줄이 두 번 발화하고, 두 동기화가 서로의 prune 과 경쟁한다.

이 검사가 헛돌지 않으려면 **양쪽 방향**을 다 봐야 한다: 둘째가 못 잡는 것뿐 아니라,
리스가 만료되면 **잡을 수 있어야** 한다(안 그러면 워커가 죽은 뒤 영영 못 뜬다 — 락이
가용성 사고로 바뀐다).
"""

from datetime import datetime, timedelta

import pytest

from app.core.worker_lock import WorkerLock, WorkerLockError, WorkerLockHeld

pytestmark = pytest.mark.unit

T0 = datetime(2026, 8, 3, 12, 0, 0)


class FakeClock:
    """리스 만료를 실제로 기다리지 않고 시험하려면 시계를 손에 쥐어야 한다."""

    def __init__(self, start=T0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds: float):
        self.now = self.now + timedelta(seconds=seconds)


def test_first_worker_acquires(tmp_path):
    lock = WorkerLock(tmp_path / "worker.lock")
    assert lock.acquire() is True
    assert lock.verify_ownership() is True


def test_second_worker_is_refused_while_the_lease_is_alive(tmp_path):
    path = tmp_path / "worker.lock"
    clock = FakeClock()
    first = WorkerLock(path, owner="first", now_fn=clock)
    second = WorkerLock(path, owner="second", now_fn=clock)

    assert first.acquire() is True
    assert second.acquire() is False, "워커가 둘 돌게 된다 — 잡이 두 번 실행된다"
    assert first.verify_ownership() is True
    assert second.verify_ownership() is False


def test_an_expired_lease_can_be_taken_over(tmp_path):
    """죽은 워커의 락 파일이 영원히 남아 새 워커가 못 뜨면, 락이 가용성 사고가 된다."""
    path = tmp_path / "worker.lock"
    clock = FakeClock()
    dead = WorkerLock(path, owner="dead", lease_seconds=120, now_fn=clock)
    assert dead.acquire() is True

    fresh = WorkerLock(path, owner="fresh", lease_seconds=120, now_fn=clock)
    clock.advance(119)
    assert fresh.acquire() is False, "아직 만료 전인데 빼앗겼다"
    clock.advance(2)  # 121초 — 만료됨
    assert fresh.acquire() is True
    assert fresh.verify_ownership() is True


def test_renew_extends_the_lease(tmp_path):
    """살아 있는 워커는 갱신으로 자기 리스를 지킨다 — 안 그러면 120초마다 스스로를 잃는다."""
    path = tmp_path / "worker.lock"
    clock = FakeClock()
    holder = WorkerLock(path, owner="holder", lease_seconds=120, now_fn=clock)
    other = WorkerLock(path, owner="other", lease_seconds=120, now_fn=clock)
    assert holder.acquire() is True

    for _ in range(5):  # 30초마다 갱신하며 150초를 버틴다
        clock.advance(30)
        assert holder.renew() is True
        assert other.acquire() is False

    assert holder.verify_ownership() is True


def test_renew_fails_after_someone_else_took_over(tmp_path):
    """리스를 빼앗긴 워커는 그 사실을 알아야 한다 — 모르면 둘이 계속 돈다."""
    path = tmp_path / "worker.lock"
    clock = FakeClock()
    stalled = WorkerLock(path, owner="stalled", lease_seconds=60, now_fn=clock)
    taker = WorkerLock(path, owner="taker", lease_seconds=60, now_fn=clock)

    assert stalled.acquire() is True
    clock.advance(61)
    assert taker.acquire() is True
    assert stalled.renew() is False, "빼앗긴 걸 모르면 워커가 둘 돈다"


def test_renew_notices_a_takeover_that_lands_right_after_its_own_write(tmp_path):
    """쓰기 직후, 다시 확인하기 전 그 찰나에 남이 파일을 덮어썼다면 갱신이 성공했다고
    믿으면 안 된다.

    `renew()` 는 쓰기 전에만 확인하고 쓴 뒤에는 확인하지 않았다 - `acquire()` 가 만료된
    리스를 인수할 때 쓰는 '쓰고 나서 바로 확인' 관용을 renew 는 안 따랐다. 그 틈에 남이
    끼어들면 다음 갱신(최대 30초 뒤)까지 자기가 리스를 잃은 걸 모른다.
    """
    import json
    from unittest import mock

    from app.core.worker_lock import WorkerLock as _WorkerLockCls

    path = tmp_path / "worker.lock"
    clock = FakeClock()
    holder = WorkerLock(path, owner="holder", lease_seconds=120, now_fn=clock)
    assert holder.acquire() is True

    orig_write = _WorkerLockCls._write

    def patched_write(self, payload):
        orig_write(self, payload)
        if self is holder:
            # 쓰기 직후, holder 가 다시 확인하기 전에 남이 끼어들어 리스를 가져간 상황.
            path.write_text(
                json.dumps(
                    {
                        "owner": "intruder",
                        "pid": 0,
                        "acquired_at": clock().isoformat(),
                        "expires_at": (clock() + timedelta(seconds=120)).isoformat(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    with mock.patch.object(_WorkerLockCls, "_write", patched_write):
        result = holder.renew()

    assert result is False, "쓰기 직후 남이 덮어쓴 걸 놓치면 리스를 잃은 걸 계속 모른다"
    assert holder._held is False


def test_release_only_removes_your_own_lease(tmp_path):
    """남의 리스를 지우면 워커가 둘이 되는 창이 열린다."""
    path = tmp_path / "worker.lock"
    clock = FakeClock()
    old = WorkerLock(path, owner="old", lease_seconds=60, now_fn=clock)
    new = WorkerLock(path, owner="new", lease_seconds=60, now_fn=clock)

    assert old.acquire() is True
    clock.advance(61)
    assert new.acquire() is True

    old.release()  # 이미 남의 것이다 — 지우면 안 된다
    assert path.exists(), "물러난 워커가 새 워커의 리스를 지웠다"
    assert new.verify_ownership() is True


def test_release_frees_the_lock_for_the_next_worker(tmp_path):
    """정상 종료 뒤에는 다음 워커가 **즉시** 뜰 수 있어야 한다 —
    안 그러면 배포 때 재시작이 리스 만료(2분)만큼 멈춘 것처럼 보인다."""
    path = tmp_path / "worker.lock"
    clock = FakeClock()
    first = WorkerLock(path, owner="first", now_fn=clock)
    assert first.acquire() is True
    first.release()
    assert not path.exists()

    second = WorkerLock(path, owner="second", now_fn=clock)
    assert second.acquire() is True


def test_context_manager_raises_when_held(tmp_path):
    path = tmp_path / "worker.lock"
    clock = FakeClock()
    holder = WorkerLock(path, owner="holder", now_fn=clock)
    holder.acquire()

    with pytest.raises(WorkerLockHeld):
        with WorkerLock(path, owner="second", now_fn=clock):
            pass


def test_a_corrupt_lock_file_does_not_wedge_the_worker(tmp_path):
    """깨진 락 파일 하나 때문에 워커가 영영 못 뜨면 안 된다."""
    path = tmp_path / "worker.lock"
    path.write_text("이건 JSON 이 아니다", encoding="utf-8")

    lock = WorkerLock(path, owner="fresh")
    assert lock.acquire() is True
    assert lock.verify_ownership() is True


def test_a_filesystem_failure_on_first_create_is_not_mistaken_for_lease_competition(tmp_path):
    """OPS-10: `os.open` 이 `FileExistsError` 가 아닌 `OSError`(권한 어긋남·디스크 가득
    참·입출력 오류)로 실패하면, 예전엔 이 예외가 그대로 위로 전파돼 `main()` 을 관통하고
    프로세스가 트레이스백과 함께 죽었다(그 시점엔 systemd 가 `RestartSec=3` 로 계속
    재시도하며 같은 이유로 또 죽는 재시작 루프였다). "다른 워커가 있다"(False 반환)와
    "이 환경에서는 락 자체를 못 쓴다"(예외)는 다른 사고라 구분한다."""
    from unittest import mock

    path = tmp_path / "worker.lock"
    lock = WorkerLock(path)

    with mock.patch("os.open", side_effect=PermissionError("EACCES")):
        with pytest.raises(WorkerLockError):
            lock.acquire()


def test_a_filesystem_failure_while_taking_over_an_expired_lease_is_not_silently_lost(tmp_path):
    """만료된 리스를 인수하는 두 번째 쓰기(`_write`)에서도 같은 구분이 필요하다 - 이
    경로는 `except FileExistsError:` 블록 안이라 첫 `os.open` 에는 안 걸린다."""
    from unittest import mock

    path = tmp_path / "worker.lock"
    clock = FakeClock()
    dead = WorkerLock(path, owner="dead", lease_seconds=60, now_fn=clock)
    assert dead.acquire() is True
    clock.advance(61)  # 만료됨

    fresh = WorkerLock(path, owner="fresh", now_fn=clock)
    with mock.patch.object(WorkerLock, "_write", side_effect=OSError("ENOSPC")):
        with pytest.raises(WorkerLockError):
            fresh.acquire()


def test_lock_file_records_who_holds_it(tmp_path):
    """운영자가 'lock 파일을 열어 누가 잡고 있나'를 볼 수 있어야 진단이 된다."""
    lock = WorkerLock(tmp_path / "worker.lock", owner="host-a:1234")
    lock.acquire()
    data = lock.read()
    assert data["owner"] == "host-a:1234"
    assert isinstance(data["pid"], int)
    assert "expires_at" in data and "acquired_at" in data
