"""티켓 본문 수정 — 지금 남은 것은 **권한과 정본**이다 (PLAN Phase 3 §E · S14).

## 예전에 이 파일이 무엇을 지켰나

정본(`tickets.body_markdown`)을 **먼저** 쓰고 그다음 Notion 블록을 push 하는 순서였다.
그 순서가 필요했던 이유는 정본이 두 곳(우리 표와 Notion 페이지)이었기 때문이고, 거기서
파생된 성질이 다섯이었다: push 실패해도 글이 남는다, 실패가 배너로 남는다, 재시도하면
배너가 사라진다, 교체는 삭제 → 추가 순서다, 남의 티켓은 못 고친다.

## 지금 남은 것과 사라진 것

정본이 한 곳뿐이라 **어긋날 짝이 없다**. push 실패·재시도·삭제 순서·원본 이미지 보존·너무
큰 원본 거절은 전부 그 두 번째 정본이 있어야 성립하던 성질이라 함께 사라졌다. 남은 것은
소스가 어디든 같아야 하는 것들이다: 범위 안의 티켓 본문은 담당자가 아니어도 고칠 수 있다,
운영자도 고칠 수 있다, 저장한 글이 상세 화면에 정본으로 돌아온다, 그리고 **컷오버 전에
찍혀 넘어온 오류 배너가 저장 한 번으로 사라진다**(어긋날 원본이 없어진 뒤에도 남으면
고칠 수 없는 경고가 된다).

본문의 마크다운 왕복과 빈 본문 처리는 저장소 계약이라
`tests/integration/test_native_ticket_repository.py` 가 본다. 티켓에 붙는 그림은 이제
Notion 블록이 아니라 우리 첨부 표이고, `tests/integration/test_ticket_attachments.py` 가
그 경로를 본다.

qa-contract-change: 두 번째 정본이던 Notion 페이지가 사라져 push 실패·재시도·블록 삭제 순서·원본 이미지 보존·거대 원본 거절은 판정할 대상 자체가 없다. 저장소가 어디든 같아야 하는 권한과 정본 응답만 남기고, 그 판정을 자체 DB 위에서 다시 세운다. 본문 왕복과 빈 본문은 저장소 계약 시험이 본다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.models_base import join_names
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
from app.tickets import service
from app.tickets.models import PROJECT_LINK_OK, TicketCache

pytestmark = pytest.mark.unit

PAGE_ID = "page-1"
#: 옛 입구(`body_markdown`)로 보내는 값. 서버가 이것을 정본 문서로 옮겨 저장한다.
BODY = "## 배경\n한 줄 적는다.\n- 항목"
#: 그 왕복의 결과. **정본은 이제 문서**이고(`tickets.body_doc`) 마크다운은 거기서 파생된다
#: (`app/knowledge/blocks.py::to_markdown`) — 블록 사이가 빈 줄 하나로 정규화된다.
#: 「보낸 글자 그대로」가 아니라 「같은 뜻의 정규형」이 계약이다. 문서 본문이 이미 그렇다.
BODY_STORED = "## 배경\n\n한 줄 적는다.\n\n- 항목"


@pytest.fixture()
def project(make_project):
    """이 파일의 티켓이 붙어 있는 Portal 프로젝트(조직 공통).

    0060 부터 티켓 소속은 프로젝트가 정한다 — 소속이 없으면 쓰기 경로가 404 로 막는다.
    이 파일이 검사하려는 것은 본문 저장 동작이므로 정상 소속을 미리 만들어 둔다.
    """
    return make_project(name="알파", external_id="px-1")


@pytest.fixture()
def ticket(db, project):
    """본문을 고칠 티켓 한 건. 담당자는 시험마다 다르므로 여기서 만들고 돌려준다."""
    def _make(*, people=None, body=None, sync_error=None) -> TicketCache:
        row = TicketCache(
            notion_page_id=PAGE_ID,
            org_id=project.org_id,
            notion_ticket_number=42,
            url=f"https://example.invalid/{PAGE_ID}",
            title="샘플",
            status="진행",
            due_date="2026-09-01",
            est_wd=2.0,
            project_ids=join_names(["px-1"]),
            project_names=join_names([project.name]),
            project_uid=project.id,
            project_link=PROJECT_LINK_OK,
            assignee_notion_ids=join_names(people or []),
            body_markdown=body,
            body_sync_error=sync_error,
        )
        db.add(row)
        db.commit()
        return row

    return _make


def _map(db, user, notion_id):
    db.add(UserNotionMapping(user_id=user.id, notion_user_id=notion_id,
                             status=STATUS_VERIFIED))
    db.commit()


def _row(db) -> TicketCache | None:
    db.expire_all()
    return db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == PAGE_ID)
    ).scalar_one_or_none()


def _save(db, settings, user, body=BODY):
    """자체 DB 저장소는 `outbound` 를 쓰지 않으므로 넘기지 않는다."""
    return service.save_ticket_body(
        db, None, settings, user, page_id=PAGE_ID, body_markdown=body
    )


# ── 정상 저장 ────────────────────────────────────────────────────────────────

def test_body_is_stored_as_the_record(db, settings, make_user, ticket):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ticket(people=["notion-me"])

    out = _save(db, settings, me)

    # 응답에 push 상태가 없다 - 밀어 넣을 원본이 없어 「못 밀어 넣었다」가 성립하지 않는다.
    assert "synced" not in out, out
    assert "body_sync_error" not in out, out
    assert out["body_markdown"] == BODY_STORED
    row = _row(db)
    assert row.body_markdown == BODY_STORED
    # 컬럼은 남는다(이관 흔적). 저장이 그것을 비우는지는 아래 시험이 본다.
    assert row.body_sync_error is None and row.body_synced_at is not None


def test_a_stale_sync_banner_is_cleared_by_the_next_save(db, settings, make_user, ticket):
    """컷오버 전에 push 가 실패해 오류가 적힌 채 넘어온 행이 있다.

    어긋날 원본이 없어진 뒤에도 그 배너가 남으면 사용자는 **고칠 수 없는 경고**를 저장할
    때마다 다시 본다. 그래서 저장 한 번이 그 표시를 지운다.
    """
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ticket(people=["notion-me"], body="옛 본문", sync_error="원본에 밀어 넣지 못했습니다.")

    out = _save(db, settings, me)

    assert "body_sync_error" not in out, out
    assert _row(db).body_sync_error is None


# ── 범위 안의 편집 ────────────────────────────────────────────────────────────

def test_a_teammate_can_edit_someone_elses_ticket_body(db, settings, make_user, ticket):
    """담당은 소유가 아니다. 범위 안이면 남의 본문도 고치고, 글이 실제로 바뀐다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ticket(people=["notion-other"], body="원래 본문")

    out = _save(db, settings, me)

    assert out["body_markdown"] == BODY_STORED
    assert _row(db).body_markdown == BODY_STORED


