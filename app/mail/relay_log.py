"""로컬 릴레이의 바깥 전달 결과 읽기 (계획 M7, D-551 · D-555).

앱이 로컬 릴레이에 넘기면 받는 쪽 서버가 받았는지는 릴레이만 안다. 릴레이(Postfix)는 그 결과를 큐(`postqueue -j`)와 로그 줄로
남긴다. 이 모듈은 그 둘을 **순수 함수**로 읽는다 — 특권 헬퍼가 로그 원문 대신 큐 id 별 요약만 돌려주고(`mailrelay.log`), 워커의
추적(`app/mail/relay_tracking.py`)이 그 요약을 발송 행의 바깥 결과로 옮긴다.

로그 줄 모양(실제 Postfix 3.8, `dist/qa/relay-container/postfix.log` 견본):

    C87DBF6954: to=<a@b>, relay=mx.b[192.0.2.1]:25, delay=0.1, delays=…, dsn=2.0.0, status=sent (250 2.0.0 OK …)
    84A7BF6954: to=<a@b>, relay=none, delay=0.09, delays=…, dsn=4.4.1, status=deferred (connect to …:25: Connection refused)
    6D980F6955: to=<a@b>, relay=none, …, dsn=5.4.4, status=bounced (Host or domain name not found. Name service error …)

서버가 말한 문장(`said`)은 300자까지만 남기고, 화면에서는 기술 정보 안에만 보인다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from app.mail.labels import (
    REMOTE_BOUNCED,
    REMOTE_DEFERRED,
    REMOTE_DELIVERED,
    REMOTE_EXPIRED,
    REMOTE_QUEUED,
    REMOTE_UNKNOWN,
)

SAID_MAX = 300
QUEUE_LIMIT = 500
# 짧은 큐 id(16진수 6~12자, 기본)와 긴 큐 id(`enable_long_queue_ids`) 둘 다.
QUEUE_ID_RE = re.compile(r"^[0-9A-Za-z]{6,20}$")
_QUEUED_AS = re.compile(r"queued as ([0-9A-Za-z]{6,20})\b")
_LINE = re.compile(r"(?:^|\s)(?P<qid>[0-9A-Za-z]{6,20}): to=<(?P<to>[^>]*)>,(?P<rest>.*)$")
_STATUS = re.compile(r"\bstatus=(?P<status>sent|deferred|bounced|expired)\b(?P<tail>.*)$")
_DSN = re.compile(r"\bdsn=(?P<dsn>\d\.\d{1,3}\.\d{1,3})\b")
_RELAY = re.compile(r"\brelay=(?P<relay>[^,\s]+)")
_REMOVED = re.compile(r"(?:^|\s)(?P<qid>[0-9A-Za-z]{6,20}): removed\s*$")

STAGE_DNS = "dns"
STAGE_CONNECT = "connect"
STAGE_TLS = "tls"
STAGE_REJECTED = "rejected"
STAGE_TEMPORARY = "temporary"
STAGE_EXPIRED = "expired"

_STATUS_MAP = {
    "sent": REMOTE_DELIVERED,
    "deferred": REMOTE_DEFERRED,
    "bounced": REMOTE_BOUNCED,
    "expired": REMOTE_EXPIRED,
}

#: 바깥 전달이 막힌 단계 → 사람이 읽는 한 문장(화면의 「바깥 전달」 줄과 발송 기록 상세).
STAGE_SENTENCES = {
    STAGE_DNS: "받는 쪽 메일 서버를 DNS 에서 찾지 못했습니다.",
    STAGE_CONNECT: "받는 쪽 메일 서버(25번)에 연결하지 못했습니다.",
    STAGE_TLS: "받는 쪽 메일 서버와 보안 연결을 맺지 못했습니다.",
    STAGE_REJECTED: "받는 쪽 메일 서버가 메일을 거부했습니다.",
    STAGE_TEMPORARY: "받는 쪽 메일 서버가 잠시 뒤에 다시 보내라고 답했습니다.",
    STAGE_EXPIRED: "정해진 시간 안에 전달하지 못해 전달을 끝냈습니다.",
}


def queue_id_from_response(response: str | None) -> str | None:
    """앱이 받은 DATA 응답(`250 2.0.0 Ok: queued as C87DBF6954`)에서 릴레이의 큐 id."""
    match = _QUEUED_AS.search(response or "")
    return match.group(1) if match else None


def classify(status: str | None, said: str | None) -> tuple[str, str | None]:
    """`(바깥 결과, 막힌 단계)`. 순수 함수 — 실제 Postfix 로그 문장으로 시험한다."""
    remote = _STATUS_MAP.get(status or "", REMOTE_UNKNOWN)
    if remote == REMOTE_DELIVERED:
        return remote, None
    if remote == REMOTE_EXPIRED:
        return remote, STAGE_EXPIRED
    text = said or ""
    lowered = text.lower()
    if "host or domain name not found" in lowered or "name service error" in lowered:
        return remote, STAGE_DNS
    said_code = re.search(r"\bsaid: (\d)\d\d\b", text)
    if said_code:
        return remote, STAGE_REJECTED if said_code.group(1) == "5" else STAGE_TEMPORARY
    if "tls" in lowered or "ssl" in lowered or "certificate" in lowered:
        return remote, STAGE_TLS
    if "connect to" in lowered or "timed out" in lowered or "refused" in lowered or "unreachable" in lowered \
            or "no route to host" in lowered or "lost connection" in lowered:
        return remote, STAGE_CONNECT
    return remote, None


def _said(tail: str) -> str | None:
    start = tail.find("(")
    if start < 0:
        return None
    text = tail[start + 1:]
    if text.endswith(")"):
        text = text[:-1]
    return " ".join(text.split())[:SAID_MAX] or None


def parse_log(text: str, queue_ids: Iterable[str]) -> dict[str, dict]:
    """로그 원문 → 큐 id 별 마지막 결과 `{status, dsn, relay, said, stage, removed}`. 모르는 큐 id 의 줄은 버린다."""
    wanted = {q for q in queue_ids if QUEUE_ID_RE.match(q or "")}
    out: dict[str, dict] = {}
    for line in (text or "").splitlines():
        removed = _REMOVED.search(line)
        if removed and removed.group("qid") in wanted:
            out.setdefault(removed.group("qid"), {})["removed"] = True
            continue
        match = _LINE.search(line)
        if not match or match.group("qid") not in wanted:
            continue
        rest = match.group("rest")
        status = _STATUS.search(rest)
        if not status:
            continue
        said = _said(status.group("tail"))
        remote, stage = classify(status.group("status"), said)
        dsn = _DSN.search(rest)
        relay = _RELAY.search(rest)
        entry = out.setdefault(match.group("qid"), {})
        entry.update({
            "status": remote, "dsn": dsn.group("dsn") if dsn else None,
            "relay": relay.group("relay")[:200] if relay else None, "said": said, "stage": stage,
        })
    return out


def parse_postqueue(text: str, *, limit: int = QUEUE_LIMIT) -> list[dict]:
    """`postqueue -j`(줄마다 JSON 하나) → 큐에 남은 메일. 깨진 줄은 건너뛴다. 상한을 둔다(헬퍼 응답 크기)."""
    items: list[dict] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        qid = str(row.get("queue_id") or "")
        if not QUEUE_ID_RE.match(qid):
            continue
        recipients = []
        for rcpt in row.get("recipients") or []:
            if isinstance(rcpt, dict):
                recipients.append({
                    "address": str(rcpt.get("address") or "")[:320],
                    "delay_reason": " ".join(str(rcpt.get("delay_reason") or "").split())[:SAID_MAX] or None,
                })
        items.append({
            "queue_id": qid,
            "queue_name": str(row.get("queue_name") or "")[:16],
            "arrival_time": row.get("arrival_time") if isinstance(row.get("arrival_time"), int) else None,
            "recipients": recipients,
        })
        if len(items) >= limit:
            break
    return items


def queue_state(item: dict) -> tuple[str, str | None, str | None]:
    """큐에 남은 한 통 → `(바깥 결과, 막힌 단계, 까닭 문장)`. 지연 까닭이 있으면 미룸, 없으면 아직 차례를 기다리는 중이다."""
    reasons = [r.get("delay_reason") for r in item.get("recipients") or [] if r.get("delay_reason")]
    if item.get("queue_name") == "deferred" or reasons:
        said = reasons[0] if reasons else None
        _remote, stage = classify("deferred", said)
        return REMOTE_DEFERRED, stage, said
    return REMOTE_QUEUED, None, None
