"""티켓 본문 수정 — 저장 순서가 이 기능의 전부다 (PLAN Phase 3 §E).

정본(`ticket_cache.body_markdown`)을 **먼저** 쓰고 그다음 Notion 블록을 push 한다. 반대로 하면
Notion 이 죽은 날 사용자가 방금 친 글이 통째로 사라진다. 여기서 못박는 성질:

  1. Notion push 가 실패해도 본문은 우리 DB 에 남는다(예외로 던지지 않는다 — 던지면 요청
     트랜잭션이 롤백돼 방금 저장한 본문까지 되돌아간다).
  2. 실패 사실이 응답과 행(`body_sync_error`)에 남는다 — 조용히 성공한 척하지 않는다.
  3. 재시도가 성공하면 그 표시가 사라진다.
  4. 본문 교체는 **기존 블록 삭제 → 새 블록 추가** 순서다. 이 순서라야 실패 후 같은 본문으로
     다시 저장하면 원하는 상태로 수렴한다(반대 순서는 실패할 때마다 본문이 한 벌씩 늘어난다).
  5. 남의 티켓 본문은 못 고친다 — 속성 편집과 같은 소유권 규칙을 쓴다.
"""

from __future__ import annotations

import pytest

from app.core.errors import ForbiddenError
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.tickets import service
from app.tickets.models import TicketCache

pytestmark = pytest.mark.unit

_SCHEMA = {
    "제목": {"type": "title"},
    "진행상태": {"type": "status", "status": {"options": [{"name": "진행"}]}},
    "마감일": {"type": "date"},
    "티켓 담당자": {"type": "people"},
    "예상 WD": {"type": "number"},
    "티켓 ID": {"type": "unique_id"},
}


def _page(*, pid="page-1", people=None):
    return {
        "id": pid,
        "url": f"https://notion/{pid}",
        "properties": {
            "제목": {"title": [{"plain_text": "샘플"}]},
            "진행상태": {"status": {"name": "진행"}},
            "마감일": {"date": {"start": "2026-09-01"}},
            "티켓 담당자": {"people": [{"id": p} for p in (people or [])]},
            "예상 WD": {"number": 2.0},
            "티켓 ID": {"unique_id": {"number": 42}},
        },
    }


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _FakeOutbound:
    """블록 읽기/삭제/추가까지 흉내내는 Notion 대역. 호출 순서를 그대로 기록한다.

    `block_write_status` 는 **쓰기 경로만** 실패시킨다 — 전부 실패시키면 소유권 확인용
    페이지 조회부터 죽어서 '본문은 저장됐는데 원본만 못 밀었다'라는 상황 자체가 안 만들어진다.
    """

    def __init__(self, *, page, blocks=None, block_write_status=None):
        self.page = page
        self.blocks = list(blocks or [])
        self.block_write_status = block_write_status
        self.trace: list[tuple[str, str]] = []   # (method, path) 순서대로
        self.appended: list[list[dict]] = []

    def request(self, method, url, **kwargs):
        path = url.split("api.notion.com", 1)[-1].split("?", 1)[0]
        self.trace.append((method, path))
        if method == "GET" and "/v1/databases/" in url:
            return _Resp(200, {"properties": _SCHEMA})
        if method == "GET" and "/v1/pages/" in url:
            return _Resp(200, self.page)
        if "/v1/blocks/" in url and method in ("PATCH", "DELETE"):
            if self.block_write_status is not None:
                return _Resp(self.block_write_status, {"message": "블록 쓰기 거부"})
            if method == "PATCH":
                children = (kwargs.get("json") or {}).get("children") or []
                self.appended.append(children)
                self.blocks.extend({**c, "id": f"new-{i}"} for i, c in enumerate(children))
                return _Resp(200, {"results": children})
            block_id = path.rsplit("/", 1)[-1]
            self.blocks = [b for b in self.blocks if b.get("id") != block_id]
            return _Resp(200, {"archived": True})
        if method == "GET" and "/v1/blocks/" in url:
            for index, block in enumerate(self.blocks):
                block.setdefault("id", f"block-{index}")
            return _Resp(200, {"results": self.blocks, "has_more": False})
        raise AssertionError(f"unexpected {method} {url}")


