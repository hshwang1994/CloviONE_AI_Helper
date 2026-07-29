"""0015(부서·직책 FK 이관)이 데이터를 잃지 않는지 실제 alembic으로 확인한다.

문자열 컬럼 → FK 이관은 데이터를 옮기는 마이그레이션이다. '테이블이 생겼다'는 것은
확인이 아니다 — 진짜 확인은 이관 전에 넣은 값이 upgrade → downgrade → upgrade를
지나서도 그대로 있는가다. 여기가 통과해야 "한 곳만 고치면 전원에 반영"이 참이 된다
(FK 없이 문자열로 두면 그 약속은 거짓이다).
"""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.regression

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 프로덕션과 같은 모양: 부서를 가진 사람, 부서+직책을 가진 사람, 같은 부서를 공유하는
# 사람, 아무것도 없는 사람. 같은 부서를 두 명이 쓰는 경우가 있어야 '중복 없이 하나로
# 모이는지'를 볼 수 있다.
SEED = [
    ("u1", "kim@goodmit.co.kr", "김지혜", "ClovirONE팀", "팀장"),
    ("u2", "lee@goodmit.co.kr", "이철수", "ClovirONE팀", "선임"),
    ("u3", "park@goodmit.co.kr", "박영희", "영업팀", None),
    ("u4", "choi@goodmit.co.kr", "최민수", None, None),
]


def _alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"alembic {args} 실패:\n{result.stdout}\n{result.stderr}"
    return result


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Path:
    """0014까지 올린 뒤(=문자열 컬럼 시절) 실제 데이터를 넣는다."""
    db_path = tmp_path / "roundtrip.sqlite3"
    _alembic(db_path, "upgrade", "0014")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        for uid, email, name, dept, title in SEED:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, display_name, department, title, role,"
                    " active, password_hash, must_change_password, failed_login_count,"
                    " created_at, updated_at)"
                    " VALUES (:id, :email, :name, :dept, :title, 'user', 1, 'x', 0, 0,"
                    " '2026-07-16 00:00:00.000000', '2026-07-16 00:00:00.000000')"
                ),
                {"id": uid, "email": email, "name": name, "dept": dept, "title": title},
            )
    engine.dispose()
    return db_path


def _rows(db_path: Path, sql: str) -> list[tuple]:
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            return [tuple(r) for r in conn.execute(text(sql))]
    finally:
        engine.dispose()


# 이관 후 사용자별 (이메일, 부서명, 직책명) — FK를 타고 읽는다.
JOINED = (
    "SELECT u.email, d.name, t.name FROM users u"
    " LEFT JOIN departments d ON d.id = u.department_id"
    " LEFT JOIN job_titles t ON t.id = u.title_id"
    " ORDER BY u.email"
)
# 이관 전/후(=downgrade 후) 문자열 컬럼을 그대로 읽는다.
FLAT = "SELECT email, department, title FROM users ORDER BY email"

EXPECTED = sorted((email, dept, title) for _, email, _, dept, title in SEED)


def test_upgrade_migrates_existing_strings_into_rows(seeded_db):
    _alembic(seeded_db, "upgrade", "head")

    # 기존 값에서 부서가 만들어졌고, 같은 이름은 하나로 모였다.
    depts = sorted(n for (n,) in _rows(seeded_db, "SELECT name FROM departments"))
    assert depts == ["ClovirONE팀", "영업팀"], f"부서가 잘못 만들어졌다: {depts}"
    titles = sorted(n for (n,) in _rows(seeded_db, "SELECT name FROM job_titles"))
    assert titles == ["선임", "팀장"]

    # 그리고 모든 사용자가 이관 전과 같은 부서·직책을 가리킨다.
    assert sorted(_rows(seeded_db, JOINED)) == EXPECTED


def test_new_rows_are_active_by_default(seeded_db):
    _alembic(seeded_db, "upgrade", "head")
    assert all(a == 1 for (a,) in _rows(seeded_db, "SELECT active FROM departments"))


def test_migrated_rows_are_readable_through_the_orm(seeded_db):
    """이관이 만든 행을 앱이 실제로 읽는 방식(ORM)으로 읽어 본다.

    raw SQL로 name만 확인하면 통과하지만 앱은 터지는 구간이 있다: created_at을 SQLite의
    STRFTIME('...%H:%M:%S.%f')로 만들면 '06:44:03.03.754'(초가 두 번)가 되어, SQLAlchemy가
    DateTime으로 파싱하는 순간 ValueError가 난다. 그러면 이관 직후 '부서 관리' 화면과
    CLI가 통째로 500/크래시다. 실제로 그 상태였고 프로덕션 데이터로 CLI를 돌려서야 나왔다.
    """
    from sqlalchemy.orm import Session

    from app.org.models import Department, JobTitle

    _alembic(seeded_db, "upgrade", "head")

    engine = create_engine(f"sqlite:///{seeded_db.as_posix()}")
    try:
        with Session(engine) as session:
            depts = session.query(Department).order_by(Department.name).all()
            assert [d.name for d in depts] == ["ClovirONE팀", "영업팀"]
            for row in depts + session.query(JobTitle).all():
                # 여기서 터지면 이관이 만든 timestamp가 앱이 읽을 수 없는 모양이다.
                assert row.created_at.year == datetime.now(timezone.utc).year
                assert row.active is True
    finally:
        engine.dispose()


