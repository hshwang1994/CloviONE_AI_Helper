"""Notion 티켓 댓글을 읽고 우리 모양으로 바꾸는 자리 (S14 · D11).

## 표본은 지어내지 않았다

아래 댓글 넷은 `var/migration-cache/cache/comments/` 에 내려받아 둔 **실제 응답**에서
그대로 옮긴 것이다(서명 주소만 짧게 줄였다). 지어낸 표본으로 시험하면 「우리가 상상한
모양」만 통과하고, 실제로 온 모양(줄바꿈이 든 코드 · 글 없이 파일만 있는 댓글 ·
사람이 아닌 작성자)은 아무도 안 본다.

## 캐시를 다시 안 받는 것이 계약이다

댓글 1,235쪽은 이미 디스크에 있다. 다시 받으면 Notion 이 초당 3요청이라 십 분이
넘고, 그 비용은 아무도 이 도구를 두 번 안 돌리게 만든다.
"""

from __future__ import annotations

import json

import pytest

from app.cli import migrate_cli
from app.migration import transform
from app.migration.source_notion import NotionSource, NotionSourceError

pytestmark = [pytest.mark.unit]


# ── 실측 표본 ────────────────────────────────────────────────────────────────

# 여러 줄짜리 자바 코드가 든 댓글. 줄바꿈이 사라지면 읽을 수 없는 한 줄이 된다.
CODE_BODY = (
    "\tString ticket = vimPort.acquireCloneTicket(connectionMng"
    ".getServiceContent().getSessionManager());\n\n"
    'String url = "vmrc://clone:" + ticket + "@" + getServer(server) '
    '+ ":443/?moid=" + vmRef.getValue();\nreturn url;'
)
CODE_COMMENT = {
    "object": "comment",
    "id": "268c5c5a-5684-80ba-94cb-001d34247b09",
    "parent": {"type": "page_id", "page_id": "265c5c5a-5684-801b-afe6-e6404fd68d58"},
    "discussion_id": "268c5c5a-5684-8068-8507-001c1239c318",
    "created_time": "2025-09-08T04:17:00.000Z",
    "last_edited_time": "2025-09-08T04:17:00.000Z",
    "created_by": {"object": "user", "id": "239d872b-594c-81fe-9f76-0002b01e5c21"},
    "rich_text": [{
        "type": "text",
        "text": {"content": CODE_BODY, "link": None},
        "annotations": {"bold": False, "italic": False, "strikethrough": False,
                        "underline": False, "code": False, "color": "default"},
        "plain_text": CODE_BODY,
        "href": None,
    }],
    "display_name": {"type": "user", "resolved_name": "황형섭"},
    "original_content_deleted": False,
}

# 같은 스레드의 답글. 원글보다 늦게 쓰였다.
REPLY_COMMENT = {
    "object": "comment",
    "id": "2aec5c5a-5684-8054-b756-001dcdad856b",
    "parent": {"type": "page_id", "page_id": "265c5c5a-5684-801b-afe6-e6404fd68d58"},
    "discussion_id": "268c5c5a-5684-8068-8507-001c1239c318",
    "created_time": "2025-11-17T01:19:00.000Z",
    "last_edited_time": "2025-11-17T01:19:00.000Z",
    "created_by": {"object": "user", "id": "239d872b-594c-81fe-9f76-0002b01e5c21"},
    "rich_text": [{
        "type": "text",
        "text": {"content": "큐브 내용에 이전 단계의 결재 의견 보여달라", "link": None},
        "annotations": {"bold": False, "italic": False, "strikethrough": False,
                        "underline": False, "code": False, "color": "default"},
        "plain_text": "큐브 내용에 이전 단계의 결재 의견 보여달라",
        "href": None,
    }],
    "display_name": {"type": "user", "resolved_name": "서윤경"},
    "original_content_deleted": False,
}

# 글은 없고 그림만 붙은 댓글. 실측 325건 중 17건이 이 모양이다.
ATTACHMENT_ONLY_COMMENT = {
    "object": "comment",
    "id": "344c5c5a-5684-80fc-bbf8-001dc888ed37",
    "parent": {"type": "page_id", "page_id": "292c5c5a-5684-804e-8d14-fb766270d442"},
    "discussion_id": "bdec5c5a-5684-8382-90cb-83a5587b491d",
    "created_time": "2026-04-16T03:59:00.000Z",
    "last_edited_time": "2026-04-16T03:59:00.000Z",
    "created_by": {"object": "user", "id": "239d872b-594c-81fe-9f76-0002b01e5c21"},
    "rich_text": [],
    "display_name": {"type": "user", "resolved_name": "서윤경"},
    "original_content_deleted": False,
    "attachments": [{
        "category": "image",
        "file": {
            "url": "https://prod-files-secure.s3.us-west-2.amazonaws.com/2557d037/"
                   "c8c11d76/image.png?X-Amz-Expires=3600",
            "expiry_time": "2026-08-24T01:09:01.108Z",
        },
    }],
}