def _map(db, user, notion_id):
    db.add(UserNotionMapping(user_id=user.id, notion_user_id=notion_id,
                             status=STATUS_VERIFIED))
    db.commit()


def _row(db, page_id="page-1") -> TicketCache | None:
    from sqlalchemy import select

    return db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == page_id)
    ).scalar_one_or_none()


BODY = "## 배경\n한 줄 적는다.\n- 항목"


# ── 정상 저장 ────────────────────────────────────────────────────────────────

def test_body_is_stored_and_pushed(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]))

    out = service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown=BODY)

    assert out["synced"] is True
    assert out["body_sync_error"] is None
    row = _row(db)
    assert row is not None and row.body_markdown == BODY
    assert row.body_sync_error is None and row.body_synced_at is not None
    # 마크다운이 블록으로 변환돼 실제로 올라갔다.
    assert ob.appended and ob.appended[0][0]["type"] == "heading_2"


def test_existing_blocks_are_deleted_before_new_ones_are_appended(db, settings, make_user):
    """순서가 뒤집히면 실패 후 재시도할 때마다 본문이 한 벌씩 늘어난다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(
        page=_page(people=["notion-me"]),
        blocks=[{"id": "old-1", "type": "paragraph", "paragraph": {"rich_text": []}},
                {"id": "old-2", "type": "paragraph", "paragraph": {"rich_text": []}}],
    )

    service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown=BODY)

    kinds = [m for m, p in ob.trace if "/v1/blocks/" in p]
    assert kinds.count("DELETE") == 2
    assert kinds.index("PATCH") > max(i for i, m in enumerate(kinds) if m == "DELETE")


# ── 비텍스트 블록 보존 (2026-08-04 제품화 지시) ───────────────────────────────

def test_saving_the_body_does_not_delete_images_or_tables(db, settings, make_user):
    """저장 한 번에 원본의 이미지·표가 사라지던 것을 막는다.

    예전에는 1레벨 children 을 **전부** 지우고 새로 넣었다. 이미지는 편집기에 실려 오지도
    않는데(마크다운으로 표현할 수 없어 자리표시로 바뀐다) 저장하면 사라졌다 — 사용자는 자기가
    무엇을 지웠는지도 몰랐다.

    사용자 지시로 이 포털이 노션을 대신하는 유일한 창구가 되면 그 유실은 곧 데이터 유실이다.
    지웠다 다시 만드는 길은 없다: Notion 호스팅 파일은 만료되는 서명 URL 로만 읽히고 API 로
    재생성할 수 없다. **안 지우는 것이 유일한 방법이다.**
    """
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(
        page=_page(people=["notion-me"]),
        blocks=[
            {"id": "text-1", "type": "paragraph", "paragraph": {"rich_text": []}},
            {"id": "img-1", "type": "image", "image": {"type": "file", "file": {"url": "https://x/y.png"}}},
            {"id": "table-1", "type": "table", "table": {"table_width": 2}},
            {"id": "text-2", "type": "paragraph", "paragraph": {"rich_text": []}},
            {"id": "div-1", "type": "divider", "divider": {}},
        ],
    )

    service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown=BODY)

    deleted = [p.rsplit("/", 1)[-1] for m, p in ob.trace if m == "DELETE" and "/v1/blocks/" in p]
    # 우리가 표현할 수 있는 것만 지웠다.
    assert sorted(deleted) == ["div-1", "text-1", "text-2"], f"지운 목록이 다르다: {deleted}"
    # 이미지와 표는 **손대지 않았다** — 이 두 줄이 이 테스트의 전부다.
    assert "img-1" not in deleted
    assert "table-1" not in deleted
    surviving = {b.get("id") for b in ob.blocks}
    assert {"img-1", "table-1"} <= surviving, f"이미지·표가 사라졌다: {surviving}"
    # 그리고 새 본문은 정상적으로 올라갔다.
    assert ob.appended and ob.appended[0][0]["type"] == "heading_2"


def test_a_body_with_only_images_is_left_alone(db, settings, make_user):
    """글이 하나도 없고 이미지만 있는 티켓에 빈 본문을 저장해도 이미지가 남는다.

    이 경우가 가장 위험했다 — 지울 글이 없으니 사용자는 '아무 일도 안 일어난다'고 생각하는데
    예전 코드는 이미지를 지웠다.
    """
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(
        page=_page(people=["notion-me"]),
        blocks=[{"id": "img-only", "type": "image", "image": {"type": "file", "file": {"url": "https://x/y.png"}}}],
    )

    service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown="")

    # 지울 것이 없으므로 DELETE 자체가 나가지 않고, 이미지는 그대로 남는다.
    # (빈 본문이라도 빈 문단 하나는 추가되므로 '블록이 이것 하나뿐'이라고 단언하지 않는다 —
    #  이 테스트가 지키는 것은 '이미지가 살아 있는가'다.)
    assert not [m for m, p in ob.trace if m == "DELETE" and "/v1/blocks/" in p]
    assert "img-only" in {b.get("id") for b in ob.blocks}


# ── Notion push 실패 ─────────────────────────────────────────────────────────

def test_body_survives_a_failed_notion_push(db, settings, make_user):
    """이 테스트가 통과하지 않으면 저장 순서를 지킨 의미가 없다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]), block_write_status=500)

    out = service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown=BODY)

    # 예외로 새어 나가지 않았고(요청이 롤백되지 않았고),
    assert out["synced"] is False
    # 왜 어긋났는지 사용자에게 말할 수 있고,
    assert out["body_sync_error"]
    # 무엇보다 사용자가 친 글이 살아 있다.
    row = _row(db)
    assert row is not None and row.body_markdown == BODY
    assert row.body_sync_error and row.body_synced_at is None