def test_downgrade_restores_strings(seeded_db):
    _alembic(seeded_db, "upgrade", "head")
    # 0015의 downgrade를 겨냥한다 — 구체 리비전(0014)으로 내린다. 예전엔 "-1"(한 단계)로
    # 적었는데 그건 0015가 head일 때만 0014를 뜻한다. 이후 마이그레이션(0016 등)이 쌓이면
    # "-1"은 0015에서 멈춰 문자열 컬럼이 아직 없는 지점을 보게 된다. 구체 리비전이 견고하다
    # (덤으로 head→0014 경로가 0016.downgrade까지 실제로 태운다).
    _alembic(seeded_db, "downgrade", "0014")

    assert sorted(_rows(seeded_db, FLAT)) == EXPECTED, "downgrade가 부서·직책을 잃었다"


def test_upgrade_downgrade_upgrade_preserves_data(seeded_db):
    """지시받은 그대로의 왕복 — 한 바퀴 돌고 와도 같은 값이어야 한다."""
    _alembic(seeded_db, "upgrade", "head")
    before = sorted(_rows(seeded_db, JOINED))

    # 0015의 downgrade를 겨냥한다 — 구체 리비전(0014)으로 내린다. 예전엔 "-1"(한 단계)로
    # 적었는데 그건 0015가 head일 때만 0014를 뜻한다. 이후 마이그레이션(0016 등)이 쌓이면
    # "-1"은 0015에서 멈춰 문자열 컬럼이 아직 없는 지점을 보게 된다. 구체 리비전이 견고하다
    # (덤으로 head→0014 경로가 0016.downgrade까지 실제로 태운다).
    _alembic(seeded_db, "downgrade", "0014")
    _alembic(seeded_db, "upgrade", "head")

    after = sorted(_rows(seeded_db, JOINED))
    assert after == before == EXPECTED, f"왕복 후 데이터가 달라졌다:\n{before}\n{after}"


def test_users_keep_identity_across_roundtrip(seeded_db):
    """부서만 보는 것으로는 부족하다 — 행 자체(계정)가 그대로 있어야 한다."""
    _alembic(seeded_db, "upgrade", "head")
    # 0015의 downgrade를 겨냥한다 — 구체 리비전(0014)으로 내린다. 예전엔 "-1"(한 단계)로
    # 적었는데 그건 0015가 head일 때만 0014를 뜻한다. 이후 마이그레이션(0016 등)이 쌓이면
    # "-1"은 0015에서 멈춰 문자열 컬럼이 아직 없는 지점을 보게 된다. 구체 리비전이 견고하다
    # (덤으로 head→0014 경로가 0016.downgrade까지 실제로 태운다).
    _alembic(seeded_db, "downgrade", "0014")
    _alembic(seeded_db, "upgrade", "head")

    ids = sorted(i for (i,) in _rows(seeded_db, "SELECT id FROM users"))
    assert ids == ["u1", "u2", "u3", "u4"]


def test_upgrade_on_empty_db_is_safe(tmp_path):
    """새로 설치하는 서버에는 옮길 문자열이 하나도 없다."""
    db_path = tmp_path / "fresh.sqlite3"
    _alembic(db_path, "upgrade", "head")
    assert _rows(db_path, "SELECT COUNT(*) FROM departments") == [(0,)]


def test_string_columns_are_gone_after_upgrade(seeded_db):
    """자유 입력 컬럼이 남아 있으면 언젠가 그리로 다시 쓰게 되고, 두 개의 진실이 생긴다."""
    _alembic(seeded_db, "upgrade", "head")
    cols = {c[1] for c in _rows(seeded_db, "PRAGMA table_info(users)")}
    assert "department" not in cols
    assert "title" not in cols
    assert "department_id" in cols
    assert "title_id" in cols


def test_sessions_fk_survives_users_table_rebuild(seeded_db):
    """SQLite에서 컬럼을 지우려면 users 테이블을 통째로 다시 만든다(batch). 그때
    users를 참조하는 sessions가 함께 깨지면 로그인 자체가 죽는다."""
    engine = create_engine(f"sqlite:///{seeded_db.as_posix()}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sessions (id, token_hash, user_id, csrf_token, created_at,"
                " last_seen_at, expires_at) VALUES ('s1', 'h', 'u1', 'c',"
                " '2026-07-16 00:00:00.000000', '2026-07-16 00:00:00.000000',"
                " '2026-07-17 00:00:00.000000')"
            )
        )
    engine.dispose()

    _alembic(seeded_db, "upgrade", "head")
    assert _rows(seeded_db, "SELECT user_id FROM sessions") == [("u1",)]
    fks = _rows(seeded_db, "PRAGMA foreign_key_list(sessions)")
    assert any(fk[2] == "users" for fk in fks), f"sessions→users FK가 사라졌다: {fks}"