# 사람이 아닌 작성자. S11 이 걷어낸 자동화가 남긴 자기 검증용 댓글 한 건이다.
BOT_COMMENT = {
    "object": "comment",
    "id": "39ec5c5a-5684-81c7-acee-001d96aa550f",
    "parent": {"type": "page_id", "page_id": "33cc5c5a-5684-8004-86f4-f3f792209273"},
    "discussion_id": "39ec5c5a-5684-81f7-b071-001c676ed2c4",
    "created_time": "2026-07-15T14:39:00.000Z",
    "last_edited_time": "2026-07-15T14:39:00.000Z",
    "created_by": {"object": "user", "id": "313c5c5a-5684-813f-b328-002709cafc20"},
    "rich_text": [{
        "type": "text",
        "text": {"content": "챗봇 댓글 기능 자동 검증입니다. 지워도 됩니다.", "link": None},
        "annotations": {"bold": False, "italic": False, "strikethrough": False,
                        "underline": False, "code": False, "color": "default"},
        "plain_text": "챗봇 댓글 기능 자동 검증입니다. 지워도 됩니다.",
        "href": None,
    }],
    "display_name": {"type": "integration",
                     "resolved_name": "ClovirONE Workflow Automation"},
    "original_content_deleted": False,
}

PAGE = "265c5c5a-5684-801b-afe6-e6404fd68d58"


# ── 변환 ─────────────────────────────────────────────────────────────────────


def test_a_comment_keeps_its_line_breaks_and_its_original_time():
    parsed = transform.parse_comment(CODE_COMMENT)
    assert parsed.body == CODE_BODY.strip()
    assert "\n" in parsed.body, "여러 줄 코드가 한 줄로 뭉쳤다"
    # naive UTC 다. 저장 계약이 UTC 이므로 tzinfo 를 달고 들어가면 안 된다.
    assert parsed.created_at.isoformat() == "2025-09-08T04:17:00"
    assert parsed.created_at.tzinfo is None
    assert parsed.author_notion_id == "239d872b-594c-81fe-9f76-0002b01e5c21"
    assert parsed.discussion_id == "268c5c5a-5684-8068-8507-001c1239c318"
    assert parsed.legacy_id == CODE_COMMENT["id"]
    assert parsed.page_id == PAGE


def test_a_comment_with_only_a_file_says_so_instead_of_landing_empty():
    """빈 글로 넣으면 화면에 아무 말도 없는 줄이 남는다."""
    parsed = transform.parse_comment(ATTACHMENT_ONLY_COMMENT)
    assert parsed.body == transform.COMMENT_ATTACHMENT_ONLY
    assert parsed.attachment_count == 1


def test_the_author_kind_is_carried_but_the_decision_is_not_made_here():
    """사람이 아닌 작성자도 **여기서는 거르지 않는다.**

    거르는 자리는 적재 하나여야 한다(`user_notion_mappings`). 두 곳이 판정하면 그 둘은
    언젠가 갈리고, 갈린 쪽이 남의 이름으로 남의 글을 적는다.
    """
    parsed = transform.parse_comment(BOT_COMMENT)
    assert parsed.author_kind == "integration"
    assert parsed.author_label == "ClovirONE Workflow Automation"
    assert parsed.author_notion_id == "313c5c5a-5684-813f-b328-002709cafc20"


def test_a_comment_without_an_id_is_left_out_instead_of_guessed():
    broken = {**CODE_COMMENT}
    broken.pop("id")
    assert transform.parse_comment(broken) is None
    parsed = transform.comments_of(PAGE, [CODE_COMMENT, broken, REPLY_COMMENT])
    assert [item.comment_id for item in parsed] == [
        CODE_COMMENT["id"], REPLY_COMMENT["id"],
    ]


# ── 캐시 (다시 안 받는다) ────────────────────────────────────────────────────


