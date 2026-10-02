"""메일 상태의 낱말 — 확인한 단계까지만 말한다 (계획 M2, D-555).

「보냈습니다」는 「받은 편지함에 들어갔습니다」가 아니다. 제품이 잴 수 있는 것은 단계마다 다르다:

  1. 큐에 들어갔다(보낼 차례)
  2. 전송을 시작했다(보내는 중)
  3. 다음 서버가 250 으로 받았다 — 외부 SMTP 면 「메일 서버가 접수함」, 로컬 릴레이면 「로컬 릴레이가 접수함」
  4. 로컬 릴레이의 바깥 전달 결과 — 받는 쪽 메일 서버가 250 으로 받았으면 「수신측 메일 서버로 전달함」, 상위 SMTP 를 거쳤으면
     「상위 SMTP 서버가 접수함」(그 뒤는 상위 서버의 일이다), 4xx 나 연결 실패면 「전달 재시도 중」, 5xx 면 「수신측이 거부함」
  5. 반송이 오지 않았다 — 반송 메일은 보내는 주소의 메일함으로 가며 제품이 추적하지 않는다
  6. 사람이 받은 편지함에서 확인했다 — 사람만 한다(E2E 증거)

그래서 이 표의 어떤 낱말도 「도착했습니다」 · 「받았습니다」라고 말하지 않는다. 서버 응답 · 발송 기록 · 시험 메일 결과가 이 표
하나를 함께 쓴다(화면이 따로 사전을 들지 않는다).
"""

from __future__ import annotations

from app.mail.models import (
    MAIL_CANCELLED,
    MAIL_FAILED,
    MAIL_QUEUED,
    MAIL_RETRYING,
    MAIL_SENT,
    MAIL_SUPERSEDED,
    MAIL_UNCONFIGURED,
)

MODE_EXTERNAL = "external"
MODE_LOCAL_RELAY = "local_relay"

REMOTE_QUEUED = "queued"
REMOTE_DEFERRED = "deferred"
REMOTE_DELIVERED = "delivered"
REMOTE_BOUNCED = "bounced"
REMOTE_EXPIRED = "expired"
REMOTE_UNKNOWN = "unknown"

DELIVERY_SMARTHOST = "smarthost"
DELIVERY_DIRECT = "direct"

#: 저장 상태 → 화면 낱말(바깥 전달 결과가 없을 때). 「발송됨」은 쓰지 않는다 — 어느 서버가 받았는지가 낱말에 든다.
STATUS_WORDS: dict[str, str] = {
    MAIL_QUEUED: "보낼 차례",
    MAIL_RETRYING: "다시 보낼 차례",
    MAIL_UNCONFIGURED: "설정이 끝나지 않아 보내지 못함",
    MAIL_FAILED: "보내지 못함",
    MAIL_CANCELLED: "취소됨",
    # 보내기 직전에 다시 보니 의미가 없어졌다 - 더 새 알림이 있거나, 너무 오래됐거나, 초대받은 사람이 이미 로그인했다. 낱말은
    # 셋을 함께 덮고 정확한 까닭은 행의 `skip_reason_label` 이 말한다(계획 표의 「더 새 알림이 있음」은 그중 하나라 쓰지 않는다).
    MAIL_SUPERSEDED: "보내지 않음(의미가 없어짐)",
}
#: 상태 조건(필터)의 낱말. 접수는 보내는 방식마다 낱말이 달라 조건에서는 「서버가 접수함」 하나로 묶는다.
STATUS_FILTER_WORDS: dict[str, str] = {
    MAIL_QUEUED: STATUS_WORDS[MAIL_QUEUED],
    MAIL_RETRYING: STATUS_WORDS[MAIL_RETRYING],
    MAIL_SENT: "서버가 접수함",
    MAIL_FAILED: STATUS_WORDS[MAIL_FAILED],
    MAIL_UNCONFIGURED: STATUS_WORDS[MAIL_UNCONFIGURED],
    MAIL_CANCELLED: STATUS_WORDS[MAIL_CANCELLED],
    MAIL_SUPERSEDED: "보내지 않음(의미가 없어짐)",
}
SENDING_WORD = "보내는 중"
ACCEPTED_EXTERNAL = "메일 서버가 접수함"
ACCEPTED_RELAY = "로컬 릴레이가 접수함"
REMOTE_WORDS: dict[tuple[str, str], str] = {
    (REMOTE_DELIVERED, DELIVERY_DIRECT): "수신측 메일 서버로 전달함",
    (REMOTE_DELIVERED, DELIVERY_SMARTHOST): "상위 SMTP 서버가 접수함",
}
REMOTE_GENERIC: dict[str, str] = {
    REMOTE_DEFERRED: "전달 재시도 중",
    REMOTE_BOUNCED: "수신측이 거부함",
    REMOTE_EXPIRED: "전달 시간이 지남",
}

#: 상태 배지의 성격(화면 색). 접수는 아직 끝이 아니라 정보색이다.
STATUS_KINDS: dict[str, str] = {
    MAIL_QUEUED: "info", MAIL_RETRYING: "warn", MAIL_UNCONFIGURED: "warn", MAIL_FAILED: "danger",
    MAIL_CANCELLED: "neutral", MAIL_SUPERSEDED: "neutral",
}

#: 단계 진단의 이름(연결 확인 · 발송 기록). 보내는 방식이 지나는 단계만 화면에 선다.
STAGE_LABELS: dict[str, str] = {
    "dns": "DNS 조회",
    "connect": "서버 연결",
    "tls": "보안 연결",
    "greeting": "인사",
    "ehlo": "인사",
    "auth": "인증",
    "sender": "보내는 사람",
    "recipient": "받는 사람",
    "data": "본문 전송",
}
VERIFY_STAGES = ("dns", "connect", "tls", "auth", "sender", "recipient")


def delivery_word(status: str, *, mode: str | None = None, remote_status: str | None = None,
                  relay_delivery: str | None = None, sending: bool = False) -> str:
    """발송 기록 한 줄의 상태 낱말. 확인한 단계까지만 말한다(머리말)."""
    if status == MAIL_QUEUED and sending:
        return SENDING_WORD
    if status != MAIL_SENT:
        return STATUS_WORDS.get(status, status)
    if mode == MODE_LOCAL_RELAY:
        if remote_status in (None, "", REMOTE_QUEUED, REMOTE_UNKNOWN):
            return ACCEPTED_RELAY
        word = REMOTE_WORDS.get((remote_status, relay_delivery or DELIVERY_DIRECT))
        return word or REMOTE_GENERIC.get(remote_status, ACCEPTED_RELAY)
    return ACCEPTED_EXTERNAL


def delivery_kind(status: str, *, remote_status: str | None = None) -> str:
    if status == MAIL_SENT:
        if remote_status == REMOTE_DELIVERED:
            return "ok"
        if remote_status in (REMOTE_BOUNCED, REMOTE_EXPIRED):
            return "danger"
        if remote_status == REMOTE_DEFERRED:
            return "warn"
        return "info"
    return STATUS_KINDS.get(status, "neutral")


def test_result_sentence(mode: str | None) -> str:
    """시험 메일을 보낸 뒤의 한 문장 — 「도착」이 아니라 「접수」다."""
    if mode == MODE_LOCAL_RELAY:
        return "로컬 릴레이가 시험 메일을 접수했습니다. 수신측 전달 결과는 발송 기록에서 볼 수 있습니다."
    return "메일 서버가 시험 메일을 접수했습니다. 받은 편지함에서 확인하세요."
