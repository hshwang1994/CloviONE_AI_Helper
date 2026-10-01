"""메일 발송 아웃박스 (9-9 P4).

## 이 표가 답하는 질문은 하나다: "그 메일 어떻게 됐나"

메일 실패는 본 작업을 막지 않는다(알림 실패와 같은 기존 규칙). 그래서 실패가 **어디에
남는지**를 정해 두지 않으면 조용히 사라진다. 여기다. 세 상태가 서로 다른 사실을 말한다:

  * ``queued``       - 큐에 넣었다. 워커가 아직 안 집었거나 집는 중이다.
  * ``sent``         - 실제로 SMTP 서버가 받았다.
  * ``failed``       - 보내려다 실패했다. ``last_error`` 에 이유가 있다.
  * ``unconfigured`` - **보내려는 시도조차 못 했다.** SMTP 설정이 없다.

  * ``retrying``     - 보내다 일시적으로 실패해 **다시 보낼 차례를 기다린다**(계획 3.3). 재시도가 남아
                        있는 동안은 ``failed`` 가 아니다 - 예전에는 첫 실패부터 ``failed`` 로 적어서
                        다음 재시도가 성공할 메일도 실패로 세었다.
  * ``cancelled``    - 사람이 취소했거나, 보내기 직전에 받을 사람이 받을 수 없게 됐다.
  * ``superseded``   - 보내기 직전에 다시 보니 **의미가 없어졌다**(더 새로운 상태 변경이 있다 등).
                        ``skip_reason`` 에 무엇 때문인지 남는다.

넷째(unconfigured)가 이 표에서 가장 중요하다. 설정이 없을 때 잡을 만들어 두면 큐가 영원히 재시도하고,
나중에 설정을 켜는 날 몇 달 전 토큰 메일이 한꺼번에 나간다. 그렇다고 아무것도 안 남기면
"관리자에게 알렸어야 할 일" 이 통째로 증발한다. 그래서 잡 없이 행만 남긴다.

## 본문(body)을 저장하지 않는 이유

비밀번호 재설정 메일 본문에는 1회용 토큰이 들어간다. 본문을 여기 담으면 그 토큰 평문이
DB 에 앉는다 - 저장소가 secret 을 파일 참조로 분리해 둔 이유(불변 §3)와 정확히 같은
문제다. 대신 ``kind`` + ``params_json``(비밀 아닌 재료)만 두고, 워커가 발송 직전에
본문을 만든다(app/mail/renderers.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, JsonText, TimestampMixin, UUIDPrimaryKeyMixin

MAIL_QUEUED = "queued"
MAIL_RETRYING = "retrying"
MAIL_SENT = "sent"
MAIL_FAILED = "failed"
MAIL_UNCONFIGURED = "unconfigured"
MAIL_CANCELLED = "cancelled"
MAIL_SUPERSEDED = "superseded"

ALL_MAIL_STATUSES = frozenset(
    {MAIL_QUEUED, MAIL_RETRYING, MAIL_SENT, MAIL_FAILED, MAIL_UNCONFIGURED, MAIL_CANCELLED, MAIL_SUPERSEDED}
)
# 아직 끝나지 않은 상태. 보존 정리는 이 둘을 절대 지우지 않고, 취소는 이 둘에서만 된다.
PENDING_MAIL_STATUSES = frozenset({MAIL_QUEUED, MAIL_RETRYING})
# 끝난 상태. 보존 정리 대상이다.
TERMINAL_MAIL_STATUSES = ALL_MAIL_STATUSES - PENDING_MAIL_STATUSES

# 화면이 상태 값을 받아 이름을 스스로 붙이면, 상태가 하나 늘 때 raw 값이 노출된다
# (app/core/authz.py 의 ROLE_LABELS 와 같은 이유).
MAIL_STATUS_LABELS: dict[str, str] = {
    MAIL_QUEUED: "발송 대기",
    MAIL_RETRYING: "다시 보내는 중",
    MAIL_SENT: "발송됨",
    MAIL_FAILED: "발송 실패",
    MAIL_UNCONFIGURED: "발송 불가(설정 없음)",
    MAIL_CANCELLED: "보내지 않음(취소)",
    MAIL_SUPERSEDED: "의미가 없어져 보내지 않음",
}

# 실패의 종류(`failure_kind`). 전송기가 SMTP 응답과 예외를 이 어휘로 나눈다(`app/mail/transport.py`).
# 영구 실패는 다시 보내도 같은 결과라 즉시 끝내고, 일시 실패는 재시도 일정대로 다시 보낸다.
FAILURE_AUTH = "auth"            # 로그인 거부
FAILURE_TLS = "tls"              # 인증서 · 보안 연결
FAILURE_SENDER = "sender"        # 보내는 사람 거부
FAILURE_RECIPIENT = "recipient"  # 받는 사람 거부
FAILURE_REJECTED = "rejected"    # 그 밖의 5xx
FAILURE_CONNECT = "connect"      # 연결 실패 · 시간 초과
FAILURE_TEMPORARY = "temporary"  # 4xx 임시 거절
FAILURE_DISCONNECTED = "disconnected"
FAILURE_RENDER = "render"        # 본문을 만들지 못했다(대상 계정이 사라짐 등)
FAILURE_CONFIG = "config"        # 설정이 없어졌다
FAILURE_UNKNOWN = "unknown"


class MailDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mail_deliveries"
    __table_args__ = (
        Index("ix_mail_deliveries_created_at", "created_at"),
        Index("ix_mail_deliveries_status_created", "status", "created_at"),
        Index("ix_mail_deliveries_recipient_created", "recipient_user_id", "created_at"),
        UniqueConstraint("idempotency_key", name="uq_mail_deliveries_idempotency_key"),
    )

    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    params_json: Mapped[str] = mapped_column(JsonText, nullable=False, default="{}")
    job_id: Mapped[str | None] = mapped_column(String(36))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    # 같은 사건이 메일을 두 번 만들지 않게 하는 열쇠(예: `notification:<알림 id>`). 있으면 유일하다.
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    # 보낸 메일의 `Message-ID`. 상대 서버 로그에서 이 메일을 찾는 단서다.
    message_id: Mapped[str | None] = mapped_column(String(300))
    failure_kind: Mapped[str | None] = mapped_column(String(32))
    # 보내지 않은 까닭(`cancelled` · `superseded`). 예: `newer_status_event`, `cancelled_by_operator`.
    skip_reason: Mapped[str | None] = mapped_column(String(64))
    # 받는 사람 계정(D-547). 발송 기록을 범위로 거르는 축이고(부서 범위 관리자 · 운영자 · 감사자는 범위 안 사람의
    # 메일만 본다), 보내기 직전의 받는 사람 재검사가 누구를 볼지 정한다(`app/mail/recipients.py`). 계정이 아닌 주소로
    # 간 메일(시험 메일의 다른 주소)은 비어 있고 전역 관리자만 본다. 계정이 지워지면 비워진다.
    recipient_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"),
    )
    # 실패한 단계(dns · connect · tls · greeting · auth · sender · recipient · data)와 다음 서버의 마지막 응답 문장.
    # 상세 화면이 「어디서 막혔나」를 말한다(D-546). 응답 원문은 기술 정보 안에서만 보인다.
    failure_stage: Mapped[str | None] = mapped_column(String(16))
    relay_response: Mapped[str | None] = mapped_column(String(300))
