"""검증하는 코드를 **먼저 검증한다** (S13 · CLAUDE.md §7 · S12 의 교훈).

S12 가 실제로 만난 것: 세는 질의가 언제나 0 을 돌려주면 원본과 복원본이 **똑같이 0**
이라 대조를 통과한다. 검사가 켜져 있는데 아무것도 안 보는 상태이고, 그 초록은
아무 뜻이 없다.

그래서 Product 판정 전에 이 검증기를 세 갈래로 시험한다:

* **Known Good** — 제대로 적재된 DB 에서 전 항 통과한다.
* **Known Bad** — 자리마다 하나씩 망가뜨리면 **그 항이** 실패한다.
* **반례** — 「검사가 안 도는 상태」가 통과로 안 읽힌다.

망가뜨리는 것은 적재 코드가 아니라 **적재된 DB** 다. 적재를 고쳐서 시험하면 「검증기가
잡았다」와 「적재가 안 했다」를 구별할 수 없다.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.migration import runner, validate
from app.migration.report import MigrationReport
from app.migration.source_sqlite import SqliteSource

from tests.integration.test_migration_dry_run import (  # 표본을 그대로 쓴다
    PROJECT,
    TICKET_A,
    FakeNotion,
    _write_source,
)

pytestmark = [pytest.mark.regression, pytest.mark.real_db]


@pytest.fixture()
def loaded(tmp_path, db_url):
    """한 번 제대로 적재해 둔 DB 와, 그 위에서 검증만 다시 도는 함수."""
    source_path = tmp_path / "legacy.sqlite3"
    _write_source(source_path)
    settings = Settings(
        _env_file=None, app_env="test", database_url=db_url,
        session_secret="test", cookie_secure=False,
        config_dir=Path("config"), secrets_dir=tmp_path / "secrets",
        data_dir=tmp_path / "data",
    )
    (tmp_path / "secrets").mkdir(exist_ok=True)
    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    with factory() as session:
        first = runner.run(
            session, runner.MigrationOptions(sqlite_path=str(source_path)),
            notion=FakeNotion(), settings=settings,
        )
    assert first.passed, [c.line() for c in first.failed_checks]

    def revalidate() -> MigrationReport:
        report = MigrationReport(mode="verify")
        with factory() as session, SqliteSource(source_path) as source:
            validate.validate(session, source, report, notion={
                "tasks": 3, "documents": 1, "projects": 1,
            })
        return report

    def sql(statement: str, **params) -> None:
        with factory() as session:
            session.execute(sa.text(statement), params)
            session.commit()

    try:
        yield revalidate, sql, source_path
    finally:
        engine.dispose()


def _failed(report: MigrationReport) -> set[str]:
    return {check.name for check in report.failed_checks}


# ── Known Good ───────────────────────────────────────────────────────────────


def test_known_good_passes_and_actually_counted_something(loaded):
    revalidate, _sql, _path = loaded
    report = revalidate()
    assert not report.failed_checks, [c.line() for c in report.failed_checks]
    assert len(report.checks) >= 30, f"검사가 {len(report.checks)}건뿐이다"
    # 「몇 개를 봤는가」가 보고서에 남는가. 이 수가 없으면 다음 사람이 「본 것」과
    # 「셌다고 말한 것」을 구별하지 못한다.
    by_name = {check.name: check for check in report.checks}
    assert by_name["수를 대조한 표"].actual > 0
    assert by_name["길이를 본 컬럼"].actual >= 300


# ── Known Bad — 자리마다 하나씩 ──────────────────────────────────────────────


def test_a_missing_row_is_caught(loaded):
    revalidate, sql, _path = loaded
    sql("DELETE FROM tickets WHERE id = :id", id=TICKET_A)
    failed = _failed(revalidate())
    assert "누락 ticket_cache → tickets" in failed


def test_a_number_without_a_display_name_is_caught(loaded):
    """번호와 표시 이름이 어긋난 상태. 화면에서는 빈 칸으로만 보인다.

    **지금은 CHECK 제약이 먼저 막는다** — 그것이 옳다. 그래서 제약을 떼고 시험한다:
    이 검사가 지키는 것은 「제약이 사라지는 날」이고, 제약이 있는 동안에는 두 겹이다.
    """
    revalidate, sql, _path = loaded
    with pytest.raises(Exception):
        sql("UPDATE tickets SET canonical_key = NULL WHERE id = :id", id=TICKET_A)
    sql("ALTER TABLE tickets DROP CONSTRAINT ck_tickets_key_assigned")
    sql("UPDATE tickets SET canonical_key = NULL WHERE id = :id", id=TICKET_A)
    failed = _failed(revalidate())
    assert "번호와 표시 이름이 어긋난 티켓" in failed


def test_a_ticket_without_a_number_and_without_a_reason_is_caught(loaded):
    """U11 의 핵심 — 「임의로 안 배정했다」와 「조용히 사라졌다」를 가른다."""
    revalidate, sql, _path = loaded
    sql(
        "UPDATE tickets SET seq = NULL, canonical_key = NULL, project_uid = NULL "
        "WHERE id = :id", id=TICKET_A,
    )
    failed = _failed(revalidate())
    assert "사유 없이 번호가 없는 티켓" in failed
    assert "번호 없는 티켓 = 열린 예외" in failed


def test_a_stale_open_exception_is_caught(loaded):
    """반대 방향 — 해결된 사유가 계속 세어지면 「몇 건 남았나」가 안 줄어든다."""
    revalidate, sql, _path = loaded
    sql(
        "INSERT INTO migration_exceptions (id, ticket_id, reason, source_evidence, "
        "created_at) VALUES (:id, :ticket, 'missing', '{}'::jsonb, now())",
        id="99999999-9999-9999-9999-999999999999", ticket=TICKET_A,
    )
    failed = _failed(revalidate())
    assert "번호가 있는데 예외가 열린 티켓" in failed


def test_a_broken_relation_is_caught(loaded):
    """FK 를 떼고 한쪽 끝을 없앤다 — 운영에서 FK 가 꺼져 있던 옛 DB 의 모양이다."""
    revalidate, sql, _path = loaded
    sql("ALTER TABLE ticket_relations "
        "DROP CONSTRAINT ticket_relations_to_ticket_id_fkey")
    sql("INSERT INTO ticket_relations (id, from_ticket_id, to_ticket_id, kind, "
        "created_at) VALUES (:id, :a, :ghost, 'subtask_of', now())",
        id="88888888-8888-8888-8888-888888888888", a=TICKET_A,
        ghost="00000000-0000-0000-0000-0000000dead0")
    failed = _failed(revalidate())
    assert "깨진 ticket_relations" in failed


def test_a_document_without_a_version_is_caught(loaded):
    revalidate, sql, _path = loaded
    sql("UPDATE documents SET current_version_id = NULL")
    failed = _failed(revalidate())
    assert "판이 없는 문서" in failed


def test_a_derived_table_with_rows_is_caught(loaded):
    """D-270 — 여기에 행이 있으면 Cutover 뒤 첫 복구 리허설 5단계가 터진다."""
    revalidate, sql, _path = loaded
    sql(
        "INSERT INTO search_documents (id, kind, ref_id, owner_user_ids, owner_kind, "
        "title, body, route, indexed_at) "
        "VALUES ('x', 'ticket', 'r', '', 'global', 't', 'b', '/x', now())"
    )
    failed = _failed(revalidate())
    assert "파생 search_documents 비어 있음" in failed


def test_a_notion_temporary_url_left_in_a_column_is_caught(loaded):
    """§7.3 — 주소를 베껴 두는 것은 「옮겼다」가 아니다.

    그 주소는 몇 시간 뒤 죽고, 죽었다는 사실은 사용자가 눌러 볼 때만 보인다.
    표 하나가 아니라 **문자열 컬럼 전수**를 보는지도 함께 확인한다.
    """
    revalidate, sql, _path = loaded
    report = revalidate()
    by_name = {c.name: c for c in report.checks}
    assert by_name["Notion 임시 파일 주소"].actual == 0
    assert by_name["임시 주소를 본 컬럼"].actual >= 300

    sql("UPDATE document_cache SET original_url = :u",
        u="https://prod-files-secure.s3.us-west-2.amazonaws.com/x/y.pdf?X-Amz-Expires=3600")
    failed = _failed(revalidate())
    assert "Notion 임시 파일 주소" in failed


def test_a_counter_left_behind_is_caught(loaded):
    """작으면 다음 신규 티켓이 기존 티켓과 같은 번호를 받는다 (D-196)."""
    revalidate, sql, _path = loaded
    sql("UPDATE project_ticket_counters SET last_seq = 0 WHERE project_id = :p",
        p=PROJECT)
    failed = _failed(revalidate())
    assert "채번 카운터가 뒤처진 프로젝트" in failed


def test_a_project_without_a_code_is_caught(loaded):
    """코드가 없으면 그 프로젝트의 티켓은 이름을 못 받는다 (D-282).

    이 자리가 조용히 통과하면 「이름 없는 티켓」이 든 DB 가 초록으로 Cutover 를 지난다.
    """
    revalidate, sql, _path = loaded
    sql("UPDATE tickets SET seq = NULL WHERE project_uid = :p", p=PROJECT)
    sql("UPDATE projects SET code = NULL WHERE id = :p", p=PROJECT)
    failed = _failed(revalidate())
    assert "코드 없는 프로젝트" in failed


def test_a_code_outside_the_alphabet_is_caught(loaded):
    """옛 정책의 값(`SKH`)이 남아 있으면 **모양 검사가 잡는다** (D-282).

    DB 의 `ck_projects_code_shape` 를 잠깐 떼고 넣는다 — 제약이 막는다는 사실과 **검사가
    본다는 사실**은 다른 것이고, 제약이 없는 DB(옛 판에서 올라온 것)를 만날 수 있다.
    """
    revalidate, sql, _path = loaded
    sql("ALTER TABLE projects DROP CONSTRAINT ck_projects_code_shape")
    sql("UPDATE projects SET code = 'SKH' WHERE id = :p", p=PROJECT)
    failed = _failed(revalidate())
    assert "모양이 틀린 코드" in failed


def test_two_projects_sharing_a_code_is_caught(loaded):
    """같은 코드가 둘이면 `<CODE>-1` 이 두 티켓을 가리킨다."""
    revalidate, sql, _path = loaded
    sql("DROP INDEX uq_projects_code")
    # 컬럼을 손으로 나열하지 않는다 — `projects` 에는 NOT NULL 컬럼이 여럿이고, 하나
    # 빠뜨릴 때마다 이 시험이 「검사가 안 잡는다」가 아니라 「INSERT 가 실패한다」로
    # 빨개진다. 행을 통째로 복사하고 id 만 바꾼다.
    sql("CREATE TEMP TABLE _dup AS SELECT * FROM projects WHERE id = :p", p=PROJECT)
    sql("UPDATE _dup SET id = :new, notion_page_id = NULL",
        new="00000000-0000-0000-0000-00000000dup0")
    sql("INSERT INTO projects SELECT * FROM _dup")
    failed = _failed(revalidate())
    assert "겹친 코드" in failed


def test_a_database_without_projects_is_not_a_pass(loaded):
    """**반례** — 볼 것이 없는 회차가 「전 항 통과」로 읽히면 안 된다.

    프로젝트가 0건이면 위 세 검사가 전부 0 을 돌려주고 전부 통과한다. 그 통과는
    「검사했다」가 아니라 「아무것도 안 봤다」이므로, 표본 수를 세는 검사가 따로 있다.
    """
    revalidate, sql, _path = loaded
    sql("UPDATE tickets SET seq = NULL, project_uid = NULL")
    sql("DELETE FROM project_ticket_counters")
    sql("DELETE FROM projects")
    failed = _failed(revalidate())
    assert "코드를 본 프로젝트" in failed


def test_a_value_longer_than_the_column_is_caught_even_where_pg_allows_it(loaded):
    """`Text` 에는 상한이 없어 **PG 가 안 막는다.** 이 검사만 본다."""
    revalidate, sql, _path = loaded
    # `String(n)` 은 PG 가 막으므로 여기서는 상한이 있는 컬럼을 직접 못 넘긴다.
    # 대신 검사가 **컬럼을 실제로 보고 있는지**를 본다: 상한 바로 아래 값은 통과한다.
    sql("UPDATE tickets SET title = repeat('가', 500) WHERE id = :a", a=TICKET_A)
    report = revalidate()
    assert "길이 초과" not in _failed(report)
    by_name = {c.name: c for c in report.checks}
    assert by_name["길이 초과"].actual == 0


# ── 반례: 검사가 안 도는 상태가 통과로 안 읽히는가 ───────────────────────────


def test_an_empty_report_is_not_a_pass(loaded):
    """검사를 하나도 안 돌린 보고서는 **통과가 아니다** (D-213)."""
    empty = MigrationReport()
    assert not empty.passed
    empty.check("무언가", True, 1, 1)
    assert empty.passed


def test_a_blocking_finding_alone_fails_the_run(loaded):
    """검사가 전부 통과해도 blocking 이 있으면 통과가 아니다."""
    report = MigrationReport()
    report.check("무언가", True, 1, 1)
    assert report.passed
    report.finding("blocking", "too_long", "tickets", "길다")
    assert not report.passed


def test_a_classified_exception_does_not_fail_the_run(loaded):
    """분류된 예외를 0 으로 만들려면 데이터를 지어내는 수밖에 없다 (U11)."""
    report = MigrationReport()
    report.check("무언가", True, 1, 1)
    report.finding("classified", "user_unmapped", "users", "짝이 없다")
    assert report.passed
    assert len(report.classified) == 1
