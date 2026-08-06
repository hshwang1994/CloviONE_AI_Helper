"""웹과 특권 헬퍼 사이의 대화 규약 (§S).

## 한 연결에 한 요청

파이프라이닝도, 유지 연결도 없다. 연결을 열고 요청 한 줄을 보내고 응답 한 줄을 받고 닫는다.
프레이밍 버그가 낄 자리를 없애는 것이 목적이다 — 이 경로는 root 권한으로 이어지므로
"길이 필드를 잘못 읽어 다음 요청의 앞부분을 이번 요청으로 해석" 같은 실수가 치명적이다.

## 크기 상한을 규약에 둔다

인증서 PEM 이 가장 큰 값이라 64KB 면 충분하다. 상한이 없으면 소켓에 붙을 수 있는 누구든
헬퍼의 메모리를 채워 root 프로세스를 죽일 수 있다.
"""

from __future__ import annotations

import json

MAX_MESSAGE_BYTES = 128 * 1024
PROTOCOL_VERSION = 1


class ProtocolError(ValueError):
    """읽은 것이 우리 규약이 아니다. 내용은 로그에 남기지 않는다(개인키가 실릴 수 있다)."""


def encode_request(action: str, params: dict | None, *, request_id: str) -> bytes:
    body = json.dumps(
        {"v": PROTOCOL_VERSION, "action": action, "params": params or {}, "request_id": request_id},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(body) + 1 > MAX_MESSAGE_BYTES:
        raise ProtocolError("요청이 너무 큽니다.")
    return body + b"\n"


def decode_request(raw: bytes) -> dict:
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("요청이 너무 큽니다.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("요청을 해석할 수 없습니다.") from exc
    if not isinstance(data, dict) or data.get("v") != PROTOCOL_VERSION:
        raise ProtocolError("규약 버전이 다릅니다.")
    if not isinstance(data.get("action"), str):
        raise ProtocolError("동작 이름이 없습니다.")
    params = data.get("params")
    if params is not None and not isinstance(params, dict):
        raise ProtocolError("인자 모양이 올바르지 않습니다.")
    return data


def encode_response(payload: dict) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(body) + 1 > MAX_MESSAGE_BYTES:
        # 응답이 상한을 넘으면 통째로 버리지 않고 **줄여서라도 결과는 전한다** —
        # 실패 여부를 못 받는 것이 가장 나쁘다.
        body = json.dumps(
            {"ok": payload.get("ok", False), "detail": "결과가 너무 커서 줄였습니다.",
             "action": payload.get("action")},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
    return body + b"\n"


def decode_response(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("응답을 해석할 수 없습니다.") from exc
    if not isinstance(data, dict):
        raise ProtocolError("응답 모양이 올바르지 않습니다.")
    return data