def test_retry_after_a_failed_push_clears_the_warning(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]), block_write_status=500)
    service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown=BODY)
    assert _row(db).body_sync_error

    ob.block_write_status = None  # Notion 이 돌아왔다
    out = service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown=BODY)

    assert out["synced"] is True
    row = _row(db)
    assert row.body_sync_error is None and row.body_synced_at is not None


def test_a_huge_source_body_is_refused_instead_of_being_deleted_block_by_block(
    db, settings, make_user
):
    """우리 편집기는 최대 100줄짜리 본문을 만든다. 그보다 훨씬 큰 원본을 여기서 교체한다는 건
    남이 Notion 에서 쓴 문서를 통째로 지운다는 뜻이고, 삭제가 블록당 DELETE 한 번이라
    요청 하나가 수백 왕복이 된다. 손대지 않고 거절하되, 사용자 글은 우리 쪽에 남긴다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    huge = [{"id": f"b{i}", "type": "paragraph", "paragraph": {"rich_text": []}}
            for i in range(201)]
    ob = _FakeOutbound(page=_page(people=["notion-me"]), blocks=huge)

    out = service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown=BODY)

    assert out["synced"] is False
    assert "너무 커서" in out["body_sync_error"]
    # 원본은 한 블록도 지우지 않았다.
    assert not any(m == "DELETE" for m, _ in ob.trace)
    assert len(ob.blocks) == 201
    # 그래도 사용자가 친 글은 우리 쪽에 저장돼 있다.
    assert _row(db).body_markdown == BODY


# ── 소유권 ───────────────────────────────────────────────────────────────────

def test_cannot_edit_someone_elses_ticket_body(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-other"]))

    with pytest.raises(ForbiddenError):
        service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown=BODY)

    assert not ob.appended            # 쓰기까지 가지 못했고
    assert _row(db) is None           # 캐시 행도 만들지 않았다


def test_operator_can_edit_any_ticket_body(db, settings, make_user):
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    ob = _FakeOutbound(page=_page(people=["notion-other"]))

    out = service.save_ticket_body(db, ob, settings, op, page_id="page-1", body_markdown=BODY)

    assert out["synced"] is True


# ── 상세 응답 ────────────────────────────────────────────────────────────────

def test_detail_returns_stored_body_and_the_sync_warning(db, settings, make_user):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(page=_page(people=["notion-me"]), block_write_status=500)
    service.save_ticket_body(db, ob, settings, me, page_id="page-1", body_markdown=BODY)

    ob.block_write_status = None  # 읽기는 원래부터 살아 있었다
    detail = service.ticket_detail(db, ob, settings, me, page_id="page-1")

    assert detail["body_markdown"] == BODY
    assert detail["body_is_local"] is True
    assert detail["body_sync_error"]


def test_detail_falls_back_to_the_source_body_when_we_have_no_canonical_copy(
    db, settings, make_user
):
    """편집기를 빈 채로 열면 '저장'이 곧 본문 삭제가 된다 — 그래서 소스 본문을 되읽어 준다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(
        page=_page(people=["notion-me"]),
        blocks=[{"id": "b1", "type": "heading_2",
                 "heading_2": {"rich_text": [{"plain_text": "배경"}]}},
                {"id": "b2", "type": "paragraph",
                 "paragraph": {"rich_text": [{"plain_text": "본문 한 줄."}]}}],
    )

    detail = service.ticket_detail(db, ob, settings, me, page_id="page-1")

    assert detail["body_markdown"] == "## 배경\n본문 한 줄."
    # 근사치라는 사실을 함께 알린다 — 이걸 그대로 저장하면 서식이 평문으로 납작해진다.
    assert detail["body_is_local"] is False
    assert detail["body_sync_error"] is None


