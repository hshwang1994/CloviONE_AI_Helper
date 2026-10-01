"""AI 연결 주기 확인 — 배치 워커의 15분 틱 (계획 3.15, D-516).

## 하는 일

  1. 계정 연결(ChatGPT)이면 access token 이 30분 안에 끝날 때 미리 갱신한다. 사람의 요청이 갱신을 기다리지 않게 한다
  2. 갱신 토큰이 5일 안에 끝나면 관리자에게 한 번 알린다(끝나면 다시 로그인해야 한다)
  3. 정상, 확인 전, 일시 장애에서는 모델 목록을 한 번 물어 자격을 가볍게 확인한다. 키가 거절되면 막힌 상태로 바꿔
     사람이 먼저 알게 한다. 목록이 답해도 상태를 **올리지 않는다** - 일시 장애에서 정상으로 돌아오는 길은 실제 생성의
     성공(사람의 호출이나 연결 확인)뿐이다(D-539). 토큰을 쓰는 생성은 하지 않는다
  4. 일시 장애가 30분 넘게 이어지면 관리자에게 한 번 알린다
  5. 하루 지난 계정 연결 시도를 지운다

## 하지 않는 일

재로그인 필요와 인증 또는 구성 오류는 사람이 고칠 때까지 자동으로 다시 시도하지 않는다. 설정이나 키를 저장하면 지문이
바뀌어 확인 전으로 돌아간다(`app/ai/credentials/state.py`). 모델 목록이 답해도 정상이라고 적지 않는다 - 정상은 같은
설정 지문으로 실제 생성이 성공한 뒤에만 쓴다. 예전에는 일시 장애에서 목록이 답하면 정상으로 올렸다 - 목록은 되는데 생성은
안 되는 모델(이름이 바뀌었거나 권한이 없다)에서 거짓 「정상」이 섰다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from app.ai.credentials import state as state_mod
from app.ai.providers import base

logger = logging.getLogger("app.ai.health")

TICK_SECONDS = 900.0
REFRESH_AHEAD = timedelta(minutes=30)
CHECK_STATES = frozenset({state_mod.STATE_OK, state_mod.STATE_UNVERIFIED, state_mod.STATE_DEGRADED})


def run_ai_health(runtime, session_factory, *, now: datetime) -> dict:
    """한 회차. 무엇을 했는지 돌려준다(시험과 로그가 읽는다). 예외를 올리지 않는다."""
    from app.ai.credentials import oauth
    from app.ai.runtime import problems

    done: dict = {"refreshed": None, "checked": None, "warned": False, "cleaned": 0}
    try:
        with session_factory() as db:
            done["cleaned"] = oauth.cleanup(db, now=now)
            db.commit()
            config = runtime.config(db)
            method = config.method()
            if method is None or problems(config, runtime.secrets):
                return done
            if method.account:
                status = runtime.chatgpt_tokens().ensure_fresh(lead=REFRESH_AHEAD)
                done["refreshed"] = status.ok
                if not status.ok and status.kind in (base.ERROR_REAUTH, base.ERROR_CONFIG, base.ERROR_AUTH):
                    runtime.record(config, result=status.kind, code=status.code, now=now)
                done["warned"] = state_mod.warn_if_refresh_ending(
                    db, config.provider, config.auth_method, now=now,
                )
                db.commit()
            # 런타임은 상태를 제 짧은 세션으로 적는다 - 이 세션이 들고 있는 옛 값을 버리고 다시 읽는다.
            db.expire_all()
            current = runtime.status(db)["state"]
            if current in CHECK_STATES:
                listing = runtime.check_credentials(config)
                done["checked"] = listing.ok
                if not listing.ok and listing.error_kind in (base.ERROR_AUTH, base.ERROR_REAUTH, base.ERROR_CONFIG,
                                                             base.ERROR_TRANSIENT):
                    runtime.record(config, result=listing.error_kind, code=listing.error_code, now=now)
            db.expire_all()
            state_mod.notify_if_needed(db, config.provider, config.auth_method, now=now)
            db.commit()
    except Exception:  # noqa: BLE001 - 워커 루프는 어떤 경우에도 살아 있어야 한다
        logger.exception("AI 연결 주기 확인이 실패했다")
    return done


def register_ai_health_tick(worker, session_factory, runtime, *, interval: float = TICK_SECONDS):
    """배치 워커에 틱을 붙인다. `app/worker_main.py::build_batch_worker` 가 부르는 유일한 배선 지점이다."""
    last: list = [None]

    def ai_health_tick(now):
        if last[0] is not None and (now - last[0]).total_seconds() < interval:
            return
        # 시각을 먼저 찍는다 - 회차가 실패해도 매 틱마다 다시 돌며 루프를 잡아먹지 않는다.
        last[0] = now
        run_ai_health(runtime, session_factory, now=now)

    worker.tick_callbacks.append(ai_health_tick)
    return ai_health_tick
