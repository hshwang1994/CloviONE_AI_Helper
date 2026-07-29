"""clovirone-user CLI (spec §29).

Uses the same service layer as the web admin API so behavior never diverges.
Passwords are never accepted as command-line arguments — stdin/getpass only.

Run:  python -m app.cli.user_cli <command> [options]
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.audit import record_audit
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.core.errors import AppError
from app.core.security import generate_temp_password
from app.core.sessions import SessionService
from app.users.models import ALL_ROLES, User
from app.users.service import (
    admin_reset_password,
    archive_user,
    create_user,
    get_user_by_email,
    set_user_active,
    unarchive_user,
    unlock_user,
    update_user,
    user_snapshot,
)


def _require_user(db: Session, email: str) -> User:
    user = get_user_by_email(db, email)
    if user is None:
        raise AppError(f"사용자를 찾을 수 없습니다: {email}")
    return user


def _read_password_stdin(prompt: str) -> str:
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    return sys.stdin.readline().rstrip("\r\n")


def _print_temp_password(email: str, password: str) -> None:
    print("--- TEMP PASSWORD (한 번만 표시됩니다 — 로그 저장 금지) ---")
    print(f"email: {email}")
    print(f"temp_password: {password}")
    print("--- 첫 로그인 시 비밀번호 변경이 강제됩니다 ---")


def _format_user_line(user: User) -> str:
    lock = "locked" if user.locked_until else "-"
    last = user.last_login_at.isoformat() if user.last_login_at else "-"
    # 보관은 활성/비활성과 다른 축이다 — 둘을 한 칸에 뭉치면 '보관된 활성 계정'이
    # 그냥 활성으로 보여 목록에서 왜 안 보이는지 알 수 없게 된다.
    state = "archived" if user.archived_at else ("active" if user.active else "disabled")
    return (
        f"{user.email:<40} {user.display_name:<12} {user.role:<13} "
        f"{state:<9} {lock:<7} last_login={last}"
    )


def cmd_add(db: Session, session_service: SessionService, settings: Settings, args) -> int:
    if args.password_stdin:
        password = _read_password_stdin("초기 비밀번호: ")
        generated = False
    else:
        password = generate_temp_password()
        generated = True
    # 사람은 uuid가 아니라 이름을 친다. 없는 이름은 조용히 만들어 주지 않고 등록된
    # 이름을 알려 주며 거절한다 — 자동 생성하면 오타가 새 부서가 되던 시절로 돌아간다.
    from app.org.models import Department, JobTitle
    from app.org.service import resolve_by_name_or_error

    user = create_user(
        db,
        email=args.email,
        display_name=args.name,
        password=password,
        settings=settings,
        role=args.role,
        active=not args.inactive,
        must_change_password=True,
        department_id=resolve_by_name_or_error(db, Department, args.department),
        title_id=resolve_by_name_or_error(db, JobTitle, args.title),
    )
    record_audit(
        db, actor_id=None, action="cli.user.create", object_type="user",
        object_id=user.id, after=user_snapshot(user),
    )
    db.commit()
    print(f"생성됨: {user.email} (role={user.role})")
    if generated:
        _print_temp_password(user.email, password)
    return 0


def cmd_list(db: Session, session_service, settings, args) -> int:
    # 웹 목록과 같은 규칙: 보관된 계정은 기본으로 감추고 --archived로만 본다.
    # 두 화면이 다른 명부를 보여 주면 어느 쪽이 사실인지 알 수 없다.
    archived_only = getattr(args, "archived", False)
    stmt = select(User).where(
        User.archived_at.is_not(None) if archived_only else User.archived_at.is_(None)
    )
    rows = db.execute(stmt.order_by(User.email)).scalars().all()
    for user in rows:
        print(_format_user_line(user))
    print(f"총 {len(rows)}{'개 (보관됨)' if archived_only else '명'}")
    if not archived_only:
        hidden = db.execute(
            select(func.count()).select_from(User).where(User.archived_at.is_not(None))
        ).scalar_one()
        if hidden:
            print(f"(보관된 계정 {hidden}개는 숨겨져 있습니다 — 보려면: list --archived)")
    return 0


def cmd_show(db: Session, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    for key, value in user_snapshot(user).items():
        print(f"{key}: {value}")
    print(f"id: {user.id}")
    print(f"locked_until: {user.locked_until}")
    print(f"last_login_at: {user.last_login_at}")
    return 0


def cmd_enable(db, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    set_user_active(db, user, True, session_service=session_service, actor_role='system_admin')
    record_audit(db, actor_id=None, action="cli.user.enable", object_type="user", object_id=user.id)
    db.commit()
    print(f"활성화됨: {user.email}")
    return 0


def cmd_disable(db, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    set_user_active(db, user, False, session_service=session_service, actor_role='system_admin')
    record_audit(db, actor_id=None, action="cli.user.disable", object_type="user", object_id=user.id)
    db.commit()
    print(f"비활성화됨: {user.email} (세션 전체 폐기)")
    return 0


def cmd_archive(db, session_service, settings, args) -> int:
    """보관 — 삭제가 아니다. 웹 API와 같은 service를 쓰므로 안전장치(권한 경계,
    마지막 system_admin 보호)가 그대로 걸린다(§29)."""
    user = _require_user(db, args.email)
    archive_user(
        db, user, session_service=session_service, actor_role="system_admin", actor_id=None
    )
    record_audit(
        db, actor_id=None, action="cli.user.archive", object_type="user",
        object_id=user.id, after=user_snapshot(user),
    )
    db.commit()
    print(f"보관됨: {user.email} (목록·검색·로그인에서 제외, 세션 전체 폐기)")
    print("되돌리려면: unarchive --email " + user.email)
    return 0


def cmd_unarchive(db, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    unarchive_user(db, user, actor_role="system_admin")
    record_audit(
        db, actor_id=None, action="cli.user.unarchive", object_type="user",
        object_id=user.id, after=user_snapshot(user),
    )
    db.commit()
    state = "활성" if user.active else "비활성"
    print(f"복구됨: {user.email} (보관 전 상태 그대로 — {state})")
    return 0


def cmd_passwd(db, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    provided = None if args.temp else _read_password_stdin("새 비밀번호: ")
    password = admin_reset_password(
        db, user, session_service=session_service, new_password=provided,
        actor_role="system_admin",
    )
    record_audit(db, actor_id=None, action="cli.user.reset_password", object_type="user", object_id=user.id)
    db.commit()
    print(f"비밀번호 재설정됨: {user.email} (세션 전체 폐기, 첫 로그인 변경 강제)")
    if provided is None:
        _print_temp_password(user.email, password)
    return 0


def cmd_unlock(db, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    unlock_user(db, user, actor_role='system_admin')
    record_audit(db, actor_id=None, action="cli.user.unlock", object_type="user", object_id=user.id)
    db.commit()
    print(f"잠금 해제됨: {user.email}")
    return 0


def cmd_sessions(db, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    rows = (
        db.execute(
            select(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.last_seen_at.desc())
        )
        .scalars()
        .all()
    )
    for s in rows:
        print(
            f"{s.id}  created={s.created_at.isoformat()}  "
            f"last_seen={s.last_seen_at.isoformat()}  ip={s.client_ip or '-'}"
        )
    print(f"활성 세션 {len(rows)}개")
    return 0


def cmd_revoke_sessions(db, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    count = session_service.revoke_all_for_user(db, user.id)
    record_audit(
        db, actor_id=None, action="cli.user.revoke_sessions", object_type="user",
        object_id=user.id, after={"revoked_count": count},
    )
    db.commit()
    print(f"세션 {count}개 폐기됨: {user.email}")
    return 0


def cmd_set_role(db, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    update_user(db, user, session_service=session_service, role=args.role, actor_role='system_admin')
    record_audit(
        db, actor_id=None, action="cli.user.set_role", object_type="user",
        object_id=user.id, after={"role": args.role},
    )
    db.commit()
    print(f"역할 변경됨: {user.email} → {args.role}")
    return 0


def _org_model(kind: str):
    from app.org.models import Department, JobTitle

    return Department if kind == "department" else JobTitle


def cmd_org_add(db, session_service, settings, args) -> int:
    """부서/직책 추가 — 웹 API와 같은 service를 쓴다(§29).

    CLI로 사용자를 만들 때 --department는 '등록된 이름'만 받는다. 여기서 명부를 만들
    수 없으면 CLI만으로는 부서를 가진 계정을 만들 방법이 아예 없어진다.
    """
    from app.org.service import create_item, label_for

    model = _org_model(args.kind)
    row = create_item(db, model, name=args.name)
    record_audit(
        db, actor_id=None, action=f"cli.{args.kind}.create", object_type=args.kind,
        object_id=row.id, after={"name": row.name},
    )
    db.commit()
    print(f"{label_for(model)} 추가됨: {row.name}")
    return 0


def cmd_org_list(db, session_service, settings, args) -> int:
    from app.org.service import label_for, list_items, usage_count

    model = _org_model(args.kind)
    rows = list_items(db, model)
    for row in rows:
        state = "active" if row.active else "inactive"
        print(f"{row.name:<24} {state:<9} 사용자 {usage_count(db, model, row.id)}명")
    print(f"총 {len(rows)}개 {label_for(model)}")
    return 0


def cmd_verify_notion(db, session_service, settings, args) -> int:
    user = _require_user(db, args.email)
    from app.core.allowlist import AllowlistRegistry
    from app.core.http_client import OutboundClient
    from app.core.secret_refs import FileSecretReferenceProvider
    from app.notion_mapping.service import verify_mapping

    outbound = OutboundClient(
        AllowlistRegistry(settings.config_dir),
        FileSecretReferenceProvider(settings.secrets_dir),
    )
    try:
        row = verify_mapping(db, user, outbound=outbound, now=SystemClock().now())
        db.commit()
    finally:
        outbound.close()
    print(f"Notion 매핑: {user.email} → {row.status}")
    if row.error_message:
        print(f"  사유: {row.error_message}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clovirone-user", description="ClovirONE Web Assistant 사용자 관리 CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="사용자 생성 (기본: 임시 비밀번호 자동 생성)")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--role", default="user", choices=sorted(ALL_ROLES))
    p.add_argument("--department", help="등록된 부서 이름 (org list-departments 참고)")
    p.add_argument("--title", help="등록된 직책 이름 (org list-titles 참고)")
    p.add_argument("--inactive", action="store_true")
    p.add_argument("--password-stdin", action="store_true", help="비밀번호를 stdin에서 읽음")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="사용자 목록 (기본: 보관된 계정 제외)")
    p.add_argument("--archived", action="store_true", help="보관된 계정만 표시")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="사용자 상세")
    p.add_argument("--email", required=True)
    p.set_defaults(func=cmd_show)

    for name, func, help_text in [
        ("enable", cmd_enable, "계정 활성화"),
        ("disable", cmd_disable, "계정 비활성화 (세션 폐기)"),
        ("archive", cmd_archive, "계정 보관 (삭제 아님 — 목록·로그인에서 제외, 되돌릴 수 있음)"),
        ("unarchive", cmd_unarchive, "보관 복구 (보관 전 상태로 되돌림)"),
        ("unlock", cmd_unlock, "로그인 잠금 해제"),
        ("sessions", cmd_sessions, "활성 세션 조회"),
        ("revoke-sessions", cmd_revoke_sessions, "모든 세션 폐기"),
        ("verify-notion", cmd_verify_notion, "Notion 매핑 검증"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--email", required=True)
        p.set_defaults(func=func)

    p = sub.add_parser("passwd", help="비밀번호 재설정 (stdin 또는 --temp)")
    p.add_argument("--email", required=True)
    p.add_argument("--temp", action="store_true", help="임시 비밀번호 자동 생성")
    p.set_defaults(func=cmd_passwd)

    p = sub.add_parser("set-role", help="역할 변경")
    p.add_argument("--email", required=True)
    p.add_argument("--role", required=True, choices=sorted(ALL_ROLES))
    p.set_defaults(func=cmd_set_role)

    # 부서·직책 명부. 이름은 여기(그리고 관리자 콘솔) 한 곳에만 있고, 사용자는 그것을
    # 가리킨다 — 이름을 바꾸면 그 부서의 전원에게 반영된다.
    for kind, noun in [("department", "부서"), ("job_title", "직책")]:
        cli_name = "dept" if kind == "department" else "title"
        p = sub.add_parser(f"{cli_name}-add", help=f"{noun} 추가")
        p.add_argument("--name", required=True)
        p.set_defaults(func=cmd_org_add, kind=kind)

        p = sub.add_parser(f"{cli_name}-list", help=f"{noun} 목록 (사용자 수 포함)")
        p.set_defaults(func=cmd_org_list, kind=kind)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    session_service = SessionService(settings, SystemClock())
    with factory() as db:
        try:
            return args.func(db, session_service, settings, args)
        except AppError as exc:
            db.rollback()
            print(f"오류: {exc.message}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
