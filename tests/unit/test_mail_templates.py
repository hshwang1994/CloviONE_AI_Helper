"""메일 틀 — HTML · 평문, 이스케이프, 링크, 금지 내용, 제목 (계획 M3, D-549).

못박는 것:
  * 종류마다 평문과 HTML 두 부분이 같은 내용을 같은 순서로 그린다(황금 파일, `UPDATE_GOLDEN=1` 로 다시 쓴다).
  * 제목 · 이름의 `<script>"&` 는 HTML 에서 글자로 이스케이프되고 평문에서는 글자 그대로다.
  * 모든 링크는 기준 주소의 절대 `https?://` 다. 원격 그림 · SVG 가 없다. 본문은 600px 상한 · `lang="ko"` 다.
  * 제품 이름을 바꾸면 메일이 따라가고, 두 색 워드마크는 기본 이름일 때만이다.
  * 메일에 내부 id(uuid) · 예외 · 유형 키 · 긴 서버 응답이 없다. 보라 채움은 주 단추 하나뿐이다.
  * 제목은 `[제품] 요약` 이고 줄바꿈 · 제어 문자가 없으며 150자까지다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app.mail import content as c
from app.mail import samples

pytestmark = pytest.mark.unit

BASE = "https://clovirassist.gooddi.lab"
GOLDEN = Path(__file__).resolve().parents[1] / "regression" / "golden" / "mail"


def _all_previews(product="ClovirAssist"):
    return {key: samples.preview(key, product=product, base_url=BASE) for key, _label, _ in samples.PREVIEW_KINDS}


def test_every_mailable_type_and_security_kind_has_a_preview_and_each_renders_both_parts():
    """D-562: 메일이 되는 알림 유형 전부 + 계정 보안 둘 + 전용 메일 다섯 + 시험 둘이 표본이다 - 미리 보기 = 실제 그리기 함수."""
    from app.mail.renderers import SECURITY_KINDS
    from app.profiles.prefs import MAILABLE_TYPES

    rendered = _all_previews()
    assert len(rendered) == len(samples.PREVIEW_KINDS) >= 26
    for key in (*MAILABLE_TYPES, *sorted(SECURITY_KINDS), "invite", "password_reset", "approval_requested", "backup_failed",
                "notify_email_verification", "test", "test_relay"):
        assert key in rendered, f"{key} 의 표본이 없다"
    for key, mail in rendered.items():
        assert mail.text.strip() and mail.html.strip(), key
        assert mail.subject.startswith("[ClovirAssist] "), key


def test_the_logo_is_an_inline_cid_image_and_the_preview_uses_a_data_uri():
    """D-561: 머리의 로고는 CID 로 붙인 PNG 한 장이다 - 원격 그림이 없고, 미리 보기는 같은 그림을 data 주소로 받는다."""
    mail = samples.preview("invite", product="ClovirAssist", base_url=BASE)
    assert f'<img src="cid:{c.LOGO_CID}"' in mail.html and mail.html.count("<img") == 1
    assert mail.inline and mail.inline[0][0] == c.LOGO_CID and mail.inline[0][1][:8] == b"\x89PNG\r\n\x1a\n"
    shown = samples.preview("invite", product="ClovirAssist", base_url=BASE, logo_src=c.logo_data_uri())
    assert '<img src="data:image/png;base64,' in shown.html and shown.inline == ()
    assert "cid:" not in shown.html


def test_the_message_carries_the_logo_as_a_related_part():
    from app.mail.config import smtp_config
    from app.mail.transport import build_message

    config = smtp_config({"enabled": True, "host": "smtp.example.com", "from_address": "noreply@example.com", "from_name": "ClovirAssist"})
    mail = samples.preview("invite", product="ClovirAssist", base_url=BASE)
    message = build_message(config, to_email="kim@example.com", subject=mail.subject, body=mail.text, html=mail.html,
                            inline=mail.inline)
    html_part = message.get_payload()[-1]
    assert html_part.get_content_type() == "multipart/related"
    parts = html_part.get_payload()
    assert parts[0].get_content_type() == "text/html"
    assert parts[1].get_content_type() == "image/png" and parts[1]["Content-ID"] == f"<{c.LOGO_CID}>"
    assert parts[1].get_content_disposition() == "inline"


def test_security_mails_have_no_settings_link_and_no_secret():
    for kind in ("account_locked", "password_change_required"):
        mail = samples.preview(kind, product="ClovirAssist", base_url=BASE)
        assert "알림 설정" in mail.text and "알림 메일 설정 바꾸기" not in mail.text, kind
        assert "/login" in mail.text and "token=" not in mail.text, kind
        assert "계정 보안" in mail.html, kind


@pytest.mark.parametrize("key", [key for key, _label, _ in samples.PREVIEW_KINDS])
def test_golden_files(key):
    mail = samples.preview(key, product="ClovirAssist", base_url=BASE)
    for suffix, body in (("txt", mail.text), ("html", mail.html)):
        path = GOLDEN / f"{key}.{suffix}"
        if os.environ.get("UPDATE_GOLDEN") == "1" or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
        assert path.read_text(encoding="utf-8") == body, f"{path.name} 이 바뀌었다 - 의도면 UPDATE_GOLDEN=1"


def test_hostile_text_is_escaped_in_html_and_literal_in_text():
    hostile = '<script>alert("x")</script> & co'
    mail = c.render(c.notification_content(
        product="ClovirAssist", base_url=BASE, subject=f"[ClovirAssist] {hostile}", name=hostile,
        type_="ticket_comment", title=hostile, body=hostile, link=f"{BASE}/#/tickets/1", type_label="티켓 댓글",
    ))
    assert "<script>" not in mail.html and "&lt;script&gt;" in mail.html and "&amp; co" in mail.html
    assert hostile in mail.text, "평문은 글자 그대로여야 한다(&amp; 가 아니라 &)"


def test_links_are_absolute_and_there_are_no_remote_images():
    for key, mail in _all_previews().items():
        hrefs = re.findall(r'href="([^"]+)"', mail.html)
        # 주소 확인 메일만 링크가 없다 - 코드를 넣게 하는 메일이다(링크 검사기가 코드를 써 버리지 못하게).
        assert hrefs or key == "notify_email_verification", key
        assert all(h.startswith(BASE + "/") for h in hrefs), (key, hrefs)
        # 그림은 CID 로 붙인 로고 한 장뿐이다(D-561) - 원격 주소의 그림 · SVG 는 없다.
        assert mail.html.count("<img") == 1 and 'src="cid:' in mail.html and "<svg" not in mail.html, key
        assert not re.search(r'<img[^>]+src="https?://', mail.html), key
        assert 'lang="ko"' in mail.html and "max-width:600px" in mail.html, key
        assert "gradient" not in mail.html and "box-shadow" not in mail.html, key


def test_the_product_name_follows_the_setting():
    renamed = _all_previews(product="굿모닝 포털")
    for key, mail in renamed.items():
        assert mail.subject.startswith("[굿모닝 포털] "), key
        assert "ClovirAssist" not in mail.text and "Clovir" not in mail.html, key
    default = samples.preview("invite", product="ClovirAssist", base_url=BASE)
    assert '>Clovir<span style="color:#5A4FCF;">Assist</span>' in default.html, "기본 이름의 두 색 워드마크가 아니다"


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_TYPE_KEY = re.compile(r"\b[a-z_]+\.[a-z_]+\b")


def _visible_text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", re.sub(r"<(style|title)[^>]*>.*?</\1>", " ", html, flags=re.S))


def test_no_internal_ids_exceptions_or_type_keys():
    for key, mail in _all_previews().items():
        for body in (mail.text, _visible_text(mail.html)):
            assert not _UUID.search(body), key
            assert "Traceback" not in body and "Error(" not in body, key
            # 주소(링크 · 메일 주소)는 빼고 본다 - 도메인의 점은 유형 키가 아니다.
            words = re.sub(r"https?://\S+|\S+@\S+|smtp\.\S+", " ", body)
            keys = _TYPE_KEY.findall(words)
            assert keys == [], (key, keys)


def test_purple_fills_only_the_one_main_button():
    for key, mail in _all_previews().items():
        fills = re.findall(r"background:#5A4FCF", mail.html)
        assert len(fills) <= 1, key


def test_a_technical_backup_reason_becomes_a_sentence():
    assert c.backup_reason_sentence("OSError: [Errno 28] No space left on device: '/var/lib/x'") == (
        "백업 작업이 실패했습니다. 관리 화면의 백업 기록에서 원인을 확인하세요."
    )
    assert c.backup_reason_sentence("저장소에 연결하지 못했습니다") == "저장소에 연결하지 못했습니다."


def test_the_chat_preview_and_decision_comment_are_withheld():
    for type_ in ("chat_mentioned", "approval_decided"):
        mail = c.render(c.notification_content(
            product="ClovirAssist", base_url=BASE, subject="[ClovirAssist] 알림", name="김하나", type_=type_,
            title="새 알림", body="비밀 회의 내용입니다", link=f"{BASE}/#/x", type_label="알림",
        ))
        assert "비밀 회의 내용입니다" not in mail.text and "비밀 회의 내용입니다" not in mail.html
        assert "ClovirAssist에서 확인하세요." in mail.text


def test_the_subject_has_no_newlines_and_a_limit(monkeypatch):
    from app.mail import service

    monkeypatch.setattr("app.mail.content.product_name", lambda db: "ClovirAssist")
    subject = service.mail_subject(None, "첫 줄\r\nBcc: x@example.com\t" + "가" * 300)
    assert "\n" not in subject and "\r" not in subject and "\t" not in subject
    assert subject.startswith("[ClovirAssist] 첫 줄 Bcc:") and len(subject) == 150
