"""0024(org_scope)가 데이터를 잃지 않고, 복합 유니크가 **실제로 거부하는지** 확인한다.

이 마이그레이션에는 조용히 깨지는 함정이 두 개 있다. 둘 다 "테이블이 생겼다"로는 절대
잡히지 않는다.

1. **org_id 를 NULL 로 두면 `(org_id, name)` 복합 유니크가 무효가 된다.**
   SQLite 는 UNIQUE 인덱스에서 NULL 을 서로 다른 값으로 본다. 인덱스는 멀쩡히 존재하고
   `PRAGMA index_list` 에도 unique 로 뜨는데 중복이 그냥 들어간다. 그래서 여기서는
   인덱스 존재를 보는 대신 **실제로 INSERT 를 쳐서 IntegrityError 가 나는지**를 본다.
   (그리고 그 검사가 헛돌지 않는다는 것을 보이기 위해, org_id 를 NULL 로 넣으면
   같은 이름이 **통과**한다는 것도 함께 못박는다 — 이것이 바로 백필하지 않았을 때의 상태다.)

2. **SQLite batch_alter_table 의 다운그레이드는 테이블을 재생성한다.**
   컬럼 순서·server_default·인덱스·다른 표의 FK 가 조용히 달라질 수 있다. 그래서
   upgrade→downgrade→upgrade 왕복 뒤에 데이터와 FK 가 그대로인지 확인한다.
   (스키마 전체 비교는 `scripts/migration_rehearsal.sh` 가 별도로 한다.)
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ORG_ID = "00000000-0000-0000-0000-00000000org1"
TS = "2026-08-01 00:00:00.000000"

# 0023 시절(=org_id 컬럼이 없던 때)에 이미 들어 있던 것처럼 심는다. 부서 두 개, 직책 하나,
# 사용자 셋(부서 있는 둘 + 부서 없는 하나) — 백필과 스코프 양쪽에 필요한 최소 구성이다.
SEED_DEPARTMENTS = (("d-dev", "개발팀"), ("d-sales", "영업팀"))
SEED_USERS = (
    ("u-kim", "kim@goodmit.co.kr", "김지혜", "d-dev"),
    ("u-lee", "lee@goodmit.co.kr", "이철수", "d-dev"),
    ("u-park", "park@goodmit.co.kr", "박영희", None),
)


def _alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, f"alembic {args} 실패:\n{result.stdout}\n{result.stderr}"
    return result


def _exec(db_path: Path, sql: str, params: dict | None = None):
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.begin() as conn:
            return conn.execute(text(sql), params or {})
    finally:
        engine.dispose()


def _rows(db_path: Path, sql: str) -> list[tuple]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql))]
    finally:
        engine.dispose()


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Path:
    """0023 까지 올린 뒤(= org_id 컬럼이 없던 시절) 실제 데이터를 넣는다."""
    db_path = tmp_path / "org_scope.sqlite3"
    _alembic(db_path, "upgrade", "0023")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        for dept_id, name in SEED_DEPARTMENTS:
            conn.execute(
                text(
                    "INSERT INTO departments (id, name, active, created_at)"
                    " VALUES (:id, :name, 1, :ts)"
                ),
                {"id": dept_id, "name": name, "ts": TS},
            )
        conn.execute(
            text(
                "INSERT INTO job_titles (id, name, active, created_at)"
                " VALUES ('t-lead', '팀장', 1, :ts)"
            ),
            {"ts": TS},
        )
        for user_id, email, name, dept in SEED_USERS:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, display_name, role, active,"
                    " password_hash, must_change_password, failed_login_count,"
                    " created_at, updated_at, department_id, title_id)"
                    " VALUES (:id, :email, :name, 'user', 1, 'x', 0, 0, :ts, :ts,"
                    " :dept, 't-lead')"
                ),
                {"id": user_id, "email": email, "name": name, "dept": dept, "ts": TS},
            )
    engine.dispose()
    return db_path


# ── 1) 백필 ───────────────────────────────────────────────────────────────────


def test_org_id_is_backfilled_with_a_real_value_not_null(seeded_db):
    """NULL 이 아니라 DEFAULT_ORG_ID 실값이어야 한다 — 이것이 이 마이그레이션의 핵심."""
    _alembic(seeded_db, "upgrade", "0024")

    for table in (
        "departments", "job_titles", "users",
        "board_posts", "document_cache", "chat_rooms", "game_rooms", "trash_items",
    ):
        nulls = _rows(seeded_db, f"SELECT COUNT(*) FROM {table} WHERE org_id IS NULL")[0][0]
        assert nulls == 0, f"{table}.org_id 에 NULL 이 남아 있다 — 복합 유니크와 스코프가 무효가 된다"

    values = {v for (v,) in _rows(seeded_db, "SELECT DISTINCT org_id FROM departments")}
    assert values == {DEFAULT_ORG_ID}


def test_admin_scope_defaults_to_global_so_existing_admins_keep_working(seeded_db):
    """좁은 기본값을 깔면 이 마이그레이션 하나로 운영 중인 관리자 화면이 빈 목록이 된다."""
    _alembic(seeded_db, "upgrade", "0024")
    scopes = {s for (s,) in _rows(seeded_db, "SELECT DISTINCT admin_scope FROM users")}
    assert scopes == {"global"}


# ── 2) 복합 유니크가 실제로 거부하는가 ────────────────────────────────────────


def test_duplicate_department_name_in_same_org_is_actually_rejected(seeded_db):
    """인덱스가 '있다'가 아니라 중복 INSERT 가 '거부된다'를 본다."""
    _alembic(seeded_db, "upgrade", "0024")

    with pytest.raises(sa.exc.IntegrityError):
        _exec(
            seeded_db,
            "INSERT INTO departments (id, name, active, created_at, org_id)"
            " VALUES ('d-dup', '개발팀', 1, :ts, :org)",
            {"ts": TS, "org": DEFAULT_ORG_ID},
        )


def test_the_check_above_is_not_vacuous_null_org_id_slips_through(seeded_db):
    """위 검사가 헛돌지 않는다는 증명.

    같은 이름을 **org_id=NULL 로** 넣으면 통과한다 — SQLite 가 UNIQUE 에서 NULL 을 서로
    다르게 보기 때문이다. 즉 백필하지 않았다면 위 테스트가 잡아내는 그 중복이 그냥
    들어갔을 것이다. 이 테스트가 통과한다는 것은 위 테스트가 **백필 덕분에** 통과했다는 뜻이다.
    """
    _alembic(seeded_db, "upgrade", "0024")

    _exec(
        seeded_db,
        "INSERT INTO departments (id, name, active, created_at, org_id)"
        " VALUES ('d-null1', '중복확인팀', 1, :ts, NULL)",
        {"ts": TS},
    )
    _exec(  # 같은 이름, 둘 다 NULL — 거부되지 않는다
        seeded_db,
        "INSERT INTO departments (id, name, active, created_at, org_id)"
        " VALUES ('d-null2', '중복확인팀', 1, :ts, NULL)",
        {"ts": TS},
    )
    dupes = _rows(seeded_db, "SELECT COUNT(*) FROM departments WHERE name = '중복확인팀'")
    assert dupes[0][0] == 2, "NULL org_id 두 행이 막혔다면 이 증명은 더 이상 유효하지 않다"


def test_same_department_name_in_a_different_org_is_allowed(seeded_db):
    """조직별 유니크의 반대 방향 — 다른 조직이면 같은 이름을 쓸 수 있어야 한다."""
    _alembic(seeded_db, "upgrade", "0024")
    _exec(
        seeded_db,
        "INSERT INTO organizations (id, slug, name, status, created_at, updated_at)"
        " VALUES ('org-two', 'two', '두번째', 'active', :ts, :ts)",
        {"ts": TS},
    )
    _exec(
        seeded_db,
        "INSERT INTO departments (id, name, active, created_at, org_id)"
        " VALUES ('d-other', '개발팀', 1, :ts, 'org-two')",
        {"ts": TS},
    )
    names = _rows(seeded_db, "SELECT COUNT(*) FROM departments WHERE name = '개발팀'")
    assert names[0][0] == 2


# ── 3) 부서 트리 ──────────────────────────────────────────────────────────────


def test_department_parent_id_makes_a_tree(seeded_db):
    _alembic(seeded_db, "upgrade", "0024")
    _exec(
        seeded_db,
        "INSERT INTO departments (id, name, active, created_at, org_id, parent_id)"
        " VALUES ('d-fe', '프런트팀', 1, :ts, :org, 'd-dev')",
        {"ts": TS, "org": DEFAULT_ORG_ID},
    )
    kids = _rows(seeded_db, "SELECT id FROM departments WHERE parent_id = 'd-dev'")
    assert kids == [("d-fe",)]


def test_migrated_rows_are_readable_through_the_orm(seeded_db):
    """raw SQL 로 name 만 보면 통과하지만 앱은 죽는 구간이 있다 — created_at 을 SQLite
    STRFTIME 으로 만들면 '초가 두 번' 들어가 ORM 파싱이 터진다(CLAUDE.md §8).
    0024 는 타임스탬프를 새로 쓰지 않지만, 배치 재생성이 기존 값을 상하게 하지 않았는지
    앱이 실제로 읽는 방식으로 확인한다.

    ⚠️ **0024 에서 멈추지 않고 head 까지 올린 뒤 읽는다.** ORM 모델은 언제나 최신 스키마를
    말하므로, 중간 리비전에 멈춘 DB 를 모델로 읽으면 그 뒤에 컬럼을 하나라도 추가한 순간
    이 파일이 "0024 가 깨졌다" 며 빨개진다 — 실제로는 0024 와 아무 상관이 없다(0060 이
    `users.membership_kind` 를 추가하면서 실제로 그렇게 됐다).

    0024 만 돌린 상태의 무결성은 raw SQL 로 보는 위 시험들과
    `test_upgrade_downgrade_upgrade_preserves_every_row` 가 지킨다. 여기서 보려는 것은
    "0024 가 다시 쓴 행을 **앱이** 읽을 수 있는가" 이고, 앱은 head 스키마에서 돈다.
    """
    from sqlalchemy.orm import Session

    from app.org.models import Department
    from app.users.models import User

    _alembic(seeded_db, "upgrade", "0024")
    _alembic(seeded_db, "upgrade", "head")
    engine = create_engine(f"sqlite:///{seeded_db.as_posix()}")
    try:
        with Session(engine) as session:
            depts = session.query(Department).order_by(Department.name).all()
            assert [d.name for d in depts] == ["개발팀", "영업팀"]
            for d in depts:
                assert d.created_at.year == 2026
                assert d.org_id == DEFAULT_ORG_ID
                assert d.parent_id is None
            user = session.query(User).filter(User.id == "u-kim").one()
            assert user.department == "개발팀"  # FK relationship 이 살아 있다
            assert user.admin_scope == "global"
            assert user.org_id == DEFAULT_ORG_ID
    finally:
        engine.dispose()


# ── 4) 왕복 ───────────────────────────────────────────────────────────────────


def test_downgrade_drops_the_new_columns_and_restores_the_global_unique(seeded_db):
    _alembic(seeded_db, "upgrade", "0024")
    _alembic(seeded_db, "downgrade", "0023")

    cols = {c[1] for c in _rows(seeded_db, "PRAGMA table_info(departments)")}
    assert "org_id" not in cols and "parent_id" not in cols
    user_cols = {c[1] for c in _rows(seeded_db, "PRAGMA table_info(users)")}
    for gone in ("org_id", "admin_scope", "scope_org_id", "scope_dept_id"):
        assert gone not in user_cols, f"downgrade 가 {gone} 을 남겼다"

    idx = dict(
        (r[1], r[2]) for r in _rows(seeded_db, "PRAGMA index_list(departments)")
    )
    assert idx.get("ix_departments_name") == 1, "0023 의 전역 유니크가 돌아오지 않았다"


def test_upgrade_downgrade_upgrade_preserves_every_row(seeded_db):
    """지시받은 그대로의 왕복 — 한 바퀴 돌고 와도 같은 값이어야 한다."""
    _alembic(seeded_db, "upgrade", "0024")
    joined = (
        "SELECT u.email, d.name, t.name FROM users u"
        " LEFT JOIN departments d ON d.id = u.department_id"
        " LEFT JOIN job_titles t ON t.id = u.title_id"
        " ORDER BY u.email"
    )
    before = sorted(_rows(seeded_db, joined))

    _alembic(seeded_db, "downgrade", "0023")
    _alembic(seeded_db, "upgrade", "0024")

    assert sorted(_rows(seeded_db, joined)) == before
    assert sorted(i for (i,) in _rows(seeded_db, "SELECT id FROM users")) == [
        "u-kim", "u-lee", "u-park",
    ]
    # 백필이 왕복 뒤에도 유효해야 한다 — 안 그러면 두 번째 upgrade 후 복합 유니크가 죽는다.
    nulls = _rows(seeded_db, "SELECT COUNT(*) FROM departments WHERE org_id IS NULL")[0][0]
    assert nulls == 0


def test_foreign_keys_survive_the_table_rebuild(seeded_db):
    """batch 는 테이블을 통째로 다시 만든다. users→departments FK 가 그때 사라지면
    부서 배정이 조용히 끊긴다(0015 가 sessions→users 로 같은 함정을 밟았다)."""
    _alembic(seeded_db, "upgrade", "0024")
    _alembic(seeded_db, "downgrade", "0023")
    _alembic(seeded_db, "upgrade", "0024")

    fks = _rows(seeded_db, "PRAGMA foreign_key_list(users)")
    targets = {(fk[2], fk[3]) for fk in fks}
    assert ("departments", "department_id") in targets
    assert ("job_titles", "title_id") in targets
    assert ("departments", "scope_dept_id") in targets
    assert ("organizations", "org_id") in targets

    dept_fks = {(fk[2], fk[3]) for fk in _rows(seeded_db, "PRAGMA foreign_key_list(departments)")}
    assert ("departments", "parent_id") in dept_fks, "자기참조 FK 가 사라졌다"


def test_upgrade_on_an_empty_database_is_safe(tmp_path):
    """새로 설치하는 서버에는 백필할 행이 하나도 없다."""
    db_path = tmp_path / "fresh.sqlite3"
    _alembic(db_path, "upgrade", "head")
    assert _rows(db_path, "SELECT COUNT(*) FROM departments") == [(0,)]
    assert _rows(db_path, "SELECT COUNT(*) FROM organizations") == [(1,)]
