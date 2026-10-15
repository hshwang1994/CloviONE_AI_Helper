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


def _test_relay(product: str, base: str):
    return c.test_content(
        product=product, base_url=base, subject=_subject(product, "메일 발송 시험"), sent_at=SAMPLE_AT,
        server="이 서버의 로컬 릴레이", security_label="", mode_label=f"{product} 로컬 릴레이", delivery_label="인터넷으로 직접 전달",
    )


# 알림 메일이 되는 나머지 유형(D-562) - 표본 재료는 한 벌이고 유형 · 제목 · 본문만 다르다.
_NOTIFICATION_SAMPLES: dict[str, tuple[str, str, str, str]] = {
    # key: (유형 이름, 알림 제목, 본문, 링크 경로)
    "offboarding_handover": ("업무 인수", f"{SAMPLE_TICKET} 인수: 퇴사자 티켓", SAMPLE_TICKET_TITLE, f"/#/tickets/{SAMPLE_TICKET}"),
    "approval_overdue": ("승인 기한 초과", "승인 기한 초과: AI 문서 만들기", f"{SAMPLE_REQUESTER} 님이 올린 요청이 기한을 넘겼습니다.", "/admin#/approvals"),
    "approval_expired": ("승인 만료", "승인 만료: AI 문서 만들기", "기한이 지나 자동으로 만료됐습니다.", "/#/approvals"),
    "approval_cancelled": ("승인 취소", "승인 취소: AI 문서 만들기", f"{SAMPLE_REQUESTER} 님이 요청을 취소했습니다.", "/#/approvals"),
    "approval_delegated": ("승인 권한 위임받음", f"{SAMPLE_REQUESTER} 님의 승인 권한 위임", "10월 1일부터 10월 7일까지 대신 결재합니다.", "/admin#/approvals"),
    "chat_invited": ("채팅방 초대", "채팅방 초대: 플랫폼개발팀", f"{SAMPLE_REQUESTER} 님이 초대했습니다.", "/#/chat-rooms"),
    "chat_mentioned": ("@멘션", f"{SAMPLE_REQUESTER} 님이 채팅에서 불렀습니다", "회의 자료 확인 부탁드립니다.", "/#/chat-rooms"),
    "document_comment": ("문서 댓글", f"문서에 새 댓글: {SAMPLE_REQUESTER}", "연차 규정 3절을 고쳤습니다. 확인 부탁드립니다.", "/#/knowledge"),
    "board_comment": ("게시글 댓글", f"게시글에 새 댓글: {SAMPLE_REQUESTER}", "좋은 제안 감사합니다. 다음 주에 반영하겠습니다.", "/#/board"),
    "idea_status_changed": ("제안 상태 변경", "제안 상태 변경: 검토 중", "메일 알림 유형 확대 제안이 검토 중으로 바뀌었습니다.", "/#/ideas"),
    "approval_decided": ("승인 결과", "승인됨: AI 문서 만들기", "승인자 의견은 메일에 싣지 않습니다.", "/#/approvals"),
    "ai_quota_exhausted": ("AI 사용 한도 도달", "이번 기간의 AI 사용 한도를 다 썼습니다", "다음 기간이 시작되면 다시 쓸 수 있습니다.", "/#/chat"),
    "ai_provider_state": ("AI 연결 상태", "AI 연결이 막혔습니다: 키 거부", "AI 연결 화면에서 키를 다시 넣으세요.", "/admin#/ai-connection"),
}


def _notification_sample(type_: str):
    label, title, body, path = _NOTIFICATION_SAMPLES[type_]

    def build(product: str, base: str):
        return c.notification_content(
            product=product, base_url=base, subject=_subject(product, title), name=SAMPLE_NAME, type_=type_,
            title=title, body=body, link=f"{base}{path}", type_label=label,
        )

    return build


