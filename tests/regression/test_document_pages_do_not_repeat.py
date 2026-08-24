"""문서 목록의 쪽 경계가 **행을 반복하거나 빠뜨리지 않는다** (S15 · Z9).

티켓 목록은 이 성질을 이미 갖고 있다 — 정렬이 전순서가 아니면 OFFSET 페이지네이션이
1쪽에 나온 행을 2쪽에 또 내거나 아예 빠뜨리고, 사용자에게는 **"문서가 사라졌다"** 로 보인다.
새로고침하면 돌아와서 재현조차 안 된다(`app/tickets/query.py::ORDER` 가 같은 이유로 id 를
타이브레이커로 붙인다).

문서 목록은 `updated_at` **하나로만** 정렬하고 있었다. 그 시각이 같은 행들의 상대 순서는
DB 가 매번 마음대로 정한다. 그리고 이 저장소에서 같은 시각은 이론이 아니다 — **이관은
문서 여럿을 한 회차에 적재한다.**

시험대는 그래서 **전부 같은 `updated_at`** 이다. 값이 다르면 정렬이 이미 전순서라 결함이
드러나지 않는다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

pytestmark = pytest.mark.regression

ME = "docpage@goodmit.co.kr"
SAME_MOMENT = datetime(2026, 8, 24, 3, 0, 0)
TOTAL = 12
PAGE = 4


@pytest.fixture()
def tied_documents(db, make_user):
    """같은 시각에 적재된 문서 열두 건. 이관 회차 한 번이 만드는 모양 그대로다."""
    from app.knowledge.models import Document, KnowledgeSpace
    from app.org.constants import DEFAULT_ORG_ID

    make_user(ME, role="user", display_name="나")
    space = KnowledgeSpace(name="이관 공간", slug="dp-space", owner_kind="organization",
                           org_id=DEFAULT_ORG_ID)
    db.add(space)
    db.flush()
    rows = [
        Document(space_id=space.id, title=f"이관 문서 {i:02d}",
                 created_at=SAME_MOMENT, updated_at=SAME_MOMENT)
        for i in range(TOTAL)
    ]
    db.add_all(rows)
    db.commit()
    # 픽스처가 실제로 동점을 만들었는지 확인한다 — 안 그러면 이 시험은 아무것도 안 본다.
    stamps = {d.updated_at for d in db.query(Document).all()}
    assert len(stamps) == 1, "동점이 안 만들어졌다 — 이 시험은 그 상태에서만 뜻이 있다"
    ids = [d.id for d in rows]
    # 삽입 순서와 id 오름차순이 같으면 아래 판정이 «타이브레이커가 있다» 와 «스캔 순서가
    # 그냥 그랬다» 를 구별하지 못한다. UUID 라 실제로는 안 겹치지만, 확인하고 간다.
    assert ids != sorted(ids), "삽입 순서와 id 순서가 같다 — 이 표본으로는 판정할 수 없다"
    return {"space": space.id, "expected": sorted(ids)}


def test_paging_through_tied_documents_sees_each_one_exactly_once(
    client, login_as, tied_documents
):
    login_as("user", email=ME)
    seen: list[str] = []
    for offset in range(0, TOTAL, PAGE):
        body = client.get(
            f"/api/knowledge/documents?space_id={tied_documents['space']}&limit={PAGE}&offset={offset}"
        ).json()
        assert body["total"] == TOTAL
        seen.extend(d["id"] for d in body["items"])

    assert len(seen) == TOTAL, "쪽을 다 넘겼는데 건수가 안 맞는다 — 어떤 문서는 어느 쪽에도 없다"
    assert len(set(seen)) == TOTAL, "같은 문서가 두 쪽에 나왔다"
    # 🔴 여기가 실제로 결함을 잡는 자리다. 타이브레이커가 없으면 순서를 정하는 것은
    # **스캔 순서**(= 삽입 순서)이고, 그 값은 id 오름차순이 아니다. 위 두 줄만으로는
    # 작은 표본에서 결함이 안 드러난다 — 실제로 그렇게 통과하는 것을 확인했다
    # (자작 프로브는 양방향으로 틀린다).
    assert seen == tied_documents["expected"], "정렬이 스캔 순서에 좌우된다 — 타이브레이커가 없다"


def test_the_same_page_is_the_same_page_twice(client, login_as, tied_documents):
    """같은 요청을 두 번 하면 같은 답이어야 한다 — 순서가 스캔에 좌우되면 여기서 흔들린다."""
    login_as("user", email=ME)
    url = (f"/api/knowledge/documents?space_id={tied_documents['space']}"
           f"&limit={PAGE}&offset={PAGE}")
    first = [d["id"] for d in client.get(url).json()["items"]]
    second = [d["id"] for d in client.get(url).json()["items"]]
    assert first == second
    assert first == tied_documents["expected"][PAGE:PAGE * 2]