# ── 이미지 블록 노출 (사용자 지시 §4) ─────────────────────────────────────────

def test_image_blocks_reach_the_screen_with_a_url(db, settings, make_user):
    """티켓에 붙은 이미지를 화면에서 **볼 수 있어야** 한다.

    예전에는 이미지 블록이 `{"kind":"unsupported","text":"[image] 원본에서 확인"}` 이라는
    문자열로 바뀌어 회색 글씨로만 나왔다. AI 도우미로 티켓을 만들 때 붙인 이미지가 정확히
    이 경로로 사라져, 포털에서는 그림이 있었다는 사실만 알 수 있고 볼 수는 없었다.

    URL 을 프록시하지 않고 그대로 내려보내는 이유는 notion_write._image_view 주석에 있다.
    """
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(
        page=_page(people=["notion-me"]),
        blocks=[
            {"id": "p1", "type": "paragraph",
             "paragraph": {"rich_text": [{"plain_text": "설명"}]}},
            {"id": "i1", "type": "image",
             "image": {"type": "file", "file": {"url": "https://files.example/x.png"},
                       "caption": [{"plain_text": "장애 화면"}]}},
            {"id": "i2", "type": "image",
             "image": {"type": "external", "external": {"url": "https://ext.example/y.png"}}},
        ],
    )

    detail = service.ticket_detail(db, ob, settings, me, page_id="page-1")
    images = [b for b in detail["blocks"] if b.get("kind") == "image"]

    assert len(images) == 2, f"이미지 블록이 화면까지 오지 않았다: {detail['blocks']}"
    # 호스팅 파일과 외부 URL 둘 다 다룬다 — 둘은 Notion 응답 모양이 다르다.
    assert images[0]["url"] == "https://files.example/x.png"
    assert images[0]["text"] == "장애 화면"      # 캡션은 그림 아래 설명으로 쓴다
    assert images[1]["url"] == "https://ext.example/y.png"
    # 자리표시 문자열은 더 이상 나오지 않는다.
    assert not [b for b in detail["blocks"] if b.get("kind") == "unsupported"]


def test_an_image_block_we_cannot_read_stays_a_placeholder(db, settings, make_user):
    """모르는 모양이면 자리표시로 둔다 — 깨진 <img> 를 그리는 것보다 낫다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ob = _FakeOutbound(
        page=_page(people=["notion-me"]),
        blocks=[{"id": "i1", "type": "image", "image": {"type": "file"}}],   # url 없음
    )

    detail = service.ticket_detail(db, ob, settings, me, page_id="page-1")

    assert [b["kind"] for b in detail["blocks"]] == ["unsupported"]