def _account_locked(product: str, base: str):
    return c.security_content(
        product=product, base_url=base, subject=_subject(product, "로그인 실패 누적으로 계정이 잠겼습니다"), name=SAMPLE_NAME,
        type_="account_locked", title="로그인 실패 누적으로 계정이 잠겼습니다",
        body="잠금 시간이 지나면 자동 해제됩니다. 즉시 해제는 관리자에게 문의하세요.", at=SAMPLE_AT,
    )


def _password_change_required(product: str, base: str):
    return c.security_content(
        product=product, base_url=base, subject=_subject(product, "비밀번호 변경이 필요합니다"), name=SAMPLE_NAME,
        type_="password_change_required", title="비밀번호 변경이 필요합니다",
        body="관리자가 비밀번호를 재발급했습니다. 다음 로그인 시 새 비밀번호로 변경해 주세요.", at=SAMPLE_AT,
    )


#: (키, 이름, 내용 함수). 나열 순서가 화면의 선택지 순서다 - 알림(업무 영역 순) → 계정 → 운영 → 시험.
PREVIEW_KINDS: tuple[tuple[str, str, object], ...] = (
    ("ticket_assigned", "티켓 배정", _ticket_assigned),
    ("ticket_status_changed", "티켓 상태 변경", _ticket_status),
    ("ticket_resolved", "티켓 완료", _ticket_resolved),
    ("ticket_comment", "티켓 댓글", _ticket_comment),
    ("offboarding_handover", "업무 인수", _notification_sample("offboarding_handover")),
    ("approval_decided", "승인 결과", _notification_sample("approval_decided")),
    ("approval_overdue", "승인 기한 초과", _notification_sample("approval_overdue")),
    ("approval_expired", "승인 만료", _notification_sample("approval_expired")),
    ("approval_cancelled", "승인 취소", _notification_sample("approval_cancelled")),
    ("approval_delegated", "승인 권한 위임", _notification_sample("approval_delegated")),
    ("chat_invited", "채팅방 초대", _notification_sample("chat_invited")),
    ("chat_mentioned", "채팅 멘션", _notification_sample("chat_mentioned")),
    ("document_comment", "문서 댓글", _notification_sample("document_comment")),
    ("board_comment", "게시글 댓글", _notification_sample("board_comment")),
    ("idea_status_changed", "제안 상태 변경", _notification_sample("idea_status_changed")),
    ("ai_quota_exhausted", "AI 사용 한도", _notification_sample("ai_quota_exhausted")),
    ("ai_provider_state", "AI 연결 상태", _notification_sample("ai_provider_state")),
    ("invite", "초대", _invite),
    ("password_reset", "비밀번호 재설정", _password_reset),
    ("account_locked", "계정 잠금 안내", _account_locked),
    ("password_change_required", "비밀번호 변경 안내", _password_change_required),
    ("notify_email_verification", "이메일 주소 확인", _verification),
    ("approval_requested", "승인 요청", _approval),
    ("backup_failed", "백업 실패", _backup_failed),
    ("test", "시험 메일(외부 SMTP)", _test),
    ("test_relay", "시험 메일(로컬 릴레이)", _test_relay),
)
_BY_KEY = {key: (label, builder) for key, label, builder in PREVIEW_KINDS}


def catalog() -> list[dict]:
    return [{"key": key, "label": label} for key, label, _ in PREVIEW_KINDS]


def preview(kind: str, *, product: str, base_url: str, support: str | None = None,
            logo_src: str | None = None, force_dark: bool = False) -> c.RenderedMail | None:
    """표본 한 통. 모르는 종류면 None. ``logo_src`` 는 미리 보기가 로고를 그릴 주소다(없으면 실제 메일처럼 CID).
    ``force_dark`` 는 미리 보기의 「다크」다(D-571, `content.render`)."""
    entry = _BY_KEY.get(kind)
    if entry is None:
        return None
    content = entry[1](product, base_url.rstrip("/"))
    content.support_email = support
    return c.render(content, logo_src=logo_src, force_dark=force_dark)
