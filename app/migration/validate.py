"""적재가 끝난 DB 에 **질문을 던진다** (S13 · MASTER_PLAN §7.3).

## 검증 항목은 계획이 정했다

§7.3 이 이름을 댄 것들이다: 수 · 누락 · 중복 · 변환 실패 · 깨진 Relation ·
깨진 File Link · **문자열 길이 초과** · `canonical_key` 충돌 · Exception 분류 결과.
여기에 **프로젝트 코드**가 더해졌다(D-282) — 모든 프로젝트가 코드를 받았는가 ·
그 코드가 정해진 모양인가 · 두 프로젝트가 같은 코드를 쓰지 않는가.

`legacy_key` 유일성은 **뺐다.** 그 컬럼이 사라졌고(D-283), 없는 컬럼을 세는 검사는
언제나 0 을 돌려주며 통과한다 — 아래 「아무것도 안 세고 통과」가 바로 그것이다.

## 「본 것의 수」를 함께 남긴다

각 검사는 기대와 실제를 둘 다 적는다. 「통과」만 남기면 **아무것도 안 세고 통과한
검사**와 구별되지 않는다 — S12 가 실제로 만난 함정이고(세는 질의가 언제나 0 을
돌려주면 양쪽이 똑같이 0 이라 통과한다), 그래서 이 파일의 자기검증
(`tests/regression/test_migration_validate_probe.py`)이 **틀린 쪽으로도 움직이는지**를
먼저 본다.

## 길이 초과를 소스가 아니라 **적재된 DB** 에서 다시 센다

적재 중에도 센다(`convert.py`). 그런데 그 검사는 「거절했다」는 사실만 남기고, 거절된
행은 DB 에 없다. Exit 조건의 「길이 초과 0」은 **들어간 값**에 대한 질문이므로 여기서
한 번 더 묻는다 — 두 검사가 같은 답을 내야 한다.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.models_base import Base
from app.migration import plan as plan_mod
from app.migration.convert import text_length_limit
from app.migration.report import MigrationReport
from app.work import codes as codes_mod
from app.work import numbering

__all__ = ["validate"]

# 「수를 맞춰야 하는」 표. 소스 표 이름 → 대상 표 이름.
#
# 전부가 아니라 이 목록인 이유: 티켓과 문서는 Notion 이 정본이라 소스(SQLite 미러)와
# 수가 **다른 것이 정상**이다. 그 둘은 아래에서 따로 본다.
COUNT_PAIRS: tuple[tuple[str, str], ...] = (
    ("users", "users"),
    ("departments", "org_units"),
    ("job_titles", "job_titles"),
    ("audit_logs", "audit_logs"),
    ("conversations", "conversations"),
    ("messages", "messages"),
    ("notifications", "notifications"),
    ("jobs", "jobs"),
    # `ticket_comments` 는 여기 없다. 옛 포털 댓글 위에 **Notion 댓글이 더해지므로**
    # (D11) 소스와 대상의 수가 같은 것이 오히려 이상하다. 그 표는 `_comments` 가
    # 「옛 포털 + 이관된 Notion 댓글」로 따로 센다.
    ("ticket_attachments", "ticket_attachments"),
    ("document_comments", "document_comments"),
    ("document_favorites", "document_favorites"),
    ("document_recent_views", "document_recent_views"),
    ("board_posts", "board_posts"),
    ("chat_messages", "chat_messages"),
    ("app_settings", "app_settings"),
    ("config_versions", "config_versions"),
    ("integrations", "integrations"),
    ("prompts", "prompts"),
    ("policies", "policies"),
    ("backups", "backups"),
    ("sessions", "sessions"),
    ("usage_events", "usage_events"),
    ("project_health_snapshots", "project_health_snapshots"),
)

# 이관이 **행을 더하는** 표. 소스에서 온 행만 골라 세야 수가 맞는다.
#
# `ticket_attachments` 가 그렇다: 티켓 본문에 박혀 있던 이미지가 여기로 오고(B2), 그
# 행들은 소스의 첨부가 아니라 본문이다. 거르지 않으면 이 검사는 「본문 이미지를 옮겼다」는
# 이유로 빨간불이 되고, 그러면 성공이 실패로 읽힌다. 고르는 잣대는 지어낸 것이 아니라
# **사실**이다 — 이관이 가져온 파일에는 올린 사람이 없다(D12).
COUNT_FILTERS: dict[str, str] = {
    "ticket_attachments": "uploaded_by_user_id IS NOT NULL",
}


def validate(db: Session, source, report: MigrationReport, *, notion) -> MigrationReport:
    """검사를 전부 돌고 결과를 보고서에 쌓는다. **예외를 삼키지 않는다.**"""
    _counts(db, source, report)
    _notion_counts(db, report, notion=notion)
    _comments(db, source, report, notion=notion)
    _no_missing(db, source, report)
    _uniqueness(db, report)
    _project_codes(db, report)
    _relations(db, report)
    _file_links(db, report)
    _lengths(db, report)
    _no_temporary_urls(db, report)
    _bodies(db, report)
    _migration_space_is_visible(db, report)
    _exceptions(db, report)
    _derived_empty(db, report)
    _conversion_findings(report)
    _counters(db, report)
    return report


def _scalar(db: Session, sql: str, params: dict | None = None) -> int:
    return int(db.execute(sa.text(sql), params or {}).scalar_one())


def _counts(db: Session, source, report: MigrationReport) -> None:
    """수 — 소스와 대상이 같은가."""
    source_tables = set(source.tables())
    checked = 0
    for source_table, target_table in COUNT_PAIRS:
        if source_table not in source_tables:
            continue
        checked += 1
        expected = source.count(source_table)
        clause = COUNT_FILTERS.get(target_table)
        actual = _scalar(
            db,
            f'SELECT count(*) FROM "{target_table}"'
            + (f" WHERE {clause}" if clause else ""),
        )
        report.check(
            f"수 {source_table} → {target_table}", actual == expected, expected, actual,
            f"이관이 더한 행은 뺐다: {clause}" if clause else "",
        )
    # 「몇 개를 셌는가」를 남긴다. 이 수가 없으면 **아무것도 안 센 회차**와 전부 센
    # 회차를 구별할 수 없다 (D-213). 문턱을 걸지 않는 이유는 소스마다 표가 달라서다 —
    # 「이 소스에 그 표가 없었다」는 `plan.classify` 가 따로 보고한다.
    report.check(
        "수를 대조한 표", checked > 0, "> 0", checked,
        f"목록 {len(COUNT_PAIRS)}쌍 중 이 소스에 있는 것",
    )
    # 목록 자체의 오타는 **소스와 무관하게** 잡는다. 오타 하나가 있으면 그 표는
    # 「소스에 없다」로 읽혀 조용히 안 세어진다 — 그리고 그 사실은 아무 데도 안 남는다.
    unknown_source = sorted(
        {s for s, _t in COUNT_PAIRS} - set(plan_mod.LEGACY_TABLES)
    )
    unknown_target = sorted(
        {t for _s, t in COUNT_PAIRS} - set(Base.metadata.tables)
    )
    report.check(
        "수 대조 목록에 오타가 없는가",
        not unknown_source and not unknown_target, 0,
        len(unknown_source) + len(unknown_target),
        _sample(unknown_source + unknown_target),
    )


def _notion_counts(db: Session, report: MigrationReport, *, notion: dict) -> None:
    """티켓·문서·프로젝트는 **Notion 이 정본**이라 그쪽 수와 맞춘다."""
    for role, table, label in (
        ("tasks", "tickets", "티켓"),
        ("documents", "documents", "문서"),
        ("projects", "projects", "프로젝트"),
    ):
        expected = notion.get(role)
        if expected is None:
            continue
        actual = _scalar(db, f'SELECT count(*) FROM "{table}"')
        # 미러에만 있는 행(원본에서 사라진 것)은 지우지 않으므로 대상이 더 많을 수 있다.
        # **적으면 누락이다.**
        report.check(
            f"수 {label} (Notion {expected} 이상)", actual >= expected, f">= {expected}",
            actual, "지우지 않으므로 대상이 더 많을 수 있습니다.",
        )


# 댓글 한 건을 「안 넣기로 하고 사유를 남긴」 자리. 이 목록이 곧 「분류된 예외」의
# 정의이므로 적재가 새 사유를 만들면 여기에도 더해야 한다 — 안 더하면 그 건수가
# 아래 등식에서 사라지고, 사라진 만큼이 「원본에는 있는데 어디에도 없다」가 된다.
COMMENT_EXCEPTION_KINDS: tuple[str, ...] = (
    "comment_ticket_missing",
    "comment_author_unresolved",
    "comment_body_empty",
    "comment_time_missing",
)


def _comments(db: Session, source, report: MigrationReport, *, notion: dict) -> None:
    """티켓 댓글 — **원본 수 = 이관된 수 + 분류된 예외** (D11).

    수 하나만 보면 안 되는 이유가 이 등식에 들어 있다. 「이관된 수」만 세면 못 옮긴
    것이 몇 건인지 안 나오고, 「예외만」 세면 그 예외가 전부인지 모른다. 둘을 더해
    원본과 맞춰야 **한 건도 그냥 사라지지 않았다**가 증명된다.

    예외 건수는 이번 회차의 Finding 에서 센다. 그래서 이 검사는 **댓글을 실제로 옮긴
    회차**에서만 돈다 — 나중에 `verify` 만 다시 도는 회차에는 그 Finding 이 없고, 없는
    것을 0 으로 읽으면 등식이 거짓으로 깨진다.
    """
    migrated = _scalar(
        db,
        "SELECT count(*) FROM legacy_mapping "
        "WHERE legacy_source = 'notion' AND target_type = 'comment'",
    )
    expected = notion.get("comments")
    if expected is not None:
        excepted = sum(
            1 for finding in report.findings if finding.kind in COMMENT_EXCEPTION_KINDS
        )
        report.check(
            "원본 댓글 = 이관된 댓글 + 분류된 예외",
            migrated + excepted == expected, expected, migrated + excepted,
            f"이관 {migrated}건, 분류된 예외 {excepted}건",
        )

    if "ticket_comments" not in set(source.tables()):
        return
    legacy = source.count("ticket_comments")
    actual = _scalar(db, "SELECT count(*) FROM ticket_comments")
    # 옛 포털 댓글은 표 복사가 그대로 옮기고, 그 위에 Notion 댓글이 더해진다. 적으면
    # 둘 중 하나가 샌 것이고, 많으면 재실행이 같은 댓글을 두 번 넣은 것이다.
    report.check(
        "수 ticket_comments (옛 포털 + 이관된 Notion 댓글)",
        actual == legacy + migrated, legacy + migrated, actual,
        f"옛 포털 {legacy}건, 이관 {migrated}건",
    )


def _no_missing(db: Session, source, report: MigrationReport) -> None:
    """누락 — 소스 행마다 대상 행이 있는가. 표본이 아니라 **전수**다."""
    tables = set(source.tables())
    if "ticket_cache" in tables:
        ids = {row["id"] for row in source.select("SELECT id FROM ticket_cache")}
        present = {
            row[0] for row in db.execute(sa.text("SELECT id FROM tickets")).all()
        }
        missing = sorted(ids - present)
        report.check(
            "누락 ticket_cache → tickets", not missing, 0, len(missing),
            _sample(missing),
        )
    if "document_cache" in tables:
        pages = {
            row["notion_page_id"]
            for row in source.select(
                "SELECT notion_page_id FROM document_cache "
                "WHERE notion_page_id IS NOT NULL"
            )
        }
        bridged = {
            row[0] for row in db.execute(
                sa.text(
                    "SELECT legacy_page_id FROM documents "
                    "WHERE legacy_page_id IS NOT NULL"
                )
            ).all()
        }
        missing = sorted(pages - bridged)
        report.check(
            "누락 document_cache → documents", not missing, 0, len(missing),
            _sample(missing),
        )
    if "users" in tables:
        ids = {row["id"] for row in source.select("SELECT id FROM users")}
        present = {row[0] for row in db.execute(sa.text("SELECT id FROM users")).all()}
        missing = sorted(ids - present)
        report.check("누락 users", not missing, 0, len(missing), _sample(missing))


def _uniqueness(db: Session, report: MigrationReport) -> None:
    """중복 — 하나여야 하는 것이 하나인가."""
    report.check(
        "중복 canonical_key",
        _scalar(db, "SELECT count(*) FROM (SELECT canonical_key FROM tickets "
                    "WHERE canonical_key IS NOT NULL GROUP BY canonical_key "
                    "HAVING count(*) > 1) d") == 0,
        0,
        _scalar(db, "SELECT count(*) FROM (SELECT canonical_key FROM tickets "
                    "WHERE canonical_key IS NOT NULL GROUP BY canonical_key "
                    "HAVING count(*) > 1) d"),
    )
    report.check(
        "중복 documents.legacy_page_id",
        _scalar(db, "SELECT count(*) FROM (SELECT legacy_page_id FROM documents "
                    "WHERE legacy_page_id IS NOT NULL GROUP BY legacy_page_id "
                    "HAVING count(*) > 1) d") == 0,
        0,
        _scalar(db, "SELECT count(*) FROM (SELECT legacy_page_id FROM documents "
                    "WHERE legacy_page_id IS NOT NULL GROUP BY legacy_page_id "
                    "HAVING count(*) > 1) d"),
    )
    dup_map = _scalar(
        db,
        "SELECT count(*) FROM (SELECT legacy_source, legacy_source_id, target_type "
        "FROM legacy_mapping GROUP BY 1,2,3 HAVING count(*) > 1) d",
    )
    report.check("중복 legacy_mapping", dup_map == 0, 0, dup_map)
    total_map = _scalar(db, "SELECT count(*) FROM legacy_mapping")
    report.check("legacy_mapping 행", total_map > 0, "> 0", total_map)


def _project_codes(db: Session, report: MigrationReport) -> None:
    """프로젝트 코드 — **전부 받았는가 · 모양이 맞는가 · 겹치지 않는가** (D-282).

    셋을 따로 세는 이유는 고칠 방법이 다르기 때문이다. 「못 받았다」는 앞 단계가 안
    돈 것이고, 「모양이 틀렸다」는 옛 정책의 값이 남은 것이며, 「겹쳤다」는 생성기가
    충돌을 안 푼 것이다. 하나로 뭉치면 세 원인 중 무엇인지 보고서만 보고는 모른다.

    **표본 수를 함께 남긴다.** 프로젝트가 0건인 DB 에서는 셋 다 0 이라 전부 통과하는데,
    그 통과는 「검사했다」가 아니라 「볼 것이 없었다」다.
    """
    total = _scalar(db, "SELECT count(*) FROM projects")
    report.check("코드를 본 프로젝트", total > 0, "> 0", total)

    without = _scalar(db, "SELECT count(*) FROM projects WHERE code IS NULL OR code = ''")
    report.check("코드 없는 프로젝트", without == 0, 0, without)

    shape = "^[" + codes_mod.CODE_ALPHABET + "]{" + str(codes_mod.CODE_LENGTH) + "}$"
    bad = db.execute(
        sa.text(
            "SELECT id, code FROM projects "
            "WHERE code IS NOT NULL AND code !~ :shape"
        ),
        {"shape": shape},
    ).all()
    report.check(
        "모양이 틀린 코드", not bad, 0, len(bad),
        _sample([str(row[1]) for row in bad]),
    )

    dup = db.execute(sa.text(
        "SELECT code FROM projects WHERE code IS NOT NULL "
        "GROUP BY code HAVING count(*) > 1"
    )).all()
    report.check(
        "겹친 코드", not dup, 0, len(dup), _sample([str(row[0]) for row in dup])
    )


def _relations(db: Session, report: MigrationReport) -> None:
    """깨진 Relation — 양끝이 다 있는가, 부모가 하나인가."""
    broken = _scalar(db, (
        "SELECT count(*) FROM ticket_relations r "
        "LEFT JOIN tickets a ON a.id = r.from_ticket_id "
        "LEFT JOIN tickets b ON b.id = r.to_ticket_id "
        "WHERE a.id IS NULL OR b.id IS NULL"
    ))
    report.check("깨진 ticket_relations", broken == 0, 0, broken)

    two_parents = _scalar(db, (
        "SELECT count(*) FROM (SELECT from_ticket_id FROM ticket_relations "
        "WHERE kind = 'subtask_of' GROUP BY from_ticket_id HAVING count(*) > 1) d"
    ))
    report.check("부모가 둘인 티켓", two_parents == 0, 0, two_parents)

    dangling_project = _scalar(db, (
        "SELECT count(*) FROM tickets t LEFT JOIN projects p ON p.id = t.project_uid "
        "WHERE t.project_uid IS NOT NULL AND p.id IS NULL"
    ))
    report.check("소속 프로젝트가 없는 티켓", dangling_project == 0, 0, dangling_project)

    dangling_space = _scalar(db, (
        "SELECT count(*) FROM documents d "
        "LEFT JOIN knowledge_spaces s ON s.id = d.space_id WHERE s.id IS NULL"
    ))
    report.check("공간이 없는 문서", dangling_space == 0, 0, dangling_space)

    no_version = _scalar(
        db, "SELECT count(*) FROM documents WHERE current_version_id IS NULL"
    )
    report.check("판이 없는 문서", no_version == 0, 0, no_version)


def _file_links(db: Session, report: MigrationReport) -> None:
    """깨진 File Link — 첨부가 가리키는 파일이 실재하고 바이트가 있는가."""
    broken = _scalar(db, (
        "SELECT count(*) FROM document_attachments a "
        "LEFT JOIN files f ON f.id = a.file_id WHERE f.id IS NULL"
    ))
    report.check("깨진 document_attachments", broken == 0, 0, broken)

    no_provider = _scalar(db, (
        "SELECT count(*) FROM files f "
        "LEFT JOIN storage_providers p ON p.id = f.storage_provider_id "
        "WHERE p.id IS NULL"
    ))
    report.check("저장소 없는 파일 행", no_provider == 0, 0, no_provider)

    bad_checksum = _scalar(
        db, "SELECT count(*) FROM files WHERE length(checksum_sha256) <> 64"
    )
    report.check("체크섬이 없는 파일 행", bad_checksum == 0, 0, bad_checksum)


def _lengths(db: Session, report: MigrationReport) -> None:
    """문자열 길이 초과 — **적재된 값**을 다시 센다.

    `VARCHAR(n)` 은 PG 가 이미 막는다. 그런데도 세는 이유는 두 가지다: (1) 「막혔다」와
    「넘는 값이 없었다」는 다른 사실이고, Exit 조건이 묻는 것은 후자다. (2) `Text`
    컬럼에는 상한이 없어 PG 가 안 막는다 — 거기 들어간 초장문은 이 검사만 본다.
    """
    over = 0
    checked = 0
    details: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name in plan_mod.DERIVED_TABLES:
            continue
        columns = [
            column for column in table.columns
            if text_length_limit(column) is not None
        ]
        if not columns:
            continue
        parts = [
            f"count(*) FILTER (WHERE length({column.name}) > "
            f"{text_length_limit(column)})"
            for column in columns
        ]
        row = db.execute(
            sa.text(f'SELECT {", ".join(parts)} FROM "{table.name}"')
        ).one()
        checked += len(columns)
        for column, value in zip(columns, row):
            if value:
                over += int(value)
                details.append(f"{table.name}.{column.name}={value}")
    report.check("길이 초과", over == 0, 0, over, _sample(details))
    # 「아무 컬럼도 안 봤다」가 0 으로 보이지 않게 한다 (D-213).
    report.check("길이를 본 컬럼", checked >= 300, ">= 300", checked)


# Notion 이 첨부에 내주는 임시 주소의 호스트. 이 문자열이 어느 컬럼에든 들어가면
# 그 값은 **몇 시간 뒤 죽는다** — 그리고 죽었다는 사실은 사용자가 눌러 볼 때만 보인다.
_TEMPORARY_URL_MARK = "prod-files-secure.s3"


def _no_temporary_urls(db: Session, report: MigrationReport) -> None:
    """§7.3 — **Notion 임시 File URL 을 새 DB 에 저장하지 않는다.**

    바이트를 실제 저장소로 옮기는 것이 이관의 일이고(D-250), 주소를 베껴 두는 것은
    「옮겼다」가 아니다. 그 주소는 몇 시간 뒤 죽는데 그때 남는 것은 **깨진 링크**이고,
    링크가 죽었다는 사실은 오류 로그가 아니라 사용자의 클릭에서만 드러난다.

    표 하나가 아니라 **문자열 컬럼 전수**를 본다. 「어느 컬럼에 새어 들어갈 수 있는가」를
    미리 아는 방법이 없기 때문이다 — 미러의 `original_url`·`source_url`·`memo` 어디로든
    갈 수 있다.
    """
    columns = [
        (table.name, column.name)
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if isinstance(column.type, (sa.String, sa.Text))
    ]
    hits: list[str] = []
    total = 0
    for table_name, column_name in columns:
        count = _scalar(
            db,
            f'SELECT count(*) FROM "{table_name}" WHERE "{column_name}" LIKE :mark',
            {"mark": f"%{_TEMPORARY_URL_MARK}%"},
        )
        if count:
            total += count
            hits.append(f"{table_name}.{column_name}={count}")
    report.check("Notion 임시 파일 주소", total == 0, 0, total, _sample(hits))
    # 「아무 컬럼도 안 봤다」가 0 으로 보이지 않게 한다 (D-213).
    report.check("임시 주소를 본 컬럼", len(columns) >= 300, ">= 300", len(columns))
    # 본문 정본은 `JSONB` 라 위 훑기가 못 본다. 이미지 `src` 가 바로 그 안에 있고, 거기
    # 서명 주소가 남으면 한 시간 뒤 문서마다 깨진 그림이 뜬다 (D4).
    in_body = _scalar(
        db,
        "SELECT count(*) FROM document_versions WHERE body::text LIKE :mark",
        {"mark": f"%{_TEMPORARY_URL_MARK}%"},
    )
    report.check("본문 JSON 의 임시 파일 주소", in_body == 0, 0, in_body)
    # 티켓 본문은 마크다운이라 위 훑기가 이미 본다. 그런데도 **따로 이름을 붙여 센다**:
    # 뭉쳐 세면 「티켓 본문에 서명 주소가 남았다」와 「미러의 어느 메모 컬럼에 남았다」가
    # 한 숫자가 되고, 둘은 고칠 자리가 다르다. 본 티켓 수를 함께 남겨 「본문이 아예
    # 없었다」와 구별한다 (D-213).
    ticket_bodies = _scalar(
        db, "SELECT count(*) FROM tickets WHERE coalesce(body_markdown, '') <> ''"
    )
    in_ticket = _scalar(
        db,
        "SELECT count(*) FROM tickets WHERE body_markdown LIKE :mark",
        {"mark": f"%{_TEMPORARY_URL_MARK}%"},
    )
    report.check(
        "티켓 본문의 임시 파일 주소", in_ticket == 0, 0, in_ticket,
        f"본문이 있는 티켓 {ticket_bodies}건을 봤다",
    )


def _bodies(db: Session, report: MigrationReport) -> None:
    """본문이 **글자 자리표시자로 바뀐 채** 들어가지 않았는가 (S14).

    옛 회차는 우리 스키마에 자리가 없는 블록을 `[원본에서 확인: image]` 같은 문단으로
    바꿔 넣었다. 그 문단은 오류가 아니라 **정상으로 보이는 손실**이다 — 검사도 화면도
    아무 말을 안 하고, 표 셀의 글자 31,310자가 어디에도 안 남는다.

    **문서와 티켓을 같이 본다.** 문서만 보면 티켓 본문 222블록이 글자로 남은 채로 초록이
    되고, 실제로 그것이 B2 이전의 상태였다.

    「본문이 몇 건인가」를 함께 센다. 0 이면 위 검사도 0 이라 둘 다 통과하는데, 그것은
    「자리표시자가 없다」가 아니라 **본문을 안 옮겼다**는 뜻이다 (D-213).
    """
    bodies = _scalar(db, "SELECT count(*) FROM document_versions")
    placeholders = _scalar(
        db,
        "SELECT count(*) FROM document_versions WHERE body_text LIKE :mark",
        {"mark": "%[원본에서 확인: %"},
    )
    report.check(
        "본문에 남은 옛 자리표시자", placeholders == 0, 0, placeholders,
        f"판 {bodies}개를 봤다",
    )
    ticket_bodies = _scalar(
        db, "SELECT count(*) FROM tickets WHERE coalesce(body_markdown, '') <> ''"
    )
    ticket_placeholders = _scalar(
        db,
        "SELECT count(*) FROM tickets WHERE body_markdown LIKE :mark",
        {"mark": "%[원본에서 확인: %"},
    )
    # 「몇 건을 실제로 옮겼는가」를 같은 줄에 남긴다. 안 남기면 자리표시자 0 이
    # 「깨끗하다」인지 「본문을 아예 안 옮겼다」인지 보고서만 보고는 못 가른다.
    # 올린 사람이 없는 첨부가 곧 이관이 본문에서 옮겨 온 파일이다(D12).
    moved = _scalar(
        db, "SELECT count(*) FROM ticket_attachments WHERE uploaded_by_user_id IS NULL"
    )
    report.check(
        "티켓 본문에 남은 옛 자리표시자", ticket_placeholders == 0, 0,
        ticket_placeholders,
        f"본문이 있는 티켓 {ticket_bodies}건을 봤고 본문 파일 {moved}건을 옮겼다",
    )


def _migration_space_is_visible(db: Session, report: MigrationReport) -> None:
    """이관 문서가 든 공간이 **누군가에게 보이는가** (D7).

    `_stored_ownership_rules` 는 소속 갈래 셋만 열어 주고 `owner_kind='unset'` 은 어느
    갈래에도 안 건다. 그래서 `unset` 공간의 문서는 전역 조회 권한을 가진 사람 말고는
    아무도 못 보고, **오류는 하나도 안 난다.** 실측에서 활성 24명 중 20명이 문서 110건을
    하나도 못 봤다.
    """
    unset = _scalar(
        db,
        "SELECT count(*) FROM knowledge_spaces s WHERE s.owner_kind = 'unset' "
        "AND EXISTS (SELECT 1 FROM documents d WHERE d.space_id = s.id)",
    )
    report.check("소속 없는 공간에 든 문서", unset == 0, 0, unset)
    orphan_org = _scalar(
        db,
        "SELECT count(*) FROM knowledge_spaces "
        "WHERE owner_kind = 'organization' AND org_id IS NULL",
    )
    # 조직 갈래는 `owner_kind` 와 `org_id` 를 **함께** 본다. 하나만 서 있으면 절이 여전히
    # 안 걸리고 화면은 고치기 전과 똑같다.
    report.check("조직 소유인데 조직이 없는 공간", orphan_org == 0, 0, orphan_org)


def _exceptions(db: Session, report: MigrationReport) -> None:
    """Exception 분류 — 번호 없는 티켓과 열린 예외가 **정확히 짝**인가.

    한쪽만 보면 둘 다 놓친다. 「예외 없이 번호가 없는 티켓」은 조용히 사라진 티켓이고,
    「번호가 있는데 예외가 열려 있는 티켓」은 이미 해결된 사유가 계속 세어지는 것이다.
    """
    unassigned = _scalar(db, "SELECT count(*) FROM tickets WHERE seq IS NULL")
    open_exceptions = _scalar(
        db, "SELECT count(*) FROM migration_exceptions WHERE resolved_at IS NULL"
    )
    report.check(
        "번호 없는 티켓 = 열린 예외", unassigned == open_exceptions,
        unassigned, open_exceptions,
    )
    unexplained = _scalar(db, (
        "SELECT count(*) FROM tickets t LEFT JOIN migration_exceptions m "
        "ON m.ticket_id = t.id AND m.resolved_at IS NULL "
        "WHERE t.seq IS NULL AND m.id IS NULL"
    ))
    report.check("사유 없이 번호가 없는 티켓", unexplained == 0, 0, unexplained)

    numbered_but_open = _scalar(db, (
        "SELECT count(*) FROM tickets t JOIN migration_exceptions m "
        "ON m.ticket_id = t.id AND m.resolved_at IS NULL WHERE t.seq IS NOT NULL"
    ))
    report.check("번호가 있는데 예외가 열린 티켓", numbered_but_open == 0, 0,
                 numbered_but_open)

    inconsistent = _scalar(db, (
        "SELECT count(*) FROM tickets WHERE "
        "(seq IS NULL) <> (canonical_key IS NULL)"
    ))
    report.check("번호와 표시 이름이 어긋난 티켓", inconsistent == 0, 0, inconsistent)


def _counters(db: Session, report: MigrationReport) -> None:
    """채번 시드 — `last_seq` 가 실제 최대 번호와 같은가 (D-196).

    작으면 **다음 신규 티켓이 기존 티켓과 같은 번호를 받는다.** 그 사고는 유니크가
    잡아 주지만, 잡히는 자리는 사용자가 「저장」을 누른 뒤다.
    """
    behind = numbering.projects_behind(db)
    report.check("채번 카운터가 뒤처진 프로젝트", behind == 0, 0, behind)


def _derived_empty(db: Session, report: MigrationReport) -> None:
    """파생 넷이 비어 있는가 (D-270).

    비어 있는 것이 **정상**이다. 여기에 행이 있으면 이관이 백업 정책과 다른 목록을
    쓰고 있다는 뜻이고, 그 상태는 Cutover 뒤 첫 복구 리허설 5단계에서 터진다.
    """
    for table in plan_mod.DERIVED_TABLES:
        rows = _scalar(db, f'SELECT count(*) FROM "{table}"')
        report.check(f"파생 {table} 비어 있음", rows == 0, 0, rows)


def _conversion_findings(report: MigrationReport) -> None:
    """변환 실패 — 적재가 거절한 값이 있는가."""
    too_long = [f for f in report.findings if f.kind == "too_long"]
    unreadable = [f for f in report.findings if f.kind == "unreadable"]
    rejected = [f for f in report.findings if f.kind == "row_rejected"]
    report.check("변환 실패 (길이)", not too_long, 0, len(too_long),
                 _sample([f.where for f in too_long]))
    report.check("변환 실패 (읽기)", not unreadable, 0, len(unreadable),
                 _sample([f.where for f in unreadable]))
    report.check("거절된 행", not rejected, 0, len(rejected),
                 _sample([f.line() for f in rejected]))


def _sample(values, limit: int = 5) -> str:
    values = list(values)
    if not values:
        return ""
    head = ", ".join(str(value) for value in values[:limit])
    more = f" 외 {len(values) - limit}건" if len(values) > limit else ""
    return head + more
