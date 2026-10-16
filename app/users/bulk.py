"""사용자 대량 작업 + CSV 가져오기/내보내기 (Phase 6).

## 부분 실패를 숨기지 않는다

대량 작업의 기본값은 "전부 성공 아니면 전부 롤백"이 아니라 **건별 처리 + 건별 결과**다.
200명 중 3명이 마지막 system_admin 이라 비활성화가 막혔다면, 나머지 197명은 처리하고 3명은
사유와 함께 돌려준다. 전부 롤백하면 관리자는 197번을 다시 손으로 눌러야 한다.

단, **인증·권한 실패는 건별 실패로 넘기지 않는다** — 그건 데이터 문제가 아니라 요청 자체가
잘못된 것이다. 범위 밖 id 는 "찾을 수 없음"으로 보고한다(존재를 알려 주지 않는다 — 단건
조회가 404 를 주는 것과 같은 이유. `app/core/scope.py` 참조).

## CSV 인젝션

엑셀·구글시트는 `=`, `+`, `-`, `@`, 탭, CR 로 시작하는 셀을 **수식으로 실행**한다. 사용자
표시 이름은 관리자가 자유롭게 입력하는 값이라 그대로 내보내면 내려받은 파일이 공격 경로가
된다(`=HYPERLINK(...)` 로 자격증명을 밖으로 보내는 고전적인 수법). 앞에 작은따옴표를 붙여
문자열로 고정한다 — 값 자체는 보존된다.

BOM 을 붙이는 이유: 국내 환경의 엑셀은 BOM 없는 UTF-8 CSV 를 CP949 로 읽어 한글이 전부
깨진다. 우리가 만드는 파일이므로 여기서 맞춰 준다.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError, ValidationAppError
from app.core.scope import Scope
from app.org.models import Department, JobTitle
from app.org.service import find_by_name
from app.users.models import ALL_ROLES, User
from app.users.schemas import display_name_problem, email_problem
from app.users.service import (
    archive_user,
    create_user,
    ensure_can_grant_role,
    ensure_can_manage_target,
    ensure_not_archived,
    get_scoped_user_or_404,
    set_user_active,
    unarchive_user,
    unlock_user,
    update_user,
    user_snapshot,
)

# 한 요청에서 다룰 수 있는 최대 인원. 요청 하나가 200번의 세션 폐기·스케줄 정리를 돌면
# 동기 워커 하나가 그만큼 잡혀 있다(WEB_WORKERS=1 고정, PLAN C10).
MAX_BULK_USERS = 200
# CSV 가져오기 한 번의 최대 행 수. 위와 같은 이유 + 실수로 만든 거대 파일 방어.
MAX_IMPORT_ROWS = 200

EXPORT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("email", "이메일"),
    ("display_name", "이름"),
    ("role", "역할"),
    ("active", "활성"),
    ("department", "부서"),
    ("title", "직책"),
    ("must_change_password", "비밀번호변경요구"),
    ("locked", "잠김"),
    ("archived_at", "보관시각"),
    ("last_login_at", "최근로그인"),
    ("created_at", "생성일"),
)

# 가져오기가 읽는 열. 한국어 헤더(내보내기와 같은 이름)와 영문 키를 둘 다 받는다 —
# 내보낸 파일을 고쳐서 그대로 다시 넣는 것이 가장 흔한 사용법이기 때문이다.
IMPORT_ALIASES: dict[str, str] = {
    "email": "email", "이메일": "email",
    "display_name": "display_name", "이름": "display_name", "name": "display_name",
    "role": "role", "역할": "role",
    "department": "department", "부서": "department",
    "title": "title", "직책": "title",
    "active": "active", "활성": "active",
}

_TRUE = {"true", "1", "y", "yes", "예", "활성", "o", "on"}
_FALSE = {"false", "0", "n", "no", "아니요", "아니오", "비활성", "x", "off"}

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    """수식으로 해석될 수 있는 셀을 문자열로 고정한다(모듈 docstring)."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _yn(value: bool) -> str:
    # 대답하는 말의 표준어는 「아니요」다(화면의 예/아니요 표시와 같은 말). 가져오기는 옛 파일의 「아니오」도 읽는다.
    return "예" if value else "아니요"


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def export_csv(rows: list[User], *, now: datetime) -> str:
    """현재 필터가 걸린 목록 그대로 CSV 로. 비밀번호 해시는 어떤 열에도 없다."""
    buffer = io.StringIO()
    # QUOTE_ALL — 이름에 콤마가 들어가도 열이 밀리지 않는다. lineterminator 를 고정하지
    # 않으면 플랫폼별로 CRLF/LF 가 달라져 골든 비교가 환경마다 갈라진다.
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow([label for _, label in EXPORT_COLUMNS])
    for user in rows:
        writer.writerow([
            csv_safe(user.email),
            csv_safe(user.display_name),
            csv_safe(user.role),
            _yn(user.active),
            csv_safe(user.department or ""),
            csv_safe(user.title or ""),
            _yn(user.must_change_password),
            _yn(bool(user.locked_until and user.locked_until > now)),
            _iso(user.archived_at),
            _iso(user.last_login_at),
            _iso(user.created_at),
        ])
    # BOM — 엑셀이 CP949 로 오해하지 않게(모듈 docstring).
    return "﻿" + buffer.getvalue()


