"""큰 조직 시드 — 조직 관리 작업 공간을 대량 데이터로 보기 위한 **개발 DB 전용** 도구 (O1 · D-533, 계획 8.3).

조직 관리 화면의 약속(문서가 구성원 수와 상관없이 굴러가지 않는다, 트리 · 구성원 판이 따로 굴러간다, 검색이 접힌 부모를 편다,
구성원을 50명씩 판 안에서 더 받는다)은 부서 몇 개 · 사람 몇 명으로는 드러나지 않는다. 그래서 5단계 · 부서 200개 · 구성원 150명
(동명이인 셋, 비활성 · 보관 계정, 아주 긴 이름과 이메일 포함)을 한 번에 심는다.

## 어디에 심는가

**개발 · 시험용 데이터베이스에만** 심는다. 다음 중 하나라도 어기면 아무것도 쓰지 않고 멈춘다:

  * `APP_ENV` 가 `production` 이다
  * 데이터베이스 주소의 호스트가 이 컴퓨터(127.0.0.1 · localhost · ::1)가 아니다
  * `--yes` 가 없다(지울 수 없는 행을 남기므로 기본값은 「안 함」이다 — 로컬 QA 하네스는 임시 DB 에 `--yes` 로 부른다)

## 쓰는 법

    python scripts/dev/seed_large_org.py --database-url postgresql://…@127.0.0.1:55433/clovir_dev --yes
    python -m scripts.ui_qa.local_capture --label org-e2e --harness workspace_e2e --target org   # 임시 DB 에 저절로 심는다

돌려주는 값(하네스가 쓴다): 큰 가지의 부서 id(구성원 120명 이상), 빈 말단 부서 id, 가장 깊은 부서의 이름.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
PREFIX = "대규모"
DEPARTMENTS = 200
MAX_DEPTH = 5
MEMBERS = 150
#: 같은 이름 셋 — 이름으로는 누구인지 모르고 이메일 열이 가른다(O1 「동명이인」).
DUPLICATE_NAME = "김민준"
LONG_NAME = "아주긴이름을가진사람의표시이름이표의이름칸을넘어서는지확인하는견본"
LONG_EMAIL_LOCAL = "very.long.address.for.overflow.checks.in.member.tables"


class Refused(RuntimeError):
    """개발 DB 가 아니어서 심지 않았다."""


def ensure_dev_database(database_url: str, *, app_env: str | None = None) -> None:
    env = (app_env if app_env is not None else os.environ.get("APP_ENV", "")).strip().lower()
    if env == "production":
        raise Refused("APP_ENV=production 에는 시드를 심지 않습니다.")
    host = (urlparse(database_url.replace("postgresql+psycopg", "postgresql")).hostname or "").lower()
    if host not in LOOPBACK:
        raise Refused(f"이 컴퓨터의 데이터베이스가 아닙니다({host or '호스트 없음'}). 개발 DB 에만 심습니다.")


def _tree_plan(total: int = DEPARTMENTS, depth: int = MAX_DEPTH) -> list[tuple[str, int, int | None]]:
    """(이름, 깊이, 부모 번호) 목록 — 너비 우선으로 맨 위 넷, 그 아래 셋씩 가지를 낸다. 결정적이라 다시 심어도 같은 모양이다.

    4 + 12 + 36 + 108 = 160 이고 다섯째 단계가 나머지 40 을 받는다 — 깊이 5 안에서 200 이 찬다."""
    plan: list[tuple[str, int, int | None]] = []
    frontier: list[int | None] = [None]
    for level in range(1, depth + 1):
        nxt: list[int] = []
        for parent in frontier:
            for _ in range(4 if parent is None else 3):
                if len(plan) >= total:
                    break
                plan.append((f"{PREFIX} {level}단계 {len(plan) + 1:03d}팀", level, parent))
                nxt.append(len(plan) - 1)
        frontier = nxt
    if len(plan) != total:
        raise ValueError(f"깊이 {depth} 안에 부서 {total}개를 세우지 못했습니다({len(plan)}개).")
    return plan


def seed(database_url: str, *, app_env: str | None = None) -> dict:
    """심고 하네스가 쓸 id 를 돌려준다. 같은 DB 에 다시 부르면 이미 있는 것을 찾아 그대로 돌려준다(멱등)."""
    ensure_dev_database(database_url, app_env=app_env)

    from datetime import datetime

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.core.db import normalize_database_url
    from app.core.security import hash_password
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.users.models import User

    engine = create_engine(normalize_database_url(database_url), future=True)
    with Session(engine) as db:
        existing = db.execute(select(Department).where(Department.name.like(f"{PREFIX} %"))).scalars().all()
        if not existing:
            plan = _tree_plan()
            rows: list[Department] = []
            for name, _level, parent in plan:
                row = Department(name=name, org_id=DEFAULT_ORG_ID, parent_id=rows[parent].id if parent is not None else None)
                db.add(row)
                db.flush()
                rows.append(row)
            # 미사용 부서 몇 개 — 「사용 중만」 토글이 무엇을 숨기는지 보이게.
            for row in rows[150:160]:
                row.active = False

            # 큰 가지: 첫 1단계 부서와 그 자손. 구성원의 대부분(120명)을 여기에 둔다.
            big = rows[0]
            branch = [r for r in rows if _is_under(rows, r, big)]
            pw = hash_password("Seed-Large-Org-1!")
            people: list[User] = []
            for i in range(MEMBERS):
                if i < 120:
                    dept = branch[i % len(branch)]
                else:
                    dept = rows[4 + (i % 40)]
                name = f"구성원{i + 1:03d}"
                email = f"member{i + 1:03d}@example.com"
                if i in (3, 41, 87):
                    name = DUPLICATE_NAME
                if i == 7:
                    name = LONG_NAME
                if i == 9:
                    email = f"{LONG_EMAIL_LOCAL}@example.com"
                people.append(User(
                    email=email, display_name=name, role="admin" if i % 37 == 0 else "user",
                    active=not (i % 29 == 5), password_hash=pw, must_change_password=False,
                    department_id=dept.id, membership_kind="department", org_id=DEFAULT_ORG_ID,
                    archived_at=datetime(2026, 9, 1) if i % 53 == 11 else None,
                ))
            db.add_all(people)
            db.commit()
            existing = db.execute(select(Department).where(Department.name.like(f"{PREFIX} %"))).scalars().all()

        by_name = {d.name: d for d in existing}
        ordered = sorted(existing, key=lambda d: d.name)
        big = by_name.get(f"{PREFIX} 1단계 001팀") or ordered[0]
        children = {d.parent_id for d in existing if d.parent_id}
        occupied = set(db.execute(
            select(User.department_id).where(User.department_id.in_([d.id for d in existing]))
        ).scalars())
        empty_leaf = next(d for d in ordered if d.id not in children and d.id not in occupied and d.active)
        deepest = max(existing, key=lambda d: _depth(by_id={x.id: x for x in existing}, row=d))
        return {"big": big.id, "big_name": big.name, "empty": empty_leaf.id, "empty_name": empty_leaf.name,
                "deepest_name": deepest.name, "departments": len(existing)}


def _is_under(rows, row, top) -> bool:
    by_id = {r.id: r for r in rows}
    cur = row
    seen = set()
    while cur is not None and cur.id not in seen:
        if cur.id == top.id:
            return True
        seen.add(cur.id)
        cur = by_id.get(cur.parent_id)
    return False


def _depth(*, by_id, row) -> int:
    n, cur, seen = 0, row, set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        n += 1
        cur = by_id.get(cur.parent_id)
    return n


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="큰 조직 시드(개발 DB 전용)")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    ap.add_argument("--yes", action="store_true", help="실제로 심는다. 없으면 무엇을 심을지만 말하고 끝낸다.")
    args = ap.parse_args()
    if not args.database_url:
        print("데이터베이스 주소가 없습니다(--database-url 또는 DATABASE_URL).", file=sys.stderr)
        return 2
    try:
        ensure_dev_database(args.database_url)
    except Refused as exc:
        print(f"[REFUSED] {exc}", file=sys.stderr)
        return 3
    if not args.yes:
        print(f"부서 {DEPARTMENTS}개(최대 {MAX_DEPTH}단계)와 구성원 {MEMBERS}명을 심습니다. 실제로 심으려면 --yes 를 붙이세요.")
        return 0
    out = seed(args.database_url)
    print("SEED_LARGE_ORG_OK", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
