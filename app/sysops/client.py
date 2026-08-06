"""웹에서 특권 헬퍼를 부르는 쪽 (§S).

## 헬퍼가 없는 것은 오류가 아니라 **상태**다

이 제품은 헬퍼 없이도 완전히 동작한다 — 시스템 설정만 못 바꿀 뿐이다. 개발 머신, 컨테이너,
헬퍼를 일부러 안 깐 설치가 전부 정상 상태다. 그래서 소켓이 없을 때 500 을 내지 않고
`available=False` 와 **왜 없는지**를 돌려준다. 화면은 그 사실을 그대로 말한다
(§불변 6: 없는 것을 있는 척 그리지 않는다).

반대로 "헬퍼가 없으니 조용히 성공했다고 하자" 도 절대 안 된다. 사용자는 타임존을 바꿨다고
믿고 떠나는데 아무것도 안 바뀐 상태가 된다.
"""

from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass

from app.sysops.protocol import (
    MAX_MESSAGE_BYTES,
    ProtocolError,
    decode_response,
    encode_request,
)

DEFAULT_SOCKET_PATH = "/run/clovirone-web-assistant/privhelper.sock"
DEFAULT_TIMEOUT_SECONDS = 90

STATUS_OK = "ok"
STATUS_NOT_INSTALLED = "not_installed"
STATUS_UNREACHABLE = "unreachable"

_AF_UNIX = getattr(socket, "AF_UNIX", None)


@dataclass(frozen=True)
class HelperReply:
    available: bool
    status: str
    ok: bool
    detail: str
    data: dict
    changed: bool = False
    rolled_back: bool = False

    @classmethod
    def unavailable(cls, status: str, detail: str) -> HelperReply:
        return cls(available=False, status=status, ok=False, detail=detail, data={})


class SysopsClient:
    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH,
                 *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._path = socket_path
        self._timeout = timeout

    @property
    def socket_path(self) -> str:
        return self._path

    def call(self, action: str, params: dict | None = None) -> HelperReply:
        if _AF_UNIX is None:
            # Windows 개발 머신. 조용히 실패하지 말고 이유를 말한다.
            return HelperReply.unavailable(
                STATUS_NOT_INSTALLED, "이 운영체제에서는 시스템 설정 기능을 쓸 수 없습니다."
            )
        request_id = uuid.uuid4().hex
        try:
            payload = encode_request(action, params, request_id=request_id)
        except ProtocolError as exc:
            return HelperReply.unavailable(STATUS_UNREACHABLE, str(exc))

        conn = socket.socket(_AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(self._timeout)
        try:
            conn.connect(self._path)
            conn.sendall(payload)
            # 헬퍼는 응답 한 줄을 보내고 닫는다. 상한을 넘으면 읽기를 멈춘다 —
            # 상대가 끝없이 보내면 웹 워커 하나가 그대로 묶인다.
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if b"\n" in chunk or total > MAX_MESSAGE_BYTES:
                    break
            raw = b"".join(chunks).split(b"\n", 1)[0]
        except FileNotFoundError:
            return HelperReply.unavailable(
                STATUS_NOT_INSTALLED,
                "시스템 설정 도우미가 설치되어 있지 않습니다(clovirone-privhelper).",
            )
        except (ConnectionRefusedError, PermissionError) as exc:
            return HelperReply.unavailable(
                STATUS_UNREACHABLE, f"시스템 설정 도우미에 연결하지 못했습니다: {exc.__class__.__name__}"
            )
        except (TimeoutError, socket.timeout):
            return HelperReply.unavailable(
                STATUS_UNREACHABLE, f"시스템 설정 도우미가 {self._timeout}초 안에 답하지 않았습니다."
            )
        except OSError as exc:
            return HelperReply.unavailable(
                STATUS_UNREACHABLE, f"시스템 설정 도우미와 통신하지 못했습니다: {exc.__class__.__name__}"
            )
        finally:
            conn.close()

        if not raw:
            return HelperReply.unavailable(
                STATUS_UNREACHABLE, "시스템 설정 도우미가 빈 응답을 보냈습니다."
            )
        try:
            data = decode_response(raw)
        except ProtocolError as exc:
            return HelperReply.unavailable(STATUS_UNREACHABLE, str(exc))

        return HelperReply(
            available=True,
            status=STATUS_OK,
            ok=bool(data.get("ok")),
            detail=str(data.get("detail") or ""),
            data=data.get("data") if isinstance(data.get("data"), dict) else {},
            changed=bool(data.get("changed")),
            rolled_back=bool(data.get("rolled_back")),
        )

    def probe(self) -> HelperReply:
        """화면이 "쓸 수 있는가" 를 물을 때. 읽기 전용 액션이라 부작용이 없다."""
        return self.call("system.info")
