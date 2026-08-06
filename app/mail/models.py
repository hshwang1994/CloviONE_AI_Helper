"""메일 발송 아웃박스 (9-9 P4).

## 이 표가 답하는 질문은 하나다: "그 메일 어떻게 됐나"

메일 실패는 본 작업을 막지 않는다(알림 실패와 같은 기존 규칙). 그래서 실패가 **어디에
남는지**를 정해 두지 않으면 조용히 사라진다. 여기다. 세 상태가 서로 다른 사실을 말한다:

  * ``queued``       - 큐에 넣었다. 워커가 아직 안 집었거나 집는 중이다.
  * ``sent``         - 실제로 SMTP 서버가 받았다.
  * ``failed``       - 보내려다 실패했다. ``last_error`` 에 이유가 있다.
  * ``unconfigured`` - **보내려는 시도조차 못 했다.** SMTP 설정이 없다.

넷째가 이 표에서 가장 중요하다. 설정이 없을 때 잡을 만들어 두면 큐가 영원히 재시도하고,
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

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MAIL_QUEUED = "queued"
MAIL_SENT = "sent"
MAIL_FAILED = "failed"
MAIL_UNCONFIGURED = "unconfigured"

ALL_MAIL_STATUSES = frozenset(
    {MAIL_QUEUED, MAIL_SENT, MAIL_FAILED, MAIL_UNCONFIGURED}
)

# 화면이 상태 값을 받아 이름을 스스로 붙이면, 상태가 하나 늘 때 raw 값이 노출된다
# (app/core/authz.py 의 ROLE_LABELS 와 같은 이유).
MAIL_STATUS_LABELS: dict[str, str] = {
    MAIL_QUEUED: "발송 대기",
    MAIL_SENT: "발송됨",
    MAIL_FAILED: "발송 실패",
    MAIL_UNCONFIGURED: "발송 불가(설정 없음)",
}


class MailDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mail_deliveries"

    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    job_id: Mapped[str | None] = mapped_column(String(36))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