# ── 가져오기 ──────────────────────────────────────────────────────────────────

def _csv_format_error(exc: csv.Error) -> ValidationAppError:
    """`csv` 모듈의 형식 오류를 이 API 의 검증 오류로 옮긴다.

    `csv` 는 한 칸이 `csv.field_size_limit()`(기본 131072자)를 넘으면 `_csv.Error` 를 던진다.
    그 예외를 그대로 두면 500 「Internal server error」 가 나가고, 붙여 넣은 사람은 자기
    파일의 어디가 문제인지 알 방법이 없다 — 이 함수의 약속은 「형식 오류는 여기서 전부
    잡는다」이므로 사유를 담아 422 로 돌려준다. 한도를 올리지 않는 이유: 한 칸이 128KB 를
    넘는 CSV 는 사람이 만든 명부가 아니라 잘못 붙여 넣은 파일이다.

    사유를 나눠 적는 이유: `csv` 는 칸 크기 말고도 따옴표가 안 닫힌 줄·NUL 문자에도 같은
    예외를 던진다. 어느 경우든 「칸이 너무 큽니다」라고 답하면 그 안내를 따라가는 사람은
    엉뚱한 곳을 고치게 된다.
    """
    if "field limit" in str(exc):
        return ValidationAppError(
            f"CSV 한 칸에 담긴 값이 너무 깁니다. 한 칸은 {csv.field_size_limit()}자까지 담을 수 있습니다."
        )
    return ValidationAppError(
        "CSV 형식이 올바르지 않아 읽을 수 없습니다. 따옴표와 줄바꿈이 짝을 이루는지 확인해 주세요."
    )


def _rows_of(reader: csv.DictReader):
    """행을 하나씩 내주되 `csv` 형식 오류는 422 로 바꾼다(`_csv_format_error`).

    데이터 행에서 터지는 오류라 헤더를 읽을 때와 자리가 다르다 — 둘 다 막아야 「형식 오류는
    여기서 전부 잡는다」가 사실이 된다.
    """
    while True:
        try:
            yield next(reader)
        except StopIteration:
            return
        except csv.Error as exc:
            raise _csv_format_error(exc) from exc


