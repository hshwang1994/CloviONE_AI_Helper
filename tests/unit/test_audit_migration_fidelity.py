"""이관 정합성 감사기(`scripts/audit_migration_fidelity.py`)를 **양방향으로** 검증한다.

## 왜 도구를 먼저 의심하는가

이 감사기는 제품이 아니라 판정자다. 판정자가 틀리는 방향은 둘이고 **둘 다 위험하다**:

  * 없는 손실을 만든다 — 원본이 비어 있는데 「손실」이라고 하면 사람이 없는 것을 고치러 간다.
  * 있는 손실을 놓친다 — 0 건을 훑고 `FIDELITY_OK` 를 찍으면 이관이 끝났다는 거짓 증거가 남는다.

그래서 시험은 Known Good(맞으면 통과) · Known Bad(일부러 지우면 잡힌다) · 반례(원본이
비어 있으면 안 잡힌다)를 짝으로 둔다. 그리고 통과하는 축마다 **`checked` 가 0 이 아닌
것**을 함께 단언한다 — 표본 없이 찍힌 초록은 초록이 아니다.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "scripts" / "audit_migration_fidelity.py"
)


def _load():
    """`sys.modules` 에 먼저 등록한다 — `@dataclass` 가 자기 모듈을 찾는다."""
    spec = importlib.util.spec_from_file_location("audit_migration_fidelity", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load()


# ── 최소 표본 만들기 ─────────────────────────────────────────────────────────


def _src_doc(page_id="doc-1", **over):
    row = {
        "page_id": page_id,
        "title": "설치 안내",
        "doc_type_names": [],
        "category_names": [],
        "project_ids": [],
        "author_ids": [],
        "author_names": [],
        "created_time": "",
        "last_edited": "",
        "attachments": [],
        "body_words": 0,
        "cell_words": 0,
        "block_kinds": {},
    }
    row.update(over)
    return row


def _tgt_doc(page_id="doc-1", **over):
    row = {
        "legacy_page_id": page_id,
        "id": "uuid-" + page_id,
        "title": "설치 안내",
        "doc_type": None,
        "created_by": None,
        "space_id": "space-1",
        "folder_id": None,
        "archived": False,
        "confidential": False,
        "source_type": "migration",
        "body": {"type": "doc", "content": []},
        "body_text": "",
        "tag_names": [],
        "attachment_count": 0,
    }
    row.update(over)
    return row


def _src_ticket(page_id="tk-1", **over):
    row = {
        "page_id": page_id,
        "title": "로그인 오류",
        "status": "진행",
        "priority": None,
        "difficulty": None,
        "category": None,
        "est_wd": None,
        "act_wd": None,
        "start_date": "",
        "due_date": "",
        "assignee_ids": [],
        "project_ids": [],
        "created_time": "",
        "parent_ids": [],
        "blocked_by": [],
        "blocks": [],
        "attachments": [],
        "body_words": 0,
        "cell_words": 0,
        "block_kinds": {},
    }
    row.update(over)
    return row


def _tgt_ticket(page_id="tk-1", **over):
    row = {
        "notion_page_id": page_id,
        "id": "uuid-" + page_id,
        "title": "로그인 오류",
        "status": "진행",
        "priority": None,
        "difficulty": None,
        "category": None,
        "est_wd": None,
        "act_wd": None,
        "start_date": None,
        "due_date": None,
        "project_uid": None,
        "project_ids": "",
        "assignee_notion_ids": "",
        "notion_created_time": None,
        "parent_page_id": None,
        "body_markdown": "",
        "source": "notion",
        "notion_missing_at": None,
        "comment_count": 0,
        "attachment_count": 0,
    }
    row.update(over)
    return row


def _target(docs=None, tickets=None, **over):
    payload = {
        "documents": list(docs or []),
        "tickets": list(tickets or []),
        "ticket_relations": [],
        "spaces": [{
            "id": "space-1", "name": "팀 문서", "slug": "team-docs",
            "owner_kind": "organization", "owner_dept_id": None,
            "owner_project_id": None, "archived": False,
        }],
        "user_notion_mappings": [],
        "projects": [],
        "files": [],
        "file_mappings": [],
        "migration_exceptions": [],
        "document_relations": 0,
        "folders": 0,
    }
    payload.update(over)
    return payload


def _axis(report, key):
    for axis in report.axes:
        if axis.key == key:
            return axis
    raise AssertionError(f"{key} 축이 없다. 있는 축: {[a.key for a in report.axes]}")


# ── Known Good ───────────────────────────────────────────────────────────────


def test_perfect_copy_passes_and_actually_looked_at_something():
    """원본과 대상이 같으면 통과한다. **그리고 실제로 몇 건을 봤는지 단언한다.**"""
    source = {
        "documents": [_src_doc(title="설치 안내", category_names=["운영"])],
        "tickets": [_src_ticket(title="로그인 오류", status="진행")],
    }
    target = _target(
        docs=[_tgt_doc(title="설치 안내", tag_names=["운영"])],
        tickets=[_tgt_ticket(title="로그인 오류", status="진행")],
    )
    report = MOD.audit(source, target)

    assert report.verdict == "FIDELITY_OK"
    assert report.total_lost == 0
    # 0 건을 훑고 초록을 찍는 것이 이 도구가 낼 수 있는 가장 나쁜 답이다.
    assert _axis(report, "doc.title").checked == 1
    assert _axis(report, "doc.category").checked == 1
    assert _axis(report, "ticket.title").checked == 1
    assert _axis(report, "ticket.status").checked == 1
    assert report.total_checked >= 4


# ── Known Bad — 일부러 망가뜨린 표본이 잡히는가 ──────────────────────────────


def test_blanked_title_is_caught_with_both_values_in_the_sample():
    source = {"documents": [_src_doc(title="설치 안내")], "tickets": []}
    target = _target(docs=[_tgt_doc(title="")])
    report = MOD.audit(source, target)

    axis = _axis(report, "doc.title")
    assert axis.checked == 1
    assert axis.lost == 1
    assert axis.status == MOD.ST_LOST
    assert report.verdict == "FIDELITY_FAILED"
    # 표본에 id 와 두 값이 함께 있어야 무엇을 고칠지 안다.
    assert "doc-1" in axis.samples[0]
    assert "설치 안내" in axis.samples[0]


def test_missing_row_is_caught():
    source = {"documents": [_src_doc()], "tickets": [_src_ticket()]}
    report = MOD.audit(source, _target(docs=[], tickets=[]))

    assert _axis(report, "doc.row").lost == 1
    assert _axis(report, "ticket.row").lost == 1
    assert report.verdict == "FIDELITY_FAILED"


def test_dropped_category_is_caught_and_extra_tag_is_not():
    """분류는 **원본이 대상에 들어 있는가**만 본다. 사용자가 더 붙인 태그는 손실이 아니다."""
    source = {"documents": [_src_doc(category_names=["운영", "보안"])], "tickets": []}

    dropped = MOD.audit(source, _target(docs=[_tgt_doc(tag_names=["운영"])]))
    assert _axis(dropped, "doc.category").lost == 1

    superset = MOD.audit(
        source, _target(docs=[_tgt_doc(tag_names=["운영", "보안", "내가붙인것"])])
    )
    assert _axis(superset, "doc.category").checked == 1
    assert _axis(superset, "doc.category").lost == 0


def test_empty_body_and_shrunken_body_are_separate_findings():
    source = {"documents": [
        _src_doc("doc-empty", body_words=100),
        _src_doc("doc-small", body_words=100),
        _src_doc("doc-full", body_words=100),
    ], "tickets": []}
    target = _target(docs=[
        _tgt_doc("doc-empty", body_text=""),
        _tgt_doc("doc-small", body_text="가" * 50),
        _tgt_doc("doc-full", body_text="가" * 100),
    ])
    report = MOD.audit(source, target)

    assert _axis(report, "doc.body_nonempty").checked == 3
    assert _axis(report, "doc.body_nonempty").lost == 1
    assert _axis(report, "doc.body_chars").checked == 3
    assert _axis(report, "doc.body_chars").lost == 2


def test_placeholder_residue_is_a_loss():
    source = {"documents": [_src_doc(body_words=5)], "tickets": []}
    kept = MOD.audit(source, _target(docs=[
        _tgt_doc(body_text="앞말 [원본에서 확인: table] 뒷말")
    ]))
    clean = MOD.audit(source, _target(docs=[_tgt_doc(body_text="앞말 표 뒷말")]))

    assert _axis(kept, "doc.placeholder").checked == 1
    assert _axis(kept, "doc.placeholder").lost == 1
    assert _axis(clean, "doc.placeholder").checked == 1
    assert _axis(clean, "doc.placeholder").lost == 0


def test_space_with_unset_owner_is_a_loss():
    """소유가 `unset` 인 공간은 소유 규칙의 어느 갈래에도 안 걸린다 (D7)."""
    source = {"documents": [_src_doc()], "tickets": []}
    unset = MOD.audit(source, _target(
        docs=[_tgt_doc()],
        spaces=[{"id": "space-1", "owner_kind": "unset", "name": "팀 문서",
                 "slug": "team-docs", "owner_dept_id": None,
                 "owner_project_id": None, "archived": False}],
    ))
    owned = MOD.audit(source, _target(docs=[_tgt_doc()]))

    assert _axis(unset, "doc.space_visible").checked == 1
    assert _axis(unset, "doc.space_visible").lost == 1
    assert _axis(owned, "doc.space_visible").checked == 1
    assert _axis(owned, "doc.space_visible").lost == 0


def test_ticket_relations_are_compared_as_directed_edges():
    source = {"documents": [], "tickets": [
        _src_ticket("tk-1", blocks=["tk-2"]),
        _src_ticket("tk-2"),
    ]}
    right = MOD.audit(source, _target(
        tickets=[_tgt_ticket("tk-1"), _tgt_ticket("tk-2")],
        ticket_relations=[{"kind": "blocks", "from_page": "tk-1", "to_page": "tk-2"}],
    ))
    flipped = MOD.audit(source, _target(
        tickets=[_tgt_ticket("tk-1"), _tgt_ticket("tk-2")],
        ticket_relations=[{"kind": "blocks", "from_page": "tk-2", "to_page": "tk-1"}],
    ))

    assert _axis(right, "ticket.blocks").checked == 1
    assert _axis(right, "ticket.blocks").lost == 0
    # 방향이 뒤집히면 잡아야 한다. 선후 관계는 뒤집혀도 화면이 정상으로 보인다.
    assert _axis(flipped, "ticket.blocks").lost == 1


# ── 반례 — 원본이 비어 있으면 손실이 아니다 ─────────────────────────────────


def test_empty_source_axes_are_not_counted_at_all():
    """원본이 비어 있으면 우리도 비어 있는 것이 정답이다."""
    source = {"documents": [_src_doc()], "tickets": [_src_ticket()]}
    report = MOD.audit(source, _target(docs=[_tgt_doc()], tickets=[_tgt_ticket()]))

    for key in (
        "doc.author", "doc.project", "doc.category", "doc.doc_type",
        "doc.attachment", "doc.created_time", "doc.last_edited",
        "ticket.priority", "ticket.difficulty", "ticket.due_date",
        "ticket.est_wd", "ticket.assignee", "ticket.parent", "ticket.attachment",
    ):
        axis = _axis(report, key)
        assert axis.checked == 0, f"{key} 가 빈 원본을 셌다"
        assert axis.lost == 0, f"{key} 가 없는 손실을 만들었다"
    assert report.verdict == "FIDELITY_OK"


def test_value_only_in_target_is_not_a_loss():
    """우리 쪽에만 있는 값은 손실이 아니다. 사용자가 나중에 채웠을 수 있다."""
    source = {"documents": [], "tickets": [_src_ticket(priority=None, due_date="")]}
    report = MOD.audit(source, _target(tickets=[
        _tgt_ticket(priority="높음", due_date="2026-09-01")
    ]))

    assert _axis(report, "ticket.priority").checked == 0
    assert report.total_lost == 0


def test_document_origin_timestamps_are_compared_both_ways():
    """원본 시각을 담을 칸이 생기면 통과하고, 없으면 손실이다.

    지금 `documents` 에는 그 칸이 없어 이 축이 늘 빨갛다. 시험을 「늘 빨갛다」로 못 박으면
    고치는 날 시험이 막아서므로, **비교기 자체**를 양방향으로 확인한다.
    """
    source = {"documents": [_src_doc(
        created_time="2026-08-12 02:40:00", last_edited="2026-08-12 04:55:00",
    )], "tickets": []}

    without = MOD.audit(source, _target(docs=[_tgt_doc()]))
    assert _axis(without, "doc.created_time").checked == 1
    assert _axis(without, "doc.created_time").lost == 1
    assert _axis(without, "doc.last_edited").lost == 1

    with_column = MOD.audit(source, _target(docs=[_tgt_doc(
        legacy_created_at="2026-08-12T02:40:00.000Z",
        legacy_updated_at="2026-08-12 04:55:00",
    )]))
    assert _axis(with_column, "doc.created_time").checked == 1
    assert _axis(with_column, "doc.created_time").lost == 0
    assert _axis(with_column, "doc.last_edited").lost == 0


def test_scalar_axis_compares_after_normalising_shape():
    """`2026-08-12T02:40:00.000Z` 와 `2026-08-12 02:40:00` 은 같은 값이다."""
    source = {"documents": [], "tickets": [
        _src_ticket(created_time="2026-08-12 02:40:00")
    ]}
    report = MOD.audit(source, _target(tickets=[
        _tgt_ticket(notion_created_time="2026-08-12 02:40:00")
    ]))

    assert _axis(report, "ticket.created_time").checked == 1
    assert _axis(report, "ticket.created_time").lost == 0


# ── 설계상 차이는 실패로 세지 않는다 ────────────────────────────────────────


def test_multiple_parents_are_a_named_design_difference():
    source = {"documents": [], "tickets": [
        _src_ticket("tk-1", parent_ids=["tk-9", "tk-8"]),
    ]}
    report = MOD.audit(source, _target(
        tickets=[_tgt_ticket("tk-1", parent_page_id="tk-9")],
        ticket_relations=[
            {"kind": "subtask_of", "from_page": "tk-1", "to_page": "tk-9"},
        ],
    ))

    axis = _axis(report, "ticket.parent")
    assert axis.checked == 1
    assert axis.lost == 0
    assert axis.by_design == 1
    assert axis.by_design_reasons == {MOD.BD_SINGLE_PARENT: 1}
    assert axis.status == MOD.ST_BY_DESIGN
    # 설계상 차이만 있으면 실패가 아니다.
    assert report.verdict == "FIDELITY_OK"


def test_single_parent_that_is_not_linked_is_still_a_loss():
    """반례. 부모가 하나뿐인데 안 이어졌으면 그것은 설계가 아니라 손실이다."""
    source = {"documents": [], "tickets": [_src_ticket("tk-1", parent_ids=["tk-9"])]}
    report = MOD.audit(source, _target(tickets=[_tgt_ticket("tk-1")]))

    axis = _axis(report, "ticket.parent")
    assert axis.checked == 1
    assert axis.lost == 1
    assert axis.by_design == 0
    assert report.verdict == "FIDELITY_FAILED"


def test_unmapped_author_is_by_design_but_mapped_one_is_a_loss():
    """이름으로 추측 매칭하지 않기로 한 결정(D9)은 봐주고, 그 밖은 안 봐준다."""
    source = {"documents": [_src_doc(author_ids=["notion-user-1"])], "tickets": []}

    unmapped = MOD.audit(source, _target(docs=[_tgt_doc(created_by=None)]))
    axis = _axis(unmapped, "doc.author")
    assert axis.checked == 1
    assert axis.by_design == 1
    assert axis.by_design_reasons == {MOD.BD_UNMAPPED_AUTHOR: 1}
    assert unmapped.verdict == "FIDELITY_OK"

    mapped = MOD.audit(source, _target(
        docs=[_tgt_doc(created_by=None)],
        user_notion_mappings=[{
            "notion_user_id": "notion-user-1", "user_id": "u-1", "status": "verified",
        }],
    ))
    axis = _axis(mapped, "doc.author")
    assert axis.checked == 1
    assert axis.lost == 1
    assert axis.by_design == 0
    assert mapped.verdict == "FIDELITY_FAILED"


def test_attachment_without_bytes_is_by_design_but_stored_one_must_be_linked():
    external = {"legacy_id": "p:0", "name": "링크", "hosted": False}
    stored = {"legacy_id": "p:1", "name": "가이드.pdf", "hosted": True}

    only_external = MOD.audit(
        {"documents": [_src_doc(attachments=[external])], "tickets": []},
        _target(docs=[_tgt_doc(attachment_count=0)]),
    )
    axis = _axis(only_external, "doc.attachment")
    assert axis.checked == 1
    assert axis.by_design == 1
    assert axis.by_design_reasons == {MOD.BD_ATTACHMENT_EXTERNAL: 1}
    assert only_external.verdict == "FIDELITY_OK"

    # 상한 초과로 **분류된** 첨부만 봐준다.
    rejected = MOD.audit(
        {"documents": [_src_doc(attachments=[stored])], "tickets": []},
        _target(docs=[_tgt_doc(attachment_count=0)]),
        ledger={"p:1": "attachment_rejected"},
    )
    axis = _axis(rejected, "doc.attachment")
    assert axis.by_design == 1
    assert axis.lost == 0
    assert axis.by_design_reasons == {MOD.BD_ATTACHMENT_LIMIT: 1}

    # 반례. 까닭이 안 적힌 채 바이트만 사라진 첨부는 손실이다 — 내려받기 실패가 그렇다.
    unexplained = MOD.audit(
        {"documents": [_src_doc(attachments=[stored])], "tickets": []},
        _target(docs=[_tgt_doc(attachment_count=0)]),
    )
    axis = _axis(unexplained, "doc.attachment")
    assert axis.lost == 1
    assert axis.by_design == 0
    assert unexplained.verdict == "FIDELITY_FAILED"

    # 반례. 바이트는 저장했는데 문서에 안 붙었으면 손실이다.
    orphan = MOD.audit(
        {"documents": [_src_doc(attachments=[stored])], "tickets": []},
        _target(
            docs=[_tgt_doc(attachment_count=0)],
            file_mappings=[{"legacy_source_id": "p:1", "target_id": "file-1"}],
        ),
    )
    axis = _axis(orphan, "doc.attachment")
    assert axis.lost == 1
    assert axis.by_design == 0
    assert orphan.verdict == "FIDELITY_FAILED"


def test_row_only_in_target_needs_a_classified_reason():
    source = {"documents": [], "tickets": []}

    classified = MOD.audit(source, _target(
        tickets=[_tgt_ticket("tk-x")],
        migration_exceptions=[{
            "ticket_id": "uuid-tk-x", "reason": "source_missing", "resolved_at": None,
        }],
    ))
    axis = _axis(classified, "ticket.extra_rows")
    assert axis.checked == 1
    assert axis.by_design == 1
    assert classified.verdict == "FIDELITY_OK"

    # 반례. 까닭 없이 우리에만 있는 행은 그냥 두지 않는다.
    unexplained = MOD.audit(source, _target(tickets=[_tgt_ticket("tk-x")]))
    assert _axis(unexplained, "ticket.extra_rows").lost == 1
    assert unexplained.verdict == "FIDELITY_FAILED"


# ── 비교하지 못한 축을 조용히 통과시키지 않는다 ─────────────────────────────


def test_not_audited_axes_are_named_in_the_output():
    report = MOD.audit({"documents": [_src_doc()], "tickets": [_src_ticket()]},
                       _target(docs=[_tgt_doc()], tickets=[_tgt_ticket()]))
    payload = report.as_dict()

    assert "doc.folder" in payload["not_audited"]
    assert "ticket.comment" in payload["not_audited"]
    assert _axis(report, "ticket.comment").status == MOD.ST_NOT_AUDITED
    text = MOD.render_table(report)
    assert "비교하지 못한 축" in text
    assert "ticket.comment" in text


def test_every_axis_reports_its_checked_count_in_the_table():
    report = MOD.audit({"documents": [_src_doc()], "tickets": [_src_ticket()]},
                       _target(docs=[_tgt_doc()], tickets=[_tgt_ticket()]))
    text = MOD.render_table(report)

    assert "본 건수" in text
    for axis in report.axes:
        assert axis.as_dict()["checked"] == axis.checked
    assert "본 건수 합계" in text


# ── 블록 보존 ────────────────────────────────────────────────────────────────


def test_image_and_table_nodes_are_counted_in_the_target_body():
    source = {
        "documents": [_src_doc(block_kinds={"image": 2, "table": 1, "table_row": 3})],
        "tickets": [],
    }
    lost = MOD.audit(source, _target(docs=[_tgt_doc(body={
        "type": "doc", "content": [{"type": "paragraph"}],
    })]))
    assert _axis(lost, "block.image").checked == 2
    assert _axis(lost, "block.image").lost == 2
    assert _axis(lost, "block.table").lost == 1

    kept = MOD.audit(source, _target(docs=[_tgt_doc(body={
        "type": "doc",
        "content": [
            {"type": "image", "attrs": {"src": "/a"}},
            {"type": "image", "attrs": {"src": "/b"}},
            {"type": "table", "content": [
                {"type": "tableRow", "content": []},
                {"type": "tableRow", "content": []},
                {"type": "tableRow", "content": []},
            ]},
        ],
    })]))
    assert _axis(kept, "block.image").lost == 0
    assert _axis(kept, "block.table").lost == 0
    assert _axis(kept, "block.table_row").lost == 0
    assert kept.verdict == "FIDELITY_OK"


def test_table_cell_characters_are_compared():
    source = {"documents": [_src_doc(cell_words=10, block_kinds={})], "tickets": []}
    empty = MOD.audit(source, _target(docs=[_tgt_doc()]))
    assert _axis(empty, "block.table_cell_chars").checked == 10
    assert _axis(empty, "block.table_cell_chars").lost == 10

    filled = MOD.audit(source, _target(docs=[_tgt_doc(body={
        "type": "doc", "content": [{"type": "table", "content": [
            {"type": "tableRow", "content": [
                {"type": "tableCell", "content": [
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": "열두글자짜리내용입니다"},
                    ]},
                ]},
            ]},
        ]}],
    })]))
    assert _axis(filled, "block.table_cell_chars").lost == 0


# ── 잔손의 반례 ──────────────────────────────────────────────────────────────


def test_word_count_ignores_placeholders_and_markdown_punctuation():
    assert MOD._words("[원본에서 확인: table]") == 0
    assert MOD._words("## 제목") == 2
    assert MOD._words("| 값 | 값 |") == 2
    assert MOD._words(None) == 0


def test_markdown_table_census_skips_code_fences():
    """코드 블록 안의 `|` 줄을 표로 세면 보존율이 부풀어 손실이 작아 보인다."""
    fenced = "```\n| not | a | table |\n| still | not | one |\n```\n"
    real = "| 머리 | 칸 |\n| --- | --- |\n| 값 | 값 |\n"

    assert MOD._md_census(fenced)["table"] == 0
    assert MOD._md_census(fenced)["tableRow"] == 0
    assert MOD._md_census(real)["table"] == 1
    assert MOD._md_census(real)["tableRow"] == 3
    assert MOD._md_census("![그림](/files/a.png)")["image"] == 1
    assert MOD._md_table_words(fenced) == 0
    assert MOD._md_table_words(real) > 0


def test_target_query_only_reads():
    sql = MOD.build_target_query()
    upper = sql.upper()

    assert upper.lstrip().startswith("SELECT")
    for verb in (
        "INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ",
        "CREATE ", "GRANT ", "COPY ",
    ):
        assert verb not in upper, f"대상 질의에 {verb.strip()} 가 있다"
    assert sql.count(";") == 0
    assert "SET default_transaction_read_only = on;" in MOD.emit_target_sql()


def test_ledger_reads_only_the_attachment_classification(tmp_path):
    """보고서에서 읽는 범위를 좁혀 둔다. 넓히면 보고서에 한 줄 적는 것으로 손실이 사라진다."""
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"findings": [
        {"kind": "attachment_rejected", "ref": "p:1", "detail": "너무 큽니다"},
        {"kind": "attachment_external_link", "ref": "p:0", "detail": "바깥 링크"},
        {"kind": "ticket_multiple_parents", "ref": "tk-1", "detail": "둘입니다"},
        {"kind": "attachment_download_failed", "ref": "p:2", "detail": "실패"},
    ]}, ensure_ascii=False), encoding="utf-8")

    ledger = MOD.load_ledger(path)
    assert ledger == {"p:1": "attachment_rejected", "p:0": "attachment_external_link"}
    assert MOD.load_ledger(tmp_path / "없는파일.json") == {}


def test_target_json_loader_skips_psql_banner(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(
        'Output format is unaligned.\nSET\n{"documents": []}\n', encoding="utf-8",
    )
    assert MOD.load_target_json(path) == {"documents": []}


# ── 캐시를 실제로 읽는다 ─────────────────────────────────────────────────────


def _write_cache(root: pathlib.Path) -> pathlib.Path:
    """Notion 응답 모양 그대로의 작은 캐시. **속성 이름이 계약이다.**"""
    cache = root / "cache"
    (cache / "blocks").mkdir(parents=True)

    def rich(text):
        return [{"type": "text", "text": {"content": text},
                 "plain_text": text, "href": None, "annotations": {}}]

    (cache / "documents.json").write_text(json.dumps([{
        "id": "doc-page-1",
        "url": "https://app.notion.com/p/doc-page-1",
        "created_time": "2026-08-12T02:40:00.000Z",
        "last_edited_time": "2026-08-12T04:55:00.000Z",
        "properties": {
            "이름 ": {"type": "title", "title": rich("설치 안내")},
            " 카테고리": {"type": "relation", "relation": [{"id": "cat-1"}]},
            "첨부파일 ": {"type": "files", "files": [
                {"name": "가이드.pdf", "file": {"url": "https://x/y.pdf"}},
            ]},
        },
    }], ensure_ascii=False), encoding="utf-8")

    (cache / "categories.json").write_text(json.dumps([{
        "id": "cat-1",
        "properties": {"이름": {"type": "title", "title": rich("운영")}},
    }], ensure_ascii=False), encoding="utf-8")

    (cache / "tasks.json").write_text(json.dumps([{
        "id": "task-page-1",
        "url": "https://app.notion.com/p/task-page-1",
        "created_time": "2026-08-12T02:40:00.000Z",
        "last_edited_time": "2026-08-12T04:55:00.000Z",
        "properties": {
            "제목": {"type": "title", "title": rich("로그인 오류")},
            "진행상태": {"type": "status", "status": {"name": "진행"}},
            "상위 작업": {"type": "relation", "relation": [{"id": "task-page-9"}]},
        },
    }], ensure_ascii=False), encoding="utf-8")

    (cache / "blocks" / "doc-page-1.json").write_text(json.dumps({
        "last_edited": "2026-08-12T04:55:00.000Z",
        "blocks": [
            {"type": "paragraph", "paragraph": {"rich_text": rich("본문 한 줄")}},
            {"type": "image", "image": {"caption": []}},
            {"type": "table", "table": {}, "_children": [
                {"type": "table_row", "table_row": {"cells": [
                    rich("머리칸"), rich("값칸"),
                ]}},
            ]},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return cache


def test_collect_source_reads_the_real_notion_property_names(tmp_path):
    """속성 이름이 어긋나면 값이 조용히 빈다. 그 자리를 시험으로 못 박는다."""
    cache = _write_cache(tmp_path)
    source = MOD.collect_source(cache)

    doc = source["documents"][0]
    assert doc["title"] == "설치 안내"
    assert doc["category_names"] == ["운영"]
    assert doc["created_time"] == "2026-08-12 02:40:00"
    assert [a["name"] for a in doc["attachments"]] == ["가이드.pdf"]
    assert doc["block_kinds"] == {
        "paragraph": 1, "image": 1, "table": 1, "table_row": 1,
    }
    assert doc["body_words"] > 0
    assert doc["cell_words"] > 0

    ticket = source["tickets"][0]
    assert ticket["title"] == "로그인 오류"
    assert ticket["status"] == "진행"
    assert ticket["parent_ids"] == ["task-page-9"]


def test_main_prints_the_verdict_and_matches_the_exit_code(tmp_path, capsys):
    cache = _write_cache(tmp_path)
    snapshot = tmp_path / "target.json"

    snapshot.write_text(json.dumps(_target(
        docs=[_tgt_doc("doc-page-1", title="", body_text="")],
        tickets=[_tgt_ticket("task-page-1")],
    ), ensure_ascii=False), encoding="utf-8")
    code = MOD.main(["--cache-dir", str(cache), "--target-json", str(snapshot)])
    out = capsys.readouterr().out
    assert code == 1
    assert out.strip().splitlines()[-1] == "FIDELITY_FAILED"

    snapshot.write_text(json.dumps(_target(
        docs=[_tgt_doc(
            "doc-page-1", title="설치 안내", tag_names=["운영"], attachment_count=1,
            legacy_created_at="2026-08-12 02:40:00",
            legacy_updated_at="2026-08-12 04:55:00",
            body_text="본문 한 줄 머리칸 값칸",
            body={"type": "doc", "content": [
                {"type": "image", "attrs": {"src": "/a"}},
                {"type": "table", "content": [{"type": "tableRow", "content": [
                    {"type": "tableCell", "content": [{"type": "paragraph", "content": [
                        {"type": "text", "text": "머리칸 값칸"},
                    ]}]},
                ]}]},
            ]},
        )],
        tickets=[_tgt_ticket(
            "task-page-1", parent_page_id="task-page-9",
            notion_created_time="2026-08-12 02:40:00",
        )],
        ticket_relations=[{
            "kind": "subtask_of", "from_page": "task-page-1", "to_page": "task-page-9",
        }],
        file_mappings=[{"legacy_source_id": "doc-page-1:0", "target_id": "file-1"}],
    ), ensure_ascii=False), encoding="utf-8")
    code = MOD.main(["--cache-dir", str(cache), "--target-json", str(snapshot)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.strip().splitlines()[-1] == "FIDELITY_OK"


def test_json_output_carries_the_verdict_and_every_axis(tmp_path, capsys):
    cache = _write_cache(tmp_path)
    snapshot = tmp_path / "target.json"
    snapshot.write_text(json.dumps(_target(
        docs=[_tgt_doc("doc-page-1", title="")],
        tickets=[_tgt_ticket("task-page-1")],
    ), ensure_ascii=False), encoding="utf-8")
    out_path = tmp_path / "out.json"

    code = MOD.main([
        "--cache-dir", str(cache), "--target-json", str(snapshot),
        "--json", str(out_path),
    ])
    payload = json.loads(out_path.read_text(encoding="utf-8"))

    assert code == 1
    assert payload["verdict"] == "FIDELITY_FAILED"
    assert payload["passed"] is False
    assert payload["total_checked"] > 0
    keys = {axis["key"] for axis in payload["axes"]}
    assert {"doc.title", "doc.placeholder", "ticket.parent", "block.image"} <= keys
    for axis in payload["axes"]:
        assert "checked" in axis and "samples" in axis


# ── 진짜 캐시 (있을 때만) ────────────────────────────────────────────────────


@pytest.mark.skipif(
    not (MOD.DEFAULT_CACHE / "documents.json").exists(),
    reason="원본 추출 캐시가 이 작업 트리에 없다 (var/ 는 추적하지 않는다).",
)
def test_real_extraction_cache_matches_the_measured_census():
    """실측으로 확인한 수를 못 박는다. Known Good 이 없으면 판정자를 믿을 근거가 없다."""
    source = MOD.collect_source(MOD.DEFAULT_CACHE)

    assert len(source["documents"]) == 110
    assert len(source["tickets"]) == 1125

    docs = {}
    for row in source["documents"]:
        for kind, count in row["block_kinds"].items():
            docs[kind] = docs.get(kind, 0) + count
    tickets = {}
    for row in source["tickets"]:
        for kind, count in row["block_kinds"].items():
            tickets[kind] = tickets.get(kind, 0) + count

    assert docs["image"] == 49
    assert docs["table"] == 93
    assert tickets["image"] == 222
    assert tickets["table"] == 35
    assert docs["image"] + tickets["image"] == 271
    assert docs["table"] + tickets["table"] == 128
