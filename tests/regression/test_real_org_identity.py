"""조직 이름과 부서 계층이 **실제 조직** 그대로인지 (P5).

## 왜 고정하는가

0034 가 리브랜딩하면서 제품명과 조직명을 같은 것으로 취급해 조직 이름에 제품 이름
("ClovirAssist")을 써 넣었다. 화면에서 조직 이름이 나오는 자리마다 회사 이름 대신 제품
이름이 찍혔고, 사용자가 그것을 지적했다(P5). 같은 혼동이 다시 일어나기 쉬운 이유는
**둘 다 문자열이고 둘 다 브랜딩처럼 보이기 때문**이다. 그래서 둘을 함께 못박는다:

  * 조직 이름 = 굿모닝아이텍 (회사)
  * 제품 이름 = ClovirAssist (이 포털)

부서 계층도 같이 본다. 실제는 `브로드컴사업본부 > ClovirONE팀` 이고, 0038 이 그 구조를
만든다. 상위 부서 없이 팀만 있으면 조직도 화면이 팀을 최상위로 그린다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.regression


def test_default_org_name_is_the_company_not_the_product():
    """시드 상수가 회사 이름이어야 한다 — 아니면 새 환경에서 되살아난다."""
    from app.org.constants import DEFAULT_ORG_NAME

    assert DEFAULT_ORG_NAME == "굿모닝아이텍", (
        "조직 이름 자리에 제품 이름이 들어갔다. 제품명은 app_settings 의 "
        "ui_branding.product_name 이고 별개다."
    )
    assert "Clovir" not in DEFAULT_ORG_NAME


def test_migration_0038_renames_org_and_builds_the_tree(tmp_path):
    """0038 을 실제로 돌려 조직명과 부서 계층을 확인한다.

    운영과 같은 모양(조직 1개 + `ClovirONE팀` 하나, 상위 없음)에서 시작한다.
    """
    import os
    import sqlite3
    import subprocess
    import sys
    import uuid

    db = tmp_path / "org.sqlite3"
    # 환경을 통째로 갈아끼우면 PATH·SYSTEMROOT 가 없어 파이썬이 뜨지도 못한다 —
    # 그러면 테스트가 조용히 skip 되고 아무것도 증명하지 않는다(처음에 그랬다).
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db.as_posix()}"}

    def alembic(target):
        return subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", target],
            env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(REPO),
        )

    first = alembic("0037")
    assert db.exists(), f"alembic 이 DB 를 못 만들었다: {first.stdout} {first.stderr}"

    con = sqlite3.connect(db)
    con.execute("UPDATE organizations SET name = 'ClovirAssist'")
    con.execute("DELETE FROM departments")
    con.execute(
        "INSERT INTO departments (id, name, active, org_id, created_at) "
        "VALUES (?, 'ClovirONE팀', 1, "
        "'00000000-0000-0000-0000-00000000org1', '2026-08-01')",
        (str(uuid.uuid4()),),
    )
    con.commit()
    con.close()

    second = alembic("head")
    assert second.returncode == 0, f"0038 적용 실패: {second.stdout} {second.stderr}"

    con = sqlite3.connect(db)
    orgs = [r[0] for r in con.execute("SELECT name FROM organizations")]
    rows = list(con.execute("SELECT id, name, parent_id FROM departments"))
    con.close()

    assert orgs == ["굿모닝아이텍"], f"조직 이름이 안 바뀌었다: {orgs}"
    by_id = {r[0]: r[1] for r in rows}
    tree = {name: by_id.get(parent) for _id, name, parent in rows}
    assert tree.get("ClovirONE팀") == "브로드컴사업본부", (
        f"부서 계층이 실제 구조가 아니다: {tree}"
    )
    assert tree.get("브로드컴사업본부") is None, "상위 부서가 최상위여야 한다"
