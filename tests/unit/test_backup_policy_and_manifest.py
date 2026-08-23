"""백업 **범위**와 **매니페스트** (S12 · D-203 · D-204).

여기서 못박는 것 셋:

1. **정책이 실제로 `pg_dump` 인자까지 간다.** 「파생 데이터는 백업 안 한다」를 문서에만
   적어 두면 문서만 맞는 상태가 된다 — 서비스가 정말 그 목록을 넘기는지를 본다.
2. **매니페스트가 자기 자신을 포함해 검증된다.** 덤프의 체크섬은 매니페스트가 들지만,
   매니페스트 자신의 체크섬은 자기 안에 못 든다. `SHA256SUMS` 가 그 바깥 한 겹이고,
   그것이 없으면 「무엇이 안 담겼나」에 대한 답이 조용히 바뀔 수 있다.
3. **모르는 것을 지어내지 않는다.** alembic head 를 못 읽으면 `None` 이지 빈 문자열이
   아니다.
"""

from __future__ import annotations

import json

import pytest

from app.backups import manifest as manifest_mod
from app.backups import policy

pytestmark = pytest.mark.unit


# ── 범위 정책 ────────────────────────────────────────────────────────────────


def test_excluded_tables_are_the_derived_four():
    """파생 넷 말고 다른 표가 슬며시 들어오면 그 표의 데이터가 백업에서 사라진다.

    이 목록에 표 하나를 더하는 것은 「그 표는 잃어도 된다」는 선언이다. 그래서 목록
    자체를 시험이 붙잡는다 — 늘리려면 이 시험을 함께 고쳐야 하고, 그 순간 왜 재생성
    가능한지 적게 된다.
    """
    assert policy.excluded_tables() == (
        "document_chunks",
        "ai_index_state",
        "search_documents",
        "rate_limit_buckets",
    )


def test_every_excluded_table_says_who_rebuilds_it():
    """재생성 경로를 못 적는 표는 **재생성 가능한 표가 아니다.**"""
    for table, label, who in policy.EXCLUDED_TABLE_DATA:
        assert label.strip(), table
        assert who.strip().endswith("."), f"{table}: 재생성 주체가 문장으로 안 적혔다"


def test_scope_manifest_carries_both_directions():
    """담는 것과 안 담는 것이 **함께** 실린다. 한쪽만 있으면 복원하는 사람이 판단 못 한다."""
    scope = policy.scope_manifest()
    assert scope["included"], "정본 범위가 비었다"
    assert {item["table"] for item in scope["excluded_table_data"]} == set(
        policy.excluded_tables()
    )


def test_backup_passes_the_policy_to_pg_dump(db, settings, fake_clock, stub_pg_dump):
    """🔴 **정책이 문서가 아니라 명령행까지 간다.**

    이것이 안 걸리면 매니페스트는 「제외했습니다」라고 적는데 덤프에는 그 행이 그대로
    들어 있다 — 문서만 맞고 실제는 다른 상태이고, 그 차이는 복원해 보기 전까지 안 보인다.
    """
    from app.backups.service import run_backup

    run_backup(db, settings, created_by=None, now=fake_clock.now())
    assert stub_pg_dump.calls, "백업이 pg_dump 계층을 아예 안 불렀다"
    assert stub_pg_dump.calls[-1]["exclude_table_data"] == policy.excluded_tables()


# ── 매니페스트 ───────────────────────────────────────────────────────────────


def _write_set(tmp_path):
    set_dir = tmp_path / "backup-20260823_120000_000000"
    set_dir.mkdir()
    (set_dir / manifest_mod.DATABASE_DUMP_NAME).write_bytes(b"PGDMP fake")
    manifest_mod.write(set_dir, {"manifest_version": 1, "scope": policy.scope_manifest()})
    return set_dir


def test_a_clean_set_verifies(tmp_path):
    assert manifest_mod.verify_set(_write_set(tmp_path))["ok"] is True


def test_a_changed_manifest_is_caught(tmp_path):
    """🔴 덤프만 보면 못 잡는다. **범위를 말하는 파일이 바뀌었다**는 것도 손상이다."""
    set_dir = _write_set(tmp_path)
    (set_dir / manifest_mod.MANIFEST_NAME).write_text('{"manifest_version": 1}', encoding="utf-8")
    result = manifest_mod.verify_set(set_dir)
    assert result["ok"] is False
    assert result["changed"] == [manifest_mod.MANIFEST_NAME]


def test_a_changed_dump_is_caught(tmp_path):
    set_dir = _write_set(tmp_path)
    (set_dir / manifest_mod.DATABASE_DUMP_NAME).write_bytes(b"tampered")
    assert manifest_mod.verify_set(set_dir)["changed"] == [manifest_mod.DATABASE_DUMP_NAME]


def test_an_extra_file_is_caught(tmp_path):
    """누가 손댔다는 뜻이다. 조용히 넘기면 무결성 검사가 아니다."""
    set_dir = _write_set(tmp_path)
    (set_dir / "note.txt").write_text("누가 여기에 뭘 뒀다", encoding="utf-8")
    assert manifest_mod.verify_set(set_dir)["extra"] == ["note.txt"]


def test_a_missing_file_is_caught(tmp_path):
    set_dir = _write_set(tmp_path)
    (set_dir / manifest_mod.DATABASE_DUMP_NAME).unlink()
    assert manifest_mod.verify_set(set_dir)["missing"] == [manifest_mod.DATABASE_DUMP_NAME]


def test_a_set_without_checksums_does_not_quietly_pass(tmp_path):
    """반례 — 체크섬 파일이 없으면 「비교할 것이 없어 통과」가 되면 안 된다."""
    set_dir = tmp_path / "backup-empty"
    set_dir.mkdir()
    (set_dir / manifest_mod.DATABASE_DUMP_NAME).write_bytes(b"PGDMP fake")
    result = manifest_mod.verify_set(set_dir)
    assert result["ok"] is False
    assert result["reason"] == "checksums_missing"


def test_checksums_file_is_the_standard_format(tmp_path):
    """`sha256sum -c` 가 그대로 읽어야 한다 — 우리 도구가 없는 서버에서 확인할 수 있게."""
    set_dir = _write_set(tmp_path)
    body = (set_dir / manifest_mod.CHECKSUMS_NAME).read_text(encoding="utf-8")
    for line in body.splitlines():
        digest, sep, name = line.partition("  ")
        assert sep == "  ", line
        assert len(digest) == 64 and name
    assert not body.count("\r"), "CRLF 로 쓰면 리눅스의 sha256sum 이 이름 끝에 \\r 를 붙인다"


def test_manifest_says_it_does_not_know_rather_than_guessing():
    """스키마 판이 둘 다 없으면 `matches` 는 참이 되면 안 된다.

    `None == None` 은 참이라, 그 비교를 그대로 두면 **아무것도 모를 때 「같다」**가 된다.
    """
    from datetime import datetime

    built = manifest_mod.build(
        created_at=datetime(2026, 8, 23, 12, 0, 0),
        created_by=None,
        database={"file": "database.dump"},
        alembic_head_code=None,
        alembic_head_db=None,
        destination=None,
        files=None,
        warnings=[],
    )
    assert built["schema"]["matches"] is False


def test_manifest_is_readable_json_with_korean_intact(tmp_path):
    set_dir = _write_set(tmp_path)
    raw = (set_dir / manifest_mod.MANIFEST_NAME).read_text(encoding="utf-8")
    assert "AI 색인 조각과 임베딩" in raw, "한글이 \\u 이스케이프로 새 나갔다"
    assert json.loads(raw)["manifest_version"] == 1
