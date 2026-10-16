# qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
"""메일 틀 — HTML · 평문, 이스케이프, 링크, 금지 내용, 제목 (계획 M3, D-549).

못박는 것:
  * 종류마다 평문과 HTML 두 부분이 같은 내용을 같은 순서로 그린다(황금 파일, `UPDATE_GOLDEN=1` 로 다시 쓴다).
  * 제목 · 이름의 `<script>"&` 는 HTML 에서 글자로 이스케이프되고 평문에서는 글자 그대로다.
  * 모든 링크는 기준 주소의 절대 `https?://` 다. 원격 그림 · SVG 가 없다. 본문은 600px 상한 · `lang="ko"` 다.
  * 제품 이름을 바꾸면 메일이 따라가고, 두 색 워드마크는 기본 이름일 때만이다.
  * 메일에 내부 id(uuid) · 예외 · 유형 키 · 긴 서버 응답이 없다. 보라 채움은 주 단추 하나뿐이다.
  * 제목은 `[제품] 요약` 이고 줄바꿈 · 제어 문자가 없으며 150자까지다.
  * 클래식 Outlook(Word 엔진)도 같은 모양으로 그린다(D-571): 600px 고스트 표, 단추마다 VML `v:roundrect` 하나(주소 = 앵커 주소),
    `mso-padding-alt`, padding 을 쓰는 inline-block 앵커 0, line-height 는 전부 px 이고 exactly 규칙, 글자 칸마다 글꼴 스택(Times 로
    떨어지지 않게), 36px 로고 하나(그림은 72x72), 머리 위 이름이 두 부분 모두에, 다크 규칙 두 벌(값은 theme.js dark 토큰), 흰 머리 띠,
    사실 행 class · nowrap 없음, `force_dark` 는 `data-ogsc` 하나만 다르다, `Reply-To` · `List-Unsubscribe`(알림만) 머리.
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


_BUTTON_BLOCK = re.compile(r'<table role="presentation" class="ca-btn".*?</table>', re.S)
_STYLE_BLOCK = re.compile(r"<style>.*?</style>", re.S)
_PURPLE_FILL = re.compile(r'(background(?:-color)?:#5A4FCF|bgcolor="#5A4FCF"|fillcolor="#5A4FCF")', re.I)


def test_purple_fills_only_the_button_block():
    """보라 채움(배경 · bgcolor · VML 채움)은 주 단추 블록 안에만 있다(D-571 - 단추 밖 0). `<style>` 의 다크 고정 규칙은 단추 칸을 겨눈다."""
    for key, mail in _all_previews().items():
        blocks = _BUTTON_BLOCK.findall(mail.html)
        assert len(blocks) == (1 if 'class="ca-btn-link"' in mail.html else 0), key
        outside = _STYLE_BLOCK.sub("", _BUTTON_BLOCK.sub("", mail.html))
        assert not _PURPLE_FILL.findall(outside), (key, _PURPLE_FILL.findall(outside))
        if blocks:
            assert len(_PURPLE_FILL.findall(blocks[0])) >= 3, key  # 칸 bgcolor · 칸 배경 · VML 채움 · 앵커 배경


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


# ── 클래식 Outlook(Word 엔진) 호환 (D-571) ────────────────────────────────────


def _with_action():
    return {key: mail for key, mail in _all_previews().items() if 'class="ca-btn-link"' in mail.html}


def test_the_layout_has_a_600px_ghost_table_and_outlook_head_settings():
    for key, mail in _all_previews().items():
        html = mail.html
        assert '<!--[if mso]><table role="presentation" width="600" align="center"' in html, key
        assert "<!--[if mso]></td></tr></table><![endif]-->" in html, key
        assert "<o:PixelsPerInch>96</o:PixelsPerInch>" in html and 'xmlns:v="urn:schemas-microsoft-com:vml"' in html, key
        assert '<meta name="x-apple-disable-message-reformatting">' in html, key
        assert '<meta name="color-scheme" content="light dark">' in html, key
        # Word 가 한글과 영문 사이에 넣는 간격을 막고, 단추 칸의 바탕 · 여백을 걷어 VML 둥근 단추만 남긴다(COM 실측).
        mso_style = html[html.index("<!--[if mso]>"):html.index("<![endif]-->")]
        assert "text-autospace: none" in mso_style and "td.ca-btn-cell { background: transparent !important" in mso_style, key


def test_each_action_is_one_vml_roundrect_and_one_block_anchor_with_the_same_address():
    mails = _with_action()
    assert len(mails) >= 24
    for key, mail in mails.items():
        html = mail.html
        assert html.count("<v:roundrect") == 1, key
        vml = re.search(r'<v:roundrect [^>]*href="([^"]+)" style="height:44px;v-text-anchor:middle;width:(\d+)px;" arcsize="14%"', html)
        anchor = re.search(r'<a class="ca-btn-link" href="([^"]+)" style="display:block;height:44px;line-height:44px;padding:0 24px;', html)
        assert vml and anchor and vml.group(1) == anchor.group(1), key
        label = re.search(r"<center [^>]*>([^<]+)</center>", html).group(1)
        assert int(vml.group(2)) == c.button_width_px(label), key
        assert re.search(r'<td class="ca-btn-cell" align="center" bgcolor="#5A4FCF" style="border-radius:6px;mso-padding-alt:0 24px;', html), key
        assert '<span style="color:#FFFFFF;">' in html, key
        # Word 가 padding 을 버리는 옛 앵커(작은 보라 상자 + 튀어나온 글자)는 없다.
        assert not re.search(r"inline-block;\s*padding", html), key


def test_button_width_counts_wide_and_narrow_letters():
    assert c.button_width_px("메일 설정 열기") == 48 + 6 * 15 + 2 * 9
    assert c.button_width_px("ClovirAssist에서 보기") == 48 + 13 * 9 + 4 * 15
    assert c.button_width_px("가" * 60) == 520


def test_every_line_height_is_px_and_word_gets_exact_lines():
    for key, mail in _all_previews().items():
        values = re.findall(r"line-height:\s*([^;\"]+)", mail.html)
        assert values and all(v.strip().endswith("px") for v in values), (key, [v for v in values if not v.strip().endswith("px")])
        assert mail.html.count("mso-line-height-rule:exactly") >= 5, key


_TEXT_TAG = re.compile(r"<(td|p|h1|a)\b([^>]*)>([^<]*)")


def test_every_text_bearing_cell_carries_the_font_stack():
    """Word 는 모르는 첫 글꼴 이름이면 Times 로 떨어진다 - 글자가 있는 td · p · h1 · a 마다 스택을 직접 단다(첫 이름 Segoe UI)."""
    for key, mail in _all_previews().items():
        body = mail.html[mail.html.index("<body"):]
        assert "-apple-system" not in mail.html, key
        for tag, attrs, text in _TEXT_TAG.findall(body):
            visible = text.replace("&nbsp;", "").strip()
            if tag in ("p", "h1", "a") or visible:
                assert "font-family:" in attrs, (key, tag, attrs[:80], visible[:20])
                assert "font-family:'Segoe UI'" in attrs or "font-family:Consolas" in attrs, (key, attrs[:80])


def test_the_logo_is_one_36px_image_from_a_72px_png():
    import struct

    for key, mail in _all_previews().items():
        imgs = re.findall(r"<img [^>]+>", mail.html)
        assert len(imgs) == 1 and 'width="36" height="36"' in imgs[0] and "width:36px;height:36px" in imgs[0], key
    png = c.logo_png()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR"
    assert struct.unpack(">II", png[16:24]) == (72, 72), "2배 그림(72x72)을 36px 로 그린다"
    assert c.LOGO_FILE.name == "mark-72.png" and c.LOGO_SIZE == 36


def test_the_eyebrow_names_the_kind_in_both_parts():
    expected = {"ticket_assigned": "티켓 배정 알림", "invite": "계정 초대", "password_reset": "비밀번호 재설정",
                "account_locked": "계정 보안", "approval_requested": "승인 요청", "backup_failed": "운영 알림",
                "test": "시험 메일", "notify_email_verification": "주소 확인"}
    previews = _all_previews()
    for key, mail in previews.items():
        content = samples._BY_KEY[key][1]("ClovirAssist", BASE)
        assert content.eyebrow, key
        assert content.eyebrow in mail.text and content.eyebrow in mail.html, key
        if key in expected:
            assert content.eyebrow == expected[key], key
    # 표지와 같은 낱말이면(계정 보안) 표지 하나만 선다 - 같은 말을 두 줄로 세우지 않는다.
    locked = previews["account_locked"].html
    assert locked.count(">계정 보안<") == 1 and 'class="ca-alert"' in locked


def _theme_tokens(mode: str) -> dict:
    theme = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "ui" / "theme.js").read_text(encoding="utf-8")
    block = theme[theme.index("const TOKENS = {"):]
    block = block[block.index(f"  {mode}: {{"):]
    block = block[:block.index("\n  },")]
    return dict(re.findall(r'^\s+(\w+): "(#[0-9A-Fa-f]{6})"', block, re.M))


def test_dark_values_mirror_the_product_dark_tokens():
    dark = _theme_tokens("dark")
    mapping = {"canvas": "canvas", "plate": "plate", "inset": "inset", "ink": "text", "muted": "muted", "line": "line",
               "rule": "rule", "line_strong": "lineStrong", "danger": "danger", "danger_bg": "dangerBg"}
    for ours, theirs in mapping.items():
        assert c.COLORS_DARK[ours].upper() == dark[theirs].upper(), ours
    brand = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "ui" / "BrandLogo.jsx").read_text(encoding="utf-8")
    assert re.search(r'INVERSE_INK = \{ accent: "' + c.COLORS_DARK["accent"] + '"', brand)


def test_two_dark_rule_sets_and_the_header_band_stays_white():
    for key, mail in _all_previews().items():
        html = mail.html
        media = html[html.index("@media (prefers-color-scheme: dark)"):]
        media = media[:media.index("</style>")]
        assert c.COLORS_DARK["plate"] in media and c.COLORS_DARK["ink"] in media, key
        assert ".ca-head" not in media, "머리 띠는 다크 규칙에서 빠진다"
        assert "[data-ogsc] .ca-ink" in html and "[data-ogsb] .ca-plate" in html, key
        # 강제 다크(Outlook.com)에서도 머리 띠는 흰색으로 고정한다.
        assert "[data-ogsc] .ca-head, [data-ogsb] .ca-head { background-color: #FFFFFF !important;" in html, key
        assert re.search(r'<td class="ca-head" bgcolor="#FFFFFF"', html), key


def test_force_dark_adds_only_the_data_ogsc_attribute():
    content = samples._BY_KEY["ticket_assigned"][1]("ClovirAssist", BASE)
    plain = c.render(content).html
    forced = c.render(content, force_dark=True).html
    assert forced.replace(' data-ogsc=""', "", 1) == plain and forced.count(' data-ogsc=""') == 1


def test_fact_rows_are_tight_classed_rows_without_nowrap():
    mail = samples.preview("test", product="ClovirAssist", base_url=BASE)
    facts = mail.html[mail.html.index('class="ca-facts"'):]
    facts = facts[:facts.index("</table>")]
    assert facts.count('<tr class="ca-fact">') == 4
    assert facts.count('<td class="ca-fact-label ca-muted" width="120"') == 4
    assert "nowrap" not in facts and "line-height:1." not in facts
    assert 'bgcolor="#F5F6FB"' in mail.html[mail.html.index('class="ca-facts"') - 200:mail.html.index('class="ca-facts"') + 200]


def test_outlook_fallback_address_breaks_before_the_query():
    html = samples.preview("password_reset", product="ClovirAssist", base_url=BASE).html
    mso = re.search(r"<!--\[if mso\]>\s*<p [^>]*>([^<]*)<br>([^<]*)</p>\s*<!\[endif\]-->", html)
    assert mso and mso.group(1) == f"{BASE}/reset-password" and mso.group(2).startswith("?token=")
    assert c.fallback_parts(f"{BASE}/#/tickets/ABC-12") == (f"{BASE}/#/tickets/ABC-12", "")


def test_footer_is_three_lines_and_says_no_reply():
    mail = samples.preview("ticket_assigned", product="ClovirAssist", base_url=BASE, support="help@example.com")
    footer = mail.html[mail.html.rindex('class="ca-rule"'):]
    assert footer.count("<p ") == 3
    assert "이 주소로는 답장할 수 없습니다." in footer and "알림 메일 설정 열기</a>" in footer and "문의: help@example.com" in footer
    assert 'class="ca-sep"' in footer and "·" not in footer
    assert "알림 메일 설정 열기: " + BASE + "/#/profile | 문의: help@example.com" in mail.text
    assert mail.text.rstrip().endswith("이 주소로는 답장할 수 없습니다.")


def test_headers_reply_to_and_list_unsubscribe_for_notifications_only():
    from app.mail.config import smtp_config
    from app.mail.transport import build_message

    config = smtp_config({"enabled": True, "host": "smtp.example.com", "from_address": "noreply@example.com"})
    for key, mail in _all_previews().items():
        notification = isinstance(samples._BY_KEY[key][1]("ClovirAssist", BASE).unsubscribe_url, str)
        assert ("List-Unsubscribe" in mail.headers) is notification, key
        assert "Reply-To" not in mail.headers, "문의 주소가 없으면 Reply-To 도 없다"
    note = samples.preview("ticket_assigned", product="ClovirAssist", base_url=BASE, support="help@example.com")
    assert note.headers == {"Reply-To": "help@example.com", "List-Unsubscribe": f"<{BASE}/#/profile>"}
    invite = samples.preview("invite", product="ClovirAssist", base_url=BASE, support="help@example.com")
    assert invite.headers == {"Reply-To": "help@example.com"}
    message = build_message(config, to_email="kim@example.com", subject=note.subject, body=note.text, html=note.html,
                            reply_to=note.headers["Reply-To"], list_unsubscribe=note.headers["List-Unsubscribe"])
    assert message["Reply-To"] == "help@example.com" and message["List-Unsubscribe"] == f"<{BASE}/#/profile>"
    assert message["List-Unsubscribe-Post"] is None, "one-click 은 싣지 않는다(P-129)"
    bare = build_message(config, to_email="kim@example.com", subject="s", body="b")
    assert bare["Reply-To"] is None and bare["List-Unsubscribe"] is None
