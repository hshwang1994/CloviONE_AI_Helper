"""온보딩·오프보딩 서비스 (Phase 6).

계획서가 이 그룹의 **최우선**으로 지목한 항목이다: *"퇴사자 보유 티켓 재배정 — `ticket_cache`
+RBAC 가 둘 다 필요한 유일한 항목이자 현재 실제 운영 공백"*. 두 조각이 다 들어왔으므로 여기서
잇는다.

## 이 모듈이 지키는 네 가지

1. **미리 보여 주고 확인받는다.** `preview()` 없이 실행하는 경로를 두지 않는다. 화면은 "이
   사람의 티켓 N건을 누구에게 옮길지"를 먼저 보여 주고, 실행은 사용자가 고른 page_id 목록만
   대상으로 한다(서버가 알아서 전부 옮기지 않는다).
2. **부분 실패를 숨기지 않는다.** 12건 중 3건이 Notion 에서 실패하면 3건을 실패로 적고
   상태를 `partial` 로 남긴다. 실패한 건은 되돌리기 대상이 아니다(애초에 안 바뀌었다).
3. **되돌릴 수 있다.** 옮기기 직전의 담당자 구성을 앱 user_id 로 기록하고, `undo()` 가 그
   구성으로 되돌린다. 계정 상태도 이 실행이 **실제로 바꾼 것만** 되돌린다.
4. **순서가 계약이다.** 티켓을 먼저 옮기고 그다음 계정을 비활성화한다. 되돌리기는 정확히
   반대 순서다 — 계정을 먼저 살리고 그다음 티켓을 되돌린다.

   왜냐하면 담당자 해석(`app/tickets/service.py::_assignee_id_to_user`)이 **active + 미보관**
   사용자만 본다. 비활성화가 먼저 일어나면 퇴사자의 담당자 토큰이 '앱이 모르는 외부 담당자'로
   보여 쓰기 경로가 그를 **보존**해 버린다 — 즉 티켓이 옮겨지지 않는다. 되돌리기에서도 계정을
   먼저 살리지 않으면 퇴사자를 담당자로 다시 넣을 수 없다(`_resolve_assignee_ids` 가 거절한다).
   이 두 문장이 이 모듈에서 가장 잘 깨지기 쉬운 부분이라 테스트로 못박아 두었다.

## 범위(RBAC)

대상·후임 모두 `get_scoped_user_or_404` 를 지난다 — 부서 관리자는 남의 부서 사람을 오프보딩
할 수 없고, 그때 응답은 403 이 아니라 **404** 다(존재 자체를 알려 주지 않는다).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import is_insert_race
from app.core.errors import AppError, ConflictError, ValidationAppError
from app.core.models_base import join_names, split_names, utcnow
from app.core.scope import apply_user_scope
from app.offboarding.models import (
    MOVE_FAILED,
    MOVE_MOVED,
    MOVE_PENDING,
    MOVE_REVERT_FAILED,
    MOVE_REVERTED,
    MOVE_SKIPPED,
    REVERTIBLE_MOVES,
    RUN_COMPLETED,
    RUN_PARTIAL,
    RUN_RUNNING,
    RUN_UNDO_PARTIAL,
    RUN_UNDONE,
    OffboardingRun,
    OffboardingTicketMove,
)
from app.tickets import service as tickets
from app.users.models import User
from app.users.service import (
    archive_user,
    ensure_can_manage_target,
    ensure_not_self,
    get_scoped_user_or_404,
    set_user_active,
    unarchive_user,
)

logger = logging.getLogger("app.offboarding")

# 한 번에 옮길 수 있는 티켓 수 상한. 건마다 Notion 왕복이 두 번(읽기+쓰기)이라 상한이 없으면
# 요청 하나가 몇 분씩 걸리고 그 사이 타임아웃이 나면 '절반만 옮겨진' 상태의 원인을 알기 어렵다.
MAX_TICKETS_PER_RUN = 100


# ── 미리보기 ──────────────────────────────────────────────────────────────────

def preview(
    db: Session, outbound, settings, *, target: User, actor: User, repo=None
) -> dict:
    """오프보딩 전에 보여 줄 모든 것 — 온보딩 상태 점검 + 보유 티켓 + 후임 후보.

    티켓 조회 실패는 **감추지 않는다**. Notion 이 안 되는 순간 목록이 빈 채로 뜨면 관리자는
    "이 사람은 티켓이 없구나" 하고 그대로 실행해 버린다(그리고 티켓은 퇴사자에게 남는다).
    """
    tickets_error: str | None = None
    held: list[dict] = []
    try:
        result = tickets.list_my_tickets(db, outbound, settings, target, repo=repo)
        held = list(result.get("tickets") or [])
    except Exception as exc:  # noqa: BLE001 — 원인은 화면에 그대로 알린다
        tickets_error = getattr(exc, "message", None) or f"티켓 조회 실패: {type(exc).__name__}"

    return {
        "user": _user_brief(target),
        # 온보딩 점검표 — 같은 화면에서 '들어올 때 갖춰야 할 것'을 그대로 뒤집어 쓴다.
        "onboarding": _onboarding_checklist(db, target),
        "tickets": held,
        "ticket_count": len(held),
        "tickets_error": tickets_error,
        "successor_candidates": _successor_candidates(db, actor, exclude_user_id=target.id),
        "max_tickets_per_run": MAX_TICKETS_PER_RUN,
        # 이 사람에 대해 아직 되돌리지 않은 실행이 있으면 중복 실행을 경고한다.
        "open_run": _open_run_view(db, target.id),
    }


def _user_brief(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "active": user.active,
        "archived_at": user.archived_at.isoformat() if user.archived_at else None,
        "department": user.department,
        "department_id": user.department_id,
        "title": user.title,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _onboarding_checklist(db: Session, user: User) -> list[dict]:
    """'이 계정이 일할 준비가 됐는가'를 그대로 뒤집어 오프보딩 점검에도 쓴다.

    항목은 전부 **이 저장소가 실제로 강제하는 것**만 담는다. 지키지 않아도 아무 일도 없는
    형식적 체크박스를 넣으면 점검표 전체가 장식이 된다.
    """
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    notion_status = db.execute(
        select(UserNotionMapping.status).where(UserNotionMapping.user_id == user.id)
    ).scalar_one_or_none()
    return [
        {"key": "department", "label": "부서 배정", "ok": bool(user.department_id),
         "value": user.department or "-",
         "help": "부서가 없으면 부서 관리자의 화면에 이 사람이 보이지 않습니다."},
        {"key": "title", "label": "직책 배정", "ok": bool(user.title_id),
         "value": user.title or "-"},
        {"key": "notion", "label": "Notion 사용자 연결", "ok": notion_status == STATUS_VERIFIED,
         "value": notion_status or "unmapped",
         "help": "연결이 없으면 이 사람이 담당한 티켓을 조회할 수 없어 재배정도 할 수 없습니다."},
        {"key": "login", "label": "첫 로그인 완료", "ok": user.last_login_at is not None,
         "value": user.last_login_at.isoformat() if user.last_login_at else "-"},
    ]


def _successor_candidates(db: Session, actor: User, *, exclude_user_id: str) -> list[dict]:
    """후임 후보 = **행위자의 관리 범위 안**에서 Notion 연결이 확인된 활성 사용자.

    범위를 안 걸면 부서 관리자가 남의 부서 사람에게 티켓을 떠넘길 수 있다 — 그 사람은 자기
    화면에서 그 티켓이 어디서 왔는지 알 방법이 없다.
    """
    from app.core.scope import management_scope
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    stmt = (
        select(User)
        .join(UserNotionMapping, UserNotionMapping.user_id == User.id)
        .where(
            User.id != exclude_user_id,
            User.active.is_(True),
            User.archived_at.is_(None),
            UserNotionMapping.status == STATUS_VERIFIED,
            UserNotionMapping.notion_user_id.is_not(None),
        )
    )
    stmt = apply_user_scope(stmt, management_scope(db, actor))
    rows = db.execute(stmt.order_by(User.display_name)).scalars().all()
    return [
        {"user_id": u.id, "display_name": u.display_name, "email": u.email,
         "department": u.department}
        for u in rows
    ]


def _open_run_view(db: Session, user_id: str) -> dict | None:
    row = db.execute(
        select(OffboardingRun)
        .where(OffboardingRun.user_id == user_id, OffboardingRun.undone_at.is_(None))
        .order_by(OffboardingRun.created_at.desc(), OffboardingRun.id.desc())
    ).scalars().first()
    return run_view(row) if row is not None else None


# ── 실행 ──────────────────────────────────────────────────────────────────────

def run_offboarding(
    db: Session, outbound, settings, *, actor: User, target: User,
    successor: User | None, page_ids: list[str], deactivate: bool, archive: bool,
    session_service, note: str | None = None, now: datetime | None = None, repo=None,
) -> dict:
    """티켓을 먼저 옮기고, 그다음 계정을 처리한다. 순서는 모듈 docstring 참조."""
    stamp = now or utcnow()
    ensure_can_manage_target(actor.role, target)
    if actor.id == target.id:
        raise ConflictError("자기 자신을 오프보딩할 수 없습니다. 다른 관리자에게 요청하세요.")
    if successor is not None and successor.id == target.id:
        raise ValidationAppError("후임은 퇴사자 본인일 수 없습니다.")
    if len(page_ids) > MAX_TICKETS_PER_RUN:
        raise ValidationAppError(
            f"한 번에 옮길 수 있는 티켓은 {MAX_TICKETS_PER_RUN}건까지입니다. 나눠서 실행하세요."
        )
    if not page_ids and not deactivate and not archive:
        raise ValidationAppError("옮길 티켓도, 계정에 적용할 변경도 없습니다.")

    # UA-15: 이 대상에게 이미 열린(안 되돌린) 실행이 있으면 새로 시작하지 않는다 — 더블클릭·
    # 새로고침으로 거의 동시에 두 번 실행되면, 아래에서 장부를 먼저 커밋한 뒤 시작하는 두
    # 번째 요청의 OffboardingTicketMove.before_user_ids가 이미 첫 번째 실행이 넣은 후임을
    # "원래 담당자"로 기록해 버려 되돌리기 계약이 깨진다(후임에게서 후임으로 되돌리는 꼴).
    # 빠른 경로(사전 확인)만으로는 진짜 동시 요청을 못 막으므로, migration 0056의 부분 유일
    # 인덱스(user_id, undone_at IS NULL) 위반도 같은 409로 잡는다(느린 경로, approvals의
    # 0052/prompts의 0053과 같은 관용).
    if _open_run_view(db, target.id) is not None:
        raise ConflictError(
            "이미 진행 중이거나 되돌리지 않은 오프보딩 실행이 있습니다. 먼저 처리해 주세요."
        )

    run = OffboardingRun(
        user_id=target.id,
        actor_user_id=actor.id,
        successor_user_id=successor.id if successor else None,
        note=(note or "").strip() or None,
        ticket_total=len(page_ids),
        org_id=getattr(target, "org_id", None),
        created_at=stamp,
        updated_at=stamp,
    )
    run.status = RUN_RUNNING
    db.add(run)
    # **장부를 먼저 커밋한다** (C3). 이 아래는 전부 Notion 을 실제로 바꾸는 일이고,
    # `get_db` 는 예외가 나면 요청 세션을 통째로 롤백한다 — 한 트랜잭션에 두면
    # 마지막 단계(계정 처리)에서 실패했을 때 **Notion 재배정은 남고 그 사실을 아는 행은
    # 전부 사라진다**. 되돌리기의 입력이 사라지므로 복구도 불가능하다.
    # (같은 논거가 `core/deps.py::_count_blocked_write` 에 이미 적혀 있다.)
    try:
        db.commit()
    except (IntegrityError, OperationalError) as exc:
        if not is_insert_race(exc):
            raise
        db.rollback()
        raise ConflictError(
            "이미 진행 중이거나 되돌리지 않은 오프보딩 실행이 있습니다. 먼저 처리해 주세요."
        ) from None

    moves = _move_tickets(
        db, outbound, settings, actor=actor, target=target, successor=successor,
        page_ids=page_ids, run=run, now=stamp, repo=repo,
    )
    run.ticket_moved = sum(1 for m in moves if m.status == MOVE_MOVED)
    run.ticket_failed = sum(1 for m in moves if m.status == MOVE_FAILED)
    db.commit()   # 티켓 결과는 계정 처리 성패와 무관하게 남아야 한다

    # 채팅방 방장직 이전 (X8). 티켓만 넘기고 방을 두면 퇴사자가 방장으로 남아
    # **아무도 그 방을 관리할 수 없다** — 그런데 관리자는 "완료" 를 보고 끝났다고 믿는다.
    # 계정 처리 **앞**이다: 비활성/보관된 계정을 멤버 후보로 다루지 않으려면 아직 살아
    # 있는 동안 정리해야 한다(티켓과 같은 순서 논리).
    from app.team_chat.service import transfer_owned_rooms

    run.rooms_transferred = transfer_owned_rooms(db, target=target, successor=successor)
    db.commit()   # 방 결과도 계정 처리 성패와 무관하게 남아야 한다

    # 계정 처리는 티켓 이동 **뒤**다(순서가 계약 — 모듈 docstring).
    # 이미 그 상태이던 계정은 건드리지 않았다고 기록한다 — 되돌리기가 없던 권한을 주지 않게.
    if deactivate and target.active:
        set_user_active(
            db, target, False, session_service=session_service, actor_role=actor.role,
        )
        run.deactivated = True
    if archive and target.archived_at is None:
        ensure_not_self(actor.id, target)
        archive_user(
            db, target, session_service=session_service, actor_role=actor.role,
            actor_id=actor.id, now=stamp,
        )
        run.archived = True

    # 넘겨받은 사람에게 통보한다 (N2). 계정 처리 뒤에 두는 이유는 없다 — 여기 있는 것은
    # 티켓, 방, 계정이 모두 정리된 **최종 결과**를 한 문장으로 적기 위해서다.
    _notify_handover(db, actor=actor, target=target, successor=successor, run=run, now=stamp)

    # 상태를 **마지막에** 확정한다. 여기까지 못 오면 행은 `running` 으로 남는다 — 그게
    # 사실이다. 앞에서 `completed` 로 적어 두면 중단된 실행이 "다 끝났다"고 거짓말한다.
    run.status = RUN_PARTIAL if run.ticket_failed else RUN_COMPLETED
    run.updated_at = stamp
    db.flush()
    return {"run": run_view(run, moves), "moves": [move_view(m) for m in moves]}


def _notify_handover(
    db: Session, *, actor: User, target: User, successor: User | None,
    run: OffboardingRun, now: datetime,
) -> None:
    """후임에게 "무엇을 넘겨받았는지"를 **한 건**으로 알린다 (N2).

    감사 확인: 티켓과 방을 넘겨받은 사람이 그 사실을 통보받지 못했다. 관리자는 마법사에서
    "완료"를 보고 끝났다고 믿는데, 정작 그 일을 하게 된 사람만 모르는 상태였다.

    ## 왜 요약 한 건인가

    건별 알림은 `replace_ticket_assignee(notify=False)` 로 껐다. 오프보딩은 티켓을 100건까지
    한 번에 옮길 수 있어서(MAX_TICKETS_PER_RUN), 건별로 보내면 배지에 100 이 찍힌다.
    그건 통보가 아니라 사고고, 한 번 겪은 사람은 그다음부터 배지를 안 본다.

    ## 안 보내는 경우

      * 후임이 없다(미할당으로 보냈다) — 받을 사람이 없다.
      * 후임이 **실행한 관리자 본인**이다 — 자기가 방금 한 일을 자기에게 알리지 않는다.
      * 실제로 넘어간 것이 하나도 없다(티켓 0건 + 방 0건) — 알릴 사건이 없다.

    ## 딥링크

    관련 객체를 싣지 않는다. 넘어간 티켓이 여럿이라 가리킬 단건이 없고, 오프보딩 실행 기록은
    관리자 화면이라 후임(대개 일반 사용자)은 열 수 없다. 없는 목적지를 만들어 붙이면
    "눌러도 아무 일이 없는 알림"이 되므로 본문으로 어디를 볼지 적는다.

    ## 실패해도 오프보딩은 되돌아가지 않는다

    이 시점에는 Notion 이 이미 바뀌었고 그 사실을 적은 행도 커밋됐다. 알림 하나 때문에
    예외를 위로 던지면 요청이 롤백되면서 **되돌리기의 입력이 사라진다** — 그래서 삼키되,
    삼킨 사실은 로그에 남긴다.
    """
    if successor is None or successor.id == actor.id:
        return
    moved = int(run.ticket_moved or 0)
    rooms = int(run.rooms_transferred or 0)
    if moved == 0 and rooms == 0:
        return
    try:
        from app.notifications.service import notify_user

        parts = []
        if moved:
            parts.append(f"티켓 {moved}건")
        if rooms:
            parts.append(f"채팅방 {rooms}개")
        notify_user(
            db, successor.id, type_="offboarding_handover",
            title=f"{target.display_name} 님의 업무를 넘겨받았습니다",
            body=f"{', '.join(parts)}이(가) 내 담당으로 바뀌었습니다. 내 티켓 화면에서 확인하세요.",
            now=now,
        )
    except Exception:  # noqa: BLE001 — 알림이 오프보딩 기록을 되돌리면 안 된다
        logger.exception("오프보딩 인수 알림에 실패했다 (run_id=%s)", run.id)


def _move_tickets(
    db: Session, outbound, settings, *, actor: User, target: User, successor: User | None,
    page_ids: list[str], run: OffboardingRun, now: datetime, repo=None,
) -> list[OffboardingTicketMove]:
    """건별로 옮기고 건별로 기록한다. 한 건이 실패해도 나머지는 계속 간다."""
    moves: list[OffboardingTicketMove] = []
    for page_id in page_ids:
        move = OffboardingTicketMove(
            run_id=run.id, ticket_page_id=page_id, created_at=now, updated_at=now,
            status=MOVE_PENDING,
        )
        # 소스를 부르기 **전에** 적고 커밋한다. 이 왕복 도중에 죽으면 Notion 이 바뀌었는지
        # 알 수 없는데, 행이 없으면 그 티켓은 아무 흔적도 남지 않는다. `pending` 은
        # "확인이 필요한 건" 이라는 뜻이고, 되돌리기 대상은 아니다(직전 담당자를 아직 모른다).
        db.add(move)
        db.commit()
        try:
            result = tickets.replace_ticket_assignee(
                db, outbound, settings, actor, page_id=page_id,
                from_user_id=target.id,
                to_user_id=successor.id if successor else None,
                now=now, repo=repo,
                # 건별 배정 알림은 끈다. 100건을 넘기면 후임의 배지에 알림 100건이 꽂히는데
                # 그건 통보가 아니라 사고다 — 대신 `_notify_handover` 가 요약 한 건을 보낸다.
                notify=False,
            )
        except AppError as exc:
            move.status = MOVE_FAILED
            move.error = exc.message
        except Exception as exc:  # noqa: BLE001 — 외부 실패를 요청 전체의 실패로 키우지 않는다
            move.status = MOVE_FAILED
            move.error = f"티켓 재배정 실패: {type(exc).__name__}"
        else:
            ticket = result.get("ticket") or {}
            move.ticket_uid = ticket.get("uid")
            move.ticket_number = ticket.get("tid")
            move.ticket_key = ticket.get("key")
            move.ticket_title = (ticket.get("title") or "")[:500]
            move.before_user_ids = join_names(result["before_user_ids"])
            move.after_user_ids = join_names(result["after_user_ids"])
            move.status = MOVE_MOVED if result["changed"] else MOVE_SKIPPED
        move.updated_at = now
        # 한 건이 끝날 때마다 확정한다 — 다음 건에서 무슨 일이 나든 이 결과는 남는다.
        db.commit()
        moves.append(move)
    return moves


# ── 되돌리기 ──────────────────────────────────────────────────────────────────

def undo(
    db: Session, outbound, settings, *, actor: User, run: OffboardingRun,
    session_service, now: datetime | None = None, repo=None,
) -> dict:
    """실행을 되돌린다 — **계정을 먼저 살리고 그다음 티켓**(순서는 모듈 docstring)."""
    stamp = now or utcnow()
    if run.undone_at is not None:
        raise ConflictError("이미 되돌린 실행입니다.")
    target = db.get(User, run.user_id)
    if target is None:
        raise ValidationAppError("대상 사용자를 찾을 수 없습니다.")
    ensure_can_manage_target(actor.role, target)

    if run.archived and target.archived_at is not None:
        unarchive_user(db, target, actor_role=actor.role)
    if run.deactivated and not target.active:
        set_user_active(
            db, target, True, session_service=session_service, actor_role=actor.role,
        )
    # 계정 복구를 먼저 확정한다 — 아래 티켓 되돌리기가 Notion 왕복이고, 거기서 죽으면
    # 계정만 잠긴 채 남는다(그리고 담당자 해석이 보관 계정을 안 봐서 재시도도 막힌다).
    db.commit()

    moves = _run_moves(db, run.id)
    failed = 0
    for move in moves:
        if move.status not in REVERTIBLE_MOVES:
            continue
        try:
            tickets.set_ticket_assignees(
                db, outbound, settings, actor, page_id=move.ticket_page_id,
                user_ids=split_names(move.before_user_ids), now=stamp, repo=repo,
                # 되돌리기도 같은 이유로 건별 알림을 끈다. 되돌리기는 '없던 일로 만드는'
                # 조작이라, 그 결과로 알림이 쏟아지면 사람들은 '또 뭘 배정받았나' 하고 본다.
                notify=False,
            )
        except AppError as exc:
            move.status = MOVE_REVERT_FAILED
            move.error = exc.message
            failed += 1
        except Exception as exc:  # noqa: BLE001
            move.status = MOVE_REVERT_FAILED
            move.error = f"되돌리기 실패: {type(exc).__name__}"
            failed += 1
        else:
            move.status = MOVE_REVERTED
            move.error = None
            move.reverted_at = stamp
        move.updated_at = stamp
        db.commit()   # 실행과 같은 이유 — 되돌린 건은 되돌린 채로 남는다

    # UA-14: undone_at은 "완전히 되돌렸다"는 뜻으로만 쓴다 — 실패 여부와 무관하게 여기서
    # 찍으면, 위 385행의 재시도 가드(`undone_at is not None`이면 409)가 부분 실패한 실행을
    # 영영 재시도 못 하게 막는다. REVERTIBLE_MOVES가 이미 MOVE_REVERT_FAILED를 재시도
    # 대상으로 넣어 둔 것(위 405행)과 정면으로 모순됐었다 — Notion이 불안정해 12건 중 3건이
    # 실패하면 그 3건은 후임자에게 영구히 남았다. 부분 실패면 undone_at을 비워 둬서 같은
    # run으로 다시 undo()를 부를 수 있게 한다(프런트는 `!sel.undone_at`로만 되돌리기 버튼을
    # 보여준다 — Offboarding.jsx — 그래서 백엔드만 고치면 된다).
    if not failed:
        run.undone_at = stamp
        run.undone_by_user_id = actor.id
    run.status = RUN_UNDO_PARTIAL if failed else RUN_UNDONE
    run.undo_error = (
        f"티켓 {failed}건을 되돌리지 못했습니다. 각 건의 사유를 확인하세요." if failed else None
    )
    db.flush()
    return {"run": run_view(run, moves), "moves": [move_view(m) for m in moves],
            "revert_failed": failed}


# ── 조회 ──────────────────────────────────────────────────────────────────────

def _run_moves(db: Session, run_id: str) -> list[OffboardingTicketMove]:
    return list(
        db.execute(
            select(OffboardingTicketMove)
            .where(OffboardingTicketMove.run_id == run_id)
            .order_by(OffboardingTicketMove.created_at, OffboardingTicketMove.id)
        ).scalars().all()
    )


def get_scoped_run_or_404(db: Session, run_id: str, scope) -> OffboardingRun:
    """범위를 존중하는 단건 조회. 범위 밖은 **404** — 사용자 단건과 같은 규칙이다.

    실행 기록은 대상 사용자에 대한 정보다. 그 사용자가 안 보이면 그 사람의 실행 기록도
    존재하지 않는 것과 같아야 한다(목록에서 가린 것이 단건에서 새면 가린 의미가 없다).
    """
    from app.core.errors import NotFoundError
    from app.core.scope import scope_allows_user

    run = db.get(OffboardingRun, run_id)
    if run is None:
        raise NotFoundError("오프보딩 실행 기록을 찾을 수 없습니다.")
    target = db.get(User, run.user_id)
    if target is None or not scope_allows_user(scope, target):
        raise NotFoundError("오프보딩 실행 기록을 찾을 수 없습니다.")
    return run


def list_runs(db: Session, scope, *, offset: int, limit: int) -> tuple[list[dict], int]:
    """실행 목록 — 대상 사용자가 범위 안인 것만. 관리 콘솔의 목록 화면이 그대로 쓴다."""
    stmt = select(OffboardingRun).join(User, User.id == OffboardingRun.user_id)
    stmt = apply_user_scope(stmt, scope)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(OffboardingRun.created_at.desc(), OffboardingRun.id.desc()).offset(offset).limit(limit)
    ).scalars().all()
    names = _name_map(db, rows)
    return [run_view(r, names=names) for r in rows], total


def _name_map(db: Session, runs) -> dict[str, str]:
    ids = {r.user_id for r in runs} | {r.actor_user_id for r in runs}
    ids |= {r.successor_user_id for r in runs if r.successor_user_id}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all()
    return {uid: name for uid, name in rows}


def run_detail(db: Session, run: OffboardingRun) -> dict:
    """단건 상세 — 실행 요약 + 티켓별 이동 기록. 라우터가 쓰는 유일한 조립 지점."""
    return run_view(run, _run_moves(db, run.id), names=_name_map(db, [run]))


def run_view(run: OffboardingRun, moves=None, *, names: dict[str, str] | None = None) -> dict:
    names = names or {}
    view = {
        "id": run.id,
        "user_id": run.user_id,
        "user_name": names.get(run.user_id),
        "actor_user_id": run.actor_user_id,
        "actor_name": names.get(run.actor_user_id),
        "successor_user_id": run.successor_user_id,
        "successor_name": names.get(run.successor_user_id) if run.successor_user_id else None,
        "status": run.status,
        "deactivated": run.deactivated,
        "archived": run.archived,
        "note": run.note,
        "ticket_total": run.ticket_total,
        "ticket_moved": run.ticket_moved,
        "ticket_failed": run.ticket_failed,
        # 화면이 "무엇을 했는가" 를 답할 수 있어야 한다 — 안 실으면 이력이 방 이전을 모른다(X8).
        "rooms_transferred": run.rooms_transferred,
        "undone_at": run.undone_at.isoformat() if run.undone_at else None,
        "undone_by_user_id": run.undone_by_user_id,
        "undo_error": run.undo_error,
        "created_at": run.created_at.isoformat(),
    }
    if moves is not None:
        view["moves"] = [move_view(m) for m in moves]
    return view


def move_view(move: OffboardingTicketMove) -> dict:
    return {
        "id": move.id,
        "ticket_page_id": move.ticket_page_id,
        "ticket_uid": move.ticket_uid,
        "tid": move.ticket_number,
        "key": move.ticket_key,
        "title": move.ticket_title,
        "before_user_ids": split_names(move.before_user_ids),
        "after_user_ids": split_names(move.after_user_ids),
        "status": move.status,
        "error": move.error,
        "reverted_at": move.reverted_at.isoformat() if move.reverted_at else None,
    }


def resolve_target(db: Session, user_id: str, scope) -> User:
    """대상 사용자 단건 — 범위 밖은 404(존재를 알려 주지 않는다)."""
    return get_scoped_user_or_404(db, user_id, scope)


