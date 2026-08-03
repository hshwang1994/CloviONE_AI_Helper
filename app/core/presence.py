"""접속 표시(presence) 쓰기 스로틀 (PLAN Phase 4 — 스케일 심).

**문제.** 놀이 방 화면은 1.2초마다, 채팅은 그보다 조금 느리게 폴링한다. 폴링마다 멤버 행의
`last_seen` 을 갱신하면 **읽기 요청이 그대로 쓰기 요청이 된다**. SQLite 는 쓰기를 직렬화하므로
(WAL 이어도 writer 는 하나다) 사람이 늘수록 아무도 아무것도 안 하는 동안에도 쓰기 큐가 찬다.
예전 임계값은 2초였는데, 그건 1.2초 폴링에 대해 "두 번에 한 번은 쓴다"는 뜻이라 사실상
스로틀이 아니었다.

**해법.** 30초. 재접속 감지(`active=False → True`)는 **즉시** 해야 하므로 스로틀에서 뺀다 —
느려도 되는 것은 '아직 여기 있다'는 갱신뿐이다.

**왜 30초가 안전한가.** 소비하는 쪽의 임계값이 훨씬 크다:
  * 놀이의 접속자 판정 `PRESENCE_SECONDS = 90`
  * 채팅 온라인 점(계획 F)은 **2분 이상**으로 정한다
30초마다 갱신하면 90초·120초 창 안에 최소 두세 번은 찍히므로, 실제로 붙어 있는 사람이
'오프라인'으로 깜빡이지 않는다. 스로틀을 이 두 값에 가깝게 올리면 그 순간 깜빡이기 시작한다 —
이 파일과 소비자 임계값은 **함께** 봐야 한다.
"""

from __future__ import annotations

from datetime import datetime

# 여기 한 곳에서만 정의한다. 놀이·채팅이 각자 숫자를 들고 있으면 한쪽만 조정되어
# '채팅에서는 온라인인데 놀이에서는 오프라인'인 상태가 생긴다.
PRESENCE_THROTTLE_SECONDS = 30.0


def should_touch(last_seen: datetime | None, now: datetime) -> bool:
    """`last_seen` 을 다시 쓸 때가 됐는가.

    `last_seen` 이 없으면(처음 보는 멤버) 무조건 쓴다. 시계가 뒤로 간 경우(음수 경과)도
    쓴다 — 안 쓰면 시계가 정상으로 돌아올 때까지 영원히 스로틀에 걸린다.
    """
    if last_seen is None:
        return True
    elapsed = (now - last_seen).total_seconds()
    return elapsed < 0 or elapsed >= PRESENCE_THROTTLE_SECONDS
