"""메일 모양 미리 보기의 표본 (계획 M3, D-549).

미리 보기는 디자인 검수 도구다 - 관리자가 사람들이 받는 메일의 모양을 본다. **실제 DB 의 사용자 · 티켓 · 토큰을 가져오지
않는다.** 이름 · 티켓 키 · 링크 · 코드가 전부 여기 고정된 표본이고, 내용은 실제 발송과 같은 내용 함수
(`app/mail/content.py`)가 만든다 - 그래서 미리 보기와 실제 메일이 갈라질 수 없다. 제품 이름과 기준 주소만 이 설치의 값을 쓴다
(사람의 정보가 아니다).

종류는 사람이 받는 메일의 갈래다(발송 기록의 `kind` 와 다르다 - 알림 메일 하나가 티켓 배정 · 상태 변경 · 완료 · 댓글로
갈린다).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.mail import content as c

SAMPLE_NAME = "김하나"
SAMPLE_REQUESTER = "이두리"
SAMPLE_TICKET = "ABC-12"
SAMPLE_TICKET_TITLE = "사내 메일 서버 인증서 갱신"
SAMPLE_TOKEN = "sample-preview-token"
SAMPLE_CODE = "482913"
SAMPLE_AT = datetime(2026, 10, 1, 5, 5, tzinfo=timezone.utc)
SAMPLE_EMAIL = "kim.hana@example.com"


def _subject(product: str, summary: str) -> str:
    return f"[{product}] {summary}"


def _ticket_link(base: str) -> str:
    return f"{base}/#/tickets/{SAMPLE_TICKET}"


def _ticket_assigned(product: str, base: str):
    title = f"{SAMPLE_TICKET} 담당자로 지정: {SAMPLE_REQUESTER}"
    return c.notification_content(
        product=product, base_url=base, subject=_subject(product, title), name=SAMPLE_NAME, type_="ticket_assigned",
        title=title, body=SAMPLE_TICKET_TITLE, link=_ticket_link(base), type_label="티켓 배정", first_assignment=True,
    )


def _ticket_status(product: str, base: str):
    title = f"{SAMPLE_TICKET} 상태 변경: 진행 중"
    return c.notification_content(
        product=product, base_url=base, subject=_subject(product, title), name=SAMPLE_NAME,
        type_="ticket_status_changed", title=title, body=SAMPLE_TICKET_TITLE, link=_ticket_link(base),
        type_label="티켓 상태 변경",
    )


def _ticket_resolved(product: str, base: str):
    title = f"{SAMPLE_TICKET} 완료: {SAMPLE_TICKET_TITLE}"
    return c.notification_content(
        product=product, base_url=base, subject=_subject(product, f"{SAMPLE_TICKET} 완료"), name=SAMPLE_NAME,
        type_="ticket_resolved", title=title, body="요청한 작업이 끝났습니다.", link=_ticket_link(base),
        type_label="요청한 티켓 결과",
    )


def _ticket_comment(product: str, base: str):
    title = f"{SAMPLE_TICKET}에 새 댓글: {SAMPLE_REQUESTER}"
    return c.notification_content(
        product=product, base_url=base, subject=_subject(product, title), name=SAMPLE_NAME, type_="ticket_comment",
        title=title, body="갱신한 인증서를 적용했습니다. 확인 부탁드립니다.", link=_ticket_link(base), type_label="티켓 댓글",
    )


def _invite(product: str, base: str):
    link = f"{base}/reset-password?token={SAMPLE_TOKEN}"
    return c.invite_content(
        product=product, base_url=base, subject=_subject(product, "계정이 만들어졌습니다"), name=SAMPLE_NAME,
        email=SAMPLE_EMAIL, link=link, days=7,
    )


def _password_reset(product: str, base: str):
    link = f"{base}/reset-password?token={SAMPLE_TOKEN}"
    return c.password_reset_content(
        product=product, base_url=base, subject=_subject(product, "비밀번호 재설정 안내"), name=SAMPLE_NAME,
        link=link, hours=1,
    )


def _approval(product: str, base: str):
    return c.approval_requested_content(
        product=product, base_url=base, subject=_subject(product, "승인 요청: AI 문서 만들기"),
        type_label="AI 문서 만들기", requester=SAMPLE_REQUESTER, target="문서", approval_id=None,
    )


def _backup_failed(product: str, base: str):
    return c.backup_failed_content(
        product=product, base_url=base, subject=_subject(product, "예약 백업 실패"), at=SAMPLE_AT,
        reason="저장소에 연결하지 못해 백업이 실패했습니다.",
    )


def _verification(product: str, base: str):
    return c.verification_code_content(
        product=product, base_url=base, subject=_subject(product, "알림 받을 주소 확인 코드"), name=SAMPLE_NAME,
        code=SAMPLE_CODE, minutes=15,
    )


def _test(product: str, base: str):
    return c.test_content(
        product=product, base_url=base, subject=_subject(product, "메일 발송 시험"), sent_at=SAMPLE_AT,
        server="smtp.example.com:587", security_label="STARTTLS", mode_label="외부 SMTP 사용",
    )


#: (키, 이름, 내용 함수). 나열 순서가 화면의 선택지 순서다.
PREVIEW_KINDS: tuple[tuple[str, str, object], ...] = (
    ("ticket_assigned", "티켓 배정", _ticket_assigned),
    ("ticket_status_changed", "티켓 상태 변경", _ticket_status),
    ("ticket_resolved", "티켓 완료", _ticket_resolved),
    ("ticket_comment", "댓글", _ticket_comment),
    ("invite", "초대", _invite),
    ("password_reset", "비밀번호 재설정", _password_reset),
    ("approval_requested", "승인 요청", _approval),
    ("backup_failed", "백업 실패", _backup_failed),
    ("notify_email_verification", "이메일 주소 확인", _verification),
    ("test", "시험 메일", _test),
)
_BY_KEY = {key: (label, builder) for key, label, builder in PREVIEW_KINDS}


def catalog() -> list[dict]:
    return [{"key": key, "label": label} for key, label, _ in PREVIEW_KINDS]


def preview(kind: str, *, product: str, base_url: str, support: str | None = None) -> c.RenderedMail | None:
    """표본 한 통. 모르는 종류면 None."""
    entry = _BY_KEY.get(kind)
    if entry is None:
        return None
    content = entry[1](product, base_url.rstrip("/"))
    content.support_email = support
    return c.render(content)
