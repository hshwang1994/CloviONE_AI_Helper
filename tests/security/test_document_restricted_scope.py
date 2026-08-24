"""문서 단위 열람 제한(SEC-10) — `document_cache.restricted`.

Notion 문서 1건에 평문 자격증명이 있고 이 앱의 미러가 그것을 인증된 사용자 전원에게
보여 주는 문제(`docs/BACKLOG.md` SEC-10)의 완화책. 원본 콘텐츠는 건드릴 수 없으므로
문서 단위 열람 범위를 좁히는 기능을 검증한다 — `test_document_scope.py`/
`test_team_docs_write_scope.py` 와 같은 fixture 관례를 그대로 따른다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

NID_MINE = "notion-doc-mine-r"

OP = "docr-op@goodmit.co.kr"          # 우리팀만 관리하는 부서 운영자
AUTHOR = "docr-author@goodmit.co.kr"  # 우리팀 일반 사용자(제한 문서의 작성자)
TEAMMATE = "docr-mate@goodmit.co.kr"  # 우리팀 일반 사용자(같은 부서, 작성자 아님)


@pytest.fixture()
def world(db, make_user, make_document):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    db.add(mine)
    db.flush()

    op = make_user(OP, role="operator", display_name="부서운영자")
    author = make_user(AUTHOR, role="user", display_name="작성자")
    mate = make_user(TEAMMATE, role="user", display_name="동료")
    op.department_id = mine.id
    op.admin_scope = "dept"
    op.scope_dept_id = mine.id
    author.department_id = mine.id
    mate.department_id = mine.id
    db.add(UserNotionMapping(user_id=author.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.commit()
    # 소속은 부서(우리팀)다. `restricted` 는 그 **위에 겹치는** 문서 단위 제한이라 소속이
    # 맞는 사람에게도 따로 막힌다 — 이 파일이 검사하는 것이 그 겹침이다(0060).
    make_document(page_id="dr", title="제한 문서", dept=mine,
                  author_notion_ids=[NID_MINE], restricted=True)
    make_document(page_id="du", title="일반 문서", dept=mine,
                  author_notion_ids=[NID_MINE], restricted=False)


def _hdr(login_as, email, role):
    return {"X-CSRF-Token": login_as(role, email=email)}


def _titles(client):
    return {d["title"] for d in client.get("/api/team-docs").json()["items"]}


# ── 읽기(목록·상세) ──────────────────────────────────────────────────────────

def test_a_restricted_doc_is_hidden_from_a_same_department_teammate(client, login_as, world):
    """같은 부서 동료라도 `restricted` 이면 안 보인다 — 부서 범위와는 다른 축이다."""
    login_as("user", email=TEAMMATE)
    titles = _titles(client)
    assert "일반 문서" in titles
    assert "제한 문서" not in titles, "같은 부서 동료에게 제한 문서가 그대로 보인다"
    assert client.get("/api/team-docs/dr").status_code == 404, "목록에서 가린 것이 id 로 열린다"


def test_a_restricted_doc_is_still_visible_to_its_author(client, login_as, world):
    login_as("user", email=AUTHOR)
    assert "제한 문서" in _titles(client)
    assert client.get("/api/team-docs/dr").status_code == 200


def test_a_restricted_doc_is_visible_to_a_scoped_moderator(client, login_as, world):
    login_as("operator", email=OP)
    assert "제한 문서" in _titles(client)
    assert client.get("/api/team-docs/dr").status_code == 200


def test_a_global_admin_still_sees_restricted_documents(client, login_as, world):
    login_as("system_admin")
    assert "제한 문서" in _titles(client)


def test_the_total_count_accounts_for_the_restricted_document(client, login_as, world):
    login_as("user", email=TEAMMATE)
    body = client.get("/api/team-docs").json()
    assert body["total"] == len(body["items"]) == 1


# ── restricted 필드/can_restrict 노출 ────────────────────────────────────────

def test_the_restricted_field_and_can_restrict_flag_are_correct_per_viewer(client, login_as, world):
    login_as("user", email=AUTHOR)
    doc = client.get("/api/team-docs/dr").json()["document"]
    assert doc["restricted"] is True
    assert doc["can_restrict"] is False, "작성자는 운영자가 아니므로 토글 버튼을 못 봐야 한다"

    login_as("operator", email=OP)
    doc = client.get("/api/team-docs/dr").json()["document"]
    assert doc["can_restrict"] is True


# ── 토글 권한 ────────────────────────────────────────────────────────────────

def test_the_author_cannot_toggle_restriction_on_their_own_document(client, login_as, db, world):
    """제한을 스스로 풀 수 있으면 제한의 의미가 없다 — 삭제와 다른 축."""
    r = client.post("/api/team-docs/dr/restrict?on=false", headers=_hdr(login_as, AUTHOR, "user"))
    assert r.status_code == 403, r.text
    from app.team_docs.repository import get_by_page_id
    db.commit()
    assert get_by_page_id(db, "dr").restricted is True, "403 을 돌려주고도 실제로는 풀렸다"


def test_a_scoped_moderator_can_toggle_restriction_within_their_scope(client, login_as, db, world):
    from app.team_docs.repository import get_by_page_id

    r = client.post("/api/team-docs/du/restrict?on=true", headers=_hdr(login_as, OP, "operator"))
    assert r.status_code == 200, r.text
    assert r.json()["restricted"] is True
    # db.commit() (not expire_all) — this session's own open read transaction would otherwise
    # keep seeing a pre-write SQLite snapshot for the *next* check below, even after expiring
    # the ORM identity map (that only forces a re-SELECT, it doesn't end the transaction).
    db.commit()
    assert get_by_page_id(db, "du").restricted is True

    r = client.post("/api/team-docs/dr/restrict?on=false", headers=_hdr(login_as, OP, "operator"))
    assert r.status_code == 200, r.text
    assert r.json()["restricted"] is False
    db.commit()
    assert get_by_page_id(db, "dr").restricted is False


def test_toggling_off_makes_the_document_visible_to_the_team_again(client, login_as, db, world):
    client.post("/api/team-docs/dr/restrict?on=false", headers=_hdr(login_as, OP, "operator"))
    login_as("user", email=TEAMMATE)
    assert "제한 문서" in _titles(client), "제한을 풀었는데도 여전히 안 보인다"


def test_an_out_of_scope_moderator_gets_404_not_403(client, login_as, db, make_user, world):
    """범위 밖은 없는 문서와 같은 404 — 403 은 그 id 가 존재한다는 사실을 알려 준다."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    other_dept = Department(name="다른팀", org_id=DEFAULT_ORG_ID)
    db.add(other_dept)
    db.flush()
    other_op = make_user("docr-other-op@goodmit.co.kr", role="operator", display_name="다른팀 운영자")
    other_op.department_id = other_dept.id
    other_op.admin_scope = "dept"
    other_op.scope_dept_id = other_dept.id
    db.commit()

    r = client.post("/api/team-docs/du/restrict?on=true",
                     headers=_hdr(login_as, "docr-other-op@goodmit.co.kr", "operator"))
    assert r.status_code == 404, r.text


# ── 「최근 열람」 읽기 경로는 사라졌다 (S14 · C2) ────────────────────────────
#
# 여기에 「제한을 걸면 최근 열람에서도 사라진다」를 확인하는 시험이 있었다. 그 경로는
# `GET /api/team-docs/filters` 의 `recent` 였고, 옛 문서 화면 말고는 아무 데서도 안 그렸다.
# 화면이 사라지면서 그 응답 칸도 없앴다 — **읽는 곳이 없으므로 샐 곳도 없다.**
#
# 최근 열람 기록 자체는 정본 문서 쪽에 남아 있지만(`app/knowledge/recent_views.py`) 그것을
# 사람에게 보여 주는 화면이 아직 없다. 그 화면을 만드는 날, 이 시험과 같은 모양의 판정을
# **그 경로에** 다시 세워야 한다.
