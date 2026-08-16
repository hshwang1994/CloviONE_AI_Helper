"""사람이 읽는 경과 시간 문구 — 분/시간/일 자동 승급 (PA-RC-0015).

`관측(observability)`/`백업`/`프로젝트 헬스`가 각자 "마지막 성공 이후 얼마나 지났나"를
말하는데, 승급 없이 한 단위(대개 분)로만 찍으면 값이 커질수록(장애가 오래갈수록) 안 읽히는
숫자가 된다 — 정확히 가장 심각한 상황에서 가장 안 읽히는 역설이 생긴다.
"""

from __future__ import annotations

_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 60 * 60
_SECONDS_PER_DAY = 24 * 60 * 60


def format_elapsed_korean(seconds: float) -> str:
    """초 단위 경과를 "N분"/"N시간"/"N일"로 승급해 표시한다.

    경계는 겹치지 않는다(절삭/내림, 반올림하지 않음 — 기존 관용 `int(age // 60)`과 동일한
    성격): 3600초 미만은 분, 86400초 미만은 시간, 그 이상은 일. 음수(시계 오차 등)는 방어적으로
    0으로 다룬다 — 이 값은 사람에게 보여 주는 문구일 뿐 판정 로직이 아니므로, 음수를 그대로
    보여줘 혼란을 주는 것보다 "0분"이 낫다.
    """
    if seconds < 0:
        seconds = 0
    if seconds < _SECONDS_PER_HOUR:
        return f"{int(seconds // _SECONDS_PER_MINUTE)}분"
    if seconds < _SECONDS_PER_DAY:
        return f"{int(seconds // _SECONDS_PER_HOUR)}시간"
    return f"{int(seconds // _SECONDS_PER_DAY)}일"