class _CountingSource(NotionSource):
    """`_call` 만 세는 얇은 껍데기. 네트워크는 안 탄다."""

    def __init__(self, cache_dir, pages=None) -> None:
        super().__init__(
            object(), secret_ref="", cache_dir=cache_dir, throttle_seconds=0,
        )
        self.calls: list[str] = []
        self._pages = pages or [{"results": [CODE_COMMENT], "has_more": False}]

    def _call(self, method: str, path: str, *, json_body=None) -> dict:
        self.calls.append(path)
        return self._pages[min(len(self.calls) - 1, len(self._pages) - 1)]


def _write_cache(source: NotionSource, page_id: str, rows) -> None:
    """이미 디스크에 있는 1,235개와 **같은 모양**으로 적는다: 배열 그대로."""
    (source.cache / "comments" / f"{page_id}.json").write_text(
        json.dumps(rows, ensure_ascii=False), encoding="utf-8"
    )


def test_a_page_that_is_already_downloaded_is_not_fetched_again(tmp_path):
    source = _CountingSource(tmp_path)
    _write_cache(source, PAGE, [CODE_COMMENT, REPLY_COMMENT])
    rows = source.page_comments(PAGE)
    assert source.calls == [], "이미 받아 둔 페이지를 다시 받았다"
    assert [row["id"] for row in rows] == [CODE_COMMENT["id"], REPLY_COMMENT["id"]]
    assert source.stats.comments_from_cache == 1
    assert source.stats.comments_seen == 2


def test_a_page_with_no_cache_file_is_fetched_and_written_in_the_same_shape(tmp_path):
    """반례. 위 시험이 「아무것도 안 한다」로 통과하지 않게 한다."""
    source = _CountingSource(tmp_path)
    rows = source.page_comments("page-new")
    assert len(source.calls) == 1
    assert source.calls[0].startswith("/v1/comments?block_id=page-new")
    assert [row["id"] for row in rows] == [CODE_COMMENT["id"]]
    written = json.loads(
        (source.cache / "comments" / "page-new.json").read_text(encoding="utf-8")
    )
    assert isinstance(written, list), "이미 있는 1,235개와 다른 모양으로 적었다"
    assert written[0]["id"] == CODE_COMMENT["id"]
    assert source.stats.comments_fetched == 1


def test_the_second_page_of_a_long_thread_is_followed(tmp_path):
    source = _CountingSource(tmp_path, pages=[
        {"results": [CODE_COMMENT], "has_more": True, "next_cursor": "c1"},
        {"results": [REPLY_COMMENT], "has_more": False},
    ])
    rows = source.page_comments("page-long")
    assert len(rows) == 2, "다음 쪽을 안 따라가면 스레드가 잘린다"
    assert "start_cursor=c1" in source.calls[1]


def test_an_unreadable_cache_file_is_refetched_not_read_as_empty(tmp_path):
    """🔴 빈 목록으로 읽으면 그 페이지는 「원본에 댓글이 없었다」로 통과한다."""
    source = _CountingSource(tmp_path)
    (source.cache / "comments" / "page-bad.json").write_text("{", encoding="utf-8")
    rows = source.page_comments("page-bad")
    assert len(source.calls) == 1
    assert len(rows) == 1


def test_a_truncated_thread_is_refused_instead_of_cached(tmp_path):
    """상한에 걸린 목록을 캐시에 적으면 다음 회차도 잘린 채로 읽는다."""
    source = _CountingSource(tmp_path, pages=[
        {"results": [CODE_COMMENT], "has_more": True, "next_cursor": "c"},
    ])
    with pytest.raises(NotionSourceError):
        source.page_comments("page-endless")
    assert not (source.cache / "comments" / "page-endless.json").exists()


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_reimport_bodies_moves_comments_by_default():
    args = migrate_cli.build_parser().parse_args(["reimport-bodies"])
    assert args.no_comments is False


def test_extract_can_prewarm_the_comment_cache():
    """캐시를 미리 못 채우면 그 왕복이 `dry-run` 안으로 들어간다."""
    args = migrate_cli.build_parser().parse_args(
        ["extract", "--sqlite", "legacy.sqlite3", "--comments"]
    )
    assert args.comments is True


def test_comments_can_be_left_out_on_purpose():
    args = migrate_cli.build_parser().parse_args(
        ["reimport-bodies", "--no-comments"]
    )
    assert args.no_comments is True
    args = migrate_cli.build_parser().parse_args(
        ["dry-run", "--sqlite", "legacy.sqlite3", "--no-comments"]
    )
    assert args.no_comments is True
