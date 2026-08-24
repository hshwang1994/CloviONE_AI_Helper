"""문서 **휴지통 이동**도 범위를 지킨다 (§0-A).

목록·상세는 `doc_in_scope` 로 좁혀 놨는데 `POST /{page_id}/trash` 는 `page_id` 를 그대로
받았다. 목록에서 가린 문서를 **id 하나로 휴지통에 넣을 수 있었다** — 읽기 유출이 아니라
남의 범위에서의 **쓰기 실행**이다.

휴지통 이동이 `ensure_can_delete_doc` 를 지나니 안전해 보이지만, 그건 **작성자/운영자
판정**이지 범위 판정이 아니다: 다른 부서 운영자는 그냥 통과한다. 문서가 사라진 팀은 원인도
못 찾는다 — 휴지통 항목은 **지운 사람의 범위**에 남기 때문이다(`app/trash/repository.py`).

## ⚠️ 작성자를 해석할 수 없는 문서는 **여전히 휴지통에 넣을 수 있어야 한다**

`author_notion_ids` 는 다음 동기화가 채우므로 지금은 대부분 비어 있다. 그걸 범위 밖으로
치면 **아무도 자기 문서를 지우지 못한다** — 고치려던 것보다 나쁜 상태다. 목록이 이미 그
성질을 갖고 있고(tests/security/test_document_scope.py), 쓰기도 **같은 판정**이어야 한다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-doc-mine", "notion-doc-theirs"

OP = "docw-op@goodmit.co.kr"          # 우리팀만 관리하는 부서 범위 운영자
AUTHOR = "docw-author@goodmit.co.kr"  # 우리팀 일반 사용자(우리팀 문서의 작성자)
OTHER = "docw-other@goodmit.co.kr"    # 남의팀 일반 사용자


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 팀 사람 + 우리팀만 보는 운영자 + 문서 셋(우리팀·남의팀·작성자 미해석)."""
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.team_docs.models import DocumentCache

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    op = make_user(OP, role="operator", display_name="부서운영자")
    author = make_user(AUTHOR, role="user", display_name="작성자")
    other = make_user(OTHER, role="user", display_name="남")
    op.department_id = mine.id
    op.admin_scope = "dept"
    op.scope_dept_id = mine.id
    author.department_id = mine.id
    other.department_id = theirs.id
    db.add(UserNotionMapping(
        user_id=author.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.add(UserNotionMapping(
        user_id=other.id, notion_user_id=NID_THEIRS, status=STATUS_VERIFIED))
    # 소속(0060)은 문서 자신이 든다. 마지막 문서는 작성자를 앱 계정으로 해석할 수 없는
    # 경우인데, 소속이 우리 팀이므로 우리 팀은 그대로 휴지통에 넣고 즐겨찾기할 수 있다.
    db.add_all([
        DocumentCache(notion_page_id="dm", title="우리팀 문서", author_notion_ids=NID_MINE,
                      owner_kind="department", owner_dept_id=mine.id),
        DocumentCache(notion_page_id="dt", title="남의팀 3분기 실적 보고서",
                      author_notion_ids=NID_THEIRS,
                      owner_kind="department", owner_dept_id=theirs.id),
        DocumentCache(notion_page_id="dn", title="작성자 미해석 문서", author_notion_ids="",
                      owner_kind="department", owner_dept_id=mine.id),
    ])
    db.commit()


def _hdr(login_as, email=OP, role="operator"):
    return {"X-CSRF-Token": login_as(role, email=email)}


def _in_trash(db, page_id: str) -> bool:
    from app.trash import repository as trash_repo
    from app.trash.models import TRASH_DOCUMENT

    db.expire_all()
    return trash_repo.get_by_page(db, TRASH_DOCUMENT, page_id) is not None


# 즐겨찾기는 여기 없다 (S14 · C2). 그 축은 정본 문서로 옮겼고, 「범위 밖 문서를 담을 수
# 있는가」는 `tests/integration/test_knowledge_favorites.py` 가 같은 모양으로 고정한다.


# ── 범위 밖은 404 ────────────────────────────────────────────────────────────

def test_a_scoped_operator_cannot_trash_another_teams_document(client, login_as, db, world):
    """운영자 판정만으로는 못 막는다 — 다른 부서 운영자가 그 판정을 그냥 통과한다."""
    r = client.post("/api/team-docs/dt/trash", headers=_hdr(login_as))
    assert r.status_code == 404, f"남의 팀 문서를 휴지통에 넣을 수 있다: {r.status_code} {r.text}"
    assert not _in_trash(db, "dt"), "404 를 돌려주고도 문서가 실제로 휴지통에 들어갔다"


def test_the_bulk_trash_path_follows_the_same_rule(client, login_as, db, world):
    """일괄 경로는 건별로 같은 판정을 지나야 한다 — 여기만 열려 있으면 단건을 막은 의미가 없다.

    실패 사유에 **제목**이 실리면 안 된다. 없다고 답해 놓고 제목을 알려 주면 앞뒤가 안 맞는다.
    """
    r = client.post("/api/team-docs/trash-bulk", json={"page_ids": ["dt"]},
                    headers=_hdr(login_as))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["trashed"] == [], f"일괄 경로로 남의 팀 문서가 지워졌다: {body}"
    assert len(body["failed"]) == 1, body
    assert not _in_trash(db, "dt")
    assert "남의팀 3분기 실적 보고서" not in r.text, f"실패 사유에 제목이 새어 나간다: {r.text}"


# ── 오탐 방지 — 정상 경로는 여전히 된다 ──────────────────────────────────────

def test_a_document_without_resolvable_authors_can_still_be_trashed(client, login_as, db, world):
    """**가장 중요한 오탐 검사.** `author_notion_ids` 는 다음 동기화가 채우므로 지금 대부분
    비어 있다 — 그걸 범위 밖으로 치면 아무도 자기 문서를 못 지운다."""
    r = client.post("/api/team-docs/dn/trash", headers=_hdr(login_as))
    assert r.status_code == 200, f"작성자 미해석 문서를 못 지운다: {r.status_code} {r.text}"
    assert _in_trash(db, "dn")


def test_an_operator_can_still_trash_their_own_team(client, login_as, db, world):
    hdr = _hdr(login_as)
    r = client.post("/api/team-docs/dm/trash", headers=hdr)
    assert r.status_code == 200, f"자기 팀 문서를 못 지운다: {r.status_code} {r.text}"
    assert _in_trash(db, "dm")


def test_the_author_can_still_trash_their_own_document(client, login_as, db, world):
    """운영자가 아닌 **작성자 본인** 경로 — 범위 판정을 앞에 붙이면서 여기가 막히기 쉽다."""
    r = client.post("/api/team-docs/dm/trash", headers=_hdr(login_as, email=AUTHOR, role="user"))
    assert r.status_code == 200, f"작성자가 자기 문서를 못 지운다: {r.status_code} {r.text}"
    assert _in_trash(db, "dm")


def test_a_global_admin_still_operates_on_everything(client, login_as, db, world):
    """전역 관리자까지 좁히면 운영이 멈춘다."""
    hdr = {"X-CSRF-Token": login_as("system_admin")}
    r = client.post("/api/team-docs/dt/trash", headers=hdr)
    assert r.status_code == 200, f"전역 관리자가 문서를 못 지운다: {r.status_code} {r.text}"
    assert _in_trash(db, "dt")


def test_a_missing_page_id_is_the_same_404_as_an_out_of_scope_one(client, login_as, world):
    """두 답이 다르면 id 를 찍어 보며 **존재하는 문서를 열거**할 수 있다."""
    hdr = _hdr(login_as)
    missing = client.post("/api/team-docs/no-such-page/trash", headers=hdr)
    hidden = client.post("/api/team-docs/dt/trash", headers=hdr)
    assert missing.status_code == hidden.status_code == 404
    assert missing.json()["error"]["message"] == hidden.json()["error"]["message"], (
        f"응답 문구가 달라 존재 여부가 새어 나간다: {missing.text} vs {hidden.text}"
    )
