"""워커 싱글턴 락 (PLAN Phase 4 — 스케일 심).

**막으려는 사고.** 워커는 잡 큐를 돌리고 스케줄러 tick 을 치고 Notion 동기화를 한다. 두 개가
동시에 돌면 잡이 두 번 실행되고(같은 워크플로가 두 번 호출된다), 동기화가 서로의 prune 과
경쟁하고, 스케줄 하나가 두 번 발화한다. 실제로 이 상태가 만들어지는 경로가 있다:
`systemd restart` 도중 이전 프로세스가 아직 안 죽었을 때, 운영자가 진단하려고 손으로
`python -m app.worker_main` 을 띄웠을 때, 배포 스크립트가 유닛을 두 번 start 했을 때.

**왜 파일 리스인가.**
  * `fcntl.flock` 은 Windows 에 없다 — 개발이 Windows 라 그 자리에서 테스트할 수 없는 것은
    쓰지 않는다.
  * SQLite `BEGIN EXCLUSIVE` 를 붙들고 있으면 그 커넥션이 앱 전체의 writer 를 막는다.
  * 그래서 **PID + 만료 시각을 담은 파일**을 쓴다. 원자적 생성(O_EXCL)으로 경쟁을 해소하고,
    살아 있는 워커가 주기적으로 리스를 갱신한다. 워커가 죽으면 갱신이 멈추고, 리스가 만료된
    뒤 다음 워커가 인수한다.

**왜 PID 생존 확인에 기대지 않는가.** `os.kill(pid, 0)` 은 Windows 에서 동작이 다르고, PID 는
재사용된다(죽은 워커의 PID 를 다른 프로세스가 물려받으면 영영 인수하지 못한다). 만료 시각
하나만 보는 편이 이식성 있고 추론하기 쉽다. 대신 리스 만료(기본 120초)를 갱신 주기(30초)의
네 배로 잡아, 잠깐 느려진 워커가 자기 락을 빼앗기지 않게 한다.

**정직한 한계.** 이것은 분산 락이 아니다. 같은 파일시스템을 보는 프로세스들 사이에서만
성립한다(단일 호스트 배포라 충분하다). NFS 위에서 여러 호스트가 돈다면 이 락을 믿으면 안 된다.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("app.worker.lock")

# 리스 유효 시간. 이 시간 동안 갱신이 없으면 다른 워커가 인수한다.
DEFAULT_LEASE_SECONDS = 120.0
# 갱신 주기. 워커의 하트비트 스레드(30초)에 얹으므로 같은 값이다.
DEFAULT_RENEW_SECONDS = 30.0

LOCK_FILENAME = "worker.lock"


class WorkerLockHeld(RuntimeError):
    """다른 워커가 살아 있는 리스를 들고 있다."""


class WorkerLockError(RuntimeError):
    """리스 경쟁이 아니라 파일시스템 자체가 리스를 못 쓰게 한다(OPS-10).

    `WorkerLockHeld`/`acquire() == False` 와 다르다 - 그 둘은 "다른 워커가 있으니 내가
    물러난다"는 정상적인 결과다. 이것은 "이 환경에서는 락 자체를 쓸 수 없다"는 뜻이라
    호출자가 조용히 넘기면 안 된다.
    """


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WorkerLock:
    """단일 워커 리스. `acquire()` → (주기적) `renew()` → `release()`.

    스레드 안전하지 않다 — 한 프로세스 안에서 한 객체만 쓴다.
    """

    def __init__(
        self,
        path: str | os.PathLike,
        *,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        owner: str | None = None,
        now_fn=_utcnow,
    ) -> None:
        self.path = Path(path)
        self.lease_seconds = float(lease_seconds)
        # owner 는 '누가 들고 있나'를 사람이 보기 위한 것이자, 우리가 여전히 주인인지
        # 확인하는 토큰이다. PID 만 쓰면 재사용된 PID 가 남의 리스를 갱신할 수 있다.
        self.owner = owner or f"{os.getpid()}@{_hostname()}"
        self._now = now_fn
        self._held = False

    # ── 조회 ────────────────────────────────────────────────────────────────
    def read(self) -> dict | None:
        """현재 리스 내용. 없거나 읽을 수 없으면 None."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 깨진 락 파일은 '아무도 없음'으로 본다. 여기서 예외를 던지면 손상된 파일
            # 하나 때문에 워커가 영영 못 뜬다.
            return None
        return data if isinstance(data, dict) else None

    def is_expired(self, data: dict | None = None) -> bool:
        data = self.read() if data is None else data
        if data is None:
            return True
        expires = data.get("expires_at")
        if not isinstance(expires, str):
            return True
        try:
            deadline = datetime.fromisoformat(expires)
        except ValueError:
            return True
        return self._now() >= deadline

    # ── 획득/갱신/해제 ──────────────────────────────────────────────────────
    def acquire(self) -> bool:
        """리스를 잡으면 True. 살아 있는 다른 리스가 있으면 False(예외를 던지지 않는다).

        경쟁 해소는 `O_CREAT|O_EXCL` 원자적 생성이 한다. 파일이 이미 있으면 만료됐는지
        보고, 만료됐을 때만 덮어쓴다.

        OPS-10: 예전엔 `os.open` 의 `FileExistsError`(= 리스 경쟁, 정상적인 일)만 잡고
        나머지 `OSError`(권한 어긋남 EACCES·디스크 가득 참 ENOSPC·입출력 오류 EIO)는
        그대로 던졌다 — `main()` 을 관통해 프로세스가 트레이스백과 함께 죽고, systemd 가
        `RestartSec=3` 로 다시 띄우고 또 같은 이유로 죽는 재시작 루프에 빠졌다. 이 서버에서
        권한 어긋남은 실제로 일어난 적이 있다(`OPS-01`, uploads 디렉터리). 리스 경쟁과
        파일시스템 고장은 서로 다른 사고이므로 구분한다 - 후자는 `WorkerLockError` 로
        올려 호출자가 "리스를 못 잡았다"(False) 가 아니라 "그 자체가 못 도는 환경이다"
        (예외)를 알 수 있게 한다.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._payload()

        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing = self.read()
            if not self.is_expired(existing):
                return False
            # 만료된 리스 인수. 여기서 두 프로세스가 동시에 덮어쓸 수 있지만, 둘 다
            # '만료된 리스를 봤다'는 뜻이고 마지막 쓰기가 이긴다. 그 뒤 verify_ownership()
            # 이 자기 것이 아님을 알아채고 진 쪽이 물러난다.
            try:
                self._write(payload)
            except OSError as exc:
                raise WorkerLockError(f"만료된 리스를 인수하려다 쓰기에 실패했다: {exc}") from exc
            if not self.verify_ownership():
                return False
            self._held = True
            logger.warning("만료된 워커 리스를 인수했다: 이전 소유자=%s", (existing or {}).get("owner"))
            return True
        except OSError as exc:
            # 리스 경쟁이 아니다 - 이 경로에서 락을 아예 못 쓴다는 뜻이라, "다른 워커가
            # 있다"(False) 처럼 조용히 넘기면 원인을 아무도 모른다.
            raise WorkerLockError(f"워커 리스 파일을 열 수 없다: {exc}") from exc
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            self._held = True
            return True

    def verify_ownership(self) -> bool:
        data = self.read()
        return bool(data) and data.get("owner") == self.owner

    def renew(self) -> bool:
        """리스 연장. 그 사이 남이 가져갔으면 False — 부르는 쪽이 물러나야 한다.

        쓰기 자체는 조건 없이 덮어쓴다(파일에 CAS가 없다). 그래서 `acquire()` 가 만료된
        리스를 인수할 때와 같은 관용을 따른다: 쓰고 나서 바로 다시 확인해, 그 찰나에 남이
        새로 썼다면 내가 방금 쓴 것과 무관하게 그 사실을 알아챈다. 쓰기 전 확인(위)만 하고
        쓴 뒤에는 확인하지 않으면, 쓰기와 확인 사이에 남이 리스를 가져가도 영영 모른다.
        """
        if not self._held:
            return False
        if not self.verify_ownership():
            self._held = False
            return False
        self._write(self._payload())
        if not self.verify_ownership():
            self._held = False
            return False
        return True

    def release(self) -> None:
        """자기 리스만 지운다. 남의 리스를 지우면 워커가 둘이 되는 창이 열린다."""
        if self._held and self.verify_ownership():
            try:
                self.path.unlink()
            except OSError:
                logger.warning("워커 락 파일을 지우지 못했다: %s", self.path)
        self._held = False

    # ── 내부 ────────────────────────────────────────────────────────────────
    def _payload(self) -> dict:
        now = self._now()
        return {
            "owner": self.owner,
            "pid": os.getpid(),
            "acquired_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self.lease_seconds)).isoformat(),
        }

    def _write(self, payload: dict) -> None:
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    def __enter__(self) -> WorkerLock:
        if not self.acquire():
            data = self.read() or {}
            raise WorkerLockHeld(
                f"다른 워커가 이미 돌고 있다(owner={data.get('owner')}). "
                f"락 파일: {self.path}"
            )
        return self

    def __exit__(self, *_exc) -> None:
        self.release()


def _hostname() -> str:
    import socket

    try:
        return socket.gethostname()
    except OSError:
        return "unknown-host"


def default_lock_path(data_dir) -> Path:
    return Path(data_dir) / LOCK_FILENAME
