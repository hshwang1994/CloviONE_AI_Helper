"""폴링 엔드포인트용 ETag / 304 (PLAN Phase 4 — 스케일 심).

**무엇을 아끼는가.** 이 앱의 화면은 여러 곳에서 짧은 주기로 폴링한다(놀이 목록 3초, 휴지통
15초, 알림 배지 60초). 내용이 안 바뀌었는데도 매번 전체 JSON 을 직렬화해 내보내면, 사람이
늘어날수록 **아무 일도 일어나지 않은 시간**의 비용이 사람 수에 비례해 커진다. ETag 를 붙이면
바뀌지 않은 동안은 본문 0바이트(304)로 끝난다.

**무엇을 아끼지 못하는가 — 정직하게.** DB 조회는 그대로 돈다. ETag 는 응답 본문을 만든 뒤
비교하는 것이라 직렬화·전송만 줄인다. 조회까지 건너뛰려면 버전 카운터를 따로 들고 있어야
하는데(채팅·놀이의 `event_seq` 가 그 방식이다), 그건 테이블마다 새 상태를 만드는 일이라
여기서는 하지 않는다.

**왜 `/api/notifications` 에는 안 거는가.** 그 엔드포인트는 페이지네이션·읽음 필터·유형
필터를 받는다. 같은 URL 이라도 파라미터 조합마다 응답이 다르므로 ETag 를 URL 단위로 캐시하는
클라이언트/프록시와 어긋나기 쉽고, 무엇보다 실제로 자주 폴링되는 것은 목록이 아니라
**배지 숫자**(`unread-count`)다. 그래서 배지 쪽에만 건다.

**강한 ETag 를 쓴다.** 본문 바이트에서 직접 해시하므로 `W/` 접두사(약한 검증자)가 아니다.
같은 바이트면 같은 ETag, 한 글자만 달라도 다른 ETag — 아래 회귀 테스트가 그 두 방향을
모두 확인한다(안 그러면 "항상 304"거나 "절대 304 아님"인 헛도는 검사가 된다).
"""

from __future__ import annotations

import hashlib
import json

from fastapi import Request, Response
from fastapi.responses import JSONResponse

# 폴링 응답은 사용자마다 다르고(세션 쿠키) 브라우저가 오래 붙들면 안 된다.
# `no-cache` 는 '캐시하지 마라'가 아니라 '쓰기 전에 반드시 재검증하라'다 — ETag 와 짝이다.
POLLING_CACHE_CONTROL = "private, no-cache"


def payload_etag(payload) -> str:
    """JSON 직렬화 가능한 값 → 강한 ETag 문자열(따옴표 포함).

    `sort_keys=True` 로 직렬화한 뒤 해시한다. dict 순서가 파이썬 버전·삽입 순서에 따라
    흔들려도 같은 내용이면 같은 ETag 가 나오게 하기 위해서다(안 그러면 내용이 그대로인데도
    304 가 안 나는 날이 생긴다).
    """
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f'"{digest}"'


def _matches(header: str, etag: str) -> bool:
    """`If-None-Match` 해석. `*` 와 콤마로 이어진 목록을 모두 받는다.

    약한 비교(W/ 접두사 무시)를 쓴다 — 중간 프록시가 `W/` 를 붙여 되돌려 보내도 304 가
    나야 한다. 우리가 만드는 것은 강한 ETag 지만, **받는 쪽**은 관대해야 한다.
    """
    header = (header or "").strip()
    if not header:
        return False
    if header == "*":
        return True
    for candidate in header.split(","):
        candidate = candidate.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == etag:
            return True
    return False


def etag_json_response(request: Request, payload) -> Response:
    """페이로드를 ETag 와 함께 돌려준다. 클라이언트가 같은 값을 들고 있으면 304.

    라우트 핸들러는 sync 여야 한다(§2 불변 1) — 이 함수도 sync 다.
    """
    etag = payload_etag(payload)
    headers = {"ETag": etag, "Cache-Control": POLLING_CACHE_CONTROL}
    if _matches(request.headers.get("If-None-Match", ""), etag):
        # 304 는 본문이 **없어야** 한다. JSONResponse 로 만들면 status 만 304 이고 본문은
        # 그대로 실려 나가, 대역폭을 하나도 아끼지 못하면서 클라이언트만 헷갈리게 한다.
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=payload, headers=headers)
