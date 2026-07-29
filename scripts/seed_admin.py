"""Create the initial system_admin account (spec §10.5).

Usage:
    python scripts/seed_admin.py --email hshwang@goodmit.co.kr --name "황형섭"

Idempotent: exits 0 without changes if the account already exists.
The generated temporary password is printed ONCE to stdout and must not be
captured into persistent logs (deploy script 45-create-admin.sh handles this).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.core.db import make_engine, make_session_factory  # noqa: E402
from app.core.security import generate_temp_password  # noqa: E402
from app.users.service import create_user, get_user_by_email  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create initial system_admin")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)

    with factory() as db:
        existing = get_user_by_email(db, args.email)
        if existing is not None:
            print(f"이미 존재하는 계정입니다: {existing.email} (role={existing.role})")
            return 0

        temp_password = generate_temp_password()
        user = create_user(
            db,
            email=args.email,
            display_name=args.name,
            password=temp_password,
            settings=settings,
            role="system_admin",
            active=True,
            must_change_password=True,
            created_by=None,
        )
        db.commit()

        print("--- TEMP PASSWORD (한 번만 표시됩니다 — 로그에 저장 금지) ---")
        print(f"email: {user.email}")
        print(f"temp_password: {temp_password}")
        print("--- 첫 로그인 시 비밀번호 변경이 강제됩니다 ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
