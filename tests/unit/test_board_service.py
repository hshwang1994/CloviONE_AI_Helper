"""자유게시판 서비스·스키마·업로드 유닛 테스트 (팀 공간 §18, 보안 §22)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.board import repository, service
from app.board.models import TARGET_POST
from app.board.schemas import CommentCreate, PostCreate, PostUpdate, ReactionInput
from app.core import uploads
from app.core.errors import ForbiddenError, ValidationAppError
from app.core.models_base import utcnow

pytestmark = pytest.mark.unit


# 유효한 매직바이트 샘플.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 16
PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"\x00" * 16


# ── uploads (순수 함수) ──────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "data,expected",
    [
        (PNG, "image/png"),
        (JPEG, "image/jpeg"),
        (GIF, "image/gif"),
        (WEBP, "image/webp"),
        (PDF, "application/pdf"),
        (b"not an image at all", None),
        (b"<html>", None),
        (b"", None),
    ],
)
def test_sniff_media_type(data, expected):
    assert uploads.sniff_media_type(data[:16]) == expected


def test_sanitize_filename_strips_paths_and_traversal():
    assert uploads.sanitize_filename("../../etc/passwd") == "etc_passwd" or "passwd" in uploads.sanitize_filename("../../etc/passwd")
    assert "/" not in uploads.sanitize_filename("a/b/c.png")
    assert "\\" not in uploads.sanitize_filename("a\\b\\c.png")
    assert uploads.sanitize_filename("") == "file"
    assert uploads.sanitize_filename("사진.png") == "사진.png"


def test_save_upload_rejects_bad_type(tmp_path):
    with pytest.raises(ValidationAppError):
        uploads.save_upload(tmp_path, "p1", filename="x.png", content=b"nope not image")


def test_save_upload_rejects_oversize(tmp_path):
    big = PNG + b"\x00" * (uploads.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ValidationAppError):
        uploads.save_upload(tmp_path, "p1", filename="big.png", content=big)


def test_save_upload_rejects_empty(tmp_path):
    with pytest.raises(ValidationAppError):
        uploads.save_upload(tmp_path, "p1", filename="e.png", content=b"")


def test_save_upload_ok_and_path_resolves(tmp_path):
    stored, media, size, display = uploads.save_upload(
        tmp_path, "post-123", filename="사진.png", content=PNG
    )
    assert media == "image/png"
    assert size == len(PNG)
    assert display == "사진.png"
    assert stored.endswith(".png")
    path = uploads.attachment_path(tmp_path, "post-123", stored)
    assert path is not None and path.is_file()
    assert path.read_bytes() == PNG


def test_attachment_path_rejects_traversal(tmp_path):
    # 서버 생성 패턴이 아닌 저장명은 거절(경로 조작 방지).
    assert uploads.attachment_path(tmp_path, "p1", "../../secret") is None
    assert uploads.attachment_path(tmp_path, "p1", "evil.png") is None
    assert uploads.attachment_path(tmp_path, "p1", "") is None


# ── 스키마 검증 ──────────────────────────────────────────────────────────────
def test_post_create_rejects_unknown_category():
    with pytest.raises(ValidationError):
        PostCreate(category="정치", title="x")


def test_post_create_rejects_empty_title():
    with pytest.raises(ValidationError):
        PostCreate(category="자유", title="   ")


def test_post_create_rejects_too_long_title():
    with pytest.raises(ValidationError):
        PostCreate(category="자유", title="a" * 201)


def test_post_create_strips_and_defaults_body():
    p = PostCreate(category="자유", title="  안녕  ")
    assert p.title == "안녕"
    assert p.body == ""


def test_post_update_rejects_extra_field():
    with pytest.raises(ValidationError):
        PostUpdate(is_pinned=True)  # 고정은 전용 엔드포인트로만 — 본문 수정으로 못 바꾼다


def test_comment_create_rejects_empty():
    with pytest.raises(ValidationError):
        CommentCreate(body="  ")


def test_reaction_rejects_bad_emoji_and_target():
    with pytest.raises(ValidationError):
        ReactionInput(target_type="post", target_id="x", emoji="🔥")  # 화이트리스트 밖
    with pytest.raises(ValidationError):
        ReactionInput(target_type="galaxy", target_id="x", emoji="👍")


# ── 서비스 규칙 (DB) ─────────────────────────────────────────────────────────
def test_ensure_can_edit_author_only(make_user):
    """수정은 작성자 본인만 — 운영자도 남의 글을 고쳐 쓸 수 없다(티켓·문서 댓글과 같은 규칙,
    step 9 #1). 예전엔 운영자도 통과했다 — 삭제 권한과 뭉뚱그려져 있었다."""
    author = make_user("author@goodmit.co.kr", role="user")
    other = make_user("other@goodmit.co.kr", role="user")
    admin = make_user("admin1@goodmit.co.kr", role="admin")

    service.ensure_can_edit(author.id, author)  # 본인 OK
    with pytest.raises(ForbiddenError):
        service.ensure_can_edit(author.id, admin)  # 운영자군도 불가 — 삭제와 다른 선
    with pytest.raises(ForbiddenError):
        service.ensure_can_edit(author.id, other)  # 남은 불가


def test_ensure_can_delete_author_and_moderator(make_user):
    author = make_user("d-author@goodmit.co.kr", role="user")
    other = make_user("d-other@goodmit.co.kr", role="user")
    admin = make_user("d-admin@goodmit.co.kr", role="admin")

    service.ensure_can_delete(author.id, author)  # 본인 OK
    service.ensure_can_delete(author.id, admin)  # 운영자군 OK(삭제는 여전히 가능)
    with pytest.raises(ForbiddenError):
        service.ensure_can_delete(author.id, other)  # 남은 불가


def test_can_moderate_roles(make_user):
    assert service.can_moderate(make_user("u@goodmit.co.kr", role="user")) is False
    assert service.can_moderate(make_user("op@goodmit.co.kr", role="operator")) is True
    assert service.can_moderate(make_user("ad@goodmit.co.kr", role="admin")) is True


def test_reaction_toggle_is_unique(db, make_user):
    user = make_user("r@goodmit.co.kr")
    now = utcnow()
    service.add_reaction(
        db, target_type=TARGET_POST, target_id="p1", user_id=user.id, emoji="👍", now=now
    )
    # 두 번째 add는 새 행을 만들지 않는다(멱등).
    service.add_reaction(
        db, target_type=TARGET_POST, target_id="p1", user_id=user.id, emoji="👍", now=now
    )
    rows = repository.reactions_for(db, TARGET_POST, ["p1"])
    assert len(rows) == 1
    # 제거하면 사라진다.
    assert service.remove_reaction(
        db, target_type=TARGET_POST, target_id="p1", user_id=user.id, emoji="👍"
    )
    assert repository.reactions_for(db, TARGET_POST, ["p1"]) == []


def test_one_level_reply_enforced(db, make_user):
    author = make_user("c@goodmit.co.kr")
    now = utcnow()
    post = service.create_post(
        db, author=author, category="자유", title="글", body="", now=now
    )
    top = service.create_comment(
        db, post=post, author=author, body="댓글", parent_comment_id=None, now=now
    )
    reply = service.create_comment(
        db, post=post, author=author, body="답글", parent_comment_id=top.id, now=now
    )
    # 답글에 다시 답글 → 거절.
    with pytest.raises(ValidationAppError):
        service.create_comment(
            db, post=post, author=author, body="답답글", parent_comment_id=reply.id, now=now
        )


def test_soft_delete_comment_cascades_to_replies(db, make_user):
    """부모 삭제는 답글도 함께 지운다(deleted_at 채움) — 살아있는 댓글 카운트는 0으로
    줄지만, `list_comments`는 **행을 지우지 않는다**(step 9 #4 — 툼스톤 규약,
    tests/integration/test_board_api.py::test_deleted_comment_is_a_tombstone_not_a_missing_row
    가 API 계약을 고정한다)."""
    author = make_user("cas@goodmit.co.kr")
    now = utcnow()
    post = service.create_post(db, author=author, category="자유", title="글", body="", now=now)
    top = service.create_comment(db, post=post, author=author, body="부모", parent_comment_id=None, now=now)
    reply = service.create_comment(db, post=post, author=author, body="답글", parent_comment_id=top.id, now=now)
    assert len(repository.list_comments(db, post.id)) == 2
    # 부모 삭제 → 답글도 함께 deleted_at 이 채워진다. 행 자체는 여전히 2개 남는다.
    service.soft_delete_comment(db, top, now=now)
    rows = {c.id: c for c in repository.list_comments(db, post.id)}
    assert set(rows) == {top.id, reply.id}, "삭제된 행이 목록에서 사라졌다 — 툼스톤 규약 위반"
    assert rows[top.id].deleted_at is not None
    assert rows[reply.id].deleted_at is not None
    assert repository.comment_count(db, post.id) == 0


def test_increment_view(db, make_user):
    author = make_user("v@goodmit.co.kr")
    now = utcnow()
    post = service.create_post(
        db, author=author, category="자유", title="조회", body="", now=now
    )
    assert post.view_count == 0
    service.increment_view(db, post)
    service.increment_view(db, post)
    assert post.view_count == 2
    fresh = repository.get_post(db, post.id)
    assert fresh.view_count == 2


def test_soft_delete_hides_post(db, make_user):
    author = make_user("d@goodmit.co.kr")
    now = utcnow()
    post = service.create_post(
        db, author=author, category="자유", title="삭제될글", body="", now=now
    )
    service.soft_delete_post(db, post, now=now)
    assert repository.get_post(db, post.id) is None  # 기본 조회에서 제외
    assert repository.get_post(db, post.id, include_deleted=True) is not None  # 행은 남음


# ── _fit_for_ticket_description — 제안→티켓 본문이 TicketCreate 를 통과하는 형태로 잘리는가
def test_fit_for_ticket_description_wraps_a_single_long_line():
    """줄바꿈 없는 긴 문단(게시글의 흔한 형태) — 예전엔 [:3900] 로만 잘라 한 줄이 여전히
    1900자를 넘어 TicketCreate._check_desc 가 결정적으로 거절했다."""
    from app.core.notion_blocks import MAX_LINE_CHARS

    body = "가" * 2500  # 줄바꿈 없는 한 문단
    fitted = service._fit_for_ticket_description(body)

    lines = fitted.split("\n")
    assert all(len(ln) <= MAX_LINE_CHARS for ln in lines), (
        f"줄 길이가 여전히 상한을 넘는다: {[len(ln) for ln in lines]}"
    )
    assert len(fitted) <= 3900
    # 내용은 보존된다(잘라 버리는 게 아니라 줄바꿈만 끼워 넣는다) — 총 길이가 4000자
    # 미만이므로 원문이 그대로 다 들어가야 한다.
    assert fitted.replace("\n", "") == body


def test_fit_for_ticket_description_passes_ticket_create_validation():
    """실제 관문(TicketCreate._check_desc)을 통과하는지 — 문자열 모양만 보지 않는다."""
    from app.tickets.schemas import TicketCreate

    body = "긴 문단입니다. " * 400  # 공백 섞인 긴 문단, 줄바꿈 없음
    fitted = service._fit_for_ticket_description(body)
    payload = TicketCreate(title="t", project_id="p1", description=fitted)  # 안 터지면 통과
    assert payload.description == fitted.strip()


def test_fit_for_ticket_description_caps_line_count():
    """줄 수가 MAX_BLOCKS 를 넘으면(개행이 아주 많은 본문) 뒤는 잘라낸다 — 총 글자수·
    줄 길이만 맞추고 줄 수는 안 맞추면 여전히 거절당한다."""
    from app.core.notion_blocks import MAX_BLOCKS

    body = "\n".join(f"줄{i}" for i in range(MAX_BLOCKS + 50))
    fitted = service._fit_for_ticket_description(body)
    assert len(fitted.split("\n")) <= MAX_BLOCKS


def test_fit_for_ticket_description_empty_stays_empty():
    assert service._fit_for_ticket_description("") == ""
    assert service._fit_for_ticket_description(None) == ""
