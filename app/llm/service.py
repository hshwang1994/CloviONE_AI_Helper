"""요약 서비스 — **워커에서만, 한 번에 하나만** (§L).

## 왜 워커에서만인가

두 가지 이유가 있고 둘 다 실제 사고다.

  * **웹에서 부르면 요청이 수십 초 잡힌다.** 이 저장소의 핸들러는 전부 sync 라(불변 §2-1)
    그동안 스레드 한 칸이 통째로 묶인다. 리포트를 여는 사람이 몇 명만 겹쳐도 포털 전체가
    느려진다.
  * **구독 한도는 사람과 공유한다.** 워커가 한도를 태우면 그 서버에서 CLI 를 쓰던 **사람이**
    막힌다. 자동화가 사람의 도구를 뺏는 모양이라, 한 번 겪으면 기능 자체를 못 믿게 된다.

## 왜 동시 실행 1개인가

같은 이유의 연장이다. 리포트를 여러 프로젝트에 대해 만들면 호출이 동시에 여러 개 나가고,
그때 한도는 순식간에 없어진다. `app/core/worker_lock.py` 의 관용을 그대로 쓴다 - PID 와
만료 시각을 담은 파일 리스, 원자적 생성(O_EXCL)으로 경쟁 해소. 새 락을 만들지 않는다.

리스 길이는 **타임아웃보다 길게** 잡는다. 짧으면 아직 도는 호출의 락을 다음 호출이
빼앗아 결국 둘이 동시에 돈다. 반대로 무한이면 프로세스가 죽었을 때 영영 못 잡는다 -
그래서 만료는 있고, 다만 한 번의 실행보다 길다.

## 정직한 한계

**'워커에서만' 은 규약이지 강제가 아니다.** 웹 코드가 이 서비스를 만들어 부르는 것을
막는 장치는 없다(그러려면 프로세스 종류를 아는 전역 상태가 필요한데, 그건 테스트를
비결정적으로 만든다). 강제되는 것은 두 가지다: **동시 실행 1개**와 **하드 타임아웃**.
그 둘이 최악(포털 전체가 LLM 을 기다린다)을 막는다.

락은 같은 파일시스템을 보는 프로세스들 사이에서만 성립한다(worker_lock.py 의 한계와 같다).

## 이 파일은 예외를 밖으로 던지지 않는다

`app/assistant/narrate.py` 와 같은 규약이다. 주간 리포트의 숫자와 목록은 LLM 과 무관하게
이미 만들어져 있다. 요약 하나 때문에 그것이 안 나가면 안 된다. 실패는 전부
`{"source": "rule", "llm_summary": None, "llm_notice": "왜 규칙 요약인지"}` 로 접힌다.

**조용히 성공한 척하지 않는다.** 로그인이 안 돼 있으면 화면이 "로그인되어 있지 않다" 고
말한다. 0 과 "없음" 과 "못 잼" 은 서로 다른 사실이다.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from app.core.worker_lock import WorkerLock
from app.llm import cli_backend, provider

logger = logging.getLogger("app.llm.service")

# 워커 락(worker.lock)과 **다른 파일**이다. 이름이 같으면 요약 한 번이 워커 전체의 리스를
# 건드려서, 요약이 도는 동안 잡 큐와 스케줄러가 멈춘다.
LOCK_FILENAME = "llm.lock"

# 리스 = 타임아웃 + 여유. 여유는 프로세스 시작과 결과 해석에 드는 시간이다.
LOCK_GRACE_SECONDS = 60

# 동시 실행 슬롯의 상한(9-5). 관리 콘솔이 이보다 큰 값을 저장하지 못한다
# (app/settings/registry.py::_llm_concurrency).
#
# 왜 이렇게 낮은가: 위 docstring 이 적어 둔 대로 **구독 한도는 이 서버에서 명령줄 도구를
# 쓰는 사람과 공유**한다. 슬롯을 늘리는 것은 성능 조절이 아니라 사람의 몫을 빼앗는 결정이라,
# 화면에서 무심코 크게 잡을 수 있는 자리가 아니다.
MAX_CONCURRENCY = 4


def _lock_path(data_dir, slot: int) -> Path:
    """슬롯 0 은 예전 이름 그대로다.

    이름을 통째로 바꾸면 업그레이드 순간 옛 이름의 살아 있는 리스를 아무도 못 보게 되고,
    그 사이 요약 두 개가 동시에 돈다. 그래서 첫 슬롯만 이름을 유지한다.
    """
    return Path(data_dir) / (LOCK_FILENAME if slot == 0 else f"llm.{slot}.lock")


def _new_lock(data_dir, slot: int, *, lease: float) -> WorkerLock:
    # 소유자를 PID 만으로 두면 **같은 프로세스의 두 번째 호출이 자기 것처럼** 보인다.
    # 워커 한 프로세스 안에서 두 갈래가 동시에 요약을 부르는 것이 바로 막으려는 상황이라,
    # 호출마다 다른 토큰을 붙인다.
    owner = f"llm:{os.getpid()}:{secrets.token_hex(4)}"
    return WorkerLock(_lock_path(data_dir, slot), lease_seconds=lease, owner=owner)


def single_run_lock(data_dir, *, timeout_seconds: int) -> WorkerLock:
    """이 저장소의 락 관용 그대로. 동시성이 1일 때의 슬롯 하나."""
    lease = cli_backend.clamp_timeout(timeout_seconds) + LOCK_GRACE_SECONDS
    return _new_lock(data_dir, 0, lease=lease)


class SlotLock:
    """슬롯 N개 중 **하나라도** 비어 있으면 잡는다. 전부 차 있으면 실패한다.

    파일 하나에 카운터를 두는 편이 우아해 보이지만, 그러려면 읽고-더하고-쓰는 사이를 막을
    또 다른 락이 필요하다. 파일 N개는 원자적 생성(O_EXCL) 하나로 경쟁이 이미 해소된다.

    **앞에서부터 시도하는 것이 의도다.** 무작위로 고르면 슬롯이 고르게 차서, 동시성을 줄인
    뒤 어느 슬롯이 아직 도는지 사람이 못 읽는다. 앞에서부터 채우면 `var/llm.lock` 하나만
    있으면 한 개가 도는 중이라는 뜻이 된다.
    """

    def __init__(self, data_dir, *, slots: int, lease_seconds: float) -> None:
        self._locks = [
            _new_lock(data_dir, slot, lease=lease_seconds) for slot in range(max(1, slots))
        ]
        self._held: WorkerLock | None = None

    def acquire(self) -> bool:
        for lock in self._locks:
            if lock.acquire():
                self._held = lock
                return True
        return False

    def release(self) -> None:
        held, self._held = self._held, None
        if held is not None:
            held.release()


def concurrency_lock(data_dir, *, timeout_seconds: int, max_concurrency: int) -> SlotLock:
    """설정된 동시성만큼의 슬롯 락. 상한은 MAX_CONCURRENCY 가 강제한다."""
    lease = cli_backend.clamp_timeout(timeout_seconds) + LOCK_GRACE_SECONDS
    slots = max(1, min(MAX_CONCURRENCY, int(max_concurrency or 1)))
    return SlotLock(data_dir, slots=slots, lease_seconds=lease)


class LlmService:
    """주간 리포트가 부르는 유일한 문. 백엔드가 무엇인지 부르는 쪽은 모른다."""

    def __init__(
        self,
        config: provider.LlmConfig,
        *,
        data_dir,
        backend=None,
        outbound=None,
        lock_factory=None,
        max_concurrency: int = 1,
    ) -> None:
        self._config = config
        self._data_dir = data_dir
        self._backend = backend
        self._outbound = outbound
        self._max_concurrency = max_concurrency
        self._lock_factory = lock_factory or (
            lambda: concurrency_lock(
                self._data_dir,
                timeout_seconds=config.timeout_seconds,
                max_concurrency=self._max_concurrency,
            )
        )

    def summarize(self, *, body: str) -> provider.LlmResult:
        """본문 → 결과. 어떤 경우에도 예외를 올리지 않는다."""
        if not self._config.enabled:
            # 꺼져 있으면 락도 잡지 않고 프로세스도 안 띄운다. 설정 안 한 설치에서
            # 리포트를 열 때마다 프로세스 실행 실패를 기다리는 일이 없어야 한다.
            return provider.failure(provider.STATUS_DISABLED, self._config.backend)

        backend = self._backend or provider.select_backend(
            self._config, outbound=self._outbound
        )
        if backend is None:
            logger.warning("알 수 없는 LLM 백엔드: %s", self._config.backend)
            return provider.failure(provider.STATUS_UNCONFIGURED, self._config.backend)

        lock = self._lock_factory()
        if not lock.acquire():
            # 예외가 아니라 값이다. 겹친 호출은 사고가 아니라 정상적인 상태다.
            logger.info("다른 LLM 요약이 진행 중이라 이번 호출은 규칙 기반으로 접는다")
            return provider.failure(provider.STATUS_BUSY, self._config.backend)

        try:
            return backend.summarize(body=body)
        except Exception:  # noqa: BLE001 - 워커 루프는 요약 하나 때문에 죽지 않는다
            logger.exception("LLM 백엔드가 예상 못 한 예외를 냈다")
            return provider.failure(provider.STATUS_FAILED, self._config.backend)
        finally:
            # 안 풀면 리스가 만료될 때까지 그 뒤 호출이 전부 규칙 요약이 된다.
            # 즉 락이 가용성 사고로 바뀐다.
            lock.release()

    def weekly_summary(self, *, body: str) -> dict:
        """주간 리포트 응답에 **그대로 합칠 수 있는** 세 칸.

        `source` 는 이미 그 응답에 있는 자리이고(app/projects/service.py), `llm_summary` 도
        자리만 있고 비어 있다. `llm_notice` 는 "왜 규칙 요약을 보고 있는가" 를 화면이 말할
        자리다 - 이유를 안 주면 화면은 침묵하고, 사용자는 LLM 이 켜져 있다고 믿는다.
        """
        return self.summarize(body=body).as_dict()


def build_service(settings, *, backend=None, outbound=None) -> LlmService:
    """설정에서 서비스 하나. 워커 부팅 지점에서 한 번 부르는 것을 전제로 한다."""
    config = provider.resolve_config(settings)
    return LlmService(
        config,
        data_dir=getattr(settings, "data_dir", "var"),
        backend=backend,
        outbound=outbound,
        # 관리 콘솔의 '동시 실행 수'(9-5). 설정 오버레이가 이 필드를 채운다
        # (app/core/tenant_config.py::apply_overrides). 없으면 1이다.
        max_concurrency=getattr(settings, "llm_max_concurrency", 1) or 1,
    )
