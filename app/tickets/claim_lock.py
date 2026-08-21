"""미할당 티켓을 **둘이 동시에 잡는 것**을 막는다 (Z1).

## 무엇이 잘못됐나

`claim_ticket` 은 담당자를 읽고 → Notion 에 쓴다. 그 사이에 **왕복이 두 번(0.5~3초)** 들어간다.
두 사람이 트리아지 화면에서 같은 티켓을 거의 동시에 누르면:

    A: 담당자를 읽는다 -> []          B: 담당자를 읽는다 -> []
    A: [A] 로 쓴다                    B: [B] 로 쓴다      <- A 를 덮어쓴다
    A: "배정됐습니다"                  B: "배정됐습니다"    <- **둘 다 성공 토스트**

A 는 자기 티켓이라고 믿고 일을 시작하는데 실제 담당자는 B 다. 아무 오류도 안 난다.
회의 중 트리아지에서 실제로 자주 일어나는 모양이다.

## 잠금은 **DB 가** 들고 있다 (D-192)

예전에는 `threading.Lock()` 이었다. 그건 한 프로세스 안에서만 성립하므로 두 가지를 못 막았다:

  * `--workers` 를 올리면 잠금이 N벌이 되어 **아무것도 막지 못한다** — 그래서 못 올렸다.
  * 웹과 워커는 원래 다른 프로세스라, 워커가 같은 티켓을 건드리는 경로는 **처음부터**
    이 잠금 밖이었다(옛 주석이 그 구멍을 적어 두고 있었다).

`pg_advisory_xact_lock` 은 DB 가 들고 있으므로 둘 다 닫힌다. 트랜잭션이 끝나면 자동으로
풀려서, 해제를 빠뜨려 잠금이 영원히 남는 경로 자체가 없다.

## 못 막는 것 (알고 두는 한계)

Notion 에서 **직접** 담당자를 바꾸는 경우는 못 막는다. Notion REST 에 조건부 갱신(CAS)이
없어서 어떤 방법으로도 못 막는다. 여기서 닫는 것은 **포털 안의 경합**이고, 사용자가 겪는
경합의 대부분이 그것이다.
"""

from __future__ import annotations

from app.core.advisory_lock import NS_TICKET_CLAIM, try_lock
from app.core.errors import AppError


class ClaimInProgressError(AppError):
    status_code = 409
    code = "claim_in_progress"
    default_message = "다른 사람이 지금 이 티켓을 배정하고 있습니다. 잠시 후 다시 시도해 주세요."


class claim_guard:
    """이 티켓의 배정을 한 번에 한 사람만 진행하게 한다.

    **기다리지 않는다.** 이미 누가 진행 중이면 곧바로 409 다. 기다리게 하면 Notion 이 느린 날
    요청이 줄줄이 쌓여 워커가 잠기고, 사용자는 그냥 멈춘 화면을 본다. "지금은 안 된다" 를
    빨리 말해 주는 편이 낫다.

    `db` 는 **어느 엔진에 붙을지** 알아내는 데에만 쓴다 — 잠금은 그 세션이 아니라 **별도 연결**에 걸린다. 요청 세션에 걸면
    배정 도중 누가 `db.commit()` 을 부르는 순간 잠금이 조용히 풀린다
    (`app/core/advisory_lock.py` 모듈 docstring).
    """

    def __init__(self, db, page_id: str) -> None:
        self._cm = try_lock(db, NS_TICKET_CLAIM, str(page_id))

    def __enter__(self) -> "claim_guard":
        if not self._cm.__enter__():
            self._cm.__exit__(None, None, None)
            raise ClaimInProgressError()
        return self

    def __exit__(self, *exc) -> None:
        self._cm.__exit__(*exc)