def test_operator_can_edit_any_ticket_body(db, settings, make_user, ticket):
    op = make_user(email="op@goodmit.co.kr", display_name="운영", role="operator")
    ticket(people=["notion-other"])

    out = _save(db, settings, op)

    assert "synced" not in out, out
    assert _row(db).body_markdown == BODY_STORED


def test_an_unassigned_ticket_body_can_be_edited_by_anyone_in_scope(
    db, settings, make_user, ticket
):
    """미할당은 담당자가 필요한 일이다 — 범위 안이면 누구나 손댈 수 있다(속성 편집과 같다)."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    ticket(people=[])

    assert "synced" not in _save(db, settings, me)
    assert _row(db).body_markdown == BODY_STORED


# ── 상세 응답 ────────────────────────────────────────────────────────────────

def test_detail_returns_the_stored_body_as_the_record(db, settings, make_user, ticket):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ticket(people=["notion-me"])
    _save(db, settings, me)

    detail = service.ticket_detail(db, None, settings, me, page_id=PAGE_ID)

    assert detail["body_markdown"] == BODY_STORED
    # **언제나 정본이다.** 「소스에서 되읽은 근사치」라는 세 번째 상태가 사라졌으므로
    # 상세는 그 구분을 싣지 않고, 화면은 서식이 납작해진다는 경고를 띄울 수 없다.
    assert "body_is_local" not in detail, detail
    assert "body_sync_error" not in detail, detail
    assert [b["kind"] for b in detail["blocks"]] == ["heading_2", "paragraph", "bulleted"]


def test_a_ticket_that_never_had_a_body_opens_the_editor_empty(db, settings, make_user, ticket):
    """본문을 한 번도 안 쓴 티켓은 빈 목록이다 — 빈 줄 하나를 그리면 「비어 있음」이 안 보인다."""
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    _map(db, me, "notion-me")
    ticket(people=["notion-me"])

    detail = service.ticket_detail(db, None, settings, me, page_id=PAGE_ID)

    assert detail["blocks"] == []
    # 본문이 없는 것과 「원본에서 되읽은 근사치」는 이제 같은 상태다 - 근사치라는 것이 없다.
    assert "body_is_local" not in detail
    assert detail["body_markdown"] == ""
    assert detail["can_edit"] is True
