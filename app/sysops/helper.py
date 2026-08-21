"""root 로 도는 특권 헬퍼 데몬 (§S).

## 이 프로세스가 지키는 것

1. **부르는 사람이 누구인지 커널에게 묻는다** (`SO_PEERCRED`). 파일 권한만 믿지 않는다 —
   소켓 권한은 설치 스크립트가 잘못 쓰면 조용히 넓어지고, 그때 그 사실을 알려 줄 것이 없다.
   커널이 알려 주는 uid 는 위조할 수 없다.
2. **이름표만 받는다.** 명령 문자열은 규약에도 없다(`app/sysops/actions.py` 참조).
3. **인자를 로그에 남기지 않는다.** 인증서 개인키가 인자로 온다. 액션 이름 · 호출자 uid ·
   결과만 남긴다. 결과에 무엇을 담을지는 액션이 정한다.
4. **한 요청이 죽어도 데몬은 산다.** 예외를 잡아 실패 응답으로 바꾼다 — 죽으면 그 뒤로
   관리 화면의 시스템 기능이 통째로 사라지고, 이유는 아무 데도 안 남는다.

## 왜 웹에 sudo 를 주지 않았나

웹 유닛은 `NoNewPrivileges=true` · `ProtectSystem=strict` 로 하드닝돼 있다. sudo 를 주려면
그 하드닝을 풀어야 하고, 그러면 웹을 뚫은 사람이 곧바로 root 가 된다. 하드닝은 그대로 두고
**할 수 있는 일의 목록**을 좁힌 별도 프로세스를 두는 편이 훨씬 좁은 문이다.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.sysops import actions as action_registry
from app.sysops.protocol import (
    MAX_MESSAGE_BYTES,
    ProtocolError,
    decode_request,
    encode_response,
)
from app.core import product
from app.sysops.runner import RealRunner

logger = logging.getLogger("app.sysops.helper")

# 기본값의 정본은 app/core/product.py 다. 유닛이 Environment= 로 같은 값을 넘기므로
# 평소에는 이 기본값이 안 쓰이지만, 어긋나 있으면 유닛 없이 손으로 띄운 헬퍼가
# 아무도 안 듣는 소켓을 만든다(R13).
DEFAULT_SOCKET_PATH = product.PRIVHELPER_SOCKET
DEFAULT_BACKUP_ROOT = product.PRIVHELPER_BACKUP_ROOT
DEFAULT_AUDIT_LOG = product.PRIVHELPER_AUDIT_LOG
DEFAULT_SERVICE_USER = product.SERVICE_USER
SOCKET_MODE = 0o660
REQUEST_TIMEOUT_SECONDS = 120

_AF_UNIX = getattr(socket, "AF_UNIX", None)


def resolve_allowed_uids(service_user: str = DEFAULT_SERVICE_USER) -> set[int]:
    """root 와 서비스 계정만 부를 수 있다.

    서비스 계정이 아직 없으면 root 만 남는다 — 넓히는 방향이 아니라 **좁히는 방향**으로
    실패해야 한다. 설치가 덜 끝난 서버에서 아무나 부를 수 있게 되면 안 된다.
    """
    uids = {0}
    try:
        import pwd  # noqa: PLC0415 - Linux 에서만 있다

        uids.add(pwd.getpwnam(service_user).pw_uid)
    except (ImportError, KeyError):
        logger.warning("서비스 계정 %s 를 찾지 못했습니다. root 만 허용합니다.", service_user)
    return uids


def peer_uid(conn: socket.socket) -> int | None:
    """커널에게 상대의 uid 를 묻는다. 못 물으면 **거절**한다(모르면 안 통과)."""
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    except (OSError, AttributeError):
        return None
    _pid, uid, _gid = struct.unpack("3i", raw)
    return uid


def _audit(path: str, record: dict) -> None:
    """추가만 하는 기록. 실패해도 동작 자체를 막지는 않되 **조용히 넘기지 않는다.**"""
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.error("특권 헬퍼 감사 기록을 쓰지 못했습니다: %s", exc)


def handle_request(
    raw: bytes, *, caller_uid: int, backup_root: str, audit_log: str, runner=None, now=None,
) -> dict:
    """요청 한 건. 소켓과 분리돼 있어 테스트가 그대로 부를 수 있다."""
    stamp = now or datetime.now(timezone.utc)
    runner = runner or RealRunner()
    try:
        request = decode_request(raw)
    except ProtocolError as exc:
        _audit(audit_log, {
            "at": stamp.isoformat(), "uid": caller_uid, "action": None,
            "ok": False, "detail": str(exc),
        })
        return {"ok": False, "detail": str(exc)}

    action_name = request["action"]
    try:
        result = action_registry.execute(
            runner, action_name, request.get("params") or {},
            backup_root=backup_root, now=stamp,
        )
        payload = {
            "ok": result.ok, "action": result.action, "detail": result.detail,
            "changed": result.changed, "data": result.data, "rolled_back": result.rolled_back,
        }
    except Exception as exc:  # noqa: BLE001 - 데몬이 죽으면 안 된다
        logger.exception("특권 동작 처리 중 예외: %s", action_name)
        # 예외 문자열에 인자가 섞여 나갈 수 있으므로 **종류만** 알린다.
        payload = {
            "ok": False, "action": action_name,
            "detail": f"처리 중 오류가 발생했습니다({exc.__class__.__name__}).",
            "changed": False, "data": {}, "rolled_back": False,
        }

    # ⚠️ `params` 는 절대 기록하지 않는다 — 인증서 개인키가 들어 있다.
    _audit(audit_log, {
        "at": stamp.isoformat(), "uid": caller_uid, "action": action_name,
        "ok": payload["ok"], "changed": payload.get("changed", False),
        "rolled_back": payload.get("rolled_back", False), "detail": payload["detail"],
        "request_id": request.get("request_id"),
    })
    return payload


def _read_line(conn: socket.socket) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if b"\n" in chunk:
            break
        if total > MAX_MESSAGE_BYTES:
            raise ProtocolError("요청이 너무 큽니다.")
    return b"".join(chunks).split(b"\n", 1)[0]


def bind_socket(path: str, *, group: str = DEFAULT_SERVICE_USER) -> socket.socket:
    if _AF_UNIX is None:  # pragma: no cover - Linux 전용 데몬
        raise RuntimeError("이 운영체제에서는 특권 헬퍼를 실행할 수 없습니다.")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # 남아 있는 소켓 파일은 지운다. 안 지우면 재시작이 EADDRINUSE 로 실패하고,
    # systemd 가 재시도하다 포기해 관리 기능이 통째로 사라진다.
    target.unlink(missing_ok=True)

    server = socket.socket(_AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(target))
    os.chmod(target, SOCKET_MODE)
    try:
        import grp  # noqa: PLC0415 - Linux 에서만 있다

        os.chown(target, 0, grp.getgrnam(group).gr_gid)
    except (ImportError, KeyError, PermissionError) as exc:
        # 그룹을 못 붙이면 서비스 계정이 못 붙는다. 조용히 넘기면 "왜 안 되는지" 를
        # 아무도 모른다.
        logger.error("소켓 그룹(%s)을 설정하지 못했습니다: %s", group, exc)
    server.listen(8)
    return server


def serve(
    server: socket.socket, *, allowed_uids: set[int], backup_root: str, audit_log: str,
    max_requests: int | None = None,
) -> None:
    served = 0
    while max_requests is None or served < max_requests:
        conn, _ = server.accept()
        conn.settimeout(REQUEST_TIMEOUT_SECONDS)
        try:
            uid = peer_uid(conn)
            if uid is None or uid not in allowed_uids:
                logger.warning("허용되지 않은 호출자(uid=%s)를 거절했습니다.", uid)
                conn.sendall(encode_response({"ok": False, "detail": "허용되지 않은 호출자입니다."}))
                continue
            try:
                raw = _read_line(conn)
            except ProtocolError as exc:
                conn.sendall(encode_response({"ok": False, "detail": str(exc)}))
                continue
            payload = handle_request(
                raw, caller_uid=uid, backup_root=backup_root, audit_log=audit_log,
            )
            conn.sendall(encode_response(payload))
        except OSError as exc:
            logger.warning("연결 처리 중 오류: %s", exc)
        finally:
            conn.close()
            served += 1


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - 데몬 진입점
    parser = argparse.ArgumentParser(description="ClovirONE 특권 헬퍼")
    parser.add_argument("--socket", default=os.environ.get("CLOVIRASSIST_PRIVHELPER_SOCKET", DEFAULT_SOCKET_PATH))
    parser.add_argument("--backup-root", default=os.environ.get("CLOVIRASSIST_PRIVHELPER_BACKUPS", DEFAULT_BACKUP_ROOT))
    parser.add_argument("--audit-log", default=os.environ.get("CLOVIRASSIST_PRIVHELPER_AUDIT", DEFAULT_AUDIT_LOG))
    parser.add_argument("--service-user", default=os.environ.get("CLOVIRASSIST_SERVICE_USER", DEFAULT_SERVICE_USER))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        logger.error("특권 헬퍼는 root 로 실행해야 합니다.")
        return 1

    allowed = resolve_allowed_uids(args.service_user)
    server = bind_socket(args.socket, group=args.service_user)
    logger.info("특권 헬퍼 시작: %s (허용 uid %s, 동작 %d개)",
                args.socket, sorted(allowed), len(action_registry.list_actions()))
    try:
        serve(server, allowed_uids=allowed, backup_root=args.backup_root, audit_log=args.audit_log)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        Path(args.socket).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
