"""메일 내용 모델 — 종류마다 내용 하나를 HTML · 평문 두 틀이 그린다 (계획 M3, D-549).

## 왜 내용과 모양을 나누는가

예전에는 종류마다 평문 문자열을 손으로 이어 붙였다. 그러면 HTML 을 더하는 순간 같은 문장이 두 벌이 되고 한쪽만
고쳐진다. 여기서는 종류마다 **내용**(`MailContent`: 미리 보기 문장 · 제목 · 핵심 문장 · 사실 상자 · 코드 · 주 단추 ·
대체 주소 · 메모 · 바닥글)만 만들고, 모양은 틀 두 벌(`app/mail/templates/layout.{html,txt}.j2`)이 정한다. 미리 보기
(`app/mail/samples.py`)도 같은 함수로 내용을 만든다 — 미리 보기와 실제 메일이 갈라질 수 없다.

## 메일에 싣지 않는 것

내부 id(uuid), 파이썬 예외 · 스택, 워커 이름, DB 상태 값, 유형 키(`approval.ai_document` 같은), 긴 서버 응답 원문. 필요하면
사람이 읽는 문장으로 바꾼다 — 그 표가 이 파일의 `backup_reason_sentence` 와 승인 유형 이름이다. 틀 시험이 금지를 단언한다
(`tests/unit/test_mail_templates.py`).

## 색은 제품 토큰 값을 옮긴다

메일 앱은 CSS 변수를 못 읽고 외부 글꼴 · 그림을 막는다. 그래서 틀은 제품 토큰(`frontend/src/ui/theme.js` 의 light 값)을
인라인 색으로 옮기고 새 색을 만들지 않는다. 보라는 워드마크의 「Assist」와 주 단추 하나에만 쓴다. 다크 규칙의 값(`COLORS_DARK`)도
같은 파일의 dark 토큰을 옮긴 것이다(D-571).

## 클래식 Outlook 도 같은 모양으로 (D-571)

클래식 Outlook 은 Word 엔진으로 그려 `<a>` 의 padding · 배경과 단위 없는 line-height 를 무시하거나 다르게 읽는다. 그래서 틀은 고스트 표 ·
`bgcolor` · px 줄 높이 · VML 단추를 쓰고, 이 파일은 그 재료(단추 폭 `button_width_px`, 대체 주소 두 갈래, 머리 위 짧은 이름 `eyebrow`)를
준다. 메일 머리(`Reply-To` · `List-Unsubscribe`)도 내용이 정한다(`RenderedMail.headers`).
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from markupsafe import Markup

DEFAULT_PRODUCT_NAME = "ClovirAssist"

# 제품 토큰의 light 값(`frontend/src/ui/theme.js::TOKENS.light` · `DEFAULT_ACCENT`). 새 값을 만들지 않는다.
COLORS = {
    "canvas": "#F5F6FB",      # inset — 메일 바깥 바탕
    "plate": "#FFFFFF",
    "inset": "#F5F6FB",
    "ink": "#161A2C",
    "muted": "#565E7A",
    "line": "#DCDFEC",
    "rule": "#E5E8F3",
    "accent": "#5A4FCF",
    "line_strong": "#BCC2D9",
    "danger": "#B3261E",
    "danger_bg": "#FAEBEC",
}
# 다크 규칙의 값(D-571). `frontend/src/ui/theme.js::TOKENS.dark` 의 값을 그대로 옮긴다 - canvas · plate · inset · text(ink) · muted ·
# line · rule · lineStrong · danger · dangerBg. 링크의 강조색은 `BrandLogo.jsx::INVERSE_INK.accent`(어두운 면 위 브랜드 잉크)다. 머리 띠와 주
# 단추는 다크에서도 바꾸지 않는다(흰 띠 위 로고, 보라 단추 위 흰 글자). 새 값을 만들지 않는다.
COLORS_DARK = {
    "canvas": "#0A0C16",
    "plate": "#141829",
    "inset": "#1C2136",
    "ink": "#E5E8F5",
    "muted": "#9BA4C4",
    "line": "#242A46",
    "rule": "#242A46",
    "accent": "#B7C4FA",
    "line_strong": "#333B5E",
    "danger": "#FF8A80",
    "danger_bg": "#2E1A18",
}
# 글자가 있는 칸마다 직접 다는 글꼴 스택(D-571). 첫 이름이 Word 가 아는 글꼴이어야 한다 - 모르는 이름(`-apple-system`)이 앞에 서면 클래식
# Outlook 은 Times 로 떨어진다. 메일 앱은 웹 글꼴을 받지 않으므로 화면의 Pretendard 규칙의 의도된 예외다.
FONT_STACK = Markup("'Segoe UI','Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',Helvetica,Arial,sans-serif")
MONO_STACK = Markup("Consolas,'SFMono-Regular',Menlo,monospace")

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
ASSET_DIR = Path(__file__).resolve().parent / "assets"
KST = timezone(timedelta(hours=9))

#: 머리의 로고 표식(D-561) — CID 로 붙인 PNG 한 장. 원격 그림이 아니라 메일 안에 들어 있고, 그림이 막힌 메일 앱에서도 글자 워드마크가 남는다.
#: 그림은 `scripts/mail/export_mark.py` 가 제품 표식(`BrandLogo.jsx`)에서 만든 2배 그림(72px, 흰 칸 · 모서리 8px)이고 36px 로 그린다(D-571).
LOGO_CID = "clovi-mark@clovirassist"
LOGO_FILE = ASSET_DIR / "mark-72.png"
LOGO_SIZE = 36


@lru_cache(maxsize=1)
def logo_png() -> bytes:
    return LOGO_FILE.read_bytes()


def logo_data_uri() -> str:
    """미리 보기(sandbox iframe)용 - `cid:` 를 그릴 수 없는 자리에 같은 그림을 data 주소로 준다. 실제 메일에는 쓰지 않는다."""
    return "data:image/png;base64," + base64.b64encode(logo_png()).decode("ascii")


@dataclass
class MailContent:
    """메일 한 통의 내용. 모양은 틀이 정한다(머리말)."""

    subject: str
    preheader: str
    heading: str
    lead: list[str] = field(default_factory=list)
    facts: list[tuple[str, str]] = field(default_factory=list)
    code: str | None = None
    action: tuple[str, str] | None = None
    fallback_url: str | None = None
    alert: str | None = None
    notes: list[str] = field(default_factory=list)
    footer_reason: str = ""
    footer_links: list[tuple[str, str]] = field(default_factory=list)
    product_name: str = DEFAULT_PRODUCT_NAME
    support_email: str | None = None
    #: 제목 위의 짧은 이름(D-571) - 이 메일이 어떤 종류인지 한눈에 가른다(「티켓 배정 알림」 · 「계정 보안」).
    eyebrow: str = ""
    #: 알림 메일만 - 받는 사람이 알림 메일 설정을 바꾸는 화면. `List-Unsubscribe` 머리가 된다(D-571, one-click 없음 - P-129).
    unsubscribe_url: str | None = None


@dataclass(frozen=True)
class RenderedMail:
    subject: str
    text: str
    html: str
    #: HTML 이 `cid:` 로 가리키는 그림들 `(cid, bytes, media_type)` — 전송기가 `multipart/related` 로 붙인다(D-561).
    inline: tuple[tuple[str, bytes, str], ...] = ()
    #: 더할 메일 머리(D-571) - `Reply-To`(문의 주소가 있을 때) · `List-Unsubscribe`(알림 메일만). 전송기가 이름을 골라 싣는다.
    headers: dict[str, str] = field(default_factory=dict)


# ── 설정에서 읽는 것 ──────────────────────────────────────────────────────────


def _branding(db) -> dict:
    from app.settings.models import AppSetting

    if db is None:
        return {}
    row = db.get(AppSetting, "ui_branding")
    if row is None:
        return {}
    try:
        value = json.loads(row.value_json)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def product_name(db) -> str:
    """메일 제목 접두와 본문의 제품 이름(`ui_branding.product_name`). 비었거나 못 읽으면 기본 이름이다."""
    name = str(_branding(db).get("product_name") or "").strip()
    return _one_line(name, 60) or DEFAULT_PRODUCT_NAME


def support_email(db) -> str | None:
    value = str(_branding(db).get("support_email") or "").strip()
    return value if re.fullmatch(r"[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}", value) else None


# ── 글 다듬기 ──────────────────────────────────────────────────────────────────


def _one_line(text, limit: int) -> str:
    """제어 문자 · 줄바꿈을 걷고 공백을 접는다."""
    cleaned = "".join(ch if ch.isprintable() else " " for ch in str(text or ""))
    return " ".join(cleaned.split())[:limit]


def kst_text(value: datetime | str | None) -> str:
    """사람이 읽는 시각 `2026년 10월 1일 14:05`(KST). UTC ISO 원문을 메일에 싣지 않는다."""
    if value is None or value == "":
        return "-"
    if isinstance(value, str):
        from app.core.dates import parse_dt

        parsed = parse_dt(value)
        if parsed is None:
            return "-"
        value = parsed
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(KST)
    return f"{local.year}년 {local.month}월 {local.day}일 {local:%H:%M}"


_TECHNICAL = re.compile(
    r"(Traceback|Error\b|Error\(|Exception|errno|\bat 0x|/[a-z_]+/|\\[A-Za-z]|[A-Za-z_]+\.[A-Za-z_]+\(|"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
_HANGUL = re.compile(r"[가-힣]")


def backup_reason_sentence(reason: str | None) -> str:
    """백업 실패의 까닭 → 메일에 실을 한 문장. 사람이 쓴 한국어 문장만 그대로 싣고, 예외 · 경로 · id 가 든 원문은 일반 문장으로
    바꾼다(원문은 관리 화면의 백업 기록에 남는다)."""
    text = _one_line(reason, 300)
    if not text or _TECHNICAL.search(text) or not _HANGUL.search(text):
        return "백업 작업이 실패했습니다. 관리 화면의 백업 기록에서 원인을 확인하세요."
    return text if text.endswith(".") else text + "."


def _link(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _footer(reason: str, product: str) -> str:
    return reason.replace("{product}", product)


# ── 종류마다 내용 하나 ─────────────────────────────────────────────────────────
#
# 모두 순수 함수다(DB 를 읽지 않는다). 실제 메일은 `app/mail/renderers.py` 가 DB 에서 재료를 모아 부르고, 미리 보기는
# `app/mail/samples.py` 가 표본 재료로 부른다.


def password_reset_content(*, product: str, base_url: str, subject: str, name: str, link: str, hours: int) -> MailContent:
    return MailContent(
        subject=subject,
        preheader=f"{hours}시간 안에 새 비밀번호를 설정하세요.",
        heading="비밀번호 재설정을 요청하셨습니다.",
        lead=[f"{name} 님, 아래 단추를 눌러 새 비밀번호를 설정하세요."],
        action=("새 비밀번호 설정하기", link),
        fallback_url=link,
        notes=[
            f"이 링크는 {hours}시간 뒤에 만료되며 한 번만 쓸 수 있습니다.",
            "본인이 요청하지 않았다면 이 메일을 무시하세요. 비밀번호는 바뀌지 않습니다.",
        ],
        footer_reason=_footer("{product}에서 비밀번호 재설정을 요청해 보낸 메일입니다.", product),
        product_name=product,
        eyebrow="비밀번호 재설정",
    )


def invite_content(*, product: str, base_url: str, subject: str, name: str, email: str, link: str, days: int) -> MailContent:
    return MailContent(
        subject=subject,
        preheader=f"{product} 계정이 만들어졌습니다. 비밀번호를 설정하고 로그인하세요.",
        heading=f"{product} 계정이 만들어졌습니다.",
        lead=[f"{name} 님, 아래 단추를 눌러 비밀번호를 설정한 뒤 로그인하세요."],
        facts=[("계정", email), ("로그인 주소", _link(base_url, "/login"))],
        action=("비밀번호 설정하기", link),
        fallback_url=link,
        notes=[
            f"이 링크는 {days}일 뒤에 만료되며 한 번만 쓸 수 있습니다.",
            "임시 비밀번호는 메일로 보내지 않습니다.",
        ],
        footer_reason=_footer("{product} 관리자가 계정을 만들어 보낸 메일입니다.", product),
        product_name=product,
        eyebrow="계정 초대",
    )


def backup_failed_content(*, product: str, base_url: str, subject: str, at, reason: str | None) -> MailContent:
    link = _link(base_url, "/admin#/backup")
    return MailContent(
        subject=subject,
        preheader="예약 백업이 실패했습니다. 백업 화면에서 상태를 확인하세요.",
        heading="백업이 실패했습니다.",
        alert="백업 실패",
        lead=["예약 백업이 끝나지 못했습니다. 백업 화면에서 상태를 확인하고 디스크 용량과 권한을 점검하세요."],
        facts=[("발생 시각", kst_text(at)), ("내용", backup_reason_sentence(reason))],
        action=("백업 화면 열기", link),
        fallback_url=link,
        footer_reason=_footer("{product}의 백업 실패 알림입니다. 관리자에게만 보냅니다.", product),
        product_name=product,
        eyebrow="운영 알림",
    )


def approval_requested_content(
    *, product: str, base_url: str, subject: str, type_label: str, requester: str, target: str, approval_id: str | None,
) -> MailContent:
    link = _link(base_url, "/admin#/approvals" + (f"?id={approval_id}" if approval_id else ""))
    return MailContent(
        subject=subject,
        preheader=f"{requester} 님이 승인을 요청했습니다.",
        heading="결재할 승인 요청이 있습니다.",
        lead=[f"{requester} 님이 올린 요청을 검토하고 승인하거나 반려하세요."],
        facts=[("요청 유형", type_label), ("요청한 사람", requester), ("대상", target)],
        action=("승인 화면에서 보기", link),
        fallback_url=link,
        footer_reason=_footer("{product}에서 이 요청을 결재할 수 있는 사람에게 보낸 메일입니다.", product),
        product_name=product,
        eyebrow="결재 요청",
    )


def test_content(
    *, product: str, base_url: str, subject: str, sent_at, server: str, security_label: str, mode_label: str,
    delivery_label: str | None = None,
) -> MailContent:
    """시험 메일. 외부 SMTP 는 서버 · 보안 연결을, 로컬 릴레이는 전달 방식(``delivery_label``)을 사실로 적는다 — 릴레이 모드에
    외부 SMTP 값이 적히던 결함(P4 ④)을 고쳤다."""
    facts = [("보낸 시각", kst_text(sent_at)), ("보내는 방법", mode_label), ("메일 서버", server)]
    facts.append(("전달 방식", delivery_label) if delivery_label else ("보안 연결", security_label))
    return MailContent(
        subject=subject,
        preheader="메일 발송 설정을 확인하려고 보낸 시험 메일입니다.",
        heading="시험 메일입니다.",
        lead=["관리 화면에서 보낸 시험 메일입니다. 이 메일이 받은 편지함에 있다면 지금 설정으로 메일이 나갑니다."],
        facts=facts,
        action=("메일 설정 열기", _link(base_url, "/admin#/mail?tab=settings")),
        footer_reason=_footer("{product} 관리자가 메일 발송을 확인하려고 보낸 메일입니다.", product),
        product_name=product,
        eyebrow="시험 메일",
    )


# 알림 유형마다 제목 문장. 본문은 알림의 제목(티켓은 키가 든 문장)과 사실이다. 메일이 되는 유형 전부(D-562)가 여기 있다.
NOTIFICATION_HEADINGS = {
    "ticket_assigned": "티켓이 배정됐습니다.",
    "ticket_status_changed": "티켓 상태가 바뀌었습니다.",
    "ticket_resolved": "요청한 티켓이 끝났습니다.",
    "ticket_comment": "티켓에 새 댓글이 있습니다.",
    "offboarding_handover": "업무를 넘겨받았습니다.",
    "approval_decided": "승인 결과가 나왔습니다.",
    "approval_overdue": "처리할 승인 요청이 기한을 넘겼습니다.",
    "approval_expired": "승인 대기 건이 만료됐습니다.",
    "approval_cancelled": "승인 요청이 취소됐습니다.",
    "approval_delegated": "승인 권한을 위임받았습니다.",
    "chat_invited": "채팅방에 초대됐습니다.",
    "chat_mentioned": "채팅에서 나를 불렀습니다.",
    "document_comment": "문서에 새 댓글이 있습니다.",
    "board_comment": "게시글에 새 댓글이 있습니다.",
    "idea_status_changed": "제안의 상태가 바뀌었습니다.",
    "ai_quota_exhausted": "AI 사용 한도에 닿았습니다.",
    "ai_provider_state": "AI 연결 상태가 바뀌었습니다.",
}
# 받는 사람에게 하는 첫 문장(완전한 문장). 알림 제목(「ABC-12 담당자로 지정: 이두리」)은 사실 상자의 「알림」 줄이다 — 예전에는 이름 뒤에
# 그 제목을 그대로 붙여 「김하나 님, ABC-12 담당자로 지정: 이두리」처럼 기록 문장으로 읽혔다(로컬 메일 E2E 의 렌더 확인).
NOTIFICATION_LEADS = {
    "ticket_assigned": "{name} 님이 티켓 담당자로 지정됐습니다.",
    "ticket_status_changed": "{name} 님과 관련된 티켓의 상태가 바뀌었습니다.",
    "ticket_resolved": "{name} 님이 요청한 티켓에 결과가 나왔습니다.",
    "ticket_comment": "{name} 님과 관련된 티켓에 새 댓글이 달렸습니다.",
    "offboarding_handover": "{name} 님이 퇴사자의 티켓을 넘겨받았습니다.",
    "approval_decided": "{name} 님이 올린 승인 요청에 결과가 나왔습니다.",
    "approval_overdue": "{name} 님이 처리할 승인 요청이 기한을 넘겼습니다.",
    "approval_expired": "{name} 님과 관련된 승인 대기 건이 기한을 넘겨 만료됐습니다.",
    "approval_cancelled": "{name} 님이 올린 승인 요청을 다른 사람이 취소했습니다.",
    "approval_delegated": "{name} 님이 다른 사람의 승인 권한을 대신 위임받았습니다.",
    "chat_invited": "{name} 님을 채팅방에 초대했습니다.",
    "chat_mentioned": "{name} 님을 채팅에서 불렀습니다.",
    "document_comment": "{name} 님과 관련된 문서에 새 댓글이 달렸습니다.",
    "board_comment": "{name} 님이 쓴 게시글에 새 댓글이 달렸습니다.",
    "idea_status_changed": "{name} 님이 올린 제안의 상태가 바뀌었습니다.",
    "ai_quota_exhausted": "{name} 님이 이번 기간의 AI 사용 한도를 다 썼습니다.",
    "ai_provider_state": "{name} 님, AI 연결 상태가 바뀌었습니다.",
}
# 알림 본문 한 줄의 이름 — 티켓 알림의 본문은 티켓 제목이다.
NOTIFICATION_FACT_LABELS = {
    "ticket_assigned": "티켓 제목", "ticket_status_changed": "티켓 제목", "ticket_resolved": "결과",
    "ticket_comment": "댓글", "document_comment": "댓글", "board_comment": "댓글", "offboarding_handover": "티켓",
    "approval_overdue": "요청", "approval_expired": "요청", "approval_cancelled": "요청", "approval_delegated": "위임",
    "chat_invited": "채팅방", "idea_status_changed": "제안", "ai_quota_exhausted": "한도",
}
# 본문을 싣지 않는 유형(D-547 내용 최소화) — 채팅 메시지 미리 보기와 승인자의 의견은 메일로 내보내지 않는다.
NOTIFICATION_BODY_WITHHELD = frozenset({"chat_mentioned", "approval_decided"})

# 계정 보안 메일(D-562) — 사용자 선택 · 관리자 허용 목록과 무관하게, 메일이 켜져 있고 주소가 있으면 본인에게 보낸다.
SECURITY_HEADINGS = {
    "account_locked": "계정이 잠겼습니다.",
    "password_change_required": "비밀번호 변경이 필요합니다.",
}
SECURITY_LEADS = {
    "account_locked": "{name} 님의 계정에 로그인 실패가 쌓여 잠시 잠겼습니다. 잠금 시간이 지나면 자동으로 풀립니다.",
    "password_change_required": "{name} 님, 관리자가 비밀번호를 재발급했습니다. 다음 로그인 때 새 비밀번호로 바꾸세요.",
}
SECURITY_NOTES = {
    "account_locked": ["본인이 로그인하려던 것이 아니라면 관리자에게 바로 알려 주세요.", "임시 비밀번호나 링크는 이 메일에 없습니다."],
    "password_change_required": ["임시 비밀번호는 메일로 보내지 않습니다. 관리자에게 직접 받으세요.",
                                 "본인이 요청한 일이 아니라면 관리자에게 알려 주세요."],
}


def security_content(*, product: str, base_url: str, subject: str, name: str, type_: str, title: str, body: str,
                     at) -> MailContent:
    """계정 잠금 · 비밀번호 변경 요청(D-562). 설정 화면 링크 대신 로그인 화면으로 보내고, 알림 설정 링크가 없다(끌 수 없는 메일)."""
    link = _link(base_url, "/login")
    facts: list[tuple[str, str]] = [("발생 시각", kst_text(at))]
    headline = _one_line(title, 200)
    if headline:
        facts.append(("알림", headline))
    text = _one_line(body, 300)
    if text:
        facts.append(("내용", text))
    return MailContent(
        subject=subject,
        preheader=headline or SECURITY_HEADINGS.get(type_, "계정 보안 안내입니다."),
        heading=SECURITY_HEADINGS.get(type_, "계정 보안 안내입니다."),
        alert="계정 보안",
        lead=[SECURITY_LEADS.get(type_, "{name} 님의 계정에 관한 안내입니다.").format(name=name)],
        facts=facts,
        action=("로그인 화면 열기", link),
        fallback_url=link,
        notes=list(SECURITY_NOTES.get(type_, [])),
        footer_reason=_footer("계정 보안에 관한 메일이라 {product}의 알림 설정과 상관없이 보냅니다.", product),
        product_name=product,
        eyebrow="계정 보안",
    )


def notification_content(
    *, product: str, base_url: str, subject: str, name: str, type_: str, title: str, body: str, link: str,
    type_label: str, first_assignment: bool = False,
) -> MailContent:
    heading = NOTIFICATION_HEADINGS.get(type_, "새 알림이 있습니다.")
    if type_ == "ticket_assigned" and first_assignment:
        # 담당자가 아무도 없던 티켓이다 - 제목이 그 사실을 말한다(같은 말을 본문에 한 번 더 쓰지 않는다).
        heading = "새 티켓이 배정됐습니다."
    lead = [NOTIFICATION_LEADS.get(type_, "{name} 님에게 새 알림이 있습니다.").format(name=name)]
    facts: list[tuple[str, str]] = []
    headline = _one_line(title, 200)
    if headline:
        facts.append(("알림", headline))
    text = _one_line(body, 300)
    if type_ in NOTIFICATION_BODY_WITHHELD:
        lead.append(f"내용은 {product}에서 확인하세요.")
    elif text:
        facts.append((NOTIFICATION_FACT_LABELS.get(type_, "내용"), text))
    return MailContent(
        subject=subject,
        preheader=_one_line(title, 120) or heading,
        heading=heading,
        lead=lead,
        facts=facts,
        action=(f"{product}에서 보기", link),
        fallback_url=link,
        footer_reason=_footer(f"이 메일은 {{product}}의 {type_label} 알림 설정에 따라 보냈습니다.", product),
        footer_links=[("알림 메일 설정 바꾸기", _link(base_url, "/#/profile"))],
        product_name=product,
        eyebrow=f"{type_label} 알림",
        unsubscribe_url=_link(base_url, "/#/profile"),
    )


def verification_code_content(
    *, product: str, base_url: str, subject: str, name: str, code: str, minutes: int,
) -> MailContent:
    """알림 받을 주소 확인(M4). 링크가 아니라 코드를 넣게 한다 — 회사 메일의 링크 검사기가 코드를 써 버리지 못한다."""
    return MailContent(
        subject=subject,
        preheader=f"확인 코드는 {minutes}분 동안 쓸 수 있습니다.",
        heading="알림 받을 이메일 주소를 확인해 주세요.",
        lead=[f"{name} 님, 내 프로필의 확인 코드 칸에 아래 6자리 코드를 넣으세요."],
        code=code,
        notes=[f"코드는 {minutes}분 동안 쓸 수 있습니다.", "본인이 요청하지 않았다면 이 메일을 무시하세요."],
        footer_reason=_footer("{product}에서 알림 받을 주소를 확인하려고 보낸 메일입니다.", product),
        product_name=product,
        eyebrow="주소 확인",
    )


# ── 그리기 ────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _environment():
    from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default_for_string=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _wordmark(product: str) -> tuple[str, str]:
    """기본 이름일 때만 두 색 워드마크(Clovir + Assist). 이름을 바꾼 설치는 한 색 글자다."""
    if product == DEFAULT_PRODUCT_NAME:
        return "Clovir", "Assist"
    return product, ""


def button_width_px(label: str) -> int:
    """클래식 Outlook 의 VML 단추 폭(D-571). Word 는 글자에 맞춰 단추를 늘이지 못해 폭을 미리 정한다 - 좌우 여백 48 + 글자마다
    한중일 글자 15 · 그 밖의 글자 9(15px 굵은 글자 기준). 600px 판 안쪽(536)을 넘지 않게 520 에서 멈춘다."""
    return min(520, 48 + sum(15 if ord(ch) > 0x2E80 else 9 for ch in label))


def fallback_parts(url: str) -> tuple[str, str]:
    """대체 주소를 첫 `?` 앞에서 둘로 - Outlook 갈래가 두 줄로 그린다(Word 는 긴 낱말을 끊지 못해 표가 600px 를 넘는다)."""
    head, sep, tail = (url or "").partition("?")
    return (head, sep + tail) if sep else (url or "", "")


def mail_headers(content: MailContent) -> dict[str, str]:
    """더할 메일 머리(D-571). 답장은 문의 주소로 가게 하고(있을 때만), 알림 메일에는 설정 화면을 `List-Unsubscribe` 로 단다
    (헤더뿐이다 - one-click POST 는 없다, P-129)."""
    headers: dict[str, str] = {}
    if content.support_email:
        headers["Reply-To"] = content.support_email
    if content.unsubscribe_url:
        headers["List-Unsubscribe"] = f"<{content.unsubscribe_url}>"
    return headers


def _footer_line(content: MailContent) -> str:
    """평문 바닥글의 둘째 줄 - 설정 링크와 문의 주소를 한 줄로(HTML 틀과 같은 순서)."""
    parts = [f"{label}: {url}" for label, url in content.footer_links]
    if content.support_email:
        parts.append(f"문의: {content.support_email}")
    return " | ".join(parts)


def render(content: MailContent, *, logo_src: str | None = None, force_dark: bool = False) -> RenderedMail:
    """내용 → (제목, 평문, HTML, 머리). HTML 은 autoescape 라 제목 · 이름의 `<script>` 같은 글자가 그대로 글자로 보인다.

    ``logo_src`` 가 없으면 로고는 `cid:` 로 가리키고 그 PNG 가 `inline` 에 실린다(실제 발송). 미리 보기는 data 주소를 넘긴다.
    ``force_dark`` 는 미리 보기의 「다크」다 - body 에 `data-ogsc` 를 달아 Outlook.com 다크 규칙이 그대로 서게 한다(그 밖의 차이는 없다).
    """
    env = _environment()
    head, tail = _wordmark(content.product_name)
    inline: tuple = ()
    if logo_src is None:
        logo_src = f"cid:{LOGO_CID}"
        inline = ((LOGO_CID, logo_png(), "image/png"),)
    fallback_head, fallback_tail = fallback_parts(content.fallback_url or "")
    values = {
        "c": content, "colors": COLORS, "dark": COLORS_DARK, "font": FONT_STACK, "mono": MONO_STACK,
        "wordmark_head": head, "wordmark_tail": tail, "logo_src": logo_src, "logo_size": LOGO_SIZE,
        "button_width": button_width_px(content.action[0]) if content.action else 0,
        # 표지(alert)가 머리 위 이름과 같은 낱말이면(계정 보안) 표지 하나만 세운다 - 같은 말을 두 줄로 세우지 않는다.
        "eyebrow_line": bool(content.eyebrow) and not (content.alert and content.alert == content.eyebrow),
        "fallback_head": fallback_head, "fallback_tail": fallback_tail,
        "footer_line": _footer_line(content), "force_dark": force_dark,
    }
    html = env.get_template("layout.html.j2").render(**values)
    # 평문 틀은 이스케이프하지 않는다 - 평문에서 `&` 는 `&amp;` 가 아니라 `&` 다.
    text_env = env.overlay(autoescape=False)
    text = text_env.get_template("layout.txt.j2").render(**values)
    return RenderedMail(subject=content.subject, text=text, html=html, inline=inline, headers=mail_headers(content))
