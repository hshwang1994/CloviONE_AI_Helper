"""문서가 언급한 티켓은 **티켓 축으로 좁혀서** 나간다 (지시 22.8 · D-194).

## 왜 이것이 보안 시험인가

문서와 티켓은 **다른 문으로 판정된다.** 문서는 공간의 가시성을 상속하고(§5.3), 티켓은
소속 프로젝트가 보이면 보인다. 그래서 「내가 볼 수 있는 문서」가 「내가 볼 수 없는 티켓」을
본문에서 언급하는 일은 정상 상태다 — 회의록 한 장이 여러 프로젝트의 티켓을 적는다.

그 문서를 열었을 때 상세가 멘션 표를 그대로 내면, 그 사람은 못 보는 티켓의 **번호와
제목**을 읽는다. 스프린트 회의 화면에서 정확히 같은 것을 놓칠 뻔했고(D-349 회차의 「문이
둘이다」), 여기서도 문이 둘이다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

ME = "dtm-me@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    from app.knowledge.models import Document, DocumentMention, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.projects.models import Project
    from app.tickets.models import Ticket

    mine = Department(name="멘션팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의 멘션팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    me = make_user(ME, role="user", display_name="나")
    me.department_id = mine.id

    # 공간은 **조직 전체**다 — 문서는 누구나 본다. 티켓만 갈린다.
    space = KnowledgeSpace(name="공통 공간", slug="dtm-space", owner_kind="organization",
                           org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()

    ours = Project(name="우리 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=mine.id)
    theirs_project = Project(name="남의 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=theirs.id)
    db.add_all([ours, theirs_project])
    db.flush()

    seen = Ticket(title="우리 티켓", project_uid=ours.id, org_id=DEFAULT_ORG_ID)
    hidden = Ticket(title="남의 티켓", project_uid=theirs_project.id, org_id=DEFAULT_ORG_ID)
    db.add_all([seen, hidden])
    db.flush()

    document = Document(space_id=space.id, title="두 프로젝트를 적은 회의록", created_by=me.id)
    db.add(document)
    db.flush()
    # 본문을 거치지 않고 멘션 표에 직접 심는다 — 여기서 보려는 것은 본문 파싱이 아니라
    # **응답이 무엇을 싣는가**다.
    db.add_all([
        DocumentMention(document_id=document.id, block_id="b1",
                        target_kind="ticket", target_id=seen.id),
        DocumentMention(document_id=document.id, block_id="b2",
                        target_kind="ticket", target_id=hidden.id),
    ])
    db.commit()
    return {"document": document.id, "seen": seen.id, "hidden": hidden.id}


def test_the_detail_only_lists_tickets_i_can_see(client, login_as, world):
    """🔴 문이 둘이다 — 문서가 보인다고 그 문서가 언급한 티켓이 보이는 것은 아니다."""
    hdr = {"X-CSRF-Token": login_as("user", email=ME)}
    r = client.get(f"/api/knowledge/documents/{world['document']}", headers=hdr)
    assert r.status_code == 200, r.text

    rows = r.json()["ticket_mentions"]
    ids = {row["ticket_id"] for row in rows}
    assert world["seen"] in ids, "볼 수 있는 티켓이 빠졌다"
    assert world["hidden"] not in ids, "범위 밖 티켓이 문서 상세로 새어 나갔다"
    # 제목도 함께 새지 않는다 — id 만 가리고 제목을 실으면 가린 의미가 없다.
    assert all("남의 티켓" not in (row["title"] or "") for row in rows)


def test_a_document_without_ticket_mentions_says_so_with_an_empty_list(client, login_as, world, db):
    """빈 목록과 「이 칸이 없다」를 구별한다 — 화면이 그 자리를 안 그리려면 값이 있어야 한다."""
    from app.knowledge.models import Document, KnowledgeSpace

    space = db.execute(
        __import__("sqlalchemy").select(KnowledgeSpace).where(KnowledgeSpace.slug == "dtm-space")
    ).scalars().one()
    plain = Document(space_id=space.id, title="아무것도 안 적은 문서")
    db.add(plain)
    db.commit()

    hdr = {"X-CSRF-Token": login_as("user", email=ME)}
    body = client.get(f"/api/knowledge/documents/{plain.id}", headers=hdr).json()
    assert body["ticket_mentions"] == []
