"""`pg_dump -Fc` 백업 계층 (§6.1 · §12 · D-204).

qa-contract-replaced-by: tests/unit/test_sqlite_backup.py

옛 파일은 `sqlite3.Connection.backup()` + `PRAGMA integrity_check` 를 못박았다. 그 계약은
사라졌다 — PG 에는 파일 복사로 성립하는 백업이 없다.

**여기서 못박는 것은 옛 파일이 못 박던 것보다 하나 많다.** 옛 계약은 "파일이 열리는가"
까지였다. 새 계약은 거기에 **"어디까지 검증했는지 정직하게 말하는가"** 를 더한다 —
`restore_test` 가 임시 DB 복원을 못 했을 때 조용히 «검증됨» 을 돌려주면, 정작 복원이 안
되는 백업이 대시보드에서 초록으로 보인다. 그것이 D-204 가 "파일 생성만으로 SUCCESS 가
아니다" 라고 적은 실패다.

## 실제 `pg_dump` 왕복은 어디서 보는가

`pg_dump`/`pg_restore` 는 PostgreSQL 서버와 함께 깔린다. 개발 머신(Windows)에는 없고
배포 대상(Ubuntu)에는 있다. 그래서 왕복 자체는 **실 서버에서** 확인하고
(`docs/platform/EVIDENCE/S2/pg_backup_roundtrip.txt`), 여기서는 바이너리 없이 판정할 수
있는 것을 전부 판정한다 — 특히 **바이너리가 없을 때 조용히 통과하지 않는가**를.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.backups import pg_backup

NOW = datetime(2026, 8, 21, 12, 0, 0)


# ── URL → libpq 환경 ─────────────────────────────────────────────────────────


def test_password_goes_to_the_environment_never_the_command_line():
    """비밀번호가 명령행에 실리면 `ps` 로 읽히고, 실패 로그에 명령행이 통째로 찍힌다."""
    env, dbname = pg_backup.libpq_env("postgresql://bob:s3cr3t@db.example:5433/clovir")
    assert env["PGPASSWORD"] == "s3cr3t"
    assert env["PGUSER"] == "bob"
    assert env["PGHOST"] == "db.example"
    assert env["PGPORT"] == "5433"
    assert dbname == "clovir"


def test_percent_encoded_credentials_are_decoded():
    """URL 은 `@`·`/` 가 든 비밀번호를 퍼센트 인코딩한다. 그대로 넘기면 인증이 실패한다."""
    env, _ = pg_backup.libpq_env("postgresql://a%40b:p%2Fw@127.0.0.1/clovir")
    assert env["PGUSER"] == "a@b"
    assert env["PGPASSWORD"] == "p/w"


def test_socket_url_without_host_or_password_is_fine():
    """운영은 유닉스 소켓 + peer 인증이라 host/password 가 없다."""
    env, dbname = pg_backup.libpq_env("postgresql:///clovir")
    assert dbname == "clovir"
    assert "PGPASSWORD" not in env


# ── 도구 해석 ────────────────────────────────────────────────────────────────


def test_bin_dir_is_not_silently_ignored(tmp_path):
    """`bin_dir` 를 줬는데 거기 없으면 **PATH 로 내려가지 않는다.**

    내려가면 서버보다 낮은 버전의 `pg_dump` 를 집어 들 수 있고, 그건 실행을 거부한다 —
    "백업이 한 번도 성공한 적 없다" 를 백업을 되돌리려는 날에야 알게 된다.
    """
    with pytest.raises(pg_backup.PgToolMissing):
        pg_backup.resolve_tool("pg_dump", str(tmp_path))


def test_bin_dir_finds_the_tool_when_present(tmp_path):
    (tmp_path / "pg_dump").write_text("#!/bin/sh\n", encoding="utf-8")
    assert pg_backup.resolve_tool("pg_dump", str(tmp_path)) == str(tmp_path / "pg_dump")


# ── 검증이 정직한가 ──────────────────────────────────────────────────────────


def test_missing_file_is_not_ok(tmp_path):
    assert pg_backup.verify_backup(tmp_path / "nope.dump") == {
        "ok": False, "reason": "file_missing",
    }


def test_checksum_mismatch_is_caught_before_any_tool_runs(tmp_path):
    """체크섬은 도구 없이도 볼 수 있다 — 파일이 바뀌었으면 그 자리에서 실패다."""
    path = tmp_path / "b.dump"
    path.write_bytes(b"PGDMP-ish bytes")
    result = pg_backup.verify_backup(path, "0" * 64)
    assert result == {"ok": False, "reason": "checksum_mismatch"}


def test_checksum_matches_its_own_file(tmp_path):
    path = tmp_path / "b.dump"
    path.write_bytes(b"PGDMP-ish bytes")
    assert pg_backup.sha256_file(path) == pg_backup.sha256_file(path)


def test_a_missing_tool_fails_it_does_not_pass(tmp_path, monkeypatch):
    """도구가 없으면 **실패**다. 통과시키면 '검증됨' 이 아무 뜻도 없어진다."""
    path = tmp_path / "b.dump"
    path.write_bytes(b"x")
    monkeypatch.setattr(pg_backup, "resolve_tool", _raise_missing)
    result = pg_backup.verify_backup(path)
    assert result["ok"] is False
    assert "tool_missing" in result["reason"]


def _raise_missing(name, bin_dir=None):
    raise pg_backup.PgToolMissing(f"{name} 없음")


def test_restore_test_says_so_when_it_only_checked_the_structure(tmp_path, monkeypatch):
    """복원 대상 서버를 모르면 **구조만 봤다고 말한다.**

    조용히 `ok=True, reason=None` 을 돌려주면 대시보드가 "복원까지 확인함" 으로 읽는다 —
    D-204 가 막으려는 바로 그 거짓 초록이다.
    """
    path = tmp_path / "b.dump"
    path.write_bytes(b"x")
    monkeypatch.setattr(
        pg_backup, "verify_backup", lambda *a, **k: {"ok": True, "reason": None}
    )
    result = pg_backup.restore_test(path)
    assert result["ok"] is True
    assert result["reason"].startswith("structure_only")


def test_restore_test_fails_when_the_structure_is_bad(tmp_path, monkeypatch):
    """구조 검증이 실패하면 복원을 시도하지도 않고 그 이유를 그대로 올린다."""
    path = tmp_path / "b.dump"
    path.write_bytes(b"x")
    monkeypatch.setattr(
        pg_backup, "verify_backup", lambda *a, **k: {"ok": False, "reason": "archive_empty"}
    )
    assert pg_backup.restore_test(path, database_url="postgresql:///x") == {
        "ok": False, "reason": "archive_empty",
    }


def test_dump_suffix_is_not_sql(tmp_path):
    """custom format 은 텍스트가 아니다 — 이름이 그 사실을 말해야 `cat` 으로 열지 않는다."""
    assert pg_backup.BACKUP_SUFFIX == ".dump"


# ── 옆 데이터베이스를 가리키기 (S12 — 복구 리허설이 복원본을 앱에 물릴 때) ────


def test_sibling_url_keeps_the_socket_shape():
    """🔴 유닉스 소켓 + peer 인증(`postgresql:///db`)이 **운영의 모양**이다.

    `urlunparse` 로 다시 조립하면 `netloc` 이 비어 `//` 가 떨어지고 `postgresql:/db` 가
    된다 — `normalize_database_url` 이 그것을 「PostgreSQL 주소가 아니다」로 거절한다.
    실 서버 리허설에서 실제로 여기서 멈췄다.
    """
    from app.core.db import normalize_database_url

    url = pg_backup.sibling_url("postgresql:///clovirassist", "restored_1")
    assert url == "postgresql:///restored_1"
    normalize_database_url(url)  # 거절하면 여기서 예외가 난다


def test_sibling_url_does_not_re_encode_the_password():
    """자격증명을 다시 조립하면 `@`·`/` 의 퍼센트 인코딩이 풀려 인증이 조용히 실패한다."""
    url = pg_backup.sibling_url("postgresql://a%40b:p%2Fw@db:5433/clovir", "restored_2")
    assert url == "postgresql://a%40b:p%2Fw@db:5433/restored_2"
    env, dbname = pg_backup.libpq_env(url)
    assert env["PGUSER"] == "a@b" and env["PGPASSWORD"] == "p/w" and dbname == "restored_2"


def test_sibling_url_carries_the_query_string():
    """`?host=/run/postgresql` 은 **어디에 붙는지**다. 떨어뜨리면 다른 서버를 가리킨다."""
    assert pg_backup.sibling_url(
        "postgresql://svc@/clovir?host=/run/postgresql", "restored_3"
    ) == "postgresql://svc@/restored_3?host=/run/postgresql"


# ── 부분 검증을 «검증됨» 이라고 하지 않는가 (D-204) ──────────────────────────


def test_partial_verification_does_not_claim_verified(db, settings, monkeypatch):
    """구조까지만 봤으면 `verified` 가 아니라 `succeeded` + 안내다.

    `verified` 라는 상태값의 뜻은 "되돌릴 수 있음을 확인했다" 이다. 임시 복원을 못 한
    백업에 그 이름표를 달면, 정작 복원이 안 되는 백업이 대시보드에서 초록으로 보이고
    그 사실을 되돌려야 하는 날에 알게 된다 — D-204 가 "파일 생성만으로 SUCCESS 가
    아니다" 라고 적은 실패다.
    """
    from app.backups import service
    from app.backups.models import STATUS_SUCCEEDED

    def fake_backup(database_url, dest_path, *, bin_dir=None, exclude_table_data=()):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text("fake", encoding="utf-8")
        return {"size_bytes": 4, "checksum": "abc"}

    monkeypatch.setattr(service, "backup_database", fake_backup)
    monkeypatch.setattr(
        service, "restore_test",
        lambda *a, **k: {"ok": True, "reason": "structure_only: 임시 DB 를 못 만들었다"},
    )

    row = service.run_backup(db, settings, created_by=None, now=NOW)

    assert row.status == STATUS_SUCCEEDED, "구조만 본 백업이 verified 로 올라갔다"
    assert row.verified_at is None
    assert "복원 가능 여부는 아직 확인되지 않았습니다" in (row.error_message or "")


def test_a_real_restore_check_does_claim_verified(db, settings, monkeypatch):
    """반대쪽도 못박는다 — 위 시험이 **무엇이든 succeeded 로 만드는 검사**가 아님을 보인다."""
    from app.backups import service
    from app.backups.models import STATUS_VERIFIED

    def fake_backup(database_url, dest_path, *, bin_dir=None, exclude_table_data=()):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text("fake", encoding="utf-8")
        return {"size_bytes": 4, "checksum": "abc"}

    monkeypatch.setattr(service, "backup_database", fake_backup)
    monkeypatch.setattr(service, "restore_test", lambda *a, **k: {"ok": True, "reason": None})

    row = service.run_backup(db, settings, created_by=None, now=NOW)

    assert row.status == STATUS_VERIFIED
    assert row.verified_at == NOW
    assert row.error_message is None