def parse_import_csv(text: str) -> list[dict]:
    """CSV 문자열 → 정규화된 행 목록. 형식 오류는 여기서 **전부** 잡는다.

    한 행이라도 파싱이 안 되면 그 행만 error 를 달고 계속 간다 — 100행짜리 파일에서 3행이
    잘못됐다고 전부 거절하면 사용자는 어느 3행인지 알아내려고 이분 탐색을 하게 된다.
    """
    if not text or not text.strip():
        raise ValidationAppError("CSV 내용이 비어 있습니다.")
    stripped = text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(stripped))
    try:
        fieldnames = reader.fieldnames
    except csv.Error as exc:
        raise _csv_format_error(exc) from exc
    if not fieldnames:
        raise ValidationAppError("CSV 헤더 행을 찾지 못했습니다.")
    mapping = {}
    for raw in reader.fieldnames:
        key = IMPORT_ALIASES.get((raw or "").strip().lower())
        if key and key not in mapping.values():
            mapping[raw] = key
    if "email" not in mapping.values() or "display_name" not in mapping.values():
        raise ValidationAppError(
            "CSV 에 '이메일'(email)과 '이름'(display_name) 열이 있어야 합니다. "
            f"찾은 열: {', '.join(reader.fieldnames)}"
        )

    rows: list[dict] = []
    row_source = _rows_of(reader)
    for index, raw_row in enumerate(row_source, start=2):  # 2 = 헤더 다음 줄(사람이 세는 줄 번호)
        if len(rows) >= MAX_IMPORT_ROWS:
            raise ValidationAppError(
                f"한 번에 가져올 수 있는 행은 {MAX_IMPORT_ROWS}개까지입니다. 파일을 나눠 주세요."
            )
        values = {
            key: (raw_row.get(header) or "").strip()
            for header, key in mapping.items()
        }
        if not any(values.values()):
            continue  # 빈 줄은 조용히 건너뛴다(엑셀이 흔히 남긴다)
        row: dict = {"line": index, **values, "error": None}
        if not row.get("email"):
            row["error"] = "이메일이 비어 있습니다."
        elif not row.get("display_name"):
            row["error"] = "이름이 비어 있습니다."
        else:
            # 단건 생성이 스키마에서 거르는 것과 **같은 규칙**을 여기서도 건다
            # (app/users/schemas.py). 예전에는 이 검사가 pydantic 스키마에만 있어서 CSV 는
            # 그대로 지나갔고, 두 가지가 동시에 깨졌다: 단건이 422 로 막는 주소
            # ("a@b@회사.com" · @ 없는 값)로 계정이 만들어졌고, 컬럼 길이를 넘는 값은
            # 미리보기에서 「추가 예정」이라고 말해 놓고 적용에서 DB 가 거절해 **파일 전체가
            # 롤백**됐다. 여기서 줄마다 잡으면 나쁜 줄만 실패로 남고 나머지는 만들어진다.
            row["error"] = email_problem(row["email"]) or display_name_problem(
                row["display_name"]
            )
            role = (row.get("role") or "").strip() or "user"
            if role not in ALL_ROLES:
                row["error"] = row["error"] or f"알 수 없는 역할입니다: {role}"
            row["role"] = role
        active_raw = (row.get("active") or "").strip().lower()
        if active_raw and active_raw not in _TRUE and active_raw not in _FALSE:
            row["error"] = row["error"] or f"활성 값을 해석할 수 없습니다: {active_raw}"
        row["active"] = active_raw not in _FALSE if active_raw else True
        rows.append(row)
    if not rows:
        raise ValidationAppError("가져올 데이터 행이 없습니다(헤더만 있습니다).")
    return rows


