"""자유게시판 서비스·스키마·업로드 유닛 테스트 (팀 공간 §18, 보안 §22).

qa-contract-change: 제안 글을 '진행' 으로 넘길 때 업무 티켓을 만들어 연결하던 경로를 사용자 결정으로 걷었다(2026-09-03) — 기능 개선 제안은 ClovirAssist 제품 자체에 대한 것이라 고객 프로젝트의 업무 티켓과 섞이면 담당자도 우선순위 기준도 다른 둘이 한 보드에 쌓인다. `_fit_for_ticket_description` 과 그 시험 넷은 잴 대상이 사라졌다. 티켓 폼 자신의 계약을 재던 시험은 남겼고, 게시판의 다른 단정(권한·알림·집계)은 한 줄도 줄이지 않았다.

qa-contract-change: 제안 글을 티켓 설명으로 옮길 때 자르던 규칙이 없어졌다 — 자르던 이유였던 「4000자·최대 100줄·한 줄 1900자」가 Notion 시절의 상한이라 함께 걷혔고, 「자르되 거절당하지 않는가」를 재던 단정을 「한 글자도 안 잘리는가」가 대신한다.
"""

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


# ── 제안 → 티켓 전환은 없어졌다 (사용자 결정, 2026-09-03)
#
# 여기 있던 `_fit_for_ticket_description` 시험 넷은 「제안 본문을 티켓 설명으로 옮길 때
# 안 자르는가」를 쟀다. 그 함수도, 그것을 부르던 전환 경로도 없어졌으므로 잴 대상이 없다
# — 기능 제안 게시판은 ClovirAssist 제품 자체에 대한 것이라 고객 프로젝트의 업무 티켓과
# 섞이면 안 된다(app/board/service.py::change_idea_status 의 머리말).
#
# 아래 한 시험은 남긴다. 그것이 재는 것은 게시판이 아니라 **티켓 폼 자신의 계약**이고,
# 그 계약은 그대로다.
def test_the_new_ticket_form_demands_an_estimate_and_a_due_date():
    """**사람이 만드는 티켓**의 계약은 더 엄하다 (지시 10).

    `TicketDraft` 는 예상 WD·마감일 없이도 서지만 `TicketCreate` 는 둘을 요구한다.
    두 계약이 조용히 같아지면 「새 티켓」 화면이 빈 값을 받아 넘기게 된다.
    """
    import pytest as _pytest
    from pydantic import ValidationError

    from app.tickets.schemas import TicketCreate

    with _pytest.raises(ValidationError):
        TicketCreate(title="t", project_id="p1")
    # 둘을 채우면 통과한다 — 막는 것은 「안 적은 것」이지 값 자체가 아니다.
    TicketCreate(title="t", project_id="p1", est_wd=0, due_date="2026-12-31")

