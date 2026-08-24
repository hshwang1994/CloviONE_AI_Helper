"""소속을 세는 자리 둘이 **공간**을 본다 (S14 · D-245).

정본인 `documents` 에는 소속 컬럼이 아예 없다. 문서를 다른 폴더로 옮기는 것이 권한을
바꾸지 않게 하려고 그렇게 만들었고, 그래서 「이 문서는 어느 부서 것인가」의 답은 언제나
그 문서가 든 공간에서 나온다.

그 사실을 안 따라간 자리가 둘 있었다. 둘 다 옛 미러(`document_cache.owner_*`)를 세고
있었고, 운영에서 그 칸은 110행 전부 `unset` 이라 **언제나 0** 이었다:

  1. 부서 삭제 앞의 「무엇이 매달려 있나」 — 0 이라고 답하면 사람이 지워도 된다고 읽는다.
     실제로는 그 부서 공간의 문서 전부가 그 순간 아무에게도 안 보이게 된다.
  2. 조직 정합성의 「소속 미지정 문서」 — 진짜 원인은 문서가 아니라 공간이었다.
"""

from __future__ import annotations

import pytest

from app.core.errors import ConflictError
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department

pytestmark = pytest.mark.integration


@pytest.fixture()
def dept(db):
    row = Department(name="자료팀", org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.commit()
    return row


def test_a_department_counts_the_documents_that_hang_off_its_space(
    db, dept, make_space, make_knowledge_document
):
    """🔴 문서는 **공간을 거쳐** 부서에 매달린다.

    문서에 소속 컬럼이 있다고 보고 세면 언제나 0 이 나오고, 그 0 은 "지워도 안전하다"로
    읽힌다.
    """
    from app.org import service

    assert service.dependents(db, dept.id) == {}, "아무것도 없는데 매달린 것이 있다고 셌다"

    space = make_space(name="자료팀 공간", slug="data-space", dept=dept)
    make_knowledge_document(space=space, title="자료팀 회의록")
    make_knowledge_document(space=space, title="자료팀 인수인계")

    found = service.dependents(db, dept.id)
    assert found.get("documents") == 2, f"공간에 든 문서를 못 셌다: {found}"
    assert found.get("knowledge_spaces") == 1, f"공간 자체를 못 셌다: {found}"


def test_an_empty_space_still_blocks_the_delete(db, dept, make_space):
    """문서가 아직 없는 공간도 삭제를 막는다.

    문서만 세면 여기서 0 이 나와 삭제가 통과하는 것처럼 보이는데, 그때 DB 가 FK 로 거절해
    원인이 안 적힌 오류가 된다.
    """
    from app.org import service

    make_space(name="빈 공간", slug="empty-space", dept=dept)

    with pytest.raises(ConflictError) as caught:
        service.delete_item(db, dept)
    assert "지식 공간" in str(caught.value.message)


def test_a_department_with_documents_cannot_be_deleted_silently(
    db, dept, make_space, make_knowledge_document
):
    from app.org import service

    space = make_space(name="자료팀 공간2", slug="data-space-2", dept=dept)
    make_knowledge_document(space=space, title="자료팀 규정")

    with pytest.raises(ConflictError) as caught:
        service.delete_item(db, dept)
    message = str(caught.value.message)
    assert "문서 1건" in message, f"무엇이 몇 건 매달렸는지 안 말했다: {message}"


def test_the_integrity_report_names_the_space_not_the_document(
    db, dept, make_space, make_knowledge_document
):
    """진단이 가리키는 대상이 **공간**이어야 고칠 자리가 하나로 정해진다.

    문서를 나열하면 같은 공간에 든 110건이 같은 이유로 줄줄이 나오고, 정작 고칠 대상 하나가
    그 안에 묻힌다. 게다가 문서에는 지정할 칸 자체가 없다.
    """
    from app.integrity import service

    orphan = make_space(name="소속 없는 공간", slug="orphan-space")
    make_knowledge_document(space=orphan, title="닫혀 있는 문서")
    owned = make_space(name="자료팀 공간3", slug="data-space-3", dept=dept)
    make_knowledge_document(space=owned, title="보이는 문서")

    report = service.report(db)
    keys = {f["key"] for f in report["findings"]}
    assert "spaces_without_ownership" in keys
    assert "documents_without_ownership" not in keys, (
        "문서에 소속을 지정하라고 말하는 진단이 남아 있다 — 지정할 칸이 없다"
    )

    finding = next(f for f in report["findings"] if f["key"] == "spaces_without_ownership")
    assert finding["count"] == 1, finding
    item = finding["items"][0]
    assert item["id"] == orphan.id
    assert item["name"] == "소속 없는 공간"
    assert "1건" in item["reason"], f"몇 건이 닫혀 있는지 안 말했다: {item}"


def test_an_owned_space_is_not_reported(db, dept, make_space, make_knowledge_document):
    """반대쪽 절반 — 소속이 있는 공간은 안 나온다. 「전부 나온다」로 통과하지 않게 한다."""
    from app.integrity import service

    owned = make_space(name="자료팀 공간4", slug="data-space-4", dept=dept)
    make_knowledge_document(space=owned, title="보이는 문서2")

    finding = next(
        f for f in service.report(db)["findings"] if f["key"] == "spaces_without_ownership"
    )
    assert finding["count"] == 0, finding