def import_users(
    db: Session, rows: list[dict], *, actor: User, scope: Scope, settings,
    effective_settings: dict | None, dry_run: bool,
) -> dict:
    """CSV 행을 계정으로. **새 계정 생성만 한다** — 기존 계정은 건드리지 않는다.

    가져오기가 기존 계정을 수정까지 하면, 한 줄 오타가 살아 있는 계정의 역할·부서를 조용히
    바꾼다. 기존 계정 변경은 화면의 대량 작업(부서/직책 일괄 지정)으로 하고, 그건 무엇이
    바뀔지 눈으로 고른 대상에만 적용된다.

    `dry_run=True` 가 기본이다. 미리보기 없이 100명이 생기는 버튼은 아무도 못 누른다.
    """
    from app.core.security import generate_temp_password
    from app.org.service import resolve_assignable
    from app.users.service import get_user_by_email

    results: list[dict] = []
    created = skipped = failed = 0
    seen_emails: set[str] = set()

    for row in rows:
        out = {
            "line": row["line"], "email": row.get("email", ""),
            "display_name": row.get("display_name", ""), "role": row.get("role", "user"),
        }
        if row.get("error"):
            out.update(status="failed", message=row["error"])
            failed += 1
            results.append(out)
            continue
        email = row["email"].strip().lower()
        if email in seen_emails:
            out.update(status="skipped", message="같은 파일 안에 중복된 이메일입니다.")
            skipped += 1
            results.append(out)
            continue
        seen_emails.add(email)
        if get_user_by_email(db, email) is not None:
            out.update(status="skipped", message="이미 있는 이메일입니다(가져오기는 새 계정만 만듭니다).")
            skipped += 1
            results.append(out)
            continue

        dept_id = _lookup_name_id(db, Department, row.get("department"), out)
        title_id = _lookup_name_id(db, JobTitle, row.get("title"), out)
        if out.get("status") == "failed":
            failed += 1
            results.append(out)
            continue

        if dry_run:
            # 만들지 않고, 만들었을 때 범위 밖이 되는지·권한 상승 요청인지까지 미리 본다 —
            # 실행 단계에서만 알게 되면 "미리보기는 초록이었는데 실행은 빨갛다"가 된다.
            # SEC-30: role 검사도 실제 create_user() 가 던지는 것과 같은 규칙
            # (ensure_can_grant_role)이어야 두 판정이 갈라지지 않는다.
            try:
                ensure_can_grant_role(actor.role, row.get("role") or "user")
            except AppError as exc:
                out.update(status="failed", message=exc.message)
                failed += 1
            else:
                if not _dept_in_scope(scope, dept_id):
                    out.update(status="failed", message="관리 범위 밖 부서로는 계정을 만들 수 없습니다.")
                    failed += 1
                else:
                    out.update(status="ready", message="새로 만들 계정입니다.")
                    created += 1
            results.append(out)
            continue

        try:
            user = create_user(
                db, email=email, display_name=row["display_name"],
                password=generate_temp_password(), settings=settings,
                actor_role=actor.role,
                role=row.get("role") or "user", active=bool(row.get("active", True)),
                must_change_password=True, department_id=dept_id, title_id=title_id,
                created_by=actor.id, effective_settings=effective_settings,
            )
            _ = resolve_assignable  # 위 create_user 가 이미 명부 검증을 한다
        except AppError as exc:
            out.update(status="failed", message=exc.message)
            failed += 1
        else:
            from app.core.scope import scope_allows_user

            if not scope_allows_user(scope, user):
                # 범위 밖 계정을 만드는 우회로를 막는다(단건 생성과 같은 규칙, users/router.py).
                # 여기서 예외를 던지면 요청 전체가 롤백되어 앞선 행들도 사라지므로, 그 대신
                # 방금 만든 행만 되돌린다.
                db.delete(user)
                db.flush()
                out.update(status="failed", message="관리 범위 밖 부서로는 계정을 만들 수 없습니다.")
                failed += 1
            else:
                out.update(status="created", message="계정을 만들었습니다(임시 비밀번호 발급).",
                           user_id=user.id)
                created += 1
        results.append(out)

    return {
        "dry_run": dry_run,
        "total": len(rows),
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


def _lookup_name_id(db: Session, model, name: str | None, out: dict) -> str | None:
    """이름 → id. CSV 는 사람이 쓰는 파일이라 UUID 가 아니라 이름이 들어온다."""
    clean = (name or "").strip()
    if not clean:
        return None
    row = find_by_name(db, model, clean)
    if row is None:
        from app.org.service import label_for

        out.update(status="failed", message=f"알 수 없는 {label_for(model)}입니다: {clean}")
        return None
    if not row.active:
        from app.org.service import label_for

        out.update(status="failed", message=f"비활성 {label_for(model)}입니다: {clean}")
        return None
    return row.id


def _dept_in_scope(scope: Scope, dept_id: str | None) -> bool:
    if scope.is_global:
        return True
    if scope.is_org:
        return True  # 조직 범위는 부서로 좁히지 않는다(scope_allows_user 와 같은 규칙)
    return bool(dept_id) and dept_id in scope.dept_ids


# ── 대량 작업 ─────────────────────────────────────────────────────────────────

BULK_ACTIONS = (
    "enable", "disable", "archive", "unarchive", "unlock",
    "revoke_sessions", "set_department", "set_title",
)

_ACTION_LABELS = {
    "enable": "활성화", "disable": "비활성화", "archive": "보관", "unarchive": "보관 복구",
    "unlock": "잠금 해제", "revoke_sessions": "세션 해제",
    "set_department": "부서 지정", "set_title": "직책 지정",
}

# 보관된 행을 **찾아야 하는** 작업. 복구는 당연히 그 행이 대상이고, 보관은 이미 보관된
# 계정에 대해 아무것도 바꾸지 않는 멱등 요청이라 없는 것처럼 답할 이유가 없다.
ARCHIVE_SAFE_ACTIONS = ("archive", "unarchive")


def bulk_apply(
    db: Session, *, user_ids: list[str], action: str, value: str | None,
    actor: User, scope: Scope, session_service, now: datetime,
) -> dict:
    """건별로 적용하고 건별로 결과를 돌려준다. 감사 기록은 부르는 쪽(라우터)이 남긴다."""
    if action not in BULK_ACTIONS:
        raise ValidationAppError(f"알 수 없는 작업입니다: {action}")
    if not user_ids:
        raise ValidationAppError("대상을 하나 이상 선택하세요.")
    if len(user_ids) > MAX_BULK_USERS:
        raise ValidationAppError(
            f"한 번에 처리할 수 있는 대상은 {MAX_BULK_USERS}명까지입니다. 나눠서 실행하세요."
        )
    if action in ("set_department", "set_title") and value:
        model = Department if action == "set_department" else JobTitle
        if db.get(model, value) is None:
            raise ValidationAppError("알 수 없는 대상 항목입니다.")

    applied: list[dict] = []
    failed: list[dict] = []
    for user_id in dict.fromkeys(user_ids):  # 중복 제거(순서 보존)
        user = None
        try:
            user = get_scoped_user_or_404(db, user_id, scope)
            if action not in ARCHIVE_SAFE_ACTIONS:
                # 보관된 계정은 쓰기 경로에서 없는 것과 같다(users/service.py
                # ensure_not_archived) — 단건 경로와 같은 판정을 여기서도 한다. 안 그러면
                # 화면이 편집 동작을 숨긴 보관 행이 일괄 작업으로는 그대로 바뀐다.
                ensure_not_archived(user)
            before = user_snapshot(user)
            changed = _apply_one(
                db, user, action=action, value=value, actor=actor,
                session_service=session_service, now=now,
            )
            applied.append({
                "id": user.id, "email": user.email, "display_name": user.display_name,
                "changed": changed, "before": before, "after": user_snapshot(user),
            })
        except AppError as exc:
            # 실패 건도 **누구인지** 함께 돌려준다. id 와 사유만 주면 화면은 「2명 실패」까지만
            # 말할 수 있고, 관리자는 40명 중 어느 둘이 왜 남았는지 알 방법이 없다.
            # 범위 밖·보관 계정(404)은 존재 자체를 숨기는 자리라 id 만 남긴다 — 이름을 실으면
            # 404 로 가린 것이 그 줄에서 다시 새 나간다.
            entry = {"id": user_id, "error": exc.message}
            if user is not None and user.archived_at is None:
                entry["email"] = user.email
                entry["display_name"] = user.display_name
            failed.append(entry)
    return {
        "action": action,
        "action_label": _ACTION_LABELS[action],
        "requested": len(user_ids),
        "applied": applied,
        "failed": failed,
    }


def _apply_one(
    db: Session, user: User, *, action: str, value: str | None, actor: User,
    session_service, now: datetime,
) -> bool:
    """한 명에게 적용. 이미 그 상태면 False(=바꾼 것 없음)."""
    if action == "enable":
        if user.active:
            return False
        set_user_active(db, user, True, session_service=session_service, actor_role=actor.role)
        return True
    if action == "disable":
        if not user.active:
            return False
        _refuse_self(actor, user, "비활성화")
        set_user_active(db, user, False, session_service=session_service, actor_role=actor.role)
        return True
    if action == "archive":
        if user.archived_at is not None:
            return False
        _refuse_self(actor, user, "보관")
        archive_user(
            db, user, session_service=session_service, actor_role=actor.role,
            actor_id=actor.id, now=now,
        )
        return True
    if action == "unarchive":
        if user.archived_at is None:
            return False
        unarchive_user(db, user, actor_role=actor.role)
        return True
    if action == "unlock":
        if not user.locked_until and not user.failed_login_count:
            return False
        unlock_user(db, user, actor_role=actor.role)
        return True
    if action == "revoke_sessions":
        ensure_can_manage_target(actor.role, user)
        _refuse_self(actor, user, "세션 해제")
        return bool(session_service.revoke_all_for_user(db, user.id))
    if action == "set_department":
        if user.department_id == (value or None):
            return False
        update_user(
            db, user, session_service=session_service, actor_role=actor.role,
            department_id=value or None,
        )
        return True
    # set_title
    if user.title_id == (value or None):
        return False
    update_user(
        db, user, session_service=session_service, actor_role=actor.role,
        title_id=value or None,
    )
    return True


def _refuse_self(actor: User, user: User, what: str) -> None:
    """자기 자신에게 적용하면 그 자리에서 자기 세션이 끊긴다 — 대량 작업에서는 특히 위험하다
    (200명을 고르다 자기가 섞여 들어간 것을 알아채기 어렵다)."""
    if actor.id == user.id:
        raise ValidationAppError(f"본인 계정은 {what}할 수 없습니다.")
